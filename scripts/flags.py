"""Flag and emblem textures drawn in code, sized to a territory's bounding box. Round parts stay round; fields and
stripes stretch with the box, which is how map videos print a flag onto a country. All functions take the texture
size (w, h) in pixels and return an RGB PIL image.
"""
import math

import numpy as np
from PIL import Image, ImageDraw

SS = 2  # supersampling for clean edges


def _canvas(w, h, colour):
    im = Image.new('RGB', (w * SS, h * SS), colour)
    return im, ImageDraw.Draw(im)


def _done(im, w, h):
    return im.resize((w, h), Image.LANCZOS)


def _disc(d, cx, cy, r, fill):
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill)


def _taeguk(im, cx, cy, r, top, bottom, tilt_deg, ring=None, ring_w=0, flip=False, stretch=1.0):
    """A taeguk: `top` colour above the S, `bottom` below, the S running along a line tilted by tilt_deg (positive =
    left end higher), the top colour bulging down on the left like the Korean flag."""
    W, H = im.size
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    t = math.radians(tilt_deg)
    ax, ay = math.cos(t), math.sin(t)  # axis unit vector, upper left -> lower right (screen y points down)
    px, py = x - cx, y - cy
    py = py / stretch  # stretch > 1: an upright ellipse, as when a flag is fitted to a tall territory
    if flip:  # mirror top-bottom (the S turns the other way)
        py = -py
    along = px * ax + py * ay
    across = -px * ay + py * ax  # > 0 below the axis
    inside = px * px + py * py <= r * r
    upper = across < 0
    left_small = (along + r / 2) ** 2 + across ** 2 <= (r / 2) ** 2
    right_small = (along - r / 2) ** 2 + across ** 2 <= (r / 2) ** 2
    is_top = (upper | left_small) & ~right_small
    a = np.asarray(im).copy()
    a[inside & is_top] = top
    a[inside & ~is_top] = bottom
    if ring:
        rr = np.sqrt(px * px + py * py)
        a[(rr > r) & (rr <= r + ring_w)] = ring
    return Image.fromarray(a)


def _trigram(d, cx, cy, ang, L, th, gap, pattern, fill):
    """Three bars centred at (cx, cy), bars perpendicular to direction `ang` (radians); pattern is three booleans,
    True = solid, from the inside (nearest the centre of the flag) outwards."""
    ux, uy = math.cos(ang), math.sin(ang)  # outward
    vx, vy = -uy, ux  # along a bar
    for i, solid in enumerate(pattern):
        off = (i - 1) * (th + gap)
        bx, by = cx + ux * off, cy + uy * off
        segs = [(-L / 2, L / 2)] if solid else [(-L / 2, -gap / 2), (gap / 2, L / 2)]
        for s0, s1 in segs:
            pts = []
            for s, o in ((s0, -th / 2), (s1, -th / 2), (s1, th / 2), (s0, th / 2)):
                pts.append((bx + vx * s + ux * o, by + vy * s + uy * o))
            d.polygon(pts, fill=fill)


def taegukgi(w, h, disc=0.5, centre=(0.5, 0.5)):
    """South Korea. Circle diameter = disc * width, trigrams on the box diagonals (geon, gam, ri, gon)."""
    im, d = _canvas(w, h, (250, 250, 250))
    W, H = im.size
    cx, cy, r = W * centre[0], H * centre[1], W * disc / 2
    tilt = math.degrees(math.atan2(H, W)) * 0.6
    im = _taeguk(im, cx, cy, r, (205, 46, 58), (0, 71, 160), tilt)
    d = ImageDraw.Draw(im)
    L, th, gap = r * 1.0, r * 0.17, r * 0.085
    k = '#111111'
    # (dir x, dir y, pattern inside->out)
    for sx, sy, pat in ((-1, -1, (1, 1, 1)), (1, -1, (0, 1, 0)), (-1, 1, (1, 0, 1)), (1, 1, (0, 0, 0))):
        tx, ty = cx + sx * r * 1.62, cy + sy * r * 1.45
        ang = math.atan2(sy * H, sx * W)
        _trigram(d, tx, ty, ang, L, th, gap, [bool(p) for p in pat], k)
    return _done(im, w, h)


def dprk(w, h, bands=(0.35, 0.37, 0.86, 0.88), disc=(0.28, 0.615, 0.2)):
    """North Korea: blue, white, red, white, blue (band edges as fractions of the height); a white disc with a red
    star (centre x, centre y as fractions, radius as a fraction of the width)."""
    im, d = _canvas(w, h, (2, 79, 162))
    W, H = im.size
    e = (0.0,) + tuple(bands) + (1.0,)
    cols = [(2, 79, 162), (250, 250, 250), (237, 28, 39), (250, 250, 250), (2, 79, 162)]
    for a, b, c in zip(e, e[1:], cols):
        d.rectangle((0, a * H, W, b * H), fill=c)
    cx, cy, r = disc[0] * W, disc[1] * H, disc[2] * W
    _disc(d, cx, cy, r, (250, 250, 250))
    pts = []
    for i in range(10):
        rr = r * 0.93 if i % 2 == 0 else r * 0.93 * 0.382
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=(237, 28, 39))
    return _done(im, w, h)


def crescent(w, h, field=(52, 110, 222), moon=(250, 250, 250), size=0.48, centre=(0.6, 0.56)):
    """A white crescent opening to the right on a blue field."""
    im, d = _canvas(w, h, field)
    W, H = im.size
    cx, cy, r = W * centre[0], H * centre[1], W * size / 2
    _disc(d, cx, cy, r, moon)
    _disc(d, cx + r * 0.5, cy - r * 0.04, r * 0.8, field)
    return _done(im, w, h)


def rings(w, h, field=(200, 30, 60), a=(250, 245, 235), b=(240, 165, 105), centre=(0.5, 0.42), size=0.62,
          bars=((0.72, 0.1), (0.42, 0.78))):
    """Concentric rings and groups of three short bars: a royal-standard-like pattern."""
    im, d = _canvas(w, h, field)
    W, H = im.size
    cx, cy, R = W * centre[0], H * centre[1], W * size / 2
    for i, c in enumerate((a, b, a, b, a)):
        _disc(d, cx, cy, R * (1 - i * 0.2), c)
    for fx, fy in bars:
        bx, by = W * fx, H * fy
        for i in range(3):
            d.rectangle((bx - W * 0.17, by + i * H * 0.03, bx + W * 0.17, by + i * H * 0.03 + H * 0.017), fill=b)
    return _done(im, w, h)


def big_taeguk(w, h, field=(250, 250, 250), top=(232, 98, 44), bottom=(46, 58, 110), size=0.78, centre=(0.5, 0.42),
               tilt=-60, flip=True, stretch=1.3):
    """An oversized taeguk with a dark ring on a white field; by default the S stands nearly upright, the warm
    colour on the left with its head at the top."""
    im, d = _canvas(w, h, field)
    W, H = im.size
    cx, cy, r = W * centre[0], H * centre[1], W * size / 2
    im = _taeguk(im, cx, cy, r, top, bottom, tilt, ring=bottom, ring_w=r * 0.14, flip=flip, stretch=stretch)
    return _done(im, w, h)


def stamp(w, h, art, field, ink=(12, 8, 8), size=0.55, centre=(0.5, 0.45), aspect=1.0, cut=0.32):
    """A one-colour emblem: the black strokes of a generated black-on-red picture (red channel < cut) printed in
    `ink` on a plain field, so every territory that uses it gets exactly the same field colour."""
    im = Image.new('RGB', (w, h), field)
    ew = int(w * size)
    eh = int(ew * aspect * art.height / art.width)
    lum = np.asarray(art.convert('RGB').resize((ew, eh), Image.LANCZOS), np.float32)[..., 0] / 255
    m = np.clip((cut + 0.06 - lum) / 0.12, 0, 1)
    m = Image.fromarray((m * 255).astype(np.uint8))
    im.paste(Image.new('RGB', (ew, eh), ink), (int(w * centre[0] - ew / 2), int(h * centre[1] - eh / 2)), m)
    return im


def emblem(w, h, art, field, size=0.55, centre=(0.5, 0.45), aspect=1.0):
    """A generated emblem picture (painted on the field colour) placed on a plain field. size = emblem width as a
    fraction of the box width; aspect stretches it vertically (1 = keep its shape on screen)."""
    im = Image.new('RGB', (w, h), field)
    ew = int(w * size)
    eh = int(ew * aspect * art.height / art.width)
    a = np.asarray(art.convert('RGB').resize((ew, eh), Image.LANCZOS), np.float32)
    # scale the picture's colours so its background lands exactly on the field colour
    bg = np.median(np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3)]), 0)
    a = Image.fromarray(np.clip(a * (np.array(field, np.float32) / np.maximum(bg, 1)), 0, 255).astype(np.uint8))
    # feather the square picture's edge into the field so no seam shows
    m = Image.new('L', (ew, eh), 0)
    ImageDraw.Draw(m).ellipse((ew * 0.02, eh * 0.02, ew * 0.98, eh * 0.98), fill=255)
    from PIL import ImageFilter
    m = m.filter(ImageFilter.GaussianBlur(ew * 0.01))
    im.paste(a, (int(w * centre[0] - ew / 2), int(h * centre[1] - eh / 2)), m)
    return im


HANJA_FONT = ('NotoSerifKR[wght].ttf', 900)  # SIL OFL; has every Hanja a Korean dynasty name needs


def hanja(w, h, text, field, ink=(18, 14, 12), size=0.62, centre=(0.5, 0.5), disc=None, vertical=None, rough=True,
          room=None, room_fill=1.25):
    """A dynasty name in large serif Hanja (朝鮮, 高句麗, ...) on a plain field, like the 漢 / 唐 / 宋 fills of map
    videos. The text block is scaled to fit `size` of the box; a tall box stacks the characters vertically (or
    `vertical`); '\\n' breaks lines. `disc` = colour of a circle behind the text (明 on a white disc). `rough` frays
    the edges a little so it reads as ink rather than type. `room` = radius (fraction of w) of the largest circle
    that fits in the territory around `centre`: the block's half-diagonal is kept within room_fill x that, so the
    text stays on the land on any shape (scripts/make.py passes it)."""
    import os
    from PIL import ImageFilter, ImageFont
    import mapkit as mk
    im = Image.new('RGB', (w, h), field)
    if vertical is None:
        vertical = h > 1.3 * w and '\n' not in text
    lines = list(text) if vertical else text.split('\n')
    big = 400
    f = ImageFont.truetype(mk.font_path(HANJA_FONT[0]), big)
    try:
        f.set_variation_by_axes([HANJA_FONT[1]])
    except Exception:
        pass
    # draw the block at a large fixed size, then scale it into the box
    lh = int(big * 1.08)
    bw = int(max(f.getlength(l) for l in lines)) + 40
    bh = lh * len(lines) + 40
    blk = Image.new('L', (bw, bh), 0)
    d = ImageDraw.Draw(blk)
    for i, l in enumerate(lines):
        d.text(((bw - f.getlength(l)) / 2, 20 + i * lh), l, font=f, fill=255)
    blk = blk.crop(blk.getbbox())
    if rough:
        n = Image.fromarray((np.random.default_rng(len(text)).random((blk.height // 6 + 1, blk.width // 6 + 1)) * 255).astype(np.uint8))
        n = n.resize(blk.size, Image.BICUBIC).filter(ImageFilter.GaussianBlur(2))
        blk = Image.fromarray(np.where(np.asarray(blk.filter(ImageFilter.GaussianBlur(3))) + (np.asarray(n) - 128) * 0.5 > 128, 255, 0).astype(np.uint8))
    k = min(size * w / blk.width, size * h / blk.height)
    if room:
        k = min(k, room_fill * room * w / (0.5 * math.hypot(blk.width, blk.height)))
    tw, th = max(1, int(blk.width * k)), max(1, int(blk.height * k))
    blk = blk.resize((tw, th), Image.LANCZOS)
    cx, cy = centre[0] * w, centre[1] * h
    if disc:
        r = 0.62 * max(tw, th)
        ImageDraw.Draw(im).ellipse((cx - r, cy - r, cx + r, cy + r), fill=tuple(disc))
    im.paste(Image.new('RGB', (tw, th), tuple(ink)), (int(cx - tw / 2), int(cy - th / 2)), blk)
    return im
