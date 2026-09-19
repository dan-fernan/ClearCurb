"""Download NYC Sidewalk Management Database tables for Lower Manhattan (CB 1-3).

These tables have no coordinates. They join like this:
  Violations (6kbp-uz6m)  --bblid-->  Lot Info (i642-2fxq)  -> boro/block/lot (BBL)
  BBL -> tax lot geometry (MapPLUTO) is a later step.
"""
import os
from pathlib import Path

import pandas as pd
import requests

BASE = "https://data.cityofnewyork.us/resource"
OUT = Path(__file__).resolve().parents[1] / "data" / "raw"
OUT.mkdir(parents=True, exist_ok=True)
PAGE = 50_000
HEADERS = {"X-App-Token": t} if (t := os.getenv("SOCRATA_APP_TOKEN")) else {}


def fetch(dataset_id, where=None):
    rows, offset = [], 0
    while True:
        params = {"$limit": PAGE, "$offset": offset, "$order": ":id"}
        if where:
            params["$where"] = where
        r = requests.get(f"{BASE}/{dataset_id}.json", params=params, headers=HEADERS, timeout=180)
        r.raise_for_status()
        batch = r.json()
        rows += batch
        if len(batch) < PAGE:
            return pd.DataFrame(rows)
        offset += PAGE


lots = fetch("i642-2fxq", "boro = '1'")            # Manhattan lots
viol = fetch("6kbp-uz6m", "cb in (1,2,3)")         # Lower Manhattan community boards
viol = viol[viol["bblid"].isin(lots["bblid"])]      # cb numbers repeat across boroughs
insp = fetch("dntt-gqwq")                           # no location/filter available

for name, df in [("lots_manhattan", lots), ("violations_lowermanhattan", viol), ("inspections", insp)]:
    df.to_csv(OUT / f"{name}.csv", index=False)
    print(f"{name}: {len(df)} rows")
