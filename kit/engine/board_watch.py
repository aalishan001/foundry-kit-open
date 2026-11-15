#!/usr/bin/env python3
"""Is each open application's posting still on its board? Report only: it never changes a status.
  board_watch.py          the applications flagged now (what /today shows)
Every sweep calls update() with each tier-1 board it read whole. For each open application whose job came from that
board (data/apps.json → data/jobs.json, tier 1):
  - on the board: seen, misses back to 0;
  - not on it: one miss (at most one a day);
  - when it's missing, its own posting page is asked once: 404 or 410 flags it at once.
Two misses in a row, or that 404/410, flag "no longer on its board" for the user to confirm. A 403 alone is never
enough (bot blocks answer 403 too). Jobs from alerts, paste-in sites or APIs have no board to watch.
State: data/board_watch.json.
"""
import re, sys
from _common import DATA, load, save, today
from fetch import FetchError, get, host_of, is_blocked

WATCH, MISSES, GONE = DATA / "board_watch.json", 2, (404, 410)

def load_watch(): return load(WATCH, {"apps": {}}) or {"apps": {}}

def probe(url):
    """HTTP status of a posting page: 200 when it answers, the error code when it doesn't, None when unknown."""
    try: get(url, robots=True, cache_hours=0); return 200
    except FetchError as e:
        m = re.search(r"HTTP (\d{3})", str(e))
        return int(m.group(1)) if m else None

def on_board(job, posts):
    url, ref = (job.get("url") or "").rstrip("/"), str((job.get("source") or {}).get("ref") or "")
    return any((p.get("url") or "").rstrip("/") == url or (ref and str(p.get("ref") or "") == ref) for p in posts)

def update(boards, probe_fn=None):
    """boards: {radar company: [postings]} read whole this sweep. -> flags raised (new and standing)."""
    from validate import APP_CLOSED
    probe_fn = probe_fn or probe
    jobs = {j["id"]: j for j in load(DATA / "jobs.json", {"jobs": []})["jobs"]}
    apps = [a for a in load(DATA / "apps.json", {"apps": []})["apps"] if a.get("status") not in APP_CLOSED and a.get("job") in jobs]
    w, day = load_watch(), today().isoformat()
    w["apps"] = {k: v for k, v in w["apps"].items() if k in {a["id"] for a in apps}}   # a closed application leaves the watch
    flags = []
    for a in apps:
        j = jobs[a["job"]]
        if (j.get("source") or {}).get("tier") != 1 or not str(j.get("url") or "").startswith("https://") or is_blocked(host_of(j["url"])): continue
        e = w["apps"].setdefault(a["id"], {"job": j["id"], "misses": 0, "last_seen": None, "last_missed": None, "flag": None})
        board = boards.get(j["company"])
        if board is None: continue   # its board wasn't read this time
        if on_board(j, board): e.update(misses=0, last_seen=day, flag=None); continue
        if e.get("last_missed") != day: e.update(misses=e["misses"] + 1, last_missed=day)
        code = probe_fn(j["url"])
        why = (f"its posting page answers HTTP {code}" if code in GONE else
               f"missing from {e['misses']} sweeps of its board in a row" if e["misses"] >= MISSES else None)
        if why:
            new = not e.get("flag")
            e["flag"] = {"since": (e.get("flag") or {}).get("since") or day, "why": why}
            flags.append({"app": a["id"], "job": j["id"], "company": a["company"], "role": a["role"], "why": why, "new": new})
    save(WATCH, w)
    return flags

def current():
    w = load_watch()
    apps = {a["id"]: a for a in load(DATA / "apps.json", {"apps": []})["apps"]}
    return [{"app": k, "company": apps[k]["company"], "role": apps[k]["role"], "why": v["flag"]["why"], "since": v["flag"]["since"]}
            for k, v in w["apps"].items() if v.get("flag") and k in apps]

def line(f):
    return f"{f['app']} {f['company']} · {f['role']}: no longer on its board ({f['why']}). The application stands; confirm with /update if it's closed."

def main(a):
    fl = current()
    for f in fl: print(line(f))
    if not fl: print("every watched posting is still on its board")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
