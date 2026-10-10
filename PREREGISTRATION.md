# Brain Changes Across the Lifespan: Pre-registration

**Author:** Michael Goldenitz · **Registered:** 2026-10-05 (date of the first commit of this file)

Analysis plan for the brain volume, brain age and sample-size analyses of the IXI dataset, specified before any association with age, sex or site was examined.

## Study status

This pre-registration covers secondary analyses of existing open data ([IXI dataset](https://brain-development.org/ixi-dataset/), CC BY-SA 3.0). Image processing is complete; no outcome analyses have been run.

**Completed before registration:**

- Downloaded 581 T1 scans and the demographics spreadsheet; 563 scans have a recorded age (Guy's 322, Hammersmith 185, IOP 74).
- Processed all 563 scans with FSL 6.0.7.23 (reorientation, neck cropping, BET, FAST, FIRST) and extracted grey matter, white matter, CSF and 15 subcortical volumes.
- Generated automated QC flags (`scripts/03_qc_flags.py`). Outliers are identified from residual z-scores of an age, sex and site regression; only the z-scores were inspected, not the regression coefficients.
- Inspected QC snapshots for about 95 scans (pilot, flagged and a random sample of passing scans).
- Began re-running FIRST on the 50 scans flagged for subcortical problems (`scripts/04_rerun_first.sh`).

**Not yet done:** no association of any brain measure with age, sex or site has been examined, plotted or tested; no brain age model has been trained.

## Hypotheses

Confirmatory hypotheses, each tested with adjustment for intracranial volume, sex and site:

| ID | Hypothesis | Expected direction |
| --- | --- | --- |
| H1 | Grey matter volume declines with age | Negative, roughly linear from the 20s |
| H2 | White matter volume changes non-linearly with age | Inverted U, peaking in mid-life, declining after |
| H3 | CSF volume increases with age, faster in later life | Positive, accelerating after about 60 |
| H4 | Hippocampal and thalamic volumes decline with age | Negative, steeper after about 60 |
| H5 | A brain age model predicts age better than a mean-age baseline | Lower cross-validated MAE than baseline |
| H6 | Brain age accuracy is worse on an unseen site | Leave-one-site-out MAE higher than within-site MAE |
| H7 | Small samples detect the grey matter–age effect less often and overestimate it | Detection rate rises with n; effect size among significant results shrinks with n |

Tests of sex differences in the brain age gap and of site differences before and after harmonisation are two-sided and exploratory.

## Sample and exclusion rules

The sample comprises all IXI participants with a T1 scan and a recorded age (n = 563), all of whom have a recorded sex.

**Core rule: a flag only triggers review; a scan is excluded only for a confirmed processing failure.** Excluding scans for being atypical for their age would remove genuine accelerated or delayed ageing and bias the brain age results.

1. **Visual rating.** Every scan is rated from its BET, grey matter and FIRST snapshots, blind to age, sex, site and z-scores: 0 = good, 1 = minor issue (retained), 2 = processing failure (excluded).
2. **Rating reliability.** 50 randomly selected scans are re-rated at least one week later; agreement is reported as Cohen's kappa.
3. **Subcortical failures.** If FIRST fails or is rated 2 after the brain-extracted rerun, the scan's subcortical volumes are set to missing and its whole-brain volumes are retained.
4. **Image quality.** Contrast-to-noise and signal-to-noise ratios are reported for every scan but are not used for exclusion.
5. **Missing data.** Each analysis uses all scans with complete data for its variables; no imputation is performed.

The number of exclusions under each rule, by site, is reported in the README.

## Variables

| Role | Variable | Source | Notes |
| --- | --- | --- | --- |
| Outcome | Grey matter, white matter, CSF volume (mm³) | FSL FAST partial-volume maps | Their sum approximates total brain and fluid volume |
| Outcome | 15 subcortical volumes (mm³): left and right thalamus, caudate, putamen, pallidum, hippocampus, amygdala, accumbens; brainstem | FSL FIRST | Left and right analysed separately |
| Outcome | Brain age gap (years) | Predicted minus actual age, bias-corrected | Model outcome for H5–H6 |
| Predictor | Age (years) | IXI.xls | Continuous |
| Covariate | Sex | IXI.xls (1 = male, 2 = female) | Binary (female = reference); 313 female, 250 male; none missing among the 563 |
| Covariate | Site | File name (Guy's, Hammersmith, IOP) | Each site used one scanner |
| Covariate | Intracranial volume (mm³) | FSL SIENAX scaling factor | Covariate in volume models |
| Descriptive | Contrast-to-noise, signal-to-noise | Computed from FAST tissue maps | Reported, not used to exclude |
| Descriptive | Visual QC rating (0/1/2) | Blind rating | Exclusion rule 1 |

## Analysis plan

**Inference criteria:** two-sided tests at α = 0.05, with false discovery rate correction (Benjamini–Hochberg, q = 0.05) across the 15 subcortical structures. All effects are reported with 95% confidence intervals as well as p-values.

**Lifespan models (H1–H4, R).** Each volume is modelled with a GAM (`mgcv`): a smooth of age (thin-plate spline, k = 5, REML) plus linear terms for sex, site and intracranial volume. The age effect is tested with the smooth term's F-test; curve shape is summarised by the age of peak white matter volume (H2) and slopes before and after 60 for CSF and subcortical volumes (H3, H4). A sex-by-age interaction is exploratory.

**Brain age model (H5–H6, Python, scikit-learn).**

1. Features: the 18 volumes, each divided by intracranial volume.
2. Models: ridge regression, random forest and gradient boosting, compared with a baseline that predicts the training-set mean age.
3. Validation: nested cross-validation (10 outer × 5 inner folds, repeated 5 times, random seed 42). Scaling, ComBat harmonisation, hyperparameter tuning and bias correction are fitted within each training fold only.
4. Bias correction: predicted age is regressed on chronological age in the training fold and the correction applied to the test fold (de Lange & Cole, 2020).
5. Metrics: mean absolute error (MAE), Pearson r and R² on outer folds. H5 is supported if the best model's MAE is lower than the baseline's across repeats (paired comparison of fold MAEs).
6. Leave-one-site-out (H6): train on two sites and test on the third, for each site, compared with within-site cross-validated MAE.
7. Brain age gap by sex and site: linear model (exploratory).

**Sample size (H7).** For n = 25, 50, 100, 200, 300 and 500, 1,000 random samples (without replacement) are each fitted with grey matter ~ age + sex + site + intracranial volume. Outcomes: detection rate (proportion with p < 0.05) and the median significant age coefficient relative to the full-sample estimate.

## Sensitivity and exploratory analyses

The confirmatory analyses (H1–H6) are repeated under each condition below; conclusions are considered robust if direction and significance are unchanged in all of them.

- Excluding scans rated 1 (minor issue) as well as 2.
- Without ComBat harmonisation.
- Without the IOP site (lowest contrast, smallest sample).
- With raw volumes instead of intracranial-volume-adjusted volumes.

Exploratory analyses, reported as such: sex-by-age interactions, site differences in the brain age gap before and after ComBat, the association between image quality and the brain age gap, and model performance above age 80 (8 scans).

## Deviations, reporting and sharing

- **Timestamp:** this plan is committed to GitHub before any outcome analysis; the commit date is the registration date.
- **Deviations:** any post-registration change is listed, with its reason and date, in the README's "Deviations from pre-registration" section.
- **Reporting:** methods follow the [COBIDAS](https://doi.org/10.1038/nn.4500) checklist for MRI and the [TRIPOD](https://doi.org/10.1136/bmj.g7594) checklist for the prediction model.
- **Reproducibility:** software versions (FSL 6.0.7.23; Python and R package versions in requirements files), random seeds and a single script that runs the full pipeline.
- **Sharing:** code, derived volumes, QC ratings and results are shared on GitHub. Raw scans are not redistributed but are available from the IXI website, and the IXI data are acknowledged as its licence requires.

## References

- de Lange, A.-M. G., & Cole, J. H. (2020). Commentary: Correction procedures in brain-age prediction. *NeuroImage: Clinical*, 26, 102229. https://doi.org/10.1016/j.nicl.2020.102229
- Fortin, J.-P., et al. (2018). Harmonization of cortical thickness measurements across scanners and sites. *NeuroImage*, 167, 104–120. https://doi.org/10.1016/j.neuroimage.2017.11.024
- Nichols, T. E., et al. (2017). Best practices in data analysis and sharing in neuroimaging using MRI. *Nature Neuroscience*, 20, 299–303. https://doi.org/10.1038/nn.4500
- Collins, G. S., et al. (2015). Transparent reporting of a multivariable prediction model (TRIPOD). *BMJ*, 350, g7594. https://doi.org/10.1136/bmj.g7594
