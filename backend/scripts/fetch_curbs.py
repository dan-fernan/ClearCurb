"""Download NYC curb data for lower Manhattan and store it locally.

Source: NYC Planimetric Database: Curbs
    https://data.cityofnewyork.us/City-Government/NYC-Planimetric-Database-Curbs/ikvd-dex8
That page is a map wrapper with no queryable rows; the Socrata API serves the
underlying table, dataset ``5xvt-8cbk``.

"Lower Manhattan" is defined as the 2020 Neighborhood Tabulation Areas (NTAs)
in Manhattan Community Districts 1-3 (everything below roughly 14th St). Curbs
are fetched by bounding box, then clipped to the neighborhood polygons locally
and tagged with the neighborhood they mostly fall in.

Output (default ``backend/data/raw/``):
    curbs_lower_manhattan.geojson   curb line segments, EPSG:4326
    neighborhoods.geojson           the NTA polygons used for clipping
    metadata.json                   fetch time, source, counts

Usage:
    python backend/scripts/fetch_curbs.py
    python backend/scripts/fetch_curbs.py --list-ntas
    python backend/scripts/fetch_curbs.py --nta MN0201 MN0202

Set SOCRATA_APP_TOKEN to raise the API rate limit (optional).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

SODA_BASE = "https://data.cityofnewyork.us/resource"
CURBS_DATASET = "5xvt-8cbk"
NTA_DATASET = "9nt8-h7nd"  # 2020 Neighborhood Tabulation Areas

# Manhattan CD1-3 NTAs (Financial District through East Village).
# MN0191 (The Battery-Governors Island-Ellis Island-Liberty Island) is left out
# because it is mostly islands; pass it with --nta to include it.
DEFAULT_NTAS = [
    "MN0101",  # Financial District-Battery Park City
    "MN0102",  # Tribeca-Civic Center
    "MN0201",  # SoHo-Little Italy-Hudson Square
    "MN0202",  # Greenwich Village
    "MN0203",  # West Village
    "MN0301",  # Chinatown-Two Bridges
    "MN0302",  # Lower East Side
    "MN0303",  # East Village
]

PAGE_SIZE = 5000
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
CURB_FIELDS = ["source_id", "feat_code", "sub_code", "status", "shape_leng"]


def session() -> requests.Session:
    s = requests.Session()
    token = os.environ.get("SOCRATA_APP_TOKEN")
    if token:
        s.headers["X-App-Token"] = token
    return s


def get_json(s: requests.Session, url: str, params: dict, retries: int = 4):
    for attempt in range(retries):
        try:
            r = s.get(url, params=params, timeout=90)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            wait = 2**attempt
            print(f"  request failed ({e}); retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)


def list_ntas(s: requests.Session) -> None:
    rows = get_json(
        s,
        f"{SODA_BASE}/{NTA_DATASET}.json",
        {
            "$select": "nta2020,ntaname",
            "$where": "boroname='Manhattan'",
            "$order": "nta2020",
            "$limit": 100,
        },
    )
    for r in rows:
        mark = "*" if r["nta2020"] in DEFAULT_NTAS else " "
        print(f"{mark} {r['nta2020']}  {r['ntaname']}")
    print("\n* = included by default")


def fetch_neighborhoods(s: requests.Session, codes: list[str]) -> list[dict]:
    quoted = ",".join(f"'{c}'" for c in codes)
    rows = get_json(
        s,
        f"{SODA_BASE}/{NTA_DATASET}.json",
        {
            "$select": "nta2020,ntaname,cdtaname,the_geom",
            "$where": f"nta2020 in({quoted})",
            "$limit": len(codes),
        },
    )
    found = {r["nta2020"] for r in rows}
    missing = set(codes) - found
    if missing:
        sys.exit(f"Unknown NTA code(s): {', '.join(sorted(missing))} (see --list-ntas)")
    return rows


def fetch_curbs_in_box(s: requests.Session, bounds: tuple[float, float, float, float]) -> list[dict]:
    minx, miny, maxx, maxy = bounds
    # within_box args: NW lat, NW lon, SE lat, SE lon
    where = f"within_box(the_geom, {maxy}, {minx}, {miny}, {maxx})"
    rows: list[dict] = []
    offset = 0
    while True:
        # Stable ordering is required for offset paging to be correct.
        page = get_json(
            s,
            f"{SODA_BASE}/{CURBS_DATASET}.json",
            {
                "$select": ",".join([":id", "the_geom", *CURB_FIELDS]),
                "$where": where,
                "$order": ":id",
                "$limit": PAGE_SIZE,
                "$offset": offset,
            },
        )
        rows.extend(page)
        print(f"  fetched {len(rows)} curb segments", end="\r")
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    print()
    return rows


def clip_to_neighborhoods(rows: list[dict], hoods: list[dict]) -> list[dict]:
    """Keep curbs that touch a neighborhood; tag each with its dominant one."""
    polys = [(h["nta2020"], h["ntaname"], shape(h["the_geom"])) for h in hoods]
    features = []
    for row in rows:
        geom_json = row.get("the_geom")
        if not geom_json:
            continue
        geom = shape(geom_json)
        best, best_len = None, 0.0
        for code, name, poly in polys:
            if geom.intersects(poly):
                # Degrees, not meters -- fine for ranking overlap between NTAs.
                length = geom.intersection(poly).length
                if best is None or length > best_len:
                    best, best_len = (code, name), length
        if best is None:
            continue
        # source_id is shared by split segments, so keep Socrata's row id as a unique key.
        props = {"row_id": row[":id"], **{k: row.get(k) for k in CURB_FIELDS}}
        for k in ("feat_code", "sub_code"):
            props[k] = int(props[k]) if props[k] is not None else None
        # Socrata serves these numeric fields as strings, e.g. "20225003296.0".
        props["source_id"] = int(float(props["source_id"])) if props["source_id"] else None
        props["shape_leng"] = float(props["shape_leng"]) if props["shape_leng"] else None
        props["nta2020"], props["ntaname"] = best
        features.append({"type": "Feature", "geometry": mapping(geom), "properties": props})
    return features


def write_json_atomic(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":")))
    tmp.replace(path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nta", nargs="+", metavar="CODE", default=DEFAULT_NTAS,
                    help="2020 NTA codes to include (default: Manhattan CD1-3)")
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--list-ntas", action="store_true", help="list Manhattan NTA codes and exit")
    args = ap.parse_args()

    s = session()
    if args.list_ntas:
        list_ntas(s)
        return

    print(f"Fetching {len(args.nta)} neighborhood boundaries...")
    hoods = fetch_neighborhoods(s, args.nta)
    for h in sorted(hoods, key=lambda h: h["nta2020"]):
        print(f"  {h['nta2020']}  {h['ntaname']}")

    bounds = unary_union([shape(h["the_geom"]) for h in hoods]).bounds
    print(f"Fetching curbs in bounding box {tuple(round(b, 4) for b in bounds)}...")
    rows = fetch_curbs_in_box(s, bounds)

    print("Clipping to neighborhood polygons...")
    features = clip_to_neighborhoods(rows, hoods)

    counts: dict[str, int] = {}
    for f in features:
        n = f["properties"]["ntaname"]
        counts[n] = counts.get(n, 0) + 1
    for name, n in sorted(counts.items()):
        print(f"  {n:>6}  {name}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        args.out_dir / "curbs_lower_manhattan.geojson",
        {"type": "FeatureCollection", "features": features},
    )
    write_json_atomic(
        args.out_dir / "neighborhoods.geojson",
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": h["the_geom"],
                    "properties": {k: h[k] for k in ("nta2020", "ntaname", "cdtaname")},
                }
                for h in hoods
            ],
        },
    )
    write_json_atomic(
        args.out_dir / "metadata.json",
        {
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "curbs_source": f"https://data.cityofnewyork.us/resource/{CURBS_DATASET}.json",
            "neighborhoods_source": f"https://data.cityofnewyork.us/resource/{NTA_DATASET}.json",
            "crs": "EPSG:4326",
            "ntas": sorted(args.nta),
            "bbox_rows_fetched": len(rows),
            "curb_features_saved": len(features),
            "per_neighborhood": counts,
        },
    )
    print(f"Saved {len(features)} curb segments to {args.out_dir}")


if __name__ == "__main__":
    main()
