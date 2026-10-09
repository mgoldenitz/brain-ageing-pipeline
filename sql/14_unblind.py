"""
Step 4e - Unblind the visual QC ratings (run once, after the retest).

What it does:
  1. Checks that the main, first-pass and retest rating files are complete, and that at
     least a week has passed since the main rating (pre-registration: retest "at least one
     week later"; main rating finished 2026-10-06).
  2. Uses data/qc_key.csv to link every code to its subject - the first time the ratings
     are seen next to subject IDs.
  3. Writes data/qc_final.csv (subject, qc_wb, qc_sc, qc_wb_first, qc_sc_first, qc_note),
     the file scripts/09_build_dataset.py needs for the real analysis.
  4. Reports rating reliability: retest vs main ratings (and vs first-pass ratings), and
     practice vs main, as Cohen's kappa (unweighted and linearly weighted, since 0/1/2 is
     ordered), percentage agreement, and agreement on fail (2) vs keep (0/1).
  5. Reports what the pre-registration asks for: exclusions at each rule, by site.
  6. Compares the visual ratings with the automatic checks: the automatic QC flags,
     image quality (CNR, SNR, robust z within site), brainstem and pallidum volume outliers,
     and the head-size mismatch scans.

Usage, from the project folder, inside WSL:
  ~/brainenv/bin/python scripts/14_unblind.py
Output: data/qc_final.csv and results/real/qc_report.txt (also printed).
"""

from datetime import date
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score

PROJECT = Path(__file__).resolve().parent.parent
DATA = PROJECT / "data"
OUT = PROJECT / "results" / "real"
EARLIEST = date(2026, 10, 13)          # one week after the main rating finished
FORCE = "--force" in sys.argv
SUB = ["L_Thal", "L_Caud", "L_Puta", "L_Pall", "L_Hipp", "L_Amyg", "L_Accu",
       "R_Thal", "R_Caud", "R_Puta", "R_Pall", "R_Hipp", "R_Amyg", "R_Accu", "BrStem"]


def read_ratings(name):
    r = pd.read_csv(DATA / name, dtype=str, encoding="utf-8-sig").fillna("")
    r = r.apply(lambda c: c.str.strip())
    for c in ["whole_brain_rating", "subcortical_rating"]:
        r[c] = pd.to_numeric(r[c], errors="coerce")
    return r


def robust_z(x):
    med = x.median()
    mad = (x - med).abs().median() * 1.4826
    return (x - med) / mad


# ---- 1. Checks ----------------------------------------------------------------------------
if date.today() < EARLIEST and not FORCE:
    sys.exit(f"Too early: the retest must be at least a week after the main rating "
             f"(on or after {EARLIEST}). Nothing was unblinded.")
if (DATA / "qc_final.csv").exists() and not FORCE:
    sys.exit("data/qc_final.csv already exists - the ratings have been unblinded already. Nothing changed.")

main = read_ratings("qc_ratings.csv")
first = read_ratings("qc_ratings_firstpass.csv")
retest = read_ratings("qc_ratings_retest.csv")
practice = read_ratings("qc_ratings_practice.csv")
for name, r in [("main", main), ("retest", retest)]:
    missing = r[r[["whole_brain_rating", "subcortical_rating"]].isna().any(axis=1)]
    if len(missing):
        sys.exit(f"{len(missing)} scans in the {name} ratings are not rated yet "
                 f"(first code: {missing['code'].iloc[0]}). Finish rating before unblinding.")

# ---- 2. Link codes to subjects ----------------------------------------------------------------
key = pd.read_csv(DATA / "qc_key.csv", dtype=str).apply(lambda c: c.str.strip())


def with_subject(r, set_name):
    k = key[key["set"] == set_name][["code", "subject"]]
    out = r.merge(k, on="code", how="left")
    if out["subject"].isna().any():
        sys.exit(f"Some {set_name} codes are not in the key - check the rating files.")
    return out


main_s = with_subject(main, "main")
first_s = with_subject(first, "main")
retest_s = with_subject(retest, "retest")
practice_s = with_subject(practice, "practice")

# ---- 3. qc_final.csv --------------------------------------------------------------------------
final = (main_s[["subject", "whole_brain_rating", "subcortical_rating", "note"]]
         .rename(columns={"whole_brain_rating": "qc_wb", "subcortical_rating": "qc_sc", "note": "qc_note"})
         .merge(first_s[["subject", "whole_brain_rating", "subcortical_rating"]]
                .rename(columns={"whole_brain_rating": "qc_wb_first", "subcortical_rating": "qc_sc_first"}),
                on="subject", how="left"))
final.to_csv(DATA / "qc_final.csv", index=False, lineterminator="\n")

# ---- 4. Reliability ---------------------------------------------------------------------------
lines = ["VISUAL QC - UNBLINDED REPORT", f"Run on {date.today()}", ""]


def agreement(a, b, label):
    rows = []
    for col, name in [("whole_brain_rating", "whole-brain"), ("subcortical_rating", "subcortical")]:
        m = a[["subject", col]].merge(b[["subject", col]], on="subject", suffixes=("_a", "_b")).dropna()
        x, y = m[col + "_a"].astype(int), m[col + "_b"].astype(int)
        same_cat = len(set(x) | set(y)) > 1
        rows.append(dict(
            comparison=label, rating=name, n=len(m),
            agreement=round((x == y).mean(), 3),
            kappa=round(cohen_kappa_score(x, y), 3) if same_cat else np.nan,
            kappa_weighted=round(cohen_kappa_score(x, y, weights="linear"), 3) if same_cat else np.nan,
            fail_agreement=round(((x == 2) == (y == 2)).mean(), 3),
            fails_a=int((x == 2).sum()), fails_b=int((y == 2).sum())))
    return rows


rel = pd.DataFrame(agreement(retest_s, main_s, "retest vs main (reviewed)")
                   + agreement(retest_s, first_s, "retest vs first pass")
                   + agreement(practice_s, main_s, "practice vs main"))
OUT.mkdir(parents=True, exist_ok=True)
rel.to_csv(OUT / "qc_reliability.csv", index=False)
lines += ["1. RATING RELIABILITY (Cohen's kappa; weighted = linear weights for the ordered 0/1/2 scale)",
          rel.to_string(index=False),
          "   Rough guide (Landis & Koch): 0.41-0.60 moderate, 0.61-0.80 substantial, > 0.80 almost perfect.", ""]

# ---- 5. Exclusions by site --------------------------------------------------------------------
part = pd.read_csv(DATA / "participants.csv")[["subject", "site", "sex", "age"]]
q = final.merge(part, on="subject", how="left")
excl = pd.DataFrame({
    "scans": q.groupby("site").size(),
    "rule 1: whole-brain 2 (excluded)": q[q.qc_wb == 2].groupby("site").size(),
    "rule 3: subcortical 2 (subcortical missing)": q[q.qc_sc == 2].groupby("site").size(),
    "rated 1 (kept)": q[(q.qc_wb == 1) | (q.qc_sc == 1)].groupby("site").size(),
    "first pass: whole-brain 2": q[q.qc_wb_first == 2].groupby("site").size(),
}).fillna(0).astype(int)
excl.loc["Total"] = excl.sum()
lines += ["2. EXCLUSIONS BY SITE (pre-registration, exclusion rules)", excl.to_string(), ""]

# ---- 6. Visual ratings vs automatic checks ------------------------------------------------------
auto = pd.read_csv(DATA / "qc_auto.csv")[["subject", "qc_auto", "qc_reasons"]]
q = q.merge(auto, on="subject", how="left")
lines += ["3. AUTOMATIC QC FLAGS vs VISUAL RATINGS",
          "Whole-brain rating:", pd.crosstab(q.qc_auto, q.qc_wb, margins=True).to_string(),
          "Subcortical rating:", pd.crosstab(q.qc_auto, q.qc_sc, margins=True).to_string(), ""]

iq = pd.read_csv(DATA / "image_quality.csv")[["subject", "cnr", "snr"]]
q = q.merge(iq, on="subject", how="left")
q["cnr_z"] = q.groupby("site")["cnr"].transform(robust_z)
q["snr_z"] = q.groupby("site")["snr"].transform(robust_z)
lines += ["4. IMAGE QUALITY BY WHOLE-BRAIN RATING (robust z within site; lower = worse)",
          q.groupby("qc_wb")[["cnr_z", "snr_z"]].agg(["median", "count"]).round(2).to_string(),
          "Low-quality scans (CNR or SNR z < -3.5):",
          q[(q.cnr_z < -3.5) | (q.snr_z < -3.5)][["subject", "site", "cnr_z", "snr_z", "qc_wb", "qc_sc"]]
          .round(2).to_string(index=False), ""]

vols = pd.read_csv(DATA / "volumes.csv").rename(columns=lambda c: c[:-4] if c.endswith("_mm3") else c)
rerun = pd.read_csv(DATA / "volumes_first_rerun.csv").rename(columns=lambda c: c[:-4] if c.endswith("_mm3") else c)
vols = vols.set_index("subject")
rerun = rerun.set_index("subject")
vols.loc[rerun.index, SUB] = rerun[SUB]
v = vols[SUB].reset_index().merge(q[["subject", "qc_sc", "qc_note"]], on="subject")
outl = []
for s in SUB:
    z = robust_z(v[s])
    for _, r in v[z.abs() > 5].iterrows():
        outl.append(dict(subject=r.subject, structure=s, volume_cm3=round(r[s] / 1000, 2),
                         robust_z=round(z[_], 1), qc_sc=r.qc_sc, note=r.qc_note))
outl = pd.DataFrame(outl)
lines += ["5. EXTREME SUBCORTICAL VOLUMES (robust z beyond +/-5) and their subcortical rating",
          outl.to_string(index=False) if len(outl) else "None.",
          "   Any with qc_sc < 2 may be missed FIRST failures - look at them before running the analysis.", ""]

watch = ["IXI150-HH-1550", "IXI234-IOP-0870", "IXI563-IOP-1153"]
lines += ["6. HEAD-SIZE MISMATCH SCANS (FAST total about 18% above the SIENAX estimate)",
          q[q.subject.isin(watch)][["subject", "qc_wb", "qc_sc", "qc_note"]].to_string(index=False), ""]

lines += ["NEXT: build the real dataset and run the analysis, in order:",
          "  ~/brainenv/bin/python scripts/09_build_dataset.py",
          "  ~/brainenv/bin/python scripts/10_harmonise.py",
          "  Rscript scripts/11_lifespan_gams.R",
          "  nohup ~/brainenv/bin/python scripts/12_brain_age.py > logs/brainage_real.out 2>&1 &",
          "  ~/brainenv/bin/python scripts/13_sample_size.py"]
report = "\n".join(lines) + "\n"
(OUT / "qc_report.txt").write_text(report)
print(report)
print("Saved data/qc_final.csv, results/real/qc_report.txt and results/real/qc_reliability.csv")
