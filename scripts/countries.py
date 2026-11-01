"""Look up countries for show.json: the Natural Earth code for "iso", the ISO 3166 alpha-2 code for a flagcdn "cdn"
flag, the Korean name and the geodesic area of the Natural Earth polygon.

    uv run --with numpy --with pillow --with shapely --with pyproj --with pyshp python scripts/countries.py 프랑스 japan VNM

Matches any of the English name, the Korean name (NAME_KO) or a code, case-insensitively, by substring. A country
whose ISO_A2 is -99 in Natural Earth (France, Norway, Kosovo, ...) gets its flag code from ISO_A2_EH.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mapkit as mk  # noqa: E402

qs = [q.lower() for q in sys.argv[1:]]
if not qs:
    sys.exit(__doc__)
from shapely.geometry import shape  # noqa: E402

r = mk._read_shp('ne_10m_admin_0_countries')
fields = [f[0] for f in r.fields[1:]]
col = lambda rec, k: rec[fields.index(k)] if k in fields else ''
for sr in r.iterShapeRecords():
    rec = sr.record
    names = [str(col(rec, k)) for k in ('NAME', 'NAME_LONG', 'NAME_KO', 'ADM0_A3', 'ISO_A3', 'ISO_A2')]
    if not any(q in n.lower() for q in qs for n in names if n):
        continue
    a2 = col(rec, 'ISO_A2')
    if a2 in ('-99', '', None):
        a2 = col(rec, 'ISO_A2_EH')
    g = shape(sr.shape.__geo_interface__)
    b = g.bounds
    print(f"{col(rec, 'NAME_KO') or '?':<12} {col(rec, 'NAME'):<28} iso {col(rec, 'ADM0_A3'):<4} cdn {str(a2).lower():<3} "
          f"{mk.area_km2(g):>12,.0f} km2   bounds lon {b[0]:.1f}..{b[2]:.1f} lat {b[1]:.1f}..{b[3]:.1f}")
