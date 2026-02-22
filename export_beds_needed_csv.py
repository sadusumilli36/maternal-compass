"""
Export a CSV of beds needed to reach low risk per county.

Reads output/risk_factor_by_county.csv, computes beds needed using the same
formula as the predictive model (risk_calculations.beds_needed_for_low_risk),
writes output/beds_needed_for_low_risk_by_county.csv.

- beds_required_for_low_risk: total OB beds required for the county to be low risk.
- additional_beds_needed: (beds_required - current_ob_beds) when positive; 0 when negative
  (negative means the county already has enough beds to be low risk).

For this CSV only: current_ob_beds of 1 is written as 0 (pipeline turned 0→1 to avoid
division by zero; we restore 0 for display here).

Columns: county, state, current_ob_beds, beds_required_for_low_risk, additional_beds_needed,
         already_low_risk, pct_counties_not_low_risk (value only in row 1)

Run: python export_beds_needed_csv.py
"""
import pandas as pd
from pathlib import Path

from config import OUTPUT_DIR
from risk_calculations import beds_needed_for_low_risk

INPUT_CSV = OUTPUT_DIR / "risk_factor_by_county.csv"
OUTPUT_CSV = OUTPUT_DIR / "beds_needed_for_low_risk_by_county.csv"


def main():
    if not INPUT_CSV.exists():
        print(f"Not found: {INPUT_CSV}. Run calculate_risk_factor.py first.")
        return 1

    df = pd.read_csv(INPUT_CSV)
    df["county"] = df["county"].astype(str).str.strip()
    required = []
    additional_list = []
    already_low = []

    for _, row in df.iterrows():
        prenatal = float(row["pct_late_no_prenatal_care"])
        births = float(row["pct_births_in_state"])
        ob_beds_csv = int(row["ob_beds"]) if pd.notna(row["ob_beds"]) else 0
        # Pipeline uses 1 in place of 0 for risk formula; actual count for display/shortfall
        actual_ob_beds = 0 if ob_beds_csv == 1 else ob_beds_csv
        res = beds_needed_for_low_risk(prenatal, births, ob_beds_csv)
        required.append(res.beds_required)
        # Difference (beds_required - current_ob_beds); only when positive (else 0 = already enough)
        diff = res.beds_required - actual_ob_beds
        additional_list.append(max(0, diff))
        already_low.append(res.already_low_risk)

    out = df[["county", "state", "ob_beds"]].copy()
    out = out.rename(columns={"ob_beds": "current_ob_beds"})
    out["current_ob_beds"] = out["current_ob_beds"].fillna(0).astype(int)
    # In this CSV only: current_ob_beds of 1 is shown as 0 (pipeline turned 0→1 to avoid div by zero)
    out["current_ob_beds"] = out["current_ob_beds"].replace(1, 0)
    out["beds_required_for_low_risk"] = pd.Series(required).astype(int)
    out["additional_beds_needed"] = pd.Series(additional_list).astype(int)
    out["already_low_risk"] = already_low

    # Percent of counties not at low risk (only in row 1)
    n_not_low = sum(1 for x in already_low if not x)
    pct_not_low = round(100.0 * n_not_low / len(out), 1)
    out["pct_counties_not_low_risk"] = ""
    out.loc[out.index[0], "pct_counties_not_low_risk"] = str(pct_not_low)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT_CSV, index=False)
    print(f"Wrote {OUTPUT_CSV} ({len(out)} counties). {pct_not_low}% of counties are not at low risk.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
