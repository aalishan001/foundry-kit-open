#!/usr/bin/env python3
"""Interview prep for one job's gaps, under the truth rule.
  prep.py gaps <j-id> [--grill <log>]      the gaps /check saved for the job (with the closest facts), and the weakest
                                           areas of a /grill log when given
  prep.py links <url> [<url> ...]          check resource links live (one polite request each)
  prep.py save <j-id> <payload>            {gaps: [{gap, primer, expect: [..], questions: [{q, answer, facts: [ids],
                                           bridge?}], quiz: [{q, a}], resources: [{title, url, why?}]}]}
                                           -> data/prep/<j-id>/prep.json, one Markdown file per gap, claims.json
  prep.py show <j-id>                      what's saved for the job
Rules for a save, all checked: per gap a primer of at least 600 characters (about ten minutes with the resources),
at least two expectations, exactly 3 questions, at least 5 quiz items and at least one resource. Every answer cites
confirmed, non-private facts, and its numbers and names appear in them (claims.py rules); naming the topic the gap or
question is about isn't a claim. An answer that only says honestly what they hasn't done ("bridge": false) needs no
citation unless it states a number, or a name from outside the gap, the question and the primer. Every
resource link must answer live (https only; LinkedIn and Naukri are never fetched). Nothing is saved if any check
fails.
"""
import sys
from _common import DATA, PROFILE, load, save, payload, die, today, stamp, read_jsonl, slug, rel, opt
import claims
from jobs import load_jobs, find

PREP = DATA / "prep"
MIN_PRIMER, MIN_EXPECT, N_QUESTIONS, MIN_QUIZ = 600, 2, 3, 5

def gap_text(g): return (g.get("gap") or g.get("text") or "") if isinstance(g, dict) else str(g)

def gaps(args):
    jid = args[0] if args else die("usage: prep.py gaps <j-id> [--grill <log>]")
    j = find(load_jobs()["jobs"], jid) or die(f"no job {jid}")
    fit = j.get("fit") or {}
    rows = fit.get("gaps") or []
    print(f"{j['id']}  {j['company']} · {j['title']}")
    if not rows and not opt(args, "--grill"):
        print("no gaps saved for this job yet: run /check on it first (its gaps are what /prep works on)"); return 1
    for i, g in enumerate(rows, 1):
        close = g.get("closest") or g.get("closest_fact") if isinstance(g, dict) else None
        print(f"  gap {i}: {gap_text(g)}" + (f"  (closest: {close})" if close else ""))
    if opt(args, "--grill"):
        import grill_clock
        for area, avg, n in grill_clock.weakest(opt(args, "--grill")):
            print(f"  grill area: {area}  average {avg:.1f}/10 over {n} answer(s)")
    return 0

def links(args):
    from fetch import check_link
    bad = 0
    for u in args:
        ok, why = check_link(u)
        bad += not ok
        print(f"{'ok  ' if ok else 'DEAD'}  {u}  {why}")
    return 1 if bad else 0

def problems(job, d):
    from fetch import check_link
    facts = {f["id"]: f for f in read_jsonl(PROFILE / "facts.jsonl")}
    emp = load(PROFILE / "employment.json", []) or []
    emp_text = " ".join(f"{e.get('employer', '')} {e.get('role', '')} {e.get('location', '')}" for e in emp)
    probs, mapping, checked = [], {}, {}
    gs = d.get("gaps") or []
    if not gs: return ["the payload has no gaps"], {}, {}
    for n, g in enumerate(gs, 1):
        w = f"gap {n} ({gap_text(g)[:40] or '?'})"
        if not gap_text(g).strip(): probs.append(f"{w}: name the gap")
        if len((g.get("primer") or "").strip()) < MIN_PRIMER: probs.append(f"{w}: the primer is under {MIN_PRIMER} characters")
        if len([x for x in g.get("expect") or [] if str(x).strip()]) < MIN_EXPECT: probs.append(f"{w}: give at least {MIN_EXPECT} things interviewers expect")
        qs = g.get("questions") or []
        if len(qs) != N_QUESTIONS: probs.append(f"{w}: exactly {N_QUESTIONS} likely questions, not {len(qs)}")
        for k, q in enumerate(qs, 1):
            ans, ids = (q.get("answer") or "").strip(), q.get("facts") or []
            if not (q.get("q") or "").strip() or not ans: probs.append(f"{w} Q{k}: needs the question and their answer"); continue
            # Naming the topic being asked about isn't a claim about them: terms from the gap and the question are allowed,
            # and an honest no-bridge answer ("I haven't; I would start with ...") may also use the primer's terms.
            topic = " ".join([gap_text(g), q.get("q") or ""] + ([g.get("primer") or ""] + list(g.get("expect") or []) if q.get("bridge") is False else []))
            own = [n for n in claims.names(ans) if not claims.kw.mentions(topic, n)]
            if q.get("bridge") is False and not ids and not claims.nums(ans) and not own: continue
            for p in claims.check_line(ans, ids, facts, emp_text + " " + topic): probs.append(f"{w} Q{k}: {p}")
            mapping[f"gap {n} Q{k}: {ans}"] = ids
        if len([x for x in g.get("quiz") or [] if (x.get("q") or "").strip() and (x.get("a") or "").strip()]) < MIN_QUIZ:
            probs.append(f"{w}: at least {MIN_QUIZ} quiz items, each with its answer")
        res = g.get("resources") or []
        if not res: probs.append(f"{w}: at least one free resource")
        for r in res:
            u = r.get("url") or ""
            if not (r.get("title") or "").strip(): probs.append(f"{w}: a resource needs a title ({u})")
            if u not in checked: checked[u] = check_link(u)
            if not checked[u][0]: probs.append(f"{w}: dead link {u} ({checked[u][1]}): drop it or find another")
    return probs, mapping, checked

def md(job, n, g, checked):
    out = [f"# {gap_text(g)}", "", f"For {job['company']} · {job['title']} ({job['id']}). Prepared {today().isoformat()}.", "",
           "## Primer (about 10 minutes)", "", g["primer"].strip(), "", "## What interviewers expect", ""]
    out += [f"- {x}" for x in g["expect"]] + ["", "## Likely questions", ""]
    for k, q in enumerate(g["questions"], 1):
        cite = f" <!-- facts: {', '.join(q['facts'])} -->" if q.get("facts") else ""
        out += [f"**Q{k}. {q['q']}**", "", q["answer"].strip() + cite, ""]
    out += ["## Quiz", ""] + [f"{k}. {x['q']}" for k, x in enumerate(g["quiz"], 1)] + ["", "<details><summary>Answers</summary>", ""]
    out += [f"{k}. {x['a']}" for k, x in enumerate(g["quiz"], 1)] + ["", "</details>", "", "## Free resources", ""]
    for r in g["resources"]:
        out.append(f"- [{r['title']}]({r['url']})" + (f": {r['why']}" if r.get("why") else "") + f" (link checked {today().isoformat()})")
    return "\n".join(out) + "\n"

def save_prep(args):
    if len(args) < 2: die("usage: prep.py save <j-id> <payload>")
    job = find(load_jobs()["jobs"], args[0]) or die(f"no job {args[0]}")
    d = payload(args[1])
    probs, mapping, checked = problems(job, d)
    if probs:
        print("NOT SAVED. Fix these and save again:\n- " + "\n- ".join(probs)); return 1
    folder = PREP / job["id"]; folder.mkdir(parents=True, exist_ok=True)
    files = []
    for n, g in enumerate(d["gaps"], 1):
        p = folder / f"{n:02d}-{slug(gap_text(g), 40)}.md"
        p.write_text(md(job, n, g, checked), encoding="utf-8", newline="\n"); files.append(rel(p))
    links_ = {u: {"ok": ok, "detail": why, "checked": today().isoformat()} for u, (ok, why) in checked.items()}
    save(folder / "prep.json", {"job": job["id"], "ts": stamp(), "gaps": d["gaps"], "links": links_, "files": files})
    save(folder / "claims.json", mapping)
    for f in files: print(f"saved {f}")
    print(f"-- {len(d['gaps'])} gap(s); {len(mapping)} answers trace to confirmed facts; {len(checked)} link(s) live")
    return 0

def show(args):
    jid = args[0] if args else die("usage: prep.py show <j-id>")
    d = load(PREP / jid / "prep.json")
    if not d: print(f"no prep for {jid} yet: /prep {jid}"); return 0
    print(f"{jid}: prepared {d['ts'][:10]}")
    for f in d["files"]: print(f"  {f}")
    return 0

def main(a):
    if not a: print(__doc__); return 1
    cmd, rest = a[0], a[1:]
    if cmd == "gaps": return gaps(rest)
    if cmd == "links": return links(rest)
    if cmd == "save": return save_prep(rest)
    if cmd == "show": return show(rest)
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
