"""
Step 7b - Redraw the brain age figure (results/<real|shuffled>/fig_brainage.png) from the saved
results of scripts/12_brain_age.py, without re-running the 30-minute model fitting.
Same figure as the one 12_brain_age.py draws; use this after changing only its appearance.

Usage, from the project folder:
  ~/brainenv/bin/python scripts/12b_brainage_figure.py             # real data
  ~/brainenv/bin/python scripts/12b_brainage_figure.py --shuffled  # blind analysis
"""

from pathlib import Path
import sys

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PROJECT = Path(__file__).resolve().parent.parent
SHUFFLED = "--shuffled" in sys.argv
OUT = PROJECT / "results" / ("shuffled" if SHUFFLED else "real")
NAMES = {"baseline": "Baseline", "ridge": "Ridge", "random_forest": "Random Forest",
         "gradient_boosting": "Gradient Boosting"}

subj = pd.read_csv(OUT / "brainage_predictions.csv")
summary = pd.read_csv(OUT / "brainage_summary.csv")
best_model = pd.read_csv(OUT / "brainage_h5.csv").set_index("analysis").loc["primary", "best_model"]

fig, ax = plt.subplots(1, 3, figsize=(15, 4.6))
lim = [subj.age.min() - 3, subj.age.max() + 3]
for a_, col, title in [(ax[0], "pred", "Predicted age (uncorrected)"),
                       (ax[1], "pred_corrected", "Predicted age (bias-corrected)")]:
    a_.scatter(subj.age, subj[col], s=8, alpha=0.5, color="#2f6db5")
    a_.plot(lim, lim, color="grey", lw=1, ls="--")
    a_.set(xlim=lim, ylim=lim, xlabel="Age (years)", ylabel="Predicted age (years)",
           title=f"{title}\n{NAMES[best_model]}, primary analysis")
s = summary[summary.analysis == "primary"].set_index("model").loc[list(NAMES)]
ax[2].bar([NAMES[m] for m in s.index], s["mae"], color=["#999999"] + ["#2f6db5"] * 3)
ax[2].set(ylabel="Mean absolute error (years)", title="Cross-validated MAE, uncorrected")
ax[2].tick_params(axis="x", rotation=20)
if SHUFFLED:
    fig.suptitle("BLIND ANALYSIS - shuffled data, results are meaningless", color="red", fontsize=13)
fig.tight_layout()
fig.savefig(OUT / "fig_brainage.png", dpi=150)
print(f"Saved {(OUT / 'fig_brainage.png').relative_to(PROJECT)}")
