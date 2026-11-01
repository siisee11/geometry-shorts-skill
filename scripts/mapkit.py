"""Map animation kit: a satellite basemap in Web Mercator, territories as polygons, and a 2.5D look (raised slab with
a flag on top, side face, drop shadow), drawn frame by frame with numpy + Pillow. Everything comes from public data:

  <data>/bmng/<tile>.jpg  NASA Blue Marble Next Generation, topography + bathymetry, July 2004: eight 90x90 degree
                          tiles at 240 px per degree (A1 180-90W ... D1 90-180E north of the equator, A2..D2
                          south), public domain. Downloaded on first use, only the ones a region needs (~70 MB each).
  <data>/ne/*.zip         Natural Earth 1:10m land, minor islands and countries (public domain), on first use.
  <data>/fonts/           Pretendard and Noto Serif KR (SIL OFL), on first use.

<data> is $MAP_SHORTS_DATA, else a data/ folder next to the scripts folder if there is one (a project that keeps its
data beside the code), else ~/.cache/map-shorts.

Coordinates: "merc degrees". x = longitude, y = Mercator northing in degrees (deg(ln tan(pi/4 + lat/2))), so one unit
is one degree of longitude everywhere and shapes keep their familiar web-map look. A camera view is (cx, cy, w): the
centre in merc degrees and the visible width in degrees of longitude. Regions are (lon0, lon1, lat0, lat1) and must
not cross the antimeridian.
"""
import math
import os
import subprocess
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

Image.MAX_IMAGE_PIXELS = None
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = (os.environ.get('MAP_SHORTS_DATA')
        or (os.path.join(ROOT, 'data') if os.path.isdir(os.path.join(ROOT, 'data'))
            else os.path.join(os.path.expanduser('~'), '.cache', 'map-shorts')))
W, H = 1080, 1920

NE_URL = 'https://naciscdn.org/naturalearth/10m/{}/{}.zip'
NE_KIND = {'ne_10m_land': 'physical', 'ne_10m_minor_islands': 'physical', 'ne_10m_admin_0_countries': 'cultural'}
FONT_URLS = {
    'Pretendard-ExtraBold.otf': 'https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/public/static/Pretendard-ExtraBold.otf',
    'Pretendard-Bold.otf': 'https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/public/static/Pretendard-Bold.otf',
    'NotoSerifKR[wght].ttf': 'https://raw.githubusercontent.com/google/fonts/main/ofl/notoserifkr/NotoSerifKR%5Bwght%5D.ttf',
}


def _complete(path):
    """Is a downloaded file whole? Checks the end marker of the formats we fetch (a cut-off JPEG decodes as grey
    blocks or raises 'image file is truncated' much later, so catch it here)."""
    try:
        size = os.path.getsize(path)
        if size == 0:
            return False
        with open(path, 'rb') as f:
            f.seek(max(0, size - 64))
            tail = f.read()
        if path.endswith('.jpg'):
            return tail.rstrip(b'\x00').endswith(b'\xff\xd9')
        if path.endswith('.png'):
            return b'IEND' in tail
        if path.endswith('.zip'):
            return zipfile.is_zipfile(path)
        return True
    except OSError:
        return False


def fetch(url, path, tries=3):
    """Download url to path once and make sure it arrived whole (plain Python, no curl needed). A connection that
    drops early can end a urllib read without an error, so the byte count is checked against Content-Length and the
    file's end marker; on a short read it retries, then falls back to curl with resume. Safe when several renders
    start at once: each process writes its own .part file and renames it into place when complete."""
    if os.path.exists(path):
        if _complete(path):
            return path
        print('re-downloading incomplete', os.path.basename(path), flush=True)
        os.remove(path)
    import shutil
    import urllib.request
    os.makedirs(os.path.dirname(path), exist_ok=True)
    print('downloading', os.path.basename(path), flush=True)
    part = f'{path}.{os.getpid()}.part'
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'map-shorts/1.0'})
            with urllib.request.urlopen(req, timeout=120) as r, open(part, 'wb') as f:
                want = int(r.headers.get('Content-Length') or 0)
                shutil.copyfileobj(r, f, 1 << 20)
            got = os.path.getsize(part)
            if (not want or got == want) and _complete(part):
                os.replace(part, path)
                return path
            print(f'  short download ({got:,} of {want:,} bytes), retrying', flush=True)
        except Exception as e:  # e.g. a macOS python.org build without certificates; curl has the system's
            print(f'  download failed ({type(e).__name__}), retrying', flush=True)
    if shutil.which('curl'):
        subprocess.run(['curl', '-fsSL', '--retry', '5', '-C', '-', '-o', part, url], check=True)
        if _complete(part):
            os.replace(part, path)
            return path
    raise SystemExit(f'could not download {url} completely; check the connection and run again')


def ffmpeg():
    """The ffmpeg executable: the one on PATH, else the static build that the imageio-ffmpeg package ships."""
    import shutil
    exe = shutil.which('ffmpeg')
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise SystemExit('ffmpeg not found: install ffmpeg, or the Python package imageio-ffmpeg (scripts/run.py does)')


def font_path(name):
    """A font file: <data>/fonts, an assets/fonts folder beside the scripts' parent folder, or downloaded (FONT_URLS)."""
    for d in (os.path.join(DATA, 'fonts'), os.path.join(ROOT, '..', 'assets', 'fonts')):
        if os.path.exists(os.path.join(d, name)):
            return os.path.join(d, name)
    return fetch(FONT_URLS[name], os.path.join(DATA, 'fonts', name))

# the default region (East Asia from Shandong to Sakhalin) and finest cache resolution, px per merc degree
EAST_ASIA = (108.0, 150.0, 22.0, 58.0)
PPD = 200
TILE_URL = ('https://eoimages.gsfc.nasa.gov/images/imagerecords/73000/73751/'
            'world.topo.bathy.200407.3x21600x21600.{}.jpg')
SRC_PPD = 240


def merc_y(lat):
    return np.degrees(np.log(np.tan(np.pi / 4 + np.radians(lat) / 2)))


def inv_merc_y(y):
    return np.degrees(2 * np.arctan(np.exp(np.radians(y))) - np.pi / 2)


def merc(lon, lat):
    return np.asarray(lon, float), merc_y(np.asarray(lat, float))


# ---------------------------------------------------------------- basemap


def fetch_tile(name):
    """<data>/bmng/<name>.jpg (e.g. 'D1'), downloaded from NASA if missing (~70 MB each)."""
    return fetch(TILE_URL.format(name), os.path.join(DATA, 'bmng', name + '.jpg'))


def equirect(region):
    """The region as one equirectangular uint8 array at 240 px/deg, stitched from the tiles it touches."""
    lon0, lon1, lat0, lat1 = region
    sp = SRC_PPD
    out = np.zeros((int(round((lat1 - lat0) * sp)), int(round((lon1 - lon0) * sp)), 3), np.uint8)
    for col, tlon in enumerate((-180, -90, 0, 90)):
        for row, tlat in enumerate((90, 0)):
            # tile covers lon tlon..tlon+90, lat tlat-90..tlat
            ix0, ix1 = max(lon0, tlon), min(lon1, tlon + 90)
            iy0, iy1 = max(lat0, tlat - 90), min(lat1, tlat)
            if ix0 >= ix1 or iy0 >= iy1:
                continue
            src = Image.open(fetch_tile('ABCD'[col] + str(row + 1)))
            box = tuple(int(round(v)) for v in ((ix0 - tlon) * sp, (tlat - iy1) * sp, (ix1 - tlon) * sp, (tlat - iy0) * sp))
            part = np.asarray(src.crop(box))
            ox, oy = int(round((ix0 - lon0) * sp)), int(round((lat1 - iy1) * sp))
            out[oy:oy + part.shape[0], ox:ox + part.shape[1]] = part[:out.shape[0] - oy, :out.shape[1] - ox]
    return out


def _cache_name(region, ppd):
    return os.path.join(DATA, 'basemap_{:g}_{:g}_{:g}_{:g}_{}.jpg'.format(*region, ppd))


def build_basemap(region=EAST_ASIA, ppd=PPD):
    """Resample the region to Mercator rows at `ppd` and write it with two halvings (a small mip pyramid, so zoomed-out
    frames don't alias)."""
    lon0, lon1, lat0, lat1 = region
    y0, y1 = float(merc_y(lat0)), float(merc_y(lat1))
    crop = equirect(region)
    sp = SRC_PPD
    ow, oh = int((lon1 - lon0) * ppd), int((y1 - y0) * ppd)
    # output row j has merc y = y1 - (j + 0.5) / ppd; take the source row for that latitude (linear blend)
    lat = inv_merc_y(y1 - (np.arange(oh) + 0.5) / ppd)
    sr = (lat1 - lat) * sp - 0.5
    r0 = np.clip(np.floor(sr).astype(int), 0, crop.shape[0] - 1)
    r1 = np.clip(r0 + 1, 0, crop.shape[0] - 1)
    f = (sr - np.floor(sr))[:, None, None]
    rows = crop[r0].astype(np.float32) * (1 - f) + crop[r1].astype(np.float32) * f
    del crop
    img = Image.fromarray(rows.clip(0, 255).astype(np.uint8)).resize((ow, oh), Image.LANCZOS)
    for k in range(3):
        p = _cache_name(region, ppd >> k)
        img.save(p, quality=94)
        print(p, img.size, flush=True)
        img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)


class Basemap:
    def __init__(self, region=EAST_ASIA, ppd=PPD):
        self.region = tuple(float(v) for v in region)
        self.lon0 = self.region[0]
        self.y1 = float(merc_y(self.region[3]))
        span_x = self.region[1] - self.region[0]
        span_y = self.y1 - float(merc_y(self.region[2]))
        self.levels = []  # (px per merc degree in x, in y, image), finest first
        for k in range(3):
            p = _cache_name(self.region, ppd >> k)
            if not os.path.exists(p):
                build_basemap(self.region, ppd)
            im = Image.open(p).convert('RGB')
            # the scale comes from the image's real size: halving an odd size rounds, so ppd >> k can be off by
            # several percent (29 px/deg -> a 14.5 px/deg image labelled 14), which slid the map off the territories
            self.levels.append((im.width / span_x, im.height / span_y, im))

    def render(self, view, size=(W, H)):
        """The basemap seen from a view, as an RGB image."""
        cx, cy, w = view
        s = size[0] / w  # screen px per merc degree
        px, py, img = next(((a, b, im) for a, b, im in self.levels[::-1] if a >= s * 0.9), self.levels[0])
        # screen (u, v) -> cache pixel (x, y)
        ax, ay = px / s, py / s
        x0 = (cx - self.lon0) * px - ax * size[0] / 2
        y0 = (self.y1 - cy) * py - ay * size[1] / 2
        return img.transform(size, Image.AFFINE, (ax, 0, x0, 0, ay, y0), resample=Image.BILINEAR)


class Look:
    """A colour grade: a curve per channel (a 256-entry table), then a vignette gain over the screen.

    Look() is the default: about 10 % darker, blue lifted a little, a soft shoulder for bright ground (deserts, ice),
    the top of the frame ~20 % darker and the bottom ~10 % darker. Look('grade.npz') loads a fitted grade instead
    (`coefs`: a cubic per channel, `vignette`: a gain map)."""

    def __init__(self, path=None, size=(W, H)):
        x = np.linspace(0, 1, 256, dtype=np.float32)
        if path:
            z = np.load(path)
            c = z['coefs'].astype(np.float32)
            self.lut = np.stack([k[0] + k[1] * x + k[2] * x * x + k[3] * x ** 3 for k in c], -1).clip(0, 1)
            v = Image.fromarray(np.clip(z['vignette'] * 128, 0, 255).astype(np.uint8)).resize(size, Image.BICUBIC)
            self.vig = (np.asarray(v, np.float32) / 128)[..., None]
            return
        lin = [(0.89, -0.03), (0.89, -0.02), (1.02, -0.04)]
        knee = 0.6  # above this the line bends into a shoulder that reaches 1.0 gently
        cols = []
        for gain, off in lin:
            y = gain * x + off
            yk = gain * knee + off
            over = np.maximum(x - knee, 0)
            y = np.where(x > knee, yk + (1 - yk) * (1 - np.exp(-over * gain / max(1 - yk, 1e-3))), y)
            cols.append(y)
        self.lut = np.stack(cols, -1).clip(0, 1).astype(np.float32)
        u = np.linspace(-1, 1, size[0], dtype=np.float32)[None, :]
        v = np.linspace(0, 1, size[1], dtype=np.float32)[:, None]
        top = np.clip(1 - v / 0.4, 0, 1) ** 2 * (0.22 + 0.06 * u * u)
        bottom = np.clip((v - 0.8) / 0.2, 0, 1) ** 2 * 0.1
        self.vig = (1 - top - bottom)[..., None]

    def grade(self, rgb8):
        """uint8 HxWx3 -> graded float32 0..1 (curve only; the vignette goes on last, over the territories too)."""
        a = np.asarray(rgb8)
        return np.stack([self.lut[a[..., c], c] for c in range(3)], -1)


def to_screen(view, x, y, size=(W, H)):
    cx, cy, w = view
    s = size[0] / w
    return size[0] / 2 + (np.asarray(x) - cx) * s, size[1] / 2 - (np.asarray(y) - cy) * s


def from_screen(view, u, v, size=(W, H)):
    cx, cy, w = view
    s = size[0] / w
    return cx + (np.asarray(u) - size[0] / 2) / s, cy - (np.asarray(v) - size[1] / 2) / s


def fit_view(bounds, box=(0.08, 0.07, 0.92, 0.70), size=(W, H)):
    """The view that fits merc bounds (x0, y0, x1, y1) into a screen box (u0, v0, u1, v1 as fractions of the frame),
    by default the part above the label."""
    x0, y0, x1, y1 = bounds
    bw, bh = (box[2] - box[0]) * size[0], (box[3] - box[1]) * size[1]
    s = min(bw / max(x1 - x0, 1e-6), bh / max(y1 - y0, 1e-6))  # px per merc degree
    # the bounds' centre goes to the box centre
    cu, cv = (box[0] + box[2]) / 2 * size[0], (box[1] + box[3]) / 2 * size[1]
    cx = (x0 + x1) / 2 - (cu - size[0] / 2) / s
    cy = (y0 + y1) / 2 + (cv - size[1] / 2) / s
    return (cx, cy, size[0] / s)


def view_rect(view, size=(W, H)):
    """Merc bounds (x0, y0, x1, y1) a view shows."""
    cx, cy, w = view
    h = w * size[1] / size[0]
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


# ---------------------------------------------------------------- vectors (Natural Earth)


def _read_shp(name):
    import shapefile  # pyshp
    import io
    z = zipfile.ZipFile(fetch(NE_URL.format(NE_KIND[name], name), os.path.join(DATA, 'ne', name + '.zip')))
    get = lambda ext: io.BytesIO(z.read(name + ext))
    return shapefile.Reader(shp=get('.shp'), shx=get('.shx'), dbf=get('.dbf'), encoding='utf-8')


def land(region=EAST_ASIA):
    """All land in a region (lon/lat shapely geometry)."""
    from shapely.geometry import box, shape
    from shapely.ops import unary_union
    clip = box(region[0], region[2], region[1], region[3])
    parts = []
    for name in ('ne_10m_land', 'ne_10m_minor_islands'):
        for s in _read_shp(name).iterShapes():
            g = shape(s.__geo_interface__)
            if g.intersects(clip):
                parts.append(g.intersection(clip))
    return unary_union(parts).buffer(0)


def country(iso):
    """A country (Natural Earth ADM0_A3, e.g. KOR, PRK) as lon/lat shapely geometry, islands included."""
    from shapely.geometry import shape
    r = _read_shp('ne_10m_admin_0_countries')
    fields = [f[0] for f in r.fields[1:]]
    i = fields.index('ADM0_A3')
    for sr in r.iterShapeRecords():
        if sr.record[i] == iso:
            return shape(sr.shape.__geo_interface__).buffer(0)
    raise KeyError(iso)


def area_km2(geom):
    """Geodesic area (WGS84) of a lon/lat geometry."""
    from pyproj import Geod
    return abs(Geod(ellps='WGS84').geometry_area_perimeter(geom)[0]) / 1e6


def to_merc(geom):
    from shapely.ops import transform
    return transform(lambda x, y, z=None: (np.asarray(x), merc_y(np.asarray(y))), geom)


def polygons(geom):
    """Exterior and hole rings of a (multi)polygon, as lists of (x, y) arrays."""
    gs = getattr(geom, 'geoms', [geom])
    out = []
    for g in gs:
        if g.geom_type != 'Polygon':
            continue
        out.append((np.asarray(g.exterior.coords), [np.asarray(r.coords) for r in g.interiors]))
    return out


# ---------------------------------------------------------------- drawing


def mask_of(geom_merc, view, ss=2, size=(W, H), grow=None):
    """Antialiased coverage (float32 HxW, 0..1) of a merc geometry seen from a view. `grow` = (ax, ay, g) scales the
    shape by g around merc point (ax, ay) first (the pop-in)."""
    big = (size[0] * ss, size[1] * ss)
    im = Image.new('L', big, 0)
    d = ImageDraw.Draw(im)
    for ext, holes in polygons(geom_merc):
        for ring, fill in [(ext, 255)] + [(h, 0) for h in holes]:
            x, y = ring[:, 0], ring[:, 1]
            if grow:
                ax, ay, g = grow
                x, y = ax + (x - ax) * g, ay + (y - ay) * g
            u, v = to_screen(view, x, y, big)
            if len(u) > 2:
                d.polygon(list(zip(u.tolist(), v.tolist())), fill=fill)
    if ss > 1:
        im = im.resize(size, Image.BOX)
    return np.asarray(im, np.float32) / 255


def place_texture(tex, bounds, view, size=(W, H), grow=None):
    """An RGB(A) texture stretched over merc bounds (x0, y0, x1, y1), seen from a view."""
    x0, y0, x1, y1 = bounds
    if grow:
        ax, ay, g = grow
        x0, x1 = ax + (x0 - ax) * g, ax + (x1 - ax) * g
        y0, y1 = ay + (y0 - ay) * g, ay + (y1 - ay) * g
    cx, cy, w = view
    s = size[0] / w
    tw, th = tex.size
    # screen u -> texture x: (cx + (u - W/2)/s - x0) / (x1 - x0) * tw
    a = tw / ((x1 - x0) * s)
    c = (cx - size[0] / 2 / s - x0) / (x1 - x0) * tw
    e = th / ((y1 - y0) * s)
    f = (y1 - cy - size[1] / 2 / s) / (y1 - y0) * th
    # outside the box (an island or exclave beyond the texture's box) continue the flag's corner colour
    return tex.transform(size, Image.AFFINE, (a, 0, c, 0, e, f), resample=Image.BICUBIC, fillcolor=tex.getpixel((1, 1)))


def blur(a, r):
    im = Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(r)), np.float32) / 255


def shift(a, dx, dy):
    out = np.zeros_like(a)
    h, w = a.shape[:2]
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = a[max(-dy, 0):h - max(dy, 0), max(-dx, 0):w - max(dx, 0)]
    return out


def relief(base_rgb, r=5.0, soft=1.2):
    """Terrain detail of the basemap under a slab: luminance minus its blur, about -1..1."""
    lum = base_rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32) / 255
    im = Image.fromarray((lum * 255).astype(np.uint8))
    lo = np.asarray(im.filter(ImageFilter.GaussianBlur(r)), np.float32) / 255
    lum = np.asarray(im.filter(ImageFilter.GaussianBlur(soft)), np.float32) / 255
    return np.clip((lum - lo) * 4.0, -1, 1)


def slab(frame, top_rgb, cover, depth=9, shadow=(8, 16, 16, 0.55), relief_map=None, relief_amt=0.22, alpha=1.0):
    """Draw a raised territory onto frame (float32 HxWx3, 0..1): drop shadow, side face (the top's colours darkened,
    shifted down `depth` px) and the top (flag colours, with the terrain relief pressed into it)."""
    if alpha <= 0:
        return frame
    sdx, sdy, sr, sa = shadow
    sh = blur(shift(cover, sdx, sdy + depth), sr) * sa * alpha
    frame = frame * (1 - sh[..., None])
    # side face: stack the outline downwards; colour = top colour 1 px above each step, darkened with depth
    side = np.zeros_like(cover)
    side_rgb = np.zeros_like(top_rgb)
    for k in range(depth, 0, -1):
        m = shift(cover, 0, k)
        c = shift(top_rgb, 0, k) * (0.72 - 0.2 * k / depth)
        side_rgb = side_rgb * (1 - m[..., None]) + c * m[..., None]
        side = np.maximum(side, m)
    a = side * alpha
    frame = frame * (1 - a[..., None]) + side_rgb * a[..., None]
    top = top_rgb
    if relief_map is not None:
        top = np.clip(top * (1 + relief_amt * relief_map[..., None]), 0, 1)
    # a soft rim light on the top's upper edges, a darker lower rim
    rim = np.clip(cover - shift(cover, 0, 3), 0, 1)
    top = np.clip(top + 0.10 * rim[..., None], 0, 1)
    a = cover * alpha
    return frame * (1 - a[..., None]) + top * a[..., None]


# ---------------------------------------------------------------- easing


def clamp01(x):
    return min(max(x, 0.0), 1.0)


def ease_inout(x):
    x = clamp01(x)
    return x * x * (3 - 2 * x)


def ease_out(x, p=3):
    x = clamp01(x)
    return 1 - (1 - x) ** p


def ease_out_back(x, k=1.4):
    x = clamp01(x)
    return 1 + (k + 1) * (x - 1) ** 3 + k * (x - 1) ** 2


def lerp_view(a, b, t):
    """Interpolate views; the width moves in log space so a zoom feels even."""
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, math.exp(math.log(a[2]) + (math.log(b[2]) - math.log(a[2])) * t))
