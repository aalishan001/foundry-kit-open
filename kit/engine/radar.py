#!/usr/bin/env python3
"""Their company radar (data/radar.json): which careers portals to check, how, and when.
  radar.py                              companies due for a check, soonest first (and the rest)
  radar.py seed                         first run: copy the pack's list into their radar (safe to re-run: adds nothing twice)
  radar.py pack-new [--add-all]         pack companies not on their radar and never dropped (offered; --add-all adds them)
  radar.py refresh                      merge the pack's latest facts (stability, alert links, portal fixes) into their
                                        radar; their checks, intervals and drops are never touched
  radar.py stability <company> <type> --source <https url> [--basis T] [--employees N] [--founded YYYY]
                                        record a company's stability (PE-backed abroad needs headcount and age)
  radar.py add <company> <careers-url> [--every N] [--segment S]   portal type detected from the URL
  radar.py drop <company> --note <reason>
  radar.py every <company> <N>
  radar.py checked <company> [--found N] [--new N] [--note T] [--date D]
  radar.py detect <url>                 what portal a URL is, and its tier
  radar.py show <company>
Tier 1 is read automatically by /sweep; tier 3 needs them to open the link and paste the JD into /check.
Stability (government-owned, listed, multinational subsidiary, large group, PE-backed, startup) is shown for every
company; abroad, a startup is excluded (fit.py).
"""
import datetime as dt, json, re, sys
from urllib.parse import urlparse
from _common import DATA, HTTPS, load, save, opt, die, today, date_arg, pack, positional
from validate import STABILITY

RADAR = DATA / "radar.json"
DEFAULT_EVERY, DEFAULT_EVERY_PASTE = 7, 14   # paste-in portals cost their time, so they come round less often
TIER3 = {"successfactors", "taleo", "oracle", "darwinbox", "zoho", "icims", "other"}
BLOCKED = ("linkedin.com", "naukri.com")

def load_radar(): return load(RADAR, {"companies": []})

def find(rad, name):
    return next((c for c in rad["companies"] if c["company"].lower() == name.strip().lower()), None)

def blocked(host): return any(host == b or host.endswith("." + b) for b in BLOCKED)

def detect(url):
    """-> portal dict {type, tier, ...} from a careers URL."""
    u = urlparse(url); host = (u.hostname or "").lower(); parts = [p for p in u.path.split("/") if p]
    if blocked(host): die(f"{host} is never scraped: find the company's own careers page instead")
    if host in ("boards.greenhouse.io", "job-boards.greenhouse.io", "boards.eu.greenhouse.io", "job-boards.eu.greenhouse.io") and parts:
        return {"type": "greenhouse", "tier": 1, "token": parts[0]}
    if host == "boards-api.greenhouse.io" and "boards" in parts:
        return {"type": "greenhouse", "tier": 1, "token": parts[parts.index("boards") + 1]}
    if host in ("jobs.lever.co", "jobs.eu.lever.co") and parts:
        return {"type": "lever", "tier": 1, "token": parts[0], **({"region": "eu"} if ".eu." in host else {})}
    if host == "jobs.ashbyhq.com" and parts:
        return {"type": "ashby", "tier": 1, "token": parts[0]}
    if host in ("careers.smartrecruiters.com", "jobs.smartrecruiters.com") and parts:
        return {"type": "smartrecruiters", "tier": 1, "token": parts[0]}
    m = re.match(r"^([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com$", host)
    if m:
        site = [p for p in parts if not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", p)]
        if not site: die("that Workday link has no career-site name in it; open the careers page and copy its full link")
        return {"type": "workday", "tier": 1, "host": host, "tenant": m.group(1), "site": site[0]}
    if "successfactors" in host or host.endswith("sapsf.com") or host.endswith("sapsf.eu"): return {"type": "successfactors", "tier": 3}
    if host.endswith("taleo.net"): return {"type": "taleo", "tier": 3}
    if host.endswith("oraclecloud.com"): return {"type": "oracle", "tier": 3}
    if "darwinbox" in host: return {"type": "darwinbox", "tier": 3}
    if "zohorecruit" in host: return {"type": "zoho", "tier": 3}
    if host.endswith("icims.com"): return {"type": "icims", "tier": 3}
    return {"type": "static", "tier": 1, "probe": True}

def due_date(c):
    last = c["checks"][-1]["date"] if c.get("checks") else None
    return (dt.date.fromisoformat(last) + dt.timedelta(days=c["every_days"])) if last else dt.date.fromisoformat(c["added"])

PACK_FIELDS = ("segment", "india_office", "families", "stability", "alert")   # facts about the company, refreshed from the pack

def entry_from_pack(p):
    portal = {k: v for k, v in p["portal"].items() if k != "how"}
    e = {"company": p["company"], "careers_url": p["careers_url"], "segment": p.get("segment"),
         "india_office": bool(p.get("india_office")), "portal": portal, "how": p["portal"].get("how", ""),
         "families": p.get("families", []), "every_days": DEFAULT_EVERY if portal.get("tier") == 1 else DEFAULT_EVERY_PASTE, "added": today().isoformat(), "checks": [],
         "source": "pack"}
    for k in ("stability", "alert"):
        if p.get(k): e[k] = p[k]
    return e

def refresh():
    """Pack facts into their radar. Never changes their checks, interval, their own additions, or a portal they changed."""
    rad, n, fields = load_radar(), 0, 0
    by_name = {p["company"].lower(): p for p in pack().get("radar", {}).get("companies", [])}
    for c in rad["companies"]:
        p = by_name.get(c["company"].lower())
        if not p or c.get("source") != "pack": continue
        changed = False
        for k in PACK_FIELDS:
            if k in p and c.get(k) != p[k] and not (k == "stability" and (c.get("stability") or {}).get("by") == "user"):
                c[k] = p[k]; changed = True; fields += 1
        pp = {k: v for k, v in p["portal"].items() if k != "how"}
        if c.get("careers_url") != p["careers_url"] and not c.get("portal_changed_by_sweep"):
            c["careers_url"] = p["careers_url"]; c["portal"] = pp; c["how"] = p["portal"].get("how", ""); changed = True; fields += 1
        n += changed
    save(RADAR, rad)
    print(f"radar: refreshed {n} companies from the pack ({fields} fields); checks and intervals unchanged")
    return 0

def stability(args):
    pos = positional(args, ("--source", "--basis", "--employees", "--founded"))
    if len(pos) < 2 or pos[1] not in STABILITY: die(f"usage: radar.py stability <company> <{'|'.join(STABILITY)}> --source <https url> [--basis T]")
    src = opt(args, "--source") or die("stability needs --source: the page that shows who owns the company")
    if not HTTPS.match(src): die("--source must be an https link")
    rad = load_radar(); c = find(rad, pos[0]) or die(f"{pos[0]} is not on the radar")
    num = lambda f: int(opt(args, f)) if (opt(args, f) or "").isdigit() else None
    c["stability"] = {"type": pos[1], "basis": opt(args, "--basis") or "", "source": src, "employees": num("--employees"),
                      "founded": num("--founded"), "checked": today().isoformat(), "by": "user"}
    save(RADAR, rad)
    print(f"radar: {c['company']} is {pos[1]} (source {src})")
    return 0

def stab(c): return (c.get("stability") or {}).get("type") or "unknown"

def seed():
    rad, n = load_radar(), 0
    for p in pack().get("radar", {}).get("companies", []):
        if not find(rad, p["company"]) and p["company"].lower() not in {d.lower() for d in rad.get("dropped_names", [])}:
            rad["companies"].append(entry_from_pack(p)); n += 1
    rad.setdefault("seeded", today().isoformat())
    save(RADAR, rad)
    t1 = sum(c["portal"]["tier"] == 1 for c in rad["companies"])
    print(f"radar: {n} companies added from the pack; {len(rad['companies'])} in total ({t1} read automatically, {len(rad['companies']) - t1} paste-in)")
    return 0

def pack_new(args=()):
    rad = load_radar()
    dropped = {d.lower() for d in rad.get("dropped_names", [])}
    rows = [p for p in pack().get("radar", {}).get("companies", []) if not find(rad, p["company"]) and p["company"].lower() not in dropped]
    if "--add-all" in args and rows:
        rad["companies"] += [entry_from_pack(p) for p in rows]; save(RADAR, rad)
        print(f"radar: added {len(rows)} companies from the pack: " + ", ".join(p["company"] for p in rows)); return 0
    print("\n".join(f"{p['company']:<30} {p.get('segment', ''):<14} tier {p['portal']['tier']}  {stab(p):<24} {p['careers_url']}" for p in rows) or "nothing new in the pack")
    return 0

def add(args):
    pos = positional(args, ("--every", "--segment"))
    if len(pos) < 2: die("usage: radar.py add <company> <careers-url> [--every N] [--segment S]")
    company, url = pos[0].strip(), pos[1]
    if not HTTPS.match(url): die("the careers URL must start with https://")
    every = opt(args, "--every")
    if every is not None and (not every.isdigit() or int(every) < 1): die("--every must be a whole number of days")
    rad = load_radar()
    if find(rad, company): die(f"{company} is already on the radar")
    portal = detect(url)
    every = every or str(DEFAULT_EVERY if portal["tier"] == 1 else DEFAULT_EVERY_PASTE)
    c = {"company": company, "careers_url": url, "segment": opt(args, "--segment"), "india_office": False, "portal": portal,
         "how": "", "families": [], "every_days": int(every), "added": today().isoformat(), "checks": [], "source": "user"}
    rad["companies"].append(c); rad["dropped_names"] = [d for d in rad.get("dropped_names", []) if d.lower() != company.lower()]
    save(RADAR, rad)
    print(f"radar: {company} every {every} days, {portal['type']} (tier {portal['tier']})"
          + ("; a static page: /sweep will try to read it and switch it to paste-in if it can't" if portal.get("probe") else ""))
    return 0

def drop(args):
    pos = positional(args, ("--note",))
    if not pos: die("usage: radar.py drop <company> --note <reason>")
    note = opt(args, "--note") or die("drop needs --note with the reason")
    rad = load_radar(); c = find(rad, pos[0]) or die(f"{pos[0]} is not on the radar")
    rad["companies"].remove(c)
    rad.setdefault("dropped_names", []).append(c["company"])
    rad.setdefault("dropped", []).append({"company": c["company"], "date": today().isoformat(), "note": note})
    save(RADAR, rad); print(f"radar: dropped {c['company']} ({note})")
    return 0

def every(args):
    if len(args) < 2 or not args[1].isdigit() or int(args[1]) < 1: die("usage: radar.py every <company> <N days>")
    rad = load_radar(); c = find(rad, args[0]) or die(f"{args[0]} is not on the radar")
    c["every_days"] = int(args[1]); save(RADAR, rad)
    print(f"radar: {c['company']} every {args[1]} days; next due {due_date(c).isoformat()}")
    return 0

def record_check(rad, c, found=None, new=None, note="", when=None, portal_update=None):
    when = when or today().isoformat()
    if c.get("checks") and when < c["checks"][-1]["date"]: die(f"{when} is before the last check ({c['checks'][-1]['date']})")
    c.setdefault("checks", []).append({"date": when, "found": found, "new": new, "note": note})
    if portal_update:
        c["portal"].update(portal_update)
        if "tier" in portal_update: c["portal_changed_by_sweep"] = True

def checked(args):
    pos = positional(args, ("--found", "--new", "--note", "--date"))
    if not pos: die("usage: radar.py checked <company> [--found N] [--new N] [--note T]")
    rad = load_radar(); c = find(rad, pos[0]) or die(f"{pos[0]} is not on the radar (radar.py add first)")
    num = lambda f: int(opt(args, f)) if opt(args, f) is not None else None
    record_check(rad, c, num("--found"), num("--new"), (opt(args, "--note") or "").strip(), date_arg(args))
    save(RADAR, rad)
    print(f"radar: {c['company']} checked; next due {due_date(c).isoformat()}")
    return 0

def show_due():
    rad = load_radar()
    if not rad["companies"]: print("The radar is empty: radar.py seed (the pack's companies) or radar.py add <company> <url>."); return 0
    rows = sorted(((due_date(c), c) for c in rad["companies"]), key=lambda x: (x[0], x[1]["company"].lower()))
    due = [(d, c) for d, c in rows if d <= today()]; later = [(d, c) for d, c in rows if d > today()]
    print(f"Due ({len(due)}):" + ("" if due else " none"))
    for d, c in due:
        last = c["checks"][-1]["date"] if c.get("checks") else "never"
        how = "automatic" if c["portal"]["tier"] == 1 else "paste-in: open the link"
        print(f"  {c['company']:<30} last {last:<10} {stab(c):<24} {c['portal']['type']:<15} {how}  {c['careers_url'] if c['portal']['tier'] == 3 else ''}".rstrip())
    if later: print("Later:\n" + "\n".join(f"  {c['company']:<30} due {d.isoformat()} (in {(d - today()).days} d)" for d, c in later))
    return 0

def main(a):
    if not a: return show_due()
    cmd, rest = a[0], a[1:]
    if cmd == "seed": return seed()
    if cmd == "pack-new": return pack_new(rest)
    if cmd == "refresh": return refresh()
    if cmd == "stability": return stability(rest)
    if cmd == "add": return add(rest)
    if cmd == "drop": return drop(rest)
    if cmd == "every": return every(rest)
    if cmd == "checked": return checked(rest)
    if cmd == "detect" and rest: print(json.dumps(detect(rest[0]))); return 0
    if cmd == "show" and rest:
        c = find(load_radar(), rest[0]) or die(f"{rest[0]} is not on the radar"); print(json.dumps(c, indent=1, ensure_ascii=False)); return 0
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
