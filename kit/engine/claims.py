#!/usr/bin/env python3
"""The truth rule, checked deterministically. Every line of a tailored resume and its application notes must
trace back to confirmed facts in their facts bank.
  claims.py <job-id>/v<N>
Resume (resume.json): every paragraph, bullet, skills item and certification cites fact ids; each cited fact
exists, is confirmed and isn't private; every number in the line appears in a cited fact; every acronym or capitalised
name in the line appears in a cited fact (directly or through the pack's keyword variants); skills items must be
mentioned by a cited fact. Role titles and dates come from employment.json, so they can't drift.
Notes (notes.md, optional): under "Why I fit" and "Message draft", any line with a number or a name ends with a
citation comment `<!-- facts: f-0003, f-0007 -->`, checked the same way. Under "Gaps", a line stating what they lack
needs no citation, but a cited one is checked. "Questions to ask" and "Pay" are free text.
Writes claims.json (line -> fact ids, for the claim-checker subagent) and checks.json -> claims. Exit 1 on failure.
"""
import re, sys
from _common import PROFILE, read_jsonl, load, save, read_text, die
import kw

NUM = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*")
CAP = re.compile(r"\b[A-Z][A-Za-z0-9&+/.-]*[A-Za-z0-9]|\b[A-Z]\b")
STOP = {"A", "An", "And", "The", "Of", "For", "In", "On", "To", "With", "By", "At", "As", "From", "Into", "Across", "Over", "Per",
        "I", "Led", "Built", "Owned", "Drove", "Managed", "Delivered", "Reduced", "Improved", "Raised", "Cut", "Set", "Ran"}
CITE = re.compile(r"<!--\s*facts:\s*([^>]*?)\s*-->")
FREE_SECTIONS = ("questions to ask", "pay")

def nums(text):
    return {n.replace(",", "").rstrip(".").lstrip("0") or "0" for n in NUM.findall(text or "")}

def fact_blob(f):
    parts = [f.get("text", ""), " ".join(f.get("keywords") or []), f.get("employer") or "", f.get("role") or ""]
    for m in f.get("metrics") or []: parts += [m.get("name", ""), str(m.get("value", "")), m.get("unit", ""), m.get("as_said", "")]
    per = f.get("period") or {}
    parts += [str(per.get("start") or ""), str(per.get("end") or "")]
    return " ".join(parts)

def names(text):
    toks = CAP.findall(text or "")
    first = (re.match(r"\W*([A-Za-z0-9]+)", text or "") or [None, None])[1]
    out = []
    for i, t in enumerate(toks):
        t = t.rstrip(".")
        if t in STOP or (i == 0 and t == first and not t.isupper()): continue
        if len(t) == 1: continue
        out.append(t)
    return out

def check_line(text, ids, facts, emp_text, kind="line"):
    """-> list of problems (empty = supported)."""
    probs = []
    if not ids: return ["cites no fact"]
    cited = []
    for i in ids:
        f = facts.get(i)
        if not f: probs.append(f"{i} doesn't exist"); continue
        if f.get("status") != "confirmed": probs.append(f"{i} isn't confirmed ({f.get('status')})"); continue
        if f.get("private"): probs.append(f"{i} is private"); continue
        cited.append(f)
    if probs: return probs
    blob = " ".join(fact_blob(f) for f in cited)
    missing = sorted(nums(text) - nums(blob), key=lambda x: (len(x), x))
    if missing: probs.append("numbers not in the cited facts: " + ", ".join(missing))
    unknown = [n for n in names(text) if not kw.mentions(blob, n) and not kw.mentions(emp_text, n)]
    if unknown: probs.append("names or terms not in the cited facts: " + ", ".join(dict.fromkeys(unknown)))
    if kind == "skill" and not kw.mentions(blob, text): probs.append("this skill isn't mentioned by the cited facts")
    return probs

def resume_lines(resume):
    for s in resume.get("sections", []):
        h = s.get("heading", "")
        for p in s.get("paragraphs", []): yield h, p.get("text", ""), p.get("facts") or [], "line"
        for r in s.get("roles", []):
            for b in r.get("bullets", []): yield h, b.get("text", ""), b.get("facts") or [], "line"
        for l in s.get("lines", []):
            for it in l.get("items", []): yield h, it, l.get("facts") or [], "skill"
        for x in s.get("items", []): yield h, x.get("text", ""), x.get("facts") or [], "line"

def notes_lines(text):
    section = ""
    for line in text.splitlines():
        if line.startswith("#"): section = line.lstrip("# ").strip().lower(); continue
        body = CITE.sub("", line).strip(" -*")
        if not body or any(section.startswith(s) for s in FREE_SECTIONS): continue
        m = CITE.search(line)
        ids = [x.strip() for x in m.group(1).split(",") if x.strip()] if m else []
        if ids or nums(body) or names(body): yield section, body, ids

def main(a):
    if not a: print(__doc__); return 1
    from render import version_dir
    jid, v, d = version_dir(a[0])
    resume = load(d / "resume.json")
    facts = {f["id"]: f for f in read_jsonl(PROFILE / "facts.jsonl")}
    emp = load(PROFILE / "employment.json", []) or []
    emp_text = " ".join(f"{e.get('employer', '')} {e.get('role', '')} {e.get('location', '')}" for e in emp)
    for s in resume.get("sections", []):
        for r in s.get("roles", []):
            if not (isinstance(r.get("employment_ref"), int) and 0 <= r["employment_ref"] < len(emp)): die(f"employment_ref {r.get('employment_ref')} isn't in employment.json")
    rows, mapping = [], {}
    for h, text, ids, kind in resume_lines(resume):
        probs = check_line(text, ids, facts, emp_text, kind)
        rows.append(("resume", h, text, ids, probs)); mapping[text] = ids
    notes = d / "notes.md"
    if notes.exists():
        for sec, text, ids in notes_lines(read_text(notes)):
            if sec.startswith("gaps") and not ids: continue
            probs = check_line(text, ids, facts, emp_text)
            rows.append(("notes", sec, text, ids, probs)); mapping[text] = ids
    failed = [r for r in rows if r[4]]
    save(d / "claims.json", mapping)
    checks = load(d / "checks.json", {}) or {}
    checks["claims"] = {"passed": not failed, "lines": len(rows), "failed": [{"where": f"{w}/{h}", "text": t, "problems": p} for w, h, t, _, p in failed]}
    save(d / "checks.json", checks)
    for w, h, t, ids, p in rows:
        print(f"{'FAIL' if p else 'ok  '}  {w}/{h[:14]:<14} {t[:80]}" + (f"  [{', '.join(ids)}]" if ids else "") + ("".join(f"\n        - {x}" for x in p)))
    print(f"-- {len(rows) - len(failed)}/{len(rows)} lines trace to confirmed facts" + ("" if not failed else f"; fix or drop the {len(failed)} failing line(s)"))
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
