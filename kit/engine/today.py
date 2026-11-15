#!/usr/bin/env python3
"""One view of what needs them today. Suggestions only: nothing is changed.
  today.py [--json]
Shows: interviews and calls in the next 7 days, radar companies due, new jobs not reviewed, shortlisted jobs not
applied after 7 days, applications with no update for 14+ days, open /start questions.
"""
import datetime as dt, json, sys
from _common import DATA, PROFILE, load, today, days_since
from validate import APP_CLOSED

STALE_APP_DAYS, OLD_SHORTLIST_DAYS, AHEAD_DAYS = 14, 7, 7

def radar_due():
    from radar import due_date
    rows = load(DATA / "radar.json", {"companies": []})["companies"]
    return sorted(((due_date(c), c) for c in rows if not c.get("dropped") and due_date(c) <= today()), key=lambda x: (x[0], x[1]["company"].lower()))

def view():
    jobs = load(DATA / "jobs.json", {"jobs": []})["jobs"]
    apps = load(DATA / "apps.json", {"apps": []})["apps"]
    intake = load(PROFILE / "intake.json", {}) or {}
    t = today()
    soon = sorted((a for a in apps if a.get("next") and t <= dt.date.fromisoformat(a["next"]) <= t + dt.timedelta(days=AHEAD_DAYS)), key=lambda a: a["next"])
    stale = sorted(((days_since(a["history"][-1]["date"]), a) for a in apps
                    if a["status"] not in APP_CLOSED and days_since(a["history"][-1]["date"]) >= STALE_APP_DAYS), key=lambda x: -x[0])
    shortlisted = [j for j in jobs if j["status"] == "shortlisted" and days_since(j["history"][-1]["date"]) > OLD_SHORTLIST_DAYS]
    new = [j for j in jobs if j["status"] == "new"]
    openq = [q for q in intake.get("questions", []) if not q.get("a")]
    return {"soon": soon, "radar_due": radar_due(), "new": new, "shortlisted_old": shortlisted, "stale": stale, "open_questions": openq,
            "intake_open": [s for s, v in (intake.get("stages") or {}).items() if v != "done" and s != "gmail"]}

def main(a):
    v = view()
    if "--json" in a:
        print(json.dumps({k: (len(x) if isinstance(x, list) else x) for k, x in v.items()}, indent=1)); return 0
    t = today()
    print(f"Today {t.isoformat()}")
    print(f"\nComing up in {AHEAD_DAYS} days ({len(v['soon'])}):" + ("" if v["soon"] else " none"))
    for a_ in v["soon"]:
        print(f"  {a_['next']}  {a_['id']}  {a_['company']} · {a_['role']}  {a_['status']}" + (f" round {a_['round']}" if a_.get("round") else ""))
    print(f"\nRadar companies due ({len(v['radar_due'])}):" + ("" if v["radar_due"] else " none"))
    for d, c in v["radar_due"][:15]:
        print(f"  {c['company']:<28} due {d.isoformat()}  tier {c['portal']['tier']}")
    if len(v["radar_due"]) > 15: print(f"  ... and {len(v['radar_due']) - 15} more (/radar)")
    print(f"\nNew jobs not reviewed ({len(v['new'])}):" + ("" if v["new"] else " none"))
    for j in v["new"][:10]: print(f"  {j['id']}  {j['company']} · {j['title']}  {j['location'] or '-'}")
    print(f"\nShortlisted, not applied after {OLD_SHORTLIST_DAYS} days ({len(v['shortlisted_old'])}):" + ("" if v["shortlisted_old"] else " none"))
    for j in v["shortlisted_old"]: print(f"  {j['id']}  {j['company']} · {j['title']}  since {j['history'][-1]['date']}")
    print(f"\nApplications with no update for {STALE_APP_DAYS}+ days ({len(v['stale'])}):" + ("" if v["stale"] else " none"))
    for n, a_ in v["stale"]:
        hint = "a follow-up note" if n < 2 * STALE_APP_DAYS else "a last follow-up, or mark it ghosted"
        print(f"  {a_['id']}  {a_['status']:<12} {n} d  {a_['company']} · {a_['role']}  (suggest: {hint})")
    if v["intake_open"] or v["open_questions"]:
        print(f"\nProfile: {len(v['open_questions'])} open question(s)" + (f"; /start stages left: {', '.join(v['intake_open'])}" if v["intake_open"] else ""))
    import board_watch
    gone = board_watch.current()
    if gone:
        print(f"\nNo longer on their boards ({len(gone)}): confirm with /update if closed")
        for f in gone: print("  " + board_watch.line(f))
    print("\nNothing was changed.")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
