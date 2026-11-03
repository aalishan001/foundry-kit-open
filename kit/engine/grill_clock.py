#!/usr/bin/env python3
"""Append-only, timestamped mock-interview log. No do-overs.
  grill_clock.py start <slug> [--limit 45]         -> prints the log path
  grill_clock.py ask <file> "<question>" [--budget N]
  grill_clock.py answer <file> "<answer>"
  grill_clock.py score <file> <n> <0-10> --area <topic> [--why T]   the score for answer n, as given (once)
  grill_clock.py weakest <file>                  areas by average score, weakest first (for /prep --areas)
  grill_clock.py status <file>
  grill_clock.py end <file> [--score X]
"""
import datetime as dt, sys
from _common import DATA, now, read_jsonl, append_jsonl, slug, die

iso = lambda t: t.isoformat()

def started(ev): return dt.datetime.fromisoformat(ev[0]["ts"]), ev[0].get("limit_min", 45)

def status(f, quiet=False):
    ev = read_jsonl(f)
    if not ev: die(f"{f} is not a grill log")
    t0, lim = started(ev)
    used = (now() - t0).total_seconds() / 60
    if not quiet: print(f"Elapsed {used:.1f} / {lim} min. {'TIME UP' if used >= lim else ''}".rstrip())
    return used, lim, ev

def guard(f):
    used, lim, ev = status(f, quiet=True)
    if ev[-1]["type"] == "end": die("the session already ended; the log is append-only")
    if used >= lim:
        append_jsonl(f, {"ts": iso(now()), "type": "end", "reason": "time limit"})
        print("TIME UP: the session ended automatically. Give the scorecard now."); sys.exit(2)
    return ev

def weakest(f):
    """[(area, average, count)], weakest first."""
    by = {}
    for e in read_jsonl(f):
        if e["type"] == "score": by.setdefault(e["area"], []).append(e["score"])
    return sorted(((k, sum(v) / len(v), len(v)) for k, v in by.items()), key=lambda x: (x[1], x[0]))

def main(a):
    if len(a) < 2: print(__doc__); return 1
    cmd = a[0]
    if cmd == "start":
        lim = int(a[a.index("--limit") + 1]) if "--limit" in a else 45
        f = DATA / "grills" / f"{now():%Y%m%d-%H%M}-{slug(a[1])}.jsonl"
        f.parent.mkdir(parents=True, exist_ok=True)
        append_jsonl(f, {"ts": iso(now()), "type": "start", "slug": slug(a[1]), "limit_min": lim}); print(f); return 0
    f = a[1]
    if cmd == "status": status(f); return 0
    if cmd == "ask" and len(a) > 2:
        ev = guard(f)
        if ev[-1]["type"] == "ask": die('the previous question is unanswered; log an answer first (use "(no answer)")')
        b = float(a[a.index("--budget") + 1]) if "--budget" in a else None
        n = sum(e["type"] == "ask" for e in ev) + 1
        append_jsonl(f, {"ts": iso(now()), "type": "ask", "n": n, "q": a[2], "budget_min": b}); print(f"Q{n} logged."); return 0
    if cmd == "answer" and len(a) > 2:
        ev = guard(f)
        q = next((e for e in reversed(ev) if e["type"] == "ask"), None)
        if not q or ev[-1]["type"] != "ask": die("no open question; answers are final (no do-overs)")
        took = (now() - dt.datetime.fromisoformat(q["ts"])).total_seconds() / 60
        over = q["budget_min"] is not None and took > q["budget_min"]
        append_jsonl(f, {"ts": iso(now()), "type": "answer", "n": q["n"], "a": a[2], "took_min": round(took, 1), "overtime": over})
        print(f"Q{q['n']} answered in {took:.1f} min{' (OVERTIME)' if over else ''}."); status(f); return 0
    if cmd == "score" and len(a) > 3:
        ev = read_jsonl(f)
        try: n, sc = int(a[2]), float(a[3])
        except ValueError: die("usage: score <file> <n> <0-10> --area <topic>")
        if not 0 <= sc <= 10: die("a score is 0-10")
        area = a[a.index("--area") + 1] if "--area" in a else die("score needs --area (the topic: technical, commercial, people ...)")
        if not any(e["type"] == "answer" and e["n"] == n for e in ev): die(f"answer {n} isn't logged")
        if any(e["type"] == "score" and e["n"] == n for e in ev): die(f"answer {n} is already scored (scores are final)")
        why = a[a.index("--why") + 1] if "--why" in a else ""
        append_jsonl(f, {"ts": iso(now()), "type": "score", "n": n, "score": sc, "area": area, "why": why}); print(f"Q{n}: {sc:g}/10 ({area})"); return 0
    if cmd == "weakest":
        rows = weakest(f)
        if not rows: print("no scored answers in this log"); return 0
        for area, avg, k in rows: print(f"{area:<24} {avg:>4.1f}/10  ({k} answer(s))")
        return 0
    if cmd == "end":
        ev = read_jsonl(f)
        if ev and ev[-1]["type"] == "end": die("the session already ended")
        score = float(a[a.index("--score") + 1]) if "--score" in a else None
        append_jsonl(f, {"ts": iso(now()), "type": "end", "reason": "completed", "score": score}); status(f); return 0
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
