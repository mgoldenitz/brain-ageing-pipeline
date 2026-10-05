"""
Step 1 - Check the IXI demographics and pick the pilot sample.

Reads IXI.xls and the list of T1 files, then writes:
  data/participants.csv    one row per T1 scan, with age, sex and hospital
  data/pilot_subjects.txt  20 scans spread across the 3 hospitals and the age range
and prints a short summary to check before processing.

Run from the project folder:  python3 scripts/01_check_demographics.py
"""

from pathlib import Path
import re
import sys

import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
RAW = Path.home() / "ixi" / "raw"          # where the T1 files and IXI.xls live (inside WSL)
OUT = PROJECT / "data"
OUT.mkdir(exist_ok=True)
PILOT_N = 20

# ---- 1. T1 files: IXI002-Guys-0828-T1.nii.gz -> id 2, site Guys
files = sorted(RAW.glob("IXI*-T1.nii.gz"))
if not files:
    sys.exit(f"No T1 files found in {RAW}. Check the download and unpack step.")

pattern = re.compile(r"IXI(\d{3})-([A-Za-z]+)-(\d+)-T1\.nii\.gz")
rows = []
for f in files:
    m = pattern.match(f.name)
    if m:
        rows.append({"subject": f.name.replace("-T1.nii.gz", ""),
                     "ixi_id": int(m.group(1)), "site": m.group(2), "file": f.name})
scans = pd.DataFrame(rows)
print(f"T1 files found: {len(files)}  (parsed: {len(scans)})")

# ---- 2. Demographics spreadsheet
demo = pd.read_excel(RAW / "IXI.xls")
print("\nColumns in IXI.xls:", list(demo.columns))
demo = demo.rename(columns=lambda c: str(c).strip().upper())
# Match columns by how their names start, e.g. "SEX_ID (1=m, 2=f)"
def col(prefix):
    return next(c for c in demo.columns if c.startswith(prefix))
demo = demo[[col("IXI_ID"), col("SEX_ID"), col("AGE")]]
demo.columns = ["ixi_id", "sex_id", "age"]
demo = demo.drop_duplicates("ixi_id")
# The spreadsheet's own column name confirms SEX_ID 1 = male and 2 = female.
demo["sex"] = demo["sex_id"].map({1: "male", 2: "female"})

df = scans.merge(demo, on="ixi_id", how="left")
df["age"] = pd.to_numeric(df["age"], errors="coerce").round(1)

# ---- 3. Summary to check
print(f"\nScans with no age: {df['age'].isna().sum()} of {len(df)}")
print("\nScans per hospital:\n", df["site"].value_counts().to_string())
print("\nSex:\n", df["sex"].value_counts(dropna=False).to_string())
print("\nAge range:", df["age"].min(), "to", df["age"].max(), "| median", df["age"].median())
print("\nScans per age decade:\n",
      pd.cut(df["age"], range(10, 100, 10), right=False).value_counts().sort_index().to_string())

df.to_csv(OUT / "participants.csv", index=False)

# ---- 4. Pilot: 20 scans with an age, spread across hospitals and ages
usable = df.dropna(subset=["age", "sex"]).copy()
usable["age_band"] = pd.qcut(usable["age"], 4, labels=False, duplicates="drop")
pilot = usable.sample(frac=1, random_state=42).groupby(["site", "age_band"]).head(2)
if len(pilot) < PILOT_N:
    extra = usable.drop(pilot.index).sample(PILOT_N - len(pilot), random_state=42)
    pilot = pd.concat([pilot, extra])
pilot = pilot.sample(min(PILOT_N, len(pilot)), random_state=42).sort_values("ixi_id")
(OUT / "pilot_subjects.txt").write_text("\n".join(pilot["subject"]) + "\n")

print(f"\nPilot sample ({len(pilot)} scans) saved to data/pilot_subjects.txt")
print(pilot[["subject", "site", "sex", "age"]].to_string(index=False))
