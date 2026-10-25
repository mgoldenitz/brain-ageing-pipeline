# Brain changes across the lifespan: study plan (plain-language version)

This is an easier-to-read summary of the study plan. The official, timestamped plan, with plain-language summaries next to the formal specification, is [PREREGISTRATION.md](PREREGISTRATION.md). If the two ever differ, the official version is the one that counts. Results are in [README_PLAIN_LANGUAGE.md](README_PLAIN_LANGUAGE.md).

Author: Michael Goldenitz. Plan written: 5 October 2026, before any results were looked at.

## What a pre-registration is

A pre-registration is a study plan written down before looking at the results. It records what I expected to find and exactly how I would test it. Once you've seen the data, it's easy (even unintentionally) to keep trying different analyses until something looks interesting. Writing the plan first, and saving it publicly with a date, makes that impossible to hide. Any later changes to the plan have to be reported openly.

## Where things stood when the plan was written

The study uses existing, freely available brain scans from the [IXI dataset](https://brain-development.org/ixi-dataset/), so no new data were collected.

Already done:

- Downloaded 581 brain scans and the participants' details. 563 of them include the participant's age.
- Ran standard brain-imaging software (FSL) on all 563 scans to remove the skull from each image, separate grey matter, white matter and CSF, and outline 15 deep-brain structures, then measured each one.
- Ran automatic checks that flag scans whose measurements look unusual, and looked at pictures of about 95 scans to see what problems looked like.
- Started re-processing 50 scans flagged for problems with the deep-brain outlines.

Not done yet: I had not looked at how any brain measurement relates to age, sex or hospital, and had not built any age-prediction model.

## The seven predictions

Each prediction is tested after accounting for sex, hospital and head size, so those don't distort the results.

- H1: Grey matter shrinks with age. I expected a steady decline from the 20s onward.
- H2: White matter changes with age in a curve. I expected it to rise until midlife and then decline.
- H3: CSF increases with age. I expected it to increase faster after about age 60.
- H4: The hippocampus and thalamus shrink with age. I expected them to shrink faster after about age 60.
- H5: A computer model can estimate a participant's age from their brain measurements. I expected smaller errors than simply using the average age.
- H6: The model is less accurate on a hospital it wasn't trained on. I expected larger errors when it was tested on a new hospital.
- H7: Small studies find the grey matter-age effect less often and overestimate it. I expected smaller studies to miss the effect more often and to exaggerate it when they find it.

I also planned to explore, without firm predictions, whether men and women differ in "brain age" and whether hospitals differ before and after correcting for scanner differences.

## Who is included, and when scans are removed

Everyone in the dataset with a scan and a recorded age is included: 563 participants, all of whom also have a recorded sex.

A scan is only removed if the software clearly made a mistake. Being unusual is not enough. Removing participants just because their brain looks unusual for their age would throw away exactly the participants who are ageing faster or slower than average, and would bias the results.

1. Visual check. Every scan's software output is checked by eye, without knowing the participant's age, sex or hospital, and rated good (0), minor issue (1, kept) or failed (2, removed).
2. Consistency check. 50 random scans are rated again at least a week later, to measure how consistent the ratings are.
3. Deep-brain errors. If only the deep-brain outlines fail, those measurements are dropped, but the scan is kept for whole-brain measurements.
4. Image quality. A measure of how clear each image is is recorded for every scan, but it is not used to remove scans.
5. Missing data. Each analysis uses every scan that has the measurements it needs. Missing values are not filled in or estimated.

## What is measured

- Main outcomes: volumes of grey matter, white matter and CSF, measured by FSL's tissue-labelling tool (FAST).
- Main outcomes: volumes of 15 deep-brain structures (thalamus, caudate, putamen, pallidum, hippocampus, amygdala and accumbens on each side, plus the brainstem), measured by FSL's outlining tool (FIRST).
- Main outcome: the "brain age gap", which is predicted age minus real age, from the age-prediction model.
- Main factor: age, from the dataset.
- Adjusted for: sex (313 women, 250 men), hospital and head size. Sex and hospital come from the dataset, and head size is estimated by FSL (SIENAX).
- Recorded only: image clarity (calculated from the scans) and the visual quality rating (rated by eye).

## How each question will be analysed

How the brain changes with age (H1-H4). For each brain measure, a flexible curve is fitted across age instead of forcing a straight line, using a method called a generalized additive model (GAM). This shows where volume peaks and whether decline speeds up after 60. Results for the 15 deep-brain structures are adjusted for the number of tests, so that some don't look significant purely by chance.

Estimating age from the brain (H5-H6).

1. The model is given the 18 brain measurements, each adjusted for head size.
2. Three common machine-learning methods are compared (ridge regression, random forest and gradient boosting) against a benchmark that simply uses the average age for everyone.
3. The models are always tested on participants they weren't trained on. This is repeated many times with different splits of the data, so that the accuracy scores are honest.
4. A standard correction is applied for these models' tendency to overestimate young participants' ages and underestimate older participants' ages.
5. H5 is supported if the best model's average error is smaller than the benchmark's.
6. For H6, the model is trained on two hospitals and tested on the third, and its accuracy is compared with training and testing within the same hospital.

Do small studies mislead? (H7). Thousands of pretend "small studies" are created by randomly drawing 25, 50, 100, 200, 300 or 500 participants from the full dataset, 1,000 times at each size. For each size, I count how often the grey matter-age effect is found, and whether the studies that find it overestimate it.

## Checking that the results hold up

The main analyses are repeated in several different reasonable ways. A result counts as reliable only if it stays the same in all of them:

- removing scans rated "minor issue" as well as "failed";
- without correcting for differences between scanners;
- without the Institute of Psychiatry hospital (the smallest group, with the lowest image clarity);
- without adjusting brain measurements for head size.

## Openness and sharing

- Timestamp: the plan is saved publicly on GitHub before any results are looked at, and the save date is the plan's official date.
- Changes: any change to the plan is listed, with its reason and date, in the README.
- Reporting: the write-up follows established checklists for brain-imaging studies (COBIDAS) and for prediction models (TRIPOD).
- Sharing: all code, measurements, quality ratings and results are shared on GitHub. The original scans aren't re-shared, but anyone can download them from the IXI website.

## References

- de Lange, A.-M. G., & Cole, J. H. (2020). Commentary: Correction procedures in brain-age prediction. *NeuroImage: Clinical*, 26, 102229. https://doi.org/10.1016/j.nicl.2020.102229
- Fortin, J.-P., et al. (2018). Harmonization of cortical thickness measurements across scanners and sites. *NeuroImage*, 167, 104-120. https://doi.org/10.1016/j.neuroimage.2017.11.024
- Nichols, T. E., et al. (2017). Best practices in data analysis and sharing in neuroimaging using MRI. *Nature Neuroscience*, 20, 299-303. https://doi.org/10.1038/nn.4500
- Collins, G. S., et al. (2015). Transparent reporting of a multivariable prediction model (TRIPOD). *BMJ*, 350, g7594. https://doi.org/10.1136/bmj.g7594
