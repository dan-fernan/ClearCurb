"""Download NYC Sidewalk Management Database - Built (repair history, ugc8-s3f6) for Lower Manhattan (CB 1-3).

One row per tax lot (bblid): when DOT or the owner last repaired it, and how much
sidewalk/curb was repaired. Use it to discount old violations on lots repaired since.

The table has no location or community board, so the area is found the same way as in
download_sidewalk_data.py: Manhattan lots (Lot Info, i642-2fxq) that have a violation
(6kbp-uz6m) in community boards 1-3. Repaired Manhattan lots with no violation on file
(~2% of them) can't be placed in a board, so they are left out; they have no violation
for a repair date to apply to anyway.
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


def fetch(dataset_id, select=None, where=None):
    rows, offset = [], 0
    while True:
        params = {"$limit": PAGE, "$offset": offset, "$order": ":id"}
        if select:
            params["$select"] = select
        if where:
            params["$where"] = where
        r = requests.get(f"{BASE}/{dataset_id}.json", params=params, headers=HEADERS, timeout=180)
        r.raise_for_status()
        batch = r.json()
        rows += batch
        if len(batch) < PAGE:
            return pd.DataFrame(rows)
        offset += PAGE


lots = fetch("i642-2fxq", "bblid", "boro = '1'")            # Manhattan lots
viol = fetch("6kbp-uz6m", "bblid", "cb in (1,2,3)")         # Lower Manhattan community boards
lower_manhattan = set(viol["bblid"]) & set(lots["bblid"])   # cb numbers repeat across boroughs
built = fetch("ugc8-s3f6")                                  # no location/filter available
built = built[built["bblid"].isin(lower_manhattan)]

built.to_csv(OUT / "built_lowermanhattan.csv", index=False)
print(f"built_lowermanhattan: {len(built)} rows")
