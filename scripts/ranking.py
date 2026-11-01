"""Satellite-map Shorts: one entry per beat, each a territory (or several) raised as a slab with its flag
on top, wiped in north to south while the camera flies to it, with a label and a counting number. Two formats:

  ranking   a title card, then a countdown: "N. name" and a counting area below the map
  timeline  no title card, entries as listed (present to past): name and a counting year above the map

scripts/make.py builds a Show from an episode's show.json; this module draws frames and encodes.

Default timing: a beat every `period` seconds, the camera's move takes 0.55 s, the wipe sweeps the map north to south
in 0.45 s from 0.12 s, the old label is half gone at 0.155 s and the new one half in at 0.235 s, the counter runs
0.45 s from 0.21 s.
"""
import math
import os
import subprocess
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import mapkit as mk

WHITE = (247, 247, 247)
GOLD = ((255, 216, 96), (242, 158, 46))  # top -> bottom gradient


@dataclass
class Entry:
    label: list            # [(text, 'white'|'gold'), ...] e.g. [('9.', 'gold'), (' 후고구려', 'white')]
    area: int              # the number the counter lands on (an area in km2 by default, see Show.unit)
    geom: object           # lon/lat shapely geometry of the territory
    texture: object        # function (w, h) -> RGB PIL image
    hold: tuple            # (view at the start of the hold, view at its end), views = (cx, cy, w)
    tex_geom: object = None  # geometry whose bounding box the texture spans (default: geom)
    count_from: int = None   # default: the previous entry's area (0 for the first)
    layers: list = field(default_factory=list)  # more territories shown with it: (geom, texture, tex_geom)


@dataclass
class Show:
    title: list            # lines, each [(text, colour), ...]; [] = no title card (the first entry opens at 0 s)
    title_views: tuple     # (view at 0 s, view when the first beat starts)
    entries: list
    t0: float = 3.10       # first beat
    period: float = 3.308  # seconds per entry
    total: float = 33.0
    fps: int = 60
    look: str = None       # a colour grade .npz (see mapkit.Look); None = the default grade
    unit: str = 'km²'      # printed after the counter
    step: int = 10         # the counter moves in steps of this
    region: tuple = mk.EAST_ASIA  # basemap area (lon0, lon1, lat0, lat1)
    ppd: int = mk.PPD      # basemap resolution, px per merc degree
    move: float = 0.55     # camera move per beat
    wipe: float = 0.45
    depth: int = 8         # slab side face, px
    seed: int = 7
    format: str = 'ranking'  # 'ranking' or 'timeline' (see LAYOUTS)
    beats: list = field(default_factory=list)

    def __post_init__(self):
        self.beats = [self.t0 + i * self.period for i in range(len(self.entries))]


# ---------------------------------------------------------------- timing curves


def move_ease(x):
    """The camera's moves: fast early, long settle (peak speed at ~40 % of the move)."""
    x = mk.clamp01(x) ** 0.85
    return x * x / (x * x + (1 - x) ** 2) if 0 < x < 1 else x


def view_at(show, t):
    tv0, tv1 = show.title_views
    if t < show.beats[0] and show.beats[0] > 0:
        return mk.lerp_view(tv0, tv1, mk.ease_inout(t / show.beats[0]))
    k = max(i for i, b in enumerate(show.beats) if b <= t)
    b = show.beats[k]
    s, e = show.entries[k].hold
    t_end = show.beats[k + 1] if k + 1 < len(show.beats) else show.total
    if t >= b + show.move:
        return mk.lerp_view(s, e, (t - b - show.move) / (t_end - b - show.move))
    prev = tv1 if k == 0 else show.entries[k - 1].hold[1]
    x = (t - b) / show.move
    v = mk.lerp_view(prev, s, move_ease(x))
    # a small zoom-out in the middle of short hops (+5 %); none on big zooms
    bump = 0.05 * max(0.0, 1 - abs(math.log(s[2] / prev[2])) / 0.2) * math.sin(math.pi * mk.clamp01(x))
    return (v[0], v[1], v[2] * (1 + bump))


def wipe_y(show, t, k, view, span):
    """Screen y of the wipe line for beat k (rows above it show the new entry). The line sweeps the map from the
    northern edge to the southern edge of the old and new territories (`span` = (top, bottom) in merc y), starting
    0.12 s into the beat, fast at first."""
    if k == 0 and not show.title:  # the opening entry is there from the first frame
        return 1e9
    x = (t - show.beats[k] - 0.12) / show.wipe
    if x <= 0:
        return -1e9
    if x >= 1:
        return 1e9
    top, bot = span
    m = 0.04 * (top - bot)
    y = (top + m) + ((bot - m) - (top + m)) * (1 - (1 - x) ** 2)
    return float(mk.to_screen(view, 0, y)[1])


# ---------------------------------------------------------------- text


_font_cache = {}


def font(name, size):
    k = (name, size)
    if k not in _font_cache:
        _font_cache[k] = ImageFont.truetype(mk.font_path(name), size)
    return _font_cache[k]


def text_rgba(runs, fnt, shadow=0.45):
    """Runs of (text, 'white'|'gold') as one RGBA numpy image (float 0..1) with a soft drop shadow."""
    pad = 30
    widths = [fnt.getlength(s) for s, _ in runs]
    asc, desc = fnt.getmetrics()
    w, h = int(sum(widths)) + 2 * pad, asc + desc + 2 * pad
    mask = Image.new('L', (w, h), 0)
    colour = np.zeros((h, w, 3), np.float32)
    x = pad
    top, bot = None, None
    for (s, c), sw in zip(runs, widths):
        m = Image.new('L', (w, h), 0)
        ImageDraw.Draw(m).text((x, pad), s, font=fnt, fill=255)
        bb = m.getbbox()
        if bb:
            top = bb[1] if top is None else min(top, bb[1])
            bot = bb[3] if bot is None else max(bot, bb[3])
        ma = np.asarray(m, np.float32)[..., None] / 255
        if c == 'gold':
            ys = np.linspace(0, 1, h)[:, None, None]
            bb = bb or (0, 0, w, h)
            g = np.clip((ys * h - bb[1]) / max(bb[3] - bb[1], 1), 0, 1)
            rgb = np.array(GOLD[0], np.float32) * (1 - g) + np.array(GOLD[1], np.float32) * g
        else:
            rgb = np.broadcast_to(np.array(WHITE, np.float32), (h, w, 3))
        colour = colour * (1 - ma) + rgb / 255 * ma
        mask = Image.fromarray(np.maximum(np.asarray(mask), np.asarray(m)))
        x += sw
    a = np.asarray(mask, np.float32) / 255
    sh = np.asarray(mask.filter(ImageFilter.GaussianBlur(7)), np.float32) / 255
    sh = mk.shift(sh, 0, 4) * shadow
    alpha = a + sh * (1 - a)
    rgb = colour * (a / np.maximum(alpha, 1e-4))[..., None]
    return np.dstack([rgb, alpha]), ((top or 0) + (bot or 0)) / 2


def paste_text(frame, img, cy_target, cy_img, opacity=1.0):
    """Paste an RGBA text image centred horizontally, with its glyph centre at screen y cy_target."""
    if opacity <= 0:
        return frame
    h, w = img.shape[:2]
    x0 = int(round(mk.W / 2 - w / 2))
    y0 = int(round(cy_target - cy_img))
    fx0, fy0, fx1, fy1 = max(x0, 0), max(y0, 0), min(x0 + w, mk.W), min(y0 + h, mk.H)
    if fx1 <= fx0 or fy1 <= fy0:
        return frame
    sub = img[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0]
    a = sub[..., 3:4] * opacity
    frame[fy0:fy1, fx0:fx1] = frame[fy0:fy1, fx0:fx1] * (1 - a) + sub[..., :3] * a
    return frame


# ---------------------------------------------------------------- the renderer


def year_runs(v):
    """A signed year as label runs: 1912 -> '1912', -60 -> '60 BC' with BC in gold (there is no year 0)."""
    return [(str(v), 'white')] if v > 0 else [(f'{max(1, -v)} ', 'white'), ('BC', 'gold')]


# Label layout per format: glyph centres (y) and fonts of the name line and the number line. A ranking labels below
# the map (name glyphs ~84 px tall at y 1510); a timeline above it (name at y 323, year digits ~52 px tall at y 441).
LAYOUTS = {
    'ranking': dict(name_y=1510, value_y=1622, name_font=('Pretendard-ExtraBold.otf', 101),
                    value_font=('Pretendard-Bold.otf', 82)),
    'timeline': dict(name_y=323, value_y=441, name_font=('Pretendard-ExtraBold.otf', 101),
                     value_font=('Pretendard-Bold.otf', 72)),
}


class Renderer:
    TITLE_Y = (885, 1007)   # glyph centres of the two title lines
    TITLE_FONT = ('Pretendard-ExtraBold.otf', 117)

    def __init__(self, show):
        self.show = show
        self.base = mk.Basemap(show.region, show.ppd)
        self.look = mk.Look(show.look)
        self.lay = LAYOUTS[show.format]
        self.layers = []  # per entry: [(merc geometry, texture box, texture), ...]
        for e in show.entries:
            ls = []
            for geom, texfn, tg in [(e.geom, e.texture, e.tex_geom)] + list(e.layers):
                gm = mk.to_merc(geom)
                b = mk.to_merc(tg if tg is not None else geom).bounds
                aspect = (b[3] - b[1]) / (b[2] - b[0])
                tw = 1400 if aspect <= 1 else int(1400 / aspect)
                ls.append((gm, b, texfn(tw, max(8, int(tw * aspect)))))
            self.layers.append(ls)
        # merc y span each wipe sweeps: the new territories and the ones they replace
        ys = []
        for ls in self.layers:
            bs = [L[0].bounds for L in ls]
            ys.append((min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)))
        self.spans = [(max(ys[i][3], ys[i - 1][3] if i else -1e9), min(ys[i][1], ys[i - 1][1] if i else 1e9))
                      for i in range(len(ys))]
        self.texts = {}
        rng = np.random.default_rng(show.seed)
        # a ragged wipe edge per beat: smooth noise along x
        self.edges = []
        for _ in show.entries:
            n = rng.normal(size=24)
            xs = np.linspace(0, 23, mk.W)
            self.edges.append(np.interp(xs, np.arange(24), n) * 16)

    def text(self, runs, f):
        k = (tuple(runs), f)
        if k not in self.texts:
            self.texts[k] = text_rgba(runs, font(*f))
        return self.texts[k]

    def cover(self, i, view):
        """Coverage and colours of entry i's territories (several are drawn as one slab)."""
        m_all, rgb_all = None, None
        for gm, b, tex in self.layers[i]:
            m = mk.mask_of(gm, view)
            rgb = np.asarray(mk.place_texture(tex, b, view), np.float32) / 255
            if m_all is None:
                m_all, rgb_all = m, rgb
            else:
                rgb_all = rgb_all * (1 - m[..., None]) + rgb * m[..., None]
                m_all = np.maximum(m_all, m)
        return m_all, rgb_all

    def map_frame(self, t):
        s = self.show
        view = view_at(s, t)
        base8 = self.base.render(view)
        frame = self.look.grade(base8)
        rel = mk.relief(np.asarray(base8))
        ks = [i for i, b in enumerate(s.beats) if b <= t]
        if ks:
            k = ks[-1]
            yy = np.arange(mk.H, dtype=np.float32)[:, None]
            wy = wipe_y(s, t, k, view, self.spans[k])
            # above = how much of each pixel already shows the new entry (None: all of it)
            above = None
            if wy < -1e8:
                above = 0.0
            elif wy < 1e8:
                above = np.clip((wy + self.edges[k][None, :] - yy) / 36 + 0.5, 0, 1)
            if k > 0 and above is not None:
                m, rgb = self.cover(k - 1, view)
                frame = mk.slab(frame, rgb, m * (1 - above), self.show.depth, relief_map=rel)
            if above is None or np.any(above):
                m, rgb = self.cover(k, view)
                frame = mk.slab(frame, rgb, m if above is None else m * above, self.show.depth, relief_map=rel)
        return frame, view

    def frame(self, t):
        s = self.show
        dt = 1 / s.fps
        frame, view = self.map_frame(t)
        # motion blur along the camera's screen motion over half a frame (only while it moves fast)
        v2 = view_at(s, t + dt / 2)
        su, sv = mk.to_screen(view, v2[0], v2[1])
        du, dv = float(mk.W / 2 - su), float(mk.H / 2 - sv)
        zoom = abs(math.log(v2[2] / view[2])) * mk.H / 2
        n = int(min(12, max(abs(du), abs(dv), zoom) / 2))
        if n >= 2:
            acc = np.zeros_like(frame)
            for j in range(n):
                tj = t + dt / 2 * (j / (n - 1) - 0.5)
                acc += self.map_frame(tj)[0]
            frame = acc / n
        # vignette over everything but the text
        frame = frame * self.look.vig
        return self.overlay(frame, t)

    def overlay(self, frame, t):
        s = self.show
        b0 = s.beats[0]
        # title
        a = mk.clamp01(t / 0.2) * (1 - mk.clamp01((t - b0 - 0.105) / 0.1))
        for line, y in zip(s.title, self.TITLE_Y):
            img, cy = self.text(line, self.TITLE_FONT)
            frame = paste_text(frame, img, y, cy, a)
        ks = [i for i, b in enumerate(s.beats) if b <= t]
        L = self.lay
        for k in ks[-2:]:
            e = s.entries[k]
            b = s.beats[k]
            nxt = s.beats[k + 1] if k + 1 < len(s.beats) else 1e9
            a_in = 1.0 if (k == 0 and not s.title) else mk.clamp01((t - b - 0.195) / 0.08)
            a = a_in * (1 - mk.clamp01((t - nxt - 0.105) / 0.1))
            if a <= 0:
                continue
            if e.count_from is not None:
                frm = e.count_from
            elif k:
                frm = s.entries[k - 1].area
            else:
                frm = e.area if s.format == 'timeline' else 0
            # the counter steps by s.step, quantised to the frame time
            x = mk.ease_out((round(t * s.fps) / s.fps - b - 0.21) / 0.45, 3)
            val = e.area if x >= 1 else int(round((frm + (e.area - frm) * x) / s.step) * s.step)
            img, cy = self.text(e.label, L['name_font'])
            frame = paste_text(frame, img, L['name_y'], cy, a)
            runs = year_runs(val) if s.format == 'timeline' else [(f'{val:,}{s.unit}', 'white')]
            img, cy = self.text(runs, L['value_font'])
            frame = paste_text(frame, img, L['value_y'], cy, a)
        return frame


def _render_chunk(args):
    make_show, i0, i1, path = args
    show = make_show()
    r = Renderer(show)
    p = subprocess.Popen([mk.ffmpeg(), '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{mk.W}x{mk.H}',
                          '-r', str(show.fps), '-i', '-', '-c:v', 'libx264', '-preset', 'medium', '-crf', '14',
                          '-pix_fmt', 'yuv420p', path], stdin=subprocess.PIPE)
    prog = path + '.progress'  # "<done> <total>", read by make.py --status
    for i in range(i0, i1):
        f = r.frame(i / show.fps)
        p.stdin.write((np.clip(f, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())
        if (i - i0) % 30 == 0 or i == i1 - 1:
            open(prog, 'w').write(f'{i - i0 + 1} {i1 - i0}')
    p.stdin.close()
    p.wait()
    return path


def render(make_show, out_mp4, audio=None, workers=None, tmp=None):
    """Render every frame in parallel (contiguous chunks, one x264 segment each), join, add audio."""
    from multiprocessing import Pool
    show = make_show()
    n = int(round(show.total * show.fps))
    if not workers:
        # every worker holds its own copy of the map (up to ~1 GB on wide views): bound by cores and by memory
        workers = max(1, (os.cpu_count() or 4) - 2)
        try:
            ram_gb = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 2 ** 30
            workers = max(1, min(workers, int(ram_gb / 1.5)))
        except (ValueError, OSError, AttributeError):
            pass
    tmp = tmp or os.path.join(os.path.dirname(out_mp4), 'seg')
    os.makedirs(tmp, exist_ok=True)
    for f in os.listdir(tmp):
        if f.endswith('.progress'):
            os.remove(os.path.join(tmp, f))
    print(f'rendering {n} frames ({show.total} s at {show.fps} fps) with {workers} workers', flush=True)
    bounds = np.linspace(0, n, workers + 1).astype(int)
    jobs = [(make_show, bounds[i], bounds[i + 1], os.path.join(tmp, f'seg{i:03d}.mp4')) for i in range(workers)
            if bounds[i + 1] > bounds[i]]
    with Pool(len(jobs)) as pool:
        segs = pool.map(_render_chunk, jobs)
    lst = os.path.join(tmp, 'list.txt')
    open(lst, 'w').write(''.join(f"file '{os.path.abspath(s)}'\n" for s in segs))
    cmd = [mk.ffmpeg(), '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst]
    if audio:
        cmd += ['-i', audio, '-map', '0:v', '-map', '1:a', '-c:a', 'aac', '-b:a', '192k', '-shortest']
    cmd += ['-c:v', 'copy', '-movflags', '+faststart', out_mp4]
    subprocess.run(cmd, check=True)
    return out_mp4
