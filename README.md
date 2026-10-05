# Brain Ageing Across the Lifespan

How do brain volumes change from age 20 to 86, and can a machine-learning model tell how old a brain is? A reproducible structural MRI pipeline on 563 open-access scans from three London hospitals.

**Status:** in progress. Scans processed and quality control under way. The analysis plan is pre-registered in [PREREGISTRATION.md](PREREGISTRATION.md) before any models are run.

## Pipeline

| Step | Script | Tools |
| --- | --- | --- |
| 1. Check demographics, pick a pilot sample | `scripts/01_check_demographics.py` | Python (pandas) |
| 2. Process T1 scans: reorient, crop, brain extraction, tissue and subcortical segmentation, volumes | `scripts/02_process_t1.sh` | Bash, FSL (BET, FAST, FIRST) |
| 3. Automated QC flags and review sheets | `scripts/03_qc_flags.py` | Python (pandas, NumPy, Pillow) |
| 3b. Rerun FIRST on flagged scans | `scripts/04_rerun_first.sh` | Bash, FSL |

Later steps (blind visual QC, head-size adjustment, ComBat harmonisation, SQL database, GAMs in R, brain age model, sample-size analysis, Power BI dashboard) are described in the pre-registration.

## Data

[IXI dataset](https://brain-development.org/ixi-dataset/), Information eXtraction from Images project, licensed CC BY-SA 3.0. Raw scans are not included in this repository; download them from the IXI site. Software: FSL 6.0.7.23 on Ubuntu 24.04 (WSL2).

## Author

Michael Goldenitz · [LinkedIn](https://www.linkedin.com/in/michael-goldenitz-790509265/)
