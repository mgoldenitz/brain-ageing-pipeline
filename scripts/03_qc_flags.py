"""
Step 3 - Automated quality control.

Flags scans whose FSL outputs look wrong, using four rules:
  1. first_failed     FIRST produced no subcortical volumes
  2. implausible      a subcortical structure is zero, or a hippocampus is under 2,000 mm3
  3. asymmetry        a structure's left-right difference is extreme compared with everyone
                      else (robust z beyond +/-3.5); small structures like the accumbens
                      vary a lot normally, so a fixed cut-off would over-flag them
  4. outlier          a global volume (GM, WM, CSF, total) is unusual for the person's
                      age, sex and site (robust z-score beyond +/-3.5)

Writes:
  data/qc_auto.csv            one row per scan: flags, reasons, auto status
  qc/sheets/review_sheet_NN.png  side-by-side BET + GM snapshots of every flagged scan
  qc/sheets/random_sheet_NN.png  a random sample of passing scans, to spot-check

Run from the project folder:  python3 scripts/03_qc_flags.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw

PROJECT = Path(__file__).resolve().parent.parent
DATA, QC = PROJECT / "data", PROJECT / "qc"
Z_LIMIT, HIPP_MIN, RANDOM_N = 3.5, 2000, 24
SHEETS = QC / "sheets"
SHEETS.mkdir(exist_ok=True)

vol = pd.read_csv(DATA / "volumes.csv")
demo = pd.read_csv(DATA / "participants.csv")[["subject", "site", "sex", "age"]]
df = vol.merge(demo, on="subject", how="left")

sub_cols = [c for c in vol.columns if c.startswith(("L_", "R_", "BrStem"))]
pairs = sorted({c[2:] for c in sub_cols if c.startswith("L_")})
reasons = {s: [] for s in df["subject"]}

# 1. FIRST failed
for s in df.loc[df[sub_cols].isna().any(axis=1), "subject"]:
    reasons[s].append("first_failed: no subcortical volumes")

# 2. Implausible subcortical values
for _, r in df.iterrows():
    for c in sub_cols:
        if pd.notna(r[c]) and r[c] <= 0:
            reasons[r.subject].append(f"implausible: {c.replace('_mm3','')} = 0")
    for side in ("L", "R"):
        v = r[f"{side}_Hipp_mm3"]
        if pd.notna(v) and v < HIPP_MIN:
            reasons[r.subject].append(f"implausible: {side} hippocampus {v:.0f} mm3")

# 3. Left-right asymmetry, judged against the whole sample
def robust_z(x):
    x = pd.Series(x, dtype=float)
    med = x.median()
    mad = (x - med).abs().median() * 1.4826
    return (x - med) / mad

for p in pairs:
    L, R = df[f"L_{p}"], df[f"R_{p}"]
    ai = (L - R) / ((L + R) / 2)          # signed asymmetry index
    z = robust_z(ai)
    for s, a, zi in zip(df["subject"], ai, z):
        if pd.notna(zi) and abs(zi) > Z_LIMIT:
            reasons[s].append(f"asymmetry: {p.replace('_mm3','')} {a:+.0%} (z = {zi:+.1f})")

# 4. Global volume outliers for age, sex and site (robust z of regression residuals)
df["total_mm3"] = df[["gm_mm3", "wm_mm3", "csf_mm3"]].sum(axis=1)
ok = df.dropna(subset=["age", "sex", "site"]).copy()
X = pd.get_dummies(ok[["sex", "site"]], drop_first=True).astype(float)
X["age"], X["age2"] = ok["age"], ok["age"] ** 2
X.insert(0, "const", 1.0)
for col in ["gm_mm3", "wm_mm3", "csf_mm3", "total_mm3"]:
    y = ok[col].to_numpy(float)
    beta, *_ = np.linalg.lstsq(X.to_numpy(), y, rcond=None)
    res = y - X.to_numpy() @ beta
    mad = np.median(np.abs(res - np.median(res))) * 1.4826
    z = (res - np.median(res)) / mad
    ok[f"z_{col}"] = z
    for s, zi in zip(ok["subject"], z):
        if abs(zi) > Z_LIMIT:
            reasons[s].append(f"outlier: {col.replace('_mm3','').upper()} z = {zi:+.1f}")
df = df.merge(ok[["subject"] + [c for c in ok.columns if c.startswith("z_")]], on="subject", how="left")

# Status: FIRST failures can still be used for whole-brain analyses
def status(rs):
    if not rs:
        return "pass"
    if all(r.startswith(("first_failed", "implausible", "asymmetry")) for r in rs):
        return "review_subcortical"
    return "review"

df["qc_reasons"] = df["subject"].map(lambda s: "; ".join(reasons[s]))
df["qc_auto"] = df["subject"].map(lambda s: status(reasons[s]))
out = df[["subject", "site", "sex", "age", "qc_auto", "qc_reasons"] + [c for c in df.columns if c.startswith("z_")]]
out = out.round(2)
out.to_csv(DATA / "qc_auto.csv", index=False)

# Contact sheets: one row per scan, BET snapshot left, GM snapshot right
def sheets(subjects, prefix, per_sheet=12):
    for old in SHEETS.glob(f"{prefix}_*.png"):
        try:
            old.unlink()
        except OSError:
            pass
    for k in range(0, len(subjects), per_sheet):
        chunk = subjects[k:k + per_sheet]
        rows = []
        for s in chunk:
            a, b = Image.open(QC / f"{s}_bet.png").convert("RGB"), Image.open(QC / f"{s}_gm.png").convert("RGB")
            w, h = a.size
            row = Image.new("RGB", (w * 2, h + 22), "black")
            row.paste(a, (0, 22)); row.paste(b, (w, 22))
            label = s + ("   " + "; ".join(reasons[s]) if reasons[s] else "")
            ImageDraw.Draw(row).text((6, 5), label[:150], fill="yellow")
            rows.append(row)
        sheet = Image.new("RGB", (rows[0].width, sum(r.height for r in rows)), "black")
        y = 0
        for r in rows:
            sheet.paste(r, (0, y)); y += r.height
        sheet.save(SHEETS / f"{prefix}_{k // per_sheet + 1:02d}.png")

flagged = out.loc[out["qc_auto"] != "pass", "subject"].tolist()
passing = out.loc[out["qc_auto"] == "pass", "subject"].sample(RANDOM_N, random_state=1).tolist()
sheets(flagged, "review_sheet")
sheets(passing, "random_sheet")

print(f"Scans checked: {len(out)}")
print(out["qc_auto"].value_counts().to_string())
print(f"\nFlagged scans ({len(flagged)}):")
print(out.loc[out["qc_auto"] != "pass", ["subject", "site", "age", "qc_auto", "qc_reasons"]].to_string(index=False))
print(f"\nReview sheets: qc/sheets/review_sheet_*.png   Spot-check sheets: qc/sheets/random_sheet_*.png")
