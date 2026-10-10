"""
Step 11 - Brain image figures for the README and LinkedIn (presentation only; no analysis).

Draws two figures from the FSL outputs already in ~/ixi/work:

  results/real/fig_qc_good_vs_failed.png
      A scan rated good beside one of the confirmed subcortical failures from the extreme-
      volume review (data/qc_volume_review.csv), on skull-stripped axial and coronal slices
      through the pallidum, with every FIRST structure outlined in its own colour.

  results/real/fig_pipeline_steps.png
      The processing steps on one axial slice, above the eyes, of the good scan:
      T1 scan -> brain extracted (BET) -> tissue segmented (FAST) -> subcortical outlines (FIRST).

Privacy: no face is shown (the only unstripped frame is an axial slice through the basal
ganglia, which lies above the eyes), and no subject ID, age, sex or site appears in either
figure. IXI data are CC BY-SA 3.0; the README credits the dataset.

Choice of scans (made from QC data only, never from age, sex or results):
  failed - IXI131-HH-1527, the largest pallidum flag in the review (decision = fail).
  good   - the Hammersmith scan (same scanner as the failure) rated 0 for both whole-brain
           and subcortical QC whose 18 volumes are closest to the sample median.

Usage, from the project folder, inside WSL:
  ~/brainenv/bin/python scripts/17_brain_image_figures.py
"""

from pathlib import Path
import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

try:
    import nibabel as nib
except ImportError:
    sys.exit("nibabel is not installed. Run:  ~/brainenv/bin/pip install nibabel")

PROJECT = Path(__file__).resolve().parent.parent
DATA = PROJECT / "data"
WORK = Path(os.environ.get("IXI_WORK", Path.home() / "ixi" / "work"))
OUT = PROJECT / "results" / "real"
FAILED = "IXI131-HH-1527"

SUB = ["L_Thal", "L_Caud", "L_Puta", "L_Pall", "L_Hipp", "L_Amyg", "L_Accu",
       "R_Thal", "R_Caud", "R_Puta", "R_Pall", "R_Hipp", "R_Amyg", "R_Accu", "BrStem"]
LABEL = {"L_Thal": 10, "L_Caud": 11, "L_Puta": 12, "L_Pall": 13, "BrStem": 16, "L_Hipp": 17,
         "L_Amyg": 18, "L_Accu": 26, "R_Thal": 49, "R_Caud": 50, "R_Puta": 51, "R_Pall": 52,
         "R_Hipp": 53, "R_Amyg": 54, "R_Accu": 58}
COLOUR = {"Thal": "#3b82f6", "Caud": "#22d3ee", "Puta": "#e040fb", "Pall": "#facc15",
          "Hipp": "#22c55e", "Amyg": "#fb923c", "Accu": "#ffffff", "BrStem": "#ef4444"}
NAME = {"Thal": "Thalamus", "Caud": "Caudate", "Puta": "Putamen", "Pall": "Pallidum",
        "Hipp": "Hippocampus", "Amyg": "Amygdala", "Accu": "Accumbens", "BrStem": "Brainstem"}
TISSUE = ["#000000", "#4f9fd9", "#9b9b9b", "#f2f2f2"]   # background, CSF, grey, white matter
BG, FG = "black", "white"

kind = lambda s: s if s == "BrStem" else s[2:]


def robust_z(x):
    med = x.median()
    return (x - med) / ((x - med).abs().median() * 1.4826)


# ---- Choose the good scan --------------------------------------------------------------
strip = lambda c: c[:-4] if c.endswith("_mm3") else c
vols = pd.read_csv(DATA / "volumes.csv").rename(columns=strip).set_index("subject")
rerun = pd.read_csv(DATA / "volumes_first_rerun.csv").rename(columns=strip).set_index("subject")
vols.loc[rerun.index, SUB] = rerun[SUB]
qc = pd.read_csv(DATA / "qc_final.csv").set_index("subject")
review = pd.read_csv(DATA / "qc_volume_review.csv").set_index("subject")
if review.loc[FAILED, "decision"] != "fail":
    sys.exit(f"{FAILED} is not marked 'fail' in data/qc_volume_review.csv")

z = vols[["gm", "wm", "csf"] + SUB].apply(robust_z).abs().max(axis=1)
ok = qc[(qc.qc_wb == 0) & (qc.qc_sc == 0)].index
ok = [s for s in ok if "-HH-" in s and s in z.index and s not in review.index]
ok = [s for s in sorted(ok, key=lambda s: z[s]) if (WORK / s / "T1.nii.gz").exists()]
if not ok:
    sys.exit(f"No good scan found with image files in {WORK}")
GOOD = ok[0]
print(f"good scan: {GOOD} (largest |robust z| {z[GOOD]:.2f});  failed scan: {FAILED}")


# ---- Image helpers ---------------------------------------------------------------------
def load(subject):
    d = WORK / subject
    rd = lambda f: nib.as_closest_canonical(nib.load(str(d / f)))
    t1 = rd("T1.nii.gz")
    seg_file = "first2_all_fast_firstseg.nii.gz"
    if not (d / seg_file).exists():
        seg_file = "first_all_fast_firstseg.nii.gz"
    img = dict(t1=np.asarray(t1.dataobj, np.float32),
               mask=np.asarray(rd("T1_brain_mask.nii.gz").dataobj) > 0,
               seg=np.asarray(rd(seg_file).dataobj).astype(np.int16),
               zooms=np.array(t1.header.get_zooms()[:3]))
    pve = [np.asarray(rd(f"fast_pve_{i}.nii.gz").dataobj, np.float32) for i in range(3)]
    stack = np.stack(pve)
    img["tissue"] = np.where(stack.max(0) > 0.1, stack.argmax(0) + 1, 0)   # 1 CSF, 2 GM, 3 WM
    brain = img["t1"][img["mask"]]
    img["vmin"], img["vmax"] = np.percentile(brain, [1, 99.5])
    img["brain"] = np.where(img["mask"], img["t1"], 0)
    print(f"  {subject}: segmentation {seg_file}")
    return img


def sl(vol, axis, idx):
    """2-D slice, transposed for imshow(origin='lower'); axis 1 = coronal, 2 = axial."""
    return np.take(vol, idx, axis=axis).T


def extent(img, axis):
    h, v = [d for d in range(3) if d != axis]
    sh, z = img["t1"].shape, img["zooms"]
    return [0, sh[h] * z[h], 0, sh[v] * z[v]]


def centre(mask, img):
    return np.array(np.nonzero(mask)).mean(axis=1)


def frame(ax, img, axis, idx, layer="brain", outlines=False, lw=1.3, zoom=None, fill=False):
    ext = extent(img, axis)
    if layer == "tissue":
        ax.imshow(sl(img["tissue"], axis, idx), cmap=ListedColormap(TISSUE), vmin=0, vmax=3,
                  origin="lower", extent=ext, interpolation="nearest")
    else:
        ax.imshow(sl(img[layer], axis, idx), cmap="gray", origin="lower", extent=ext,
                  vmin=img["vmin"], vmax=img["vmax"], interpolation="bilinear")
    if outlines:
        lab = sl(img["seg"], axis, idx)
        for name, lv in LABEL.items():
            m = lab == lv
            if m.any():
                if fill:
                    ax.imshow(np.ma.masked_where(~m, m), cmap=ListedColormap([COLOUR[kind(name)]]),
                              alpha=0.45, origin="lower", extent=ext, interpolation="nearest")
                ax.contour(m.astype(float), levels=[0.5], origin="lower", extent=ext,
                           colors=COLOUR[kind(name)], linewidths=lw)
    if zoom is not None:
        (cx, cy), half = zoom
        ax.set_xlim(cx - half, cx + half); ax.set_ylim(cy - half, cy + half)
    ax.set_xticks([]); ax.set_yticks([]); ax.set_facecolor(BG)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.text(0.03, 0.04, "L", color=FG, transform=ax.transAxes, fontsize=9, alpha=.8)
    ax.text(0.93, 0.04, "R", color=FG, transform=ax.transAxes, fontsize=9, alpha=.8)


def brain_box(img, axis, idx, margin=6):
    """Square field of view around the head/brain on this slice (mm)."""
    m = sl(img["t1"] > img["vmin"], axis, idx)
    h, v = [d for d in range(3) if d != axis]
    ys, xs = np.nonzero(m)
    zh, zv = img["zooms"][h], img["zooms"][v]
    x0, x1, y0, y1 = xs.min() * zh, xs.max() * zh, ys.min() * zv, ys.max() * zv
    half = max(x1 - x0, y1 - y0) / 2 + margin
    return ((x0 + x1) / 2, (y0 + y1) / 2), half


legend_handles = [Line2D([], [], color=c, lw=2.5, label=NAME[k]) for k, c in COLOUR.items()
                  if k not in ("BrStem",)]

good, bad = load(GOOD), load(FAILED)
OUT.mkdir(parents=True, exist_ok=True)

# ---- Figure 1: good vs failed ----------------------------------------------------------
fig, axes = plt.subplots(2, 2, figsize=(9, 11), facecolor=BG)
for col, (img, title) in enumerate([(good, "Rated good"),
                                    (bad, "Failed: pallidum outline leaks")]):
    pall = np.isin(img["seg"], [LABEL["L_Pall"], LABEL["R_Pall"]])
    c = centre(pall, img)
    cmm = c * img["zooms"]
    for row, axis in enumerate([2, 1]):                     # axial, coronal
        h, v = [d for d in range(3) if d != axis]
        frame(axes[row, col], img, axis, int(round(c[axis])), outlines=True, lw=1.6,
              zoom=((cmm[h], cmm[v] + (8 if axis == 1 else 0)), 42))
    axes[0, col].set_title(title, color="#f87171" if col else "#86efac", fontsize=14, pad=10,
                           fontweight="bold")
for row, name in enumerate(["Axial", "Coronal"]):
    axes[row, 0].set_ylabel(name, color=FG, fontsize=12, labelpad=8)
fig.legend(handles=legend_handles, loc="lower center", ncol=4, frameon=False,
           labelcolor=FG, fontsize=10.5, handlelength=1.6, bbox_to_anchor=(0.5, 0.07))
fig.suptitle("Subcortical segmentation quality control (FSL FIRST)", color=FG, fontsize=15, y=0.975)
fig.text(0.5, 0.025, "Skull-stripped T1 slices through the pallidum. Left: outlines follow the anatomy. "
         "Right: the pallidum (yellow)\nspreads beyond the structure, to about 2.7 times the median volume. "
         "Subcortical volumes from this scan were excluded.",
         ha="center", color="#bdbdbd", fontsize=9)
fig.subplots_adjust(left=0.07, right=0.98, top=0.89, bottom=0.15, wspace=0.06, hspace=0.06)
p1 = OUT / "fig_qc_good_vs_failed.png"
fig.savefig(p1, dpi=150, facecolor=BG)
plt.close(fig)
print(f"saved {p1.relative_to(PROJECT)}")

# ---- Figure 2: processing steps --------------------------------------------------------
img = good
deep = np.isin(img["seg"], [LABEL[s] for s in ("L_Puta", "R_Puta", "L_Thal", "R_Thal")])
k = int(round(centre(deep, img)[2]))                         # axial slice through the basal ganglia
box = brain_box(img, 2, k)
steps = [("1. MRI scan\n(T1-weighted)", dict(layer="t1")),
         ("2. Brain extracted\n(BET)", dict(layer="brain")),
         ("3. Tissue segmented\n(FAST)", dict(layer="tissue")),
         ("4. Subcortical structures\n(FIRST)", dict(layer="brain", outlines=True, lw=1.1, fill=True))]
fig, axes = plt.subplots(1, 4, figsize=(14, 4.8), facecolor=BG)
for ax, (title, kw) in zip(axes, steps):
    frame(ax, img, 2, k, zoom=box, **kw)
    ax.set_title(title, color=FG, fontsize=12.5, pad=8)
tissue_h = [Patch(color=TISSUE[i], label=l) for i, l in [(1, "CSF"), (2, "Grey matter"), (3, "White matter")]]
fig.legend(handles=tissue_h + legend_handles[:5], loc="lower center", ncol=8, frameon=False,
           labelcolor=FG, fontsize=10, handlelength=1.4)
fig.tight_layout(rect=(0, 0.08, 1, 0.97), w_pad=2.5)
for a, b in zip(axes[:-1], axes[1:]):                         # arrows between frames, after layout
    pa, pb = a.get_position(), b.get_position()
    y = (pa.y0 + pa.y1) / 2
    fig.add_artist(matplotlib.patches.FancyArrowPatch(
        (pa.x1 + 0.004, y), (pb.x0 - 0.004, y), transform=fig.transFigure,
        arrowstyle="-|>", mutation_scale=14, color="#9ca3af"))
p2 = OUT / "fig_pipeline_steps.png"
fig.savefig(p2, dpi=150, facecolor=BG)
plt.close(fig)
print(f"saved {p2.relative_to(PROJECT)}")
