# Brain Ageing Across the Lifespan

How do brain volumes change from age 20 to 86, and can a machine-learning model tell how old a brain is? A reproducible structural MRI pipeline on 563 open-access scans from three London hospitals.

**Status:** in progress. Scans processed; blind visual quality control rated, test-retest check pending. The analysis plan is pre-registered in [PREREGISTRATION.md](PREREGISTRATION.md) before any models are run.

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

Rating rules are in [QC_RATING_GUIDE.md](QC_RATING_GUIDE.md). Later steps (head-size adjustment, ComBat harmonisation, SQL database, GAMs in R, brain age model, sample-size analysis, Power BI dashboard) are described in the pre-registration.

## Quality-control decisions made before unblinding (6 October 2026)

- **Primary analysis:** follows the pre-registered rule. Scans with a whole-brain rating of 2 are excluded; scans with a subcortical rating of 2 keep their whole-brain volumes but have subcortical volumes set to missing.
- **Second look at failures:** all scans rated 2 were reviewed again in a blinded second pass, applying the rating guide's test of whether the error would change volumes by more than a few percent. First-pass ratings are kept in `data/qc_ratings_firstpass.csv`, and every change is logged in `data/qc_review_log.csv`. Whole-brain fails went from 72 to 18 of 563 (3.2%); subcortical fails went from 16 to 6 (1.1%).
- **Added sensitivity analyses:** because the review changed many ratings, the main models will also be run (a) with the 18 whole-brain-fail scans included and (b) with the 72 first-pass exclusions applied. This was decided before ratings were linked to subject IDs and before any outcome analysis.

## Data

[IXI dataset](https://brain-development.org/ixi-dataset/), Information eXtraction from Images project, licensed CC BY-SA 3.0. Raw scans are not included in this repository; download them from the IXI site. Software: FSL 6.0.7.23 on Ubuntu 24.04 (WSL2).

## Author

Michael Goldenitz · [LinkedIn](https://www.linkedin.com/in/michael-goldenitz-790509265/)
