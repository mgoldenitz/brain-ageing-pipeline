"""
Step 9 - Build the SQLite database (sql/schema.sql, sql/views.sql) and run the example
queries (sql/example_queries.sql).

  ~/brainenv/bin/python scripts/15_build_database.py --shuffled
      BLIND: participants' age, sex and site, and the per-subject QC ratings, come from the
      shuffled dataset (data/analysis_shuffled.csv) -> data/brain_ageing_shuffled.db
  ~/brainenv/bin/python scripts/15_build_database.py
      REAL (after unblinding): needs data/analysis_dataset.csv -> data/brain_ageing.db

Tables: sites, participants, scans, structures, volumes (long format), qc_auto,
qc_ratings (coded, never linked to subjects), qc_final, build_info.
Views: v_scan_wide, v_volumes_qc, v_site_summary.
Query results are saved to results/<shuffled|real>/sql_example_queries.txt.
Open the .db file in DB Browser for SQLite (free) to explore it with a point-and-click interface.
"""

from datetime import datetime
from pathlib import Path
import re
import sqlite3
import sys

import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
DATA, SQL = PROJECT / "data", PROJECT / "sql"
SHUFFLED = "--shuffled" in sys.argv
STEM = "analysis_shuffled" if SHUFFLED else "analysis_dataset"
DB = DATA / ("brain_ageing_shuffled.db" if SHUFFLED else "brain_ageing.db")
OUT = PROJECT / "results" / ("shuffled" if SHUFFLED else "real")
OUT.mkdir(parents=True, exist_ok=True)

SITES = [("Guys", "Guy's Hospital, London", "Philips", 1.5),
         ("HH", "Hammersmith Hospital, London", "Philips", 3.0),
         ("IOP", "Institute of Psychiatry, London", "GE", 1.5)]
STRUCTURES = [  # code, name, hemisphere, category, tool, FIRST label
    ("gm", "Grey matter", "both", "tissue", "FAST", None),
    ("wm", "White matter", "both", "tissue", "FAST", None),
    ("csf", "Cerebrospinal fluid", "both", "tissue", "FAST", None),
    ("L_Thal", "Thalamus", "left", "subcortical", "FIRST", 10),
    ("L_Caud", "Caudate", "left", "subcortical", "FIRST", 11),
    ("L_Puta", "Putamen", "left", "subcortical", "FIRST", 12),
    ("L_Pall", "Pallidum", "left", "subcortical", "FIRST", 13),
    ("L_Hipp", "Hippocampus", "left", "subcortical", "FIRST", 17),
    ("L_Amyg", "Amygdala", "left", "subcortical", "FIRST", 18),
    ("L_Accu", "Nucleus accumbens", "left", "subcortical", "FIRST", 26),
    ("R_Thal", "Thalamus", "right", "subcortical", "FIRST", 49),
    ("R_Caud", "Caudate", "right", "subcortical", "FIRST", 50),
    ("R_Puta", "Putamen", "right", "subcortical", "FIRST", 51),
    ("R_Pall", "Pallidum", "right", "subcortical", "FIRST", 52),
    ("R_Hipp", "Hippocampus", "right", "subcortical", "FIRST", 53),
    ("R_Amyg", "Amygdala", "right", "subcortical", "FIRST", 54),
    ("R_Accu", "Nucleus accumbens", "right", "subcortical", "FIRST", 58),
    ("BrStem", "Brainstem", "both", "subcortical", "FIRST", 16),
]
VOLS = [s[0] for s in STRUCTURES]

src = DATA / f"{STEM}.csv"
if not src.exists():
    sys.exit(f"{src.relative_to(PROJECT)} not found. Run scripts/09_build_dataset.py "
             f"{'--shuffled ' if SHUFFLED else ''}first.")
d = pd.read_csv(src)
if bool(d["shuffled"].iloc[0]) != SHUFFLED:
    sys.exit("The dataset's 'shuffled' flag doesn't match the --shuffled option.")

part = pd.read_csv(DATA / "participants.csv")[["subject", "ixi_id", "file"]]
head = pd.read_csv(DATA / "head_size.csv")[["subject", "vscaling"]]
auto = pd.read_csv(DATA / "qc_auto.csv")[["subject", "qc_auto", "qc_reasons"]]   # flags only

DB.unlink(missing_ok=True)
con = sqlite3.connect(DB)
con.execute("PRAGMA foreign_keys = ON")
con.executescript((SQL / "schema.sql").read_text())

con.executemany("INSERT INTO sites VALUES (?, ?, ?, ?)", SITES)
con.executemany("INSERT INTO structures VALUES (?, ?, ?, ?, ?, ?)", STRUCTURES)

p = d[["subject", "site", "sex", "age"]].merge(part, on="subject", how="left")
con.executemany("INSERT INTO participants VALUES (?, ?, ?, ?, ?)",
                p[["subject", "ixi_id", "site", "sex", "age"]].itertuples(index=False))

s = d[["subject", "first_source", "icv", "cnr", "snr"]].merge(head, on="subject").merge(part, on="subject")
con.executemany("INSERT INTO scans VALUES (?, ?, ?, ?, ?, ?, ?)",
                s[["subject", "file", "first_source", "icv", "vscaling", "cnr", "snr"]].itertuples(index=False))

long = d.melt(id_vars="subject", value_vars=VOLS, var_name="structure_code", value_name="volume_mm3").dropna()
con.executemany("INSERT INTO volumes VALUES (?, ?, ?)", long.itertuples(index=False))

auto = auto[auto.subject.isin(d.subject)].where(auto.notna(), None)
con.executemany("INSERT INTO qc_auto VALUES (?, ?, ?)", auto.itertuples(index=False))


def coded(file, rating_set, pass_):
    r = pd.read_csv(DATA / file, dtype=str, encoding="utf-8-sig").fillna("")
    r = r.apply(lambda c: c.str.strip())
    rows = []
    for _, x in r.iterrows():
        to_int = lambda v: int(v) if v != "" else None
        rows.append((x["code"], rating_set, pass_, int(x["sheet"]), to_int(x["whole_brain_rating"]),
                     to_int(x["subcortical_rating"]), x["note"] or None))
    return rows


for file, rs, ps in [("qc_ratings_practice.csv", "practice", "first"),
                     ("qc_ratings_firstpass.csv", "main", "first"),
                     ("qc_ratings.csv", "main", "reviewed"),
                     ("qc_ratings_retest.csv", "retest", "first")]:
    con.executemany("INSERT INTO qc_ratings VALUES (?, ?, ?, ?, ?, ?, ?)", coded(file, rs, ps))

qc = d[["subject", "qc_wb", "qc_sc", "qc_wb_first", "qc_sc_first"]].astype(object)
qc = qc.where(qc.notna(), None)
for c in ["qc_wb", "qc_sc", "qc_wb_first", "qc_sc_first"]:
    qc[c] = qc[c].map(lambda v: None if v is None else int(v))
con.executemany("INSERT INTO qc_final VALUES (?, ?, ?, ?, ?)", qc.itertuples(index=False))

con.executemany("INSERT INTO build_info VALUES (?, ?)", [
    ("mode", "SHUFFLED (blind analysis: age, sex, site and QC ratings shuffled)" if SHUFFLED else "real"),
    ("built", datetime.now().isoformat(timespec="seconds")),
    ("source", src.name), ("sqlite_version", sqlite3.sqlite_version)])
con.executescript((SQL / "views.sql").read_text())
con.commit()

# ---- Integrity checks ----------------------------------------------------------------------
problems = con.execute("PRAGMA foreign_key_check").fetchall()
counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
          for t in ["sites", "participants", "scans", "structures", "volumes", "qc_auto", "qc_ratings", "qc_final"]}
print(f"{'BLIND ANALYSIS (shuffled data)' if SHUFFLED else 'REAL DATA'} - built {DB.relative_to(PROJECT)}")
print("Rows:", ", ".join(f"{t} {n}" for t, n in counts.items()))
print("Foreign-key problems:", len(problems))
assert counts["participants"] == len(d) and not problems

# ---- Example queries ------------------------------------------------------------------------
text = (SQL / "example_queries.sql").read_text()
blocks = re.split(r"^-- @query ", text, flags=re.M)[1:]
lines = [f"EXAMPLE QUERIES - {'BLIND ANALYSIS, SHUFFLED DATA: demographic and QC results are meaningless' if SHUFFLED else 'REAL DATA'}", ""]
pd.set_option("display.width", 200)
for b in blocks:
    title, sql = b.split("\n", 1)
    res = pd.read_sql_query(sql, con)
    lines += [title, res.to_string(index=False), ""]
con.close()
(OUT / "sql_example_queries.txt").write_text("\n".join(lines))
print("\n".join(lines[:12]))
print(f"... all {len(blocks)} query results saved to {(OUT / 'sql_example_queries.txt').relative_to(PROJECT)}")
