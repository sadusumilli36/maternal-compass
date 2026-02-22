"""
One-time fix: Remove avg_drive_time_min from output/risk_factor_by_county.csv
and ensure avg_distance_miles column exists. Run after calculate_risk_factor.py
to backfill distance if needed: python calculate_risk_factor.py
"""
import pandas as pd
from pathlib import Path

from config import OUTPUT_DIR

CSV_PATH = OUTPUT_DIR / "risk_factor_by_county.csv"

def main():
    if not CSV_PATH.exists():
        print(f"Not found: {CSV_PATH}")
        return 1
    df = pd.read_csv(CSV_PATH)
    # Remove average drive time column; keep average distance
    if "avg_drive_time_min" in df.columns:
        df = df.drop(columns=["avg_drive_time_min"])
        print("Dropped column: avg_drive_time_min")
    if "avg_distance_miles" not in df.columns:
        df["avg_distance_miles"] = None
        print("Added column: avg_distance_miles")
    try:
        df.to_csv(CSV_PATH, index=False)
        print(f"Updated {CSV_PATH}. Columns: {list(df.columns)}")
    except PermissionError:
        out = CSV_PATH.parent / "risk_factor_by_county_fixed.csv"
        df.to_csv(out, index=False)
        print(f"Original file is locked. Wrote {out}. Close risk_factor_by_county.csv and copy over, or rename.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
