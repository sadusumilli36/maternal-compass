"""
Regenerate risk_factor_by_county.csv with avg_distance_miles from existing caches only (no network).
Run: python regenerate_risk_csv_from_caches.py
"""
import json
import math
from pathlib import Path

import pandas as pd

# Run from project root
PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output"
CSV_PATH = OUTPUT_DIR / "risk_factor_by_county.csv"
COUNTY_CACHE = OUTPUT_DIR / "county_latlon_cache.json"
FACILITY_CACHE = OUTPUT_DIR / "facility_latlon_cache.json"


def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3959  # Earth radius miles
    a = math.radians(lat2 - lat1)
    b = math.radians(lon2 - lon1)
    x = math.sin(a / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(b / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def main():
    if not CSV_PATH.exists():
        print(f"Not found: {CSV_PATH}")
        return 1
    if not COUNTY_CACHE.exists() or not FACILITY_CACHE.exists():
        print("Missing county or facility cache. Run calculate_risk_factor.py or backfill_avg_distance.py first.")
        return 2

    with open(COUNTY_CACHE, encoding="utf-8") as f:
        county_cache = json.load(f)
    with open(FACILITY_CACHE, encoding="utf-8") as f:
        facilities = json.load(f)

    df = pd.read_csv(CSV_PATH)
    df["county"] = df["county"].astype(str).str.strip()
    state = "GA"
    if "state" in df.columns and df["state"].notna().any():
        state = str(df["state"].iloc[0]).strip()

    distances = []
    for _, row in df.iterrows():
        c = str(row["county"]).strip()
        key = f"{c}|{state}"
        cent = county_cache.get(key)
        if not cent or len(cent) < 2:
            distances.append(None)
            continue
        cy, cx = float(cent[0]), float(cent[1])
        best = None
        for fac in facilities:
            lat, lon = fac.get("lat"), fac.get("lon")
            if lat is None or lon is None or (lat == 0 and lon == 0):
                continue
            d = haversine_miles(cy, cx, lat, lon)
            if best is None or d < best:
                best = round(d, 2)
        distances.append(best)

    df["avg_distance_miles"] = distances
    if "avg_drive_time_min" in df.columns:
        df = df.drop(columns=["avg_drive_time_min"])
    out_path = CSV_PATH
    try:
        df.to_csv(out_path, index=False)
    except PermissionError:
        out_path = CSV_PATH.parent / "risk_factor_by_county_regenerated.csv"
        df.to_csv(out_path, index=False)
        print(f"Original file locked. Wrote {out_path} — copy over risk_factor_by_county.csv when closed.")
    filled = sum(1 for x in distances if x is not None)
    print(f"Regenerated: avg_distance_miles filled for {filled}/{len(df)} counties.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
