"""
Step 5b - Apply the QC rules and ComBat-harmonise the volumes for the lifespan models (H1-H4).

For each analysis variant, the QC rules pick the scans and volumes, then ComBat removes
scanner (site) differences while preserving age, age squared, sex and head size
(Fortin et al., 2018). ComBat is refitted for every variant, because each uses a different
set of scans.

Variants (pre-registration "Sensitivity analyses" and README "Quality-control decisions"):
  primary       whole-brain 2 excluded; subcortical 2 -> subcortical volumes missing
  exclude_1s    scans rated 1 excluded as well (whole-brain >= 1 excluded; subcortical >= 1 missing)
  no_iop        primary, without the IOP site
  include_wb2   whole-brain 2 kept (subcortical rule unchanged)                      [README (a)]
  first_pass    exclusions from the first-pass ratings instead of the reviewed ones  [README (b)]
"Without ComBat" and "raw volumes" sensitivity analyses use the unharmonised columns, so
they need no extra rows here.

Whole-brain volumes (gm, wm, csf) are harmonised on all included scans; the 15 FIRST
volumes on included scans that have all 15 (complete cases).

Run from the project folder:
  ~/brainenv/bin/python scripts/10_harmonise.py --shuffled   # blind analysis
  ~/brainenv/bin/python scripts/10_harmonise.py              # real data, after unblinding
Output: data/analysis_<shuffled|dataset>_harmonised.csv - one row per scan per variant,
with raw volumes and harmonised copies (suffix _h).
"""

from pathlib import Path
import contextlib
import io
import sys
import warnings

import numpy as np
import pandas as pd
from neuroCombat import neuroCombat

PROJECT = Path(__file__).resolve().parent.parent
DATA = PROJECT / "data"
SHUFFLED = "--shuffled" in sys.argv
STEM = "analysis_shuffled" if SHUFFLED else "analysis_dataset"

SUB = ["L_Thal", "L_Caud", "L_Puta", "L_Pall", "L_Hipp", "L_Amyg", "L_Accu",
       "R_Thal", "R_Caud", "R_Puta", "R_Pall", "R_Hipp", "R_Amyg", "R_Accu", "BrStem"]
WHOLE = ["gm", "wm", "csf"]


def apply_qc(d, variant):
    """Return the scans and volumes used by one analysis variant."""
    d = d.copy()
    wb, sc = d["qc_wb"], d["qc_sc"]
    if variant == "first_pass":
        wb, sc = d["qc_wb_first"], d["qc_sc_first"]
    wb_limit = 1 if variant == "exclude_1s" else 2          # exclude ratings >= this
    sc_limit = 1 if variant == "exclude_1s" else 2
    if variant != "include_wb2":
        d = d[~(wb >= wb_limit)]
    d.loc[sc.loc[d.index] >= sc_limit, SUB] = np.nan
    if variant == "no_iop":
        d = d[d["site"] != "IOP"]
    return d


def combat(d, cols):
    """ComBat on the rows of d with all of cols present; returns harmonised values (same index)."""
    ok = d[cols].notna().all(axis=1)
    sub = d[ok]
    covars = pd.DataFrame({"site": sub["site"].to_numpy(), "sex": sub["sex"].to_numpy(),
                           "age": sub["age"].to_numpy(), "age2": sub["age"].to_numpy() ** 2,
                           "icv": sub["icv"].to_numpy()})
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):   # quiet
        warnings.simplefilter("ignore")
        res = neuroCombat(dat=sub[cols].to_numpy().T, covars=covars, batch_col="site",
                          categorical_cols=["sex"], continuous_cols=["age", "age2", "icv"])
    out = pd.DataFrame(np.nan, index=d.index, columns=[c + "_h" for c in cols])
    out.loc[ok, :] = res["data"].T
    return out


data_file = DATA / f"{STEM}.csv"
if not data_file.exists():
    sys.exit(f"{data_file.relative_to(PROJECT)} not found. Run scripts/09_build_dataset.py "
             f"{'--shuffled ' if SHUFFLED else ''}first.")
d = pd.read_csv(data_file)
if d["shuffled"].iloc[0] != SHUFFLED:
    sys.exit("The dataset's 'shuffled' flag doesn't match the --shuffled option.")

parts = []
print(f"{'BLIND ANALYSIS (shuffled data)' if SHUFFLED else 'REAL DATA'} - ComBat per variant")
print(f"{'variant':12s} {'scans':>5s} {'whole-brain':>11s} {'subcortical':>11s}  sites")
for variant in ["primary", "exclude_1s", "no_iop", "include_wb2", "first_pass"]:
    v = apply_qc(d, variant)
    h = pd.concat([combat(v, WHOLE), combat(v, SUB)], axis=1)
    v = pd.concat([v, h], axis=1)
    v.insert(0, "variant", variant)
    parts.append(v)
    print(f"{variant:12s} {len(v):5d} {v[WHOLE[0] + '_h'].notna().sum():11d} "
          f"{v[SUB[0] + '_h'].notna().sum():11d}  "
          + ", ".join(f"{s} {n}" for s, n in v["site"].value_counts().sort_index().items()))

out = DATA / f"{STEM}_harmonised.csv"
pd.concat(parts).to_csv(out, index=False, lineterminator="\n")
print(f"Saved {out.relative_to(PROJECT)}")

# Check that ComBat did its job: site means of grey matter (raw vs harmonised), primary variant.
# After harmonisation the site means should be almost identical. (On shuffled data the raw
# site means are meaningless too, because site labels are shuffled.)
p = parts[0]
print("\nCheck: grey matter site means, primary variant (cm3)")
print((p.groupby("site")[["gm", "gm_h"]].mean() / 1000).round(1).to_string())
