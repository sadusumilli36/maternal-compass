"""
Add an 'address' column to output/ob_hospitals_with_level.csv.

Uses output/facility_latlon_cache.json for (Hospital Name, county) -> (lat, lon),
then reverse geocodes each location via Nominatim and caches results in
output/facility_address_cache.json. First run takes ~1–2 min (1 req/sec);
later runs use the cache and finish in seconds.

Run after add_level_to_csv.py:
  python add_addresses_to_ob_hospitals.py
"""
import json
import time
from pathlib import Path

import pandas as pd

from config import OUTPUT_DIR
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from geopy.geocoders import Nominatim

OUTPUT_CSV = OUTPUT_DIR / "ob_hospitals_with_level.csv"
FACILITY_CACHE = OUTPUT_DIR / "facility_latlon_cache.json"
ADDRESS_CACHE = OUTPUT_DIR / "facility_address_cache.json"
GEOCODE_DELAY_SEC = 1.2
USER_AGENT = "maternal-risk-factor-app"


def _geolocator():
    return Nominatim(user_agent=USER_AGENT)


def _load_address_cache():
    if not ADDRESS_CACHE.exists():
        return {}
    with open(ADDRESS_CACHE, encoding="utf-8") as f:
        return json.load(f)


def _save_address_cache(cache):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(ADDRESS_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def reverse_geocode(lat: float, lon: float, cache: dict, geolocator) -> str:
    key = f"{lat:.6f},{lon:.6f}"
    if key in cache:
        return cache[key] or ""
    time.sleep(GEOCODE_DELAY_SEC)
    try:
        loc = geolocator.reverse(f"{lat}, {lon}", timeout=10)
        if loc and getattr(loc, "address", None):
            cache[key] = loc.address
            return loc.address
    except (GeocoderTimedOut, GeocoderServiceError):
        pass
    cache[key] = None
    return ""


def main():
    if not OUTPUT_CSV.exists():
        print(f"Not found: {OUTPUT_CSV}. Run add_level_to_csv.py first.")
        return 2
    if not FACILITY_CACHE.exists():
        print(f"Not found: {FACILITY_CACHE}. Run nearest_facility.build_facility_cache() or calculate_risk_factor.py first.")
        return 2

    df = pd.read_csv(OUTPUT_CSV)
    df["Hospital Name"] = df["Hospital Name"].astype(str).str.strip()
    df["county"] = df["county"].astype(str).str.strip()

    with open(FACILITY_CACHE, encoding="utf-8") as f:
        facilities = json.load(f)

    # (facility_name, county) -> (lat, lon)
    coord_map = {}
    for fac in facilities:
        name = (fac.get("facility_name") or "").strip()
        county = (fac.get("county") or "").strip()
        if name and county and fac.get("lat") and fac.get("lon"):
            coord_map[(name, county)] = (fac["lat"], fac["lon"])

    address_cache = _load_address_cache()
    geolocator = _geolocator()
    addresses = []
    for _, row in df.iterrows():
        name = row["Hospital Name"]
        county = row["county"]
        coords = coord_map.get((name, county))
        if not coords:
            addresses.append("")
            continue
        lat, lon = coords
        addr = reverse_geocode(lat, lon, address_cache, geolocator)
        addresses.append(addr or "")

    _save_address_cache(address_cache)
    df["address"] = addresses
    df.to_csv(OUTPUT_CSV, index=False)
    filled = sum(1 for a in addresses if a)
    print(f"Updated {OUTPUT_CSV} with address column ({filled}/{len(addresses)} filled).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
