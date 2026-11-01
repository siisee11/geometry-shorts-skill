"""Make a satellite-map Short (rankings and timelines of countries) from one spec file.

    UV="uv run --with numpy --with scipy --with pillow --with shapely --with pyproj --with pyshp"
    $UV python scripts/make.py episodes/<slug> --plan            # entries, values, views, basemap area (fast)
    $UV python scripts/make.py episodes/<slug> --still 5,8.4     # stills -> out/stills/<t>.png
    $UV python scripts/make.py episodes/<slug> [--fps 30]        # music + every frame -> out/video.mp4, out/timeline.json

FORMATS ("format" in show.json)
  "ranking"   (default) a title card, then a countdown: "N. name" and a counting area below the map. Entries are
              sorted by value; ties share a rank ("공동 3."). Defaults: t0 3.1, period 3.308, unit km², step 10.
  "timeline"  no title card, entries as listed (e.g. present to past): name and a counting year above the map.
              "year" is the number (negative = BC, shown "60 BC"). Defaults: t0 0, period 1.98, step 1.

episodes/<slug>/show.json (a ranking needs "title" and "entries"; a timeline only "entries"):

{
  "format": "ranking",
  "title": ["동남아시아에서", "가장 큰 나라 {TOP5}"],     lines; {...} is printed in gold
  "unit": "km²", "step": 10,                              counter suffix and step
  "t0": 3.1, "period": 3.308, "tail": 3.3,                first beat, seconds per entry, time after the last beat
  "title_view": [lon0, lat0, lon1, lat1],                 optional title framing (default: all entries)
  "title_hold": [[cx, cy, w], [cx, cy, w]],               or exact title views (merc), like an entry's "hold"
  "order": "countdown",                                   smallest first ("as_listed" keeps the file's order)
  "entries": [
    {"name": "인도네시아",
     "geom": {"iso": ["IDN"]},                            see GEOMETRY
     "value": "auto",                                     a number, or "auto" = geodesic area (timeline: "year")
     "round": 100,                                        rounding for "auto"
     "flag": {"cdn": "id"},                               see FLAGS
     "frame": [95, -11, 141, 6],                          optional camera bounds (lon0, lat0, lon1, lat1)
     "flag_box": "main",                                  "frame" (default), "main" (largest part) or a bbox
     "hold": [[cx, cy, w], [cx, cy, w]]}                  optional exact views (merc) instead of auto framing
  ]
}
An entry with several territories at once (후삼국, 삼국) lists them instead of geom/flag/flag_box:
    {"name": "남북국", "year": 800, "territories": [{"geom": ..., "flag": ...}, {"geom": ..., "flag": ...}]}

GEOMETRY  {"iso": ["KOR", "PRK"]}                Natural Earth countries (ADM0_A3), joined
          {"claim": [[lon, lat], ...]}           a polygon (or a list of rings) cut to the land
          {"borders": "borders.json", "key": k}  claim rings stored in a file: {"<key>": {"claim": [ring, ...]}}
          any of them + "clip": [lon0, lat0, lon1, lat1] and/or "minus": <geometry> (e.g. minus a neighbour);
          a list of specs is their union

FLAGS     {"cdn": "fr"}                          the country's flag from flagcdn.com (public-domain flag images)
                                                 + "fit": "auto" (stretch up to 1.6x, then crop around the
                                                 territory's visual centre), "cover" or "stretch",
                                                 + "scale": 0.5 to shrink a one-colour flag (Vietnam) around it
          {"hanja": "高句麗", "field": [r, g, b], "ink": [r, g, b]}   a name in large Hanja (Noto Serif KR Black),
                                                 sized to stay inside the territory; "disc", "vertical", "size"
          {"draw": "taegukgi", "args": {...}}    a function in scripts/flags.py
          {"stamp": "emblems/crow.png", "field": [r, g, b], "size": 0.6, "centre": [0.5, 0.4]}
          {"emblem": "emblems/dragon.png", "field": [r, g, b], ...}   see scripts/flags.py
          {"image": "my_flag.png"}  {"color": [r, g, b]}

The camera frames each entry into the screen part the labels leave free (mapkit.fit_view), holds with the
slow zoom-in (1.3 %/s) and moves with a 0.55 s ease; a ranking's title shows all entries. The
basemap area and resolution follow from those views, and the NASA tiles it needs are downloaded on first use.
"""
import argparse
import functools
import hashlib
import json
import math
import os
import pickle
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import flags  # noqa: E402
import mapkit as mk  # noqa: E402
import ranking  # noqa: E402
from PIL import Image  # noqa: E402

HOLD_ZOOM = 0.013  # per second, while an entry is on screen
PLAN_VERSION = 'v2'  # bump when resolve() stores something new, so old out/plan.pkl caches are rebuilt
FLAG_CDN = 'https://flagcdn.com/w2560/{}.png'

# Per-format defaults (show.json keys override them). A timeline moves faster (an entry every ~2 s from 0 s) and
# has its labels above the map, so the map sits lower.
FORMATS = {
    'ranking': dict(t0=3.1, period=3.308, order='countdown', unit='km²', step=10, box=(0.08, 0.07, 0.92, 0.70)),
    'timeline': dict(t0=0.0, period=1.98, order='as_listed', unit='', step=1, box=(0.06, 0.28, 0.94, 0.78)),
}


def opt(spec, key):
    if key == 't0' and 't0' not in spec and spec.get('title'):
        return FORMATS['ranking']['t0']  # a title card needs its 3.1 s in any format
    return spec.get(key, FORMATS[spec.get('format', 'ranking')][key])


def territories(e):
    """An entry's territories: its "territories" list, or the entry itself as one."""
    return e.get('territories') or [{k: e[k] for k in ('geom', 'flag', 'flag_box') if k in e}]


# ---------------------------------------------------------------- geometry


@functools.lru_cache(None)
def _land(bbox):
    lon0, lat0, lon1, lat1 = bbox
    return mk.land((lon0, lon1, lat0, lat1))


def geometry(spec, ep):
    from shapely.geometry import MultiPolygon, Polygon, box
    from shapely.ops import unary_union
    if isinstance(spec, list):
        return unary_union([geometry(s, ep) for s in spec])
    if 'iso' in spec:
        g = unary_union([mk.country(c) for c in spec['iso']])
    else:
        if 'borders' in spec:
            rings = json.load(open(os.path.join(ep, spec['borders'])))[spec['key']]['claim']
        else:
            rings = spec['claim']
            if rings and isinstance(rings[0][0], (int, float)):
                rings = [rings]
        claim = MultiPolygon([Polygon(r) for r in rings]).buffer(0)
        b = claim.bounds
        g = _land((math.floor(b[0]) - 1, math.floor(b[1]) - 1, math.ceil(b[2]) + 1, math.ceil(b[3]) + 1)).intersection(claim)
    if 'clip' in spec:
        c = spec['clip']
        g = g.intersection(box(c[0], c[1], c[2], c[3]))
    if 'minus' in spec:  # e.g. a kingdom = its claim minus its neighbours
        g = g.difference(geometry(spec['minus'], ep))
    return g.buffer(0)


def parts(g):
    return sorted(getattr(g, 'geoms', [g]), key=lambda p: -p.area)


def frame_bounds(g, min_share=0.05, near=0.25, min_near_share=0.002):
    """Lon/lat bounds of the parts that matter for framing and for the flag: those at least `min_share` of the
    largest part, plus smaller ones lying close to it (within `near` of its bounding-box diagonal and at least
    `min_near_share` of its area): Tierra del Fuego, Corsica, Sicily. Far-off islands (overseas territories, the
    Galapagos) are left out, so they don't shrink the view."""
    from shapely.ops import unary_union
    ps = parts(g)
    big = ps[0]
    b = big.bounds
    diag = math.hypot(b[2] - b[0], b[3] - b[1])
    keep = [p for p in ps if p.area >= big.area * min_share
            or (p.area >= big.area * min_near_share and p.distance(big) <= near * diag)]
    return unary_union(keep).bounds


def merc_bounds(b):
    return (b[0], float(mk.merc_y(b[1])), b[2], float(mk.merc_y(b[3])))


# ---------------------------------------------------------------- flags


def flag_image(code):
    return Image.open(mk.fetch(FLAG_CDN.format(code.lower()), os.path.join(mk.DATA, 'flags', f'{code}.png'))).convert('RGB')


def fit_image(img, w, h, mode='auto', focus=(0.5, 0.5), max_stretch=1.6, scale=1.0):
    """An image on a w x h box.
    'stretch': fill the box exactly (the genre's usual way of printing a flag on a country).
    'cover':   keep proportions, crop the overflow.
    'auto':    stretch by up to max_stretch (as map Shorts usually do), and cover beyond that.
    When cropping, the image's centre goes to `focus` (fractions of the box: the territory's visual centre), so a
    star or a disc lands on the land rather than in the middle of the bounding box. scale < 1 shrinks the flag
    around the focus and fills the rest with its corner colour: for one-colour fields with a central emblem
    (Vietnam, Japan) on narrow territories."""
    if mode == 'stretch':
        return img.resize((w, h), Image.LANCZOS)
    a = img.width / img.height
    c = 1.0 if mode == 'cover' else min(max((w / h) / a, 1 / max_stretch), max_stretch)
    fh = max(h, w / (a * c)) * scale
    fw = fh * a * c
    if scale < 1:
        pad = Image.new('RGB', (max(w, round(fw)) * 2 + w, max(h, round(fh)) * 2 + h), img.getpixel((1, 1)))
        f = img.resize((round(fw), round(fh)), Image.LANCZOS)
        pad.paste(f, ((pad.width - f.width) // 2, (pad.height - f.height) // 2))
        x, y = pad.width / 2 - focus[0] * w, pad.height / 2 - focus[1] * h
        return pad.crop((round(x), round(y), round(x) + w, round(y) + h))
    big = img.resize((max(w, round(fw)), max(h, round(fh))), Image.LANCZOS)
    x = min(max(big.width / 2 - focus[0] * w, 0), big.width - w)
    y = min(max(big.height / 2 - focus[1] * h, 0), big.height - h)
    return big.crop((round(x), round(y), round(x) + w, round(y) + h))


def texture(spec, ep, focus=(0.5, 0.5), room=None):
    """A function (w, h) -> RGB image for a flag spec. `focus` is the territory's visual centre (fractions of the
    box): image flags centre there when cropped, text emblems sit there. `room` = the radius of the largest circle
    inside the territory around it, as a fraction of the box width: text emblems are sized to stay inside it."""
    art = lambda f: Image.open(os.path.join(ep, f))
    opts = {k: (tuple(v) if isinstance(v, list) else v) for k, v in spec.items()
            if k not in ('cdn', 'draw', 'args', 'stamp', 'emblem', 'image', 'color', 'fit', 'scale')}
    for k in ('field', 'ink', 'disc'):
        if k in opts:
            opts[k] = tuple(opts[k])
    fit, sc = spec.get('fit', 'auto'), spec.get('scale', 1.0)
    if 'cdn' in spec:
        return lambda w, h: fit_image(flag_image(spec['cdn']), w, h, fit, focus, scale=sc)
    if 'image' in spec:
        return lambda w, h: fit_image(art(spec['image']).convert('RGB'), w, h, fit, focus, scale=sc)
    if 'color' in spec:
        return lambda w, h: Image.new('RGB', (w, h), tuple(spec['color']))
    if 'draw' in spec:
        fn = getattr(flags, spec['draw'])
        args = {k: (tuple(v) if isinstance(v, list) else v) for k, v in spec.get('args', {}).items()}
        return lambda w, h: fn(w, h, **args)
    if 'stamp' in spec:
        return lambda w, h: flags.stamp(w, h, art(spec['stamp']), **opts)
    if 'emblem' in spec:
        return lambda w, h: flags.emblem(w, h, art(spec['emblem']), **opts)
    if 'hanja' in spec:
        opts.pop('hanja')
        opts.setdefault('centre', focus)
        if room is not None:
            opts.setdefault('room', room)
        return lambda w, h: flags.hanja(w, h, spec['hanja'], **opts)
    raise ValueError(f'unknown flag spec {spec}')


# ---------------------------------------------------------------- the plan


def load(ep):
    return json.load(open(os.path.join(ep, 'show.json')))


def resolve(ep):
    """Geometries, values and ranks, cached in out/plan.pkl (workers load it instead of recomputing)."""
    spec = load(ep)
    key = hashlib.sha1(json.dumps(spec, sort_keys=True).encode()).hexdigest() + PLAN_VERSION
    for f in sorted(set(__import__('re').findall(r'"borders": "([^"]+)"', json.dumps(spec)))):  # claim files too
        key += str(os.path.getmtime(os.path.join(ep, f)))
    cache = os.path.join(ep, 'out', 'plan.pkl')
    if os.path.exists(cache):
        c = pickle.load(open(cache, 'rb'))
        if c['key'] == key:
            return c
    from shapely.ops import unary_union
    ents = []
    for e in spec['entries']:
        tg = [geometry(t['geom'], ep) for t in territories(e)]
        g = unary_union(tg)
        v = e.get('year', e.get('value', 'auto'))
        if v == 'auto':
            r = e.get('round', 10)
            v = int(round(mk.area_km2(g) / r) * r)
        ents.append({'spec': e, 'geom': g, 'geoms': tg, 'value': int(v)})
    # ranks: 1 + how many are strictly bigger (ties share a rank)
    for e in ents:
        e['rank'] = e['spec'].get('rank', 1 + sum(o['value'] > e['value'] for o in ents))
    for e in ents:
        e['tie'] = sum(o['rank'] == e['rank'] for o in ents) > 1
    if opt(spec, 'order') == 'countdown':
        ents = sorted(ents, key=lambda e: -e['rank'])  # stable: ties keep the listed order
    c = {'key': key, 'entries': ents}
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    pickle.dump(c, open(cache, 'wb'))
    return c


LAT_LIMIT = 85  # the map stops here (Web Mercator's usual edge); cameras are kept inside it


def keep_on_map(v):
    """Slide a view up or down so it doesn't show past the map's top or bottom edge (a black band), as wide views
    of high-latitude empires would."""
    cx, cy, w = v
    h = w * mk.H / mk.W * 1.08  # room for the move's zoom-out bump
    top, bot = float(mk.merc_y(LAT_LIMIT)), float(mk.merc_y(-LAT_LIMIT))
    cy = min(cy, top - h / 2)
    cy = max(cy, bot + h / 2)
    return (cx, cy, w)


def views(spec, ents):
    period = opt(spec, 'period')
    tail = spec.get('tail', period)
    box = opt(spec, 'box')
    holds, frames = [], []
    for i, e in enumerate(ents):
        s = e['spec']
        if 'hold' in s:  # exact views (merc) given in show.json
            holds.append(tuple(tuple(v) for v in s['hold']))
            frames.append(merc_bounds(frame_bounds(e['geom'])))
            continue
        fb = merc_bounds(s['frame'] if 'frame' in s else frame_bounds(e['geom']))
        frames.append(fb)
        v0 = mk.fit_view(fb, box=box)
        dur = (period if i + 1 < len(ents) else tail) - 0.55
        holds.append((v0, (v0[0], v0[1], v0[2] * math.exp(-HOLD_ZOOM * dur))))
    if 'title_hold' in spec:  # exact views (merc) at 0 s and at the first beat
        return tuple(tuple(v) for v in spec['title_hold']), holds
    if not spec.get('title'):  # no title card: open slightly wide on the first entry and settle in
        s0 = holds[0][0]
        z = keep_on_map((s0[0], s0[1], s0[2] * 1.15))
        return (z, z), [tuple(keep_on_map(v) for v in h) for h in holds]
    if 'title_view' in spec:
        tv = mk.fit_view(merc_bounds(spec['title_view']), box=(0.04, 0.04, 0.96, 0.96))
    else:
        u = (min(f[0] for f in frames), min(f[1] for f in frames), max(f[2] for f in frames), max(f[3] for f in frames))
        tv = mk.fit_view(u, box=(0.04, 0.04, 0.96, 0.96))
    title = (keep_on_map(tuple(tv[:2]) + (tv[2] * 1.166,)), keep_on_map(tv))
    return title, [tuple(keep_on_map(v) for v in h) for h in holds]


def region_for(title, holds, max_px=12000):
    """Basemap area covering every view (with the move's zoom-out bump), and a resolution that is sharp at the
    closest view but keeps the cache under max_px a side."""
    rects = [mk.view_rect((v[0], v[1], v[2] * 1.08)) for v in [title[0]] + [h[0] for h in holds]]
    x0 = max(-180, math.floor(min(r[0] for r in rects)) - 1)
    x1 = min(180, math.ceil(max(r[2] for r in rects)) + 1)
    lat0 = max(-LAT_LIMIT, math.floor(float(mk.inv_merc_y(min(r[1] for r in rects)))) - 1)
    lat1 = min(LAT_LIMIT, math.ceil(float(mk.inv_merc_y(max(r[3] for r in rects)))) + 1)
    need = max(mk.W / v[2] for v in [title[1]] + [h[1] for h in holds]) * 1.1
    ppd = int(min(mk.PPD, max(16, need)))
    hm = float(mk.merc_y(lat1) - mk.merc_y(lat0))
    while max(x1 - x0, hm) * ppd > max_px:
        ppd = int(ppd * 0.9)
    return (float(x0), float(x1), float(lat0), float(lat1)), ppd


def title_runs(line):
    """'가장 큰 나라 {TOP5}' -> [('가장 큰 나라 ', 'white'), ('TOP5', 'gold')]"""
    out, cur, gold = [], '', False
    for ch in line:
        if ch in '{}':
            if cur:
                out.append((cur, 'gold' if gold else 'white'))
            cur, gold = '', ch == '{'
        else:
            cur += ch
    if cur:
        out.append((cur, 'gold' if gold else 'white'))
    return out


def build_show(ep, fps=None):
    spec = load(ep)
    ents = resolve(ep)['entries']
    title, holds = views(spec, ents)
    region, ppd = region_for(title, holds)
    E = []
    fmt = spec.get('format', 'ranking')
    for e, hold in zip(ents, holds):
        s = e['spec']
        if fmt == 'timeline':
            label = [(s['name'], 'white')]
        else:
            label = ([('공동 ', 'white')] if e['tie'] else []) + [(f"{e['rank']}.", 'gold'), (' ' + s['name'], 'white')]
        layers = [(g, *flag_layer(t, g, ep)) for t, g in zip(territories(s), e['geoms'])]
        g0, tex0, tg0 = layers[0]
        E.append(ranking.Entry(label, e['value'], g0, tex0, hold, tex_geom=tg0, layers=layers[1:]))
    t0, period = opt(spec, 't0'), opt(spec, 'period')
    look = spec.get('look')
    return ranking.Show(
        title=[title_runs(l) for l in spec.get('title', [])], title_views=title, entries=E,
        t0=t0, period=period, total=round(t0 + period * (len(E) - 1) + spec.get('tail', period), 3),
        look=os.path.join(ep, look) if look else None, unit=opt(spec, 'unit'), step=opt(spec, 'step'),
        region=region, ppd=ppd, format=fmt, fps=int(fps or spec.get('fps', 60)))


def flag_layer(t, g, ep):
    """(texture function, texture box geometry) for one territory spec and its geometry."""
    from shapely.geometry import box
    from shapely.ops import polylabel
    fb = t.get('flag_box', 'frame')
    if fb == 'main':
        tg = parts(g)[0]
    elif fb == 'frame':
        tg = box(*frame_bounds(g))
    else:
        tg = box(*fb)
    # the main part's visual centre (pole of inaccessibility, in merc so it matches the screen) and the radius of
    # the largest circle around it that stays inside, as fractions of the flag box
    main = mk.to_merc(parts(g)[0])
    pt = polylabel(main, tolerance=0.02) if main.geom_type == 'Polygon' else main.representative_point()
    r = main.exterior.distance(pt) if main.geom_type == 'Polygon' else 0
    bx0, by0, bx1, by1 = merc_bounds(tg.bounds)
    focus = ((pt.x - bx0) / max(bx1 - bx0, 1e-6), (by1 - pt.y) / max(by1 - by0, 1e-6))
    return texture(t['flag'], ep, focus, r / max(bx1 - bx0, 1e-6)), tg


# ---------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('episode')
    ap.add_argument('--plan', action='store_true', help='print ranks, values, views and the basemap area')
    ap.add_argument('--still', help='comma-separated times: write out/stills/<t>.png')
    ap.add_argument('--fps', type=int, help='frame rate of the video (default 60; 30 renders in half the time)')
    ap.add_argument('--workers', type=int, help='parallel render processes (default: cores - 2, bounded by memory)')
    ap.add_argument('--out', help='video path (default <episode>/out/video.mp4)')
    ap.add_argument('--status', action='store_true', help='progress of a render running in the background')
    a = ap.parse_args()
    ep = os.path.abspath(a.episode)
    out = os.path.join(ep, 'out')
    os.makedirs(out, exist_ok=True)
    if a.status:
        seg = os.path.join(out, 'seg')
        done = total = 0
        for f in sorted(os.listdir(seg)) if os.path.isdir(seg) else []:
            if f.endswith('.progress'):
                d, t = map(int, open(os.path.join(seg, f)).read().split())
                done, total = done + d, total + t
        video = a.out or os.path.join(out, 'video.mp4')
        fresh = os.path.exists(video) and (not total or os.path.getmtime(video) > max(
            os.path.getmtime(os.path.join(seg, f)) for f in os.listdir(seg) if f.endswith('.progress')))
        print(f'finished: {video}' if fresh else
              f'{done}/{total} frames ({100 * done / total:.0f}%)' if total else 'no render running')
        return
    show = build_show(ep, a.fps)
    print(f'{len(show.entries)} entries, {show.total} s, basemap {show.region} at {show.ppd} px/deg')
    for e, b in zip(show.entries, show.beats):
        val = ''.join(x for x, _ in ranking.year_runs(e.area)) if show.format == 'timeline' else f'{e.area:,}{show.unit}'
        print(f"  {b:6.2f}s  {''.join(x for x, _ in e.label):<16} {val:>14}  x{1 + len(e.layers)}   view {tuple(round(v, 3) for v in e.hold[0])}")
    if a.plan:
        return
    if a.still:
        import numpy as np
        r = ranking.Renderer(show)
        os.makedirs(os.path.join(out, 'stills'), exist_ok=True)
        for t in a.still.split(','):
            f = r.frame(float(t))
            p = os.path.join(out, 'stills', f'{float(t):.2f}.png')
            Image.fromarray((np.clip(f, 0, 1) * 255 + 0.5).astype(np.uint8)).save(p)
            print(p)
        return
    import music
    raw, wav = os.path.join(out, 'music_raw.wav'), os.path.join(out, 'music.wav')
    music.track(show.beats, show.total, raw)
    subprocess.run([mk.ffmpeg(), '-loglevel', 'error', '-y', '-i', raw, '-af', 'loudnorm=I=-14:TP=-1.2:LRA=9', '-ar', '48000',
                    wav], check=True)
    mp4 = ranking.render(functools.partial(build_show, ep, a.fps), a.out or os.path.join(out, 'video.mp4'), wav, a.workers)
    ends = show.beats[1:] + [show.total]
    shots = [{'name': '제목', 'dur': round(show.beats[0], 3)}] + [
        {'name': ''.join(x for x, _ in e.label).strip(), 'dur': round(t1 - t0, 3)}
        for e, t0, t1 in zip(show.entries, show.beats, ends)]
    json.dump({'fps': show.fps, 'total': show.total, 'shots': shots}, open(os.path.join(out, 'timeline.json'), 'w'),
              ensure_ascii=False, indent=1)
    # one picture of the whole video (2 frames a second) to check the flow without playing it
    n = int(show.total * 2)
    subprocess.run([mk.ffmpeg(), '-loglevel', 'error', '-y', '-i', mp4, '-vf',
                    f'fps=2,scale=180:-1,tile={min(n, 11)}x{-(-n // 11)}', '-frames:v', '1',
                    os.path.join(out, 'sheet.png')], check=True)
    print(mp4)
    print(os.path.join(out, 'sheet.png'))


if __name__ == '__main__':
    main()
