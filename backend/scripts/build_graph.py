"""Build the pedestrian routing graph (topology and geometry only, no accessibility attributes).

Model
    nodes   sidewalk corners: at every LION node there is one corner in each gap between
            neighbouring street legs (a dead end has one corner; a mid-block bend has two)
    edges   sidewalk   one per side of every street segment, an offset of the centerline
                       running from a corner at one end to a corner at the other
            crossing   links the two corners on either side of a street leg
                       (geometry comes from build_crossings.py)
            step       a step street; it has its own end nodes
            link       zero-length join between a step street end and the corners there

Corner position: the intersection of the two neighbouring legs' offset lines, each offset
by half the roadway width plus a small margin. Where the legs are nearly straight or
nearly parallel that intersection is unstable, so the corner is placed on the bisector instead.

Inputs   data/processed/lion_streets.parquet, crossings.parquet, sidewalks.parquet
Outputs  data/processed/graph_nodes.parquet, graph_edges.parquet   (EPSG:2263, feet)

Usage:
    python backend/scripts/build_graph.py
"""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import networkx as nx
import pandas as pd
from shapely.geometry import LineString, Point
from shapely.ops import linemerge, unary_union

PROC = Path(__file__).resolve().parents[1] / "data" / "processed"
FT = "EPSG:2263"

DEFAULT_WIDTH_FT = 30.0
MIN_WIDTH_FT = 16.0
CURB_MARGIN_FT = 4.0        # matches build_crossings.py so crossing ends land on the corners
STEP_WIDTH_FT = 10.0
LEG_PROBE_FT = 25.0         # distance along a leg used to measure its direction
UNSTABLE_SIN = 0.35         # |sin(gap angle)| below this uses the bisector fallback
SIDEWALK_NEAR_FT = 8.0      # diagnostic: how much of a sidewalk edge sits on a sidewalk polygon


def merged_line(geom) -> LineString | None:
    if geom.geom_type == "MultiLineString":
        geom = linemerge(geom)
        if geom.geom_type == "MultiLineString":
            geom = max(geom.geoms, key=lambda g: g.length)
    return None if geom.is_empty or geom.length == 0 else geom


def half_width(row) -> float:
    if row.is_step_street:
        return STEP_WIDTH_FT / 2 + CURB_MARGIN_FT
    w = pd.to_numeric(row.StreetWidth_Max, errors="coerce")
    w = w if w == w and w >= MIN_WIDTH_FT else DEFAULT_WIDTH_FT
    return w / 2 + CURB_MARGIN_FT


def unit(dx: float, dy: float) -> tuple[float, float]:
    n = math.hypot(dx, dy)
    return dx / n, dy / n


def corner_position(node: tuple[float, float], ua, ha: float, ub, hb: float, gap: float) -> tuple[float, float]:
    """Corner in the gap that runs counter-clockwise from leg a to leg b."""
    nx_, ny_ = node
    sin_gap = math.sin(gap)
    theta_a = math.atan2(ua[1], ua[0])
    bis = (math.cos(theta_a + gap / 2), math.sin(theta_a + gap / 2))
    fallback = (nx_ + bis[0] * (ha + hb) / 2, ny_ + bis[1] * (ha + hb) / 2)
    if abs(sin_gap) < UNSTABLE_SIN:
        return fallback
    # c . na = ha and c . nb = hb, with na = left normal of a and nb = right normal of b
    na, nb = (-ua[1], ua[0]), (ub[1], -ub[0])
    det = na[0] * nb[1] - na[1] * nb[0]
    cx = (ha * nb[1] - na[1] * hb) / det
    cy = (na[0] * hb - ha * nb[0]) / det
    if math.hypot(cx, cy) > 3 * max(ha, hb):
        return fallback
    return nx_ + cx, ny_ + cy


def main() -> None:
    streets = gpd.read_parquet(PROC / "lion_streets.parquet")
    crossings = gpd.read_parquet(PROC / "crossings.parquet")
    sidewalks = gpd.read_parquet(PROC / "sidewalks.parquet")

    # ---- segments and node positions ------------------------------------------------------------
    segs = {}
    node_xy: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for r in streets.itertuples():
        line = merged_line(r.geometry)
        if line is None:
            continue
        a, b = int(r.NodeIDFrom), int(r.NodeIDTo)
        segs[r.SegmentID] = dict(row=r, line=line, a=a, b=b, hw=half_width(r), step=bool(r.is_step_street))
        node_xy[a].append(line.coords[0])
        node_xy[b].append(line.coords[-1])
    pos = {n: tuple(map(lambda v: sum(v) / len(v), zip(*pts))) for n, pts in node_xy.items()}
    spread = max(
        math.hypot(x - pos[n][0], y - pos[n][1]) for n, pts in node_xy.items() for x, y in pts
    )
    print(f"{len(segs)} segments, {len(pos)} LION nodes; max endpoint disagreement at a node: {spread:.1f} ft")

    # ---- legs at each node (step streets are not part of the roadway corner geometry) -----------
    legs_at: dict[int, list[dict]] = defaultdict(list)
    for sid, s in segs.items():
        if s["step"]:
            continue
        for node, start in ((s["a"], True), (s["b"], False)):
            line = s["line"] if start else LineString(list(s["line"].coords)[::-1])
            probe = line.interpolate(min(LEG_PROBE_FT, line.length / 2))
            u = unit(probe.x - pos[node][0], probe.y - pos[node][1])
            legs_at[node].append(dict(sid=sid, u=u, hw=s["hw"], theta=math.atan2(u[1], u[0]), start=start))

    # ---- corner nodes ---------------------------------------------------------------------------
    node_rows: list[dict] = []
    corner_of: dict[tuple[int, str, bool], int] = {}   # (lion node, segment, side_is_left) -> corner id

    def add_node(kind: str, lion_node: int, xy) -> int:
        node_rows.append(dict(node_id=len(node_rows), kind=kind, lion_node=lion_node, geometry=Point(xy)))
        return len(node_rows) - 1

    for node, legs in legs_at.items():
        legs.sort(key=lambda l: l["theta"])
        d = len(legs)
        gap_corner = []
        for k in range(d):
            a, b = legs[k], legs[(k + 1) % d]
            if d == 1:
                xy = pos[node]
            else:
                gap = (b["theta"] - a["theta"]) % (2 * math.pi)
                xy = corner_position(pos[node], a["u"], a["hw"], b["u"], b["hw"], gap)
            gap_corner.append(add_node("corner", node, xy))
        for k, leg in enumerate(legs):
            corner_of[(node, leg["sid"], True)] = gap_corner[k]                 # left of the outward leg
            corner_of[(node, leg["sid"], False)] = gap_corner[(k - 1) % d]      # right of the outward leg

    edge_rows: list[dict] = []

    def add_edge(u: int, v: int, kind: str, geom: LineString, **extra) -> None:
        edge_rows.append(dict(edge_id=len(edge_rows), u=u, v=v, edge_type=kind, length_ft=geom.length,
                              geometry=geom, **extra))

    # ---- sidewalk edges -------------------------------------------------------------------------
    node_pt = {r["node_id"]: r["geometry"] for r in node_rows}
    for sid, s in segs.items():
        if s["step"]:
            continue
        line = s["line"]
        for side_left in (True, False):
            # Travelling a -> b, the left side at b is the right side of the leg pointing outward from b.
            u = corner_of[(s["a"], sid, side_left)]
            v = corner_of[(s["b"], sid, not side_left)]
            off = line.offset_curve(s["hw"] if side_left else -s["hw"])
            interior: list = []
            if off.geom_type == "LineString" and not off.is_empty:
                coords = list(off.coords)
                start = Point(line.coords[0])
                if start.distance(Point(coords[0])) > start.distance(Point(coords[-1])):
                    coords = coords[::-1]  # keep the offset running a -> b whichever way shapely returns it
                interior = coords[1:-1]
            pts = [node_pt[u].coords[0], *interior, node_pt[v].coords[0]]
            geom = LineString(pts) if len(set(pts)) > 1 else LineString([pts[0], pts[0]])
            add_edge(u, v, "sidewalk", geom, segment_id=sid, side="left" if side_left else "right")

    # ---- crossing edges -------------------------------------------------------------------------
    skipped = 0
    seen: set[tuple[int, str]] = set()
    for c in crossings.itertuples():
        key = (int(c.node_id), c.segment_id)
        if key in seen:
            continue
        left = corner_of.get((key[0], key[1], True))
        right = corner_of.get((key[0], key[1], False))
        if left is None or left == right:
            skipped += 1
            continue
        seen.add(key)
        # build_crossings.py draws the line from the right side of the leg to the left side
        add_edge(right, left, "crossing", c.geometry, segment_id=c.segment_id, crossing_id=int(c.crossing_id))
    print(f"crossings: {len(seen)} added, {skipped} skipped (leg missing from the graph)")

    # ---- step streets ---------------------------------------------------------------------------
    step_node: dict[int, int] = {}
    for sid, s in segs.items():
        if not s["step"]:
            continue
        ends = []
        for node in (s["a"], s["b"]):
            if node not in step_node:
                step_node[node] = add_node("step_end", node, pos[node])
                node_pt[step_node[node]] = node_rows[-1]["geometry"]
                for (n2, _sid, _left), cid in corner_of.items():
                    if n2 == node:
                        add_edge(step_node[node], cid,
                                 "link", LineString([pos[node], node_pt[cid].coords[0]]))
            ends.append(step_node[node])
        add_edge(ends[0], ends[1], "step", s["line"], segment_id=sid)

    nodes = gpd.GeoDataFrame(node_rows, crs=FT)
    edges = gpd.GeoDataFrame(edge_rows, crs=FT)

    # ---- diagnostic: does each sidewalk edge sit on a mapped sidewalk? ---------------------------
    near = unary_union(sidewalks.geometry).buffer(SIDEWALK_NEAR_FT)
    is_sw = edges["edge_type"] == "sidewalk"
    edges["sw_overlap"] = None
    edges.loc[is_sw, "sw_overlap"] = [
        (g.intersection(near).length / g.length) if g.length else 0.0 for g in edges.loc[is_sw, "geometry"]
    ]
    edges["sw_overlap"] = edges["sw_overlap"].astype(float)

    nodes.to_parquet(PROC / "graph_nodes.parquet")
    edges.to_parquet(PROC / "graph_edges.parquet")

    # ---- connectivity report --------------------------------------------------------------------
    G = nx.MultiGraph()
    G.add_nodes_from(nodes["node_id"])
    G.add_edges_from(zip(edges["u"], edges["v"]))
    comps = sorted(nx.connected_components(G), key=len, reverse=True)
    print(f"\nnodes: {len(nodes)}  edges: {len(edges)}")
    print(edges["edge_type"].value_counts().to_string())
    print(f"connected components: {len(comps)}; largest holds {len(comps[0]) / len(nodes):.1%} of nodes")
    print(f"next largest components: {[len(c) for c in comps[1:8]]}")
    sw = edges.loc[is_sw, "sw_overlap"]
    print(f"sidewalk edges within {SIDEWALK_NEAR_FT:.0f} ft of a sidewalk polygon: "
          f"median overlap {sw.median():.0%}; {(sw < 0.5).mean():.0%} of edges are under 50%")


if __name__ == "__main__":
    main()
