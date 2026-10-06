-- Example queries for the brain ageing database.
-- Each query starts with a "-- @query" line; scripts/15_build_database.py runs them all and
-- saves the output. They also run as-is in DB Browser for SQLite or the sqlite3 command line.

-- @query 1. Sample by site (uses the v_site_summary view)
SELECT site_code, hospital, scanner, scans, mean_age, min_age, max_age, pct_female,
       mean_cnr, mean_snr
FROM v_site_summary
ORDER BY scans DESC;

-- @query 2. QC exclusions by site (pre-registration exclusion rules 1 and 3)
SELECT p.site_code,
       COUNT(*)                                   AS scans,
       SUM(q.qc_wb = 2)                           AS rule1_excluded,
       SUM(q.qc_wb < 2 AND q.qc_sc = 2)           AS rule3_subcortical_missing,
       SUM(q.qc_wb = 1 OR q.qc_sc = 1)            AS rated_minor_issue,
       SUM(q.qc_wb_first = 2)                     AS first_pass_excluded
FROM participants p
JOIN qc_final q ON q.subject = p.subject
GROUP BY p.site_code
UNION ALL
SELECT 'Total', COUNT(*), SUM(qc_wb = 2), SUM(qc_wb < 2 AND qc_sc = 2),
       SUM(qc_wb = 1 OR qc_sc = 1), SUM(qc_wb_first = 2)
FROM qc_final;

-- @query 3. Automatic QC flags vs blind visual ratings (cross-tabulation)
SELECT a.flag                         AS automatic_flag,
       COUNT(*)                       AS scans,
       SUM(q.qc_wb = 2)               AS visual_whole_brain_fail,
       SUM(q.qc_sc = 2)               AS visual_subcortical_fail,
       SUM(q.qc_wb = 0 AND q.qc_sc = 0) AS visual_both_good
FROM qc_auto a
JOIN qc_final q ON q.subject = a.subject
GROUP BY a.flag
ORDER BY scans DESC;

-- @query 4. How the second QC pass changed the ratings (coded ratings, no subject IDs)
SELECT COALESCE(CAST(f.whole_brain AS TEXT), 'unrated') AS first_pass,
       r.whole_brain AS reviewed, COUNT(*) AS scans
FROM qc_ratings f
JOIN qc_ratings r ON r.code = f.code AND r.rating_set = f.rating_set
WHERE f.rating_set = 'main' AND f.pass = 'first' AND r.pass = 'reviewed'
GROUP BY f.whole_brain, r.whole_brain
ORDER BY first_pass, reviewed;

-- @query 5. Head size by sex and site (mean intracranial volume, litres)
SELECT p.sex, p.site_code, COUNT(*) AS scans,
       ROUND(AVG(s.icv_mm3) / 1e6, 3) AS mean_icv_l,
       ROUND(MIN(s.icv_mm3) / 1e6, 3) AS min_icv_l,
       ROUND(MAX(s.icv_mm3) / 1e6, 3) AS max_icv_l
FROM participants p
JOIN scans s ON s.subject = p.subject
GROUP BY p.sex, p.site_code
ORDER BY p.sex, p.site_code;

-- @query 6. Left-right asymmetry of each subcortical structure (CTE + self-join)
-- Asymmetry index = (L - R) / mean(L, R): positive = left larger. Summarised by mean and spread.
WITH pairs AS (
    SELECT l.subject,
           SUBSTR(l.structure_code, 3)                          AS structure,
           (l.volume_mm3 - r.volume_mm3) / ((l.volume_mm3 + r.volume_mm3) / 2.0) AS asym
    FROM volumes l
    JOIN volumes r ON r.subject = l.subject
                  AND r.structure_code = 'R_' || SUBSTR(l.structure_code, 3)
    WHERE l.structure_code LIKE 'L\_%' ESCAPE '\'
)
SELECT structure, COUNT(*) AS scans,
       ROUND(AVG(asym), 3)                                      AS mean_asymmetry,
       ROUND(SQRT(AVG(asym * asym) - AVG(asym) * AVG(asym)), 3) AS sd_asymmetry,
       ROUND(MIN(asym), 3) AS min_asym, ROUND(MAX(asym), 3) AS max_asym
FROM pairs
GROUP BY structure
ORDER BY sd_asymmetry DESC;

-- @query 7. Lowest and highest 1% of hippocampal volume, relative to head size, within each site
-- (window functions: RANK and NTILE over a partition)
WITH hipp AS (
    SELECT p.subject, p.site_code, q.qc_sc,
           (w.L_Hipp + w.R_Hipp) / w.icv_mm3 * 1000 AS hipp_per_litre_icv
    FROM v_scan_wide w
    JOIN participants p ON p.subject = w.subject
    JOIN qc_final q     ON q.subject = w.subject
    WHERE w.L_Hipp IS NOT NULL AND w.R_Hipp IS NOT NULL
), ranked AS (
    SELECT *, RANK()   OVER (PARTITION BY site_code ORDER BY hipp_per_litre_icv) AS rank_in_site,
              NTILE(100) OVER (PARTITION BY site_code ORDER BY hipp_per_litre_icv) AS percentile_in_site
    FROM hipp
)
SELECT subject, site_code, ROUND(hipp_per_litre_icv, 3) AS hipp_per_litre_icv,
       percentile_in_site, qc_sc AS subcortical_rating
FROM ranked
WHERE percentile_in_site <= 1 OR percentile_in_site >= 100
ORDER BY site_code, hipp_per_litre_icv;

-- @query 8. Image quality vs whole-brain rating (does lower CNR go with failed scans?)
SELECT q.qc_wb AS whole_brain_rating, COUNT(*) AS scans,
       ROUND(AVG(s.cnr), 2) AS mean_cnr, ROUND(AVG(s.snr), 1) AS mean_snr
FROM qc_final q
JOIN scans s ON s.subject = q.subject
GROUP BY q.qc_wb
ORDER BY q.qc_wb;

-- @query 9. Brain volumes by age decade after QC rules (descriptive; outcome data - real database only)
SELECT CAST(p.age / 10 AS INTEGER) * 10                AS decade,
       COUNT(DISTINCT p.subject)                       AS scans,
       ROUND(AVG(CASE WHEN v.structure_code = 'gm'  THEN v.volume_mm3 END) / 1000, 1) AS mean_gm_cm3,
       ROUND(AVG(CASE WHEN v.structure_code = 'wm'  THEN v.volume_mm3 END) / 1000, 1) AS mean_wm_cm3,
       ROUND(AVG(CASE WHEN v.structure_code = 'csf' THEN v.volume_mm3 END) / 1000, 1) AS mean_csf_cm3
FROM participants p
JOIN v_volumes_qc v ON v.subject = p.subject
GROUP BY decade
ORDER BY decade;
