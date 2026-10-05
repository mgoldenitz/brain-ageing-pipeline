# Brain Ageing Across the Lifespan: Pre-registration

**Author:** Michael Goldenitz · **Registered:** 2026-10-05 (date of the first commit of this file)

Analysis plan for the brain volume, brain age and sample-size analyses of the IXI dataset, fixed before any association with age, sex or site is examined.

## Study status

This is a pre-registration of secondary analyses of existing open data ([IXI dataset](https://brain-development.org/ixi-dataset/), CC BY-SA 3.0). Processing is complete; no outcome analyses have been run.

**Done before this plan:**

- Downloaded 581 T1 scans and the demographics spreadsheet; 563 scans have an age (Guy's 322, Hammersmith 185, IOP 74).
- Processed all 563 with FSL 6.0.7.23 (reorientation, neck cropping, BET, FAST, FIRST) and extracted grey matter, white matter, CSF and 15 subcortical volumes.
- Ran automated QC flags (`scripts/03_qc_flags.py`). The outlier rule fits an age, sex and site regression to compute residual z-scores; only the z-scores were inspected, not the regression coefficients.
- Viewed QC snapshots for about 95 scans (pilot, flagged and a random sample of passing scans).
- Started a FIRST rerun on the 50 scans flagged for subcortical problems (`scripts/04_rerun_first.sh`).

**Not done:** no association between any brain measure and age, sex or site has been examined, plotted or tested; no brain age model has been trained.

## Hypotheses

Confirmatory hypotheses, each tested after adjusting for intracranial volume, sex and site:

| ID | Hypothesis | Expected direction |
| --- | --- | --- |
| H1 | Grey matter volume declines with age | Negative, roughly linear from the 20s |
| H2 | White matter volume changes non-linearly with age | Inverted U, peaking in mid-life, declining after |
| H3 | CSF volume increases with age, faster in later life | Positive, accelerating after about 60 |
| H4 | Hippocampal and thalamic volumes decline with age | Negative, steeper after about 60 |
| H5 | A brain age model predicts age better than a mean-age baseline | Lower cross-validated MAE than baseline |
| H6 | Brain age accuracy is worse on an unseen site | Leave-one-site-out MAE higher than within-site MAE |
| H7 | Small samples detect the grey matter–age effect less often and overestimate it | Detection rate rises with n; effect size among significant results shrinks with n |

Tests of sex differences in the brain age gap, and of site differences before and after harmonisation, are two-sided and exploratory.

## Sample and exclusion rules

The sample is all IXI participants with a T1 scan and a recorded age (n = 563). All 563 have a recorded sex.

**Core rule: a flag only triggers review. A scan is excluded only for a confirmed processing failure.** Excluding scans for being unusual for their age would remove genuine accelerated or delayed ageing and bias the brain age results.

1. **Visual rating.** Every scan is rated from its BET, GM and FIRST snapshots, blind to age, sex, site and z-scores, using 0 = good, 1 = minor issue (kept), 2 = processing failure (excluded).
2. **Rating reliability.** A random 50 scans are re-rated at least one week later; agreement is reported as Cohen's kappa.
3. **Subcortical failures.** If FIRST still fails or is rated 2 after the brain-extracted rerun, that scan's subcortical volumes are set to missing; its whole-brain volumes are kept.
4. **Image quality.** Contrast-to-noise and signal-to-noise ratios are reported for every scan but are not used to exclude.
5. **Missing data.** Each analysis uses all scans with the variables it needs (complete-case per analysis); no imputation.

The number excluded at each rule, by site, is reported in the README.

## Variables

| Role | Variable | Source | Notes |
| --- | --- | --- | --- |
| Outcome | Grey matter, white matter, CSF volume (mm³) | FSL FAST partial-volume maps | Added together, these give a rough estimate of total brain and fluid volume |
| Outcome | 15 subcortical volumes (mm³): left and right thalamus, caudate, putamen, pallidum, hippocampus, amygdala, accumbens; brainstem | FSL FIRST | Left and right analysed separately |
| Outcome | Brain age gap (years) | Predicted minus actual age, bias-corrected | Model outcome for H5–H6 |
| Predictor | Age (years) | IXI.xls | Continuous |
| Covariate | Sex | IXI.xls (1 = male, 2 = female) | Binary (female = reference); 313 female, 250 male; none missing among the 563 |
| Covariate | Site | File name (Guy's, Hammersmith, IOP) | Each site used one scanner |
| Covariate | Intracranial volume (mm³) | FSL SIENAX scaling factor | Covariate in volume models |
| Descriptive | Contrast-to-noise, signal-to-noise | Computed from FAST tissue maps | Reported, not used to exclude |
| Descriptive | Visual QC rating (0/1/2) | Blind rating | Exclusion rule 1 |

## Analysis plan

**Inference criteria:** two-sided tests at α = 0.05. False discovery rate (Benjamini–Hochberg, q = 0.05) across the 15 subcortical structures. Every effect is reported with a 95% confidence interval, not only a p-value.

**Lifespan models (H1–H4, R).** For each volume, a GAM (`mgcv`) with a smooth of age (thin-plate spline, k = 5, REML), plus sex, site and intracranial volume as linear terms. The age effect is tested with the smooth term's F-test. The shape is described from the fitted curve: the age of peak volume for white matter (H2), and the slope before and after 60 for CSF and subcortical volumes (H3, H4). A sex-by-age interaction is tested as exploratory.

**Brain age model (H5–H6, Python, scikit-learn).**

1. Features: the 18 volumes, each divided by intracranial volume.
2. Models: ridge regression, random forest and gradient boosting, compared with a baseline that predicts the training-set mean age.
3. Validation: nested cross-validation (10 outer × 5 inner folds, repeated 5 times, random seed 42). Scaling, ComBat harmonisation, hyperparameter tuning and bias correction are all fitted inside each training fold, never on test data.
4. Bias correction: regress predicted age on actual age in the training fold, then apply the correction to the test fold (de Lange & Cole, 2020).
5. Metrics: mean absolute error (MAE), Pearson r and R² on outer folds. H5 is supported if the best model's MAE is lower than the baseline's across repeats (paired comparison of fold MAEs).
6. Leave-one-site-out (H6): train on two sites, test on the third, for each site; compare with within-site cross-validated MAE.
7. The brain age gap is tested against sex and site in a linear model (exploratory).

**Sample size (H7).** Draw 1,000 random samples (without replacement) at n = 25, 50, 100, 200, 300 and 500. Fit grey matter ~ age + sex + site + intracranial volume in each. Report the detection rate (share with p < 0.05) and the median age coefficient among significant samples, relative to the full-sample estimate.

## Sensitivity and exploratory analyses

The confirmatory results (H1–H6) are repeated under each of these conditions. Conclusions are called robust if the direction and significance hold in all of them.

- Excluding scans rated 1 (minor issue) as well as 2.
- Without ComBat harmonisation.
- Without the IOP site (lowest contrast, smallest sample).
- With raw volumes instead of intracranial-volume-adjusted volumes.

Exploratory, reported as such: sex-by-age interactions, site differences in the brain age gap before and after ComBat, the relationship between image quality and the brain age gap, and model performance above age 80 (only 8 scans).

## Deviations, reporting and sharing

- **Timestamp:** this plan is committed to the GitHub repository before any outcome analysis; the commit date is the registration date.
- **Deviations:** any change after registration is listed in a "Deviations from pre-registration" section of the README, with the reason and date.
- **Reporting:** methods follow the [COBIDAS](https://doi.org/10.1038/nn.4500) checklist for MRI and the [TRIPOD](https://doi.org/10.1136/bmj.g7594) checklist for the prediction model.
- **Reproducibility:** software versions (FSL 6.0.7.23, Python and R package versions in requirements files), random seeds and one script that runs the pipeline in order.
- **Sharing:** code, derived volumes, QC ratings and results are shared on GitHub; raw scans are not redistributed but can be downloaded from the IXI site. IXI data are acknowledged as required by its licence.

## References

- de Lange, A.-M. G., & Cole, J. H. (2020). Commentary: Correction procedures in brain-age prediction. *NeuroImage: Clinical*, 26, 102229. https://doi.org/10.1016/j.nicl.2020.102229
- Fortin, J.-P., et al. (2018). Harmonization of cortical thickness measurements across scanners and sites. *NeuroImage*, 167, 104–120. https://doi.org/10.1016/j.neuroimage.2017.11.024
- Nichols, T. E., et al. (2017). Best practices in data analysis and sharing in neuroimaging using MRI. *Nature Neuroscience*, 20, 299–303. https://doi.org/10.1038/nn.4500
- Collins, G. S., et al. (2015). Transparent reporting of a multivariable prediction model (TRIPOD). *BMJ*, 350, g7594. https://doi.org/10.1136/bmj.g7594
