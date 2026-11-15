#!/usr/bin/env python3
"""ATS checks.
  ats.py keywords <job-id>/v<N>     which of the JD's pack keywords the resume covers, and which are missing
  ats.py lint <file.pdf|docx> [--pages N]   layout problems an ATS trips on
  ats.py check <job-id>/v<N>        the tailoring checks /tailor loops on: the JD's exact spellings (the pack's keyword
                                    map is the alias table; a JD's lower-case slip never beats the proper name), the
                                    keyword score, no headline title they never held, one bullet per fact, no term
                                    twice in Skills, a minimum of bullets per role, and plain wording (no stock AI
                                    phrases). Numbers and claims are claims.py's job; the page limit is render.py's
DOCX lint: no tables, text boxes, images, multi-column sections, or text in headers/footers; only Word's built-in
styles (Title, Heading 1, List Bullet, Normal). PDF lint: real extractable text, embedded fonts, page limit.
"""
import json, pathlib, re, sys
from _common import HOME, DATA, PROFILE, load, die, save
import kw

ALLOWED_STYLES = {"Title", "Heading 1", "List Bullet", "Normal"}

def lint_docx(p):
    import docx
    from docx.oxml.ns import qn
    d, probs = docx.Document(str(p)), []
    if d.tables: probs.append(f"{len(d.tables)} table(s)")
    body = d.element.body
    if body.findall(".//" + qn("w:txbxContent")): probs.append("text boxes")
    if body.findall(".//" + qn("w:drawing")) or d.inline_shapes: probs.append("images or drawings")
    for s in d.sections:
        cols = s._sectPr.find(qn("w:cols"))
        if cols is not None and int(cols.get(qn("w:num"), "1")) > 1: probs.append("a multi-column section")
        for hf in (s.header, s.footer):
            if any(par.text.strip() for par in hf.paragraphs): probs.append("text in a page header or footer")
    styles = {par.style.name for par in d.paragraphs}
    if styles - ALLOWED_STYLES: probs.append(f"non-standard styles {sorted(styles - ALLOWED_STYLES)}")
    return {"pages": None, "problems": probs}

def lint_pdf(p, limit):
    from pypdf import PdfReader
    r, probs = PdfReader(str(p)), []
    text = "\n".join(pg.extract_text() or "" for pg in r.pages)
    if len(text.strip()) < 200: probs.append("hardly any extractable text (an ATS would see an image)")
    if limit and len(r.pages) > limit: probs.append(f"{len(r.pages)} pages, over the {limit}-page limit: trim bullets")
    for pg in r.pages:
        fonts = ((pg.get("/Resources") or {}).get("/Font") or {})
        for f in fonts.values():
            f = f.get_object()
            desc = f.get("/FontDescriptor")
            if desc is None and f.get("/DescendantFonts"): desc = f["/DescendantFonts"][0].get_object().get("/FontDescriptor")
            desc = desc.get_object() if desc is not None else {}
            if not any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3")): probs.append(f"font {f.get('/BaseFont')} not embedded"); break
    return {"pages": len(r.pages), "problems": sorted(set(probs))}

def lint(p, limit=2):
    p = pathlib.Path(p)
    return lint_docx(p) if p.suffix.lower() == ".docx" else lint_pdf(p, limit)

def resume_text(resume):
    emp = load(PROFILE / "employment.json", []) or []
    parts = []
    for s in resume.get("sections", []):
        parts += [p["text"] for p in s.get("paragraphs", [])] + [x["text"] for x in s.get("items", [])]
        for r in s.get("roles", []):
            i = r.get("employment_ref")
            if isinstance(i, int) and 0 <= i < len(emp): parts.append(emp[i]["role"])
            parts += [b["text"] for b in r.get("bullets", [])]
        for l in s.get("lines", []): parts += l["items"]
    return "\n".join(parts)

def keywords(ref):
    from render import version_dir
    from jobs import load_jobs, find, jd_text_of
    jid, v, d = version_dir(ref)
    job = find(load_jobs()["jobs"], jid) or die(f"no job {jid}")
    jd = jd_text_of(job) or die(f"{jid} has no saved JD")
    need, have = kw.find(jd), kw.find(resume_text(load(d / "resume.json")))
    covered = sorted(set(need) & set(have)); missing = sorted(set(need) - set(have))
    checks = load(d / "checks.json", {}) or {}
    checks["ats"] = {"covered": [need[k] for k in covered], "missing": [need[k] for k in missing]}
    save(d / "checks.json", checks)
    print(f"JD keywords covered ({len(covered)}/{len(need)}): " + (", ".join(need[k] for k in covered) or "none"))
    print(f"Missing ({len(missing)}): " + (", ".join(need[k] for k in missing) or "none"))
    if missing: print("Add a missing keyword only where a confirmed fact supports it; otherwise it's a gap for the notes.")
    return 0

# ---------------------------------------------------------------- the tailoring check loop
BANNED = ["spearhead", "spearheaded", "spearheading", "orchestrated", "orchestrating", "synergy", "synergize", "synergized", "leverage",
          "leveraged", "leveraging", "utilize", "utilized", "utilizing", "utilise", "utilised", "delve", "delved", "delving", "testament",
          "pivotal", "paramount", "cutting-edge", "state-of-the-art", "seamless", "seamlessly", "robust", "transformative", "passionate",
          "results-driven", "meticulous", "meticulously", "fostered", "fostering", "harnessed", "harnessing", "worked on", "helped",
          "assisted", "responsible for", "various", "innovative", "world-class", "best-in-class", "game-changing"]
TAIL = re.compile(r",\s+(resulting in|leading to|thereby|ensuring|enabling|culminating in)\b", re.I)
MIN_BULLETS = 1

def spellings(jd, text):
    """[(JD spelling, resume spelling)] where they name one term differently and the JD's spelling is the proper one."""
    out = []
    for t in kw.terms():
        rx = kw._rx(t)
        a, b = rx.search(jd or ""), rx.search(text or "")
        if not (a and b): continue
        js, rs = a.group(0), b.group(0)
        if js == rs or js.lower() == js and rs.lower() != rs: continue   # same, or the JD slipped into lower case
        if rs in (jd or ""): continue   # the JD uses their spelling too
        short_alias = js == t["canonical"] and len(rs) <= 5 and len(js) > len(rs)   # K8s for Kubernetes, JS for JavaScript
        if js.lower() == rs.lower() or short_alias: out.append((js, rs))   # a different tool under the same term is not a spelling
    return out

def held_titles():
    from fit import _expand, YEARS
    return [_expand(YEARS.sub(" ", e.get("role", ""))) for e in load(PROFILE / "employment.json", []) or []]

def headline_problem(resume, job):
    """The summary must not present the JD's title as theirs unless they held it."""
    from fit import _expand, level_of
    summary = " ".join(p["text"] for s in resume.get("sections", []) for p in s.get("paragraphs", []))
    core = re.sub(r"\s+", " ", re.split(r"\s+[-–|,(]\s*|\s*\(", job["title"])[0]).strip()
    if not core or not re.search(rf"(?i)\b{re.escape(core)}\b", summary): return None
    if any(_expand(core) in h or h in _expand(core) for h in held_titles()): return None
    return f"the summary calls them a '{core}', a title they never held: describe the work instead"

def wording(lines):
    probs = []
    body = "\n".join(lines)
    for w in BANNED:
        for m in re.finditer(rf"(?i)(?<![-\w]){re.escape(w)}\b", body): probs.append(f"stock wording '{m.group(0)}': say what was done, plainly")
    if sum(1 for l in lines if TAIL.search(l)) > 1: probs.append("more than one bullet ends on ', resulting in / leading to / ensuring ...'")
    if body.count("—") > 1: probs.append(f"{body.count('—')} em dashes (one at most): use a colon, a comma or a full stop")
    return probs

def builder(resume):
    probs = []
    prefs = load(PROFILE / "resume_prefs.json", {}) or {}
    least = int(prefs.get("min_bullets", MIN_BULLETS))
    seen = {}
    for s in resume.get("sections", []):
        for r in s.get("roles", []):
            if len(r.get("bullets", [])) < least: probs.append(f"{s['heading']}: a role has fewer than {least} bullet(s)")
            for b in r.get("bullets", []):
                key = tuple(sorted(b.get("facts") or []))
                if len(key) == 1 and key in seen: probs.append(f"two bullets rest on the same single fact {key[0]}: one bullet per fact")
                seen[key] = True
        items = [i.strip().lower() for l in s.get("lines", []) for i in l.get("items", [])]
        dup = sorted({i for i in items if items.count(i) > 1})
        if dup: probs.append(f"{s['heading']}: listed twice: {', '.join(dup)}")
    return probs

def check(ref):
    from render import version_dir
    from jobs import load_jobs, find, jd_text_of
    jid, v, d = version_dir(ref)
    job = find(load_jobs()["jobs"], jid) or die(f"no job {jid}")
    jd = jd_text_of(job) or die(f"{jid} has no saved JD")
    resume = load(d / "resume.json")
    text = resume_text(resume)
    lines = [b["text"] for s in resume.get("sections", []) for r in s.get("roles", []) for b in r.get("bullets", [])]
    lines += [p["text"] for s in resume.get("sections", []) for p in s.get("paragraphs", [])]
    probs = [f"use the JD's spelling '{a}' (the resume says '{b}')" for a, b in spellings(jd, text)]
    h = headline_problem(resume, job)
    if h: probs.append(h)
    probs += builder(resume) + wording(lines)
    need, have = kw.find(jd), kw.find(text)
    score = round(100 * len(set(need) & set(have)) / len(need)) if need else 100
    checks = load(d / "checks.json", {}) or {}
    checks["tailor"] = {"passed": not probs, "keyword_score": score, "problems": probs}
    save(d / "checks.json", checks)
    print(f"keyword score: {score}% of the JD's terms" + ("" if score >= 60 else " (low: add only what a confirmed fact supports)"))
    print("tailoring checks: OK" if not probs else "fix these, then check again:\n- " + "\n- ".join(probs))
    return 0 if not probs else 1

def main(a):
    if len(a) >= 2 and a[0] == "keywords": return keywords(a[1])
    if len(a) >= 2 and a[0] == "check": return check(a[1])
    if len(a) >= 2 and a[0] == "lint":
        lim = int(a[a.index("--pages") + 1]) if "--pages" in a else 2
        r = lint(a[1], lim)
        print("ATS lint: OK" + (f" ({r['pages']} page(s))" if r["pages"] else "") if not r["problems"] else "ATS lint problems:\n- " + "\n- ".join(r["problems"]))
        return 0 if not r["problems"] else 1
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
