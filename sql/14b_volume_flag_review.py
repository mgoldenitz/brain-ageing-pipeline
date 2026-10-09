"""
Step 4f - Review the scans with extreme subcortical volumes (run after 14_unblind.py,
before 09_build_dataset.py).

Why: the pre-registration's core QC rule is "a flag only triggers review; a scan is
excluded only for a confirmed processing failure". The unblinding report (section 5) flags
FIRST volumes more than 5 robust z from the median that were rated 0 or 1. The rating
snapshots colour each hemisphere in one shade, so a pallidum that has spread into the
putamen or internal capsule is hard to see there. This script redraws each flagged scan
with every structure outlined in its own colour, zoomed on the flagged structure.

What it does:
  1. Finds the flagged scans exactly as 14_unblind.py does: |robust z| > 5 for any of the
     15 FIRST volumes (rerun volumes where a rerun exists), subcortical rating 0 or 1.
  2. Draws qc/volume_review/<NN>_<subject>.png: axial, coronal and sagittal slices through
     the flagged structure, plain T1 on the left and coloured outlines on the right.
     The flagged structure's outline is drawn thicker. No age, sex or results are shown.
  3. Creates data/qc_volume_review.csv (subject, flagged, decision, note) for you to fill
     in: decision = keep or fail. An existing file is never overwritten (use --force).

Decision rule (same as the subcortical "2 = Fail" in QC_RATING_GUIDE.md):
  fail = the outline clearly leaves the structure (spreads into neighbouring tissue or
         another structure, misses most of it, or sits in the wrong place)
  keep = the outline follows the visible anatomy, even if the structure itself is
         unusually large or small (that may be real anatomy, e.g. atrophy)
Decide from the image alone.

Then scripts/09_build_dataset.py reads the file: "fail" sets that scan's subcortical
rating to 2 (subcortical volumes missing; whole-brain volumes kept, exclusion rule 3).

Usage, from the project folder, inside WSL:
  ~/brainenv/bin/python scripts/14b_volume_flag_review.py
(needs nibabel: ~/brainenv/bin/pip install nibabel)
"""

from pathlib import Path
import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

try:
    import nibabel as nib
except ImportError:
    sys.exit("nibabel is not installed. Run:  ~/brainenv/bin/pip install nibabel")

PROJECT = Path(__file__).resolve().parent.parent
DATA = PROJECT / "data"
WORK = Path(os.environ.get("IXI_WORK", Path.home() / "ixi" / "work"))
OUT = PROJECT / "qc" / "volume_review"
REVIEW = DATA / "qc_volume_review.csv"
FORCE = "--force" in sys.argv
Z_LIMIT = 5

SUB = ["L_Thal", "L_Caud", "L_Puta", "L_Pall", "L_Hipp", "L_Amyg", "L_Accu",
       "R_Thal", "R_Caud", "R_Puta", "R_Pall", "R_Hipp", "R_Amyg", "R_Accu", "BrStem"]
LABEL = {"L_Thal": 10, "L_Caud": 11, "L_Puta": 12, "L_Pall": 13, "BrStem": 16, "L_Hipp": 17,
         "L_Amyg": 18, "L_Accu": 26, "R_Thal": 49, "R_Caud": 50, "R_Puta": 51, "R_Pall": 52,
         "R_Hipp": 53, "R_Amyg": 54, "R_Accu": 58}
COLOUR = {"Thal": "#3b82f6", "Caud": "#22d3ee", "Puta": "#e040fb", "Pall": "#facc15",
          "Hipp": "#22c55e", "Amyg": "#fb923c", "Accu": "#ffffff", "BrStem": "#ef4444"}
NAME = {"Thal": "thalamus", "Caud": "caudate", "Puta": "putamen", "Pall": "pallidum",
        "Hipp": "hippocampus", "Amyg": "amygdala", "Accu": "accumbens", "BrStem": "brainstem"}


def kind(s):
    return s if s == "BrStem" else s[2:]


def robust_z(x):
    med = x.median()
    return (x - med) / ((x - med).abs().median() * 1.4826)


# ---- 1. Flagged scans (same rule as 14_unblind.py section 5) -----------------------------
if not (DATA / "qc_final.csv").exists():
    sys.exit("data/qc_final.csv not found - run scripts/14_unblind.py first.")
strip = lambda c: c[:-4] if c.endswith("_mm3") else c
vols = pd.read_csv(DATA / "volumes.csv").rename(columns=strip).set_index("subject")
rerun = pd.read_csv(DATA / "volumes_first_rerun.csv").rename(columns=strip).set_index("subject")
vols.loc[rerun.index, SUB] = rerun[SUB]
qc = pd.read_csv(DATA / "qc_final.csv").set_index("subject")
z = vols[SUB].apply(robust_z)

flags = {}
for s in z.index:
    if qc.loc[s, "qc_sc"] >= 2:
        continue
    hit = [c for c in SUB if abs(z.loc[s, c]) > Z_LIMIT]
    if hit:
        flags[s] = hit
flagged = sorted(flags, key=lambda s: -z.loc[s, flags[s]].abs().max())
print(f"{len(flagged)} scans with a volume beyond +/-{Z_LIMIT} robust z and subcortical rating 0 or 1")

# ---- 2. Images -----------------------------------------------------------------------------
OUT.mkdir(parents=True, exist_ok=True)


def load(subject):
    folder = WORK / subject
    seg = folder / "first2_all_fast_firstseg.nii.gz"
    source = "rerun"
    if not seg.exists():
        seg, source = folder / "first_all_fast_firstseg.nii.gz", "original"
    t1 = nib.as_closest_canonical(nib.load(str(folder / "T1.nii.gz")))
    sg = nib.as_closest_canonical(nib.load(str(seg)))
    return (np.asarray(t1.dataobj, dtype=np.float32), np.asarray(sg.dataobj).astype(np.int16),
            t1.header.get_zooms()[:3], source)


def show(ax, t1, seg, axis, idx, zooms, centre_mm, half_fov, thick, vmin, vmax):
    """One slice; axis 0 = sagittal, 1 = coronal, 2 = axial (RAS voxel order)."""
    take = lambda a: np.take(a, idx, axis=axis)
    dims = [d for d in range(3) if d != axis]          # horizontal, vertical
    img, lab = take(t1), take(seg)
    h, v = dims
    extent = [0, img.shape[0] * zooms[h], 0, img.shape[1] * zooms[v]]
    for a in ax:
        a.imshow(img.T, cmap="gray", origin="lower", extent=extent, vmin=vmin, vmax=vmax,
                 interpolation="nearest")
        a.set_xlim(centre_mm[h] - half_fov, centre_mm[h] + half_fov)
        a.set_ylim(centre_mm[v] - half_fov, centre_mm[v] + half_fov)
        a.set_xticks([]); a.set_yticks([])
        a.set_facecolor("black")
    for name, lv in LABEL.items():
        m = (lab == lv)
        if m.any():
            ax[1].contour(m.T.astype(float), levels=[0.5], origin="lower", extent=extent,
                          colors=COLOUR[kind(name)], linewidths=2.6 if name in thick else 1.0)
    if axis in (1, 2):                                   # left-right on the horizontal axis
        for a in ax:
            a.text(0.02, 0.03, "L", color="white", transform=a.transAxes, fontsize=10)
            a.text(0.95, 0.03, "R", color="white", transform=a.transAxes, fontsize=10)


rows = []
for n, s in enumerate(flagged, 1):
    hit = flags[s]
    label = "; ".join(f"{c} {vols.loc[s, c] / 1000:.2f} cm3 (z {z.loc[s, c]:+.1f})" for c in hit)
    rows.append(dict(subject=s, flagged=label, decision="", note=""))
    try:
        t1, seg, zooms, source = load(s)
    except FileNotFoundError as e:
        print(f"  {s}: image files not found ({e.filename}) - skipped")
        continue
    brain = t1[t1 > 0]
    vmin, vmax = np.percentile(brain, [1, 99.5])
    # One block of views per flagged structure type (L and R together)
    blocks = []
    for k in dict.fromkeys(kind(c) for c in hit):
        names = [c for c in hit if kind(c) == k]
        mask = np.isin(seg, [LABEL[c] for c in names])
        if not mask.any():
            continue
        com = np.array(np.nonzero(mask)).mean(axis=1)
        views = [(2, "axial"), (1, "coronal")]
        for c in names:                                  # a sagittal slice through each side
            cm = np.array(np.nonzero(seg == LABEL[c])).mean(axis=1)
            views.append((0, f"sagittal {c[:1] if c != 'BrStem' else ''}".strip(), cm))
        blocks.append((k, names, com, views))
    nrow = sum(len(b[3]) for b in blocks)
    fig, axes = plt.subplots(nrow, 2, figsize=(9, 4.3 * nrow), facecolor="black")
    axes = np.atleast_2d(axes)
    r = 0
    for k, names, com, views in blocks:
        half = 55 if k == "BrStem" else 40
        for view in views:
            axis, title = view[0], view[1]
            cvox = view[2] if len(view) > 2 else com
            centre_mm = cvox * np.array(zooms)
            show(axes[r], t1, seg, axis, int(round(cvox[axis])), zooms, centre_mm, half,
                 set(names), vmin, vmax)
            axes[r, 0].set_ylabel(f"{NAME[k]}\n{title}", color="white", fontsize=11)
            r += 1
    axes[0, 0].set_title("T1", color="white")
    axes[0, 1].set_title("FIRST outlines (flagged structure thicker)", color="white")
    handles = [Line2D([], [], color=c, lw=2, label=NAME[k]) for k, c in COLOUR.items()]
    fig.legend(handles=handles, loc="lower center", ncol=4, facecolor="black", labelcolor="white",
               frameon=False, fontsize=9)
    fig.suptitle(f"{n}. {s}   ({source} FIRST)\nflagged: {label}", color="yellow", fontsize=11)
    fig.tight_layout(rect=(0, 0.04, 1, 0.97))
    path = OUT / f"{n:02d}_{s}.png"
    fig.savefig(path, dpi=110, facecolor="black")
    plt.close(fig)
    print(f"  {n:2d}. {s}  ->  {path.relative_to(PROJECT)}")

# ---- 3. Decision sheet -------------------------------------------------------------------
if REVIEW.exists() and not FORCE:
    print(f"\n{REVIEW.relative_to(PROJECT)} already exists - not overwritten (use --force to start again).")
else:
    pd.DataFrame(rows).to_csv(REVIEW, index=False, lineterminator="\n")
    print(f"\nFill in {REVIEW.relative_to(PROJECT)}: decision = keep or fail for every row.")
print("Rule: fail only if the outline clearly leaves the structure; an unusual size alone is not a failure.")
print("Then run:  ~/brainenv/bin/python scripts/09_build_dataset.py")
