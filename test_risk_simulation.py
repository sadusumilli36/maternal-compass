"""
Test how risk level changes when beds are added to a county.

Usage:
  python test_risk_simulation.py
    -> runs built-in examples (High -> Moderate -> Low)

  python test_risk_simulation.py Walker
    -> uses real data for Walker county, tries adding 0, 10, 30, 70 beds

  python test_risk_simulation.py Fulton 0 10 50
    -> uses Fulton, simulates adding 0, 10, and 50 beds
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from risk_calculations import (
    risk_factor,
    get_risk_level,
    simulate_beds,
    LOW_RISK_THRESHOLD,
    MODERATE_RISK_THRESHOLD,
    HIGH_RISK_THRESHOLD,
)


def run_example(prenatal_pct: float, births_pct: float, current_beds: int, beds_to_try: list):
    """Simulate adding different numbers of beds and print risk level each time."""
    rf = risk_factor(prenatal_pct, births_pct, current_beds)
    level = get_risk_level(rf)
    print(f"  Current: {current_beds} beds -> risk_factor={rf:.3f} -> {level}")
    for n in beds_to_try:
        sim = simulate_beds(prenatal_pct, births_pct, current_beds, rf, n)
        print(f"  +{n} beds -> {sim.simulated_beds} total -> risk_factor={sim.simulated_risk_factor:.3f} -> {sim.simulated_risk_level}  (achieves_low_risk={sim.achieves_low_risk})")
    print()


def main():
    if len(sys.argv) >= 2 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0

    if len(sys.argv) == 1:
        print("Thresholds: Low <= {:.2f}, Moderate <= {:.2f}, High <= {:.2f}, else Very High\n".format(
            LOW_RISK_THRESHOLD, MODERATE_RISK_THRESHOLD, HIGH_RISK_THRESHOLD))
        print("Example 1: High-risk county (1 bed), add 0 / 10 / 30 / 70 beds")
        run_example(91.0, 0.6, 1, [0, 10, 30, 70])
        print("Example 2: Moderate-risk, add beds until Low")
        run_example(12.0, 1.0, 10, [0, 5, 6, 10])
        print("Example 3: Already low risk (many beds)")
        run_example(15.0, 8.8, 365, [0, 10])
        return 0

    county_name = sys.argv[1].strip()
    beds_to_try = [int(x) for x in sys.argv[2:]] if len(sys.argv) > 2 else [0, 10, 30, 70]

    csv_path = Path(__file__).resolve().parent / "output" / "risk_factor_by_county.csv"
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}. Run calculate_risk_factor.py first.")
        return 1

    import pandas as pd
    df = pd.read_csv(csv_path)
    df["county"] = df["county"].astype(str).str.strip()
    match = df[df["county"].str.equals(county_name, case=False)]
    if match.empty:
        print(f"County not found: {county_name}")
        return 1

    row = match.iloc[0]
    prenatal = float(row["pct_late_no_prenatal_care"])
    births = float(row["pct_births_in_state"])
    ob_beds = int(row["ob_beds"]) if pd.notna(row["ob_beds"]) else 0
    risk = float(row["risk_factor"])
    level = row.get("level", "")
    print(f"County: {county_name}")
    print(f"  prenatal_pct={prenatal}, births_pct={births}, ob_beds={ob_beds}, risk_factor={risk:.3f}, level={level}")
    print(f"  Simulate adding: {beds_to_try}")
    run_example(prenatal, births, ob_beds, beds_to_try)
    return 0


if __name__ == "__main__":
    sys.exit(main())
