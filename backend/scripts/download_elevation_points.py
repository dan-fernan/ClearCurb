"""Download NYC Planimetric Database: Elevation Points for Lower Manhattan.

Source: https://data.cityofnewyork.us/Transportation/NYC-Planimetric-Database-Elevation-Points/szwg-xci6
That page is a map wrapper with no queryable rows; the Socrata API serves the underlying
table, dataset ``9uxf-ng6q``.

Point subtypes (sub_code): 300000 spot elevation (ground), 300020 bridge deck,
301000 standing water, 302000 building roof (highest point of the roof).
Roof points are >half of all rows and say nothing about street grade, so they are
left out unless --include-buildings is passed.

Elevations are in FEET (NAVD88). The DEMs from download_dem.py are in METERS.

The area is the same as fetch_curbs.py (Manhattan CD1-3 NTAs, see lower_manhattan.py).
Saved as GeoParquet (EPSG:4326), like download_ramps.py.

    python backend/scripts/download_elevation_points.py
"""

from __future__ import annotations

import argparse

import geopandas as gpd
import pandas as pd

from lower_manhattan import (
    DEFAULT_NTAS,
    RAW_DIR,
    SODA_BASE,
    fetch_neighborhoods,
    get_json,
    session,
    study_area,
)

DATASET = "9uxf-ng6q"
PAGE = 50_000
KINDS = {300000: "spot", 300020: "bridge", 301000: "water", 302000: "building_roof"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--include-buildings", action="store_true", help="also keep building-roof points")
    args = ap.parse_args()

    s = session()
    area = study_area(fetch_neighborhoods(s, DEFAULT_NTAS))
    minx, miny, maxx, maxy = area.bounds
    # within_box args: NW lat, NW lon, SE lat, SE lon
    where = f"within_box(the_geom, {maxy}, {minx}, {miny}, {maxx})"
    if not args.include_buildings:
        where += " AND sub_code != 302000"

    rows, offset = [], 0
    while True:
        batch = get_json(
            s,
            f"{SODA_BASE}/{DATASET}.json",
            {
                "$select": ":id,the_geom,feat_code,sub_code,elevation,source_id,status",
                "$where": where,
                "$order": ":id",
                "$limit": PAGE,
                "$offset": offset,
            },
        )
        rows += batch
        if len(batch) < PAGE:
            break
        offset += PAGE

    gdf = gpd.GeoDataFrame(
        {
            "row_id": [r[":id"] for r in rows],
            "sub_code": [int(r["sub_code"]) for r in rows],
            "elevation_ft": [float(r["elevation"]) for r in rows],
            "source_id": [int(float(r["source_id"])) for r in rows],
            "status": [r["status"] for r in rows],
        },
        geometry=gpd.points_from_xy(
            [r["the_geom"]["coordinates"][0] for r in rows],
            [r["the_geom"]["coordinates"][1] for r in rows],
        ),
        crs="EPSG:4326",
    )
    gdf["kind"] = gdf["sub_code"].map(KINDS)

    in_box = len(gdf)
    gdf = gdf[gdf.within(area)].reset_index(drop=True)  # box -> neighborhood polygons

    out = RAW_DIR / "elevation_points_lowermanhattan.parquet"
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(out)
    print(f"{in_box} points in bounding box, {len(gdf)} inside the neighborhoods -> {out}")
    print(gdf.groupby("kind")["elevation_ft"].agg(["count", "min", "median", "max"]).round(1).to_string())


if __name__ == "__main__":
    main()
