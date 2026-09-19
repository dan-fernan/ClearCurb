"""Write an interactive map for eyeballing the routing graph against the source data.

Layers (toggle them in the top-right control):
    Sidewalk polygons        the Planimetric sidewalks
    LION centerlines         the street lines the graph is built from
    Sidewalk edges           graph edges, green = on a mapped sidewalk, red = mostly off one
    Crossing edges           graph crossings, green = ramps at both ends, orange = one, red = none
    Corner nodes             graph nodes
    Ramps                    surveyed curb ramps

Output: backend/data/processed/graph_map.html (open it in a browser)

Usage:
    python backend/scripts/view_graph.py
    python backend/scripts/view_graph.py --open
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import folium
import geopandas as gpd
import shapely

PROC = Path(__file__).resolve().parents[1] / "data" / "processed"
CENTER = (40.7215, -73.9985)


def ll(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.to_crs("EPSG:4326")
    gdf["geometry"] = shapely.set_precision(gdf.geometry.values, 1e-6)  # ~4 inches; keeps the file small
    return gdf


def add(m, gdf, name, style, tooltip_cols, show=True, marker_radius=None):
    fg = folium.FeatureGroup(name=name, show=show)
    kwargs = dict(
        style_function=style,
        tooltip=folium.GeoJsonTooltip(fields=tooltip_cols) if tooltip_cols else None,
    )
    if marker_radius:
        kwargs["marker"] = folium.CircleMarker(radius=marker_radius)
    folium.GeoJson(gdf[tooltip_cols + ["geometry"]].to_json() if tooltip_cols else gdf[["geometry"]].to_json(),
                   **kwargs).add_to(fg)
    fg.add_to(m)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--open", action="store_true", help="open the map in the default browser")
    args = ap.parse_args()

    sidewalks = ll(gpd.read_parquet(PROC / "sidewalks.parquet"))
    lion = ll(gpd.read_parquet(PROC / "lion_streets.parquet"))
    edges = ll(gpd.read_parquet(PROC / "graph_edges.parquet"))
    nodes = ll(gpd.read_parquet(PROC / "graph_nodes.parquet"))
    ramps = ll(gpd.read_parquet(PROC / "ramps.parquet"))
    crossings = ll(gpd.read_parquet(PROC / "crossings.parquet"))

    sw_edges = edges[edges["edge_type"] == "sidewalk"].copy()
    sw_edges["overlap"] = (sw_edges["sw_overlap"] * 100).round(0).astype(int).astype(str) + "%"
    sw_edges["len"] = sw_edges["length_ft"].round(0).astype(int)
    x_edges = edges[edges["edge_type"] == "crossing"].merge(
        crossings[["crossing_id", "ramp_status", "street"]], on="crossing_id", how="left"
    )
    x_edges = gpd.GeoDataFrame(x_edges, geometry="geometry", crs="EPSG:4326")
    x_edges["len"] = x_edges["length_ft"].round(0).astype(int)
    nodes = nodes.assign(node=nodes["node_id"].astype(int))
    ramps = ramps.assign(dws=ramps["dws_conditions"].fillna("?"), slope=ramps["ramp_running_slope_total"].round(1))

    m = folium.Map(location=CENTER, zoom_start=16, tiles=None, prefer_canvas=True)
    # OpenStreetMap's tile servers reject pages opened from file://, so use Esri's street basemap.
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
        attr="Esri, HERE, Garmin, OpenStreetMap contributors",
        name="Basemap",
        max_zoom=19,
    ).add_to(m)

    add(m, sidewalks, "Sidewalk polygons",
        lambda f: dict(color="#7a7a7a", weight=0.5, fillColor="#bdbdbd", fillOpacity=0.5), [])
    add(m, lion, "LION centerlines",
        lambda f: dict(color="#444", weight=1, dashArray="4 4"), ["Street", "SegmentID"], show=False)
    add(m, sw_edges, "Sidewalk edges",
        lambda f: dict(color="#2e7d32" if float(f["properties"]["overlap"].rstrip("%")) >= 50 else "#c62828", weight=2),
        ["segment_id", "side", "len", "overlap"])
    color = {"both": "#2e7d32", "one": "#ef6c00", "none": "#c62828"}
    add(m, x_edges, "Crossing edges",
        lambda f: dict(color=color.get(f["properties"]["ramp_status"], "#6a1b9a"), weight=3),
        ["street", "ramp_status", "len"])
    add(m, nodes, "Corner nodes",
        lambda f: dict(color="#1565c0", fillColor="#1565c0", fillOpacity=0.9, weight=1),
        ["node", "kind"], show=False, marker_radius=3)
    add(m, ramps, "Ramps",
        lambda f: dict(color="#6a1b9a", fillColor="#6a1b9a", fillOpacity=0.7, weight=1),
        ["ramp_onstr", "dws", "slope"], show=False, marker_radius=3)

    folium.LayerControl(collapsed=False).add_to(m)
    out = PROC / "graph_map.html"
    m.save(out)
    print(f"Saved {out} ({out.stat().st_size / 1e6:.1f} MB)")
    if args.open:
        subprocess.run(["open", str(out)], check=False)


if __name__ == "__main__":
    main()
