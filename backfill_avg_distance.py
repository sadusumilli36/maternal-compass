"""
Backfill avg_distance_miles in output/risk_factor_by_county.csv using centroid-to-nearest facility.
Run: python backfill_avg_distance.py
Takes ~2–3 min the first time (geocodes county centroids); later runs use cache and finish in seconds.
"""
import pandas as pd
from pathlib import Path

from config import OUTPUT_DIR

CSV_PATH = OUTPUT_DIR / "risk_factor_by_county.csv"


def main():
    if not CSV_PATH.exists():
        print(f"Not found: {CSV_PATH}. Run calculate_risk_factor.py first.")
        return 1
    df = pd.read_csv(CSV_PATH)
    df["county"] = df["county"].astype(str).str.strip()
    county_list = df["county"].dropna().unique().tolist()
    state = "GA"
    if "state" in df.columns and df["state"].notna().any():
        state = str(df["state"].iloc[0]).strip()

    from nearest_facility import compute_county_nearest
    county_info = compute_county_nearest(county_list, state=state)
    if not county_info:
        print("Could not compute distances (facility or county cache issue).")
        return 2

    df["avg_distance_miles"] = df["county"].map(
        lambda c: county_info.get(str(c).strip(), {}).get("distance_miles") if c is not None else None
    )
    # Drop drive time column if present
    if "avg_drive_time_min" in df.columns:
        df = df.drop(columns=["avg_drive_time_min"])
    df.to_csv(CSV_PATH, index=False)
    filled = df["avg_distance_miles"].notna().sum()
    print(f"Updated {CSV_PATH}: avg_distance_miles filled for {filled}/{len(df)} counties.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
