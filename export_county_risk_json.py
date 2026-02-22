"""
Export county risk summary to JSON: county name, risk level, average distance to hospital.

Reads output/risk_factor_by_county.csv (or risk_factor_by_county_with_level.csv for levels),
assigns risk level by quantiles if needed (Very High, High, Moderate, Low), and writes
output/county_risk_distance.json.

Usage:
  python export_county_risk_json.py
  python export_county_risk_json.py --input output/risk_factor_by_county_with_level.csv
"""
from pathlib import Path
import argparse
import json

import pandas as pd

from config import OUTPUT_DIR


def assign_levels(df: pd.DataFrame) -> pd.Series:
    """Assign quantile-based risk levels: Very High, High, Moderate, Low."""
    labels = ["Low", "Moderate", "High", "Very High"]
    if df["risk_factor"].isna().all():
        return pd.Series([None] * len(df), index=df.index)
    try:
        return pd.qcut(df["risk_factor"], q=4, labels=labels, duplicates="drop")
    except Exception:
        return pd.cut(df["risk_factor"], bins=4, labels=labels, include_lowest=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export county, risk level, avg distance to JSON")
    parser.add_argument(
        "--input", "-i",
        default=str(OUTPUT_DIR / "risk_factor_by_county.csv"),
        help="Input CSV path",
    )
    parser.add_argument(
        "--output", "-o",
        default=str(OUTPUT_DIR / "county_risk_distance.json"),
        help="Output JSON path",
    )
    args = parser.parse_args()

    path = Path(args.input)
    if not path.exists():
        print(f"Input not found: {path}")
        return 2

    df = pd.read_csv(path)
    if "county" not in df.columns or "risk_factor" not in df.columns:
        print("Input CSV must have 'county' and 'risk_factor' columns.")
        return 3

    # Ensure avg_distance_miles: merge from pipeline CSV if missing or empty
    pipeline_csv = OUTPUT_DIR / "risk_factor_by_county.csv"
    if pipeline_csv.exists() and pipeline_csv != path:
        df_dist = pd.read_csv(pipeline_csv)
        if "county" in df_dist.columns and "avg_distance_miles" in df_dist.columns:
            dist_lookup = df_dist.set_index(df_dist["county"].astype(str).str.strip())["avg_distance_miles"]
            if "avg_distance_miles" not in df.columns or df["avg_distance_miles"].isna().all():
                df["avg_distance_miles"] = df["county"].astype(str).str.strip().map(dist_lookup)

    # If still no distances, compute centroid-to-nearest facility per county
    if "avg_distance_miles" not in df.columns or df["avg_distance_miles"].isna().all():
        try:
            from nearest_facility import compute_county_nearest
            county_list = df["county"].dropna().astype(str).str.strip().unique().tolist()
            state = "GA"
            county_info = compute_county_nearest(county_list, state=state)
            df["avg_distance_miles"] = df["county"].astype(str).str.strip().map(
                lambda c: county_info.get(c, {}).get("distance_miles")
            )
        except Exception:
            pass

    # Use existing level column if present and looks like our labels; otherwise assign
    if "level" in df.columns and df["level"].notna().any():
        level_vals = df["level"].dropna().unique()
        if any(v in ["Very High", "High", "Moderate", "Low"] for v in level_vals):
            level = df["level"]
        else:
            level = assign_levels(df)
    else:
        level = assign_levels(df)

    df = df.copy()
    df["level"] = level

    # Average distance: use avg_distance_miles if present
    dist_col = "avg_distance_miles" if "avg_distance_miles" in df.columns else None
    rows = []
    for _, r in df.iterrows():
        county = str(r["county"]).strip()
        lvl = r["level"]
        if pd.isna(lvl):
            lvl = None
        else:
            lvl = str(lvl).strip()
        dist = None
        if dist_col and pd.notna(r.get(dist_col)):
            try:
                dist = round(float(r[dist_col]), 2)
            except (TypeError, ValueError):
                pass
        rows.append({
            "county": county,
            "risk_level": lvl,
            "avg_distance_miles": dist,
        })

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)

    print(f"Wrote {len(rows)} counties to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
