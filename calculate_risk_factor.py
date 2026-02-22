"""
Maternal Risk Factor Pipeline.

Formula:
  risk_factor = (Pct_Late_No_Prenatal_Care * Pct_Births_In_State) / max(OB_Beds, 1)

Run: python calculate_risk_factor.py
"""
from pathlib import Path
import json

import pandas as pd

from config import (
    OUTPUT_DIR,
    DATASET_Prenatal_Care,
    DATASET_Births_In_State,
    DATASET_OB_Beds,
    DATASET_Avg_Distance,
    ZIP_COUNTY_CSV_PATH,
    USE_ZIP_AVG_DISTANCE,
    COUNTY_GEOJSON_PATH,
    GEOJSON_JOIN_KEY,
    USE_FIPS_COLUMNS,
    STATE_FIPS_COL,
    COUNTY_FIPS_COL,
)
from pathlib import Path


def load_table(path: Path, file_type: str, sheet_name=None) -> pd.DataFrame:
    """Load CSV or Excel file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")
    if file_type == "csv":
        return pd.read_csv(path)
    if file_type == "excel":
        kwargs = {}
        if sheet_name is not None:
            kwargs["sheet_name"] = sheet_name
        return pd.read_excel(path, **kwargs)
    raise ValueError(f"Unsupported file_type: {file_type}")


def load_and_rename(cfg: dict, required_cols: list) -> pd.DataFrame:
    """Load a dataset and rename columns to standard names."""
    sheet_name = cfg.get("sheet_name")
    df = load_table(cfg["path"], cfg["file_type"], sheet_name=sheet_name)
    renames = {v: k for k, v in cfg["columns"].items() if v in df.columns}
    df = df.rename(columns=renames)
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns {missing} in {cfg['path']}. Available: {list(df.columns)}")
    return df


def normalize_percent(series: pd.Series, is_decimal: bool) -> pd.Series:
    """Ensure percent is in 0-100 scale."""
    s = pd.to_numeric(series, errors="coerce")
    if is_decimal:
        s = s * 100
    return s


def build_fips(df: pd.DataFrame) -> pd.Series:
    """Build 5-digit FIPS from state_fips (2-digit) and county_fips (3-digit)."""
    return (
        df[STATE_FIPS_COL].astype(str).str.zfill(2)
        + df[COUNTY_FIPS_COL].astype(str).str.zfill(3)
    )


def run_pipeline() -> pd.DataFrame:
    # ----- Dataset 1: Prenatal care by county (and optionally % births in state from same file) -----
    prenatal_cols = ["county", "pct_late_no_prenatal_care"]
    if "pct_births_in_state" in DATASET_Prenatal_Care.get("columns", {}):
        prenatal_cols.append("pct_births_in_state")
    else:
        prenatal_cols.append("state")
    df_prenatal = load_and_rename(DATASET_Prenatal_Care, prenatal_cols)
    df_prenatal["pct_late_no_prenatal_care"] = normalize_percent(
        df_prenatal["pct_late_no_prenatal_care"],
        DATASET_Prenatal_Care.get("pct_is_decimal", False),
    )
    if "pct_births_in_state" in df_prenatal.columns:
        df_prenatal["pct_births_in_state"] = normalize_percent(
            df_prenatal["pct_births_in_state"],
            DATASET_Prenatal_Care.get("pct_is_decimal", False),
        )
    if "state" not in df_prenatal.columns and DATASET_Prenatal_Care.get("state_fixed"):
        df_prenatal["state"] = DATASET_Prenatal_Care["state_fixed"]
    df_prenatal["county"] = df_prenatal["county"].astype(str).str.strip()
    df_prenatal["state"] = df_prenatal["state"].astype(str).str.strip()

    # ----- Dataset 2: Percent births in state (optional; skip if from Dataset 1) -----
    if DATASET_Births_In_State.get("path") and Path(DATASET_Births_In_State["path"]).exists():
        df_state = load_and_rename(
            DATASET_Births_In_State,
            ["state", "pct_births_in_state"],
        )
        df_state["pct_births_in_state"] = normalize_percent(
            df_state["pct_births_in_state"],
            DATASET_Births_In_State.get("pct_is_decimal", False),
        )
        df_state["state"] = df_state["state"].astype(str).str.strip()
        merged = df_prenatal.merge(df_state, on="state", how="left")
    else:
        merged = df_prenatal.copy()

    # ----- Dataset 3: OB beds by county (from GA_OB_Hospitals_by_County.xlsx) -----
    df_ob = load_and_rename(DATASET_OB_Beds, ["county", "ob_beds"])
    df_ob = df_ob[["county", "ob_beds"]].copy()
    df_ob["county"] = df_ob["county"].astype(str).str.strip()
    df_ob["ob_beds"] = pd.to_numeric(df_ob["ob_beds"], errors="coerce").fillna(0).astype(int)
    df_ob["state"] = DATASET_OB_Beds.get("state_fixed", "GA")

    merged = merged.merge(
        df_ob,
        on=["county", "state"],
        how="left",
    )
    merged["ob_beds"] = merged["ob_beds"].fillna(0).astype(int)
    # If a county has 0 OB beds, set to 1 to avoid division by zero and better represent lack of capacity
    merged["ob_beds"] = merged["ob_beds"].replace(0, 1)

    # ----- Optional: derive county-level maternal care `level` from facilities list -----
    facilities_path = Path(__file__).resolve().parent / "GA_Maternal_Care_Facilities.xlsx"
    ob_hospitals_path = Path(__file__).resolve().parent / "GA_OB_Hospitals_by_County.xlsx"
    if facilities_path.exists() and ob_hospitals_path.exists():
        try:
            df_fac = pd.read_excel(facilities_path, sheet_name=0)
            # Parse 'Level I/II/III/IV' headings interleaved in the file.
            current_level = None
            fac_rows = []
            import re

            roman_map = {"i": 1, "ii": 2, "iii": 3, "iv": 4}
            for _, r in df_fac.iterrows():
                name = str(r.get("Facility Name", "")).strip()
                county = r.get("County")
                if not name:
                    continue
                m = re.match(r"^level\s*([ivxlcdm]+|\d+)", name.strip(), flags=re.I)
                if m:
                    tok = m.group(1).lower()
                    if tok.isdigit():
                        current_level = int(tok)
                    else:
                        current_level = roman_map.get(tok, None)
                    continue
                # normal facility row
                fac_rows.append({"facility_name": name, "county": str(county).strip() if pd.notna(county) else "" , "level": current_level})

            df_fac_parsed = pd.DataFrame(fac_rows)
            # Normalize facility names for matching
            df_fac_parsed["_name_norm"] = df_fac_parsed["facility_name"].str.lower().str.replace(r"[^\w]", " ", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()

            # Read OB hospitals list and normalize names
            df_obs = pd.read_excel(ob_hospitals_path, sheet_name="OB Hospitals by County")
            df_obs["_hosp_norm"] = df_obs["Hospital Name"].astype(str).str.lower().str.replace(r"[^\w]", " ", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()

            # For each hospital, attempt to find matching facility by exact normalized name or substring
            matches = []
            for _, h in df_obs.iterrows():
                hname = h["Hospital Name"]
                hnorm = h["_hosp_norm"]
                found_levels = []
                # exact match
                exact = df_fac_parsed[df_fac_parsed["_name_norm"] == hnorm]
                if not exact.empty:
                    found_levels.extend(exact["level"].dropna().astype(int).tolist())
                else:
                    # substring match both ways
                    contains = df_fac_parsed[df_fac_parsed["_name_norm"].str.contains(hnorm, na=False)]
                    if not contains.empty:
                        found_levels.extend(contains["level"].dropna().astype(int).tolist())
                    else:
                        # fallback: match by first token
                        first_tok = hnorm.split()[0] if hnorm else ""
                        if first_tok:
                            contained_in = df_fac_parsed[df_fac_parsed["_name_norm"].str.contains(first_tok, na=False)]
                            if not contained_in.empty:
                                found_levels.extend(contained_in["level"].dropna().astype(int).tolist())

                lvl = max(found_levels) if found_levels else None
                matches.append({"Hospital Name": hname, "county": h.get("County", ""), "level": lvl})

            df_hosp_levels = pd.DataFrame(matches)
            # aggregate highest level per county
            county_level = (
                df_hosp_levels.dropna(subset=["level"]).groupby(df_hosp_levels["county"].str.strip())["level"].max().reset_index()
            )
            county_level.columns = ["county", "level"]
            county_level["state"] = DATASET_OB_Beds.get("state_fixed", "GA")

            merged = merged.merge(county_level, on=["county", "state"], how="left")
        except Exception:
            # If anything fails, continue without level
            pass

    # Optional: average distance
    if DATASET_Avg_Distance.get("path") and Path(DATASET_Avg_Distance["path"]).exists():
        df_dist = load_and_rename(
            DATASET_Avg_Distance,
            ["county", "state", "avg_distance_miles"],
        )
        df_dist["county"] = df_dist["county"].astype(str).str.strip()
        df_dist["state"] = df_dist["state"].astype(str).str.strip()
        merged = merged.merge(
            df_dist,
            on=["county", "state"],
            how="left",
        )
    else:
        # Compute distance per county: centroid-to-nearest (fast) or zip-based average (slow).
        # Use centroid unless USE_ZIP_AVG_DISTANCE is True so avg_distance_miles populates in ~2–3 min.
        county_list = merged["county"].dropna().astype(str).str.strip().unique().tolist()
        state_abbr = merged["state"].iloc[0] if "state" in merged.columns else "GA"
        zip_county_path = Path(ZIP_COUNTY_CSV_PATH) if ZIP_COUNTY_CSV_PATH else None
        county_info = None
        try:
            if USE_ZIP_AVG_DISTANCE and zip_county_path and zip_county_path.exists():
                from nearest_facility import compute_county_avg_distance_by_zip
                county_info = compute_county_avg_distance_by_zip(county_list, zip_county_path, state=state_abbr)
            else:
                from nearest_facility import compute_county_nearest
                county_info = compute_county_nearest(county_list, state=state_abbr)
        except Exception:
            county_info = None
        if not county_info and USE_ZIP_AVG_DISTANCE and zip_county_path and zip_county_path.exists():
            try:
                from nearest_facility import compute_county_nearest
                county_info = compute_county_nearest(county_list, state=state_abbr)
            except Exception:
                pass
        if county_info:
            merged["avg_distance_miles"] = merged["county"].map(lambda c: county_info.get(str(c).strip(), {}).get("distance_miles") if c is not None else None)
        else:
            merged["avg_distance_miles"] = None

    # Build FIPS if requested (for GeoJSON join)
    if USE_FIPS_COLUMNS and STATE_FIPS_COL in merged.columns and COUNTY_FIPS_COL in merged.columns:
        merged["fips"] = build_fips(merged)
    else:
        merged["fips"] = None

    # Ensure pct_births_in_state is numeric and default zeros to 1 (avoid zeroing risk)
    if "pct_births_in_state" in merged.columns:
        merged["pct_births_in_state"] = pd.to_numeric(merged["pct_births_in_state"], errors="coerce")
        merged["pct_births_in_state"] = merged["pct_births_in_state"].replace(0, 1)

    # ----- Risk factor formula (denominator min 1 to avoid division by zero) -----
    ob_beds_safe = merged["ob_beds"].clip(lower=1)
    merged["risk_factor"] = (
        merged["pct_late_no_prenatal_care"] * merged["pct_births_in_state"]
    ) / ob_beds_safe

    # Round risk_factor for output clarity
    merged["risk_factor"] = merged["risk_factor"].round(3)

    # Drop rows where we're missing required inputs (optional: could impute)
    merged = merged.dropna(subset=["pct_late_no_prenatal_care", "pct_births_in_state"])
    merged = merged.sort_values("risk_factor", ascending=False).reset_index(drop=True)

    return merged


def save_table(df: pd.DataFrame) -> None:
    """Write risk factor table to CSV and Excel. Excludes avg_drive_time_min and fips."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    drop_cols = [c for c in ["avg_drive_time_min", "fips"] if c in out.columns]
    if drop_cols:
        out = out.drop(columns=drop_cols)
    out_csv = OUTPUT_DIR / "risk_factor_by_county.csv"
    out_xlsx = OUTPUT_DIR / "risk_factor_by_county.xlsx"
    out.to_csv(out_csv, index=False)
    out.to_excel(out_xlsx, index=False, engine="openpyxl")
    print(f"Table saved: {out_csv}, {out_xlsx}")


def normalize_fips_for_join(fips) -> str:
    """Ensure FIPS is 5-digit string for joining with GeoJSON."""
    if pd.isna(fips):
        return ""
    s = str(int(fips)) if fips == fips else str(fips)
    return s.zfill(5) if len(s) <= 5 else s[-5:]


def build_geojson_join_key(row, join_key: str, df: pd.DataFrame) -> str:
    if join_key == "fips":
        if "fips" in df.columns and row.get("fips") is not None:
            return normalize_fips_for_join(row["fips"])
        if USE_FIPS_COLUMNS:
            return normalize_fips_for_join(
                str(row.get(STATE_FIPS_COL, "")).zfill(2)
                + str(row.get(COUNTY_FIPS_COL, "")).zfill(3)
            )
        return ""
    # name: state + county
    return f"{row.get('state', '')}|{row.get('county', '')}".strip()


def enrich_geojson(df: pd.DataFrame, geojson_path: Path, join_key: str) -> dict:
    """
    Load county GeoJSON and add risk_factor + popup fields to each feature's properties.
    GeoJSON feature id or properties.id or properties.FIPS should match county identifier.
    """
    with open(geojson_path, encoding="utf-8") as f:
        geojson = json.load(f)

    # Build lookup from pipeline table: join_key_value -> row
    df = df.copy()
    df["_join"] = df.apply(lambda r: build_geojson_join_key(r, join_key, df), axis=1)
    lookup = df.set_index("_join").to_dict("index")

    def get_feature_id(feat):
        fid = feat.get("id")
        if fid is not None:
            return str(fid).zfill(5) if join_key == "fips" else str(fid)
        prop = feat.get("properties") or {}
        return str(prop.get("FIPS") or prop.get("fips") or prop.get("GEO_ID") or "").zfill(5)

    matched = 0
    for feat in geojson.get("features", []):
        fid = get_feature_id(feat)
        if join_key == "name":
            prop = feat.get("properties") or {}
            fid = f"{prop.get('STATE', '')}|{prop.get('NAME', '')}"
        row = lookup.get(fid)
        if row is None and len(fid) == 5:
            row = lookup.get(fid.lstrip("0")) or lookup.get(fid)
        if row is not None:
            matched += 1
            props = feat.setdefault("properties", {})
            props["risk_factor"] = round(float(row["risk_factor"]), 4)
            props["pct_late_no_prenatal_care"] = round(float(row["pct_late_no_prenatal_care"]), 2)
            props["ob_beds"] = int(row["ob_beds"])
            if row.get("avg_distance_miles") is not None and pd.notna(row["avg_distance_miles"]):
                props["avg_distance_miles"] = round(float(row["avg_distance_miles"]), 2)
            else:
                props["avg_distance_miles"] = None
            props["pct_births_in_state"] = round(float(row["pct_births_in_state"]), 2)
            if "county" not in props:
                props["county"] = row.get("county", "")
            if "state" not in props:
                props["state"] = row.get("state", "")

    print(f"GeoJSON: matched {matched} counties to pipeline output.")
    return geojson


def save_geojson(geojson: dict) -> None:
    """Write enriched GeoJSON to output directory."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "counties_with_risk.geojson"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, indent=2)
    print(f"GeoJSON saved: {out_path}")


def main() -> None:
    print("Running maternal risk factor pipeline...")
    df = run_pipeline()
    print(f"Computed risk factor for {len(df)} counties.")
    save_table(df)

    if COUNTY_GEOJSON_PATH and Path(COUNTY_GEOJSON_PATH).exists():
        geojson = enrich_geojson(df, Path(COUNTY_GEOJSON_PATH), GEOJSON_JOIN_KEY)
        save_geojson(geojson)
    else:
        print("No county GeoJSON path set or file missing. Skipping GeoJSON output.")
        print("Set config.COUNTY_GEOJSON_PATH and re-run to generate map data.")


if __name__ == "__main__":
    main()
