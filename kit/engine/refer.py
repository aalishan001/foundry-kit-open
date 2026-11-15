#!/usr/bin/env python3
"""Referrals: who the user knows at each company, where each ask stands, and the message to send. The kit never
sends anything and never opens LinkedIn: it writes the message, and the user sends it themselves.
  refer.py add <payload>                 {name, company, how_known?, link?, notes?} -> c-NNNN at stage to_ask
  refer.py list [--company C] [--all]    contacts and where each stands (declined ones only with --all)
  refer.py stage <c-id> <stage> [--job <j-id>] [--note T] [--date D]
        a stage the user reported: to_ask, asked, replied_yes, referred, declined. "asked" needs --job: that
        contact is then locked to the role (one contact per open role)
  refer.py nudged <c-id> [--date D]      they sent the one nudge
  refer.py ask <c-id> --job <j-id> [--kind ask|connect] [--pitch <payload>]
        the message, from templates/refer_<kind>.md, into data/refer/; --pitch {text, facts} is a line about the user,
        checked like a resume line. An ask stays under 85 words; a connection note under 220 characters
  refer.py hold <j-id> --note T | unhold <j-id>     keep a role out of outreach (a company's own referral limit)
  refer.py park <company> | unpark <company>        a company with no live role
  refer.py due                           today: asks left under the daily cap, nudges due, locks released
Settings in profile/search.json → referrals: daily_cap (20), nudge_days (5). Stages change only on the user's word.
Contacts are other people's details: they stay in data/contacts.json and never leave the folder except in the
message the user sends.
"""
import json, re, sys
from _common import DATA, PROFILE, HOME, load, save, payload, opt, die, today, date_arg, next_id, days_since, read_jsonl, kit_path, rel, slug
from jobs import load_jobs, find

CONTACTS, OUT = DATA / "contacts.json", DATA / "refer"
STAGES = ["to_ask", "asked", "replied_yes", "referred", "declined"]
ASK_WORDS, CONNECT_CHARS = 85, 220

def load_c(): return load(CONTACTS, {"contacts": [], "holds": {}, "parked": []}) or {"contacts": [], "holds": {}, "parked": []}

def settings():
    from _common import search_rules
    r = search_rules().get("referrals") or {}
    return int(r.get("daily_cap", 20)), int(r.get("nudge_days", 5))

def contact(d, cid): return next((c for c in d["contacts"] if c["id"] == cid), None) or die(f"no contact {cid}")

def stage_of(c): return c["history"][-1]["stage"]

def released(c, nudge_days):
    """A lock ends when they decline, or stay silent past the nudge (nudge_days after it)."""
    if stage_of(c) == "declined": return True
    if stage_of(c) == "asked" and c.get("nudged"): return days_since(c["nudged"]) >= nudge_days
    return False

def asks_today(d):
    t = today().isoformat()
    return sum(1 for c in d["contacts"] for h in c["history"] if h["stage"] == "asked" and h["date"] == t)

def errors(d, jobs):
    e, ids = [], set()
    for c in d.get("contacts", []):
        w = f"contacts.json {c.get('id')}"
        if not re.fullmatch(r"c-\d{4}", str(c.get("id", ""))) or c["id"] in ids: e.append(f"{w}: id must be a unique c-NNNN")
        ids.add(c.get("id"))
        for k in ("name", "company"):
            if not str(c.get(k) or "").strip(): e.append(f"{w}: {k} is required")
        if c.get("link") and not str(c["link"]).startswith("https://"): e.append(f"{w}: link must be https")
        prev = ""
        for h in c.get("history") or []:
            if h.get("stage") not in STAGES: e.append(f"{w}: stage {h.get('stage')!r} is not valid")
            if str(h.get("date", "")) < prev: e.append(f"{w}: history goes back in time")
            prev = str(h.get("date", ""))
            if h.get("source") != "user": e.append(f"{w}: stages change only on the user's word")
        if c.get("job") and c["job"] not in jobs: e.append(f"{w}: job {c['job']} is not in jobs.json")
    return e

def add(raw):
    p = payload(raw); d = load_c()
    for k in ("name", "company"):
        if not str(p.get(k) or "").strip(): die(f"{k} is required")
    if p.get("link") and not str(p["link"]).startswith("https://"): die("link must be an https address (it's never opened by the kit)")
    if any(c["name"].lower() == p["name"].strip().lower() and c["company"].lower() == p["company"].strip().lower() for c in d["contacts"]):
        die(f"{p['name']} at {p['company']} is already a contact")
    c = {"id": next_id(d["contacts"], "c"), "name": p["name"].strip(), "company": p["company"].strip(), "how_known": p.get("how_known") or "",
         "link": p.get("link") or None, "notes": p.get("notes") or "", "job": None, "nudged": None,
         "history": [{"date": today().isoformat(), "stage": "to_ask", "note": "added", "source": "user"}]}
    d["contacts"].append(c); save(CONTACTS, d)
    print(f"{c['id']}  {c['name']} at {c['company']} (to ask)"); return 0

def set_stage(args):
    if len(args) < 2 or args[1] not in STAGES: die(f"usage: refer.py stage <c-id> <{'|'.join(STAGES)}> [--job j-NNNN]")
    d = load_c(); c = contact(d, args[0]); st, cap, nudge = args[1], *settings()
    when = date_arg(args)
    if when < c["history"][-1]["date"]: die(f"{when} is before the last change ({c['history'][-1]['date']})")
    job = opt(args, "--job")
    if st == "asked":
        job = job or c.get("job") or die("an ask is for a role: give --job j-NNNN")
        j = find(load_jobs()["jobs"], job) or die(f"no job {job}")
        if job in d["holds"]: die(f"{job} is held out of outreach ({d['holds'][job]}): unhold it first")
        if j["company"].lower() in {x.lower() for x in d["parked"]}: die(f"{j['company']} is parked: unpark it first")
        other = next((x for x in d["contacts"] if x["id"] != c["id"] and x.get("job") == job and stage_of(x) in ("asked", "replied_yes", "referred")
                      and not released(x, nudge)), None)
        if other: die(f"{other['name']} ({other['id']}) is already asked for {job}: one contact per role, until they decline or go quiet past the nudge")
        if stage_of(c) != "asked" and asks_today(d) >= cap: die(f"the daily cap of {cap} asks is reached: send the rest tomorrow")
        c["job"], c["nudged"] = job, None
    c["history"].append({"date": when, "stage": st, "note": opt(args, "--note") or "", "source": "user", **({"job": job} if job else {})})
    if st == "declined": c["job"] = None
    save(CONTACTS, d); print(f"{c['id']}  {c['name']}: {st}" + (f" for {job}" if st == "asked" else "")); return 0

def nudged(args):
    d = load_c(); c = contact(d, args[0])
    if stage_of(c) != "asked": die("only a waiting ask gets a nudge")
    if c.get("nudged"): die(f"already nudged on {c['nudged']}: one nudge, then nothing")
    c["nudged"] = date_arg(args); save(CONTACTS, d); print(f"{c['id']}  nudged {c['nudged']}"); return 0

def facts_line(p):
    """Check a line about the user like a resume line."""
    import claims
    facts = {f["id"]: f for f in read_jsonl(PROFILE / "facts.jsonl")}
    emp = load(PROFILE / "employment.json", []) or []
    emp_text = " ".join(f"{e.get('employer', '')} {e.get('role', '')}" for e in emp)
    probs = claims.check_line(p.get("text", ""), p.get("facts") or [], facts, emp_text)
    if probs: die("the line about them doesn't pass the truth rule: " + "; ".join(probs))
    return p["text"].strip()

def ask(args):
    d = load_c(); c = contact(d, args[0]); jid = opt(args, "--job") or c.get("job") or die("give --job j-NNNN")
    j = find(load_jobs()["jobs"], jid) or die(f"no job {jid}")
    kind = opt(args, "--kind", "ask")
    if kind not in ("ask", "connect"): die("--kind is ask or connect")
    ident = load(PROFILE / "identity.json", {}) or {}
    me = (ident.get("name") or {}).get("preferred") or (ident.get("name") or {}).get("full") or ""
    pitch = facts_line(payload(opt(args, "--pitch"))) if opt(args, "--pitch") else ""
    t = kit_path("templates", f"refer_{kind}.md").read_text(encoding="utf-8")
    first = c["name"].split()[0]
    msg = t.format(first_name=first, company=j["company"], role=j["title"], job_link=j.get("url") or "", me=me, pitch=pitch,
                   how_known=c.get("how_known") or "").strip()
    msg = re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+\n", "\n", msg))
    words = len(re.findall(r"\b[\w'’-]+\b", msg))
    if kind == "ask" and words > ASK_WORDS: die(f"the ask is {words} words: keep it under {ASK_WORDS} (shorten the pitch line)")
    if kind == "connect" and len(msg) > CONNECT_CHARS: die(f"the connection note is {len(msg)} characters: keep it under {CONNECT_CHARS}")
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{c['id']}-{jid}-{kind}.md"; p.write_text(msg + "\n", encoding="utf-8", newline="\n")
    print(msg); print(f"\n-- {words} words, {len(msg)} characters; saved {rel(p)}. Send it yourself, then: refer.py stage {c['id']} asked --job {jid}")
    return 0

def hold(args, on):
    d = load_c(); jid = args[0] if args else die("give the job id")
    if on: d["holds"][jid] = opt(args, "--note") or die("hold needs --note with the reason")
    else: d["holds"].pop(jid, None)
    save(CONTACTS, d); print(f"{jid}: " + ("held out of outreach" if on else "back in outreach")); return 0

def park(args, on):
    d = load_c(); name = " ".join(x for x in args if not x.startswith("--")).strip() or die("give the company")
    d["parked"] = [x for x in d["parked"] if x.lower() != name.lower()] + ([name] if on else [])
    save(CONTACTS, d); print(f"{name}: " + ("parked (no live role)" if on else "unparked")); return 0

def listing(args):
    d = load_c(); co = opt(args, "--company"); cap, nudge = settings()
    rows = [c for c in d["contacts"] if (not co or c["company"].lower() == co.lower()) and ("--all" in args or stage_of(c) != "declined")]
    for c in sorted(rows, key=lambda c: (c["company"].lower(), c["id"])):
        extra = f" for {c['job']}" if c.get("job") else ""
        extra += f", nudged {c['nudged']}" if c.get("nudged") else ""
        extra += " (parked company)" if c["company"].lower() in {x.lower() for x in d["parked"]} else ""
        print(f"{c['id']}  {c['company']:<20} {c['name']:<24} {stage_of(c):<12} since {c['history'][-1]['date']}{extra}")
    if not rows: print("no contacts yet: refer.py add")
    return 0

def due(args):
    d = load_c(); cap, nudge = settings(); n = asks_today(d)
    print(f"asks today: {n} of {cap}")
    for c in d["contacts"]:
        if stage_of(c) != "asked": continue
        waited = days_since(c["history"][-1]["date"])
        if not c.get("nudged") and waited >= nudge: print(f"nudge due: {c['id']} {c['name']} at {c['company']} ({waited} days, {c.get('job')})")
        elif released(c, nudge): print(f"quiet past the nudge: {c['id']} {c['name']}: {c.get('job')} is free for another contact")
    for jid, why in d["holds"].items(): print(f"held: {jid} ({why})")
    for x in d["parked"]: print(f"parked: {x}")
    return 0

def main(a):
    if not a: print(__doc__); return 1
    cmd, rest = a[0], a[1:]
    if cmd == "add" and rest: return add(rest[0])
    if cmd == "list": return listing(rest)
    if cmd == "stage": return set_stage(rest)
    if cmd == "nudged" and rest: return nudged(rest)
    if cmd == "ask" and rest: return ask(rest)
    if cmd in ("hold", "unhold"): return hold(rest, cmd == "hold")
    if cmd in ("park", "unpark"): return park(rest, cmd == "park")
    if cmd == "due": return due(rest)
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
