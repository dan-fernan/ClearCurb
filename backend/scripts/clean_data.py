"""Clean the raw ClearCurb layers and write analysis-ready copies.

Reads  backend/data/raw/, writes backend/data/processed/ (geometry in EPSG:2263, US survey feet).
Raw files are never modified, so this is safe to rerun.

Study area: the Manhattan CD1-3 neighborhoods (NTAs) from fetch_curbs.py, buffered a little so
edge crossings survive. Features that intersect the area are kept whole (never cut into slivers).

Layers:
    lion_streets       walkable Manhattan street segments, slimmed to the columns routing needs
    sidewalks          valid, non-sliver sidewalk polygons
    elevation_points   ground points only (rooftop/building heights removed), outliers dropped
    ramps              numeric fields cleaned (999 = not measured -> null), one row per ramp
    crossings          crossings from build_crossings.py, deduplicated
    curbs              curb line segments from fetch_curbs.py (already clipped to the neighborhoods)
    violations.csv     dates parsed, defect flags as booleans, open/closed flag (not yet located)

Not handled: inspections (no location or lot id in the table) and locating violations
(needs MapPLUTO lot geometry).

Usage:
    python backend/scripts/clean_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import make_valid
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_curbs import DEFAULT_NTAS, fetch_neighborhoods, session, write_json_atomic  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
RAW = BACKEND / "data" / "raw"
OUT = BACKEND / "data" / "processed"
FT = "EPSG:2263"

AREA_BUFFER_FT = 150
MIN_SIDEWALK_AREA_SQFT = 25         # smaller polygons are drafting noise
ELEV_GROUND_CODES = {"3000", "3010"}  # 3020 medians ~84 ft with a 1,413 ft max: rooftop heights
ELEV_RANGE_FT = (-5.0, 50.0)        # street-level range here; higher points are the Brooklyn Bridge deck
NOT_MEASURED = 100                  # ramp survey uses 999 for "not measured"

LION_KEEP = [
    "SegmentID", "Street", "SegmentTyp", "RW_TYPE", "NodeIDFrom", "NodeIDTo", "TrafDir",
    "StreetWidth_Min", "StreetWidth_Max", "BikeLane", "POSTED_SPEED", "SHAPE_Length",
    "is_step_street",
]

report: list[tuple[str, int, int]] = []


def study_area() -> gpd.GeoSeries:
    path = RAW / "neighborhoods.geojson"
    if not path.exists():
        print("neighborhoods.geojson missing; fetching NTA polygons...")
        hoods = fetch_neighborhoods(session(), DEFAULT_NTAS)
        write_json_atomic(path, {"type": "FeatureCollection", "features": [
            {"type": "Feature", "geometry": h["the_geom"],
             "properties": {k: h[k] for k in ("nta2020", "ntaname", "cdtaname")}} for h in hoods]})
    hoods = gpd.read_file(path).set_crs("EPSG:4326", allow_override=True).to_crs(FT)
    return gpd.GeoSeries([unary_union(hoods.geometry).buffer(AREA_BUFFER_FT)], crs=FT)


def load(name: str) -> gpd.GeoDataFrame:
    return gpd.read_parquet(RAW / f"{name}.parquet").to_crs(FT)


def tidy_geometry(gdf: gpd.GeoDataFrame, area: gpd.GeoSeries) -> gpd.GeoDataFrame:
    """Repair invalid geometries, drop empties, and keep features that touch the study area."""
    gdf = gdf.copy()
    bad = ~gdf.geometry.is_valid
    gdf.loc[bad, "geometry"] = gdf.loc[bad, "geometry"].map(make_valid)
    gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notna()]
    return gdf[gdf.intersects(area.iloc[0])].reset_index(drop=True)


def save(name: str, before: int, gdf: gpd.GeoDataFrame) -> None:
    gdf.to_parquet(OUT / f"{name}.parquet")
    report.append((name, before, len(gdf)))


def clean_lion(area) -> None:
    raw = load("lion_lowermanhattan")
    m = raw[(raw["LBoro"] == 1) | (raw["RBoro"] == 1)]
    m = m[
        (m["FeatureTyp"].astype(str).str.strip() == "0")
        & (m["RW_TYPE"].astype(str).str.strip().isin({"1", "7"}))  # streets, plus step streets kept flagged
        & (m["NonPed"].astype(str).str.strip() == "")
    ]
    m = tidy_geometry(m, area)[LION_KEEP + ["geometry"]]
    for c in m.select_dtypes(include=["object", "string"]):
        m[c] = m[c].str.strip()
    m["NodeIDFrom"], m["NodeIDTo"] = m["NodeIDFrom"].astype(int), m["NodeIDTo"].astype(int)
    save("lion_streets", len(raw), m.drop_duplicates("SegmentID"))


def clean_sidewalks(area) -> None:
    raw = load("sidewalks_lowermanhattan")
    g = tidy_geometry(raw, area)
    g = g[g.geometry.area >= MIN_SIDEWALK_AREA_SQFT].drop_duplicates("source_id")
    save("sidewalks", len(raw), g)


def clean_elevation(area) -> None:
    raw = load("elevation_points_lowermanhattan")
    g = tidy_geometry(raw, area)
    g = g[g["feat_code"].astype(str).isin(ELEV_GROUND_CODES)]
    lo, hi = ELEV_RANGE_FT
    g = g[g["elevation"].between(lo, hi)]
    print(f"elevation kept: {g['elevation'].describe().round(1)[['min', '50%', 'max']].to_dict()}")
    save("elevation_points", len(raw), g)


def clean_ramps(area) -> None:
    raw = load("ramps_lowermanhattan")
    g = tidy_geometry(raw, area)
    for c in ["lnd_width", "ramp_width", "lnd_cross_slope", "ramp_length", "ramp_running_slope_total",
              "counter_slope", "lnd_length", "curb_reveal", "gutter_slope", "ramp_cross_slope",
              "ramp_left_flare", "ramp_right_flare"]:
        g[c] = pd.to_numeric(g[c], errors="coerce").where(lambda x: x < NOT_MEASURED)
    g["dws_conditions"] = g["dws_conditions"].str.strip()
    g["dws_missing"] = g["dws_conditions"].eq("Missing")
    g["dws_defective"] = g["dws_conditions"].str.contains("Defective", na=False)
    save("ramps", len(raw), g.drop_duplicates("rampid"))


def clean_crossings(area) -> None:
    raw = load("crossings_lowermanhattan")
    g = tidy_geometry(raw, area)
    # Dual carriageways / duplicate legs can yield the same line twice.
    key = g.geometry.map(lambda ln: tuple(sorted((round(x, 0), round(y, 0)) for x, y in ln.coords)))
    save("crossings", len(raw), g[~key.duplicated()])


def clean_curbs(area) -> None:
    raw = gpd.read_file(RAW / "curbs_lower_manhattan.geojson").set_crs("EPSG:4326", allow_override=True).to_crs(FT)
    g = tidy_geometry(raw, area)
    g = g[g.geometry.length > 0].drop_duplicates("row_id")
    save("curbs", len(raw), g)


def clean_violations() -> None:
    raw = pd.read_csv(RAW / "violations_lowermanhattan.csv", low_memory=False)
    v = raw.copy()
    for c in ["vissuedate", "vdismissdate", "certi_date", "post_date", "entrydate"]:
        v[c] = pd.to_datetime(v[c], errors="coerce")
    flags = ["broken", "patchwork", "trip_haz", "slope", "other_def", "undermined", "flag",
             "hardware", "integrity", "sw_missing"]
    for c in flags:
        v[c] = v[c].notna()
    v["is_open"] = v["vdismissdate"].isna() & v["certi_date"].isna()
    v["sw_defect"] = v[flags].any(axis=1)
    for c in ["onstname", "frstname", "tostname"]:
        v[c] = v[c].str.replace(r"\s+", " ", regex=True).str.strip()
    v = v.drop_duplicates("violationid")
    v.to_csv(OUT / "violations.csv", index=False)
    report.append(("violations", len(raw), len(v)))
    print(f"violations: {int(v['is_open'].sum())} open of {len(v)}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    area = study_area()
    clean_lion(area)
    clean_sidewalks(area)
    clean_elevation(area)
    clean_ramps(area)
    clean_crossings(area)
    clean_curbs(area)
    clean_violations()

    print(f"\n{'layer':<18}{'raw':>9}{'clean':>9}")
    for name, before, after in report:
        print(f"{name:<18}{before:>9}{after:>9}")
    for name in ["lion_streets", "sidewalks", "elevation_points", "ramps", "crossings", "curbs"]:
        g = gpd.read_parquet(OUT / f"{name}.parquet")
        assert g.crs == FT and g.geometry.is_valid.all() and not g.geometry.is_empty.any(), name


if __name__ == "__main__":
    main()
