"""
Step 4d - Rating tool: rate the QC scans one at a time in your web browser.

Shows one scan at a time (mask | grey matter on top, FIRST structures underneath), large,
with only its code. Press keys to rate; each rating is saved straight into the rating CSV.
Close it any time and run it again: it starts at the first scan you haven't rated.

Run from the project folder, inside WSL:
  python3 scripts/08_rating_tool.py            # main set   -> data/qc_ratings.csv
  python3 scripts/08_rating_tool.py practice   # practice   -> data/qc_ratings_practice.csv
  python3 scripts/08_rating_tool.py retest     # retest     -> data/qc_ratings_retest.csv
  python3 scripts/08_rating_tool.py review     # second look at main-set scans rated 2 (and any unrated)
Then open  http://localhost:8765  in your browser (Edge or Chrome on Windows).
Stop it with Ctrl+C in the Ubuntu window.

Keys:
  0 1 2        first press = whole-brain rating, second press = subcortical rating
               (saves and moves to the next scan)
  N            add a note before the second rating (Enter saves the note)
  Enter        keep the ratings shown and move on (useful in review)
  Left/Right   previous / next scan       Z  zoom in and out       ?  show the rating guide

Blinding: the tool reads data/qc_key.csv to find each scan's images, but the browser
only ever receives the code and the picture - never the subject, site, age or flags.
Don't have the rating CSV open in Excel while using the tool (Excel locks the file).
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import csv
import io
import json
import os
import sys
import shutil
import time

from PIL import Image

PROJECT = Path(__file__).resolve().parent.parent
DATA, QC = PROJECT / "data", PROJECT / "qc"
PORT = 8765
SET = sys.argv[1] if len(sys.argv) > 1 else "main"
REVIEW = SET == "review"          # second look at main-set scans rated 2 (or left unrated)
if REVIEW:
    SET = "main"
FILES = {"main": "qc_ratings.csv", "practice": "qc_ratings_practice.csv", "retest": "qc_ratings_retest.csv"}
if SET not in FILES:
    sys.exit(f"Unknown set '{SET}'. Use one of: main, practice, retest")
RATINGS = DATA / FILES[SET]
FIELDS = ["code", "sheet", "whole_brain_rating", "subcortical_rating", "note"]

with (DATA / "qc_key.csv").open(newline="", encoding="utf-8-sig") as f:
    code_to_subject = {r["code"].strip(): r["subject"].strip() for r in csv.DictReader(f) if r["set"].strip() == SET}


def read_rows():
    with RATINGS.open(newline="", encoding="utf-8-sig") as f:
        rows = [{k: (r.get(k) or "").strip() for k in FIELDS} for r in csv.DictReader(f)]
    return [r for r in rows if r["code"]]


def write_rows(rows):
    tmp = RATINGS.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    for attempt in range(5):                     # OneDrive can hold the file for a moment
        try:
            os.replace(tmp, RATINGS)
            return
        except PermissionError:
            time.sleep(0.4)
    tmp.unlink(missing_ok=True)
    raise PermissionError


rows = read_rows()
missing = [r["code"] for r in rows if r["code"] not in code_to_subject]
if missing:
    sys.exit(f"{len(missing)} codes in {RATINGS.name} are not in qc_key.csv for set '{SET}'.")

SNAPSHOT = DATA / "qc_ratings_firstpass.csv"     # main ratings as they were before the review
REVIEW_LOG = DATA / "qc_review_log.csv"          # every review decision: before and after
review_codes, first_by_code = [], {}
if REVIEW:
    if not SNAPSHOT.exists():
        shutil.copyfile(RATINGS, SNAPSHOT)
    with SNAPSHOT.open(newline="", encoding="utf-8-sig") as f:
        first = [{k: (r.get(k) or "").strip() for k in FIELDS} for r in csv.DictReader(f)]
    first_by_code = {r["code"]: r for r in first}
    # scans currently rated 2 (or unrated), in sheet order
    review_codes = [r["code"] for r in rows
                    if "2" in (r["whole_brain_rating"], r["subcortical_rating"])
                    or "" in (r["whole_brain_rating"], r["subcortical_rating"])]


def reviewed_codes():
    if not REVIEW_LOG.exists():
        return []
    with REVIEW_LOG.open(newline="", encoding="utf-8-sig") as f:
        return [r["code"] for r in csv.DictReader(f)]


def log_review(code, wb, sc, note):
    new = not REVIEW_LOG.exists()
    with REVIEW_LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        if new:
            w.writerow(["code", "first_whole_brain", "first_subcortical", "review_whole_brain",
                        "review_subcortical", "note", "time"])
        fp = first_by_code[code]
        w.writerow([code, fp["whole_brain_rating"], fp["subcortical_rating"], wb, sc, note,
                    time.strftime("%Y-%m-%d %H:%M:%S")])


_cache = {}
def scan_png(code):
    if code not in _cache:
        s = code_to_subject[code]
        bet, gm, first = (Image.open(p).convert("RGB") for p in
                          (QC / f"{s}_bet.png", QC / f"{s}_gm.png", QC / "first_all" / f"{s}_first.png"))
        w = max(bet.width + gm.width, first.width)
        first = first.resize((w, round(first.height * w / first.width)))
        top_h = max(bet.height, gm.height)
        img = Image.new("RGB", (w, top_h + 12 + first.height), "black")
        img.paste(bet, (0, 0))
        img.paste(gm, (bet.width, 0))
        img.paste(first, (0, top_h + 12))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        _cache[code] = buf.getvalue()
        if len(_cache) > 40:
            _cache.pop(next(iter(_cache)))
    return _cache[code]


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>QC rating</title>
<style>
:root{--bg:#111;--panel:#1c1c1c;--text:#eee;--muted:#999;--accent:#f5c518;--ok:#4caf50;--warn:#ff9800;--bad:#f44336}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px system-ui,Segoe UI,sans-serif}
header{display:flex;gap:20px;align-items:center;padding:10px 16px;background:var(--panel);flex-wrap:wrap}
#code{font-size:26px;font-weight:700;color:var(--accent)}#prog{color:var(--muted)}
#bar{flex:1;min-width:120px;height:6px;background:#333;border-radius:3px}#fill{height:100%;background:var(--accent);border-radius:3px;width:0}
main{padding:10px 16px;text-align:center}#wrap{overflow:auto;max-height:calc(100vh - 210px)}
#img{width:100%;max-width:1600px;image-rendering:auto;cursor:zoom-in}#img.zoom{width:auto;max-width:none;height:auto;transform-origin:top left;zoom:1.8;cursor:zoom-out}
.labels{display:flex;max-width:1600px;margin:2px auto 0;color:var(--muted);font-size:12px}.labels span{flex:1}
footer{position:fixed;bottom:0;left:0;right:0;background:var(--panel);padding:10px 16px;display:flex;gap:24px;align-items:center;flex-wrap:wrap}
.grp b{display:inline-block;width:110px}.btn{display:inline-block;min-width:44px;padding:6px 10px;margin:0 3px;border:1px solid #444;border-radius:6px;background:#2a2a2a;color:var(--text);cursor:pointer;font-size:16px}
.btn.sel0{background:var(--ok);border-color:var(--ok)}.btn.sel1{background:var(--warn);border-color:var(--warn);color:#111}.btn.sel2{background:var(--bad);border-color:var(--bad)}
.grp.active b{color:var(--accent)}#note{width:280px;padding:6px;background:#2a2a2a;color:var(--text);border:1px solid #444;border-radius:6px}
#msg{color:var(--muted)}#msg.err{color:var(--bad);font-weight:700}
#help{display:none;position:fixed;inset:40px;background:#222;border:1px solid #555;border-radius:10px;padding:20px 28px;overflow:auto;text-align:left;z-index:5}
#help h3{color:var(--accent);margin-top:14px}kbd{background:#333;border:1px solid #555;border-radius:4px;padding:1px 6px}
</style></head><body>
<header><span id="code">Scan ----</span><span id="prog"></span><div id="bar"><div id="fill"></div></div>
<span id="msg"></span><span class="btn" onclick="toggleHelp()">? Guide</span></header>
<main><div id="wrap"><img id="img" onclick="this.classList.toggle('zoom')"></div>
<div class="labels"><span>mask outline</span><span>grey matter</span></div></main>
<footer>
<div class="grp" id="g_wb"><b>Whole brain</b><span class="btn" data-g="wb" data-v="0">0</span><span class="btn" data-g="wb" data-v="1">1</span><span class="btn" data-g="wb" data-v="2">2</span></div>
<div class="grp" id="g_sc"><b>Subcortical</b><span class="btn" data-g="sc" data-v="0">0</span><span class="btn" data-g="sc" data-v="1">1</span><span class="btn" data-g="sc" data-v="2">2</span></div>
<input id="note" placeholder="Note (press N)">
<span style="color:var(--muted)"><kbd>&larr;</kbd><kbd>&rarr;</kbd> move &nbsp; <kbd>Enter</kbd> keep &nbsp; <kbd>Z</kbd> zoom &nbsp; <kbd>?</kbd> guide</span>
</footer>
<div id="help" onclick="toggleHelp()">
<h2>Rating guide (summary) - full version in QC_RATING_GUIDE.md</h2>
<h3>Whole brain (top row: mask outline, grey matter)</h3>
<p><b>0 Good</b> - mask follows the brain edge all round; clear cortical ribbon and deep grey matter.<br>
<b>1 Minor</b> - thin strip of dura/skull inside, a little cortex clipped, mild motion blur, slightly patchy GM.<br>
<b>2 Fail</b> - a whole region cut off, eyes/neck inside the mask, GM mislabelled across a lobe, or unusable motion.</p>
<h3>Subcortical (bottom row: FIRST structures, left = yellow, right = red)</h3>
<p><b>0 Good</b> - each structure on its anatomy, follows its edges, left and right alike.<br>
<b>1 Minor</b> - a little too big/small or a few voxels into white matter or a ventricle.<br>
<b>2 Fail</b> - a structure in the wrong place, missing, much too big/small, straight-edged/boxy, or no outlines.</p>
<h3>When unsure</h3><p>Between 0 and 1, pick 1. Between 1 and 2: would the error change the volume by more than a few percent? If yes, 2. Atrophy segmented correctly is 0.</p>
<p style="color:var(--muted)">Click anywhere to close.</p></div>
<script>
let codes=[],i=0,cur={},step=0,isReview=false,reviewed=new Set();const $=id=>document.getElementById(id);
async function load(){const s=await (await fetch('/api/state')).json();codes=s.rows;i=s.start;isReview=s.set==='review';reviewed=new Set(s.reviewed||[]);$('prog').dataset.set=s.set;show();}
function done(){if(isReview)return reviewed.size;return codes.filter(r=>r.whole_brain_rating!==''&&r.subcortical_rating!=='').length}
function show(){if(i>=codes.length){i=codes.length-1;msg('All scans in this set are rated. You can close the tool.');}
 cur=codes[i];$('code').textContent='Scan '+cur.code;
 $('prog').textContent=`${$('prog').dataset.set} - scan ${i+1} of ${codes.length} (sheet ${cur.sheet}) - ${done()} ${isReview?'reviewed':'rated'}`;
 $('fill').style.width=(100*done()/codes.length)+'%';$('img').src='/img/'+cur.code+'.png';$('note').value=cur.note;
 step=cur.whole_brain_rating===''?0:(cur.subcortical_rating===''?1:0);paint();
 if(i+1<codes.length){new Image().src='/img/'+codes[i+1].code+'.png';}}
function paint(){document.querySelectorAll('.btn[data-g]').forEach(b=>{const v=b.dataset.g==='wb'?cur.whole_brain_rating:cur.subcortical_rating;b.className='btn'+(v===b.dataset.v?' sel'+v:'');});
 $('g_wb').classList.toggle('active',step===0);$('g_sc').classList.toggle('active',step===1);}
function msg(t,err){$('msg').textContent=t;$('msg').className=err?'err':'';}
async function save(){let r;try{r=await fetch('/api/rate',{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify({code:cur.code,wb:cur.whole_brain_rating,sc:cur.subcortical_rating,note:cur.note})});}catch(e){msg('NOT SAVED: the tool is not running. Start it again in Ubuntu, then reload this page.',true);return false;}
 const j=await r.json();if(!j.ok){msg(j.error,true);return false;}if(isReview)reviewed.add(cur.code);msg('Saved scan '+cur.code);return true;}
async function rate(g,v){if(g==='wb'){cur.whole_brain_rating=v;step=1;paint();}
 else{cur.subcortical_rating=v;if(cur.whole_brain_rating===''){step=0;paint();return;}paint();if(await save()){i++;show();}}}
document.querySelectorAll('.btn[data-g]').forEach(b=>b.onclick=()=>rate(b.dataset.g,b.dataset.v));
$('note').addEventListener('keydown',async e=>{if(e.key==='Enter'||e.key==='Escape'){cur.note=$('note').value.replace(/,/g,';');$('note').blur();
 if(cur.whole_brain_rating!==''&&cur.subcortical_rating!=='')await save();}e.stopPropagation();});
function toggleHelp(){const h=$('help');h.style.display=h.style.display==='block'?'none':'block';}
document.addEventListener('keydown',e=>{if(document.activeElement===$('note'))return;
 if(['0','1','2'].includes(e.key)){rate(step===0?'wb':'sc',e.key);}
 else if((e.key==='Enter'||e.key===' ')&&cur.whole_brain_rating!==''&&cur.subcortical_rating!==''){e.preventDefault();save().then(ok=>{if(ok){i++;show();}});}
 else if(e.key==='ArrowRight'&&i<codes.length-1){i++;show();}else if(e.key==='ArrowLeft'&&i>0){i--;show();}
 else if(e.key==='n'||e.key==='N'){e.preventDefault();$('note').focus();}
 else if(e.key==='z'||e.key==='Z'){$('img').classList.toggle('zoom');}
 else if(e.key==='?'||e.key==='/'){toggleHelp();}else if(e.key==='Escape'){$('help').style.display='none';}});
load();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, body, ctype, status=200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store" if ctype != "image/png" else "max-age=3600")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self.send(PAGE.encode(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            rs = read_rows()
            if REVIEW:
                by = {r["code"]: r for r in rs}
                rs = [by[c] for c in review_codes]
                done = set(reviewed_codes())
                start = next((n for n, r in enumerate(rs) if r["code"] not in done), max(len(rs) - 1, 0))
                body = {"set": "review", "rows": rs, "start": start, "reviewed": sorted(done)}
            else:
                start = next((n for n, r in enumerate(rs)
                              if r["whole_brain_rating"] == "" or r["subcortical_rating"] == ""), len(rs) - 1)
                body = {"set": SET, "rows": rs, "start": start}
            self.send(json.dumps(body).encode(), "application/json")
        elif self.path.startswith("/img/") and self.path.endswith(".png"):
            code = self.path[5:-4]
            if code in code_to_subject:
                self.send(scan_png(code), "image/png")
            else:
                self.send(b"not found", "text/plain", 404)
        else:
            self.send(b"not found", "text/plain", 404)

    def do_POST(self):
        if self.path != "/api/rate":
            return self.send(b"not found", "text/plain", 404)
        d = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        ok = {"0", "1", "2", ""}
        if d.get("wb") not in ok or d.get("sc") not in ok:
            return self.send(json.dumps({"ok": False, "error": "Ratings must be 0, 1 or 2"}).encode(), "application/json")
        try:
            rs = read_rows()
            for r in rs:
                if r["code"] == d["code"]:
                    r["whole_brain_rating"], r["subcortical_rating"] = d["wb"], d["sc"]
                    r["note"] = str(d.get("note", "")).replace(",", ";").replace("\n", " ").strip()
            write_rows(rs)
            if REVIEW and d["wb"] and d["sc"]:
                log_review(d["code"], d["wb"], d["sc"],
                           str(d.get("note", "")).replace(",", ";").replace("\n", " ").strip())
            self.send(json.dumps({"ok": True}).encode(), "application/json")
        except PermissionError:
            self.send(json.dumps({"ok": False, "error": f"Couldn't save: close {RATINGS.name} in Excel, then press the key again."}).encode(),
                      "application/json")


n_done = sum(1 for r in rows if r["whole_brain_rating"] and r["subcortical_rating"])
if REVIEW:
    print(f"Review mode: {len(review_codes)} scans rated 2 or unrated in the first pass; "
          f"{len(set(reviewed_codes()))} reviewed so far.")
    print("First-pass ratings kept in data/qc_ratings_firstpass.csv; decisions logged in data/qc_review_log.csv")
print(f"Rating set '{SET}': {n_done} of {len(rows)} scans rated so far. Saving to data/{RATINGS.name}")
print(f"Open http://localhost:{PORT} in your browser. Press Ctrl+C here to stop.")
try:
    ThreadingHTTPServer((os.environ.get("HOST", "127.0.0.1"), PORT), Handler).serve_forever()
except KeyboardInterrupt:
    print("\nStopped. Your ratings are saved.")
