"""Derive street crossings from LION intersections and match them to curb ramps.

LION has street centerlines only, so a crossing is synthesised: at every real
intersection node (3+ walkable street legs) each leg gets one crossing, a line
perpendicular to that leg, set back from the node by the cross street's half
width and as long as the leg's roadbed. Each crossing end is then matched to the
nearest surveyed ramp (preferring ramps whose ``ramp_onstr`` names the street
being crossed).

Inputs  (from fetch_network_data.py, download_ramps.py):
    lion_lowermanhattan.parquet, ramps_lowermanhattan.parquet,
    raised_crosswalks_lowermanhattan.parquet  (optional)
Output:
    crossings_lowermanhattan.parquet   LineStrings, EPSG:4326

Key columns:
    ramp_status   'both' | 'one' | 'none'   ramps found at the two ends
    raised        a DOT raised crosswalk exists at this intersection node
                  (matched by node only, not by leg)
    *_a / *_b     matched ramp id, running slope, and detectable-warning state at each end

Distances are computed in EPSG:2263 (US survey feet), then converted back.

Usage:
    python backend/scripts/build_crossings.py
    python backend/scripts/build_crossings.py --tolerance 60
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point
from shapely.ops import linemerge
from shapely.strtree import STRtree

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
FT = "EPSG:2263"

DEFAULT_WIDTH_FT = 30.0   # used when LION has no roadbed width
MIN_WIDTH_FT = 16.0
CURB_MARGIN_FT = 4.0      # extend past the roadbed edge onto the sidewalk
SETBACK_MARGIN_FT = 8.0   # crossing sits this far beyond the cross street's edge
ADA_MAX_RUNNING_SLOPE = 8.33  # percent; assumes the ramp data reports percent


def load_legs(lion: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Walkable Manhattan street segments, in feet."""
    m = lion[(lion["LBoro"] == 1) | (lion["RBoro"] == 1)]
    m = m[
        (m["FeatureTyp"].astype(str).str.strip() == "0")
        & (m["RW_TYPE"].astype(str).str.strip() == "1")
        & (m["NonPed"].astype(str).str.strip() == "")
    ]
    m = m.to_crs(FT).copy()
    m["node_from"] = m["NodeIDFrom"].astype(int)
    m["node_to"] = m["NodeIDTo"].astype(int)
    width = pd.to_numeric(m["StreetWidth_Max"], errors="coerce")
    m["width_ft"] = width.where(width >= MIN_WIDTH_FT, DEFAULT_WIDTH_FT)
    return m


def oriented_line(geom, from_start: bool) -> LineString | None:
    if geom.geom_type == "MultiLineString":
        geom = linemerge(geom)
        if geom.geom_type == "MultiLineString":
            geom = max(geom.geoms, key=lambda g: g.length)
    if geom.is_empty or geom.length == 0:
        return None
    return geom if from_start else LineString(list(geom.coords)[::-1])


def build_crossings(legs: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    # One row per (node, leg); a segment contributes a leg to each of its two nodes.
    ends = pd.concat(
        [
            legs.assign(node_id=legs["node_from"], from_start=True),
            legs.assign(node_id=legs["node_to"], from_start=False),
        ]
    )
    counts = ends.groupby("node_id").size()
    ends = ends[ends["node_id"].map(counts) >= 3]

    rows = []
    for node_id, grp in ends.groupby("node_id"):
        for leg in grp.itertuples():
            others = grp[grp["SegmentID"] != leg.SegmentID]
            line = oriented_line(leg.geometry, leg.from_start)
            if line is None or others.empty:
                continue
            setback = others["width_ft"].max() / 2 + SETBACK_MARGIN_FT
            setback = min(setback, line.length * 0.45)
            c = line.interpolate(setback)
            p0, p1 = line.interpolate(max(setback - 2, 0)), line.interpolate(setback + 2)
            dx, dy = p1.x - p0.x, p1.y - p0.y
            norm = math.hypot(dx, dy)
            if norm == 0:
                continue
            half = leg.width_ft / 2 + CURB_MARGIN_FT
            nx, ny = -dy / norm * half, dx / norm * half
            rows.append(
                {
                    "node_id": int(node_id),
                    "segment_id": leg.SegmentID,
                    "street": leg.Street,
                    "width_ft": leg.width_ft,
                    "geometry": LineString([(c.x - nx, c.y - ny), (c.x + nx, c.y + ny)]),
                }
            )
    out = gpd.GeoDataFrame(rows, crs=FT)
    out.insert(0, "crossing_id", range(len(out)))
    return out


def norm_names(s) -> set[str]:
    if not isinstance(s, str):
        return set()
    return {p.strip().upper() for p in s.split(",") if p.strip()}


def match_ramps(crossings: gpd.GeoDataFrame, ramps: gpd.GeoDataFrame, tol: float) -> gpd.GeoDataFrame:
    ramps = ramps.to_crs(FT).reset_index(drop=True)
    tree = STRtree(ramps.geometry.values)
    names = ramps["ramp_onstr"].map(norm_names).tolist()
    num = lambda col: pd.to_numeric(ramps[col], errors="coerce")  # noqa: E731
    # The survey uses 999 as a "not measured" placeholder.
    run_slope = num("ramp_running_slope_total").where(lambda x: x < 100)
    cross_slope = num("ramp_cross_slope").where(lambda x: x < 100)

    keys = ("id", "slope", "cross", "dws", "by_name", "dist")
    sides = {side: {k: [] for k in keys} for side in "ab"}
    for geom, street in zip(crossings.geometry, crossings["street"]):
        street_n = street.strip().upper() if isinstance(street, str) else ""
        for side, end in (("a", Point(geom.coords[0])), ("b", Point(geom.coords[-1]))):
            idx = tree.query(end.buffer(tol))
            best = None
            for j in idx:
                d = end.distance(ramps.geometry[j])
                if d > tol:
                    continue
                key = (street_n not in names[j], d)  # name match first, then distance
                if best is None or key < best[0]:
                    best = (key, j, d)
            s = sides[side]
            if best is None:
                for k in s:
                    s[k].append(None)
            else:
                (mismatch, _), j, d = best
                s["id"].append(ramps.at[j, "rampid"])
                s["slope"].append(run_slope[j])
                s["cross"].append(cross_slope[j])
                s["dws"].append(ramps.at[j, "dws_conditions"])
                s["by_name"].append(not mismatch)
                s["dist"].append(round(d, 1))

    out = crossings.copy()
    for side, s in sides.items():
        out[f"ramp_id_{side}"] = s["id"]
        out[f"running_slope_{side}"] = s["slope"]
        out[f"cross_slope_{side}"] = s["cross"]
        out[f"dws_{side}"] = s["dws"]
        out[f"name_match_{side}"] = s["by_name"]
        out[f"ramp_dist_ft_{side}"] = s["dist"]
    n = out[["ramp_id_a", "ramp_id_b"]].notna().sum(axis=1)
    out["ramp_status"] = n.map({2: "both", 1: "one", 0: "none"})
    steep = lambda c: out[c].astype(float) > ADA_MAX_RUNNING_SLOPE  # noqa: E731
    out["steep_ramp"] = steep("running_slope_a") | steep("running_slope_b")
    out["dws_missing"] = (out["dws_a"] == "Missing") | (out["dws_b"] == "Missing")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tolerance", type=float, default=45.0, help="max ft from a crossing end to a ramp")
    ap.add_argument("--raw-dir", type=Path, default=RAW)
    args = ap.parse_args()

    legs = load_legs(gpd.read_parquet(args.raw_dir / "lion_lowermanhattan.parquet"))
    print(f"{len(legs)} walkable street segments")
    crossings = build_crossings(legs)
    print(f"{len(crossings)} crossings at {crossings['node_id'].nunique()} intersections")

    ramps = gpd.read_parquet(args.raw_dir / "ramps_lowermanhattan.parquet")
    crossings = match_ramps(crossings, ramps, args.tolerance)

    raised_path = args.raw_dir / "raised_crosswalks_lowermanhattan.parquet"
    raised_nodes = set(gpd.read_parquet(raised_path)["nodeid"]) if raised_path.exists() else set()
    crossings["raised"] = crossings["node_id"].isin(raised_nodes)

    print(crossings["ramp_status"].value_counts().to_string())
    both = crossings[crossings["ramp_status"] != "none"]
    matched = pd.concat([both["name_match_a"].dropna(), both["name_match_b"].dropna()])
    print(f"ramp matches by street name: {matched.mean():.0%}; "
          f"steep: {int(crossings['steep_ramp'].sum())}, dws missing: {int(crossings['dws_missing'].sum())}, "
          f"raised: {int(crossings['raised'].sum())}")

    crossings.to_crs("EPSG:4326").to_parquet(args.raw_dir / "crossings_lowermanhattan.parquet")
    print("Saved crossings_lowermanhattan.parquet")


if __name__ == "__main__":
    main()
