#!/usr/bin/env python3
"""Validate a domain pack.
  pack_check.py [<pack-id>] [--quiet]     default: the profile's pack (profile/search.json), else the kit default
Exit 1 with a list of problems.
"""
import re, sys
from _common import HTTPS, load, read_jsonl, pack_dir, pack_id
from validate import STABILITY

PORTALS = {"greenhouse", "lever", "smartrecruiters", "ashby", "workday", "static", "successfactors", "taleo", "oracle",
           "darwinbox", "zoho", "icims", "other"}
SEGMENTS = {"ipp", "oem", "om-contractor", "epc", "ci", "software", "consultancy"}   # when pack.json lists none
TOPICS = {"technical", "system-design", "coding", "safety", "commercial", "people", "behavioral"}

def check(pid):
    d, e = pack_dir(pid), []
    def need(name):
        p = d / name
        if not p.exists(): e.append(f"{name} is missing"); return None
        return read_jsonl(p) if name.endswith(".jsonl") else load(p)
    pk = need("pack.json") or {}
    if pk.get("id") != pid: e.append(f"pack.json id {pk.get('id')!r} must equal the folder name {pid!r}")
    for k in ("name", "version", "description"):
        if not pk.get(k): e.append(f"pack.json: {k} is required")
    ranks = [lv.get("rank") for lv in pk.get("levels", [])]
    if not ranks or ranks != sorted(ranks) or len(set(ranks)) != len(ranks): e.append("pack.json: levels need unique ranks in ascending order")
    seen_titles = {}
    for lv in pk.get("levels", []):
        if not lv.get("titles"): e.append(f"pack.json: level {lv.get('rank')} has no titles")
        for t in lv.get("titles", []):
            if t.lower() in seen_titles: e.append(f"pack.json: title {t!r} is on two levels")
            seen_titles[t.lower()] = lv["rank"]
        yh = lv.get("years_hint")
        if yh is not None and not (isinstance(yh, list) and len(yh) == 2 and yh[0] <= yh[1]): e.append(f"pack.json: level {lv.get('rank')} years_hint must be [min, max]")
    for r in pk.get("ic_ranks", []):
        if r not in ranks: e.append(f"pack.json: ic_ranks has {r}, which isn't a level")
    roles = (need("roles.json") or {}).get("families", [])
    ids = [f.get("id") for f in roles]
    if len(ids) != len(set(ids)): e.append("roles.json: family ids must be unique")
    if not any(f.get("default") for f in roles) and not pk.get("open_families"): e.append("roles.json: at least one family must be default")
    for f in roles:
        w = f"roles.json {f.get('id')}"
        for k in ("name", "titles", "must_keywords"):
            if not f.get(k): e.append(f"{w}: {k} is required")
        for a in f.get("adjacent", []):
            if a not in ids: e.append(f"{w}: adjacent {a!r} is not a family")
        if not isinstance(f.get("default"), bool): e.append(f"{w}: default must be true or false")
    terms = (need("keywords.json") or {}).get("terms", [])
    tids = [t.get("id") for t in terms]
    if len(tids) != len(set(tids)): e.append("keywords.json: term ids must be unique")
    for t in terms:
        w = f"keywords.json {t.get('id')}"
        if not t.get("canonical") or not t.get("variants"): e.append(f"{w}: canonical and variants are required")
        bad = set(t.get("exact_case", [])) - set(t.get("variants", []))
        if bad: e.append(f"{w}: exact_case {sorted(bad)} must also be variants")
        for fam in t.get("families", []):
            if fam not in ids: e.append(f"{w}: family {fam!r} is not in roles.json")
    rub = need("rubric.json") or {}
    if sum(c.get("weight", 0) for c in rub.get("criteria", [])) != 100: e.append("rubric.json: weights must sum to 100")
    if not (d / "rubric.md").exists(): e.append("rubric.md is missing")
    radar = (need("radar.json") or {}).get("companies", [])
    names = set()
    for c in radar:
        w = f"radar.json {c.get('company')}"
        n = str(c.get("company") or "").lower()
        if not n: e.append(f"{w}: company is required")
        if n in names: e.append(f"{w}: listed twice")
        names.add(n)
        segs = set(pk.get("segments") or SEGMENTS)
        if c.get("segment") not in segs: e.append(f"{w}: segment must be one of {sorted(segs)}")
        if not HTTPS.match(str(c.get("careers_url", ""))): e.append(f"{w}: careers_url must be https")
        p = c.get("portal") or {}
        if p.get("type") not in PORTALS: e.append(f"{w}: portal.type {p.get('type')!r} is not known")
        tier = 1 if p.get("type") in ("greenhouse", "lever", "smartrecruiters", "ashby", "workday") else p.get("tier")
        if p.get("tier") != tier or tier not in (1, 3): e.append(f"{w}: portal.tier is wrong for {p.get('type')}")
        if p.get("type") in ("greenhouse", "lever", "smartrecruiters", "ashby") and not p.get("token"): e.append(f"{w}: {p['type']} needs a token")
        if p.get("type") == "workday" and not all(p.get(k) for k in ("host", "tenant", "site")): e.append(f"{w}: workday needs host, tenant and site")
        for fam in c.get("families", []):
            if fam not in ids: e.append(f"{w}: family {fam!r} is not in roles.json")
        st = c.get("stability")
        if st is not None:
            if not isinstance(st, dict) or st.get("type") not in STABILITY + [None]: e.append(f"{w}: stability.type must be one of {STABILITY} or null")
            elif st.get("type") and not (HTTPS.match(str(st.get("source") or "")) and re.match(r"^\d{4}-\d{2}-\d{2}$", str(st.get("checked", "")))):
                e.append(f"{w}: stability needs an https source and a checked date")
        al = c.get("alert")
        if al is not None and not (isinstance(al, dict) and (al.get("url") is None or HTTPS.match(str(al["url"])))): e.append(f"{w}: alert.url must be https or null")
        v = c.get("verified") or {}
        if v.get("result") not in ("ok", "tier3", "failed") or not re.match(r"^\d{4}-\d{2}-\d{2}$", str(v.get("date", ""))): e.append(f"{w}: verified needs a date and result ok|tier3|failed")
    probes = need("probes.json") or {}
    for fam in (probes.get("families") or {}):
        if fam not in ids: e.append(f"probes.json: family {fam!r} is not in roles.json")
    gids = set()
    for g in need("grill.jsonl") or []:
        w = f"grill.jsonl {g.get('id')}"
        if g.get("id") in gids: e.append(f"{w}: id used twice")
        gids.add(g.get("id"))
        if g.get("family") not in ids and g.get("family") != "general": e.append(f"{w}: family {g.get('family')!r} is not in roles.json")
        if g.get("topic") not in TOPICS: e.append(f"{w}: topic must be one of {sorted(TOPICS)}")
        for k in ("question", "what_good_looks_like"):
            if not g.get(k): e.append(f"{w}: {k} is required")
    return e, {"families": len(roles), "terms": len(terms), "companies": len(radar), "questions": len(gids)}

def main(a):
    pos = [x for x in a if not x.startswith("--")]
    pid = pos[0] if pos else pack_id()
    e, n = check(pid)
    if e: print(f"PACK {pid}: {len(e)} problem(s)\n- " + "\n- ".join(e)); return 1
    if "--quiet" not in a: print(f"PACK {pid}: OK ({n['families']} families, {n['terms']} keyword terms, {n['companies']} companies, {n['questions']} questions)")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
