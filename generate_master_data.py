import json
import pandas as pd
import os

def create_master_json():
    # 1. Exact file names from your workspace
    risk_file = 'risk_factor_by_county_with_level1.csv'
    hospital_file = 'ob_hospitals_with_level.csv'
    
    print(f"--- Starting Data Sync ---")

    # Check if files exist
    if not os.path.exists(risk_file) or not os.path.exists(hospital_file):
        print(f"ERROR: Missing files.")
        print(f"Ensure '{risk_file}' and '{hospital_file}' are in the folder.")
        return

    try:
        # LOAD RISK DATA
        # Rename 'level' to 'risk_level' because it refers to the severity (Very High, etc.)
        risk_df = pd.read_csv(risk_file)
        risk_df = risk_df.rename(columns={'level': 'risk_level'})
        
        # LOAD HOSPITAL DATA
        hosp_df = pd.read_csv(hospital_file)
        
        # Get the MAX Level of Care per county (Highest facility capability)
        hosp_df['level'] = pd.to_numeric(hosp_df['level'], errors='coerce')
        facility_summary = hosp_df.groupby('county')['level'].max().reset_index()
        facility_summary = facility_summary.rename(columns={'level': 'care_level'})
        
        # Sum all OB Beds in the county
        beds_summary = hosp_df.groupby('county')['Number of OB Beds'].sum().reset_index()
        
        # MERGE
        df = pd.merge(risk_df, facility_summary, on='county', how='left')
        df = pd.merge(df, beds_summary, on='county', how='left')
        
        # Fill missing values
        df['care_level'] = df['care_level'].fillna(0).astype(int)
        df['Number of OB Beds'] = df['Number of OB Beds'].fillna(0).astype(int)
        
    except Exception as e:
        print(f"Error merging data: {e}")
        return

    master_list = []

    for _, row in df.iterrows():
        # Bed logic: use hospital file sum, fallback to risk file
        beds = int(row['Number of OB Beds']) if row['Number of OB Beds'] > 0 else int(row['ob_beds'])
        
        score = row['risk_factor']

        master_list.append({
            "county": row['county'],
            "risk_score": round(float(score), 2),
            "metrics": {
                "prenatal_risk": row['pct_late_no_prenatal_care'],
                "birth_share": row['pct_births_in_state'],
                "total_beds": beds,
                "risk_level": row['risk_level'],
                "care_level": int(row['care_level']),
                "distance": row['avg_distance_miles']
            }
        })

    with open('maternal_risk_master.json', 'w') as f:
        json.dump(master_list, f, indent=4)
    
    print(f"Success! 'maternal_risk_master.json' is generated.")

if __name__ == "__main__":
    create_master_json()