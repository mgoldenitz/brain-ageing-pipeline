#!/usr/bin/env bash
# Step 2 - Process T1 scans with FSL, one participant at a time.
#
# For each subject in the list:
#   reorient -> crop the neck -> brain extraction (BET) -> tissue segmentation (FAST)
#   -> subcortical segmentation (FIRST) -> QC snapshot images -> volumes into a CSV row
#
# Usage (from the project folder, inside WSL):
#   bash scripts/02_process_t1.sh data/pilot_subjects.txt
# Overnight, so it keeps running if the terminal closes:
#   nohup bash scripts/02_process_t1.sh data/pilot_subjects.txt > logs/pilot.out 2>&1 &
#
# Finished subjects are skipped on re-runs, so a crash or reboot just means running it again.

set -u

LIST="${1:?Give a subject list, e.g. data/pilot_subjects.txt}"
RAW="$HOME/ixi/raw"
WORK="$HOME/ixi/work"
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
RESULTS="$PROJECT/data/volumes.csv"
QCDIR="$PROJECT/qc"
LOGDIR="$PROJECT/logs"
mkdir -p "$WORK" "$QCDIR" "$LOGDIR"

command -v bet >/dev/null || { echo "FSL not found. Open a new Ubuntu terminal after installing FSL."; exit 1; }

# FIRST labels: left and right thalamus, caudate, putamen, pallidum, hippocampus, amygdala, accumbens, plus brainstem
LABELS=(10 11 12 13 17 18 26 49 50 51 52 53 54 58 16)
NAMES=(L_Thal L_Caud L_Puta L_Pall L_Hipp L_Amyg L_Accu R_Thal R_Caud R_Puta R_Pall R_Hipp R_Amyg R_Accu BrStem)

if [ ! -f "$RESULTS" ]; then
  echo "subject,gm_mm3,wm_mm3,csf_mm3,$(IFS=,; echo "${NAMES[*]}" | sed 's/[^,]*/&_mm3/g')" > "$RESULTS"
fi

# Volume of a FAST partial-volume map: mean value x total volume (fslstats -M -V)
pve_volume () { fslstats "$1" -M -V | awk '{printf "%.0f", $1 * $3}'; }

while read -r SUBJ; do
  [ -z "$SUBJ" ] && continue
  if grep -q "^$SUBJ," "$RESULTS"; then
    echo "$(date '+%F %T')  $SUBJ already done, skipping"
    continue
  fi

  IN="$RAW/${SUBJ}-T1.nii.gz"
  OUT="$WORK/$SUBJ"
  LOG="$LOGDIR/$SUBJ.log"
  mkdir -p "$OUT"
  [ -f "$IN" ] || { echo "$(date '+%F %T')  $SUBJ: input missing ($IN)"; continue; }

  echo "$(date '+%F %T')  $SUBJ: started"
  (
    set -e
    fslreorient2std "$IN" "$OUT/T1_reor"
    robustfov -i "$OUT/T1_reor" -r "$OUT/T1"                 # crop the neck so BET works well
    bet "$OUT/T1" "$OUT/T1_brain" -R -f 0.5 -m                # brain extraction + mask
    fast -t 1 -n 3 -o "$OUT/fast" "$OUT/T1_brain"             # pve_0 = CSF, pve_1 = GM, pve_2 = WM
    run_first_all -i "$OUT/T1" -o "$OUT/first"                # subcortical structures

    # QC snapshots: brain mask outline on the head, and the GM map
    slicer "$OUT/T1" "$OUT/T1_brain_mask" -a "$QCDIR/${SUBJ}_bet.png"
    slicer "$OUT/T1" "$OUT/fast_pve_1" -a "$QCDIR/${SUBJ}_gm.png"
  ) >> "$LOG" 2>&1
  if [ $? -ne 0 ]; then
    echo "$(date '+%F %T')  $SUBJ: FAILED, see $LOG"
    continue
  fi

  GM=$(pve_volume "$OUT/fast_pve_1")
  WM=$(pve_volume "$OUT/fast_pve_2")
  CSF=$(pve_volume "$OUT/fast_pve_0")
  SEG="$OUT/first_all_fast_firstseg"
  SUB=""
  for L in "${LABELS[@]}"; do
    V=$(fslstats "$SEG" -l $((L - 1)).5 -u "$L".5 -V | awk '{print $2}')
    SUB="$SUB,$V"
  done
  echo "$SUBJ,$GM,$WM,$CSF$SUB" >> "$RESULTS"

  # Keep the outputs needed later; delete bulky intermediates
  # Keep only what QC or later steps need: the cropped T1, brain mask, tissue maps and subcortical labels
  find "$OUT" -type f ! -name 'T1.nii.gz' ! -name 'T1_brain_mask.nii.gz' \
       ! -name 'fast_pve_*.nii.gz' ! -name 'first_all_fast_firstseg.nii.gz' -delete
  echo "$(date '+%F %T')  $SUBJ: done (GM $GM, WM $WM, CSF $CSF mm3)"
done < "$LIST"

echo "$(date '+%F %T')  All subjects in $LIST processed. Results: $RESULTS"
