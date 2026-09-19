"""Download NYC Pedestrian Ramp Locations (ufzp-rrqu) for Lower Manhattan.

Each row is one ramp point with surveyed measurements. Saved as GeoParquet (EPSG:4326).
"""
import os
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

URL = "https://data.cityofnewyork.us/resource/ufzp-rrqu.geojson"
OUT = Path(__file__).resolve().parents[1] / "data" / "raw"
OUT.mkdir(parents=True, exist_ok=True)
PAGE = 50_000
HEADERS = {"X-App-Token": t} if (t := os.getenv("SOCRATA_APP_TOKEN")) else {}

# Lower Manhattan (south, west, north, east): Battery up to ~14th St
S, W, N, E = 40.700, -74.020, 40.740, -73.970
WHERE = f"borough = 1 AND within_box(the_geom, {S}, {W}, {N}, {E})"

frames, offset = [], 0
while True:
    r = requests.get(URL, params={"$where": WHERE, "$limit": PAGE, "$offset": offset, "$order": ":id"},
                     headers=HEADERS, timeout=180)
    r.raise_for_status()
    feats = r.json()["features"]
    if feats:
        frames.append(gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326"))
    if len(feats) < PAGE:
        break
    offset += PAGE

ramps = pd.concat(frames, ignore_index=True)
ramps.to_parquet(OUT / "ramps_lowermanhattan.parquet")
print(f"ramps_lowermanhattan: {len(ramps)} rows")
