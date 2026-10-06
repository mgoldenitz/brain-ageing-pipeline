# Brain Ageing Across the Lifespan

How do brain volumes change from age 20 to 86, and can a machine-learning model tell how old a brain is? A reproducible structural MRI pipeline on 563 open-access scans from three London hospitals.

**Status:** in progress. Scans processed; blind visual quality control rated, test-retest check pending. Analysis code written and tested on shuffled data, ready for unblinding. The analysis plan is pre-registered in [PREREGISTRATION.md](PREREGISTRATION.md) before any models are run.

## Pipeline

| Step | Script | Tools |
| --- | --- | --- |
| 1. Check demographics, pick a pilot sample | `scripts/01_check_demographics.py` | Python (pandas) |
| 2. Process T1 scans: reorient, crop, brain extraction, tissue and subcortical segmentation, volumes | `scripts/02_process_t1.sh` | Bash, FSL (BET, FAST, FIRST) |
| 3. Automated QC flags and review sheets | `scripts/03_qc_flags.py` | Python (pandas, NumPy, Pillow) |
| 3b. Rerun FIRST on flagged scans | `scripts/04_rerun_first.sh` | Bash, FSL |
| 4a. QC images for every scan; image quality (CNR, SNR) | `scripts/05_qc_images_metrics.sh` | Bash, FSL |
| 4b. Blinded rating sheets (random codes, shuffled order) | `scripts/06_rating_sheets.py` | Python (Pillow) |
| 4c. Head size (SIENAX scaling factor) | `scripts/07_sienax.sh` | Bash, FSL (SIENAX) |
| 4d. Browser-based blind rating tool | `scripts/08_rating_tool.py` | Python (standard library, Pillow) |
| 5a. Analysis dataset (real, or shuffled for blind analysis) | `scripts/09_build_dataset.py` | Python (pandas) |
| 5b. QC rules and ComBat harmonisation for each analysis | `scripts/10_harmonise.py` | Python (neuroCombat) |
| 6. Lifespan models, H1–H4 | `scripts/11_lifespan_gams.R` | R (mgcv, ggplot2) |
| 7. Brain age model, H5–H6 | `scripts/12_brain_age.py` | Python (scikit-learn, statsmodels) |

Rating rules are in [QC_RATING_GUIDE.md](QC_RATING_GUIDE.md). Later steps (head-size adjustment, ComBat harmonisation, SQL database, GAMs in R, brain age model, sample-size analysis, Power BI dashboard) are described in the pre-registration.

## Quality-control decisions made before unblinding (6 October 2026)

- **Primary analysis:** follows the pre-registered rule. Scans with a whole-brain rating of 2 are excluded; scans with a subcortical rating of 2 keep their whole-brain volumes but have subcortical volumes set to missing.
- **Second look at failures:** all scans rated 2 were reviewed again in a blinded second pass, applying the rating guide's test of whether the error would change volumes by more than a few percent. First-pass ratings are kept in `data/qc_ratings_firstpass.csv`, and every change is logged in `data/qc_review_log.csv`. Whole-brain fails went from 72 to 18 of 563 (3.2%); subcortical fails went from 16 to 6 (1.1%).
- **Added sensitivity analyses:** because the review changed many ratings, the main models will also be run (a) with the 18 whole-brain-fail scans included and (b) with the 72 first-pass exclusions applied. This was decided before ratings were linked to subject IDs and before any outcome analysis.

## Deviations from pre-registration

All analysis code was written and tested on a **blind version of the data**: age, sex and site were shuffled between participants, and the QC ratings were shuffled between scans (`scripts/09_build_dataset.py --shuffled`). That broke every real relationship while keeping the data's structure. The deviations below were made on that basis, before the QC ratings were unblinded and before any outcome analysis on real data. The scripts were committed to this repository before unblinding.

**1. Site counts corrected (6 October 2026).** The pre-registration gives site counts of Guy's 322, Hammersmith 185 and IOP 74. Those are counts for all 581 downloaded scans. The 563 scans with a recorded age split 314, 181 and 68. This is a reporting error only; no analysis changes.

**2. ComBat in the lifespan models stated explicitly (6 October 2026).** The pre-registration lists "without ComBat harmonisation" as a sensitivity analysis but doesn't say that the main lifespan models (H1–H4) use harmonised volumes. They do. ComBat is fitted separately for each analysis's set of scans, preserving age, age², sex and intracranial volume, and site stays in the model as a covariate. Raw volumes are used in the "without ComBat" sensitivity analysis.

**3. Decision rules for H1–H4 written out (6 October 2026).** The pre-registration states the expected directions. The exact checks are now fixed in `scripts/11_lifespan_gams.R`:

| Hypothesis | Check |
| --- | --- |
| H1 | p < .05 and grey matter lower at the oldest age than the youngest |
| H2 | p < .05, peak at least 5 years inside the age range, and declining after 60 |
| H3 | p < .05, CSF higher at the oldest age, and rising faster after 60 than before |
| H4 | FDR-corrected p < .05, volume lower at the oldest age, and declining faster after 60 than before, checked separately for left and right hippocampus and thalamus |

**4. H5 judged on uncorrected predictions (6 October 2026).** Bias correction uses each person's real age, which makes predictions look more accurate than they are. So the H5 comparison with the baseline uses uncorrected mean absolute error. Bias-corrected predictions are used for the brain-age-gap analyses. Both are reported. The "best model" is the one with the lowest mean cross-validated error.

**5. Bias-correction safeguard (6 October 2026).** If the correction's slope is below 0.1, meaning the model has learned almost nothing about age, the correction divides by nearly zero and becomes unstable. In that case it isn't applied for that fold. The blind analysis showed this happening on shuffled data, with corrected errors of over 200 years.

**6. H6 rule refined (6 October 2026).** The blind analysis showed that the pre-registered rule (leave-one-site-out error higher than within-site error) can be met with no real brain-age signal at all. The sites differ in age range, so a model trained on two sites starts from the wrong average age for the third. The refined rule compares each model with the mean-age baseline in both settings. H6 is supported if the model is at least 10% better than the baseline within sites and that advantage shrinks on an unseen site. Both the pre-registered and refined results are reported. ComBat isn't used in this comparison, because a site missing from training can't be harmonised.

**7. Brain-age-gap models adjusted for age (6 October 2026).** The exploratory models of the brain-age gap (by sex, site and image quality) include age as a covariate, as recommended by de Lange & Cole (2020). Without it, the gap's built-in correlation with age produced spurious "effects" on the shuffled data.

## Data

[IXI dataset](https://brain-development.org/ixi-dataset/), Information eXtraction from Images project, licensed CC BY-SA 3.0. Raw scans are not included in this repository; download them from the IXI site. Software: FSL 6.0.7.23 on Ubuntu 24.04 (WSL2).

## Author

Michael Goldenitz · [LinkedIn](https://www.linkedin.com/in/michael-goldenitz-790509265/)
