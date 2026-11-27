"""Load the EV spec CSV and the past-ad samples into SQLite.

specs: the source CSV is synthetic: the same model appears many times with
contradictory specs. We keep a single row per (brand, model) so a lookup
returns exactly one answer: the most recent year, and within that year the
row with the highest annual_sales_units.

ads: one row per ad from data/ad_performance.json (made by make_ad_samples.py).
Copy and metric fields differ by channel, so unused columns are NULL.
"""

import json
import sqlite3
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
CSV_PATH = HERE / "data" / "ev_market_2026.csv"
ADS_PATH = HERE / "data" / "ad_performance.json"
DB_PATH = HERE / "ev.db"

raw = pd.read_csv(CSV_PATH)
specs = (
    raw.sort_values(["year", "annual_sales_units"], ascending=False)
    .drop_duplicates(["brand", "model"])
    .sort_values(["brand", "model"])
    .reset_index(drop=True)
)
assert not specs.duplicated(["brand", "model"]).any()

ads = pd.json_normalize(json.loads(ADS_PATH.read_text())["ads"], sep="_")
ads.columns = [c.removeprefix("copy_").removeprefix("metrics_") for c in ads.columns]
# Ads say "Chevrolet" but specs say "GM/Chevrolet"; models are unique, so ads join specs on model.
missing = set(ads["model"]) - set(specs["model"])
assert not missing, f"ads reference models not in specs: {missing}"

with sqlite3.connect(DB_PATH) as con:
    specs.to_sql("specs", con, if_exists="replace", index=False)
    ads.to_sql("ads", con, if_exists="replace", index=False)
    n = con.execute("SELECT COUNT(*) FROM specs").fetchone()[0]
    n_ads = con.execute("SELECT COUNT(*) FROM ads").fetchone()[0]

print(f"{len(raw)} rows in CSV -> {n} models in {DB_PATH.name}")
print(f"{n_ads} ads -> ads table in {DB_PATH.name}")
