"""
Step 5a - Build the analysis dataset: one row per scan with demographics, volumes,
head size, image quality and QC ratings.

Two modes:
  python3 scripts/09_build_dataset.py --shuffled
      BLIND ANALYSIS (before unblinding). Age, sex and site are shuffled together between
      participants and the QC ratings are shuffled between scans, so no result computed
      from this file means anything. Used to write and test the analysis code.
      -> data/analysis_shuffled.csv

  python3 scripts/09_build_dataset.py
      REAL DATA (after unblinding). Needs data/qc_final.csv (subject, qc_wb, qc_sc,
      qc_wb_first, qc_sc_first), which is made when the ratings are unblinded.
      -> data/analysis_dataset.csv

Volume rules:
  * Subcortical volumes come from the brain-extracted FIRST rerun where one exists
    (data/volumes_first_rerun.csv), because that is the segmentation that was rated.
  * Rows are never dropped here. The analysis scripts apply the exclusion rules using the
    QC columns (pre-registration, exclusion rules 1 and 3), so every sensitivity analysis
    starts from the same file.

Columns: subject, site, sex, age, icv, cnr, snr, gm, wm, csf, the 15 FIRST structures,
first_source (rerun / original), qc_wb, qc_sc, qc_wb_first, qc_sc_first, shuffled.
"""

from pathlib import Path
import sys

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
DATA = PROJECT / "data"
SHUFFLED = "--shuffled" in sys.argv
SEED = 20261006

SUB = ["L_Thal", "L_Caud", "L_Puta", "L_Pall", "L_Hipp", "L_Amyg", "L_Accu",
       "R_Thal", "R_Caud", "R_Puta", "R_Pall", "R_Hipp", "R_Amyg", "R_Accu", "BrStem"]
WHOLE = ["gm", "wm", "csf"]


def strip_mm3(df):
    return df.rename(columns=lambda c: c[:-4] if c.endswith("_mm3") else c)


subjects = [s.strip() for s in (DATA / "all_subjects.txt").read_text().splitlines() if s.strip()]
part = pd.read_csv(DATA / "participants.csv")[["subject", "site", "sex", "age"]]
vols = strip_mm3(pd.read_csv(DATA / "volumes.csv"))
rerun = strip_mm3(pd.read_csv(DATA / "volumes_first_rerun.csv"))
head = pd.read_csv(DATA / "head_size.csv")[["subject", "icv_mm3"]].rename(columns={"icv_mm3": "icv"})
iq = pd.read_csv(DATA / "image_quality.csv")[["subject", "cnr", "snr"]]

# Subcortical volumes from the rerun where available
vols["first_source"] = "original"
rr = rerun.set_index("subject")
mask = vols["subject"].isin(rr.index)
vols.loc[mask, SUB] = rr.loc[vols.loc[mask, "subject"], SUB].to_numpy()
vols.loc[mask, "first_source"] = "rerun"

d = (pd.DataFrame({"subject": subjects})
     .merge(part, on="subject", how="left")
     .merge(head, on="subject", how="left")
     .merge(iq, on="subject", how="left")
     .merge(vols[["subject"] + WHOLE + SUB + ["first_source"]], on="subject", how="left"))

if SHUFFLED:
    rng = np.random.default_rng(SEED)
    # Age, sex and site move together, so their mix stays realistic (e.g. each site's age range)
    # but none of them is linked to the brain measures any more
    perm = rng.permutation(len(d))
    d[["age", "sex", "site"]] = d[["age", "sex", "site"]].to_numpy()[perm]
    # QC ratings: the real set of (current, first-pass) rating pairs, dealt to random scans.
    # Uses only the coded rating files, never the key.
    cur = pd.read_csv(DATA / "qc_ratings.csv", dtype=str).fillna("")
    first = pd.read_csv(DATA / "qc_ratings_firstpass.csv", dtype=str).fillna("")
    pairs = cur.merge(first, on="code", suffixes=("", "_first"))
    pairs = pairs.iloc[rng.permutation(len(pairs))].reset_index(drop=True)
    d["qc_wb"] = pd.to_numeric(pairs["whole_brain_rating"], errors="coerce").to_numpy()
    d["qc_sc"] = pd.to_numeric(pairs["subcortical_rating"], errors="coerce").to_numpy()
    d["qc_wb_first"] = pd.to_numeric(pairs["whole_brain_rating_first"], errors="coerce").to_numpy()
    d["qc_sc_first"] = pd.to_numeric(pairs["subcortical_rating_first"], errors="coerce").to_numpy()
    out = DATA / "analysis_shuffled.csv"
else:
    qc_file = DATA / "qc_final.csv"
    if not qc_file.exists():
        sys.exit("data/qc_final.csv not found: the real dataset can only be built after unblinding.\n"
                 "Before then, use:  python3 scripts/09_build_dataset.py --shuffled")
    qc = pd.read_csv(qc_file)
    d = d.merge(qc[["subject", "qc_wb", "qc_sc", "qc_wb_first", "qc_sc_first"]], on="subject", how="left")
    out = DATA / "analysis_dataset.csv"

d["shuffled"] = SHUFFLED
d.to_csv(out, index=False, lineterminator="\n")

# ---- Summary (counts only, no age-volume relationships)
print(f"{'BLIND ANALYSIS - age, sex, site and QC ratings are SHUFFLED' if SHUFFLED else 'REAL DATA'}")
print(f"Saved {out.relative_to(PROJECT)}: {len(d)} scans, {d.shape[1]} columns")
print(f"Subcortical volumes from the FIRST rerun: {(d.first_source == 'rerun').sum()} scans")
missing = d[["age", "sex", "site", "icv", "cnr"] + WHOLE + SUB + ["qc_wb", "qc_sc"]].isna().sum()
print("Missing values:", ", ".join(f"{k} {v}" for k, v in missing.items() if v) or "none")
tab = pd.DataFrame({
    "scans": d.groupby("site").size(),
    "whole-brain 2 (excluded)": d[d.qc_wb == 2].groupby("site").size(),
    "subcortical 2 (set missing)": d[d.qc_sc == 2].groupby("site").size(),
    "first-pass whole-brain 2": d[d.qc_wb_first == 2].groupby("site").size(),
}).fillna(0).astype(int)
tab.loc["Total"] = tab.sum()
print(tab.to_string())
