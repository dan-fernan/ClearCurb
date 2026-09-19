"""Check how each mobility profile behaves on the graph before any routing API exists.

For every profile (and again with unverified crossings allowed) it reports:
    blocked edges by type and reason
    how much of the graph is still connected
    over random node pairs in the largest connected piece: how many are reachable, and how much longer
    the cheapest route is than the shortest path

Usage:
    python backend/scripts/evaluate_profiles.py
    python backend/scripts/evaluate_profiles.py --pairs 300
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.profiles import PROFILES, evaluate_edge, with_unverified_crossings  # noqa: E402

PROC = BACKEND / "data" / "processed"


def build_digraph(edges, profile) -> tuple[nx.DiGraph, Counter]:
    G = nx.DiGraph()
    blocked: Counter = Counter()
    for e in edges.drop(columns="geometry").to_dict("records"):
        for forward, (a, b) in ((True, (e["u"], e["v"])), (False, (e["v"], e["u"]))):
            cost, notes = evaluate_edge(e, profile, forward)
            if cost is None:
                blocked[(e["edge_type"], notes[0].split(" ")[1] if notes else "?")] += 1
                continue
            if not G.has_edge(a, b) or cost < G[a][b]["cost"]:
                G.add_edge(a, b, cost=cost, length=e["length_ft"])
    return G, blocked


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs", type=int, default=150)
    args = ap.parse_args()

    nodes = gpd.read_parquet(PROC / "graph_nodes_attrs.parquet")
    edges = gpd.read_parquet(PROC / "graph_edges_attrs.parquet")
    print(f"{len(nodes)} nodes, {len(edges)} edges\n")

    # Baseline: everything passable, cost = length. Sample pairs from its largest piece.
    base = nx.Graph()
    base.add_weighted_edges_from(zip(edges["u"], edges["v"], edges["length_ft"]))
    core = sorted(nx.connected_components(base), key=len, reverse=True)[0]
    rng = random.Random(7)
    pairs = [tuple(rng.sample(sorted(core), 2)) for _ in range(args.pairs)]
    shortest = {p: nx.shortest_path_length(base, *p, weight="weight") for p in pairs}

    xy = dict(zip(nodes["node_id"], zip(nodes.geometry.x, nodes.geometry.y)))
    far = [p for p in pairs if np.hypot(*np.subtract(xy[p[0]], xy[p[1]])) > 1000]
    print(f"{len(pairs)} random node pairs ({len(far)} more than 1,000 ft apart)\n")

    for base_profile in PROFILES.values():
        for profile in (base_profile, with_unverified_crossings(base_profile)):
            tag = f"{profile.label}{' + unverified crossings' if profile.allow_unverified else ''}"
            G, blocked = build_digraph(edges, profile)
            comp = max(nx.weakly_connected_components(G), key=len)
            print(f"== {tag}")
            print(f"   blocked directed edges: {sum(blocked.values())} "
                  + str({f'{t}:{r}': n for (t, r), n in blocked.most_common(6)}))
            print(f"   largest connected piece: {len(comp) / len(nodes):.1%} of nodes")
            ratios, reachable = [], 0
            for p in pairs:
                try:
                    cost = nx.shortest_path_length(G, *p, weight="cost")
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue
                reachable += 1
                if p in far:
                    ratios.append(cost / shortest[p])
            print(f"   reachable pairs: {reachable / len(pairs):.0%}; "
                  f"cost vs shortest path (long trips): median {np.median(ratios):.2f}x, "
                  f"p90 {np.percentile(ratios, 90):.2f}x\n")


if __name__ == "__main__":
    main()
