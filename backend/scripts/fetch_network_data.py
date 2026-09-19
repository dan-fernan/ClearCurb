"""Download sidewalk polygons, elevation points, and LION streets for Lower Manhattan.

Sources (Socrata page IDs in the docs are map wrappers; these are the queryable tables):
    sidewalks   52n9-sdep  NYC Planimetric Database: Sidewalk (page vfx9-tbb6)
    elevation   9uxf-ng6q  NYC Planimetric Database: Elevation Points (page szwg-xci6)
    lion        2v4z-66xt  LION single line street base map (zip of a file geodatabase)
    raised      uh2s-ftgh  Raised Crosswalk Locations (145 points citywide, keyed by LION node id)

Output (default ``backend/data/raw/``), all EPSG:4326 GeoParquet:
    sidewalks_lowermanhattan.parquet
    elevation_points_lowermanhattan.parquet
    lion_lowermanhattan.parquet      streets, with a boolean ``is_step_street`` (RW_TYPE = 7)
    raised_crosswalks_lowermanhattan.parquet

Usage:
    python backend/scripts/fetch_network_data.py
    python backend/scripts/fetch_network_data.py --only lion
    python backend/scripts/fetch_network_data.py --lion-zip ~/Downloads/nyclion.zip

Set SOCRATA_APP_TOKEN to raise the API rate limit (optional).
"""

from __future__ import annotations

import argparse
import os
import tempfile
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

BASE = "https://data.cityofnewyork.us/resource"
LION_URL = (
    "https://data.cityofnewyork.us/api/views/2v4z-66xt/files/"
    "30298730-5064-447c-8c39-a3981409d9b3?download=true&filename=nyclion.zip"
)
OUT = Path(__file__).resolve().parents[1] / "data" / "raw"
PAGE = 50_000
HEADERS = {"X-App-Token": t} if (t := os.getenv("SOCRATA_APP_TOKEN")) else {}

# Lower Manhattan (south, west, north, east): matches download_ramps.py
S, W, N, E = 40.700, -74.020, 40.740, -73.970
WHERE = f"within_box(the_geom, {S}, {W}, {N}, {E})"


def fetch_socrata(dataset_id: str, select: str) -> gpd.GeoDataFrame:
    frames, offset = [], 0
    while True:
        r = requests.get(
            f"{BASE}/{dataset_id}.geojson",
            params={"$select": select, "$where": WHERE, "$limit": PAGE, "$offset": offset, "$order": ":id"},
            headers=HEADERS,
            timeout=180,
        )
        r.raise_for_status()
        feats = r.json()["features"]
        if feats:
            frames.append(gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326"))
        print(f"  {dataset_id}: {offset + len(feats)} rows", end="\r")
        if len(feats) < PAGE:
            break
        offset += PAGE
    print()
    return pd.concat(frames, ignore_index=True) if frames else gpd.GeoDataFrame()


def fetch_sidewalks() -> None:
    gdf = fetch_socrata("52n9-sdep", "the_geom,source_id,feat_code,sub_code,status,shape_area")
    gdf["shape_area"] = pd.to_numeric(gdf["shape_area"], errors="coerce")  # sq ft
    gdf.to_parquet(OUT / "sidewalks_lowermanhattan.parquet")
    print(f"Saved {len(gdf)} sidewalk polygons")


def fetch_elevation() -> None:
    gdf = fetch_socrata("9uxf-ng6q", "the_geom,source_id,feat_code,elevation,status")
    gdf["elevation"] = pd.to_numeric(gdf["elevation"], errors="coerce")  # feet, NAVD88
    gdf.to_parquet(OUT / "elevation_points_lowermanhattan.parquet")
    print(f"Saved {len(gdf)} elevation points")


def fetch_lion(zip_path: Path | None) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        if zip_path is None:
            zip_path = Path(tmp) / "nyclion.zip"
            print("Downloading LION (~46 MB)...")
            with requests.get(LION_URL, stream=True, timeout=180) as r:
                r.raise_for_status()
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)
        gdb = next(Path(tmp).rglob("*.gdb"))
        # LION ships in EPSG:2263, so build the bbox in that CRS before reading.
        box = gpd.GeoSeries.from_xy([W, E], [S, N], crs="EPSG:4326").to_crs("EPSG:2263").total_bounds
        gdf = gpd.read_file(gdb, layer="lion", bbox=tuple(box))
    gdf = gdf.to_crs("EPSG:4326")
    gdf["is_step_street"] = gdf["RW_TYPE"].astype(str).str.strip() == "7"
    gdf.to_parquet(OUT / "lion_lowermanhattan.parquet")
    print(f"Saved {len(gdf)} LION segments ({int(gdf['is_step_street'].sum())} step streets)")


def fetch_raised_crosswalks() -> None:
    # Small table with no lat/long columns: x/y are EPSG:2263 feet, so fetch all rows and clip locally.
    r = requests.get(f"{BASE}/uh2s-ftgh.json", params={"$limit": 5000}, headers=HEADERS, timeout=180)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    gdf = gpd.GeoDataFrame(
        df[["treatment", "date", "nodeid"]].assign(nodeid=df["nodeid"].astype(int)),
        geometry=gpd.points_from_xy(df["x"].astype(float), df["y"].astype(float)),
        crs="EPSG:2263",
    ).to_crs("EPSG:4326")
    gdf = gdf.cx[W:E, S:N]
    gdf.to_parquet(OUT / "raised_crosswalks_lowermanhattan.parquet")
    print(f"Saved {len(gdf)} raised crosswalks (of {len(df)} citywide)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=["sidewalks", "elevation", "lion", "raised"], help="fetch a single dataset")
    ap.add_argument("--lion-zip", type=Path, help="use an already-downloaded nyclion.zip")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    if args.only in (None, "sidewalks"):
        fetch_sidewalks()
    if args.only in (None, "elevation"):
        fetch_elevation()
    if args.only in (None, "lion"):
        fetch_lion(args.lion_zip)
    if args.only in (None, "raised"):
        fetch_raised_crosswalks()


if __name__ == "__main__":
    main()
