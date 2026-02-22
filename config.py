"""
Configuration for the maternal risk factor pipeline.
Uses GA_Births_Prenatal_Care.xlsx and GA_OB_Hospitals_by_County.xlsx.
Risk formula: (Pct_Late_No_Prenatal_Care × Pct_Births_In_State) / max(OB_Beds, 1).
"""
from pathlib import Path

# Base paths (absolute to workspace root)
PROJECT_ROOT = Path(r"D:/WW 765/OneDrive - MV Foods 1 LLC/Mahi/Georgia Tech/Hacklytics 2026")
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"

# ---------------------------------------------------------------------------
# Dataset 1: Percent of Births With Late Or No Prenatal Care + % of Georgia Births (by county)
# Source: GA_Births_Prenatal_Care.xlsx
# ---------------------------------------------------------------------------
DATASET_Prenatal_Care = {
    "path": PROJECT_ROOT / "GA_Births_Prenatal_Care.xlsx",
    "file_type": "excel",
    "sheet_name": "Prenatal Care & Births",
    "columns": {
        "county": "County",
        "pct_late_no_prenatal_care": "% Births with Late or No Prenatal Care",
        "pct_births_in_state": "% of Georgia Births",
    },
    "pct_is_decimal": False,
    "state_fixed": "GA",  # no state column in file; all rows are Georgia
}

# ---------------------------------------------------------------------------
# Dataset 2: Percent of Births in the State (by state)
# Set path to None when pct_births_in_state comes from Dataset 1 (same file).
# ---------------------------------------------------------------------------
DATASET_Births_In_State = {
    "path": None,
    "file_type": "csv",
    "columns": {
        "state": "state",
        "pct_births_in_state": "pct_births_in_state",
    },
    "pct_is_decimal": False,
}

# ---------------------------------------------------------------------------
# Dataset 3: Number of OB Beds in the County
# Source: GA_OB_Hospitals_by_County.xlsx – "Summary by County" has Total OB Beds per county.
# ---------------------------------------------------------------------------
DATASET_OB_Beds = {
    "path": PROJECT_ROOT / "GA_OB_Hospitals_by_County.xlsx",
    "file_type": "excel",
    "sheet_name": "Summary by County",
    "columns": {
        "county": "County",
        "ob_beds": "Total OB Beds",
    },
    "state_fixed": "GA",
}

# ---------------------------------------------------------------------------
# Optional: Dataset 4 – Average distance to maternal care center (by county)
# ---------------------------------------------------------------------------
DATASET_Avg_Distance = {
    "path": None,
    "file_type": "csv",
    "columns": {
        "county": "county",
        "state": "state",
        "avg_distance_miles": "avg_distance_miles",
    },
}

# ---------------------------------------------------------------------------
# Optional: Zip-to-County CSV for true average distance (by zip) per county.
# CSV must have columns: zip (or zcta), county. Set to None to use centroid-to-nearest only.
# USE_ZIP_AVG_DISTANCE: If True, use zip-based average (slow: geocodes many zips). If False, use
# centroid-to-nearest (fast, ~2–3 min). Set True only when you need zip-averaged distance.
# ---------------------------------------------------------------------------
ZIP_COUNTY_CSV_PATH = DATA_DIR / "zip_county_ga.csv"  # Set to None to use centroid-to-nearest only
USE_ZIP_AVG_DISTANCE = False  # True = slow zip-based avg; False = fast centroid-to-nearest (recommended)

# ---------------------------------------------------------------------------
# County GeoJSON for map (US counties with FIPS or matching id)
# Set to None to skip GeoJSON output.
# ---------------------------------------------------------------------------
COUNTY_GEOJSON_PATH = None
GEOJSON_JOIN_KEY = "fips"
USE_FIPS_COLUMNS = False
STATE_FIPS_COL = "state_fips"
COUNTY_FIPS_COL = "county_fips"
