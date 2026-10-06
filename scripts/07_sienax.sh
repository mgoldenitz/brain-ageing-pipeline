#!/usr/bin/env bash
# Step 4c - Head size: SIENAX volumetric scaling factor for every scan.
#
# SIENAX registers each brain to the MNI152 template using the skull to constrain
# scaling. Its VSCALING factor is the inverse of head size: multiply a volume by it to
# express that volume as if every head were the template's size. Intracranial volume is
# estimated as (template brain volume) / VSCALING.
#
# Usage (from the project folder, inside WSL), best overnight:
#   nohup bash scripts/07_sienax.sh data/all_subjects.txt > logs/sienax.out 2>&1 &
# Runs several subjects at once (half the CPU cores). Finished subjects are skipped.

set -u
LIST="${1:?Give a subject list, e.g. data/all_subjects.txt}"
export WORK="$HOME/ixi/work"
export PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$PROJECT/data/sienax" "$PROJECT/logs"
JOBS=$(( $(nproc) / 2 )); [ "$JOBS" -lt 1 ] && JOBS=1

one_subject () {
  S="$1"; OUT="$WORK/$S"; RES="$PROJECT/data/sienax/$S.csv"
  [ -s "$RES" ] && return 0
  echo "$(date '+%F %T')  $S: started"
  rm -rf "$OUT/sienax"
  sienax "$OUT/T1" -o "$OUT/sienax" -B "-f 0.5 -R" >> "$PROJECT/logs/${S}_sienax.log" 2>&1
  REP="$OUT/sienax/report.sienax"
  if [ -f "$REP" ] && grep -q VSCALING "$REP"; then
    VS=$(awk '/VSCALING/{print $2}' "$REP")
    echo "$S,$VS" > "$RES"
    cp "$REP" "$PROJECT/logs/${S}_report.sienax"
    rm -rf "$OUT/sienax"                       # keep only the report
    echo "$(date '+%F %T')  $S: done (vscaling $VS)"
  else
    echo "$(date '+%F %T')  $S: FAILED, see logs/${S}_sienax.log"
  fi
}
export -f one_subject

echo "$(date '+%F %T')  Starting with $JOBS parallel jobs"
grep -v '^$' "$LIST" | xargs -P "$JOBS" -I{} bash -c 'one_subject "$@"' _ {}

# Combine, and estimate intracranial volume from the template brain mask volume
TEMPLATE_VOL=$(fslstats "$FSLDIR/data/standard/MNI152_T1_1mm_brain_mask" -V | awk '{print $2}')
{ echo "subject,vscaling,icv_mm3"; awk -F, -v t="$TEMPLATE_VOL" '{printf "%s,%s,%.0f\n", $1, $2, t/$2}' "$PROJECT"/data/sienax/*.csv; } > "$PROJECT/data/head_size.csv"
echo "$(date '+%F %T')  Finished. Results: data/head_size.csv"
