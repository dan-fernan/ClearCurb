"""Shared definition of the "lower Manhattan" study area, used by the fetch scripts.

Lower Manhattan = the 2020 Neighborhood Tabulation Areas (NTAs) in Manhattan
Community Districts 1-3 (everything below roughly 14th St).
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

SODA_BASE = "https://data.cityofnewyork.us/resource"
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

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


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
        sys.exit(f"Unknown NTA code(s): {', '.join(sorted(missing))} (see fetch_curbs.py --list-ntas)")
    return rows


def study_area(hoods: list[dict]) -> BaseGeometry:
    """Union of the neighborhood polygons (EPSG:4326)."""
    return unary_union([shape(h["the_geom"]) for h in hoods])
