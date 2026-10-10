"""
Step 7 - Brain age model (hypotheses H5 and H6), following the pre-registration.

Features: the 18 volumes, each divided by intracranial volume. Target: age.
Models: ridge regression, random forest and gradient boosting, against a baseline that
always predicts the training-set mean age.

Validation (nothing is ever fitted on test data):
  * Nested cross-validation: 10 outer x 5 inner folds, repeated 5 times (seed 42).
  * Inside every training fold: ComBat harmonisation (age, age squared and sex preserved),
    scaling, hyperparameter tuning (inner folds) and the bias-correction fit.
  * ComBat is applied to test scans with the training-fold estimates only. No age is used
    for test scans: the covariate part is set to the training-fold average.
  * Bias correction (de Lange & Cole, 2020): within the training fold, inner
    cross-validated predictions are regressed on age (pred = a * age + b); test predictions
    are corrected as (pred - b) / a. If a < 0.1 the model has learned almost nothing about
    age, the correction is unstable (dividing by nearly zero), and corrected predictions for
    that fold are left missing.

H5 decision (written before any real result): the best model (lowest mean MAE) is
compared with the baseline on the 50 paired outer-fold MAEs (Wilcoxon signed-rank test).
H5 is supported if its mean MAE is lower and p < .05. MAE is judged on UNcorrected
predictions, because the correction uses each person's true age and flatters accuracy;
corrected predictions give the brain age gap used in the exploratory analyses.

H6 (leave-one-site-out): for each site, the best model type is trained on the other two
sites and tested on it, and compared with cross-validation within that site alone (10 folds
x 5 repeats). ComBat is not used here: a site absent from training can't be harmonised, and
a single site needs no harmonisation.
  Pre-registered rule: H6 is supported if the mean leave-one-site-out MAE across the three
  sites is higher than the mean within-site MAE.
  Added before unblinding (found in the blind analysis): the sites differ in age range, so a
  model trained on other sites starts from a different average age; that alone makes
  leave-one-site-out MAE higher, even with no real brain-age signal. So the mean-age baseline
  is run in both settings too, and skill = 1 - MAE(model) / MAE(baseline). Refined rule: H6
  is supported if the model has real skill within sites (mean within-site skill >= 0.10, i.e.
  at least 10% better than the baseline) and mean skill is lower leave-one-site-out than
  within-site. Both rules are reported.

Sensitivity analyses (H5 repeated in each): exclude_1s, no_iop, no_combat, raw_volumes
(volumes not divided by ICV), include_wb2, first_pass. H5 is called robust if it holds in all.

Exploratory (reported as such), from the primary analysis:
  brain age gap (bias-corrected, averaged over repeats) ~ sex + site, before and after
  ComBat; brain age gap ~ CNR + site; accuracy above age 80.

Usage, from the project folder:
  ~/brainenv/bin/python scripts/12_brain_age.py --shuffled          # blind analysis
  ~/brainenv/bin/python scripts/12_brain_age.py --shuffled --quick  # fast code test
  ~/brainenv/bin/python scripts/12_brain_age.py                     # real data, after unblinding
Outputs in results/<shuffled|real>/: brainage_folds.csv, brainage_summary.csv,
brainage_h5.csv, brainage_loso.csv, brainage_predictions.csv, brainage_exploratory.txt,
fig_brainage.png, brainage_versions.txt
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
import scipy
from scipy import stats
import sklearn
import statsmodels.formula.api as smf
from neuroCombat import neuroCombat
from sklearn.base import BaseEstimator, TransformerMixin, clone
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.model_selection import GridSearchCV, KFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
PROJECT = Path(__file__).resolve().parent.parent
SHUFFLED = "--shuffled" in sys.argv
QUICK = "--quick" in sys.argv
STEM = "analysis_shuffled" if SHUFFLED else "analysis_dataset"
OUT = PROJECT / "results" / ("shuffled" if SHUFFLED else "real")
OUT.mkdir(parents=True, exist_ok=True)

SEED = 42
REPEATS, OUTER, INNER = (1, 5, 3) if QUICK else (5, 10, 5)
N_JOBS = -1
SUB = ["L_Thal", "L_Caud", "L_Puta", "L_Pall", "L_Hipp", "L_Amyg", "L_Accu",
       "R_Thal", "R_Caud", "R_Puta", "R_Pall", "R_Hipp", "R_Amyg", "R_Accu", "BrStem"]
VOLS = ["gm", "wm", "csf"] + SUB


# ---- Data and QC rules (same rules as scripts/10_harmonise.py) -------------------------------
def apply_qc(d, variant):
    d = d.copy()
    wb, sc = (d["qc_wb_first"], d["qc_sc_first"]) if variant == "first_pass" else (d["qc_wb"], d["qc_sc"])
    limit = 1 if variant == "exclude_1s" else 2
    if variant != "include_wb2":
        d = d[~(wb >= limit)]
    d.loc[sc.loc[d.index] >= limit, SUB] = np.nan
    if variant == "no_iop":
        d = d[d["site"] != "IOP"]
    return d


def make_xy(d, raw_volumes=False):
    """Complete cases; features = volumes / ICV (or raw volumes), plus site and sex for ComBat."""
    d = d.dropna(subset=VOLS + ["age", "icv", "site", "sex"]).reset_index(drop=True)
    X = d[VOLS].copy() if raw_volumes else d[VOLS].div(d["icv"], axis=0)
    X["site"] = d["site"].to_numpy()
    X["sex"] = (d["sex"] == "male").astype(float).to_numpy()
    return X, d["age"].to_numpy(dtype=float), d


# ---- ComBat as a scikit-learn step, fitted on training data only -------------------------------
class ComBat(BaseEstimator, TransformerMixin):
    """Harmonises the volume columns across sites; drops the site and sex columns.
    fit() uses the training fold's site, sex and age (y); transform() uses only site."""

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
        self.mean_ = (e["stand.mean"][:, 0] + e["mod.mean"].mean(axis=1))   # covariates at train average
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


MODELS = {
    "baseline": (DummyRegressor(strategy="mean"), {}),
    "ridge": (Ridge(), {"model__alpha": np.logspace(-3, 3, 7)}),
    "random_forest": (RandomForestRegressor(n_estimators=300, random_state=SEED, n_jobs=1),
                      {"model__max_features": [0.33, 1.0], "model__min_samples_leaf": [1, 5]}),
    "gradient_boosting": (GradientBoostingRegressor(n_estimators=200, subsample=0.8, random_state=SEED),
                          {"model__learning_rate": [0.05, 0.1], "model__max_depth": [2, 3]}),
}


def pipeline(model, combat):
    return Pipeline([("combat", ComBat(use=combat)), ("scale", StandardScaler()), ("model", clone(model))])


def tuned(name, combat, inner_seed):
    model, grid = MODELS[name]
    pipe = pipeline(model, combat)
    if not grid:
        return pipe
    return GridSearchCV(pipe, grid, cv=KFold(INNER, shuffle=True, random_state=inner_seed),
                        scoring="neg_mean_absolute_error", n_jobs=N_JOBS)


def metrics(y, p):
    mae = float(np.mean(np.abs(p - y)))
    r = float(np.corrcoef(y, p)[0, 1]) if np.std(p) > 0 else np.nan
    r2 = float(1 - np.sum((y - p) ** 2) / np.sum((y - y.mean()) ** 2))
    return mae, r, r2


def nested_cv(X, y, combat, model_names, label):
    """Repeated nested CV. Returns per-fold metrics and out-of-fold predictions."""
    folds, preds = [], []
    for rep in range(REPEATS):
        outer = KFold(OUTER, shuffle=True, random_state=SEED + rep)
        for k, (tr, te) in enumerate(outer.split(X)):
            Xtr, Xte, ytr, yte = X.iloc[tr], X.iloc[te], y[tr], y[te]
            for name in model_names:
                est = tuned(name, combat, SEED + 100 * rep + k).fit(Xtr, ytr)
                p = est.predict(Xte)
                pc = np.full_like(p, np.nan)
                if name != "baseline":
                    best = est.best_estimator_ if hasattr(est, "best_estimator_") else est
                    p_tr = cross_val_predict(clone(best), Xtr, ytr,
                                             cv=KFold(INNER, shuffle=True, random_state=SEED + rep))
                    a, b = np.polyfit(ytr, p_tr, 1)
                    if a >= 0.1:
                        pc = (p - b) / a
                mae, r, r2 = metrics(yte, p)
                mae_c, r_c, r2_c = metrics(yte, pc) if name != "baseline" else (np.nan,) * 3
                folds.append(dict(analysis=label, repeat=rep, fold=k, model=name, n_test=len(te),
                                  mae=mae, r=r, r2=r2, mae_corrected=mae_c, r_corrected=r_c,
                                  r2_corrected=r2_c))
                preds.append(pd.DataFrame(dict(analysis=label, repeat=rep, model=name, row=te,
                                               age=yte, pred=p, pred_corrected=pc)))
        print(f"    {label}: repeat {rep + 1}/{REPEATS} done", flush=True)
    return pd.DataFrame(folds), pd.concat(preds, ignore_index=True)


def h5_test(folds, label):
    f = folds[folds.analysis == label]
    means = f.groupby("model")["mae"].mean()
    best = means.drop("baseline").idxmin()
    a = f[f.model == best].sort_values(["repeat", "fold"])["mae"].to_numpy()
    b = f[f.model == "baseline"].sort_values(["repeat", "fold"])["mae"].to_numpy()
    diff = a - b
    p = stats.wilcoxon(a, b).pvalue if np.any(diff != 0) else 1.0
    return dict(analysis=label, best_model=best, mae_best=means[best], mae_baseline=means["baseline"],
                mean_difference=diff.mean(), n_pairs=len(diff), wilcoxon_p=p,
                h5_supported=bool(diff.mean() < 0 and p < 0.05))


# ---- Run ---------------------------------------------------------------------------------------
t0 = time.time()
data_file = PROJECT / "data" / f"{STEM}.csv"
if not data_file.exists():
    sys.exit(f"{data_file.relative_to(PROJECT)} not found. Run scripts/09_build_dataset.py "
             f"{'--shuffled ' if SHUFFLED else ''}first.")
data = pd.read_csv(data_file)
if bool(data["shuffled"].iloc[0]) != SHUFFLED:
    sys.exit("The dataset's 'shuffled' flag doesn't match the --shuffled option.")
print(f"{'BLIND ANALYSIS (shuffled data) - results are meaningless' if SHUFFLED else 'REAL DATA'}"
      f"{' - QUICK TEST' if QUICK else ''}")
print(f"Nested CV: {REPEATS} repeat(s) x {OUTER} outer x {INNER} inner folds")

ANALYSES = {  # label: (QC variant, ComBat, raw volumes)
    "primary": ("primary", True, False),
    "exclude_1s": ("exclude_1s", True, False),
    "no_iop": ("no_iop", True, False),
    "no_combat": ("primary", False, False),
    "raw_volumes": ("primary", True, True),
    "include_wb2": ("include_wb2", True, False),
    "first_pass": ("first_pass", True, False),
}
all_folds, all_preds, h5_rows, rows_used = [], [], [], {}
for label, (variant, combat, raw) in ANALYSES.items():
    X, y, d = make_xy(apply_qc(data, variant), raw_volumes=raw)
    rows_used[label] = d
    print(f"  {label}: {len(y)} scans")
    f, p = nested_cv(X, y, combat, list(MODELS), label)
    all_folds.append(f)
    all_preds.append(p)
    h5_rows.append(h5_test(f, label))
folds = pd.concat(all_folds, ignore_index=True)
preds = pd.concat(all_preds, ignore_index=True)
folds.to_csv(OUT / "brainage_folds.csv", index=False)
summary = (folds.groupby(["analysis", "model"])[["mae", "r", "r2", "mae_corrected", "r_corrected"]]
           .mean().round(3).reset_index())
summary.to_csv(OUT / "brainage_summary.csv", index=False)
h5 = pd.DataFrame(h5_rows)
h5["robust"] = h5["h5_supported"].all()
h5.to_csv(OUT / "brainage_h5.csv", index=False)

# Subject-level predictions (primary analysis): averaged over repeats
best_model = h5.loc[h5.analysis == "primary", "best_model"].iloc[0]
prim = rows_used["primary"]
pp = preds[(preds.analysis == "primary") & (preds.model == best_model)]
subj = pp.groupby("row")[["age", "pred", "pred_corrected"]].mean()
subj = prim.loc[subj.index, ["subject", "site", "sex", "cnr"]].join(subj)
subj["gap"] = subj["pred"] - subj["age"]
subj["gap_corrected"] = subj["pred_corrected"] - subj["age"]
subj.to_csv(OUT / "brainage_predictions.csv", index=False)

# ---- H6: leave-one-site-out vs within-site --------------------------------------------------------
X, y, d = make_xy(apply_qc(data, "primary"))
sites = d["site"].to_numpy()
loso_rows = []
for s in sorted(set(sites)):
    tr, te = np.where(sites != s)[0], np.where(sites == s)[0]
    row = dict(site=s, n=len(te), model=best_model)
    for name, tag in [(best_model, ""), ("baseline", "_baseline")]:
        est = tuned(name, False, SEED).fit(X.iloc[tr], y[tr])
        row["mae_leave_site_out" + tag] = metrics(y[te], est.predict(X.iloc[te]))[0]
        Xs, ys = X.iloc[te], y[te]
        within = []
        for rep in range(REPEATS):
            for k, (a, b) in enumerate(KFold(min(OUTER, len(ys)), shuffle=True,
                                             random_state=SEED + rep).split(Xs)):
                e2 = tuned(name, False, SEED + rep).fit(Xs.iloc[a], ys[a])
                within.append(metrics(ys[b], e2.predict(Xs.iloc[b]))[0])
        row["mae_within_site" + tag] = float(np.mean(within))
    row["skill_leave_site_out"] = 1 - row["mae_leave_site_out"] / row["mae_leave_site_out_baseline"]
    row["skill_within_site"] = 1 - row["mae_within_site"] / row["mae_within_site_baseline"]
    loso_rows.append(row)
    print(f"  leave-one-site-out: {s} done", flush=True)
loso = pd.DataFrame(loso_rows)
loso["h6_preregistered_rule"] = loso["mae_leave_site_out"].mean() > loso["mae_within_site"].mean()
loso["h6_refined_rule"] = bool(loso["skill_within_site"].mean() >= 0.10
                               and loso["skill_leave_site_out"].mean() < loso["skill_within_site"].mean())
loso.to_csv(OUT / "brainage_loso.csv", index=False)

# ---- Exploratory ------------------------------------------------------------------------------------
GAP = "gap_corrected"
if subj["gap_corrected"].notna().sum() < 30:   # bias correction undefined (e.g. shuffled data)
    GAP = "gap"
    subj["gap_corrected"] = subj["gap"]
lines = ["EXPLORATORY ANALYSES" + (" - BLIND ANALYSIS, SHUFFLED DATA, MEANINGLESS" if SHUFFLED else ""),
         f"Best model: {best_model}; brain age gap = "
         + ("bias-corrected prediction - age" if GAP == "gap_corrected" else
            "UNCORRECTED prediction - age (bias correction undefined: model learned almost nothing about age)")
         + ", averaged over repeats", ""]
lines.append("All gap models include age as a covariate, as recommended for brain age gaps (de Lange & Cole, 2020).")
lines.append("1. Brain age gap ~ age + sex + site (after ComBat):")
lines.append(smf.ols("gap_corrected ~ age + C(sex) + C(site)", data=subj).fit().summary().tables[1].as_text())
nc = preds[(preds.analysis == "no_combat") & (preds.model == best_model)].groupby("row")[["age", "pred", "pred_corrected"]].mean()
nc = rows_used["no_combat"].loc[nc.index, ["site", "sex"]].join(nc)
nc["gap_corrected"] = nc["pred_corrected"] - nc["age"]
if GAP == "gap":
    nc["gap_corrected"] = nc["pred"] - nc["age"] if "pred" in nc else np.nan
lines += ["", "2. Brain age gap ~ age + sex + site (without ComBat):",
          smf.ols("gap_corrected ~ age + C(sex) + C(site)", data=nc).fit().summary().tables[1].as_text()]
lines += ["", "3. Brain age gap ~ age + CNR + site (image quality):",
          smf.ols("gap_corrected ~ age + cnr + C(site)", data=subj).fit().summary().tables[1].as_text()]
old = subj[subj.age >= 80]
lines += ["", f"4. Accuracy above age 80: n = {len(old)}; MAE (uncorrected) = "
          f"{np.mean(np.abs(old.pred - old.age)):.2f} years; mean gap (uncorrected) = {old.gap.mean():.2f}"
          if len(old) else "4. No scans aged 80 or over."]
(OUT / "brainage_exploratory.txt").write_text("\n".join(lines) + "\n")

# ---- Figure -----------------------------------------------------------------------------------------
# (scripts/12b_brainage_figure.py redraws this figure from the saved results, without re-running the models)
NAMES = {"baseline": "Baseline", "ridge": "Ridge", "random_forest": "Random Forest",
         "gradient_boosting": "Gradient Boosting"}
fig, ax = plt.subplots(1, 3, figsize=(15, 4.6))
lim = [subj.age.min() - 3, subj.age.max() + 3]
for a_, col, title in [(ax[0], "pred", "Predicted age (uncorrected)"),
                       (ax[1], "pred_corrected", "Predicted age (bias-corrected)")]:
    a_.scatter(subj.age, subj[col], s=8, alpha=0.5, color="#2f6db5")
    a_.plot(lim, lim, color="grey", lw=1, ls="--")
    a_.set(xlim=lim, ylim=lim, xlabel="Age (years)", ylabel="Predicted age (years)",
           title=f"{title}\n{NAMES[best_model]}, primary analysis")
s = summary[summary.analysis == "primary"].set_index("model").loc[list(MODELS)]
ax[2].bar([NAMES[m] for m in s.index], s["mae"], color=["#999999"] + ["#2f6db5"] * 3)
ax[2].set(ylabel="Mean absolute error (years)", title="Cross-validated MAE, uncorrected")
ax[2].tick_params(axis="x", rotation=20)
if SHUFFLED:
    fig.suptitle("BLIND ANALYSIS - shuffled data, results are meaningless", color="red", fontsize=13)
fig.tight_layout()
fig.savefig(OUT / "fig_brainage.png", dpi=150)

(OUT / "brainage_versions.txt").write_text(
    f"python {sys.version.split()[0]}\nnumpy {np.__version__}\npandas {pd.__version__}\n"
    f"scikit-learn {sklearn.__version__}\nscipy {scipy.__version__}\nmatplotlib {matplotlib.__version__}\n"
    f"seed {SEED}; repeats {REPEATS}; outer {OUTER}; inner {INNER}\n")

# ---- Console summary ----------------------------------------------------------------------------------
print(f"\n{'BLIND ANALYSIS (shuffled data) - results are meaningless' if SHUFFLED else 'REAL DATA'}")
print("Mean cross-validated MAE in years (primary analysis):")
print(s[["mae", "r", "mae_corrected"]].to_string())
print("\nH5 (best model beats the mean-age baseline):")
print(h5[["analysis", "best_model", "mae_best", "mae_baseline", "wilcoxon_p", "h5_supported"]]
      .round(3).to_string(index=False))
print("\nH6 (leave-one-site-out vs within-site; skill = 1 - MAE / baseline MAE):")
print(loso[["site", "n", "mae_leave_site_out", "mae_within_site", "skill_leave_site_out",
            "skill_within_site"]].round(3).to_string(index=False))
print(f"H6 pre-registered rule: {loso.h6_preregistered_rule.iloc[0]}   refined rule: {loso.h6_refined_rule.iloc[0]}")
if SHUFFLED:
    print("\nExpected on shuffled data: every model's MAE close to the baseline's, H5 FALSE.")
print(f"\nSaved in {OUT.relative_to(PROJECT)}/  ({(time.time() - t0) / 60:.1f} minutes)")
