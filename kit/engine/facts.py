#!/usr/bin/env python3
"""The facts bank (profile/facts.jsonl). Only confirmed, non-private facts can be cited by /tailor.
  facts.py add <payload>                 one fact or a list: {kind, text, employer?, role?, period?, metrics?,
                                         keywords?, private?, source}; saved as draft unless "status": "confirmed"
  facts.py confirm <id>[,<id>...] | --all-drafts   they approved the wording
  facts.py edit <id> <payload> [--confirm]          change fields; old text kept in history; back to draft
                                                    unless --confirm (they approved the new wording just now)
  facts.py retire <id> --note <reason>   never citable again (kept for history)
  facts.py list [--status S] [--kind K] [--employer E] [--json]
  facts.py search <words...> [--all]     ranked by words and the pack's keyword variants; confirmed only unless --all
  facts.py get <id>[,<id>...]            JSON
Payloads: inline JSON, '-' (stdin) or '@data/tmp/<file>.json'.
"""
import json, re, sys
from _common import PROFILE, payload, opt, die, read_jsonl, write_jsonl, stamp, today, next_id, norm
from validate import fact_errors, FACT_KINDS
import kw

FACTS = PROFILE / "facts.jsonl"
FIELDS = ("kind", "text", "employer", "role", "period", "metrics", "keywords", "private", "source")

def load_facts(): return read_jsonl(FACTS)

def citable(f): return f.get("status") == "confirmed" and not f.get("private")

def save_all(rows):
    errs = [e for f in rows for e in fact_errors(f)]
    if errs: die("; ".join(errs))
    write_jsonl(FACTS, rows)

def ids_arg(s): return [x.strip() for x in s.split(",") if x.strip()]

def add(raw):
    d = payload(raw)
    items = d if isinstance(d, list) else [d]
    rows, new = load_facts(), []
    for it in items:
        if not isinstance(it, dict): die("each fact must be a JSON object")
        unknown = set(it) - set(FIELDS) - {"status"}
        if unknown: die(f"unknown fields {sorted(unknown)}; allowed: {', '.join(FIELDS)}")
        f = {"id": next_id(rows + new, "f"), **{k: it[k] for k in FIELDS if k in it}}
        f.setdefault("keywords", []); f.setdefault("metrics", []); f.setdefault("private", False)
        f["text"] = str(f.get("text", "")).strip()
        f["status"] = "confirmed" if it.get("status") == "confirmed" else "draft"
        if f["status"] == "confirmed": f["confirmed"] = today().isoformat()
        f["created"] = f["updated"] = stamp(); f["history"] = []
        dup = [r["id"] for r in rows + new if norm(r["text"]) == norm(f["text"]) and r.get("status") != "retired"]
        if dup: die(f"the same text is already {dup[0]}; edit that one instead")
        errs = fact_errors(f, f"new fact '{f['text'][:40]}'")
        if errs: die("; ".join(errs))
        new.append(f)
    save_all(rows + new)
    for f in new: print(f"{f['id']}  {f['status']:<9} {f['kind']:<14} {f['text'][:90]}")
    return 0

def confirm(args):
    rows = load_facts()
    want = {r["id"] for r in rows if r["status"] == "draft"} if "--all-drafts" in args else set(ids_arg(args[0]) if args else [])
    if not want: die("name the facts to confirm (f-0001,f-0002) or --all-drafts")
    missing = want - {r["id"] for r in rows}
    if missing: die(f"no such facts: {', '.join(sorted(missing))}")
    n = 0
    for r in rows:
        if r["id"] in want:
            if r["status"] == "retired": die(f"{r['id']} is retired; add it again if it's true after all")
            if r["status"] != "confirmed":
                r.update(status="confirmed", confirmed=today().isoformat(), updated=stamp()); n += 1
    save_all(rows)
    print(f"confirmed {n} fact(s)" + (f" ({len(want) - n} already confirmed)" if len(want) > n else ""))
    return 0

def edit(fid, raw, args):
    d, rows = payload(raw), load_facts()
    f = next((r for r in rows if r["id"] == fid), None) or die(f"no fact {fid}")
    if f["status"] == "retired": die(f"{fid} is retired")
    bad = set(d) - set(FIELDS)
    if bad: die(f"can't edit {sorted(bad)}")
    f["history"].append({"ts": stamp(), "text": f["text"], "status": f["status"], "source": f.get("source")})
    f.update({k: (str(v).strip() if k == "text" else v) for k, v in d.items()})
    if "--confirm" in args: f.update(status="confirmed", confirmed=today().isoformat())
    else: f["status"] = "draft"; f.pop("confirmed", None)
    f["updated"] = stamp()
    save_all(rows)
    print(f"{fid}  {f['status']}  {f['text'][:100]}")
    return 0

def retire(fid, args):
    note = opt(args, "--note") or die("retire needs --note <reason>")
    rows = load_facts()
    f = next((r for r in rows if r["id"] == fid), None) or die(f"no fact {fid}")
    f["history"].append({"ts": stamp(), "text": f["text"], "status": f["status"], "note": f"retired: {note}"})
    f.update(status="retired", updated=stamp()); f.pop("confirmed", None)
    save_all(rows)
    print(f"{fid} retired ({note})")
    return 0

def show(rows, as_json):
    if as_json: print(json.dumps(rows, indent=1, ensure_ascii=False)); return
    if not rows: print("No facts match."); return
    for f in rows:
        where = " · ".join(x for x in (f.get("role"), f.get("employer")) if x)
        flags = (" PRIVATE" if f.get("private") else "")
        print(f"{f['id']}  {f['status']:<9} {f['kind']:<14} {f['text']}" + (f"  [{where}]" if where else "") + flags)

def list_facts(args):
    rows = load_facts()
    for flag, key in (("--status", "status"), ("--kind", "kind"), ("--employer", "employer")):
        v = opt(args, flag)
        if v: rows = [r for r in rows if str(r.get(key) or "").lower() == v.lower()]
    if not opt(args, "--status"): rows = [r for r in rows if r["status"] != "retired"]
    show(rows, "--json" in args)
    counts = {s: sum(r["status"] == s for r in load_facts()) for s in ("confirmed", "draft", "retired")}
    if "--json" not in args: print(f"-- {counts['confirmed']} confirmed, {counts['draft']} draft, {counts['retired']} retired")
    return 0

def fact_text(f):
    return " ".join([f.get("text", ""), " ".join(f.get("keywords") or []), f.get("role") or "", f.get("employer") or "",
                     " ".join(f"{m.get('name','')} {m.get('value','')}{m.get('unit','')}" for m in f.get("metrics") or [])])

def search(words, include_all=False):
    q = " ".join(words)
    qterms = set(kw.find(q))
    qwords = [w for w in norm(q).split() if len(w) > 2]
    scored = []
    for f in load_facts():
        if f["status"] == "retired" or (not include_all and not citable(f)): continue
        t = fact_text(f); nt = norm(t)
        s = 3 * len(qterms & set(kw.find(t))) + sum(1 for w in qwords if re.search(rf"\b{re.escape(w)}", nt))
        if s: scored.append((s, f))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    show([f for _, f in scored], False)
    return 0

def get(ids):
    want = ids_arg(ids)
    rows = {r["id"]: r for r in load_facts()}
    missing = [i for i in want if i not in rows]
    if missing: die(f"no such facts: {', '.join(missing)}")
    print(json.dumps([rows[i] for i in want], indent=1, ensure_ascii=False))
    return 0

def main(a):
    if not a: print(__doc__); return 1
    cmd, rest = a[0], a[1:]
    if cmd == "add" and rest: return add(rest[0])
    if cmd == "confirm": return confirm(rest)
    if cmd == "edit" and len(rest) >= 2: return edit(rest[0], rest[1], rest[2:])
    if cmd == "retire" and rest: return retire(rest[0], rest[1:])
    if cmd == "list": return list_facts(rest)
    if cmd == "search" and rest: return search([w for w in rest if w != "--all"], "--all" in rest)
    if cmd == "get" and rest: return get(rest[0])
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
