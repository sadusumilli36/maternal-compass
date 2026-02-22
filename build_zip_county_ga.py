"""
Build data/zip_county_ga.csv for use with average-distance-by-zip.

Downloads Census ZCTA-to-County national file and filters for Georgia (state FIPS 13).
Saves zip,county CSV.

Usage:
  python build_zip_county_ga.py

Output: data/zip_county_ga.csv (columns: zip, county)

Census source: https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt
"""
from pathlib import Path
import urllib.request

import pandas as pd

from config import DATA_DIR

# Georgia FIPS 13xxx -> county name (no " County" suffix). Used as fallback if file has no names.
GA_FIPS_TO_COUNTY = [
    (1, "Appling"), (3, "Atkinson"), (5, "Bacon"), (7, "Baker"), (9, "Baldwin"),
    (11, "Banks"), (13, "Barrow"), (15, "Bartow"), (17, "Ben Hill"), (19, "Berrien"),
    (21, "Bibb"), (23, "Bleckley"), (25, "Brantley"), (27, "Brooks"), (29, "Bryan"),
    (31, "Bulloch"), (33, "Burke"), (35, "Butts"), (37, "Calhoun"), (39, "Camden"),
    (43, "Candler"), (45, "Carroll"), (47, "Catoosa"), (49, "Charlton"), (51, "Chatham"),
    (53, "Chattahoochee"), (55, "Chattooga"), (57, "Cherokee"), (59, "Clarke"), (61, "Clay"),
    (63, "Clayton"), (65, "Clinch"), (67, "Cobb"), (69, "Coffee"), (71, "Colquitt"),
    (73, "Columbia"), (75, "Cook"), (77, "Coweta"), (79, "Crawford"), (81, "Crisp"),
    (83, "Dade"), (85, "Dawson"), (87, "Decatur"), (89, "DeKalb"), (91, "Dodge"),
    (93, "Dooly"), (95, "Dougherty"), (97, "Douglas"), (99, "Early"), (101, "Echols"),
    (103, "Effingham"), (105, "Elbert"), (107, "Emanuel"), (109, "Evans"), (111, "Fannin"),
    (113, "Fayette"), (115, "Floyd"), (117, "Forsyth"), (119, "Franklin"), (121, "Fulton"),
    (123, "Gilmer"), (125, "Glascock"), (127, "Glynn"), (129, "Gordon"), (131, "Grady"),
    (133, "Greene"), (135, "Gwinnett"), (137, "Habersham"), (139, "Hall"), (141, "Hancock"),
    (143, "Haralson"), (145, "Harris"), (147, "Hart"), (149, "Heard"), (151, "Henry"),
    (153, "Houston"), (155, "Irwin"), (157, "Jackson"), (159, "Jasper"), (161, "Jeff Davis"),
    (163, "Jefferson"), (165, "Jenkins"), (167, "Johnson"), (169, "Jones"), (171, "Lamar"),
    (173, "Lanier"), (175, "Laurens"), (177, "Lee"), (179, "Liberty"), (181, "Lincoln"),
    (183, "Long"), (185, "Lowndes"), (187, "Lumpkin"), (189, "McDuffie"), (191, "McIntosh"),
    (193, "Macon"), (195, "Madison"), (197, "Marion"), (199, "Meriwether"), (201, "Miller"),
    (205, "Mitchell"), (207, "Monroe"), (209, "Montgomery"), (211, "Morgan"), (213, "Murray"),
    (215, "Muscogee"), (217, "Newton"), (219, "Oconee"), (221, "Oglethorpe"), (223, "Paulding"),
    (225, "Peach"), (227, "Pickens"), (229, "Pierce"), (231, "Pike"), (233, "Polk"),
    (235, "Pulaski"), (237, "Putnam"), (239, "Quitman"), (241, "Rabun"), (243, "Randolph"),
    (245, "Richmond"), (247, "Rockdale"), (249, "Schley"), (251, "Screven"), (253, "Seminole"),
    (255, "Spalding"), (257, "Stephens"), (259, "Stewart"), (261, "Sumter"), (263, "Talbot"),
    (265, "Taliaferro"), (267, "Tattnall"), (269, "Taylor"), (271, "Telfair"), (273, "Terrell"),
    (275, "Thomas"), (277, "Tift"), (279, "Toombs"), (281, "Towns"), (283, "Treutlen"),
    (285, "Troup"), (287, "Turner"), (289, "Twiggs"), (291, "Union"), (293, "Upson"),
]

# National ZCTA-County file (tab-delimited); we filter for GEOID_COUNTY_20 starting with "13"
CENSUS_ZCTA_COUNTY_URL = "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt"
CENSUS_LOCAL_PATH = DATA_DIR / "tab20_zcta520_county20_natl.txt"
OUTPUT_PATH = DATA_DIR / "zip_county_ga.csv"


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    fips_to_county = {f"13{str(c).zfill(3)}": name for c, name in GA_FIPS_TO_COUNTY}

    if not CENSUS_LOCAL_PATH.exists():
        print("Downloading Census ZCTA-County national file...")
        try:
            urllib.request.urlretrieve(CENSUS_ZCTA_COUNTY_URL, CENSUS_LOCAL_PATH)
        except Exception as e:
            print(f"Download failed: {e}")
            print("Download manually and save as:", CENSUS_LOCAL_PATH)
            print("URL:", CENSUS_ZCTA_COUNTY_URL)
            return

    # Pipe-delimited; columns include GEOID_ZCTA5_20, GEOID_COUNTY_20, NAMELSAD_COUNTY_20
    df = pd.read_csv(CENSUS_LOCAL_PATH, dtype=str, sep="|")
    # Filter for Georgia (county GEOID starts with 13)
    geoid_county = "GEOID_COUNTY_20" if "GEOID_COUNTY_20" in df.columns else [c for c in df.columns if "county" in c.lower() and "geoid" in c.lower()][0]
    df = df[df[geoid_county].astype(str).str.strip().str.startswith("13")].copy()

    zip_col = "GEOID_ZCTA5_20" if "GEOID_ZCTA5_20" in df.columns else [c for c in df.columns if "zcta" in c.lower() and "geoid" in c.lower()][0]
    name_col = None
    if "NAMELSAD_COUNTY_20" in df.columns:
        name_col = "NAMELSAD_COUNTY_20"
    elif any("namelsad" in c.lower() for c in df.columns):
        name_col = [c for c in df.columns if "namelsad" in c.lower() and "county" in c.lower()][0]

    if name_col:
        df["county"] = df[name_col].astype(str).str.strip().str.replace(r"\s+County\s*$", "", regex=True, case=False)
    else:
        df["county"] = df[geoid_county].astype(str).str.strip().map(fips_to_county)
    df = df.dropna(subset=["county"])
    out = df[[zip_col, "county"]].drop_duplicates()
    out = out.rename(columns={zip_col: "zip"})
    out["zip"] = out["zip"].astype(str).str.strip()
    out.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(out)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
