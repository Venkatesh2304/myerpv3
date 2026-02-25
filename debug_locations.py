import pickle
import os
import pandas as pd

cache_dir = '.temp/stock_analysis/lakme_urban'
file = '2026-01-01.pkl'
path = os.path.join(cache_dir, file)

with open(path, 'rb') as f:
    df = pickle.load(f)
    print(f"Total rows: {len(df)}")
    if 'Location' in df.columns:
        print("Unique Locations:", df['Location'].unique().tolist())
        main_godown = df[df['Location'].astype(str).str.upper() == 'MAIN GODOWN']
        print(f"Rows in MAIN GODOWN: {len(main_godown)}")
        if not main_godown.empty:
            print("Sample in MAIN GODOWN:", main_godown.iloc[0]['SKU7'] if 'SKU7' in main_godown.columns else "No SKU7")
    else:
        print("Location column not found")
