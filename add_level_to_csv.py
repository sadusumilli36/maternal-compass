"""Add a `level` column to the risk factor CSV.

Default behavior:
- Reads `output/risk_factor_by_county.csv`
- Creates `level` by quantiles (4 bins: Low, Moderate, High, Very High)
- Writes `output/risk_factor_by_county_with_level.csv` (or overwrites with --inplace)

Usage:
  python add_level_to_csv.py
  python add_level_to_csv.py --input output/risk_factor_by_county.csv --q 3 --labels Low,Mid,High
  python add_level_to_csv.py --inplace
"""
from pathlib import Path
import argparse
import sys
from typing import Optional, List

import pandas as pd


def make_labels(q: int, labels_arg: Optional[str]):
    if labels_arg:
        labels = [l.strip() for l in labels_arg.split(",")]
        if len(labels) != q:
            raise ValueError("Number of labels must match q")
        return labels
    if q == 4:
        return ["Low", "Moderate", "High", "Very High"]
    return [f"Level {i+1}" for i in range(q)]


def assign_levels(df: pd.DataFrame, q: int, labels: List[str]) -> pd.Series:
    """Try to assign quantile-based levels; fall back to equal-width bins."""
    if df["risk_factor"].isna().all():
        return pd.Series([pd.NA] * len(df), index=df.index)

    # Try qcut (quantiles)
    try:
        levels = pd.qcut(df["risk_factor"], q=q, labels=labels, duplicates="drop")
        # If qcut produced fewer bins due to ties, fallback to cut
        if levels.isna().all() or levels.nunique(dropna=True) < min(q, 2):
            raise ValueError("qcut produced insufficient bins")
        return levels
    except Exception:
        # Fallback: equal-width bins
        try:
            levels = pd.cut(df["risk_factor"], bins=q, labels=labels, include_lowest=True)
            return levels
        except Exception:
            return pd.Series([pd.NA] * len(df), index=df.index)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Add level categories to risk factor CSV")
    parser.add_argument(
        "--input",
        "-i",
        default="output/risk_factor_by_county.csv",
        help="Path to input CSV (default: output/risk_factor_by_county.csv)",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Path to output CSV. Default: input_with_level.csv unless --inplace is set",
    )
    parser.add_argument("--q", type=int, default=4, help="Number of bins/quantiles (default: 4)")
    parser.add_argument(
        "--labels",
        help="Comma-separated labels (must match q). If omitted, defaults used for q=4.",
    )
    parser.add_argument(
        "--inplace",
        action="store_true",
        help="Overwrite the input file instead of writing a separate output file",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing `level` column if present",
    )

    args = parser.parse_args(argv)

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"Input file not found: {in_path}")
        return 2

    df = pd.read_csv(in_path)


    if "risk_factor" not in df.columns:
        print("Input CSV has no 'risk_factor' column. Cannot compute levels.")
        return 3

    # Prepare level column: create if missing. If present and not --force, we'll only fill NaNs.
    overwrite_all = bool(args.force)
    if "level" not in df.columns:
        df["level"] = pd.NA

    # Attempt to derive facility levels (1-4) by matching hospital names.
    facilities_path = Path("GA_Maternal_Care_Facilities.xlsx")
    ob_hospitals_path = Path("GA_OB_Hospitals_by_County.xlsx")

    def _norm(s: str) -> str:
        if not isinstance(s, str):
            return ""
        return (
            s.lower()
            .strip()
            .replace("&", " and ")
            .replace("-", " ")
            .replace("/", " ")
            .replace(",", " ")
        )

    filled = False
    if facilities_path.exists() and ob_hospitals_path.exists():
        try:
            df_fac = pd.read_excel(facilities_path)
            df_obs = pd.read_excel(ob_hospitals_path, sheet_name="OB Hospitals by County")

            # Keep only rows where Level is present in facilities file
            if "Level" in df_fac.columns:
                df_fac_clean = df_fac[df_fac["Level"].notna()].copy()
                df_fac_clean["_fnorm"] = df_fac_clean["Facility Name"].astype(str).map(_norm)
                df_obs["_hnorm"] = df_obs["Hospital Name"].astype(str).map(_norm)

                matches = []
                for _, h in df_obs.iterrows():
                    hnorm = h.get("_hnorm", "")
                    hcounty = h.get("County", "")
                    lvl = None
                    # exact normalized match
                    exact = df_fac_clean[df_fac_clean["_fnorm"] == hnorm]
                    if not exact.empty:
                        lvl = exact["Level"].dropna().astype(float).astype(int).max()
                    else:
                        # facility name contains hospital normalized
                        contains = df_fac_clean[df_fac_clean["_fnorm"].str.contains(hnorm, na=False)]
                        if not contains.empty:
                            lvl = contains["Level"].dropna().astype(float).astype(int).max()
                        else:
                            # hospital normalized contained in facility names
                            contained = df_fac_clean[df_fac_clean["_fnorm"].str.contains(hnorm.split()[0] if hnorm else "", na=False)]
                            if not contained.empty:
                                lvl = contained["Level"].dropna().astype(float).astype(int).max()

                    matches.append({"Hospital Name": h.get("Hospital Name"), "county": hcounty, "level": lvl})

                df_hosp_levels = pd.DataFrame(matches)
                # aggregate highest level per county
                county_level = (
                    df_hosp_levels.dropna(subset=["level"]).groupby(df_hosp_levels["county"].astype(str).str.strip())["level"].max().reset_index()
                )
                county_level.columns = ["county", "level_from_fac"]

                df = df.merge(county_level, on="county", how="left")
                # keep facility-derived numeric level separate from county risk category
                df["hospital_level"] = df.get("level_from_fac")
                if "level_from_fac" in df.columns:
                    df = df.drop(columns=["level_from_fac"])
                filled = True
        except Exception:
            filled = False

    # If facility mapping didn't fill levels for all or files missing, fallback to quantile labeling for remaining rows
    # Compute county risk categories from risk_factor (Low/Moderate/High/Very High)
    labels = make_labels(args.q, args.labels)
    q_levels = assign_levels(df, args.q, labels)
    # always use quantile-based labels for county-level `level`
    df["level"] = q_levels

    out_path = in_path if args.inplace else Path(args.output or in_path.with_name(in_path.stem + "_with_level.csv"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Do not include hospital-level numeric values; drop drive-time column if present (we keep avg_distance_miles only)
    drop_cols = [c for c in ["hospital_level", "avg_drive_time_min", "fips"] if c in df.columns]
    county_only = df.drop(columns=drop_cols)
    county_only.to_csv(out_path, index=False)

    # If we built a hospital-level mapping earlier, write it separately (hospital -> level)
    try:
        if "df_hosp_levels" in locals():
            hosp_out = Path("output") / "ob_hospitals_with_level.csv"
            hosp_out.parent.mkdir(parents=True, exist_ok=True)
            df_hosp_levels.to_csv(hosp_out, index=False)
            print(f"Wrote hospital-level mapping: {hosp_out}")
    except Exception as e:
        print("Failed to write hospital-level mapping:", e)

    # Print a compact summary for the county-only CSV
    counts = county_only["level"].value_counts(dropna=False)
    print(f"Wrote: {out_path} — counts by level:")
    for lvl, c in counts.items():
        print(f"  {lvl}: {c}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
