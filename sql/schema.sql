-- Brain Ageing Across the Lifespan: database schema (SQLite)
-- One row per real-world thing; volumes in long format (one row per scan and structure).
-- Built by scripts/15_build_database.py.

PRAGMA foreign_keys = ON;

-- The three IXI hospitals and their scanners
CREATE TABLE sites (
    site_code        TEXT PRIMARY KEY,                  -- Guys, HH, IOP
    hospital         TEXT NOT NULL,
    scanner          TEXT,
    field_strength_t REAL
);

-- One row per participant with a T1 scan and a recorded age
CREATE TABLE participants (
    subject    TEXT PRIMARY KEY,                        -- e.g. IXI002-Guys-0828
    ixi_id     INTEGER NOT NULL,
    site_code  TEXT NOT NULL REFERENCES sites (site_code),
    sex        TEXT NOT NULL CHECK (sex IN ('female', 'male')),
    age        REAL NOT NULL CHECK (age BETWEEN 0 AND 120)
);

-- Scan-level measures: head size (SIENAX) and image quality (from FAST tissue maps)
CREATE TABLE scans (
    subject       TEXT PRIMARY KEY REFERENCES participants (subject),
    t1_file       TEXT NOT NULL,
    first_source  TEXT NOT NULL CHECK (first_source IN ('original', 'rerun')),
    icv_mm3       REAL CHECK (icv_mm3 > 0),             -- SIENAX-based head-size estimate
    vscaling      REAL CHECK (vscaling > 0),
    cnr           REAL,                                 -- grey/white contrast-to-noise
    snr           REAL                                  -- white-matter signal-to-noise
);

-- Lookup table of the 18 measured structures
CREATE TABLE structures (
    structure_code TEXT PRIMARY KEY,                    -- matches the CSV column names
    name           TEXT NOT NULL,
    hemisphere     TEXT NOT NULL CHECK (hemisphere IN ('left', 'right', 'both')),
    category       TEXT NOT NULL CHECK (category IN ('tissue', 'subcortical')),
    fsl_tool       TEXT NOT NULL CHECK (fsl_tool IN ('FAST', 'FIRST')),
    fsl_label      INTEGER                              -- FIRST label number (NULL for FAST)
);

-- Volumes in long format: one row per scan and structure (missing segmentations have no row)
CREATE TABLE volumes (
    subject         TEXT NOT NULL REFERENCES participants (subject),
    structure_code  TEXT NOT NULL REFERENCES structures (structure_code),
    volume_mm3      REAL NOT NULL CHECK (volume_mm3 >= 0),
    PRIMARY KEY (subject, structure_code)
);

-- Automatic QC flags (scripts/03_qc_flags.py)
CREATE TABLE qc_auto (
    subject  TEXT PRIMARY KEY REFERENCES participants (subject),
    flag     TEXT NOT NULL,                             -- pass, review, review_subcortical
    reasons  TEXT
);

-- Blind visual ratings exactly as entered: identified by random code only, never by subject
CREATE TABLE qc_ratings (
    code         TEXT NOT NULL,
    rating_set   TEXT NOT NULL CHECK (rating_set IN ('practice', 'main', 'retest')),
    pass         TEXT NOT NULL CHECK (pass IN ('first', 'reviewed')),
    sheet        INTEGER NOT NULL,
    whole_brain  INTEGER CHECK (whole_brain IN (0, 1, 2)),
    subcortical  INTEGER CHECK (subcortical IN (0, 1, 2)),
    note         TEXT,
    PRIMARY KEY (code, rating_set, pass)
);

-- Visual QC per subject (after unblinding; dealt out at random in the shuffled database)
CREATE TABLE qc_final (
    subject      TEXT PRIMARY KEY REFERENCES participants (subject),
    qc_wb        INTEGER CHECK (qc_wb IN (0, 1, 2)),          -- reviewed whole-brain rating
    qc_sc        INTEGER CHECK (qc_sc IN (0, 1, 2)),          -- reviewed subcortical rating
    qc_wb_first  INTEGER CHECK (qc_wb_first IN (0, 1, 2)),    -- first-pass ratings
    qc_sc_first  INTEGER CHECK (qc_sc_first IN (0, 1, 2)),
    volume_review_fail INTEGER NOT NULL DEFAULT 0 CHECK (volume_review_fail IN (0, 1))
                                                              -- 1 = confirmed FIRST failure in the extreme-volume
                                                              --     review (scripts/14b): qc_sc and qc_sc_first set to 2
);

-- How and when this database was built
CREATE TABLE build_info (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

CREATE INDEX idx_participants_site ON participants (site_code);
CREATE INDEX idx_volumes_structure ON volumes (structure_code);
