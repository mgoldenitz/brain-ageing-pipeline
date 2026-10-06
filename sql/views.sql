-- Views: reusable queries stored in the database

-- One row per scan with every volume as a column (long -> wide with conditional aggregation)
CREATE VIEW v_scan_wide AS
SELECT p.subject, p.site_code, p.sex, p.age, s.icv_mm3, s.cnr, s.snr,
       MAX(CASE WHEN v.structure_code = 'gm'     THEN v.volume_mm3 END) AS gm,
       MAX(CASE WHEN v.structure_code = 'wm'     THEN v.volume_mm3 END) AS wm,
       MAX(CASE WHEN v.structure_code = 'csf'    THEN v.volume_mm3 END) AS csf,
       MAX(CASE WHEN v.structure_code = 'L_Thal' THEN v.volume_mm3 END) AS L_Thal,
       MAX(CASE WHEN v.structure_code = 'R_Thal' THEN v.volume_mm3 END) AS R_Thal,
       MAX(CASE WHEN v.structure_code = 'L_Caud' THEN v.volume_mm3 END) AS L_Caud,
       MAX(CASE WHEN v.structure_code = 'R_Caud' THEN v.volume_mm3 END) AS R_Caud,
       MAX(CASE WHEN v.structure_code = 'L_Puta' THEN v.volume_mm3 END) AS L_Puta,
       MAX(CASE WHEN v.structure_code = 'R_Puta' THEN v.volume_mm3 END) AS R_Puta,
       MAX(CASE WHEN v.structure_code = 'L_Pall' THEN v.volume_mm3 END) AS L_Pall,
       MAX(CASE WHEN v.structure_code = 'R_Pall' THEN v.volume_mm3 END) AS R_Pall,
       MAX(CASE WHEN v.structure_code = 'L_Hipp' THEN v.volume_mm3 END) AS L_Hipp,
       MAX(CASE WHEN v.structure_code = 'R_Hipp' THEN v.volume_mm3 END) AS R_Hipp,
       MAX(CASE WHEN v.structure_code = 'L_Amyg' THEN v.volume_mm3 END) AS L_Amyg,
       MAX(CASE WHEN v.structure_code = 'R_Amyg' THEN v.volume_mm3 END) AS R_Amyg,
       MAX(CASE WHEN v.structure_code = 'L_Accu' THEN v.volume_mm3 END) AS L_Accu,
       MAX(CASE WHEN v.structure_code = 'R_Accu' THEN v.volume_mm3 END) AS R_Accu,
       MAX(CASE WHEN v.structure_code = 'BrStem' THEN v.volume_mm3 END) AS BrStem
FROM participants p
JOIN scans s           ON s.subject = p.subject
LEFT JOIN volumes v    ON v.subject = p.subject
GROUP BY p.subject;

-- Volumes after the pre-registered QC rules: whole-brain 2 excluded,
-- subcortical 2 keeps the scan but drops its subcortical volumes
CREATE VIEW v_volumes_qc AS
SELECT v.subject, v.structure_code, st.category,
       CASE WHEN st.category = 'subcortical' AND q.qc_sc = 2 THEN NULL
            ELSE v.volume_mm3 END AS volume_mm3
FROM volumes v
JOIN structures st ON st.structure_code = v.structure_code
JOIN qc_final q    ON q.subject = v.subject
WHERE q.qc_wb < 2;

-- Per-site summary: sample, demographics, image quality and QC outcomes
CREATE VIEW v_site_summary AS
SELECT p.site_code, si.hospital, si.scanner,
       COUNT(*)                                        AS scans,
       ROUND(AVG(p.age), 1)                            AS mean_age,
       MIN(p.age)                                      AS min_age,
       MAX(p.age)                                      AS max_age,
       ROUND(100.0 * SUM(p.sex = 'female') / COUNT(*), 1) AS pct_female,
       ROUND(AVG(s.cnr), 2)                            AS mean_cnr,
       ROUND(AVG(s.snr), 1)                            AS mean_snr,
       SUM(q.qc_wb = 2)                                AS excluded_whole_brain,
       SUM(q.qc_sc = 2)                                AS subcortical_missing
FROM participants p
JOIN sites si    ON si.site_code = p.site_code
JOIN scans s     ON s.subject = p.subject
JOIN qc_final q  ON q.subject = p.subject
GROUP BY p.site_code;
