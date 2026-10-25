# Visual QC rating guide

Every scan gets two ratings, each 0, 1 or 2. The sheets are in `qc/rating/`. Each scan block has the brain mask outline (top left), the grey-matter map (top right) and the FIRST subcortical outlines (bottom row).

Rate what you see on the sheet, not what you expect. You don't know which scans the automatic checks flagged, and that is on purpose.

## Whole-brain rating (top two images)

- 0 = good (use as is). The mask follows the edge of the brain all round. No big chunks of brain are cut off, and no scalp, eyes or neck are inside. The grey-matter map shows a clear cortical ribbon and deep grey matter.
- 1 = minor issue (keep, note it). Small problems that barely change total volumes: a thin strip of dura or skull inside the mask, a little cortex clipped at the top or around the temporal poles, mild blur or ringing from movement, or grey matter looking a bit patchy in one area.
- 2 = fail (exclude from all analyses). A large error: a whole region cut off (for example the cerebellum or a frontal lobe), eyes or neck tissue inside the mask, grey matter clearly mislabelled across a lobe, or motion so bad the tissues can't be told apart.

## Subcortical rating (bottom row)

Six slices: two sagittal (through left and right hippocampus), two coronal and two axial. Coloured outlines mark the thalamus, caudate, putamen, pallidum, hippocampus, amygdala, accumbens and brainstem.

- 0 = good (use as is). Each outline sits on its structure and follows its edges. Left and right look alike.
- 1 = minor issue (keep, note it). An outline a little too big or small, or spilling a few voxels into white matter or a ventricle. Small structures (accumbens, amygdala) slightly off.
- 2 = fail (subcortical volumes set to missing). A structure clearly in the wrong place, missing, much too big (for example the putamen swallowing the pallidum) or much too small, or no outlines at all.

A subcortical 2 only removes that scan's subcortical volumes. The scan stays in the whole-brain analyses unless its whole-brain rating is also 2. This follows the pre-registration.

## How to record ratings

- Open `data/qc_ratings.csv` (or the practice or retest file) and type 0, 1 or 2 in `whole_brain_rating` and `subcortical_rating` next to the code shown on the sheet.
- Use `note` for anything worth remembering, such as "L hippocampus too small" or "motion". Short words are fine.
- Save as CSV, and close Excel before running any script.
- Do not open `data/qc_key.csv` until all rating, including the retest, is finished.

## Order of work

1. Practice first: `practice_01` to `practice_04` (24 scans). Rate them and reread this guide where you hesitated. These ratings aren't used in the analysis.
2. Main sheets: `sheet_01` onwards, in order. Aim for sessions of about 30 minutes (around 10 sheets), with breaks, so attention stays even.
3. Retest, at least a week after finishing the main sheets: `retest_01` to `retest_09` (50 scans, new codes). Don't look back at your main ratings first. Agreement between the two passes is reported as Cohen's kappa.

## When unsure

- Between 0 and 1, pick 1. Between 1 and 2, ask whether the error would change the volume by more than a few percent. If yes, pick 2.
- Rate the image and ignore who the scan belongs to. An unusual but correctly segmented brain (large ventricles, atrophy) is a 0.
