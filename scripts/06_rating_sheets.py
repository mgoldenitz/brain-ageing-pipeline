"""
Step 4b - Build blinded rating sheets for the visual QC.

Every scan gets a random 4-digit code and the scans are shuffled, so when you rate them
you can't see the subject ID, hospital, age or whether the automatic checks flagged it.

For each scan the sheet shows three images (all made earlier by FSL):
  1. Brain mask outline on the head    (qc/<subject>_bet.png)        -> whole-brain rating
  2. Grey-matter map                   (qc/<subject>_gm.png)         -> whole-brain rating
  3. FIRST subcortical outlines        (qc/first_all/<subject>_first.png) -> subcortical rating

Three sets of sheets are made in one go, each with its own codes:
  practice  qc/rating/practice_NN.jpg  24 random scans to calibrate on first (ratings not used)
  main      qc/rating/sheet_NN.jpg     all scans, 6 per sheet
  retest    qc/rating/retest_NN.jpg    50 random scans to rate again at least a week later
                                       (test-retest agreement, Cohen's kappa)

Files written:
  data/qc_key.csv                 code -> subject. DO NOT OPEN until all rating is finished.
  data/qc_ratings.csv             fill in for the main sheets
  data/qc_ratings_practice.csv    fill in for the practice sheets
  data/qc_ratings_retest.csv      fill in for the retest sheets
Rating rules: QC_RATING_GUIDE.md

Run from the project folder, after scripts/05_qc_images_metrics.sh has finished:
  python3 scripts/06_rating_sheets.py
The key and rating files are never overwritten once they exist (so your ratings are safe).
Use --force only to start again from scratch before any rating has been done.
"""

from pathlib import Path
import csv
import random
import sys

from PIL import Image, ImageDraw, ImageFont

PROJECT = Path(__file__).resolve().parent.parent
DATA, QC = PROJECT / "data", PROJECT / "qc"
OUTDIR = QC / "rating"
SEED = 20261005
PER_SHEET = 6           # 2 columns x 3 rows
N_PRACTICE, N_RETEST = 24, 50
BLOCK_W = 1280          # width of one scan's block in pixels
FORCE = "--force" in sys.argv

subjects = [s.strip() for s in (DATA / "all_subjects.txt").read_text().splitlines() if s.strip()]

def images_for(s):
    return [QC / f"{s}_bet.png", QC / f"{s}_gm.png", QC / "first_all" / f"{s}_first.png"]

missing = [s for s in subjects if not all(p.exists() for p in images_for(s))]
if missing:
    sys.exit(f"{len(missing)} scans are missing images (first: {missing[0]}). "
             "Run scripts/05_qc_images_metrics.sh on data/all_subjects.txt first.")

key_file = DATA / "qc_key.csv"
rating_files = {"main": DATA / "qc_ratings.csv",
                "practice": DATA / "qc_ratings_practice.csv",
                "retest": DATA / "qc_ratings_retest.csv"}
if key_file.exists() and not FORCE:
    sys.exit("data/qc_key.csv already exists, so the sheets have been made. Nothing changed. "
             "(Use --force to start again, but only if no rating has been done yet.)")
if FORCE:
    started = [f.name for f in rating_files.values() if f.exists()
               and any(r.get("whole_brain_rating") for r in csv.DictReader(f.open()))]
    if started:
        sys.exit(f"Ratings already entered in {', '.join(started)}. Not overwriting.")

# ---- codes and order
rng = random.Random(SEED)
sets = {"practice": rng.sample(subjects, N_PRACTICE),
        "main": rng.sample(subjects, len(subjects)),       # every scan, shuffled
        "retest": rng.sample(subjects, N_RETEST)}
total = sum(len(v) for v in sets.values())
codes = iter(rng.sample(range(1000, 10000), total))        # unique across all three sets

try:
    font = ImageFont.truetype("DejaVuSans-Bold.ttf", 40)
    small = ImageFont.truetype("DejaVuSans.ttf", 24)
except OSError:
    font = small = ImageFont.load_default()

def fit(img, width):
    return img.resize((width, round(img.height * width / img.width)))

def scan_block(s, code):
    bet, gm, first = (Image.open(p).convert("RGB") for p in images_for(s))
    half = BLOCK_W // 2
    bet, gm, first = fit(bet, half), fit(gm, half), fit(first, BLOCK_W)
    label_h = 60
    h = label_h + max(bet.height, gm.height) + first.height + 20
    block = Image.new("RGB", (BLOCK_W, h), "black")
    d = ImageDraw.Draw(block)
    d.text((10, 8), f"Scan {code}", fill="yellow", font=font)
    d.text((BLOCK_W - 560, 18), "mask | grey matter  /  FIRST outlines", fill="grey", font=small)
    block.paste(bet, (0, label_h))
    block.paste(gm, (half, label_h))
    block.paste(first, (0, label_h + max(bet.height, gm.height) + 10))
    return block

OUTDIR.mkdir(parents=True, exist_ok=True)
prefix = {"practice": "practice", "main": "sheet", "retest": "retest"}
key_rows = []
for set_name, subs in sets.items():
    rating_rows = []
    for i in range(0, len(subs), PER_SHEET):
        sheet_no = i // PER_SHEET + 1
        blocks = []
        for s in subs[i:i + PER_SHEET]:
            code = next(codes)
            key_rows.append({"code": code, "set": set_name, "sheet": sheet_no, "subject": s})
            rating_rows.append({"code": code, "sheet": sheet_no, "whole_brain_rating": "",
                                "subcortical_rating": "", "note": ""})
            blocks.append(scan_block(s, code))
        row_h = max(b.height for b in blocks)
        sheet = Image.new("RGB", (BLOCK_W * 2 + 20, row_h * 3 + 40), (40, 40, 40))
        for j, b in enumerate(blocks):
            sheet.paste(b, ((j % 2) * (BLOCK_W + 20), (j // 2) * (row_h + 20)))
        sheet.save(OUTDIR / f"{prefix[set_name]}_{sheet_no:02d}.jpg", quality=92)
        print(f"  {prefix[set_name]}_{sheet_no:02d}.jpg", flush=True)
    with rating_files[set_name].open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["code", "sheet", "whole_brain_rating", "subcortical_rating", "note"], lineterminator="\n")
        w.writeheader()
        w.writerows(rating_rows)
    print(f"{set_name:9s} {len(subs):4d} scans -> qc/rating/{prefix[set_name]}_NN.jpg, "
          f"ratings in {rating_files[set_name].relative_to(PROJECT)}")

with key_file.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["code", "set", "sheet", "subject"], lineterminator="\n")
    w.writeheader()
    w.writerows(key_rows)
print("Key saved to data/qc_key.csv - don't open it until all rating is finished.")
