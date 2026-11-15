#!/usr/bin/env python3
"""Pull new openings. Tier 1 automatically; tier 2 from alert emails they pasted; tier 3 listed as reminders.
  sweep.py [--all | --company <name>] [--max-jd N] [--dry-run]
        every due tier-1 radar company (or all, or one): fetch openings, skip known ones, apply the deterministic
        prefilter (level, country, role family), fetch the JD only for the ones that pass (up to N per company,
        default 10), add them to data/jobs.json as new, record the radar check, and write data/sweeps/<ts>.json
  sweep.py alerts <file> [--dry-run]   job-alert email(s) (pasted text saved to a file, .txt or .eml): same prefilter,
        added as tier 2 without a JD (links from LinkedIn or Naukri are kept, never fetched)
  sweep.py dropped [<sweep file>]      what the last sweep dropped, and why
A portal that fails is reported and skipped; the sweep carries on. A static page that can't be read without a
browser becomes paste-in (tier 3), and they are told.
"""
import json, sys
from _common import DATA, load, save, opt, die, today, ts_name, stamp, rel, search_rules, unique_path
import fit, jobs, radar, sources
from fetch import FetchError

SWEEPS = DATA / "sweeps"

def targets(rad, args):
    if opt(args, "--company"):
        c = radar.find(rad, opt(args, "--company")) or die(f"{opt(args, '--company')} is not on the radar")
        return [c]
    due = lambda c: radar.due_date(c) <= today()
    return [c for c in rad["companies"] if "--all" in args or due(c)]

def sweep_company(c, rules, known, max_jd, dry, boards=None):
    rep = {"company": c["company"], "found": 0, "known": 0, "dropped": [], "added": [], "reposts": [], "error": None}
    try: posts = sources.openings(c)
    except sources.Unreadable as e:
        rep["error"] = f"unreadable: {e}"; return rep, {"tier": 3, "probe": False}
    except FetchError as e:
        rep["error"] = str(e); return rep, None
    rep["found"] = len(posts)
    if boards is not None: boards[c["company"]] = posts   # the whole read, for the board watch
    keep, reposts = [], []
    for p in posts:
        if not p["title"]: continue
        hit = jobs.existing(known, p)
        if hit and p.get("url") and hit.get("url") and p["url"] != hit["url"]:   # same title and place, new posting: a repost
            reposts.append(p); continue
        if hit: rep["known"] += 1; continue
        ok, why = fit.prefilter(p, rules, company=c)
        if ok: keep.append(p)
        else: rep["dropped"].append({"title": p["title"], "location": p["location"], "url": p["url"], "why": why})
    items, texts = [], {}
    for i, p in enumerate(keep):
        jd = None
        if i < max_jd:
            try: jd = sources.jd_text(c, p)
            except FetchError as e: rep.setdefault("jd_errors", []).append(f"{p['title']}: {e}")
        if jd and len(jd.strip()) >= 200: texts[len(items)] = jd
        items.append({"company": p["company"], "title": p["title"], "url": p["url"], "location": p["location"], "remote": p["remote"],
                      "posted": p["posted"], "source": {"tier": 1, "via": c["portal"]["type"], "ref": p.get("ref")}})
    items += [{"company": p["company"], "title": p["title"], "url": p["url"], "location": p["location"], "remote": p["remote"],
               "posted": p["posted"], "source": {"tier": 1, "via": c["portal"]["type"], "ref": p.get("ref")}} for p in reposts]
    added, _ = jobs.add_jobs(items, texts, dry)
    known += added
    fresh = [j for j in added if j["status"] != "repost"]
    rep["added"] = [j["id"] for j in fresh] if not dry else [f"(dry) {j['title']}" for j in fresh]
    rep["reposts"] = [{"id": j.get("id"), "repost_of": j["repost_of"], "title": j["title"]} for j in added if j["status"] == "repost"]
    return rep, ({"probe": False} if c["portal"].get("probe") else None)

def run(args):
    rad, rules = radar.load_radar(), search_rules()
    if not (rules.get("current") or {}).get("ladder_rank"): print("NOTE: their current level isn't set, so no role is dropped for level (profile_cli.py current)")
    dry, max_jd = "--dry-run" in args, int(opt(args, "--max-jd", "10"))
    known = jobs.load_jobs()["jobs"]
    report = {"ts": stamp(), "companies": [], "reminders": []}
    boards = {}
    for c in targets(rad, args):
        if c["portal"]["tier"] != 1:
            report["reminders"].append({"company": c["company"], "url": c["careers_url"], "how": c.get("how", "")}); continue
        rep, portal_update = sweep_company(c, rules, known, max_jd, dry, boards)
        report["companies"].append(rep)
        if not dry:
            note = rep["error"] or f"{rep['found']} openings, {len(rep['added'])} new"
            radar.record_check(rad, c, rep["found"], len(rep["added"]), note, portal_update=portal_update)
    if not dry:
        import board_watch
        report["gone"] = board_watch.update(boards)
        save(radar.RADAR, rad)
        p = unique_path(SWEEPS, ts_name(), "json"); save(p, report)
    show(report, None if dry else rel(p))
    return 0

def show(report, path):
    new = []
    print(f"{'Company':<30} {'found':>5} {'known':>5} {'dropped':>7} {'new':>4}")
    for r in report["companies"]:
        if r["error"]: print(f"{r['company']:<30} {'':>5} {'':>5} {'':>7} {'':>4}  {r['error']}"); continue
        print(f"{r['company']:<30} {r['found']:>5} {r['known']:>5} {len(r['dropped']):>7} {len(r['added']):>4}")
        new += r["added"]
    rows = {j["id"]: j for j in jobs.load_jobs()["jobs"]}
    if new:
        print(f"\nNew ({len(new)}):")
        for i in new:
            j = rows.get(i)
            print(f"  {i}  {j['company']} · {j['title']}  {j['location'] or '-'}" + ("" if j.get("jd") else "  (no JD yet)") if j else f"  {i}")
    if report["reminders"]:
        print(f"\nPaste-in companies due ({len(report['reminders'])}): open the link, copy any matching posting into /check")
        for r in report["reminders"]: print(f"  {r['company']:<30} {r['url']}")
    unread = [r["company"] for r in report["companies"] if (r["error"] or "").startswith("unreadable")]
    if unread: print("\nSwitched to paste-in (the page needs a browser): " + ", ".join(unread))
    rp = [x for r in report["companies"] for x in r.get("reposts", [])]
    if rp: print(chr(10) + "Reposts (shown once, not ranked again): " + "; ".join(f"{x['title']} = repost of {x['repost_of']}" for x in rp))
    dropped = sum(len(r["dropped"]) for r in report["companies"])
    if dropped: print(f"\nDropped {dropped} by the rules (level, country, role family): sweep.py dropped")
    import board_watch
    for f in report.get("gone") or []: print(("\nNo longer on its board: " if f["new"] else "  still gone: ") + board_watch.line(f))
    if path: print(f"\nSaved {path}")

def import_alerts(path, rules=None, dry=False):
    """One alert email (pasted .txt or .eml): parse, prefilter, add the survivors as tier 2. -> (rows, added, dupes, dropped)."""
    import alerts as al
    rules = rules or search_rules()
    rows = al.parse_file(path)
    items, dropped = [], []
    for r in rows:
        if not r["company"]: dropped.append({**r, "why": "no company in the email: add it by hand if it matters"}); continue
        ok, why = fit.prefilter({"title": r["title"], "location": r["location"]}, rules)
        if not ok: dropped.append({**r, "why": why}); continue
        items.append({"company": r["company"], "title": r["title"], "location": r["location"],
                      "url": r["url"] if r["url"].startswith("https://") else None, "source": {"tier": 2, "via": r["via"]}})
    added, dupes = jobs.add_jobs(items, None, dry)
    return rows, added, dupes, dropped

def alerts(args):
    pos = [x for x in args if not x.startswith("--")]
    if not pos: die("usage: sweep.py alerts <file> [--dry-run]")
    dry = "--dry-run" in args
    rows, added, dupes, dropped = import_alerts(pos[0], dry=dry)
    for j in added: print(f"{j['id'] if not dry else '(dry)'}  {j['company']} · {j['title']}  {j['location'] or '-'}  (via {j['source']['via']})")
    for d, i in dupes: print(f"already {i}: {d['company']} · {d['title']}")
    for d in dropped: print(f"dropped: {d['title']} | {d['company'] or '?'}: {d['why']}")
    print(f"-- {len(rows)} in the email, {len(added)} new, {len(dupes)} known, {len(dropped)} dropped")
    if not dry: save(unique_path(SWEEPS, f"{ts_name()}-alerts", "json"), {"ts": stamp(), "file": pos[0], "added": [j["id"] for j in added], "dropped": dropped})
    return 0

def dropped(args):
    files = sorted(SWEEPS.glob("*.json"), key=lambda f: f.stat().st_mtime)
    p = (DATA.parent / args[0]) if args else (files[-1] if files else None)
    if not p or not p.exists(): print("no sweep yet"); return 0
    rep = load(p)
    for r in rep.get("companies", []):
        for d in r["dropped"]: print(f"{r['company']:<26} {d['title'][:60]:<60} {d['why']}")
    for d in rep.get("dropped", []): print(f"{d.get('company') or '?':<26} {d['title'][:60]:<60} {d['why']}")
    return 0

def main(a):
    if a and a[0] in ("-h", "--help", "help"): print(__doc__); return 0
    if a and a[0] == "alerts": return alerts(a[1:])
    if a and a[0] == "dropped": return dropped(a[1:])
    return run(a)

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
