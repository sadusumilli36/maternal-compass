"""
Nearest OB facility by zip code.
Uses geopy (Nominatim) for geocoding. Caches facility lat/lon so we only geocode once.
"""
from pathlib import Path
import json
import os
import time
from typing import Dict, List, Optional, Tuple

import pandas as pd
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

from config import PROJECT_ROOT, OUTPUT_DIR

# Optional HTTP requests (used for Google Distance Matrix)
try:
    import requests
    HAS_REQUESTS = True
except Exception:
    requests = None
    HAS_REQUESTS = False

OB_HOSPITALS_PATH = PROJECT_ROOT / "GA_OB_Hospitals_by_County.xlsx"
OB_HOSPITALS_SHEET = "OB Hospitals by County"
MATERNAL_LEVELS_PATH = PROJECT_ROOT / "GA_Maternal_Care_Facilities.xlsx"
MATERNAL_LEVELS_SHEET = "GA Maternal Care Facilities"
FACILITY_CACHE_PATH = OUTPUT_DIR / "facility_latlon_cache.json"
ZIP_CACHE_PATH = OUTPUT_DIR / "zip_latlon_cache.json"
COUNTY_CACHE_PATH = OUTPUT_DIR / "county_latlon_cache.json"
ZIP_NEAREST_DISTANCE_CACHE_PATH = OUTPUT_DIR / "zip_nearest_distance_cache.json"

# Maternal care level headers in the Excel (section headers with NaN County)
LEVEL_NAMES = ("Level I", "Level II", "Level III", "Level IV")

# Nominatim allows 1 request per second (policy); use a short delay
GEOCODE_DELAY_SEC = 1.2
USER_AGENT = "maternal-risk-factor-app"


def _geolocator():
    return Nominatim(user_agent=USER_AGENT)


def _load_ob_hospitals() -> pd.DataFrame:
    """Load OB hospitals list (Hospital Name, County, OB Beds)."""
    path = OB_HOSPITALS_PATH
    if not path.exists():
        raise FileNotFoundError(f"OB hospitals file not found: {path}")
    df = pd.read_excel(path, sheet_name=OB_HOSPITALS_SHEET)
    # Drop header-like rows where County is missing
    df = df.dropna(subset=["County", "OB Beds"])
    df["County"] = df["County"].astype(str).str.strip()
    df["Hospital Name"] = df["Hospital Name"].astype(str).str.strip()
    df["OB Beds"] = pd.to_numeric(df["OB Beds"], errors="coerce").fillna(0).astype(int)
    return df


def _load_facility_levels() -> Dict[tuple, Optional[str]]:
    """
    Load (facility name, county) -> maternal care level from GA_Maternal_Care_Facilities.xlsx.
    Level is given by section headers (Level I, Level II, Level III, Level IV); each facility
    row gets the level of the preceding header. Returns dict keyed by (name_lower, county_lower).
    """
    path = MATERNAL_LEVELS_PATH
    if not path.exists():
        return {}
    df = pd.read_excel(path, sheet_name=MATERNAL_LEVELS_SHEET)
    level_map = {}
    current_level = None
    for _, row in df.iterrows():
        name = str(row.get("Facility Name", "")).strip()
        county = row.get("County")
        if name in LEVEL_NAMES:
            current_level = name
            continue
        if pd.isna(county) or not name:
            continue
        county = str(county).strip()
        key = (name.lower(), county.lower())
        level_map[key] = current_level or None
    return level_map


def _geocode_with_retry(geolocator, query: str, max_tries: int = 2) -> Optional[Tuple[float, float]]:
    """Geocode a string; return (lat, lon) or None. Respects rate limit."""
    for _ in range(max_tries):
        try:
            time.sleep(GEOCODE_DELAY_SEC)
            loc = geolocator.geocode(query, timeout=10)
            if loc:
                return (loc.latitude, loc.longitude)
        except (GeocoderTimedOut, GeocoderServiceError):
            time.sleep(GEOCODE_DELAY_SEC)
    return None


def _apply_levels_to_facilities(facilities: List[dict], level_map: Dict[tuple, Optional[str]]) -> None:
    """Set 'level' on each facility dict where missing, using level_map. Mutates in place."""
    for fac in facilities:
        if "level" not in fac:
            key = (fac["facility_name"].lower(), fac["county"].lower())
            fac["level"] = level_map.get(key)


def build_facility_cache(force_rebuild: bool = False) -> List[dict]:
    """
    Build or load cache of (facility -> lat, lon, level).
    Each facility is geocoded as "Hospital Name, County, GA, USA"; on failure, use county centroid.
    Level (Level I/II/III/IV) is added from GA_Maternal_Care_Facilities.xlsx where available.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    level_map = _load_facility_levels()

    if FACILITY_CACHE_PATH.exists() and not force_rebuild:
        with open(FACILITY_CACHE_PATH, encoding="utf-8") as f:
            results = json.load(f)
        # Ensure level is present on cached entries (for caches built before level was added)
        _apply_levels_to_facilities(results, level_map)
        return results

    df = _load_ob_hospitals()
    geolocator = _geolocator()
    county_coords: dict[str, tuple[float, float]] = {}
    results = []

    for _, row in df.iterrows():
        name = row["Hospital Name"]
        county = row["County"]
        ob_beds = int(row["OB Beds"])
        query_full = f"{name}, {county}, GA, USA"
        query_county = f"{county}, Georgia, USA"

        coords = _geocode_with_retry(geolocator, query_full)
        if coords:
            lat, lon = coords
        else:
            if county not in county_coords:
                county_coords[county] = _geocode_with_retry(geolocator, query_county) or (0.0, 0.0)
            lat, lon = county_coords[county]
        key = (name.lower(), county.lower())
        results.append({
            "facility_name": name,
            "county": county,
            "ob_beds": ob_beds,
            "lat": lat,
            "lon": lon,
            "level": level_map.get(key),
        })

    with open(FACILITY_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    return results


def _load_zip_cache() -> dict[str, list[float]]:
    """Load zip -> [lat, lon] cache."""
    if not ZIP_CACHE_PATH.exists():
        return {}
    with open(ZIP_CACHE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_zip_cache(cache: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(ZIP_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f)


def _geocode_zip(zip_code: str) -> Optional[Tuple[float, float]]:
    """Geocode US zip code; use cache if available."""
    zip_code = str(zip_code).strip()
    if not zip_code or len(zip_code) < 5:
        return None
    # US zip: ensure 5 digits
    zip_code = zip_code[:5].zfill(5) if zip_code.isdigit() else zip_code
    cache = _load_zip_cache()
    if zip_code in cache:
        c = cache[zip_code]
        return (c[0], c[1])
    geolocator = _geolocator()
    query = f"{zip_code}, USA"
    time.sleep(GEOCODE_DELAY_SEC)
    try:
        loc = geolocator.geocode(query, timeout=10)
        if loc:
            coords = (loc.latitude, loc.longitude)
            cache[zip_code] = [coords[0], coords[1]]
            _save_zip_cache(cache)
            return coords
    except (GeocoderTimedOut, GeocoderServiceError):
        pass
    return None


def _read_env_key(key_name: str) -> Optional[str]:
    """Read a key from env or .env file at project root. key_name e.g. 'API_KEY' or 'ORS_API_KEY'."""
    key = os.getenv(key_name)
    if key:
        return key.strip()
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return None
    try:
        text = env_path.read_text(encoding="utf-8")
    except Exception:
        return None
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    key_upper = key_name.upper()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip().upper() == key_upper:
            val = v.strip().strip('"').strip("'")
            return val if val else None
    return None


def _read_api_key() -> Optional[str]:
    """Read Google Distance Matrix API key (API_KEY)."""
    return _read_env_key("API_KEY")


def _read_ors_api_key() -> Optional[str]:
    """Read OpenRouteService API key (ORS_API_KEY or OPENROUTE_API_KEY)."""
    return _read_env_key("ORS_API_KEY") or _read_env_key("OPENROUTE_API_KEY")


def _ors_distance_duration(orig: Tuple[float, float], dest: Tuple[float, float], api_key: str) -> Optional[Tuple[float, float]]:
    """Call OpenRouteService Directions API for driving distance/time between two lat/lon points.

    Returns (distance_miles, duration_minutes) or None on failure.
    ORS expects coordinates as [lon, lat]. Key can be sent as query param or Authorization header.
    """
    if not HAS_REQUESTS or not api_key:
        return None
    key = api_key.strip()
    url = f"https://api.openrouteservice.org/v2/directions/driving-car?api_key={key}"
    # ORS uses [lon, lat] order
    body = {
        "coordinates": [
            [orig[1], orig[0]],
            [dest[1], dest[0]],
        ],
    }
    headers = {"Content-Type": "application/json"}
    try:
        resp = requests.post(url, json=body, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        routes = data.get("routes") or []
        if not routes:
            return None
        summary = routes[0].get("summary") or {}
        dist_m = summary.get("distance")
        dur_s = summary.get("duration")
        if dist_m is None or dur_s is None:
            return None
        miles = dist_m / 1609.344
        mins = dur_s / 60.0
        return (round(miles, 2), round(mins, 1))
    except Exception:
        return None


def _google_distance_duration(orig: Tuple[float, float], dest: Tuple[float, float], api_key: str) -> Optional[Tuple[float, float]]:
    """Call Google Distance Matrix for driving distance/time between two lat/lon points.

    Returns (distance_miles, duration_minutes) or None on failure.
    """
    if not HAS_REQUESTS or not api_key:
        return None
    base = "https://maps.googleapis.com/maps/api/distancematrix/json"
    origins = f"{orig[0]},{orig[1]}"
    destinations = f"{dest[0]},{dest[1]}"
    params = {
        "origins": origins,
        "destinations": destinations,
        "key": api_key,
        "mode": "driving",
        "units": "imperial",
    }
    try:
        resp = requests.get(base, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        rows = data.get("rows") or []
        if not rows:
            return None
        elems = rows[0].get("elements") or []
        if not elems:
            return None
        el = elems[0]
        if el.get("status") != "OK":
            return None
        # distance in meters, duration in seconds
        dist_m = el["distance"]["value"]
        dur_s = el["duration"]["value"]
        miles = dist_m / 1609.344
        mins = dur_s / 60.0
        return (round(miles, 2), round(mins, 1))
    except Exception:
        return None


def _driving_distance_duration(orig: Tuple[float, float], dest: Tuple[float, float]) -> Optional[Tuple[float, float]]:
    """Get driving distance (miles) and duration (minutes). Tries OpenRouteService first, then Google.
    Returns (distance_miles, duration_minutes) or None if no API key or request failed."""
    ors_key = _read_ors_api_key()
    if ors_key:
        res = _ors_distance_duration(orig, dest, ors_key)
        if res:
            return res
    api_key = _read_api_key()
    if api_key:
        return _google_distance_duration(orig, dest, api_key)
    return None


def get_nearest_facility(zip_code: str) -> Optional[dict]:
    """
    Given a zip code, return the nearest OB facility with distance (miles) and OB bed count.
    Returns None if zip cannot be geocoded or no facilities in cache.
    """
    facilities = build_facility_cache()
    zip_coords = _geocode_zip(zip_code)
    if not zip_coords:
        return None
    zip_point = zip_coords

    # Precompute straight-line distances and pick a small candidate set to query driving times
    candidates = []
    for fac in facilities:
        lat, lon = fac["lat"], fac["lon"]
        if lat == 0 and lon == 0:
            continue
        miles = geodesic(zip_point, (lat, lon)).miles
        candidates.append((miles, fac))
    if not candidates:
        return None
    # sort by straight-line distance and take top K to avoid many API calls
    candidates.sort(key=lambda x: x[0])
    K = min(6, len(candidates))
    top = [c[1] for c in candidates[:K]]

    chosen = None
    chosen_drive_miles = None
    chosen_drive_mins = None

    # If ORS or Google API available, compute driving distance/time for top candidates
    if _read_ors_api_key() or _read_api_key():
        best_drive_mins = float("inf")
        for fac in top:
            coords = (fac["lat"], fac["lon"])
            res = _driving_distance_duration(zip_point, coords)
            if res:
                d_miles, d_mins = res
                if d_mins < best_drive_mins:
                    best_drive_mins = d_mins
                    chosen = fac
                    chosen_drive_miles = d_miles
                    chosen_drive_mins = d_mins
        # If driving durations were found, return the chosen facility
        if chosen is not None:
            out = {
                "facility_name": chosen["facility_name"],
                "county": chosen["county"],
                "distance_miles": chosen_drive_miles,
                "drive_time_min": chosen_drive_mins,
                "ob_beds": chosen["ob_beds"],
            }
            if chosen.get("level"):
                out["level"] = chosen["level"]
            return out

    # Fallback: return nearest by straight-line distance and report geodesic distance
    best_geo = min(candidates, key=lambda x: x[0])[1]
    out = {
        "facility_name": best_geo["facility_name"],
        "county": best_geo["county"],
        "distance_miles": round(min(candidates, key=lambda x: x[0])[0], 2),
        "drive_time_min": None,
        "ob_beds": best_geo["ob_beds"],
    }
    if best_geo.get("level"):
        out["level"] = best_geo["level"]
    return out


def compute_county_nearest(counties: List[str], state: str = "GA") -> Dict[str, dict]:
    """For each county name, compute nearest facility geodesic distance and optional drive time.

    Returns mapping: county -> {"distance_miles": float, "drive_time_min": float|None, "facility_name": str, "ob_beds": int}
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Load or build facility cache
    facilities = build_facility_cache()
    if not facilities:
        return {}

    # Load county centroid cache
    county_cache = {}
    if COUNTY_CACHE_PATH.exists():
        try:
            with open(COUNTY_CACHE_PATH, encoding="utf-8") as f:
                county_cache = json.load(f)
        except Exception:
            county_cache = {}

    geolocator = _geolocator()
    results: Dict[str, dict] = {}
    for county in counties:
        ckey = county.strip()
        if not ckey:
            continue
        cache_key = f"{ckey}|{state}"
        if cache_key in county_cache:
            centroid = tuple(county_cache[cache_key])
        else:
            # Geocode county centroid
            q = f"{ckey} County, {state}, USA"
            centroid = None
            try:
                loc = _geocode_with_retry(geolocator, q)
                if loc:
                    centroid = loc
            except Exception:
                centroid = None
            if centroid is None:
                county_cache[cache_key] = None
            else:
                county_cache[cache_key] = [centroid[0], centroid[1]]

        centroid = county_cache.get(cache_key)
        if not centroid:
            results[ckey] = {"distance_miles": None, "drive_time_min": None, "facility_name": None, "ob_beds": None}
            continue

        # find nearest facility by geodesic distance
        best = None
        best_m = float("inf")
        for fac in facilities:
            lat, lon = fac["lat"], fac["lon"]
            if lat == 0 and lon == 0:
                continue
            m = geodesic(tuple(centroid), (lat, lon)).miles
            if m < best_m:
                best_m = m
                best = fac

        if best is None:
            results[ckey] = {"distance_miles": None, "drive_time_min": None, "facility_name": None, "ob_beds": None}
            continue

        drive_min = None
        drive_miles = None
        g = _driving_distance_duration(tuple(centroid), (best["lat"], best["lon"]))
        if g:
            drive_miles, drive_min = g

        results[ckey] = {
            "distance_miles": round(best_m, 2),
            "drive_time_min": drive_min,
            "facility_name": best.get("facility_name"),
            "ob_beds": best.get("ob_beds"),
        }

    # persist county cache
    try:
        with open(COUNTY_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(county_cache, f, indent=2)
    except Exception:
        pass

    return results


def _load_zip_nearest_cache() -> dict:
    """Load zip -> {distance_miles, drive_time_min} cache."""
    if not ZIP_NEAREST_DISTANCE_CACHE_PATH.exists():
        return {}
    try:
        with open(ZIP_NEAREST_DISTANCE_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_zip_nearest_cache(cache: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(ZIP_NEAREST_DISTANCE_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def compute_county_avg_distance_by_zip(
    counties: List[str],
    zip_county_csv_path: Path,
    state: str = "GA",
) -> Dict[str, dict]:
    """Compute average distance to nearest OB facility per county using zip codes.

    Reads a CSV with columns (zip or zcta) and (county). For each county, averages
    the distance from each zip in that county to its nearest OB facility. Uses
    get_nearest_facility(zip) and caches results in zip_nearest_distance_cache.json.

    Returns mapping: county -> {"distance_miles": float, "drive_time_min": float|None,
    "zip_count": int, "facility_name": str|None, "ob_beds": int|None}
    """
    zip_county_path = Path(zip_county_csv_path)
    if not zip_county_path.exists():
        return {}

    df = pd.read_csv(zip_county_path)
    # Accept zip or zcta for zip column; county must exist
    zip_col = "zip" if "zip" in df.columns else "zcta" if "zcta" in df.columns else None
    if zip_col is None or "county" not in df.columns:
        return {}

    df["county"] = df["county"].astype(str).str.strip()
    df[zip_col] = df[zip_col].astype(str).str.strip()
    # Normalize county name (e.g. "Fulton County" -> "Fulton")
    df["county"] = df["county"].str.replace(r"\s+County\s*$", "", regex=True, case=False)
    county_to_zips: Dict[str, List[str]] = {}
    for c in df["county"].dropna().unique():
        c = str(c).strip()
        if not c:
            continue
        zips = df.loc[df["county"] == c, zip_col].dropna().astype(str).str.strip().unique().tolist()
        zips = [z for z in zips if len(z) >= 5 and z[:5].replace("-", "").isdigit()]
        if zips:
            county_to_zips.setdefault(c, []).extend(zips)
    # Dedupe per county
    for c in county_to_zips:
        county_to_zips[c] = list(dict.fromkeys(county_to_zips[c]))

    facilities = build_facility_cache()
    if not facilities:
        return {}

    cache = _load_zip_nearest_cache()
    api_key = _read_ors_api_key() or _read_api_key()  # either enables drive-time backfill
    all_zips = list(set(z for zips in county_to_zips.values() for z in zips))
    for zip_code in all_zips:
        # Skip only if we have distance and (we have drive time or no API key to get it)
        if zip_code in cache and cache[zip_code].get("distance_miles") is not None:
            if cache[zip_code].get("drive_time_min") is not None or not api_key:
                continue
        res = get_nearest_facility(zip_code)
        if res and res.get("distance_miles") is not None:
            cache[zip_code] = {
                "distance_miles": res["distance_miles"],
                "drive_time_min": res.get("drive_time_min"),
            }
        else:
            cache[zip_code] = {"distance_miles": None, "drive_time_min": None}
    _save_zip_nearest_cache(cache)

    results: Dict[str, dict] = {}
    counties_set = {c.strip() for c in counties if c and str(c).strip()}
    for county, zips in county_to_zips.items():
        if county not in counties_set:
            continue
        distances = []
        drive_times = []
        for z in zips:
            ent = cache.get(z)
            if ent and ent.get("distance_miles") is not None:
                distances.append(ent["distance_miles"])
                if ent.get("drive_time_min") is not None:
                    drive_times.append(ent["drive_time_min"])
        if not distances:
            results[county] = {"distance_miles": None, "drive_time_min": None, "zip_count": len(zips), "facility_name": None, "ob_beds": None}
            continue
        avg_miles = round(sum(distances) / len(distances), 2)
        avg_drive = round(sum(drive_times) / len(drive_times), 1) if drive_times else None
        results[county] = {
            "distance_miles": avg_miles,
            "drive_time_min": avg_drive,
            "zip_count": len(zips),
            "facility_name": None,
            "ob_beds": None,
        }
    return results


if __name__ == "__main__":
    # Prebuild facility cache (geocodes each hospital; takes ~1–2 min with Nominatim rate limit).
    import sys
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv
    print("Building facility lat/lon cache (this may take 1–2 minutes)...")
    out = build_facility_cache(force_rebuild=force)
    print(f"Cached {len(out)} facilities at {FACILITY_CACHE_PATH}")
    if args and (args[0].isdigit() or (len(args[0]) >= 5 and args[0][:5].replace("-", "").isdigit())):
        zip_code = args[0]
        result = get_nearest_facility(zip_code)
        print(f"Nearest facility for {zip_code}: {result}")
