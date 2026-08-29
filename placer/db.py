import json
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  cell TEXT, cdl TEXT, rows INTEGER, pattern TEXT,
  tracks INTEGER, threshold REAL, routability REAL,
  first TEXT, dumNumAdd_requested INTEGER, dumNumAdd_used INTEGER,
  ts TEXT, t_phase1 REAL, t_phase2 REAL, t_total REAL
);
CREATE TABLE IF NOT EXISTS placements (
  run_id INTEGER, W INTEGER, ovf INTEGER, cong INTEGER, wl INTEGER,
  align_g INTEGER, align_sd INTEGER, align_pg INTEGER, route INTEGER,
  first_type TEXT, grid_json TEXT
);
"""

def connect(path):
    cx = sqlite3.connect(path)
    cx.row_factory = sqlite3.Row
    cx.executescript(SCHEMA)
    return cx

def save_run(cx, meta, placements):
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    cur = cx.execute(
        """INSERT INTO runs(cell,cdl,rows,pattern,tracks,threshold,routability,first,
           dumNumAdd_requested,dumNumAdd_used,ts,t_phase1,t_phase2,t_total)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (meta['cell'], meta['cdl'], meta['rows'], meta['pattern'], meta['tracks'],
         meta['threshold'], meta['routability'], meta['first'],
         meta['dumNumAdd_requested'], meta['dumNumAdd_used'], ts,
         meta['t_phase1'], meta['t_phase2'], meta['t_total']))
    rid = cur.lastrowid
    for p in placements:
        cx.execute(
            """INSERT INTO placements(run_id,W,ovf,cong,wl,align_g,align_sd,align_pg,route,first_type,grid_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (rid, p['W'], p['ovf'], p['cong'], p['wl'], p['align_g'], p['align_sd'],
             p['align_pg'], p['route'], p['first_type'], json.dumps(p['grid'])))
    cx.commit()
    return rid

def get_run(cx, run_id=None, cell=None):
    if run_id is not None:
        row = cx.execute('SELECT * FROM runs WHERE id=?', (run_id,)).fetchone()
    elif cell:
        row = cx.execute('SELECT * FROM runs WHERE cell=? ORDER BY id DESC LIMIT 1', (cell,)).fetchone()
    else:
        row = cx.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 1').fetchone()
    if row is None:
        raise SystemExit('no run found')
    pls = cx.execute('SELECT * FROM placements WHERE run_id=?', (row['id'],)).fetchall()
    return row, pls
