"""
Step 8 - Sample size (hypothesis H7): how often small studies detect the grey matter-age
effect, and how much they overestimate it when they do.

Following the pre-registration: 1,000 random samples (without replacement) at each of
n = 25, 50, 100, 200, 300 and 500 from the primary analysis set. In each, a linear model
  grey matter ~ age + sex + site + intracranial volume
is fitted (ComBat-harmonised grey matter, as in the main analysis), and the age coefficient
and its p-value are kept.

Reported for each n:
  detection_rate      share of samples with p < .05 for age (statistical power, in effect)
  median_coef_sig     median age coefficient among the significant samples (cm3/year)
  ratio_sig_to_full   that median divided by the full-sample age coefficient
                      (above 1 = significant small studies overestimate the effect:
                      the "winner's curse")
  sign_errors_sig     share of significant samples whose coefficient has the wrong sign

H7 decision (written before any real result): supported if
  (a) the detection rate rises with n (Spearman correlation between n and detection rate
      > 0, and the rate at n = 500 is higher than at n = 25), and
  (b) the ratio_sig_to_full is larger at n = 25 than at n = 500.

Usage, from the project folder (after scripts/10_harmonise.py):
  ~/brainenv/bin/python scripts/13_sample_size.py --shuffled   # blind analysis
  ~/brainenv/bin/python scripts/13_sample_size.py              # real data, after unblinding
Outputs in results/<shuffled|real>/: sample_size_draws.csv, sample_size_summary.csv,
sample_size_h7.csv, fig_sample_size.png
"""

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

PROJECT = Path(__file__).resolve().parent.parent
SHUFFLED = "--shuffled" in sys.argv
STEM = "analysis_shuffled" if SHUFFLED else "analysis_dataset"
OUT = PROJECT / "results" / ("shuffled" if SHUFFLED else "real")
OUT.mkdir(parents=True, exist_ok=True)
SIZES = [25, 50, 100, 200, 300, 500]
DRAWS = 1000
SEED = 42


def age_effect(X, y):
    """OLS age coefficient and two-sided p-value. Column 1 of X is age.
    Columns that are constant zero in this sample (a site with no scans) are dropped."""
    keep = np.any(X != 0, axis=0)
    X = X[:, keep]
    n, k = X.shape
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    df = n - k
    sigma2 = resid @ resid / df
    cov = sigma2 * np.linalg.pinv(X.T @ X)
    se = np.sqrt(cov[1, 1])
    t = beta[1] / se
    return beta[1], 2 * stats.t.sf(abs(t), df)


infile = PROJECT / "data" / f"{STEM}_harmonised.csv"
if not infile.exists():
    sys.exit(f"{infile.relative_to(PROJECT)} not found. Run scripts/09 and 10 "
             f"{'with --shuffled ' if SHUFFLED else ''}first.")
d = pd.read_csv(infile)
if bool(d["shuffled"].iloc[0]) != SHUFFLED:
    sys.exit("The dataset's 'shuffled' flag doesn't match the --shuffled option.")
d = d[d["variant"] == "primary"].dropna(subset=["gm_h", "age", "sex", "site", "icv"]).reset_index(drop=True)

# Design matrix: intercept, age, male, one dummy per non-reference site, ICV (litres)
sites = sorted(d["site"].unique())
X = np.column_stack([np.ones(len(d)), d["age"], (d["sex"] == "male").astype(float)]
                    + [(d["site"] == s).astype(float) for s in sites[1:]]
                    + [d["icv"] / 1e6])
y = d["gm_h"].to_numpy() / 1000                       # cm3
full_coef, full_p = age_effect(X, y)

rng = np.random.default_rng(SEED)
rows = []
for n in SIZES:
    if n > len(d):
        print(f"  n = {n} skipped: only {len(d)} scans")
        continue
    for draw in range(DRAWS):
        idx = rng.choice(len(d), size=n, replace=False)
        coef, p = age_effect(X[idx], y[idx])
        rows.append((n, draw, coef, p))
draws = pd.DataFrame(rows, columns=["n", "draw", "age_coef", "p"])
draws.to_csv(OUT / "sample_size_draws.csv", index=False)


def summarise(g):
    sig = g[g["p"] < 0.05]
    med = sig["age_coef"].median() if len(sig) else np.nan
    return pd.Series({
        "detection_rate": (g["p"] < 0.05).mean(),
        "n_significant": len(sig),
        "median_coef_all": g["age_coef"].median(),
        "median_coef_sig": med,
        "ratio_sig_to_full": med / full_coef if len(sig) else np.nan,
        "sign_errors_sig": (np.sign(sig["age_coef"]) != np.sign(full_coef)).mean() if len(sig) else np.nan,
        "coef_2.5%": g["age_coef"].quantile(0.025),
        "coef_97.5%": g["age_coef"].quantile(0.975),
    })


summary = draws.groupby("n")[["age_coef", "p"]].apply(summarise).reset_index()
summary.to_csv(OUT / "sample_size_summary.csv", index=False)

rho = stats.spearmanr(summary["n"], summary["detection_rate"]).correlation
r25, r500 = summary.set_index("n").loc[[25, 500], "ratio_sig_to_full"]
d25, d500 = summary.set_index("n").loc[[25, 500], "detection_rate"]
part_a = bool(rho > 0 and d500 > d25)
part_b = bool(np.isfinite(r25) and np.isfinite(r500) and r25 > r500)
h7 = pd.DataFrame([dict(full_sample_n=len(d), full_coef=full_coef, full_p=full_p,
                        spearman_n_detection=rho, detection_25=d25, detection_500=d500,
                        ratio_25=r25, ratio_500=r500, part_a=part_a, part_b=part_b,
                        h7_supported=part_a and part_b)])
h7.to_csv(OUT / "sample_size_h7.csv", index=False)

# ---- Figure -----------------------------------------------------------------------------
fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
ax[0].plot(summary["n"], summary["detection_rate"], "o-", color="#2f6db5")
ax[0].axhline(0.05, color="grey", ls=":", lw=1)
ax[0].axhline(0.8, color="grey", ls="--", lw=1)
ax[0].text(SIZES[-1], 0.81, "80% power", ha="right", va="bottom", fontsize=9, color="grey")
ax[0].set(xscale="log", xticks=SIZES, xticklabels=SIZES, ylim=(0, 1.02),
          xlabel="Sample size (log scale)", ylabel="Share of samples with p < .05",
          title="How often the age effect is detected")
for n in summary["n"]:
    g = draws[draws.n == n]
    jitter = n * np.exp(rng.normal(0, 0.05, len(g)))
    sig = g["p"] < 0.05
    ax[1].scatter(jitter[~sig], g["age_coef"][~sig], s=3, alpha=0.15, color="grey")
    ax[1].scatter(jitter[sig], g["age_coef"][sig], s=3, alpha=0.3, color="#c0392b")
ax[1].axhline(full_coef, color="#2f6db5", lw=1.5, label=f"Full sample (n = {len(d)})")
ax[1].scatter([], [], color="#c0392b", s=10, label="p < .05")
ax[1].scatter([], [], color="grey", s=10, label="p ≥ .05")
ax[1].set(xscale="log", xticks=SIZES, xticklabels=SIZES, xlabel="Sample size (log scale)",
          ylabel="Grey matter change per year of age (cm³)",
          title="Estimated age effect in each sample")
ax[1].legend(fontsize=8, loc="lower right")
if SHUFFLED:
    fig.suptitle("BLIND ANALYSIS - shuffled data, results are meaningless", color="red", fontsize=13)
fig.tight_layout()
fig.savefig(OUT / "fig_sample_size.png", dpi=150)

print(f"{'BLIND ANALYSIS (shuffled data) - results are meaningless' if SHUFFLED else 'REAL DATA'}")
print(f"Full sample: n = {len(d)}, age coefficient = {full_coef:.3f} cm3/year (p = {full_p:.3g})")
print(summary[["n", "detection_rate", "median_coef_sig", "ratio_sig_to_full", "sign_errors_sig"]]
      .round(3).to_string(index=False))
print(f"\nH7: (a) detection rises with n: {part_a}   (b) small-sample overestimation: {part_b}"
      f"   -> supported: {part_a and part_b}")
if SHUFFLED:
    print("Expected on shuffled data: detection rate about 5% at every n (chance), H7 FALSE.")
print(f"Saved in {OUT.relative_to(PROJECT)}/")
