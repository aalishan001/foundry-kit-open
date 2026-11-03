#!/usr/bin/env python3
"""Free job-search APIs (Adzuna, Jooble, JSearch) for roles posted outside their radar. Optional: each runs only when
its key is in Credential Manager (keys.py). Postings go in as tier 2, under the same prefilter and dedupe as sweeps.
  job_apis.py [--only <api>] [--dry-run]   query every API with a key, within its daily and monthly caps
  job_apis.py queries                      the searches it would run: their target families' titles × their places
  job_apis.py usage                        calls used today and this month, per API
Caps sit under the free tiers (data/api_usage.json counts them): Adzuna 25 a day, Jooble 20 a day, JSearch 6 a day
and 150 a month. Keys never reach a file: they're redacted from caches, fixtures and messages.
"""
import re, sys
from _common import DATA, load, save, today, search_rules, pack, opt, die
from fetch import get, FetchError
import secrets_store as vault

USAGE = DATA / "api_usage.json"
CAPS = {"adzuna": {"day": 25, "month": None}, "jooble": {"day": 20, "month": None}, "jsearch": {"day": 6, "month": 150}}
ADZUNA_COUNTRIES = {"GB", "US", "AT", "AU", "BE", "BR", "CA", "CH", "DE", "ES", "FR", "IN", "IT", "MX", "NL", "NZ", "PL", "SG", "ZA"}
TITLES_PER_FAMILY = 2
TAG = re.compile(r"<[^>]+>")

# ---------------------------------------------------------------- what to search
def places(rules=None):
    """[(country code, place text for the query)] in their order: home first, then their abroad list."""
    from fit import GEO
    s = rules or search_rules()
    L = s.get("locations") or {}
    home = L.get("home_country", "IN")
    names = GEO.get("countries", {})
    out = [(home, names.get(home, [home])[0])]
    for a in L.get("abroad") or []:
        cc = str(a.get("country", "")).upper()
        cities = a.get("cities") or []
        out += [(cc, c) for c in cities] if cities else [(cc, names.get(cc, [cc])[0])]
    return out

def level_word(rank):
    """(word, position) that carries the level in a search, from the pack's level_words: [[min_rank, word], ...] and
    level_word_position (prefix or suffix). ('', ...) below the first band."""
    p = pack()
    word = ""
    for lo, w in sorted(p.get("level_words") or [], key=lambda x: x[0]):
        if rank is not None and rank >= lo: word = w
    return word, p.get("level_word_position", "suffix")

def search_titles(rules=None):
    """Per target family, its first titles that fit their level: a title that names a level below theirs is skipped,
    one at or above it is used as is, and an area phrase ("backend engineer") gets their level word."""
    from fit import level_of
    s = rules or search_rules()
    cur = (s.get("current") or {}).get("ladder_rank")
    word, pos = level_word(cur)
    fams = {f["id"]: f for f in pack().get("roles", {}).get("families", [])}
    out = []
    for fid in s.get("target_families") or []:
        picked = []
        for t in (fams.get(fid) or {}).get("titles", []):
            rank, _ = level_of(t)
            if rank is not None and cur is not None and rank < cur: continue
            q = t if rank is not None or not word else (f"{word} {t}" if pos == "prefix" else f"{t} {word}")
            if q not in out and q not in picked: picked.append(q)
            if len(picked) == TITLES_PER_FAMILY: break
        out += picked
    out += [t for t in s.get("target_titles") or [] if t not in out]
    return out

def queries(rules=None):
    """[(title, country, place)]: for each place in their order, the searches for their families at their level."""
    s = rules or search_rules()
    return [(t, cc, pl) for cc, pl in places(s) for t in search_titles(s)]

# ---------------------------------------------------------------- usage caps
def _usage():
    u = load(USAGE, {}) or {}
    d, m = today().isoformat(), today().isoformat()[:7]
    for api in CAPS:
        r = u.setdefault(api, {})
        if r.get("day") != d: r.update(day=d, day_calls=0)
        if r.get("month") != m: r.update(month=m, month_calls=0)
    return u

def left(u, api):
    c, r = CAPS[api], u[api]
    n = c["day"] - r["day_calls"]
    if c["month"] is not None: n = min(n, c["month"] - r["month_calls"])
    return max(0, n)

def spend(u, api):
    u[api]["day_calls"] += 1; u[api]["month_calls"] += 1

def usage_line(api):
    u, c = _usage(), CAPS[api]
    return f"today {u[api]['day_calls']}/{c['day']}" + (f", this month {u[api]['month_calls']}/{c['month']}" if c["month"] else "")

# ---------------------------------------------------------------- adapters: each -> list of postings
def _posting(**kw):
    p = {"company": "", "title": "", "location": "", "remote": False, "url": None, "posted": None, "jd_text": None, "snippet": None}
    p.update({k: v for k, v in kw.items() if v is not None})
    p["title"] = re.sub(r"\s+", " ", TAG.sub("", p["title"])).strip()
    p["company"] = re.sub(r"\s+", " ", p["company"]).strip()
    return p

def adzuna(title, cc, place):
    if cc not in ADZUNA_COUNTRIES: return None   # Adzuna doesn't cover this country
    app_id, app_key = vault.get("adzuna_app_id"), vault.get("adzuna_app_key")
    from urllib.parse import urlencode
    q = urlencode({"app_id": app_id, "app_key": app_key, "what": title, "where": "" if place.lower() in ("india",) else place,
                   "results_per_page": 50, "max_days_old": 14, "content-type": "application/json"})
    d = get(f"https://api.adzuna.com/v1/api/jobs/{cc.lower()}/search/1?{q}", as_json=True, secrets=(app_id, app_key))
    return [_posting(company=(r.get("company") or {}).get("display_name", ""), title=r.get("title", ""),
                     location=(r.get("location") or {}).get("display_name", ""), url=r.get("redirect_url"),
                     posted=(r.get("created") or "")[:10] or None, snippet=TAG.sub("", r.get("description") or "")[:500] or None)
            for r in d.get("results", [])]

def jooble(title, cc, place):
    key = vault.get("jooble_key")
    d = get(f"https://jooble.org/api/{key}", method="POST", body={"keywords": title, "location": place, "page": "1"}, as_json=True, secrets=(key,))
    return [_posting(company=r.get("company", ""), title=r.get("title", ""), location=r.get("location", ""), url=r.get("link"),
                     posted=(r.get("updated") or "")[:10] or None, snippet=TAG.sub("", r.get("snippet") or "")[:500] or None)
            for r in d.get("jobs", [])]

def jsearch(title, cc, place):
    key = vault.get("jsearch_key")
    from urllib.parse import urlencode
    q = urlencode({"query": f"{title} in {place}", "page": 1, "num_pages": 1, "date_posted": "week", "country": cc.lower()})
    d = get(f"https://jsearch.p.rapidapi.com/search?{q}", as_json=True, secrets=(key,),
            headers={"X-RapidAPI-Key": key, "X-RapidAPI-Host": "jsearch.p.rapidapi.com"})
    out = []
    for r in d.get("data", []):
        loc = ", ".join(x for x in (r.get("job_city"), r.get("job_state"), r.get("job_country")) if x)
        out.append(_posting(company=r.get("employer_name", ""), title=r.get("job_title", ""), location=loc, url=r.get("job_apply_link"),
                            remote=bool(r.get("job_is_remote")), posted=(r.get("job_posted_at_datetime_utc") or "")[:10] or None,
                            jd_text=r.get("job_description")))
    return out

ADAPTERS = {"adzuna": adzuna, "jooble": jooble, "jsearch": jsearch}

def ready(api):
    import keys
    return keys.stored(api)

# ---------------------------------------------------------------- run
def collect(only=None, rules=None):
    """{api: {"calls", "postings", "errors", "skipped"}} for every API with a key, within its caps."""
    u, out = _usage(), {}
    plan = queries(rules)
    for api, fn in ADAPTERS.items():
        if only and api != only: continue
        rep = {"calls": 0, "postings": [], "errors": [], "skipped": None}
        out[api] = rep
        try:
            if not ready(api): rep["skipped"] = "no key (optional: API keys.cmd)"; continue
        except vault.Missing as e: rep["skipped"] = str(e); continue
        start = u[api].get("cursor", 0) % len(plan) if plan else 0
        done = 0
        for title, cc, place in plan[start:] + plan[:start]:   # a capped day picks up tomorrow where it stopped
            if left(u, api) <= 0: rep["skipped"] = f"cap reached ({usage_line(api)})"; break
            done += 1
            try: rows = fn(title, cc, place)
            except FetchError as e: rep["errors"].append(f"{title} / {place}: {e}"); spend(u, api); continue
            if rows is None: continue
            spend(u, api); rep["calls"] += 1
            for p in rows: p["via"] = api; p["query"] = f"{title} / {place}"
            rep["postings"] += rows
        u[api]["cursor"] = (start + done) % len(plan) if plan else 0
        save(USAGE, u)
    return out

def add(report, dry=False, rules=None):
    """Prefilter and dedupe the postings, add the survivors as tier-2 jobs. -> (added, dropped, known)."""
    import fit, jobs, radar
    s = rules or search_rules()
    rad = radar.load_radar()
    items, texts, dropped, seen = [], {}, [], set()
    for api, rep in report.items():
        for p in rep["postings"]:
            if not p["title"] or not p["company"]: continue
            k = jobs.dedupe_key(p["company"], p["title"], p["location"])
            if k in seen: continue
            seen.add(k)
            ok, why = fit.prefilter(p, s, company=radar.find(rad, p["company"]))
            if not ok: dropped.append({"title": p["title"], "company": p["company"], "location": p["location"], "via": api, "why": why}); continue
            if p.get("jd_text") and len(p["jd_text"].strip()) >= 200: texts[len(items)] = p["jd_text"]
            items.append({"company": p["company"], "title": p["title"], "location": p["location"], "remote": p["remote"],
                          "url": p["url"] if (p["url"] or "").startswith("https://") else None, "posted": p["posted"],
                          "snippet": p.get("snippet"), "source": {"tier": 2, "via": api, "ref": p.get("query")}})
    added, dupes = jobs.add_jobs(items, texts, dry)
    return added, dropped, dupes

def run(args):
    only = opt(args, "--only")
    if only and only not in ADAPTERS: die(f"--only takes {', '.join(ADAPTERS)}")
    rep = collect(only)
    added, dropped, dupes = add(rep, "--dry-run" in args)
    for api, r in rep.items():
        print(f"{api:<8} " + (r["skipped"] if r["skipped"] and not r["calls"] else f"{r['calls']} call(s), {len(r['postings'])} posting(s)"
              + (f"; stopped: {r['skipped']}" if r["skipped"] else "")) + "".join(f"\n         error: {e}" for e in r["errors"][:3]))
    for j in added: print(f"  {j.get('id', '(dry)')}  {j['company']} · {j['title']}  {j['location'] or '-'}  (via {j['source']['via']})")
    print(f"-- {len(added)} new, {len(dupes)} known, {len(dropped)} dropped by the rules")
    return 0

def main(a):
    if a and a[0] in ("-h", "--help", "help"): print(__doc__); return 0
    if a and a[0] == "queries":
        for t, cc, pl in queries(): print(f"{cc}  {pl:<24} {t}")
        return 0
    if a and a[0] == "usage":
        for api in CAPS: print(f"{api:<8} {usage_line(api)}")
        return 0
    return run(a)

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
