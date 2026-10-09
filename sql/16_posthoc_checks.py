"""
Step 10 - Post-hoc checks (added after seeing the real results; not pre-registered).

1. Mean vs median baseline for H5. The brain age models are judged on mean absolute error
   (MAE). The best single constant guess for MAE is the median age, not the mean, so a
   median-age baseline is the stricter comparison. This prints both, on the primary
   analysis scans, using the whole sample (an upper bound on how good either guess can be).
2. Is the sex difference in brain age gap a head-size effect? The model's features are
   volumes divided by intracranial volume (ICV), and men have larger ICV. This refits the
   exploratory gap model with ICV added as a covariate.

Usage, from the project folder (after scripts/12_brain_age.py, real data):
  ~/brainenv/bin/python scripts/16_posthoc_checks.py
Output: results/real/posthoc_checks.txt (also printed)
"""

from pathlib import Path

import pandas as pd
import statsmodels.formula.api as smf

PROJECT = Path(__file__).resolve().parent.parent
OUT = PROJECT / "results" / "real"
pred = pd.read_csv(OUT / "brainage_predictions.csv")
data = pd.read_csv(PROJECT / "data" / "analysis_dataset.csv")[["subject", "icv"]]
pred = pred.merge(data, on="subject", how="left")
pred["icv_l"] = pred["icv"] / 1e6

lines = ["POST-HOC CHECKS (not pre-registered)", ""]
age = pred["age"]
lines += ["1. Constant-guess baselines on the primary analysis scans "
          f"(n = {len(age)})",
          f"   mean age   {age.mean():5.1f} -> MAE {(age - age.mean()).abs().mean():.2f} years",
          f"   median age {age.median():5.1f} -> MAE {(age - age.median()).abs().mean():.2f} years", ""]

lines += ["2. Brain age gap (bias-corrected) and sex, with and without intracranial volume",
          "   mean ICV (litres): " + ", ".join(f"{k} {v:.3f}" for k, v in
                                               pred.groupby("sex")["icv_l"].mean().items())]
for f in ["gap_corrected ~ age + sex + site", "gap_corrected ~ age + sex + site + icv_l"]:
    m = smf.ols(f, pred).fit()
    lines.append(f"   {f}")
    for term in ["sex[T.male]", "icv_l"]:
        if term in m.params:
            lo, hi = m.conf_int().loc[term]
            lines.append(f"      {term:12s} {m.params[term]:+6.2f} years  (95% CI {lo:+.2f} to {hi:+.2f}, "
                         f"p = {m.pvalues[term]:.3g})")
report = "\n".join(lines) + "\n"
(OUT / "posthoc_checks.txt").write_text(report)
print(report)
