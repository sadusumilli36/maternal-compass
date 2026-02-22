"""
Predictive model calculations for county risk factor.

Uses the same risk factor equation and thresholds as the pipeline and add_level_to_csv.
All functions are pure and easy to unit test.

Risk Factor = (pct_late_no_prenatal_care * pct_births_in_state) / max(ob_beds, 1)
Percentages are raw numbers (e.g. 13.4, not 0.134).
"""

import math
from typing import Literal, NamedTuple

# ---------------------------------------------------------------------------
# Risk level thresholds (must match add_level_to_csv quantile-based output).
# These values are the approximate 25th, 50th, 75th percentiles from current data.
# Do not change without updating add_level_to_csv / pipeline.
# ---------------------------------------------------------------------------
LOW_RISK_THRESHOLD = 0.77      # Risk factor <= this = Low
MODERATE_RISK_THRESHOLD = 1.25  # Low < risk <= this = Moderate
HIGH_RISK_THRESHOLD = 2.86     # Moderate < risk <= this = High; above = Very High

RiskLevel = Literal["Low", "Moderate", "High", "Very High"]


class BedsNeededResult(NamedTuple):
    """Result of beds needed to reach low risk."""
    current_ob_beds: int
    beds_required: int          # total beds needed (ceil of numerator / threshold)
    additional_beds_needed: int
    already_low_risk: bool


class SimulateResult(NamedTuple):
    """Result of simulating adding beds."""
    simulated_beds: int
    simulated_risk_factor: float
    simulated_risk_level: RiskLevel
    risk_factor_reduction: float
    percent_improvement: float
    achieves_low_risk: bool
    more_beds_needed_for_low: int  # 0 if already achieves low


def risk_factor(prenatal_pct: float, births_pct: float, ob_beds: int) -> float:
    """
    Current risk factor equation (same as pipeline).
    If ob_beds is 0, treat as 1 to avoid division by zero.
    """
    beds = max(int(ob_beds), 1)
    return (float(prenatal_pct) * float(births_pct)) / beds


def get_risk_level(value: float) -> RiskLevel:
    """Classify a risk factor into Low, Moderate, High, or Very High using existing thresholds."""
    if value <= LOW_RISK_THRESHOLD:
        return "Low"
    if value <= MODERATE_RISK_THRESHOLD:
        return "Moderate"
    if value <= HIGH_RISK_THRESHOLD:
        return "High"
    return "Very High"


def beds_needed_for_low_risk(
    prenatal_pct: float,
    births_pct: float,
    current_ob_beds: int,
) -> BedsNeededResult:
    """
    Beds needed to bring county to low-risk threshold.
    All bed counts are rounded up to whole integers (you can't have half a bed).

    Beds Required = ceil((Prenatal% × Births%) / Low Risk Threshold)
    Additional Beds Needed = max(0, Beds Required - Current OB Beds)
    If already low risk, additional_beds_needed = 0.
    """
    current = max(int(current_ob_beds), 1)
    numerator = float(prenatal_pct) * float(births_pct)
    current_rf = numerator / current

    if current_rf <= LOW_RISK_THRESHOLD:
        return BedsNeededResult(
            current_ob_beds=max(int(current_ob_beds), 0),
            beds_required=current,
            additional_beds_needed=0,
            already_low_risk=True,
        )

    # Beds Needed = ceil(numerator / LOW_RISK_THRESHOLD)
    beds_required = int(math.ceil(numerator / LOW_RISK_THRESHOLD))
    additional = max(0, beds_required - current_ob_beds)
    if additional == 0 and current_rf > LOW_RISK_THRESHOLD:
        additional = 1  # edge case: rounding left us still above threshold

    return BedsNeededResult(
        current_ob_beds=current_ob_beds,
        beds_required=beds_required,
        additional_beds_needed=additional,
        already_low_risk=False,
    )


def simulate_beds(
    prenatal_pct: float,
    births_pct: float,
    current_ob_beds: int,
    current_risk_factor: float,
    beds_to_add: int,
) -> SimulateResult:
    """
    Simulate adding beds and return new risk factor, level, and whether low risk is achieved.
    """
    current_beds_safe = max(int(current_ob_beds), 1)
    simulated_beds = max(current_ob_beds + int(beds_to_add), 1)
    numerator = float(prenatal_pct) * float(births_pct)
    simulated_rf = numerator / simulated_beds
    simulated_level = get_risk_level(simulated_rf)

    reduction = current_risk_factor - simulated_rf
    if reduction < 0:
        reduction = 0.0
    percent = (reduction / current_risk_factor * 100.0) if current_risk_factor > 0 else 0.0

    achieves = simulated_rf <= LOW_RISK_THRESHOLD
    more_needed = 0
    if not achieves:
        beds_required = int(math.ceil(numerator / LOW_RISK_THRESHOLD))
        more_needed = max(0, beds_required - simulated_beds)

    return SimulateResult(
        simulated_beds=simulated_beds,
        simulated_risk_factor=round(simulated_rf, 3),
        simulated_risk_level=simulated_level,
        risk_factor_reduction=round(reduction, 3),
        percent_improvement=round(percent, 1),
        achieves_low_risk=achieves,
        more_beds_needed_for_low=more_needed,
    )
