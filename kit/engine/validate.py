#!/usr/bin/env python3
"""Validate their profile and tracking data against the schemas below.
  validate.py            every file; prints OK or the problems; exit 1 on any problem
  validate.py --quiet    prints only problems
Writers call the same checks before saving, so a bad record never reaches disk.
"""
import re, sys
from _common import (PROFILE, DATA, DATE, MONTH, HTTPS, SHA, load, read_jsonl, rel)

FACT_KINDS = {"role", "responsibility", "achievement", "metric", "skill", "tool", "certification", "education",
              "award", "language", "project", "other"}
FACT_STATUS = {"draft", "confirmed", "retired"}
SOURCE = re.compile(r"^(user(:.+)?|engine(:.+)?|doc:.+|web:https://\S+)$")
APP_STATUSES = ["applied", "oa", "screen", "interviewing", "offer", "accepted", "declined", "rejected", "withdrawn", "ghosted"]
APP_CLOSED = {"accepted", "declined", "rejected", "withdrawn", "ghosted"}
JOB_STATUSES = ["new", "shortlisted", "dismissed", "applied", "closed", "repost", "parked"]
CHANNELS = ["careers_site", "referral", "recruiter", "email", "job_board", "other"]
TIERS = {1, 2, 3}
PORTALS = {"greenhouse", "lever", "smartrecruiters", "ashby", "workday", "oraclehcm", "amazon", "eightfold", "static", "successfactors", "taleo", "oracle",
           "darwinbox", "zoho", "icims", "other", "unknown"}
FORMATS = {"pdf", "docx"}
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
STABILITY = ["government-owned", "listed", "multinational subsidiary", "large group", "PE-backed", "startup"]

def _month(v): return v is None or bool(MONTH.match(str(v)))

def fact_errors(f, where=None):
    w, e = where or f"fact {f.get('id')}", []
    if not re.fullmatch(r"f-\d{4}", str(f.get("id", ""))): e.append(f"{w}: id must be f-NNNN")
    if f.get("kind") not in FACT_KINDS: e.append(f"{w}: kind must be one of {sorted(FACT_KINDS)}")
    if not str(f.get("text") or "").strip(): e.append(f"{w}: text is required")
    if f.get("status") not in FACT_STATUS: e.append(f"{w}: status must be draft, confirmed or retired")
    if f.get("status") == "confirmed" and not DATE.match(str(f.get("confirmed") or "")): e.append(f"{w}: confirmed facts need a confirmed date")
    if not SOURCE.match(str(f.get("source") or "")): e.append(f"{w}: source must be user, engine, doc:<file> or web:<https url>")
    per = f.get("period")
    if per is not None:
        if not isinstance(per, dict) or not _month(per.get("start")) or not _month(per.get("end")): e.append(f"{w}: period needs start/end as YYYY-MM or null")
        elif per.get("start") and per.get("end") and per["end"] < per["start"]: e.append(f"{w}: period ends before it starts")
    for i, m in enumerate(f.get("metrics") or []):
        if not (isinstance(m, dict) and str(m.get("name") or "").strip() and str(m.get("value") or "").strip()): e.append(f"{w}: metrics[{i}] needs name and value")
    if not isinstance(f.get("keywords", []), list): e.append(f"{w}: keywords must be a list")
    if not isinstance(f.get("private", False), bool): e.append(f"{w}: private must be true or false")
    return e

def identity_errors(d):
    e, w = [], "identity.json"
    name = d.get("name") or {}
    if d.get("source") != "engine" and not str(name.get("full") or "").strip(): e.append(f"{w}: name.full is required")
    if d.get("email") and not EMAIL.match(d["email"]): e.append(f"{w}: email is not a valid address")
    if d.get("phone") and len(re.sub(r"\D", "", d["phone"])) < 8: e.append(f"{w}: phone has too few digits")
    for k, v in (d.get("links") or {}).items():
        if k == "other":
            for o in v or []:
                if not HTTPS.match(str(o.get("url", ""))): e.append(f"{w}: links.other urls must be https")
        elif v and not HTTPS.match(str(v)): e.append(f"{w}: links.{k} must be an https URL")
    return e

def search_errors(d):
    e, w = [], "search.json"
    r = d.get("rules") or {}
    if r.get("never_lower_level") is not True: e.append(f"{w}: rules.never_lower_level is always true")
    if r.get("company_app_cap") is not None and not (isinstance(r["company_app_cap"], int) and r["company_app_cap"] >= 1): e.append(f"{w}: rules.company_app_cap must be a whole number of 1 or more, or null")
    if r.get("max_steps_up") is not None and not (isinstance(r["max_steps_up"], int) and r["max_steps_up"] >= 0): e.append(f"{w}: rules.max_steps_up must be a whole number or null")
    hco = (d.get("locations") or {}).get("home_cities_only")
    if hco is not None and not (isinstance(hco, list) and all(isinstance(x, str) for x in hco)): e.append(f"{w}: locations.home_cities_only must be a list of cities")
    pct = r.get("lateral_min_raise_pct")
    if not (isinstance(pct, (int, float)) and not isinstance(pct, bool) and 0 <= pct <= 200): e.append(f"{w}: rules.lateral_min_raise_pct must be a number 0-200")
    if r.get("raise_basis", "ctc") not in ("ctc", "fixed"): e.append(f"{w}: rules.raise_basis must be ctc or fixed")
    cur = d.get("current") or {}
    for k in ("ctc_lpa", "fixed_lpa", "variable_pct"):
        v = cur.get(k)
        if v is not None and not (isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0): e.append(f"{w}: current.{k} must be a number or null")
    if cur.get("ladder_rank") is not None and not isinstance(cur["ladder_rank"], int): e.append(f"{w}: current.ladder_rank must be an integer")
    loc = d.get("locations") or {}
    for k in ("eligible_countries", "preferred", "avoid", "abroad"):
        if not isinstance(loc.get(k, []), list): e.append(f"{w}: locations.{k} must be a list")
    seen = set()
    for i, a in enumerate(loc.get("abroad") or []):
        if not (isinstance(a, dict) and re.fullmatch(r"[A-Z]{2}", str(a.get("country", "")))): e.append(f"{w}: locations.abroad[{i}].country must be a two-letter code"); continue
        if a["country"] in seen: e.append(f"{w}: locations.abroad lists {a['country']} twice")
        seen.add(a["country"])
        if not isinstance(a.get("cities", []), list): e.append(f"{w}: locations.abroad[{i}].cities must be a list")
    if not isinstance(loc.get("pay_over_place", False), bool): e.append(f"{w}: locations.pay_over_place must be true or false")
    for k in ("pe_min_employees", "pe_min_years"):
        if k in r and not (isinstance(r[k], int) and r[k] >= 0): e.append(f"{w}: rules.{k} must be a whole number")
    st = r.get("abroad_stability")
    if st is not None and not (isinstance(st, list) and set(st) <= set(STABILITY)): e.append(f"{w}: rules.abroad_stability must list types from {STABILITY}")
    if not isinstance(d.get("target_families", []), list): e.append(f"{w}: target_families must be a list")
    if not isinstance(d.get("target_titles", []), list): e.append(f"{w}: target_titles must be a list")
    g = d.get("gmail") or {}
    if g.get("enabled") and (g.get("mode", "imap") != "imap" or not EMAIL.match(str(g.get("address") or ""))):
        e.append(f"{w}: gmail.enabled needs mode imap and their Gmail address (set by Gmail setup.cmd)")
    if "notice_period_days" in d and d["notice_period_days"] is not None and not (isinstance(d["notice_period_days"], int) and 0 <= d["notice_period_days"] <= 365):
        e.append(f"{w}: notice_period_days must be a whole number of days")
    return e

def employment_errors(rows):
    e = []
    if not isinstance(rows, list): return ["employment.json must be a list"]
    for i, j in enumerate(rows):
        w = f"employment.json[{i}]"
        for k in ("employer", "role", "start"):
            if not str(j.get(k) or "").strip(): e.append(f"{w}: {k} is required")
        if j.get("start") and not MONTH.match(str(j["start"])): e.append(f"{w}: start must be YYYY-MM")
        if j.get("end") is not None and not MONTH.match(str(j["end"])): e.append(f"{w}: end must be YYYY-MM or null (present)")
        if j.get("end") and j.get("start") and j["end"] < j["start"]: e.append(f"{w}: ends before it starts")
        if not SOURCE.match(str(j.get("source") or "")): e.append(f"{w}: source is required")
    return e

def education_errors(rows):
    e = []
    if not isinstance(rows, list): return ["education.json must be a list"]
    for i, r in enumerate(rows):
        w = f"education.json[{i}]"
        for k in ("degree", "institution"):
            if not str(r.get(k) or "").strip(): e.append(f"{w}: {k} is required")
        for k in ("start", "end"):
            if r.get(k) is not None and not MONTH.match(str(r[k])): e.append(f"{w}: {k} must be YYYY-MM or null")
        if not SOURCE.match(str(r.get("source") or "")): e.append(f"{w}: source is required")
    return e

def prefs_errors(d):
    e, w = [], "resume_prefs.json"
    f = d.get("format") or []
    if not f or not set(f) <= FORMATS: e.append(f"{w}: format must be a non-empty subset of pdf, docx")
    if not (isinstance(d.get("page_limit", 2), int) and 1 <= d.get("page_limit", 2) <= 4): e.append(f"{w}: page_limit must be 1-4")
    return e

def _history(w, rows, statuses):
    e, prev = [], ""
    if not isinstance(rows, list) or not rows: return [f"{w}: history must be a non-empty list"]
    for i, h in enumerate(rows):
        if not DATE.match(str(h.get("date", ""))): e.append(f"{w}: history[{i}].date must be YYYY-MM-DD")
        elif h["date"] < prev: e.append(f"{w}: history[{i}] goes back in time")
        else: prev = h["date"]
        if h.get("status") not in statuses: e.append(f"{w}: history[{i}].status {h.get('status')!r} is not valid")
    return e

def jobs_errors(d):
    e, seen = [], set()
    ids_all = {j.get("id") for j in d.get("jobs", [])}
    for j in d.get("jobs", []):
        w = f"jobs.json {j.get('id')}"
        if not re.fullmatch(r"j-\d{4}", str(j.get("id", ""))): e.append(f"{w}: id must be j-NNNN")
        if j.get("id") in seen: e.append(f"{w}: id used twice")
        seen.add(j.get("id"))
        for k in ("company", "title"):
            if not str(j.get(k) or "").strip(): e.append(f"{w}: {k} is required")
        if j.get("url") and not HTTPS.match(str(j["url"])): e.append(f"{w}: url must be https")
        if (j.get("source") or {}).get("tier") not in TIERS: e.append(f"{w}: source.tier must be 1, 2 or 3")
        if j.get("status") not in JOB_STATUSES: e.append(f"{w}: status {j.get('status')!r} is not valid")
        e += _history(w, j.get("history"), JOB_STATUSES)
        if (j.get("history") or [{}])[-1].get("status") != j.get("status"): e.append(f"{w}: status must match the last history entry")
        if j.get("jd") and not (DATA.parent / j["jd"]).is_file(): e.append(f"{w}: JD copy {j['jd']} is missing")
        if j.get("status") == "repost" and j.get("repost_of") not in ids_all: e.append(f"{w}: a repost needs repost_of, an existing job id")
    return e

def apps_errors(d, jobs, resumes):
    e = []
    for a in d.get("apps", []):
        w = f"apps.json {a.get('id')}"
        if not re.fullmatch(r"a-\d{4}", str(a.get("id", ""))): e.append(f"{w}: id must be a-NNNN")
        for k in ("company", "role"):
            if not str(a.get(k) or "").strip(): e.append(f"{w}: {k} is required")
        if not DATE.match(str(a.get("applied", ""))): e.append(f"{w}: applied must be YYYY-MM-DD")
        if a.get("channel") not in CHANNELS: e.append(f"{w}: channel must be one of {CHANNELS}")
        if a.get("referrer") and a.get("channel") != "referral": e.append(f"{w}: a referrer goes with channel referral")
        if a.get("resume") not in resumes and not (a.get("backfill") and a.get("resume") is None): e.append(f"{w}: resume is not in resumes/index.json")
        if a.get("job") and a["job"] not in jobs: e.append(f"{w}: job {a['job']} is not in jobs.json")
        if a.get("status") not in APP_STATUSES: e.append(f"{w}: status {a.get('status')!r} is not valid")
        if (a.get("status") == "interviewing") != bool(a.get("round")): e.append(f"{w}: round goes with interviewing, and interviewing needs one")
        e += _history(w, a.get("history"), APP_STATUSES)
        last = (a.get("history") or [{}])[-1]
        if (last.get("status"), last.get("round")) != (a.get("status"), a.get("round")): e.append(f"{w}: status/round must match the last history entry")
        if any(h.get("source") != "user" for h in a.get("history") or []): e.append(f"{w}: statuses change only on their word (source user)")
    return e

def resumes_errors(d):
    import hashlib
    e, out = [], {}
    for i, r in enumerate(d.get("resumes", [])):
        w = f"resumes/index.json[{i}]"
        h = str(r.get("sha256", ""))
        if not SHA.match(h): e.append(f"{w}: sha256 must be 64 hex characters"); continue
        f = DATA.parent / str(r.get("file", ""))
        if not f.is_file(): e.append(f"{w}: {r.get('file')} is missing")
        elif hashlib.sha256(f.read_bytes()).hexdigest() != h: e.append(f"{w}: {r['file']} doesn't match its hash (a stored resume never changes)")
        out[h] = r
    return e, out

def radar_errors(d):
    e, seen = [], set()
    for c in d.get("companies", []):
        w = f"radar.json {c.get('company')}"
        name = str(c.get("company") or "").strip().lower()
        if not name: e.append(f"{w}: company is required")
        if name in seen: e.append(f"{w}: listed twice")
        seen.add(name)
        if not HTTPS.match(str(c.get("careers_url", ""))): e.append(f"{w}: careers_url must be https")
        p = c.get("portal") or {}
        if p.get("type") not in PORTALS: e.append(f"{w}: portal.type {p.get('type')!r} is not known")
        if p.get("tier") not in (1, 3): e.append(f"{w}: portal.tier must be 1 or 3")
        if not (isinstance(c.get("every_days"), int) and c["every_days"] >= 1): e.append(f"{w}: every_days must be an integer >= 1")
        st = c.get("stability")
        if st is not None:
            if not isinstance(st, dict) or (st.get("type") is not None and st.get("type") not in STABILITY): e.append(f"{w}: stability.type must be one of {STABILITY} or null")
            elif st.get("type") and not HTTPS.match(str(st.get("source") or "")): e.append(f"{w}: stability needs a source (https link)")
        prev = ""
        for k, ch in enumerate(c.get("checks") or []):
            if not DATE.match(str(ch.get("date", ""))) or ch["date"] < prev: e.append(f"{w}: checks[{k}].date must be YYYY-MM-DD, in order")
            else: prev = ch["date"]
    return e

def all_errors():
    e = []
    for f in read_jsonl(PROFILE / "facts.jsonl"): e += fact_errors(f)
    ids = [f.get("id") for f in read_jsonl(PROFILE / "facts.jsonl")]
    if len(ids) != len(set(ids)): e.append("facts.jsonl: an id is used twice")
    for name, fn in (("identity.json", identity_errors), ("search.json", search_errors), ("resume_prefs.json", prefs_errors)):
        d = load(PROFILE / name)
        if d is not None: e += fn(d)
    for name, fn in (("employment.json", employment_errors), ("education.json", education_errors)):
        d = load(PROFILE / name)
        if d is not None: e += fn(d)
    jobs = load(DATA / "jobs.json", {"jobs": []})
    e += jobs_errors(jobs)
    re_, resumes = resumes_errors(load(DATA / "resumes" / "index.json", {"resumes": []}))
    e += re_
    e += apps_errors(load(DATA / "apps.json", {"apps": []}), {j["id"] for j in jobs.get("jobs", [])}, resumes)
    e += radar_errors(load(DATA / "radar.json", {"companies": []}))
    import refer
    e += refer.errors(load(DATA / "contacts.json", {"contacts": []}) or {"contacts": []}, {j["id"] for j in jobs.get("jobs", [])})
    return e

def main(a):
    e = all_errors()
    if e:
        print("PROBLEMS:\n- " + "\n- ".join(e)); return 1
    if "--quiet" not in a: print("OK: profile and data are valid")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
