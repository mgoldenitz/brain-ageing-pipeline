#!/usr/bin/env bash
# Step 4a - QC images and image-quality metrics for every scan.
#
# For each subject:
#   * FIRST outline image (qc/first_all/<subject>_first.png): six slices through the deep
#     grey matter (two sagittal through each hippocampus, two coronal, two axial), placed
#     relative to the centre of the segmented structures, using the rerun segmentation
#     where one exists
#   * Image-quality metrics from the FAST tissue maps (data/iq/<subject>.csv):
#       CNR = (WM mean - GM mean) / sqrt(GM sd^2 + WM sd^2)   grey/white contrast
#       SNR = WM mean / WM sd                                  white-matter signal-to-noise
#     Voxels count as GM or WM when their partial-volume estimate is at least 0.9.
#
# Usage (from the project folder, inside WSL):
#   bash scripts/05_qc_images_metrics.sh data/all_subjects.txt        # all scans
#   bash scripts/05_qc_images_metrics.sh data/test3.txt               # a quick test
# Runs several subjects at once (half the CPU cores). Finished subjects are skipped.

set -u
LIST="${1:?Give a subject list, e.g. data/all_subjects.txt}"
export WORK="$HOME/ixi/work"
export PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$PROJECT/qc/first_all" "$PROJECT/data/iq" "$PROJECT/logs"
JOBS=$(( $(nproc) / 2 )); [ "$JOBS" -lt 1 ] && JOBS=1

one_subject () {
  S="$1"; OUT="$WORK/$S"; IMG="$PROJECT/qc/first_all/${S}_first.png"; IQ="$PROJECT/data/iq/$S.csv"
  [ -f "$IMG" ] && [ -f "$IQ" ] && return 0
  TMP=$(mktemp -d)
  {
    # FIRST image: rerun segmentation if present, otherwise the original
    SEG="$OUT/first2_all_fast_firstseg.nii.gz"
    [ -f "$SEG" ] || SEG="$OUT/first_all_fast_firstseg.nii.gz"
    if [ -f "$SEG" ]; then
      overlay 1 0 "$OUT/T1" -a "$SEG" 1 60 "$TMP/ovl"
      # Centre of the deep grey matter (all FIRST structures except the brainstem, label 16),
      # in voxels, so the slices land on the same anatomy whatever the head position
      fslmaths "$SEG" -thr 16 -uthr 16 -bin "$TMP/bs"
      fslmaths "$SEG" -bin -sub "$TMP/bs" -bin "$TMP/deep"
      read CX CY CZ < <(fslstats "$TMP/deep" -C)
    else
      cp "$OUT/T1.nii.gz" "$TMP/ovl.nii.gz"            # no segmentation: plain T1, middle of the image
      CX=$(( $(fslval "$OUT/T1" dim1) / 2 )); CY=$(( $(fslval "$OUT/T1" dim2) / 2 )); CZ=$(( $(fslval "$OUT/T1" dim3) / 2 ))
    fi
    PX=$(fslval "$OUT/T1" pixdim1); PY=$(fslval "$OUT/T1" pixdim2); PZ=$(fslval "$OUT/T1" pixdim3)
    # Slice numbers: 25 mm either side of the centre (left and right hippocampus/putamen),
    # 6 mm behind and in front of it (thalamus; striatum and amygdala),
    # 10 mm below it (hippocampus, amygdala) and 2 mm above it (basal ganglia, thalamus)
    read X1 X2 Y1 Y2 Z1 Z2 < <(awk -v cx="$CX" -v cy="$CY" -v cz="$CZ" -v px="$PX" -v py="$PY" -v pz="$PZ" \
      'function r(v){return int(v+0.5)} BEGIN{print r(cx-25/px), r(cx+25/px), r(cy-6/py), r(cy+6/py), r(cz-10/pz), r(cz+2/pz)}')
    # A negative number tells slicer to use an absolute slice number instead of a fraction
    slicer "$TMP/ovl" -x -"$X1" "$TMP/a.png" -x -"$X2" "$TMP/b.png" \
                      -y -"$Y1" "$TMP/c.png" -y -"$Y2" "$TMP/d.png" \
                      -z -"$Z1" "$TMP/e.png" -z -"$Z2" "$TMP/f.png"
    pngappend "$TMP/a.png" + "$TMP/b.png" + "$TMP/c.png" + "$TMP/d.png" + "$TMP/e.png" + "$TMP/f.png" "$IMG"

    # Image-quality metrics
    fslmaths "$OUT/fast_pve_1" -thr 0.9 -bin "$TMP/gm"
    fslmaths "$OUT/fast_pve_2" -thr 0.9 -bin "$TMP/wm"
    read GMM GMS < <(fslstats "$OUT/T1" -k "$TMP/gm" -M -S)
    read WMM WMS < <(fslstats "$OUT/T1" -k "$TMP/wm" -M -S)
    awk -v s="$S" -v gm="$GMM" -v gs="$GMS" -v wm="$WMM" -v ws="$WMS" \
      'BEGIN{printf "%s,%.3f,%.3f,%.3f,%.3f,%.4f,%.3f\n", s, gm, gs, wm, ws, (wm-gm)/sqrt(gs^2+ws^2), wm/ws}' > "$IQ"
  } >> "$PROJECT/logs/${S}_qc_images.log" 2>&1
  rm -rf "$TMP"
  if [ -f "$IMG" ] && [ -s "$IQ" ]; then echo "$(date '+%F %T')  $S: done"; else echo "$(date '+%F %T')  $S: FAILED, see logs/${S}_qc_images.log"; fi
}
export -f one_subject

echo "$(date '+%F %T')  Starting with $JOBS parallel jobs"
grep -v '^$' "$LIST" | xargs -P "$JOBS" -I{} bash -c 'one_subject "$@"' _ {}

# Combine the per-subject metric files into one table
{ echo "subject,gm_mean,gm_sd,wm_mean,wm_sd,cnr,snr"; cat "$PROJECT"/data/iq/*.csv; } > "$PROJECT/data/image_quality.csv"
echo "$(date '+%F %T')  Finished. Images: qc/first_all/   Metrics: data/image_quality.csv"
