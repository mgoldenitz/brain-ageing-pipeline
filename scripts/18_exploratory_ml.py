"""
Step 12 - Exploratory machine-learning checks on the brain age model.
POST-HOC: added after the real results were seen, NOT pre-registered. Everything here is
reported as exploratory and none of it changes a hypothesis verdict.

Uses the primary analysis scans and the same features, ComBat step, tuning grids and
cross-validation splits as scripts/12_brain_age.py (run that first). Six checks:

  1. Three more model types: support vector regression (SVR) and Gaussian process regression
     (GPR), both common in published brain age work, and a small neural network (multi-layer
     perceptron, MLP; one or two hidden layers, early stopping, age standardised for training). Same 5 x 10 x 5 nested CV, same folds,
     so their fold MAEs can be compared pairwise with the saved models (Wilcoxon test).
  2. Leave-one-site-out (H6) recomputed with scikit-learn's LeaveOneGroupOut, as a check that
     the hand-written split loop in 12_brain_age.py gives the same numbers.
  3. Permutation importance: within each of 10 outer folds, the best model is trained on the
     training scans and each volume is shuffled in the TEST scans; the rise in MAE (years) is
     that volume's importance. Left and right structures are correlated, so they share credit.
  4. Partial dependence: how the best model's predicted age changes across each of the four
     most important volumes, other volumes held at their observed values (descriptive).
  5. Learning curve: test MAE as the number of training scans grows (10 random 80/20 splits).
     If the curve is still falling at the full sample, more data would help.
  6. Unsupervised outlier detection (IsolationForest, LocalOutlierFactor) on the 18 volumes,
     scored against the QC decisions: do the detectors rank the confirmed segmentation
     failures as unusual? Compared with the robust-z rule used to flag scans for review.

Usage, from the project folder (after scripts/12_brain_age.py on real data):
  ~/brainenv/bin/python scripts/18_exploratory_ml.py           # full run, about 15-30 minutes
  ~/brainenv/bin/python scripts/18_exploratory_ml.py --quick   # fast code test
Outputs in results/real/: exploratory_ml.txt, exploratory_ml_models.csv,
exploratory_ml_importance.csv, exploratory_ml_outliers.csv, fig_feature_importance.png,
fig_learning_curve.png
"""

from pathlib import Path
import contextlib
import io
import sys
import time
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats
import sklearn
from neuroCombat import neuroCombat
from sklearn.base import BaseEstimator, TransformerMixin, clone
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import GradientBoostingRegressor, IsolationForest, RandomForestRegressor
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel
from sklearn.inspection import partial_dependence, permutation_importance
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import roc_auc_score
from sklearn.compose import TransformedTargetRegressor
from sklearn.model_selection import (GridSearchCV, KFold, LeaveOneGroupOut, ShuffleSplit,
                                     cross_validate, learning_curve)
from sklearn.neighbors import LocalOutlierFactor
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR

warnings.filterwarnings("ignore")
PROJECT = Path(__file__).resolve().parent.parent
OUT = PROJECT / "results" / "real"
QUICK = "--quick" in sys.argv
SEED = 42
REPEATS, OUTER, INNER = (1, 5, 3) if QUICK else (5, 10, 5)
N_PERM = 5 if QUICK else 20
N_LC_SPLITS = 3 if QUICK else 10
N_JOBS = -1
SUB = ["L_Thal", "L_Caud", "L_Puta", "L_Pall", "L_Hipp", "L_Amyg", "L_Accu",
       "R_Thal", "R_Caud", "R_Puta", "R_Pall", "R_Hipp", "R_Amyg", "R_Accu", "BrStem"]
VOLS = ["gm", "wm", "csf"] + SUB
PART = {"Thal": "thalamus", "Caud": "caudate", "Puta": "putamen", "Pall": "pallidum",
        "Hipp": "hippocampus", "Amyg": "amygdala", "Accu": "accumbens"}
PRETTY = {"gm": "Grey matter", "wm": "White matter", "csf": "CSF", "BrStem": "Brainstem"}
PRETTY.update({f"{s}_{k}": f"{'Left' if s == 'L' else 'Right'} {v}" for s in "LR" for k, v in PART.items()})
NAMES = {"baseline": "Baseline", "ridge": "Ridge", "random_forest": "Random Forest",
         "gradient_boosting": "Gradient Boosting", "svr": "SVR", "gaussian_process": "Gaussian Process", "mlp": "Neural network (MLP)"}


# ---- Same data rules, features and ComBat step as scripts/12_brain_age.py --------------------
def apply_qc(d, variant="primary"):
    d = d.copy()
    wb, sc = d["qc_wb"], d["qc_sc"]
    d = d[~(wb >= 2)]
    d.loc[sc.loc[d.index] >= 2, SUB] = np.nan
    return d


def make_xy(d):
    d = d.dropna(subset=VOLS + ["age", "icv", "site", "sex"]).reset_index(drop=True)
    X = d[VOLS].div(d["icv"], axis=0)
    X["site"] = d["site"].to_numpy()
    X["sex"] = (d["sex"] == "male").astype(float).to_numpy()
    return X, d["age"].to_numpy(dtype=float), d


class ComBat(BaseEstimator, TransformerMixin):
    """Harmonises the volume columns across sites (training-fold estimates only)."""

    def __init__(self, use=True):
        self.use = use

    def fit(self, X, y):
        if not self.use:
            return self
        covars = pd.DataFrame({"site": X["site"].to_numpy(), "sex": X["sex"].to_numpy(),
                               "age": y, "age2": y ** 2})
        with contextlib.redirect_stdout(io.StringIO()):
            res = neuroCombat(dat=X[VOLS].to_numpy().T, covars=covars, batch_col="site",
                              categorical_cols=["sex"], continuous_cols=["age", "age2"])
        e = res["estimates"]
        self.levels_ = np.array(e["batches"], dtype=str)
        self.mean_ = (e["stand.mean"][:, 0] + e["mod.mean"].mean(axis=1))
        self.sd_ = np.sqrt(np.asarray(e["var.pooled"]).ravel())
        self.gamma_ = np.asarray(e["gamma.star"])
        self.delta_ = np.asarray(e["delta.star"])
        return self

    def transform(self, X):
        V = X[VOLS].to_numpy(dtype=float)
        if not self.use:
            return V
        site = X["site"].to_numpy(dtype=str)
        unknown = set(site) - set(self.levels_)
        if unknown:
            raise ValueError(f"ComBat can't harmonise sites not in the training data: {unknown}")
        idx = np.array([np.where(self.levels_ == s)[0][0] for s in site])
        Z = (V - self.mean_) / self.sd_
        Z = (Z - self.gamma_[idx]) / np.sqrt(self.delta_[idx])
        return Z * self.sd_ + self.mean_


GPR_KERNEL = (ConstantKernel(1.0, (1e-2, 1e2)) * RBF(5.0, (1e-1, 1e3))
              + WhiteKernel(1.0, (1e-3, 1e1)))
MODELS = {
    "baseline": (DummyRegressor(strategy="mean"), {}),
    "ridge": (Ridge(), {"model__alpha": np.logspace(-3, 3, 7)}),
    "random_forest": (RandomForestRegressor(n_estimators=300, random_state=SEED, n_jobs=1),
                      {"model__max_features": [0.33, 1.0], "model__min_samples_leaf": [1, 5]}),
    "gradient_boosting": (GradientBoostingRegressor(n_estimators=200, subsample=0.8, random_state=SEED),
                          {"model__learning_rate": [0.05, 0.1], "model__max_depth": [2, 3]}),
    # Added here (exploratory):
    "svr": (SVR(kernel="rbf"), {"model__C": [10, 30, 100], "model__epsilon": [0.5, 2.0]}),
    "gaussian_process": (GaussianProcessRegressor(kernel=GPR_KERNEL, normalize_y=True,
                                                  random_state=SEED), {}),  # kernel fitted by marginal likelihood
    "mlp": (TransformedTargetRegressor(
                regressor=MLPRegressor(max_iter=2000, early_stopping=True, validation_fraction=0.15,
                                       n_iter_no_change=30, learning_rate_init=0.005, random_state=SEED),
                transformer=StandardScaler()),
            {"model__regressor__hidden_layer_sizes": [(16,), (64,), (32, 16)],
             "model__regressor__alpha": [1e-3, 1e-1, 1.0]}),
}


def pipeline(model, combat):
    return Pipeline([("combat", ComBat(use=combat)), ("scale", StandardScaler()), ("model", clone(model))])


def tuned(name, combat, inner_seed, n_jobs=N_JOBS):
    model, grid = MODELS[name]
    pipe = pipeline(model, combat)
    if not grid:
        return pipe
    return GridSearchCV(pipe, grid, cv=KFold(INNER, shuffle=True, random_state=inner_seed),
                        scoring="neg_mean_absolute_error", n_jobs=n_jobs)


def mae(y, p):
    return float(np.mean(np.abs(p - y)))


# ---- Load ------------------------------------------------------------------------------------
t0 = time.time()
data = pd.read_csv(PROJECT / "data" / "analysis_dataset.csv")
if bool(data["shuffled"].iloc[0]):
    sys.exit("data/analysis_dataset.csv is the shuffled version; rebuild the real dataset first.")
saved_folds_file = OUT / "brainage_folds.csv"
if not saved_folds_file.exists():
    sys.exit("results/real/brainage_folds.csv not found - run scripts/12_brain_age.py first.")
saved = pd.read_csv(saved_folds_file)
saved = saved[saved.analysis == "primary"]
best = pd.read_csv(OUT / "brainage_h5.csv").set_index("analysis").loc["primary", "best_model"]
X, y, d = make_xy(apply_qc(data))
print(f"POST-HOC EXPLORATORY ANALYSES{' - QUICK TEST' if QUICK else ''}: {len(y)} scans, "
      f"best pre-registered model = {NAMES[best]}")
report = ["EXPLORATORY MACHINE-LEARNING CHECKS (post-hoc, not pre-registered)"
          + (" - QUICK TEST, NOT FOR REPORTING" if QUICK else ""),
          f"Primary analysis scans: n = {len(y)}; best pre-registered model: {NAMES[best]}", ""]

# ---- 1. SVR and Gaussian process in the same nested CV ------------------------------------------
rows = []
for rep in range(REPEATS):
    for k, (tr, te) in enumerate(KFold(OUTER, shuffle=True, random_state=SEED + rep).split(X)):
        for name in ["baseline", "svr", "gaussian_process", "mlp"]:
            est = tuned(name, True, SEED + 100 * rep + k).fit(X.iloc[tr], y[tr])
            rows.append(dict(repeat=rep, fold=k, model=name, mae=mae(y[te], est.predict(X.iloc[te]))))
    print(f"  1. extra models: repeat {rep + 1}/{REPEATS} done", flush=True)
new = pd.DataFrame(rows)
both = pd.concat([saved[["repeat", "fold", "model", "mae"]], new[new.model != "baseline"]])
# Same folds as 12_brain_age.py? The baseline depends only on the split, so its MAEs must match.
chk = (new[new.model == "baseline"].merge(saved[saved.model == "baseline"], on=["repeat", "fold"],
                                           suffixes=("_new", "_saved")))
same_folds = len(chk) == len(new[new.model == "baseline"]) and np.allclose(chk.mae_new, chk.mae_saved)
both.to_csv(OUT / "exploratory_ml_models.csv", index=False)
means = both.groupby("model")["mae"].agg(["mean", "std"]).sort_values("mean")
report += ["1. Three additional model types (same nested CV and folds as the pre-registered models)",
           f"   Folds identical to scripts/12_brain_age.py: {same_folds}",
           "   Mean cross-validated MAE (years, uncorrected):"]
for m, r in means.iterrows():
    report.append(f"     {NAMES[m]:22s} {r['mean']:6.2f}  (SD across folds {r['std']:.2f})")
if same_folds:
    b = saved[saved.model == best].sort_values(["repeat", "fold"])["mae"].to_numpy()
    for m in ["svr", "gaussian_process", "mlp"]:
        a = new[new.model == m].sort_values(["repeat", "fold"])["mae"].to_numpy()
        p = stats.wilcoxon(a, b).pvalue
        report.append(f"   {NAMES[m]} vs {NAMES[best]}: mean difference {np.mean(a - b):+.2f} years, "
                      f"Wilcoxon p = {p:.3g} ({len(a)} paired folds)")
report.append("")

# ---- 2. Leave-one-site-out with LeaveOneGroupOut ---------------------------------------------------
logo = LeaveOneGroupOut()
groups = d["site"].to_numpy()
site_order = np.unique(groups)
loso_saved = pd.read_csv(OUT / "brainage_loso.csv").set_index("site")
report += ["2. Leave-one-site-out recomputed with LeaveOneGroupOut (no ComBat, as in H6)",
           "   Site            n   MAE now   MAE in brainage_loso.csv"]
diffs = []
for name, col in [(best, "mae_leave_site_out"), ("baseline", "mae_leave_site_out_baseline")]:
    cv = cross_validate(tuned(name, False, SEED), X, y, groups=groups, cv=logo,
                        scoring="neg_mean_absolute_error")
    for s, score in zip(site_order, -cv["test_score"]):
        old = loso_saved.loc[s, col] if s in loso_saved.index else np.nan
        diffs.append(abs(score - old))
        report.append(f"   {s:12s} {int((groups == s).sum()):4d}   {score:7.2f}   {old:7.2f}   ({NAMES[name]})")
report += [f"   Largest difference from the hand-written loop: {np.nanmax(diffs):.3f} years", ""]
print("  2. leave-one-site-out done", flush=True)

# ---- 3. Permutation importance (held-out folds, best model) ----------------------------------------
imp = []
for k, (tr, te) in enumerate(KFold(OUTER, shuffle=True, random_state=SEED).split(X)):
    est = tuned(best, True, SEED + k).fit(X.iloc[tr], y[tr])
    r = permutation_importance(est, X.iloc[te], y[te], scoring="neg_mean_absolute_error",
                               n_repeats=N_PERM, random_state=SEED, n_jobs=N_JOBS)
    imp.append(pd.Series(r.importances_mean, index=X.columns))
imp = pd.DataFrame(imp)[VOLS]
imp_sum = pd.DataFrame({"importance_mean": imp.mean(), "importance_sd": imp.std()}).sort_values(
    "importance_mean", ascending=False)
imp_sum.to_csv(OUT / "exploratory_ml_importance.csv")
report += [f"3. Permutation importance ({NAMES[best]}; rise in test MAE, years, when a volume is shuffled;",
           f"   mean over {OUTER} held-out folds x {N_PERM} shuffles)"]
for v, r in imp_sum.iterrows():
    report.append(f"     {PRETTY[v]:18s} {r.importance_mean:+6.2f}  (SD {r.importance_sd:.2f})")
report += ["   Left and right structures are correlated, so they split the credit between them.", ""]
print("  3. permutation importance done", flush=True)

# ---- 4. Partial dependence (final model on all scans) ------------------------------------------------
final = tuned(best, True, SEED).fit(X, y)
final = final.best_estimator_ if hasattr(final, "best_estimator_") else final
top = list(imp_sum.index[:4])
pdp = {}
for v in top:
    res = partial_dependence(final, X, [v], grid_resolution=25, percentiles=(0.05, 0.95), kind="average")
    grid = res["grid_values"][0] if "grid_values" in res else res["values"][0]
    pdp[v] = (np.asarray(grid) * 100, np.asarray(res["average"][0]))
report += ["4. Partial dependence: predicted age at the 5th and 95th percentile of each top volume"]
for v in top:
    g, a = pdp[v]
    report.append(f"     {PRETTY[v]:18s} {g[0]:.3f}% of ICV -> {a[0]:.1f} y;  {g[-1]:.3f}% -> {a[-1]:.1f} y")
report.append("")
print("  4. partial dependence done", flush=True)

fig = plt.figure(figsize=(14, 6.2))
gs = fig.add_gridspec(2, 4, width_ratios=[1.5, 0.12, 1, 1], wspace=0.35, hspace=0.55)
ax = fig.add_subplot(gs[:, 0])
s = imp_sum.iloc[::-1]
ax.barh([PRETTY[v] for v in s.index], s.importance_mean, xerr=s.importance_sd, color="#2f6db5",
        ecolor="#9ca3af", capsize=2)
ax.axvline(0, color="grey", lw=0.8)
ax.set(xlabel="Increase in MAE when shuffled (years)",
       title=f"Permutation importance\n{NAMES[best]}, held-out folds")
lo = min(p[1].min() for p in pdp.values()) - 2           # one shared y scale, so effect sizes compare
hi = max(p[1].max() for p in pdp.values()) + 2
for i, v in enumerate(top):
    a = fig.add_subplot(gs[i // 2, 2 + i % 2])
    g, avg = pdp[v]
    a.plot(g, avg, color="#2f6db5", lw=2)
    a.set_ylim(lo, hi)
    a.plot(np.percentile(X[v] * 100, np.arange(10, 100, 10)), np.full(9, lo + 0.8), "|",
           color="#6b7280", ms=8)
    a.set(title=PRETTY[v], xlabel="% of intracranial volume", ylabel="Predicted age (years)")
fig.text(0.70, 0.98, "Partial dependence (top four volumes, same scale)", ha="center", va="top", fontsize=12)
fig.suptitle("EXPLORATORY (post-hoc)" + (" - QUICK TEST" if QUICK else ""), x=0.01, ha="left",
             fontsize=9, color="#6b7280")
fig.savefig(OUT / "fig_feature_importance.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# ---- 5. Learning curve ------------------------------------------------------------------------------
cv = ShuffleSplit(n_splits=N_LC_SPLITS, test_size=0.2, random_state=SEED)
n_max = int(len(y) * 0.8)
sizes = np.unique(np.r_[[80, 120, 160, 240, 320], n_max])
lc = {}
lc_models = list(dict.fromkeys(["baseline", "ridge", best]))
for name in lc_models:
    ts, tr_s, te_s = learning_curve(tuned(name, True, SEED, n_jobs=1), X, y, train_sizes=sizes, cv=cv,
                                    scoring="neg_mean_absolute_error", n_jobs=N_JOBS,
                                    shuffle=True, random_state=SEED, error_score=np.nan)
    lc[name] = (ts, -te_s)
    print(f"  5. learning curve: {NAMES[name]} done", flush=True)
report += [f"5. Learning curve (test MAE, years; mean of {N_LC_SPLITS} random 80/20 splits)",
           "   Training scans  " + "  ".join(f"{n:6d}" for n in sizes)]
for name, (ts, te) in lc.items():
    report.append(f"   {NAMES[name]:15s} " + "  ".join(f"{np.nanmean(r):6.2f}" for r in te))
m = lc[best][1]
drop = np.nanmean(m[-2]) - np.nanmean(m[-1])
report += [f"   {NAMES[best]}: MAE changed by {-drop:+.2f} years over the last step "
           f"({sizes[-2]} -> {sizes[-1]} scans); near zero means more scans would add little.", ""]
fig, ax = plt.subplots(figsize=(7.5, 4.8))
colours = {"baseline": "#9ca3af", "ridge": "#f59e0b", best: "#2f6db5"}
for name, (ts, te) in lc.items():
    mu, sd = np.nanmean(te, axis=1), np.nanstd(te, axis=1)
    ax.plot(ts, mu, "o-", color=colours.get(name, "#10b981"), label=NAMES[name], lw=2, ms=4)
    ax.fill_between(ts, mu - sd, mu + sd, color=colours.get(name, "#10b981"), alpha=0.15)
ax.set(xlabel="Number of training scans", ylabel="Test MAE (years)",
       title="Learning curve" + (" - QUICK TEST" if QUICK else " (exploratory)"))
ax.legend(frameon=False)
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(OUT / "fig_learning_curve.png", dpi=150)
plt.close(fig)

# ---- 6. Unsupervised outlier detection vs QC decisions -----------------------------------------------
o = data.dropna(subset=VOLS + ["icv", "age"]).reset_index(drop=True)
F = o[VOLS].div(o["icv"], axis=0)
F_age = F - LinearRegression().fit(np.c_[o.age, o.age ** 2], F).predict(np.c_[o.age, o.age ** 2])
sc_fail = (o["qc_sc"] >= 2).to_numpy()            # subcortical segmentation failures
wb_fail = (o["qc_wb"] >= 2).to_numpy()            # whole-brain processing failures
med = o[SUB].median()
rz = ((o[SUB] - med) / ((o[SUB] - med).abs().median() * 1.4826)).abs().max(axis=1).to_numpy()
scores = {"Robust z (rule used to pick scans for review)": rz}
for label, feats in [("", F), (" (age-adjusted)", F_age)]:
    Z = StandardScaler().fit_transform(feats)
    scores["IsolationForest" + label] = -IsolationForest(n_estimators=500, random_state=SEED).fit(Z).score_samples(Z)
    scores["LocalOutlierFactor" + label] = -LocalOutlierFactor(n_neighbors=20).fit(Z).negative_outlier_factor_
top_n = int(round(0.05 * len(o)))
report += [f"6. Outlier detection on the 18 volumes (n = {len(o)}; {sc_fail.sum()} subcortical and "
           f"{wb_fail.sum()} whole-brain QC failures)",
           f"   AUC = how well the score ranks failures above passes (0.5 = chance);",
           f"   'in top 5%' = failures among the {top_n} highest-scoring scans.",
           "   Method                                          AUC sub  top5% sub   AUC wb  top5% wb"]
out = o[["subject", "site", "qc_wb", "qc_sc"]].copy()
for name, sc in scores.items():
    out[name] = sc
    top_idx = np.argsort(-sc)[:top_n]
    report.append(f"   {name:46s} {roc_auc_score(sc_fail, sc):7.2f}  {sc_fail[top_idx].sum():4d}/{sc_fail.sum():<4d}"
                  f"  {roc_auc_score(wb_fail, sc):7.2f}  {wb_fail[top_idx].sum():4d}/{wb_fail.sum()}")
report += ["   Caveat: 7 of the subcortical failures were found by reviewing robust-z flags, so the",
           "   robust-z row is partly circular for subcortical failures.", ""]
out.to_csv(OUT / "exploratory_ml_outliers.csv", index=False)
print("  6. outlier detection done", flush=True)

report.append(f"scikit-learn {sklearn.__version__}; seed {SEED}; repeats {REPEATS}; outer {OUTER}; inner {INNER}")
text = "\n".join(report) + "\n"
(OUT / "exploratory_ml.txt").write_text(text)
print("\n" + text)
print(f"Saved in results/real/  ({(time.time() - t0) / 60:.1f} minutes)")
