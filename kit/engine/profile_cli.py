#!/usr/bin/env python3
"""Their profile files other than the facts bank: identity, search rules, employment, education, resume preferences,
and the /start progress record.
  profile_cli.py init                          create missing files with the stated defaults (safe to re-run)
  profile_cli.py show [identity|search|employment|education|prefs|intake]
  profile_cli.py set <section> <payload>       identity, search, prefs: merged in; employment, education: the whole list
  profile_cli.py current "<title>" [--ctc L] [--fixed L] [--variable P]   their current title (mapped to the pack ladder)
                                           and pay in lakh per annum
  profile_cli.py answer "<question>" "<their answer>"   keep their own words for a search rule
  profile_cli.py intake [done <stage> | ask "<question>" | answered <n> "<answer>"]
  profile_cli.py packs                         the fields the kit has a pack for
  profile_cli.py pack <id>                     choose the field: sets search.pack and that pack's default role families
  profile_cli.py titles <"title", ...>         the job titles they're after (any field; the sweep keeps roles matching them)
  profile_cli.py abroad [show | add <CC> [--cities "A, B"] [--at N] | remove <CC> | move <CC> <N>]
                                           their ordered list of countries (and cities) abroad; every one counts as eligible
Payloads: inline JSON, '-' (stdin) or '@data/tmp/<file>.json'.
"""
import json, sys
from _common import PROFILE, load, save, payload, opt, die, today, stamp, pack, packs, DEFAULT_PACK
from validate import identity_errors, search_errors, employment_errors, education_errors, prefs_errors
from fit import ESTABLISHED, GEO

FILES = {"identity": "identity.json", "search": "search.json", "employment": "employment.json",
         "education": "education.json", "prefs": "resume_prefs.json", "intake": "intake.json"}
CHECKS = {"identity": identity_errors, "search": search_errors, "employment": employment_errors,
          "education": education_errors, "prefs": prefs_errors}
STAGES = ["field", "documents", "facts", "gaps", "identity", "search", "prefs", "gmail"]

def defaults():
    roles = pack().get("roles", {}).get("families", [])
    return {
        "identity": {"name": {"full": "", "preferred": "", "resume": ""}, "email": "", "phone": "",
                     "links": {"linkedin": "", "other": []}, "location": {"city": "", "state": "", "country": "IN"},
                     "source": "engine", "updated": today().isoformat()},
        "search": {"pack": pack()["id"] if pack().get("id") else DEFAULT_PACK,
                   "target_families": [r["id"] for r in roles if r.get("default")], "target_titles": [],
                   "current": {"title": "", "ladder_rank": None, "ctc_lpa": None, "fixed_lpa": None, "variable_pct": None},
                   "rules": {"never_lower_level": True, "lateral_min_raise_pct": 20, "raise_basis": "ctc",
                             "abroad_stability": list(ESTABLISHED), "pe_min_employees": 1000, "pe_min_years": 10},
                   "locations": {"home_country": "IN", "eligible_countries": ["IN"], "preferred": [], "avoid": [],
                                 "abroad": [], "pay_over_place": False, "remote_ok": True, "relocate": True},
                   "notice_period_days": None, "deal_breakers": [],
                   "referrals": {"daily_cap": 20, "nudge_days": 5},
                   "gmail": {"enabled": False, "mode": "imap", "address": "", "label": "Job Alerts", "checked": None},
                   "answers": [], "source": "engine", "updated": today().isoformat()},
        "employment": [], "education": [],
        "prefs": {"format": ["pdf", "docx"], "page_limit": 2, "contacts": ["email", "phone", "linkedin", "city"],
                  "source": "engine", "updated": today().isoformat()},
        "intake": {"stages": {s: "open" for s in STAGES}, "questions": [], "updated": stamp()},
    }

def path(section):
    if section not in FILES: die(f"section must be one of {', '.join(FILES)}")
    return PROFILE / FILES[section]

def get(section):
    d = load(path(section))
    return d if d is not None else defaults()[section]

def put(section, d):
    errs = CHECKS[section](d) if section in CHECKS else []
    if errs: die("; ".join(errs))
    if isinstance(d, dict) and section != "intake": d["updated"] = today().isoformat()
    save(path(section), d)

def merge(base, new):
    for k, v in new.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict): merge(base[k], v)
        else: base[k] = v
    return base

def init():
    made = []
    for s in FILES:
        if not path(s).exists(): save(path(s), defaults()[s]); made.append(FILES[s])
    (PROFILE / "facts.jsonl").touch(exist_ok=True)
    print("created " + ", ".join(made) if made else "profile already set up")
    return 0

def set_section(section, raw):
    d = payload(raw)
    if section in ("employment", "education"):
        if not isinstance(d, list): die(f"{section} takes the whole list")
        for r in d: r.setdefault("source", "user")
        new = d
    elif section in ("identity", "search", "prefs"):
        if not isinstance(d, dict): die(f"{section} takes a JSON object")
        if section == "search" and d.get("rules", {}).get("never_lower_level") is False:
            die("never_lower_level is a fixed rule: a role below their current level is never suggested")
        new = merge(get(section), d)
        new["source"] = "user"
    else: die("set works on identity, search, employment, education or prefs")
    put(section, new)
    print(f"saved {FILES[section]}")
    return 0

def current(args):
    from fit import level_of
    title = args[0] if args and not args[0].startswith("--") else die('usage: current "<title>" [--ctc L] [--fixed L] [--variable P]')
    s = get("search")
    rank, matched = level_of(title)
    s["current"]["title"] = title
    s["current"]["ladder_rank"] = rank
    for flag, key in (("--ctc", "ctc_lpa"), ("--fixed", "fixed_lpa"), ("--variable", "variable_pct")):
        v = opt(args, flag)
        if v is not None:
            try: s["current"][key] = float(v)
            except ValueError: die(f"{flag} must be a number")
    s["source"] = "user"
    put("search", s)
    print(f"current: {title} -> " + (f"ladder rank {rank} ({matched})" if rank else "NOT on the pack ladder: ask them which level it equals and set it with "
          "profile_cli.py set search '{\"current\": {\"ladder_rank\": N}}'"))
    return 0

def answer(q, a):
    s = get("search")
    s["answers"].append({"q": q, "a": a, "date": today().isoformat()})
    put("search", s)
    print(f"recorded answer {len(s['answers'])}")
    return 0

def intake(args):
    d = get("intake")
    if args and args[0] == "done" and len(args) > 1:
        if args[1] not in STAGES: die(f"stage must be one of {', '.join(STAGES)}")
        d["stages"][args[1]] = "done"
    elif args and args[0] == "ask" and len(args) > 1:
        d["questions"].append({"n": len(d["questions"]) + 1, "q": args[1], "a": None, "asked": today().isoformat()})
    elif args and args[0] == "answered" and len(args) > 2:
        q = next((x for x in d["questions"] if str(x["n"]) == args[1]), None) or die(f"no question {args[1]}")
        q.update(a=args[2], answered=today().isoformat())
    elif args: die('usage: intake [done <stage> | ask "<q>" | answered <n> "<a>"]')
    d["updated"] = stamp()
    save(path("intake"), d)
    nxt = next((s for s in STAGES if d["stages"].get(s) != "done"), None)
    print("stages: " + ", ".join(f"{s} {'done' if d['stages'].get(s) == 'done' else 'open'}" for s in STAGES))
    openq = [q for q in d["questions"] if not q.get("a")]
    print(f"open questions: {len(openq)}" + "".join(f"\n  {q['n']}. {q['q']}" for q in openq))
    print(f"next stage: {nxt}" if nxt else "intake complete")
    return 0

def country_code(text):
    """'AE', 'UAE' or 'United Arab Emirates' -> 'AE'."""
    t = text.strip()
    if t.upper() in GEO.get("countries", {}): return t.upper()
    for code, names in GEO.get("countries", {}).items():
        if any(n.lower() == t.lower() for n in names): return code
    die(f"{text!r} isn't a country the kit knows: use its two-letter code (AE, SA, SG ...)")

def list_packs():
    cur = get("search").get("pack")
    for pid, name, desc in packs(): print(f"{pid:<16} {name}{'  (chosen)' if pid == cur else ''}\n                 {desc}")
    return 0

def choose_pack(pid):
    ids = [p[0] for p in packs()]
    if pid not in ids: die(f"no pack {pid!r}: choose one of {', '.join(ids)} (general fits any field)")
    s = get("search")
    s["pack"] = pid
    s["target_families"] = [f["id"] for f in pack(pid).get("roles", {}).get("families", []) if f.get("default")]
    s.setdefault("target_titles", [])
    s["source"] = "user"; put("search", s)
    if (s.get("current") or {}).get("title"):   # the ladder changed: map the current title again
        import _common; _common._PACK.clear()
        from fit import level_of
        s["current"]["ladder_rank"] = level_of(s["current"]["title"])[0]; put("search", s)
    fams = s["target_families"]
    print(f"field: {pack(pid).get('name', pid)}; role families ticked by default: {', '.join(fams) or 'none (set target titles)'}")
    return 0

def set_titles(args):
    titles = [t.strip() for a in args for t in a.split(",") if t.strip()]
    s = get("search"); s["target_titles"] = titles; s["source"] = "user"; put("search", s)
    print("target titles: " + (", ".join(titles) or "none")); return 0

def show_abroad(L):
    ab = L.get("abroad") or []
    if not ab: print("abroad list: empty (home country only, plus eligible_countries)"); return
    for i, a in enumerate(ab, 1):
        name = GEO.get("countries", {}).get(a["country"], [a["country"]])[0]
        print(f"  {i}. {name} ({a['country']})" + (f": {', '.join(a['cities'])}" if a.get("cities") else ""))

def abroad(args):
    s = get("search"); L = s.setdefault("locations", {}); ab = L.setdefault("abroad", [])
    cmd = args[0] if args else "show"
    pos = [x for x in args[1:] if not x.startswith("--")]
    if cmd == "show": show_abroad(L); return 0
    if cmd == "add" and pos:
        code = country_code(pos[0])
        if any(a["country"] == code for a in ab): die(f"{code} is already on the list (move it, or remove it first)")
        cities = [c.strip() for c in (opt(args, "--cities") or "").split(",") if c.strip()]
        at = opt(args, "--at")
        n = int(at) - 1 if at and at.isdigit() else len(ab)
        ab.insert(max(0, min(n, len(ab))), {"country": code, "cities": cities})
    elif cmd == "remove" and pos:
        code = country_code(pos[0])
        if not any(a["country"] == code for a in ab): die(f"{code} isn't on the list")
        L["abroad"] = ab = [a for a in ab if a["country"] != code]
    elif cmd == "move" and len(pos) == 2 and pos[1].isdigit():
        code = country_code(pos[0])
        item = next((a for a in ab if a["country"] == code), None) or die(f"{code} isn't on the list")
        ab.remove(item); ab.insert(max(0, min(int(pos[1]) - 1, len(ab))), item)
    else: die('usage: abroad [show | add <CC> [--cities "A, B"] [--at N] | remove <CC> | move <CC> <N>]')
    s["source"] = "user"
    put("search", s)
    show_abroad(L)
    return 0

def show(section):
    secs = [section] if section else list(FILES)
    for s in secs:
        print(f"== {FILES[s]}"); print(json.dumps(get(s), indent=1, ensure_ascii=False))
    return 0

def main(a):
    if not a: print(__doc__); return 1
    cmd, rest = a[0], a[1:]
    if cmd == "init": return init()
    if cmd == "show": return show(rest[0] if rest else None)
    if cmd == "set" and len(rest) == 2: return set_section(rest[0], rest[1])
    if cmd == "current": return current(rest)
    if cmd == "answer" and len(rest) == 2: return answer(rest[0], rest[1])
    if cmd == "intake": return intake(rest)
    if cmd == "abroad": return abroad(rest)
    if cmd == "packs": return list_packs()
    if cmd == "pack" and rest: return choose_pack(rest[0])
    if cmd == "titles": return set_titles(rest)
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
