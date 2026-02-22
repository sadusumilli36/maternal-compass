"""
Pin-drop risk level: given (lat, lon) and optional beds to add,
resolve county → temporarily add beds → recalculate risk factor → return new risk level.

No data is changed on disk. Uses reverse geocoding (Nominatim) to find county from coordinates.
Run: python pin_drop_risk.py
  Or use: pin_drop_to_risk_level(lat, lon, beds_added=0) from this module.
"""

import time
from pathlib import Path
from typing import Optional

import pandas as pd
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

from config import OUTPUT_DIR
from risk_calculations import get_risk_level, risk_factor

# ---------------------------------------------------------------------------
# Reverse geocode: (lat, lon) -> county name, state
# ---------------------------------------------------------------------------
GEOCODE_DELAY_SEC = 1.2
USER_AGENT = "maternal-risk-pin-drop"


def _geolocator():
    return Nominatim(user_agent=USER_AGENT)


def county_from_coords(lat: float, lon: float) -> Optional[dict]:
    """
    Reverse geocode (lat, lon) to get county and state.
    Returns {"county": str, "state": str} or None if not found.
    """
    try:
        time.sleep(GEOCODE_DELAY_SEC)
        loc = _geolocator().reverse(f"{lat}, {lon}", timeout=10, language="en")
        if not loc or not loc.raw:
            return None
        raw = loc.raw
        # Prefer structured addressdetails (Nominatim with addressdetails=1)
        addr = raw.get("address") or {}
        county = (
            addr.get("county")
            or addr.get("state_district")
            or (loc.address.split(",")[1].strip() if loc.address and "," in loc.address else None)
        )
        state = addr.get("state") or ""
        if not county:
            return None
        return {"county": str(county).strip(), "state": str(state).strip()}
    except (GeocoderTimedOut, GeocoderServiceError, Exception):
        return None


def _normalize_county(name: str) -> str:
    """Match CSV: e.g. 'Fulton County' -> 'Fulton', 'Fulton' -> 'Fulton'."""
    if not name:
        return ""
    s = str(name).strip()
    if s.lower().endswith(" county"):
        s = s[:-7].strip()
    return s


# ---------------------------------------------------------------------------
# Load county row from pipeline CSV
# ---------------------------------------------------------------------------
RISK_CSV = OUTPUT_DIR / "risk_factor_by_county.csv"


def _load_county_row(county_name: str, state: str = "GA") -> Optional[dict]:
    """
    Load one county's data from risk_factor_by_county.csv.
    county_name: normalized name (e.g. 'Fulton' or 'Fulton County').
    Returns dict with county, pct_late_no_prenatal_care, pct_births_in_state, ob_beds, risk_factor, level (optional).
    """
    if not RISK_CSV.exists():
        return None
    df = pd.read_csv(RISK_CSV)
    df["county"] = df["county"].astype(str).str.strip().str.replace(r"\s+County\s*$", "", regex=True, case=False)
    norm = _normalize_county(county_name)
    match = df[(df["county"].str.strip().str.lower() == norm.lower()) & (df["state"].astype(str).str.strip().str.upper() == str(state).upper())]
    if match.empty:
        return None
    row = match.iloc[0]
    return {
        "county": str(row["county"]).strip(),
        "state": str(row["state"]).strip(),
        "pct_late_no_prenatal_care": float(row["pct_late_no_prenatal_care"]),
        "pct_births_in_state": float(row["pct_births_in_state"]),
        "ob_beds": int(row["ob_beds"]) if pd.notna(row["ob_beds"]) else 0,
        "risk_factor": float(row["risk_factor"]) if pd.notna(row["risk_factor"]) else None,
        "level": str(row["level"]).strip() if "level" in row and pd.notna(row.get("level")) else None,
    }


# ---------------------------------------------------------------------------
# Main: pin drop -> temporary beds -> recalc risk -> new level
# ---------------------------------------------------------------------------
def pin_drop_to_risk_level(
    lat: float,
    lon: float,
    beds_added: int = 0,
) -> dict:
    """
    Given a pin at (lat, lon) and optional beds to add:

    1. Resolve which county the pin is in (reverse geocode).
    2. Temporarily add beds_added to that county's OB bed count (no data saved).
    3. Recalculate risk factor: (Prenatal% × Births%) / max(ob_beds + beds_added, 1).
    4. Return the new risk level and related info.

    Returns dict with:
      - county, state
      - original_ob_beds, original_risk_factor, original_risk_level
      - beds_added, temporary_ob_beds
      - temporary_risk_factor, new_risk_level
      - error: str if something failed (e.g. county not found, no CSV).
    """
    out = {
        "county": None,
        "state": None,
        "original_ob_beds": None,
        "original_risk_factor": None,
        "original_risk_level": None,
        "beds_added": int(beds_added),
        "temporary_ob_beds": None,
        "temporary_risk_factor": None,
        "new_risk_level": None,
        "error": None,
    }
    if beds_added < 0:
        beds_added = 0

    # 1. Resolve county from coordinates
    geo = county_from_coords(lat, lon)
    if not geo:
        out["error"] = "Could not determine county from coordinates."
        return out
    county_name = geo["county"]
    state = geo["state"] or "GA"

    # 2. Load county data from CSV
    row = _load_county_row(county_name, state)
    if not row:
        out["error"] = f"County '{county_name}' not found in risk data (or CSV missing)."
        return out

    out["county"] = row["county"]
    out["state"] = row["state"]
    prenatal = row["pct_late_no_prenatal_care"]
    births = row["pct_births_in_state"]
    ob_beds = row["ob_beds"]
    # Pipeline may store 1 for 0-bed counties; use as-is for formula consistency
    out["original_ob_beds"] = ob_beds
    out["original_risk_factor"] = row["risk_factor"]
    out["original_risk_level"] = row["level"] or get_risk_level(row["risk_factor"] or 0.0)

    # 3. Temporary beds and recalc risk factor (no write)
    temporary_beds = ob_beds + beds_added
    out["temporary_ob_beds"] = temporary_beds
    new_rf = risk_factor(prenatal, births, temporary_beds)
    out["temporary_risk_factor"] = round(new_rf, 3)
    out["new_risk_level"] = get_risk_level(new_rf)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python pin_drop_risk.py <latitude> <longitude> [beds_added]")
        print("Example: python pin_drop_risk.py 33.7490 -84.3880 10")
        sys.exit(1)
    lat = float(sys.argv[1])
    lon = float(sys.argv[2])
    beds = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    result = pin_drop_to_risk_level(lat, lon, beds_added=beds)
    if result.get("error"):
        print("Error:", result["error"])
        sys.exit(2)
    print("County:", result["county"], result["state"])
    print("Original: OB beds =", result["original_ob_beds"], ", risk factor =", result["original_risk_factor"], ", level =", result["original_risk_level"])
    print("After adding", result["beds_added"], "beds (temporary): OB beds =", result["temporary_ob_beds"], ", risk factor =", result["temporary_risk_factor"])
    print("New risk level:", result["new_risk_level"])
    sys.exit(0)
