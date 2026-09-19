"""Attach accessibility attributes to the routing graph.

Reads   data/processed/graph_nodes.parquet, graph_edges.parquet          (from build_graph.py)
        elevation_points.parquet, violations_located.parquet, crossings.parquet, ramps.parquet
Writes  data/processed/graph_nodes_attrs.parquet, graph_edges_attrs.parquet

Node attributes
    elevation_ft     inverse-distance-weighted elevation from nearby ground points (null if too few)

Sidewalk / step edge attributes
    grade_pct        signed grade in the u -> v direction, from the LION-node elevations at the two
                     ends of the street segment divided by the centerline length
    grade_reliable   false on segments under 60 ft, where a few feet of elevation noise swings the grade
    n_open_viol, viol_trip_hazard, viol_broken, viol_slope, viol_undermined, viol_sw_missing
                     open sidewalk violations on this side of the segment (matched by street name only)

Crossing edge attributes (grade is left null: crossings run across the street, so DEM points cannot
resolve it, and the surveyed ramp slopes are the better signal)
    ramp_status, raised, ramp_slope_max, ramp_cross_slope_max, lip_in_max, dws_missing, dws_defective

Usage:
    python backend/scripts/attach_attributes.py
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import Point
from shapely.strtree import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_graph import merged_line  # noqa: E402

PROC = Path(__file__).resolve().parents[1] / "data" / "processed"

IDW_RADII_FT = (150, 300)   # widen once if a node has too few points nearby
IDW_MIN_POINTS = 3
IDW_POWER = 2
MIN_RELIABLE_SEGMENT_FT = 60

VIOLATION_FLAGS = {
    "viol_trip_hazard": "trip_haz",
    "viol_broken": "broken",
    "viol_slope": "slope",
    "viol_undermined": "undermined",
    "viol_sw_missing": "sw_missing",
}


def interpolate_elevation(points: list[Point], elev: gpd.GeoDataFrame) -> np.ndarray:
    geoms = elev.geometry.values
    vals = elev["elevation"].to_numpy(dtype=float)
    tree = STRtree(geoms)
    out = np.full(len(points), np.nan)
    for i, p in enumerate(points):
        for radius in IDW_RADII_FT:
            idx = tree.query(p.buffer(radius))
            if len(idx) == 0:
                continue
            d = shapely.distance(p, geoms[idx])
            keep = d <= radius
            if keep.sum() >= IDW_MIN_POINTS:
                w = 1.0 / np.maximum(d[keep], 5.0) ** IDW_POWER
                out[i] = float((w * vals[idx][keep]).sum() / w.sum())
                break
    return out


def lion_node_positions(streets: gpd.GeoDataFrame) -> dict[int, tuple[float, float]]:
    ends: dict[int, list] = defaultdict(list)
    for r in streets.itertuples():
        line = merged_line(r.geometry)
        if line is None:
            continue
        ends[int(r.NodeIDFrom)].append(line.coords[0])
        ends[int(r.NodeIDTo)].append(line.coords[-1])
    return {n: tuple(np.mean(pts, axis=0)) for n, pts in ends.items()}


def side_of_segment(line, pt: Point) -> str:
    """Which side of the centerline (travelling from -> to) the point falls on."""
    d = line.project(pt)
    a, b = line.interpolate(max(d - 2, 0)), line.interpolate(min(d + 2, line.length))
    cross = (b.x - a.x) * (pt.y - a.y) - (b.y - a.y) * (pt.x - a.x)
    return "left" if cross > 0 else "right"


def attach_grades(nodes, edges, streets, elev) -> None:
    pos = lion_node_positions(streets)
    lion_ids = list(pos)
    z_lion = dict(zip(lion_ids, interpolate_elevation([Point(pos[n]) for n in lion_ids], elev)))
    nodes["elevation_ft"] = interpolate_elevation(list(nodes.geometry), elev)
    print(f"elevation: {np.isfinite(list(z_lion.values())).mean():.1%} of LION nodes, "
          f"{nodes['elevation_ft'].notna().mean():.1%} of graph nodes")

    seg = {r.SegmentID: (int(r.NodeIDFrom), int(r.NodeIDTo), merged_line(r.geometry)) for r in streets.itertuples()}
    grade, reliable = [], []
    for e in edges.itertuples():
        if e.edge_type not in ("sidewalk", "step") or e.segment_id not in seg:
            grade.append(np.nan)
            reliable.append(False)
            continue
        a, b, line = seg[e.segment_id]
        za, zb = z_lion.get(a, np.nan), z_lion.get(b, np.nan)
        grade.append(100.0 * (zb - za) / line.length if np.isfinite(za) and np.isfinite(zb) else np.nan)
        reliable.append(line.length >= MIN_RELIABLE_SEGMENT_FT)
    edges["grade_pct"] = grade
    edges["grade_reliable"] = reliable


def attach_violations(edges, streets) -> gpd.GeoDataFrame:
    viol = gpd.read_parquet(PROC / "violations_located.parquet")
    total = len(viol)
    viol = viol[viol["is_open"] & viol["segment_id"].notna() & viol["name_match"].fillna(False).astype(bool)]
    print(f"violations attached: {len(viol)} open street-name-matched (of {total} located)")
    lines = {r.SegmentID: merged_line(r.geometry) for r in streets.itertuples()}

    rows = []
    for v in viol.itertuples():
        line = lines.get(v.segment_id)
        if line is None:
            continue
        rows.append({"segment_id": v.segment_id, "side": side_of_segment(line, v.geometry),
                     **{out: bool(getattr(v, col)) for out, col in VIOLATION_FLAGS.items()}})
    df = pd.DataFrame(rows)
    agg = df.groupby(["segment_id", "side"]).agg(
        n_open_viol=("segment_id", "size"), **{c: (c, "sum") for c in VIOLATION_FLAGS}
    ).reset_index()
    edges = edges.merge(agg, on=["segment_id", "side"], how="left")
    for c in ["n_open_viol", *VIOLATION_FLAGS]:
        edges[c] = edges[c].fillna(0).astype(int)
    print(f"  sidewalk edges with an open violation: {int((edges['n_open_viol'] > 0).sum())}; "
          f"with a trip hazard: {int((edges['viol_trip_hazard'] > 0).sum())}")
    return edges


def crossing_attributes() -> pd.DataFrame:
    c = gpd.read_parquet(PROC / "crossings.parquet")
    ramps = gpd.read_parquet(PROC / "ramps.parquet").set_index("rampid")

    def ramp_col(ids, col):
        return ids.map(ramps[col])

    out = pd.DataFrame({"crossing_id": c["crossing_id"], "ramp_status": c["ramp_status"], "raised": c["raised"]})
    out["ramp_slope_max"] = c[["running_slope_a", "running_slope_b"]].astype(float).max(axis=1)
    out["ramp_cross_slope_max"] = c[["cross_slope_a", "cross_slope_b"]].astype(float).abs().max(axis=1)
    lips = pd.concat([ramp_col(c["ramp_id_a"], "curb_reveal"), ramp_col(c["ramp_id_b"], "curb_reveal")], axis=1)
    out["lip_in_max"] = lips.astype(float).max(axis=1)
    out["dws_missing"] = c["dws_missing"].astype(bool)
    out["dws_defective"] = c[["dws_a", "dws_b"]].apply(lambda s: s.str.contains("Defective", na=False)).any(axis=1)
    return out


def main() -> None:
    nodes = gpd.read_parquet(PROC / "graph_nodes.parquet")
    edges = gpd.read_parquet(PROC / "graph_edges.parquet")
    streets = gpd.read_parquet(PROC / "lion_streets.parquet")
    elev = gpd.read_parquet(PROC / "elevation_points.parquet")

    attach_grades(nodes, edges, streets, elev)
    g = edges.loc[edges["grade_reliable"], "grade_pct"].abs().dropna()
    print(f"grade on {len(g)} reliable edges (abs %): "
          f"median {g.median():.1f}, p90 {g.quantile(.9):.1f}, p99 {g.quantile(.99):.1f}; "
          f">5%: {(g > 5).mean():.1%}, >8.33%: {(g > 8.33).mean():.1%}")

    edges = attach_violations(edges, streets)

    cx = crossing_attributes()
    keep = [c for c in cx.columns if c != "crossing_id"]
    edges = edges.drop(columns=[c for c in keep if c in edges.columns]).merge(cx, on="crossing_id", how="left")
    edges["raised"] = edges["raised"].fillna(False).astype(bool)
    edges["is_step"] = edges["edge_type"] == "step"
    print("crossing ramp_status:", edges.loc[edges["edge_type"] == "crossing", "ramp_status"].value_counts().to_dict())

    nodes.to_parquet(PROC / "graph_nodes_attrs.parquet")
    edges.to_parquet(PROC / "graph_edges_attrs.parquet")
    print("Saved graph_nodes_attrs.parquet, graph_edges_attrs.parquet")


if __name__ == "__main__":
    main()
