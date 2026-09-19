"""Download bare-earth elevation (DEM) rasters for Lower Manhattan as GeoTIFF.

Two sources, both served by NYS ITS from https://elevation.its.ny.gov/arcgis/rest/services :

  nyc  NYC_TopoBathymetric_2017_1_meter  NYC's 2017 LiDAR bare-earth DEM (native 1 ft grid).
       (The service named "..._1_foot" in nyc-accessibility-data-sources.md does not exist.)
  nys  Latest_DEM                        NYS Elevation Program statewide 1 m mosaic. For
       lower Manhattan its top layer is the NYC 2017 DEM above, so the two match here.

Both are requested in EPSG:2263 (NY State Plane Long Island, US survey feet) so they line up
with the project's CRS convention. Pixels default to 1 m. VALUES ARE METERS above NAVD88
(the horizontal grid is in feet) -- convert one or the other before computing slope.
The NYC DEM includes river-bottom bathymetry, so water pixels can be negative.

The area is the bounding box of the same neighborhoods as fetch_curbs.py (lower_manhattan.py).
No polygon mask is applied, so curbs at the edge of the neighborhoods still sample valid values.

Output (backend/data/raw/): dem_<source>_lowermanhattan.tif and a .json sidecar.

    python backend/scripts/download_dem.py                  # nyc
    python backend/scripts/download_dem.py --source nys nyc
    python backend/scripts/download_dem.py --res-m 2
"""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import datetime, timezone

import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from rasterio.windows import Window
from shapely.ops import transform as shp_transform

from lower_manhattan import DEFAULT_NTAS, RAW_DIR, fetch_neighborhoods, session, study_area

SERVICES = {
    "nyc": "NYC_TopoBathymetric_2017_1_meter",
    "nys": "Latest_DEM",
}
REST = "https://elevation.its.ny.gov/arcgis/rest/services"
FT_PER_M = 3937 / 1200  # US survey feet, the unit of EPSG:2263
NODATA = -9999.0
TILE = 2000  # px per request side; the servers cap a request at 15000 x 4100


def export_tile(svc: str, bbox: tuple, size: tuple[int, int], retries: int = 4) -> np.ndarray:
    w, h = size
    params = {
        "bbox": ",".join(map(str, bbox)),
        "bboxSR": 2263,
        "imageSR": 2263,
        "size": f"{w},{h}",
        "format": "tiff",
        "pixelType": "F32",
        "interpolation": "RSP_BilinearInterpolation",
        # Without this, cells with no coverage come back as 0.0 -- same as sea level.
        "noData": NODATA,
        "f": "image",
    }
    for attempt in range(retries):
        try:
            r = requests.get(f"{REST}/{svc}/ImageServer/exportImage", params=params, timeout=180)
            r.raise_for_status()
            if not r.headers.get("content-type", "").startswith("image/"):
                raise requests.RequestException(f"unexpected response: {r.text[:200]}")
            with MemoryFile(r.content) as mf, mf.open() as d:
                a = d.read(1)
            if a.shape != (h, w):
                raise requests.RequestException(f"got {a.shape}, expected {(h, w)}")
            return a
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def download(source: str, bounds: tuple, res_m: float) -> None:
    svc = SERVICES[source]
    px = res_m * FT_PER_M
    xmin, ymin, xmax, ymax = bounds
    ncols, nrows = math.ceil((xmax - xmin) / px), math.ceil((ymax - ymin) / px)
    transform = from_origin(xmin, ymin + nrows * px, px, px)  # top-left origin
    top = ymin + nrows * px

    out = RAW_DIR / f"dem_{source}_lowermanhattan.tif"
    print(f"[{source}] {svc}: {ncols} x {nrows} px at {res_m} m")
    valid = total = 0
    lo, hi = np.inf, -np.inf
    with rasterio.open(
        out, "w", driver="GTiff", height=nrows, width=ncols, count=1, dtype="float32",
        crs="EPSG:2263", transform=transform, nodata=NODATA,
        compress="deflate", predictor=3, tiled=True, blockxsize=256, blockysize=256,
    ) as dst:
        dst.units = ("metre",)
        dst.update_tags(vertical_unit="meters", vertical_datum="NAVD88", source=svc)
        for row in range(0, nrows, TILE):
            for col in range(0, ncols, TILE):
                w, h = min(TILE, ncols - col), min(TILE, nrows - row)
                bbox = (xmin + col * px, top - (row + h) * px, xmin + (col + w) * px, top - row * px)
                a = export_tile(svc, bbox, (w, h))
                dst.write(a, 1, window=Window(col, row, w, h))
                ok = a != NODATA
                valid += int(ok.sum())
                total += a.size
                if ok.any():
                    lo, hi = min(lo, float(a[ok].min())), max(hi, float(a[ok].max()))
                print(f"  tile row {row} col {col}: {ok.mean():.0%} valid", end="\r")
    print()

    meta = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "service": f"{REST}/{svc}/ImageServer",
        "crs": "EPSG:2263",
        "pixel_size_m": res_m,
        "pixel_size_ft": px,
        "width": ncols,
        "height": nrows,
        "bounds_2263_ft": [xmin, ymin, xmax, ymin + nrows * px],
        "value_unit": "meters",
        "vertical_datum": "NAVD88",
        "nodata": NODATA,
        "valid_fraction": valid / total,
        "min_m": lo,
        "max_m": hi,
        "ntas": DEFAULT_NTAS,
    }
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2))
    print(f"[{source}] saved {out} ({out.stat().st_size / 1e6:.1f} MB), {valid / total:.0%} valid, {lo:.1f} to {hi:.1f} m")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", nargs="+", choices=SERVICES, default=["nyc"])
    ap.add_argument("--res-m", type=float, default=1.0, help="output pixel size in meters (default 1)")
    args = ap.parse_args()

    area = study_area(fetch_neighborhoods(session(), DEFAULT_NTAS))
    to_2263 = Transformer.from_crs(4326, 2263, always_xy=True).transform
    bounds = shp_transform(to_2263, area).bounds

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for source in args.source:
        download(source, bounds, args.res_m)


if __name__ == "__main__":
    main()
