"""
Step 8b - EXPLORATORY (not pre-registered): the H7 sample-size simulation for every volume.

Why: in the real data the grey matter-age effect (H7's pre-registered outcome) is so large
(p ~ 1e-118) that even n = 25 detects it 99.8% of the time, so H7's test hit a ceiling and
says little about small-sample problems. This script runs the identical simulation for all
18 volumes (grey matter, white matter, CSF and the 15 FIRST structures), whose age effects
range from enormous to essentially zero. Running every volume, rather than picking one weak
effect after seeing the results, avoids choosing the example that tells the best story.

Same method as scripts/13_sample_size.py: 1,000 random samples (without replacement) at
n = 25, 50, 100, 200, 300, 500 from the primary analysis set; in each, a linear model
  volume ~ age + sex + site + intracranial volume   (ComBat-harmonised volumes)
and the age coefficient and its p-value are kept. Subcortical volumes use the scans with all
15 structures (complete cases), whole-brain volumes use all primary scans.

Reported for each volume and n: detection rate (share with p < .05), median age coefficient
among the significant samples divided by the full-sample coefficient ("exaggeration ratio",
above 1 = winner's curse), and the share of significant samples with the wrong sign.

Usage, from the project folder (after scripts/10_harmonise.py, real data):
  ~/brainenv/bin/python scripts/13b_sample_size_all_structures.py
Outputs in results/real/: sample_size_all_structures.csv, fig_sample_size_all_structures.png
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
OUT = PROJECT / "results" / "real"
OUT.mkdir(parents=True, exist_ok=True)
SIZES = [25, 50, 100, 200, 300, 500]
DRAWS = 1000
SEED = 42
WHOLE = ["gm", "wm", "csf"]
SUB = ["L_Thal", "L_Caud", "L_Puta", "L_Pall", "L_Hipp", "L_Amyg", "L_Accu",
       "R_Thal", "R_Caud", "R_Puta", "R_Pall", "R_Hipp", "R_Amyg", "R_Accu", "BrStem"]


def age_effect(X, y):
    """OLS age coefficient and two-sided p-value (column 1 of X is age)."""
    keep = np.any(X != 0, axis=0)
    X = X[:, keep]
    n, k = X.shape
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    df = n - k
    se = np.sqrt(resid @ resid / df * np.linalg.pinv(X.T @ X)[1, 1])
    t = beta[1] / se
    return beta[1], t, 2 * stats.t.sf(abs(t), df)


infile = PROJECT / "data" / "analysis_dataset_harmonised.csv"
if not infile.exists():
    sys.exit("data/analysis_dataset_harmonised.csv not found. Run scripts/09 and 10 (real data) first.")
data = pd.read_csv(infile)
if bool(data["shuffled"].iloc[0]):
    sys.exit("This exploratory script is for the real data only.")
data = data[data["variant"] == "primary"]

rng = np.random.default_rng(SEED)
rows = []
for vol in WHOLE + SUB:
    cols = [c + "_h" for c in (WHOLE if vol in WHOLE else SUB)]
    d = data.dropna(subset=cols + ["age", "sex", "site", "icv"]).reset_index(drop=True)
    sites = sorted(d["site"].unique())
    X = np.column_stack([np.ones(len(d)), d["age"], (d["sex"] == "male").astype(float)]
                        + [(d["site"] == s).astype(float) for s in sites[1:]] + [d["icv"] / 1e6])
    y = d[vol + "_h"].to_numpy() / 1000                   # cm3
    full_coef, full_t, full_p = age_effect(X, y)
    for n in SIZES:
        if n > len(d):
            continue
        res = np.array([age_effect(X[idx], y[idx])
                        for idx in (rng.choice(len(d), size=n, replace=False) for _ in range(DRAWS))])
        coef, p = res[:, 0], res[:, 2]
        sig = p < 0.05
        rows.append(dict(
            volume=vol, full_n=len(d), full_coef=full_coef, full_t=full_t, full_p=full_p, n=n,
            detection_rate=sig.mean(),
            median_coef_sig=np.median(coef[sig]) if sig.any() else np.nan,
            exaggeration_ratio=np.median(coef[sig]) / full_coef if sig.any() else np.nan,
            sign_errors_sig=(np.sign(coef[sig]) != np.sign(full_coef)).mean() if sig.any() else np.nan))
    print(f"  {vol:7s} done (full-sample t = {full_t:+.1f})", flush=True)

res = pd.DataFrame(rows)
res.to_csv(OUT / "sample_size_all_structures.csv", index=False)

# ---- Figure -----------------------------------------------------------------------------
order = res.drop_duplicates("volume").sort_values("full_t", key=np.abs, ascending=False)
cmap = plt.get_cmap("viridis")
tmax = np.log10(order["full_t"].abs().max())
colour = {v: cmap(np.log10(max(abs(t), 1)) / tmax * 0.9) for v, t in zip(order.volume, order.full_t)}
fig, ax = plt.subplots(1, 2, figsize=(14, 5.4))
fig.subplots_adjust(wspace=0.32)
for v in order.volume:
    g = res[res.volume == v]
    ax[0].plot(g.n, g.detection_rate, "o-", ms=3, color=colour[v], lw=1.2)
    if g.full_p.iloc[0] < 0.05:
        ax[1].plot(g.n, g.exaggeration_ratio, "o-", ms=3, color=colour[v], lw=1.2)
for v in order.volume[:1].tolist():
    g = res[res.volume == v]
    ax[0].annotate(v, (g.n.iloc[-1], g.detection_rate.iloc[-1]), xytext=(4, 0),
                   textcoords="offset points", fontsize=7, va="center", color=colour[v])
ax[0].axhline(0.05, color="grey", ls=":", lw=1)
ax[0].axhline(0.8, color="grey", ls="--", lw=1)
ax[0].set(xscale="log", xticks=SIZES, xticklabels=SIZES, ylim=(0, 1.02), xlabel="Sample size (log scale)",
          ylabel="Share of samples with p < .05", title="Detection rate of the age effect, all 18 volumes")
ax[1].axhline(1, color="grey", lw=1)
ax[1].set(xscale="log", xticks=SIZES, xticklabels=SIZES, yscale="log", xlabel="Sample size (log scale)",
          ylabel="Median significant estimate / full-sample estimate",
          title="Exaggeration of significant results\n(volumes with a significant full-sample age effect)")
fig.colorbar(plt.cm.ScalarMappable(cmap=cmap, norm=matplotlib.colors.LogNorm(1, 10 ** (tmax / 0.9))),
             ax=ax, label="|t| of the age effect in the full sample (log scale)", shrink=0.8)
fig.suptitle("EXPLORATORY (not pre-registered): H7 simulation repeated for every volume", fontsize=11, y=1.05)
fig.savefig(OUT / "fig_sample_size_all_structures.png", dpi=150, bbox_inches="tight")

# ---- Summary ------------------------------------------------------------------------------
wide = res.pivot(index="volume", columns="n", values="detection_rate").loc[order.volume]
ratio = res.pivot(index="volume", columns="n", values="exaggeration_ratio").loc[order.volume]
info = order.set_index("volume")[["full_n", "full_coef", "full_t", "full_p"]]
pd.set_option("display.width", 200)
print("\nEXPLORATORY - full-sample age effect (cm3/year) and detection rate by n:")
print(pd.concat([info.round({"full_coef": 4, "full_t": 1, "full_p": 4}), wide.round(3)], axis=1).to_string())
print("\nExaggeration ratio (median significant estimate / full-sample estimate) by n:")
print(ratio.round(2).to_string())
print(f"\nSaved results/real/sample_size_all_structures.csv and fig_sample_size_all_structures.png")
