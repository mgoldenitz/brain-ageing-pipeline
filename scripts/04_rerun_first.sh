#!/usr/bin/env bash
# Step 3b - Rerun FIRST (subcortical segmentation) on scans flagged by 03_qc_flags.py.
#
# The first run gave FIRST the whole head. Here it gets the brain-extracted image
# (-b), which usually fixes failed registrations. Each scan also gets a QC image of
# the new subcortical outlines (qc/first/<subject>_first.png).
#
# Usage (from the project folder, inside WSL):
#   python3 -c "import pandas as pd; d=pd.read_csv('data/qc_auto.csv'); open('data/rerun_first.txt','w').write('\n'.join(d.loc[d.qc_auto=='review_subcortical','subject'])+'\n')"
#   nohup bash scripts/04_rerun_first.sh data/rerun_first.txt > logs/rerun_first.out 2>&1 &

set -u
LIST="${1:?Give a subject list, e.g. data/rerun_first.txt}"
WORK="$HOME/ixi/work"
PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
RESULTS="$PROJECT/data/volumes_first_rerun.csv"
QCDIR="$PROJECT/qc/first"
mkdir -p "$QCDIR" "$PROJECT/logs"

LABELS=(10 11 12 13 17 18 26 49 50 51 52 53 54 58 16)
NAMES=(L_Thal L_Caud L_Puta L_Pall L_Hipp L_Amyg L_Accu R_Thal R_Caud R_Puta R_Pall R_Hipp R_Amyg R_Accu BrStem)
[ -f "$RESULTS" ] || echo "subject,$(IFS=,; echo "${NAMES[*]}" | sed 's/[^,]*/&_mm3/g')" > "$RESULTS"

while read -r SUBJ; do
  [ -z "$SUBJ" ] && continue
  grep -q "^$SUBJ," "$RESULTS" && { echo "$(date '+%F %T')  $SUBJ already rerun, skipping"; continue; }
  OUT="$WORK/$SUBJ"; LOG="$PROJECT/logs/${SUBJ}_first_rerun.log"
  echo "$(date '+%F %T')  $SUBJ: rerunning FIRST"
  (
    set -e
    fslmaths "$OUT/T1" -mas "$OUT/T1_brain_mask" "$OUT/T1_brain"
    run_first_all -b -i "$OUT/T1_brain" -o "$OUT/first2"
    overlay 1 0 "$OUT/T1" -a "$OUT/first2_all_fast_firstseg" 1 60 "$OUT/first_overlay"
    slicer "$OUT/first_overlay" -S 6 1200 "$QCDIR/${SUBJ}_first.png"
  ) >> "$LOG" 2>&1
  SEG="$OUT/first2_all_fast_firstseg.nii.gz"
  if [ ! -f "$SEG" ] || grep -qi "error" "$LOG"; then
    echo "$(date '+%F %T')  $SUBJ: FIRST FAILED again, see $LOG"
    continue
  fi
  ROW="$SUBJ"
  for L in "${LABELS[@]}"; do
    ROW="$ROW,$(fslstats "$SEG" -l $((L - 1)).5 -u "$L".5 -V | awk '{print $2}')"
  done
  echo "$ROW" >> "$RESULTS"
  find "$OUT" -type f -name 'first2-*' -delete
  rm -f "$OUT/first_overlay.nii.gz"
  echo "$(date '+%F %T')  $SUBJ: done"
done < "$LIST"
echo "$(date '+%F %T')  Rerun finished. Results: $RESULTS"
