"""Load the pedestrian graph and find the cheapest accessible route for a mobility profile.

The graph comes from backend/scripts/ (build_graph.py, then attach_attributes.py):
    data/processed/graph_nodes_attrs.parquet, graph_edges_attrs.parquet   (EPSG:2263, feet)
Set CLEARCURB_DATA to read them from somewhere else.

Start and end points are snapped to the nearest sidewalk corner that is connected to the rest of the
network *under the chosen profile*, so a point next to a blocked island never strands the route.
A route is only returned over crossings with a verified ramp unless ``allow_unverified`` is set.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import networkx as nx
import shapely
from pyproj import Transformer
from shapely.geometry import LineString, Point, mapping
from shapely.strtree import STRtree

from .profiles import PROFILES, Profile, evaluate_edge, with_unverified_crossings

DATA_DIR = Path(os.environ.get("CLEARCURB_DATA", Path(__file__).resolve().parents[1] / "data" / "processed"))
SNAP_RADII_FT = (150, 300, 600)
MAX_SNAP_FT = 600
FT_PER_MILE = 5280
WALK_FT_PER_MIN = {"manual": 260, "power": 300, "walker": 160}  # rough speeds for a time estimate

# Order matters: the first matching keyword picks the category shown to the user.
NOTE_CATEGORIES = [
    ("blocked", "blocked"),
    ("step street", "steps"),
    ("trip hazard", "trip hazard"),
    ("missing sidewalk", "missing sidewalk"),
    ("broken pavement", "broken pavement"),
    ("undermined", "undermined sidewalk"),
    ("sloped defect", "sloped defect"),
    ("open violation", "open violation"),
    ("no verified ramp", "no verified ramp"),
    ("ramp slope", "steep ramp"),
    ("cross slope", "cross slope"),
    ("curb lip", "curb lip"),
    ("grade", "steep grade"),
]


class NoRoute(Exception):
    """No route exists for these points and this profile."""


class SamePoint(ValueError):
    """Start and end are effectively the same place."""


class OutsideCoverage(Exception):
    """A point is too far from the mapped network."""


@dataclass
class Route:
    feature_collection: dict
    summary: dict
    snapped: dict


@dataclass
class _ProfileGraph:
    graph: nx.DiGraph
    component: frozenset[int]
    blocked_edges: int
    tree: STRtree
    tree_ids: list[int]


@dataclass
class RouteEngine:
    nodes: gpd.GeoDataFrame
    edges: gpd.GeoDataFrame
    _edge_attrs: list[dict] = field(default_factory=list, repr=False)
    _cache: dict = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, data_dir: Path = DATA_DIR) -> "RouteEngine":
        nodes = gpd.read_parquet(data_dir / "graph_nodes_attrs.parquet")
        edges = gpd.read_parquet(data_dir / "graph_edges_attrs.parquet")
        engine = cls(nodes=nodes, edges=edges)
        engine._edge_attrs = edges.drop(columns="geometry").to_dict("records")
        engine._geoms = edges.geometry.values
        engine._xy = dict(zip(nodes["node_id"], zip(nodes.geometry.x, nodes.geometry.y)))
        engine._kind = dict(zip(nodes["node_id"], nodes["kind"]))
        engine._to_ft = Transformer.from_crs("EPSG:4326", "EPSG:2263", always_xy=True)
        engine._to_ll = Transformer.from_crs("EPSG:2263", "EPSG:4326", always_xy=True)
        return engine

    # ---- graph per profile ---------------------------------------------------------------------
    def _profile_graph(self, profile: Profile) -> _ProfileGraph:
        key = (profile, )
        if key in self._cache:
            return self._cache[key]
        G = nx.DiGraph()
        blocked = 0
        for i, e in enumerate(self._edge_attrs):
            for forward, (a, b) in ((True, (e["u"], e["v"])), (False, (e["v"], e["u"]))):
                cost, _ = evaluate_edge(e, profile, forward)
                if cost is None:
                    blocked += 1
                elif not G.has_edge(a, b) or cost < G[a][b]["cost"]:
                    G.add_edge(a, b, cost=cost, edge=i, forward=forward)
        component = frozenset(max(nx.weakly_connected_components(G), key=len))
        # Snap targets: corners in the main connected piece.
        ids = [n for n in component if self._kind[n] == "corner"]
        tree = STRtree([Point(self._xy[n]) for n in ids])
        pg = _ProfileGraph(G, component, blocked, tree, ids)
        self._cache[key] = pg
        return pg

    def warm(self) -> None:
        for p in PROFILES.values():
            self._profile_graph(p)

    # ---- snapping ------------------------------------------------------------------------------
    def _snap(self, pg: _ProfileGraph, lon: float, lat: float) -> tuple[int, float]:
        x, y = self._to_ft.transform(lon, lat)
        pt = Point(x, y)
        for radius in SNAP_RADII_FT:
            hits = pg.tree.query(pt.buffer(radius))
            if len(hits):
                dists = shapely.distance(pt, pg.tree.geometries[hits])
                j = int(dists.argmin())
                if dists[j] <= MAX_SNAP_FT:
                    return pg.tree_ids[int(hits[j])], float(dists[j])
        raise OutsideCoverage(f"({lat:.5f}, {lon:.5f}) is more than {MAX_SNAP_FT} ft from the mapped sidewalks")

    def _ll_point(self, node_id: int) -> list[float]:
        lon, lat = self._to_ll.transform(*self._xy[node_id])
        return [round(lon, 6), round(lat, 6)]

    # ---- routing -------------------------------------------------------------------------------
    def route(self, start: tuple[float, float], end: tuple[float, float], profile_key: str,
              allow_unverified: bool = False) -> Route:
        """start and end are (lat, lon)."""
        profile = PROFILES[profile_key]
        if allow_unverified:
            profile = with_unverified_crossings(profile)
        pg = self._profile_graph(profile)

        s, s_dist = self._snap(pg, start[1], start[0])
        t, t_dist = self._snap(pg, end[1], end[0])
        if s == t:
            raise SamePoint("Start and end are at the same place; there is nothing to route.")
        try:
            path = nx.shortest_path(pg.graph, s, t, weight="cost")
        except nx.NetworkXNoPath as exc:
            raise NoRoute("No route found for this profile.") from exc

        features, counts, cost, length = [], Counter(), 0.0, 0.0
        max_grade, ascent, uses_unverified = 0.0, 0.0, False
        for a, b in zip(path, path[1:]):
            data = pg.graph[a][b]
            e = self._edge_attrs[data["edge"]]
            forward = data["forward"]
            edge_cost, notes = evaluate_edge(e, profile, forward)
            cost += edge_cost
            length += e["length_ft"]
            geom: LineString = self._geoms[data["edge"]]
            coords = list(geom.coords) if forward else list(geom.coords)[::-1]
            # Crossing lines stop 10-15 ft short of their corner nodes; join every edge end to its node.
            coords[0], coords[-1] = self._xy[a], self._xy[b]
            ll = [self._to_ll.transform(x, y) for x, y in coords]
            for note in notes:
                cat = next((c for k, c in NOTE_CATEGORIES if k in note), None)
                if cat:
                    counts[cat] += 1
            grade = e.get("grade_pct")
            if e["edge_type"] in ("sidewalk", "step") and grade == grade and grade is not None:
                g_travel = grade if forward else -grade
                max_grade = max(max_grade, abs(grade))
                ascent += max(g_travel, 0) / 100 * e["length_ft"]
            if e["edge_type"] == "crossing" and e.get("ramp_status") in ("one", "none") and not e.get("raised"):
                uses_unverified = True
            features.append({
                "type": "Feature",
                "geometry": mapping(LineString([(round(x, 6), round(y, 6)) for x, y in ll])),
                "properties": {"edge_type": e["edge_type"], "length_ft": round(e["length_ft"], 1),
                               "warnings": notes},
            })

        feature_collection = {"type": "FeatureCollection", "features": features}
        crossings = sum(1 for f in features if f["properties"]["edge_type"] == "crossing")
        summary = {
            "profile": profile.key,
            "length_ft": round(length),
            "length_miles": round(length / FT_PER_MILE, 2),
            "estimated_minutes": round(length / WALK_FT_PER_MIN[profile.key], 1),
            "crossings": crossings,
            "max_grade_pct": round(max_grade, 1),
            "total_ascent_ft": round(ascent, 1),
            "uses_unverified_crossings": uses_unverified,
            "warning_counts": dict(counts),
            "detour_vs_shortest": None,
        }
        # How much longer than the plain shortest path? Only meaningful against an all-passable baseline.
        summary["detour_vs_shortest"] = self._detour(s, t, length)
        return Route(
            feature_collection=feature_collection,
            summary=summary,
            snapped={
                "start": {"lonlat": self._ll_point(s), "snap_distance_ft": round(s_dist)},
                "end": {"lonlat": self._ll_point(t), "snap_distance_ft": round(t_dist)},
            },
        )

    def _detour(self, s: int, t: int, route_length: float) -> float | None:
        if "_plain" not in self._cache:
            G = nx.Graph()
            G.add_weighted_edges_from((e["u"], e["v"], e["length_ft"]) for e in self._edge_attrs)
            self._cache["_plain"] = G
        try:
            plain = nx.shortest_path_length(self._cache["_plain"], s, t, weight="weight")
        except nx.NetworkXNoPath:
            return None
        return round(route_length / plain, 2) if plain > 0 else None
