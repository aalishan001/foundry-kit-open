#!/usr/bin/env python3
"""Exact fit rules: level ladder, the lateral pay threshold, location, role family. Judgment (match, likeliness)
stays with Claude; these are the parts that must never be guessed.
  fit.py level "<title>"                    the pack ladder rank of a title
  fit.py rules <payload>                    {title, years_min?, location?, remote?, pay_min_lpa?, pay_max_lpa?,
                                            ic_ladder? (true at software firms, consultancies, India offices of global companies),
                                            company?, stability?, stability_source?, employees?, founded?}
                                            -> level, pay, location and company verdicts against their search rules (JSON)
  fit.py family "<title>" ["<jd text>"]     which role families a posting belongs to
  fit.py weights                            the pack rubric's weights, adjusted for their profile (pay over place)
Rules: a role below their current level is excluded, always; so is one more than rules.max_steps_up levels above it
(no cap unless they set one). At home, locations.home_cities_only (off unless they set it) keeps only those cities and
remote roles. The years a posting asks for are read and compared with theirs, as a fit input that never excludes. A lateral role must clear their raise threshold
(lateral_min_raise_pct, 20 by default) on the basis they chose (CTC or fixed). Preferred places only add a boost;
they never filter. Countries outside their eligible list (plus their abroad list) are excluded. A role abroad needs an
established company (rules.abroad_stability: every stability type but startup, by default). A PE-backed company
counts as established only when it is also large and long-running (rules.pe_min_employees, 1,000, and
rules.pe_min_years, 10); otherwise it is "unclear", with the reason. In their home country stability is shown, never
filtered.
"""
import json, re, sys
from _common import load, KIT, die, payload, search_rules, pack, norm, today
import kw

GEO = load(KIT / "engine" / "geo.json", {})
STABILITY = ["government-owned", "listed", "multinational subsidiary", "large group", "PE-backed", "startup"]
ESTABLISHED = [t for t in STABILITY if t != "startup"]
YEARS = re.compile(r"(?i)\b(\d{1,2})\s*(?:\+|plus|-|–|to)?\s*(?:\d{1,2})?\s*\+?\s*(?:yrs?|years?)\b")
JD_YEARS = re.compile(r"(?i)(?<![\d.])(\d{1,2})(?:\.\d)?\s*\+?\s*(?:(?:-|–|to)\s*\d{1,2}\s*\+?\s*)?(?:yrs?|years?)(?:'s?)?\s+"
                      r"(?:of\s+)?(?:[\w/&,.()-]+\s+){0,6}?(?:experience|exp\b)")
YEARS_TOLERANCE = 2

def title_years(title):
    """The smallest years figure a title states ("3 - 5 years", "8+ yrs", "(3-5)"), or None."""
    hits = [int(m.group(1)) for m in YEARS.finditer(title or "")]
    hits += [int(m.group(1)) for m in re.finditer(r"\((\d{1,2})\s*-\s*\d{1,2}\)", title or "")]
    return min(hits) if hits else None

def jd_years(text, pick=min):
    """The years of experience a JD asks for ("4+ years of backend experience"), or None. Free text takes the smallest,
    so an "or" (Bachelor's + 5 or Master's + 3) never undersells what they'd qualify for."""
    ys = [int(m.group(1)) for m in JD_YEARS.finditer(text or "") if 0 < int(m.group(1)) <= 20]
    return pick(ys) if ys else None

def my_years():
    """Years since their earliest job start (profile/employment.json), to one decimal, or None."""
    import datetime as dt
    from _common import PROFILE, today
    starts = [e.get("start") for e in load(PROFILE / "employment.json", []) or [] if re.fullmatch(r"\d{4}-\d{2}", str(e.get("start") or ""))]
    if not starts: return None
    return round((today() - dt.date.fromisoformat(min(starts) + "-01")).days / 365.25, 1)

def years_rule(asked, mine=None):
    """How their years compare with what the posting asks: a fit input with its reason, never an exclusion."""
    mine = my_years() if mine is None else mine
    tol = pack().get("years_tolerance", YEARS_TOLERANCE)
    out = {"asked": asked, "theirs": mine, "tolerance": tol}
    if asked is None: out.update(verdict="unstated", why="the posting doesn't state years")
    elif mine is None: out.update(verdict="unknown", why=f"asks {asked}+ years; their start dates aren't recorded yet")
    elif mine >= asked: out.update(verdict="meets", why=f"asks {asked}+ years; they have {mine:g}")
    elif mine >= asked - tol: out.update(verdict="close", why=f"asks {asked}+ years; they have {mine:g} (within {tol})")
    else: out.update(verdict="short", why=f"asks {asked}+ years; they have {mine:g}, more than {tol} short: say how they bridge it")
    return out

# ---------------------------------------------------------------- level
def _expand(title):
    t = " " + norm(title) + " "
    for short, full in (pack().get("abbreviations") or {}).items():
        t = re.sub(rf"(?<= ){re.escape(short.lower())}(?= )", full.lower(), t)
    return re.sub(r"\s+", " ", t).strip()

def level_of(title):
    """(rank, matched ladder title) or (None, None). The longest ladder title found in the title wins, so
    'assistant general manager' beats 'manager'."""
    t = " " + _expand(YEARS.sub(" ", title or "")) + " "   # "(3 - 5 years)" is not a level number
    if any(f" {norm(u)} " in t for u in pack().get("unclear_titles") or []): return (None, None)   # means different levels at different companies
    best = None
    for lv in pack().get("levels", []):
        for name in lv["titles"]:
            n = norm(name)
            if f" {n} " in t and (best is None or len(n) > len(best[1])): best = (lv["rank"], n)
    return best if best else (None, None)

def ranks_for_years(years):
    if years is None: return []
    return [lv["rank"] for lv in pack().get("levels", []) if lv.get("years_hint") and lv["years_hint"][0] <= years <= lv["years_hint"][1]]

def ic_unclear(company_entry):
    """Software companies, consultancies and India offices of global companies use their own IC ladders."""
    c = company_entry or {}
    return bool(c.get("india_office")) or c.get("segment") in (pack().get("ic_unclear_segments") or [])

def level_rule(title, years_min=None, current=None, ic=False):
    cur = current if current is not None else (search_rules().get("current") or {}).get("ladder_rank")
    rank, matched = level_of(title)
    out = {"rank": rank, "matched": matched, "current": cur}
    if cur is None:
        out.update(verdict="unclear", why="their current level isn't set (profile_cli.py current)"); return out
    if rank is None:
        yr = ranks_for_years(years_min)
        out["years_ranks"] = yr
        if yr and max(yr) < cur:
            out.update(verdict="unclear", why=f"title not on the ladder; {years_min}+ years suggests a lower level ({min(yr)}-{max(yr)}): check before applying")
        else:
            out.update(verdict="unclear", why="title not on the ladder" + (f"; {years_min}+ years suggests level {min(yr)}-{max(yr)}" if yr else ""))
        return out
    if rank < cur and ic and rank in (pack().get("ic_ranks") or []):
        out.update(verdict="unclear", why=f"{matched} looks lower, but this company's IC titles don't map onto the ladder: check years and pay")
    elif rank < cur: out.update(verdict="lower", why=f"{matched} is below their level: excluded (never a lower role)")
    elif (up := (search_rules().get("rules") or {}).get("max_steps_up")) is not None and rank > cur + up and not (ic and rank in (pack().get("ic_ranks") or [])):
        out.update(verdict="too senior", why=f"{matched} is {rank - cur} levels above theirs (their limit is {up}): excluded")
    elif rank == cur: out.update(verdict="lateral", why=f"{matched} is their current level: needs the pay rise threshold")
    else: out.update(verdict="step up", why=f"{matched} is above their current level")
    return out

# ---------------------------------------------------------------- pay
def pay_rule(level_verdict, pay_min=None, pay_max=None, rules=None):
    s = rules or search_rules()
    r, cur = s.get("rules") or {}, s.get("current") or {}
    pct = r.get("lateral_min_raise_pct", 20)
    basis = r.get("raise_basis", "ctc")
    now_pay = cur.get("fixed_lpa" if basis == "fixed" else "ctc_lpa")
    out = {"threshold_pct": pct, "basis": basis, "current_lpa": now_pay, "stated": [pay_min, pay_max]}
    if level_verdict != "lateral":
        out.update(verdict="n/a", why="the pay threshold applies only to lateral roles"); return out
    if now_pay is None:
        out.update(verdict="unknown", why=f"their current {basis.upper()} isn't recorded, so the threshold can't be applied"); return out
    ask = round(now_pay * (1 + pct / 100), 2)
    out["ask_at_least_lpa"] = ask
    lo, hi = pay_min, pay_max if pay_max is not None else pay_min
    if lo is None and hi is None:
        out.update(verdict="ask", why=f"pay not stated: ask for at least ₹{ask:g} LPA ({basis.upper()}, {pct:g}% over ₹{now_pay:g} LPA)")
    elif lo is not None and lo >= ask:
        out.update(verdict="clears", raise_pct=round((lo / now_pay - 1) * 100, 1), why=f"even the bottom of the range (₹{lo:g} LPA) clears ₹{ask:g} LPA")
    elif hi >= ask:
        out.update(verdict="possible", raise_pct=round((hi / now_pay - 1) * 100, 1), why=f"only the top of the range clears ₹{ask:g} LPA: negotiate for at least that")
    else:
        out.update(verdict="below", raise_pct=round((hi / now_pay - 1) * 100, 1), why=f"₹{hi:g} LPA is under their ₹{ask:g} LPA threshold: excluded")
    return out

# ---------------------------------------------------------------- location
def _has(text, word): return re.search(rf"(?<![^\W_]){re.escape(word)}(?![^\W_])", text, re.I) is not None

def place(location):
    """{country, state, region} read from a location string, as far as it says."""
    loc = location or ""
    india = GEO.get("india", {})
    for city, state in sorted(india.get("cities", {}).items(), key=lambda kv: -len(kv[0])):
        if _has(loc, city): return {"country": "IN", "state": state, "region": india["states"].get(state), "city": city}
    for state, region in india.get("states", {}).items():
        if _has(loc, state): return {"country": "IN", "state": state, "region": region, "city": None}
    for code, names in GEO.get("countries", {}).items():
        if any(_has(loc, n) for n in names): return {"country": code, "state": None, "region": None, "city": None}
    return {"country": None, "state": None, "region": None, "city": None}

def abroad_list(L):
    """Their ordered abroad preferences: [{country, cities}] (codes upper-cased)."""
    return [{"country": str(a.get("country", "")).upper(), "cities": a.get("cities") or []} for a in L.get("abroad") or [] if a.get("country")]

def eligible(L):
    home = L.get("home_country", "IN")
    return set(L.get("eligible_countries") or ["IN"]) | {home} | {a["country"] for a in abroad_list(L)}

# The same city under its old and new names: "Bangalore" is "Bengaluru" for home_cities_only.
CITY_ALIASES = {"bangalore": "bengaluru", "gurgaon": "gurugram", "bombay": "mumbai", "madras": "chennai", "calcutta": "kolkata",
                "new delhi": "delhi", "poona": "pune", "trivandrum": "thiruvananthapuram", "cochin": "kochi", "vizag": "visakhapatnam",
                "mysore": "mysuru", "secunderabad": "hyderabad"}

def city_key(name): n = norm(name or ""); return CITY_ALIASES.get(n, n)

def in_cities(location, cities):
    want = {city_key(c) for c in cities}
    found = place(location)["city"]
    if found and city_key(found) in want: return True
    return any(_has(location or "", c) for c in cities) or any(_has(location or "", a) for a, b in CITY_ALIASES.items() if b in want)

def location_rule(location, remote=False, rules=None):
    s = rules or search_rules()
    L = s.get("locations") or {}
    home, ok_countries = L.get("home_country", "IN"), eligible(L)
    p = place(location)
    out = {"place": p, "remote": bool(remote)}
    texts = " ".join(x for x in (location or "", p.get("state") or "", (p.get("region") or "") + " india") if x)
    pref = [x for x in L.get("preferred") or [] if _has(texts, x)]   # a city, a state, or a region ("north India")
    avoid = [x for x in L.get("avoid") or [] if _has(texts, x)]
    only = L.get("home_cities_only") or []   # their explicit choice: at home, only these cities (or remote)
    if only and not remote and not _has(location or "", "remote") and p["country"] == home and not in_cities(location, only):
        out.update(verdict="excluded", score=-9, why=f"{p.get('city') or p.get('state') or 'that place'} is outside their cities ({', '.join(only)}) and not remote")
        out["preferred"] = []; return out
    if p["country"] is None and not remote:
        out.update(verdict="unclear", score=0, why="location not recognised: read it yourself")
    elif p["country"] is not None and p["country"] not in ok_countries and not (remote and L.get("remote_ok", True)):
        out.update(verdict="excluded", score=-9, why=f"{p['country']} is not a country they can work in")
    elif p["country"] == home or (remote and L.get("remote_ok", True) and p["country"] in (None, home)):
        out.update(verdict="home", score=2 + (1 if pref else 0), why="home country" + (f"; preferred ({', '.join(pref)})" if pref else ""))
    else:
        ab = abroad_list(L)
        i = next((n for n, a in enumerate(ab) if a["country"] == p["country"]), None)
        if i is None:
            out.update(verdict="abroad", score=1, why=f"{p['country']}: eligible abroad (not on their abroad list)")
        else:
            cities = [c for c in ab[i]["cities"] if _has(location or "", c)]
            out.update(verdict="abroad", score=round(1 + (len(ab) - i) / len(ab) + (0.5 if cities else 0), 2), abroad_rank=i + 1,
                       why=f"{p['country']}: their abroad choice {i + 1} of {len(ab)}" + (f"; preferred city ({', '.join(cities)})" if cities else ""))
            if cities: pref = cities
    if avoid: out.update(avoid=avoid, why=out["why"] + f"; they'd rather avoid {', '.join(avoid)}")
    out["preferred"] = pref
    return out

# ---------------------------------------------------------------- company stability
PE_MIN_EMPLOYEES, PE_MIN_YEARS = 1000, 10

def stability_of(entry):
    """(type, source, employees, founded) from a radar entry's stability record."""
    st = (entry or {}).get("stability") or {}
    return st.get("type"), st.get("source"), st.get("employees"), st.get("founded")

def company_rule(stability, loc_verdict, rules=None, source=None, employees=None, founded=None):
    """Abroad needs an established company; at home stability is shown, never filtered. PE-backed counts as
    established only when large and long-running; anything short of that, or unknown, is unclear with the reason."""
    s = rules or search_rules()
    r = s.get("rules") or {}
    allowed = r.get("abroad_stability") or ESTABLISHED
    min_emp, min_years = r.get("pe_min_employees", PE_MIN_EMPLOYEES), r.get("pe_min_years", PE_MIN_YEARS)
    t = stability if stability in STABILITY else None
    out = {"stability": t, "source": source, "employees": employees, "founded": founded}
    size = ", ".join(x for x in (f"about {employees:,} employees" if isinstance(employees, int) else "",
                                 f"founded {founded}" if isinstance(founded, int) else "") if x)
    if loc_verdict != "abroad":
        out.update(verdict="shown", why=(t or "stability unknown") + (f" ({size})" if size else "") + ": shown only; not a filter at home")
    elif t is None:
        out.update(verdict="unclear", why="abroad, and the company's stability is unknown: check it's established (not a startup) before applying")
    elif t not in allowed:
        out.update(verdict="excluded", why=f"{t}: a role abroad needs an established company" + (", never a startup" if t == "startup" else ""))
    elif t == "PE-backed":
        age = today().year - founded if isinstance(founded, int) else None
        short = []
        if not isinstance(employees, int): short.append("headcount unknown")
        elif employees < min_emp: short.append(f"about {employees:,} employees (under {min_emp:,})")
        if age is None: short.append("founding year unknown")
        elif age < min_years: short.append(f"founded {founded}, {age} years ago (under {min_years})")
        if short:
            out.update(verdict="unclear", why=f"PE-backed: established abroad only when large and long-running ({min_emp:,}+ employees, "
                                              f"{min_years}+ years); here " + "; ".join(short) + ". Check before applying")
        else:
            out.update(verdict="ok", why=f"PE-backed, {size}: large and long-running enough for a move abroad")
    else:
        out.update(verdict="ok", why=f"{t}: established enough for a move abroad")
    return out

# ---------------------------------------------------------------- family
def families_of(title, text=""):
    """[(family id, score, default?)] best first. Title words weigh most; JD keywords add evidence."""
    t, body = _expand(title), (text or "")
    out = []
    for f in pack().get("roles", {}).get("families", []):
        s = 0
        if any(f" {norm(x)} " in f" {t} " for x in f.get("titles", [])): s += 6
        s += 3 * sum(1 for x in f.get("synonyms", []) if f" {norm(x)} " in f" {t} ")
        s += 2 * sum(1 for x in f.get("must_keywords", []) if kw.mentions(title, x))
        if body:
            s += sum(1 for x in f.get("must_keywords", []) if kw.mentions(body, x))
            s += 0.5 * sum(1 for x in f.get("nice_keywords", []) if kw.mentions(body, x))
        if s: out.append((f["id"], s, bool(f.get("default"))))
    return sorted(out, key=lambda x: -x[1])

# ---------------------------------------------------------------- prefilter (used by sweep)
def prefilter(job, rules=None, company=None):
    """(keep, reason). Deterministic: drops only what the rules exclude for certain. company: its radar entry."""
    s = rules or search_rules()
    lv = level_rule(job.get("title", ""), current=(s.get("current") or {}).get("ladder_rank"), ic=ic_unclear(company))
    if lv["verdict"] in ("lower", "too senior"): return False, lv["why"]
    loc = location_rule(job.get("location", ""), job.get("remote", False), s)
    if loc["verdict"] == "excluded": return False, loc["why"]
    t, src, emp, fnd = stability_of(company)
    co = company_rule(t, loc["verdict"], s, src, emp, fnd)
    if co["verdict"] == "excluded": return False, co["why"]
    targets = set(s.get("target_families") or [])
    fams = families_of(job.get("title", ""), job.get("jd_text") or "")
    own = [t for t in s.get("target_titles") or [] if f" {norm(t)} " in f" {_expand(job.get('title', ''))} "]
    if own: return True, f"{lv['verdict']}; {loc['verdict']}; their title list ({own[0]})"
    if (targets or s.get("target_titles")) and not any(f in targets and score >= 3 for f, score, _ in fams):
        return False, "no target role family in the title" + (f" (closest: {fams[0][0]})" if fams else "")
    return True, f"{lv['verdict']}; {loc['verdict']}; " + ", ".join(f for f, sc, _ in fams[:2] if f in targets)

def rules(raw):
    d = payload(raw)
    if not d.get("title"): die("rules needs at least a title")
    lv = level_rule(d["title"], d.get("years_min"), ic=bool(d.get("ic_ladder")))
    loc = location_rule(d.get("location", ""), d.get("remote", False))
    stab, src, emp, fnd = d.get("stability"), d.get("stability_source"), d.get("employees"), d.get("founded")
    if d.get("company") and stab is None:
        from radar import load_radar, find
        c = find(load_radar(), d["company"])
        if c and (c.get("stability") or {}).get("type"): stab, src, emp, fnd = stability_of(c)
    if stab is not None and stab not in STABILITY: die(f"stability must be one of {', '.join(STABILITY)} (or leave it out when unknown)")
    asked = d.get("years_min") if d.get("years_min") is not None else (jd_years(d.get("jd_text")) or title_years(d["title"]))
    out = {"level": lv, "pay": pay_rule(lv["verdict"], d.get("pay_min_lpa"), d.get("pay_max_lpa")), "location": loc, "years": years_rule(asked),
           "company": company_rule(stab, loc["verdict"], source=src, employees=emp, founded=fnd),
           "families": [{"id": f, "score": s} for f, s, _ in families_of(d["title"], d.get("jd_text", ""))[:3]]}
    out["excluded"] = (lv["verdict"] in ("lower", "too senior") or out["pay"]["verdict"] == "below" or loc["verdict"] == "excluded"
                       or out["company"]["verdict"] == "excluded")
    print(json.dumps(out, indent=1, ensure_ascii=False))
    for k in ("level", "pay", "location", "company", "years"): print(f"# {k}: {out[k]['verdict']} - {out[k]['why']}", file=sys.stderr)
    return 0

def weights(rules=None):
    """The rubric's criteria with their profile's adjustment: pay over place moves 5 points from location to level."""
    s = rules or search_rules()
    crit = [dict(c) for c in pack().get("rubric", {}).get("criteria", [])]
    adj = None
    if (s.get("locations") or {}).get("pay_over_place"):
        loc, lev = next((c for c in crit if c["id"] == "location"), None), next((c for c in crit if c["id"] == "level"), None)
        if loc and lev:
            move = min(5, loc["weight"]); loc["weight"] -= move; lev["weight"] += move
            adj = f"pay over place: location {loc['weight'] + move} -> {loc['weight']}, level (carries the pay verdict) {lev['weight'] - move} -> {lev['weight']}"
    return crit, adj

def main(a):
    if not a: print(__doc__); return 1
    if a[0] == "level" and len(a) > 1:
        rank, m = level_of(a[1]); print(f"{a[1]!r}: " + (f"rank {rank} ({m})" if rank else "not on the ladder")); return 0
    if a[0] == "rules" and len(a) > 1: return rules(a[1])
    if a[0] == "weights":
        crit, adj = weights()
        for c in crit: print(f"{c['id']:<12} {c['weight']:>3}  {c['what']}")
        print(f"total {sum(c['weight'] for c in crit)}" + (f"; {adj}" if adj else ""))
        return 0
    if a[0] == "family" and len(a) > 1:
        for f, s, d in families_of(a[1], a[2] if len(a) > 2 else ""): print(f"{f:<24} {s:>5.1f}" + ("" if d else "  (adjacent)"))
        return 0
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
