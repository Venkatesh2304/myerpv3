import pickle
import os
import pandas as pd
import numpy as np
import datetime

company_name = 'lakme_urban'
dates = [datetime.date(2026, 1, i) for i in range(1, 32)]
stock_id = 'PDLZ101'
cache_dir = f'.temp/stock_analysis/{company_name}'

all_records = []
for date in dates:
    path = os.path.join(cache_dir, f"{date}.pkl")
    if os.path.exists(path):
        with open(path, 'rb') as f:
            df = pickle.load(f)
            # SKU7, Units, Location
            df = df.rename(columns={"SKU7": "stock_id", "Units": "qty", "Location": "godown"})
            # No godown filter
            df = df[df["stock_id"].astype(str).str.strip() == stock_id]
            qty_sum = pd.to_numeric(df["qty"], errors='coerce').sum()
            all_records.append({"date": date, "qty": qty_sum})
    else:
        all_records.append({"date": date, "qty": 0})

df_res = pd.DataFrame(all_records)
qtys = df_res['qty'].values.astype(float)

print(f"Stats for {stock_id} across ALL godowns (Jan 1 - Jan 31):")
print(f"Mean: {np.mean(qtys):.2f}")
print(f"Std Dev: {np.std(qtys):.2f}")
print(f"Min: {np.min(qtys):.2f}")
print(f"Max: {np.max(qtys):.2f}")
print("\nDaily Breakdown:")
print(df_res)
