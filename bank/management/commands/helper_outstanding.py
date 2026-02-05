import pandas as pd
import sys
import os
date = int(sys.argv[2]) - 1
party = sys.argv[3]
df = pd.read_pickle(os.path.join("simulator","devaki_hul",f"2026-01-{date:02d} 00:00:00.pkl"))
df = df[df["Party Name"].str.lower().str.contains(party.lower(),na=False)]
df = df[["Bill Number","O/S Amount","In Days"]].sort_values("In Days",ascending=False)
print(df)
exit(0)