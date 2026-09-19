"""Attach a location to each sidewalk violation.

Violations carry no coordinates, so the location is built through the tax lot:
    violation --bblid--> Lot Info (boro, block, lot) --> BBL --> PLUTO lot point --> nearest LION street

The BBL is boro * 1e9 + block * 1e4 + lot. Lot points come from PLUTO (Socrata 64uk-42ks),
fetched for Manhattan community districts 1-3. Each point is snapped to a walkable LION segment
within ``--max-snap`` feet, preferring a segment whose street name equals the violation's
``onstname`` (so a corner lot does not snap to the wrong street), then the closest one.

The point is the middle of the lot, not the sidewalk itself, so treat the location as
"the block face in front of this lot".

Inputs:  data/raw/lots_manhattan.csv, data/processed/violations.csv, data/processed/lion_streets.parquet
Output:  data/processed/violations_located.parquet  (points, EPSG:2263)
         data/raw/pluto_lower_manhattan.csv          (cached lot points)

Usage:
    python backend/scripts/locate_violations.py
    python backend/scripts/locate_violations.py --max-snap 200 --refresh

Set SOCRATA_APP_TOKEN to raise the API rate limit (optional).
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.strtree import STRtree

BACKEND = Path(__file__).resolve().parents[1]
RAW = BACKEND / "data" / "raw"
PROC = BACKEND / "data" / "processed"
FT = "EPSG:2263"

PLUTO = "https://data.cityofnewyork.us/resource/64uk-42ks.json"
PAGE = 50_000
HEADERS = {"X-App-Token": t} if (t := os.getenv("SOCRATA_APP_TOKEN")) else {}


def fetch_pluto(refresh: bool) -> pd.DataFrame:
    cache = RAW / "pluto_lower_manhattan.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache)
    rows, offset = [], 0
    while True:
        r = requests.get(
            PLUTO,
            params={
                "$select": "bbl,latitude,longitude,address",
                "$where": "borough='MN' AND cd in('101','102','103') AND latitude IS NOT NULL",
                "$order": "bbl",
                "$limit": PAGE,
                "$offset": offset,
            },
            headers=HEADERS,
            timeout=180,
        )
        r.raise_for_status()
        page = r.json()
        rows += page
        if len(page) < PAGE:
            break
        offset += PAGE
    df = pd.DataFrame(rows)
    df["bbl"] = df["bbl"].astype(float).astype("int64")
    df.to_csv(cache, index=False)
    return df


def norm(s) -> str:
    return " ".join(s.upper().split()) if isinstance(s, str) else ""


def snap(points: gpd.GeoDataFrame, streets: gpd.GeoDataFrame, max_snap: float) -> gpd.GeoDataFrame:
    tree = STRtree(streets.geometry.values)
    names = streets["Street"].map(norm).tolist()
    seg_ids = streets["SegmentID"].tolist()
    out = []
    for pt, street in zip(points.geometry, points["onstname"].map(norm)):
        best = None
        for j in tree.query(pt.buffer(max_snap)):
            d = pt.distance(streets.geometry.iloc[j])
            if d > max_snap:
                continue
            key = (names[j] != street, d)  # name match first, then distance
            if best is None or key < best[0]:
                best = (key, j, d)
        if best is None:
            out.append((None, None, None))
        else:
            (mismatch, _), j, d = best
            out.append((seg_ids[j], round(d, 1), not mismatch))
    res = points.copy()
    res["segment_id"], res["snap_dist_ft"], res["name_match"] = zip(*out)
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-snap", type=float, default=150.0, help="max ft from lot point to a street segment")
    ap.add_argument("--refresh", action="store_true", help="re-download PLUTO instead of using the cache")
    args = ap.parse_args()

    viol = pd.read_csv(PROC / "violations.csv", low_memory=False)
    lots = pd.read_csv(RAW / "lots_manhattan.csv").drop_duplicates("bblid")
    lots["bbl"] = lots["boro"] * 10**9 + lots["block"] * 10**4 + lots["lot"]
    pluto = fetch_pluto(args.refresh).drop_duplicates("bbl")
    print(f"{len(pluto)} PLUTO lots in CD1-3")

    v = viol.merge(lots[["bblid", "bbl"]], on="bblid", how="left").merge(
        pluto, on="bbl", how="left"
    )
    no_lot = v["latitude"].isna()
    print(f"violations: {len(v)}; no PLUTO lot for {int(no_lot.sum())} "
          f"(condo billing lots or lots renumbered since)")
    v = v[~no_lot]

    pts = gpd.GeoDataFrame(
        v, geometry=gpd.points_from_xy(v["longitude"].astype(float), v["latitude"].astype(float)), crs="EPSG:4326"
    ).to_crs(FT)
    streets = gpd.read_parquet(PROC / "lion_streets.parquet")
    located = snap(pts, streets, args.max_snap)

    ok = located["segment_id"].notna()
    print(f"snapped to a street within {args.max_snap:.0f} ft: {int(ok.sum())} of {len(located)}")
    print(f"  by street name: {int(located['name_match'].fillna(False).sum())}; "
          f"median snap distance: {located['snap_dist_ft'].median():.0f} ft")
    print(f"  open violations located: {int((located['is_open'] & ok).sum())} of {int(viol['is_open'].sum())}")

    located = located.rename(columns={"latitude": "lot_lat", "longitude": "lot_lon"})
    located.to_parquet(PROC / "violations_located.parquet")
    print("Saved violations_located.parquet")


if __name__ == "__main__":
    main()
