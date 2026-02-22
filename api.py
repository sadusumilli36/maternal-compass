"""
FastAPI backend: serves risk factor table, GeoJSON, nearest-facility by zip, and predictive model.

Run: uvicorn api:app --reload
Then open: http://127.0.0.1:8000/docs for Swagger UI.
"""
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import OUTPUT_DIR
from nearest_facility import get_nearest_facility
from risk_calculations import (
    LOW_RISK_THRESHOLD,
    MODERATE_RISK_THRESHOLD,
    HIGH_RISK_THRESHOLD,
    beds_needed_for_low_risk,
    simulate_beds,
)

app = FastAPI(
    title="Maternal Risk Factor API",
    description="Serves county risk factor data, GeoJSON for the heat map, and nearest OB facility by zip code.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEOJSON_PATH = OUTPUT_DIR / "counties_with_risk.geojson"
TABLE_CSV_PATH = OUTPUT_DIR / "risk_factor_by_county.csv"
TABLE_WITH_LEVEL_PATH = OUTPUT_DIR / "risk_factor_by_county_with_level.csv"
STATIC_DIR = Path(__file__).resolve().parent / "static"


def _load_counties_df() -> pd.DataFrame:
    """Load county table; prefer with_level CSV if present."""
    path = TABLE_WITH_LEVEL_PATH if TABLE_WITH_LEVEL_PATH.exists() else TABLE_CSV_PATH
    if not path.exists():
        raise HTTPException(status_code=503, detail="Run calculate_risk_factor.py first.")
    df = pd.read_csv(path)
    df["county"] = df["county"].astype(str).str.strip()
    return df


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def root():
    return {
        "message": "Maternal Risk Factor API",
        "endpoints": {
            "map": "/map",
            "geojson": "/api/counties/geojson",
            "table": "/api/counties/table",
            "counties": "/api/counties",
            "thresholds": "/api/thresholds",
            "predictive": "/api/counties/{county}/predictive",
            "nearest_facility": "/api/nearest-facility?zip=30332",
            "docs": "/docs",
        },
    }


@app.get("/map")
def map_page():
    """Serve the county risk map with predictive model panel."""
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Map app not found")
    return FileResponse(index_path, media_type="text/html")


@app.get("/api/counties/geojson")
def get_counties_geojson():
    """
    Returns the enriched GeoJSON (county geometries + risk_factor and popup fields).
    Use this in the frontend to render the choropleth and fill click popups.
    """
    if not GEOJSON_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail="GeoJSON not generated. Run calculate_risk_factor.py with COUNTY_GEOJSON_PATH set in config.",
        )
    return FileResponse(
        GEOJSON_PATH,
        media_type="application/geo+json",
    )


@app.get("/api/counties/table")
def get_counties_table():
    """
    Returns the risk factor table as CSV (for download or tabular display).
    """
    if not TABLE_CSV_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail="Table not generated. Run calculate_risk_factor.py first.",
        )
    return FileResponse(
        TABLE_CSV_PATH,
        media_type="text/csv",
        filename="risk_factor_by_county.csv",
    )


@app.get("/api/nearest-facility")
def api_nearest_facility(zip: str = Query(..., description="US zip code (e.g. 30332)")):
    """
    Given a zip code, returns the nearest OB facility in Georgia:
    facility name, county, distance in miles, and OB bed count at that hospital.
    """
    result = get_nearest_facility(zip)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Could not geocode that zip code or no facilities available. Try a valid Georgia (or US) zip.",
        )
    return result


@app.get("/api/thresholds")
def get_thresholds():
    """Return risk level thresholds used by the predictive model (same as pipeline)."""
    return {
        "low_risk_threshold": LOW_RISK_THRESHOLD,
        "moderate_risk_threshold": MODERATE_RISK_THRESHOLD,
        "high_risk_threshold": HIGH_RISK_THRESHOLD,
    }


@app.get("/api/counties")
def get_counties_json():
    """
    Return counties as JSON for map and detail panel.
    Includes fields needed for predictive model: county, prenatal_pct, births_pct, ob_beds, risk_factor, risk_level.
    """
    df = _load_counties_df()
    cols = {
        "county": "county",
        "pct_late_no_prenatal_care": "prenatal_pct",
        "pct_births_in_state": "births_pct",
        "ob_beds": "ob_beds",
        "risk_factor": "risk_factor",
        "level": "risk_level",
        "avg_distance_miles": "avg_distance_miles",
    }
    out = []
    for _, row in df.iterrows():
        rec = {}
        for csv_col, api_col in cols.items():
            if csv_col in df.columns:
                v = row[csv_col]
                if pd.isna(v) and api_col != "risk_level":
                    v = None
                elif api_col == "ob_beds":
                    v = int(v) if pd.notna(v) else 0
                elif api_col in ("risk_factor", "prenatal_pct", "births_pct", "avg_distance_miles") and pd.notna(v):
                    v = float(v)
                elif api_col == "risk_level" and pd.notna(v):
                    v = str(v).strip()
                rec[api_col] = v
        rec["low_risk_threshold"] = LOW_RISK_THRESHOLD
        out.append(rec)
    return out


@app.get("/api/counties/{county_name}/predictive")
def get_county_predictive(
    county_name: str,
    beds_added: int = Query(0, ge=0, le=10000, description="Simulate adding this many beds"),
):
    """
    Predictive model for a county: beds needed for low risk + optional simulation.
    Returns beds needed and, if beds_added > 0, simulated risk factor and level.
    """
    df = _load_counties_df()
    county_name = county_name.strip()
    match = df[df["county"].str.strip().str.equals(county_name, case=False)]
    if match.empty:
        raise HTTPException(status_code=404, detail=f"County not found: {county_name}")
    row = match.iloc[0]
    prenatal = float(row["pct_late_no_prenatal_care"])
    births = float(row["pct_births_in_state"])
    ob_beds = int(row["ob_beds"]) if pd.notna(row["ob_beds"]) else 0
    risk = float(row["risk_factor"])
    current_level = str(row.get("level", "")).strip() if "level" in row and pd.notna(row.get("level")) else None

    beds_result = beds_needed_for_low_risk(prenatal, births, ob_beds)
    sim = simulate_beds(prenatal, births, ob_beds, risk, beds_added or 0)

    return {
        "county": county_name,
        "prenatal_pct": prenatal,
        "births_pct": births,
        "ob_beds": ob_beds,
        "risk_factor": risk,
        "risk_level": current_level,
        "low_risk_threshold": LOW_RISK_THRESHOLD,
        "beds_needed": {
            "current_ob_beds": beds_result.current_ob_beds,
            "beds_required": beds_result.beds_required,
            "additional_beds_needed": beds_result.additional_beds_needed,
            "already_low_risk": beds_result.already_low_risk,
        },
        "simulation": {
            "beds_added": beds_added or 0,
            "simulated_beds": sim.simulated_beds,
            "simulated_risk_factor": sim.simulated_risk_factor,
            "simulated_risk_level": sim.simulated_risk_level,
            "risk_factor_reduction": sim.risk_factor_reduction,
            "percent_improvement": sim.percent_improvement,
            "achieves_low_risk": sim.achieves_low_risk,
            "more_beds_needed_for_low": sim.more_beds_needed_for_low,
        },
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}
