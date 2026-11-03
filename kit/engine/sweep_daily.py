#!/usr/bin/env python3
"""The engine part of /sweep, with no AI: run every morning by Windows Task Scheduler (schedule.py), or by /sweep when
the morning run didn't happen.
  sweep_daily.py [--if-older H] [--dry-run]   read every tier-1 radar company, the Gmail Job Alerts label (if set up)
                                              and the job-search APIs (if keys are set); dedupe and prefilter; add new
                                              jobs as status new, waiting to be ranked; report, log, backup commit.
                                              --if-older 20: only if the last run is older than 20 hours
  sweep_daily.py report [<file>]              the last daily run: new jobs, paste-in reminders, failures, drops
A failing portal, Gmail or API is reported and skipped; the run carries on. A lock stops two runs at once. Output
goes to data/logs/sweep_daily.log as well (the scheduled run has no window).
"""
import datetime as dt, json, os, sys, time, traceback
from _common import DATA, load, save, opt, today, now, stamp, ts_name, rel, search_rules, unique_path

SWEEPS, LOGS = DATA / "sweeps", DATA / "logs"
LOCK, LOG = DATA / "tmp" / "sweep_daily.lock", LOGS / "sweep_daily.log"
STALE_LOCK_HOURS = 3

def log(msg):
    LOGS.mkdir(parents=True, exist_ok=True)
    line = f"{stamp()}  {msg}"
    with open(LOG, "a", encoding="utf-8", newline="\n") as f: f.write(line + "\n")
    try: print(msg, flush=True)
    except Exception: pass   # pythonw: no console

def last_run():
    files = sorted(SWEEPS.glob("*-daily.json"), key=lambda f: f.stat().st_mtime) if SWEEPS.exists() else []
    return (load(files[-1]), files[-1]) if files else (None, None)

def take_lock():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    if LOCK.exists() and time.time() - LOCK.stat().st_mtime < STALE_LOCK_HOURS * 3600: return False
    LOCK.write_text(f"{os.getpid()} {stamp()}\n", encoding="utf-8")
    return True

def tier1(rep, rules, dry):
    import radar, sweep, jobs
    rad = radar.load_radar()
    known = jobs.load_jobs()["jobs"]
    for c in rad["companies"]:
        if c["portal"].get("tier") != 1:
            if radar.due_date(c) <= today(): rep["reminders"].append({"company": c["company"], "url": c["careers_url"], "how": c.get("how", ""),
                                                                      "alert": (c.get("alert") or {}).get("url")})
            continue
        try: r, upd = sweep.sweep_company(c, rules, known, 10, dry)
        except Exception as e: r, upd = {"company": c["company"], "found": 0, "known": 0, "dropped": [], "added": [], "error": f"{type(e).__name__}: {e}"}, None
        rep["companies"].append(r)
        rep["added"] += r["added"]
        if not dry: radar.record_check(rad, c, r["found"], len(r["added"]), r["error"] or f"{r['found']} openings, {len(r['added'])} new (daily)", portal_update=upd)
    if not dry: save(radar.RADAR, rad)

def gmail(rep, rules, dry):
    import gmail_imap, sweep
    if not (rules.get("gmail") or {}).get("enabled"): rep["gmail"] = "off"; return
    try: files = gmail_imap.fetch(dry=dry)
    except Exception as e: rep["gmail"] = f"error: {e}"; rep["failures"].append(f"Gmail: {e}"); return
    if dry: rep["gmail"] = f"{len(files)} new message(s) (dry run: not read)"; return
    n = 0
    for f in files:
        try: rows, added, dupes, dropped = sweep.import_alerts(str(f), rules, dry)
        except Exception as e: rep["failures"].append(f"Gmail message {f.name}: {e}"); continue
        n += len(rows); rep["added"] += [j["id"] for j in added] if not dry else []; rep["dropped_alerts"] += dropped
    rep["gmail"] = f"{len(files)} new message(s), {n} posting(s)"

def apis(rep, rules, dry):
    import job_apis
    try:
        out = job_apis.collect(rules=rules)
        added, dropped, dupes = job_apis.add(out, dry, rules)
    except Exception as e: rep["failures"].append(f"job-search APIs: {e}"); return
    rep["apis"] = {k: {"calls": v["calls"], "postings": len(v["postings"]), "skipped": v["skipped"], "errors": v["errors"][:3]} for k, v in out.items()}
    rep["added"] += [j["id"] for j in added] if not dry else []
    rep["dropped_api"] = dropped

def run(args):
    dry = "--dry-run" in args
    older = opt(args, "--if-older")
    if older:
        prev, _ = last_run()
        if prev and (now() - dt.datetime.fromisoformat(prev["ts"])).total_seconds() < float(older) * 3600:
            print(f"the daily sweep already ran at {prev['ts'][11:16]} on {prev['ts'][:10]}: nothing to fetch"); return 0
    if not take_lock(): print("a sweep is already running: try again in a few minutes"); return 0
    rules, p = search_rules(), None
    rep = {"ts": stamp(), "kind": "daily", "companies": [], "reminders": [], "added": [], "failures": [], "dropped_alerts": [], "dropped_api": []}
    try:
        log("daily sweep started" + (" (dry run)" if dry else ""))
        for step in (tier1, gmail, apis):
            try: step(rep, rules, dry)
            except Exception as e:
                rep["failures"].append(f"{step.__name__}: {type(e).__name__}: {e}")
                log(traceback.format_exc().strip().splitlines()[-1])
        rep["failures"] += [f"{r['company']}: {r['error']}" for r in rep["companies"] if r.get("error")]
        if not dry:
            p = unique_path(SWEEPS, f"{ts_name()}-daily", "json"); save(p, rep)
            try:
                import backup
                if backup.is_repo(): backup.commit(f"daily sweep: {len(rep['added'])} new")
            except SystemExit: pass
            except Exception as e: log(f"backup commit failed: {e}")
        log(f"daily sweep done: {len(rep['added'])} new, {len(rep['failures'])} failure(s), {len(rep['reminders'])} paste-in due")
    finally:
        LOCK.unlink(missing_ok=True)
    show(rep, rel(p) if p else None)
    return 0

def show(rep, path=None):
    import jobs
    rows = {j["id"]: j for j in jobs.load_jobs()["jobs"]}
    print(f"Daily sweep {rep['ts'][:16].replace('T', ' ')}: {len(rep['added'])} new")
    for i in rep["added"]:
        j = rows.get(i)
        if j: print(f"  {i}  {j['company']} · {j['title']}  {j['location'] or '-'}  (via {j['source']['via']})")
    print(f"Gmail: {rep.get('gmail', 'off')}")
    for k, v in (rep.get("apis") or {}).items():
        print(f"{k}: " + (v["skipped"] if v["skipped"] and not v["calls"] else f"{v['calls']} call(s), {v['postings']} posting(s)"))
    if rep["reminders"]:
        print(f"Paste-in companies due ({len(rep['reminders'])}):")
        for r in rep["reminders"]: print(f"  {r['company']:<30} {r['url']}" + ("  (alert sign-up exists)" if r.get("alert") else ""))
    if rep["failures"]:
        print(f"Couldn't read ({len(rep['failures'])}):")
        for f in rep["failures"]: print(f"  {f}")
    d = sum(len(r["dropped"]) for r in rep["companies"]) + len(rep["dropped_alerts"]) + len(rep["dropped_api"])
    if d: print(f"Dropped {d} by the rules (level, country, company, role family)")
    if path: print(f"Saved {path}")

def report(args):
    if args:
        from _common import HOME
        rep = load(HOME / args[0])
    else: rep, _ = last_run()
    if not rep: print("no daily sweep yet: sweep_daily.py"); return 0
    show(rep); return 0

def main(a):
    if a and a[0] in ("-h", "--help"): print(__doc__); return 0
    if a and a[0] == "report": return report(a[1:])
    try: return run(a)
    except Exception:
        log("daily sweep crashed: " + traceback.format_exc().strip().splitlines()[-1]); raise

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
