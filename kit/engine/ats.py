#!/usr/bin/env python3
"""ATS checks.
  ats.py keywords <job-id>/v<N>     which of the JD's pack keywords the resume covers, and which are missing
  ats.py lint <file.pdf|docx> [--pages N]   layout problems an ATS trips on
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

def main(a):
    if len(a) >= 2 and a[0] == "keywords": return keywords(a[1])
    if len(a) >= 2 and a[0] == "lint":
        lim = int(a[a.index("--pages") + 1]) if "--pages" in a else 2
        r = lint(a[1], lim)
        print("ATS lint: OK" + (f" ({r['pages']} page(s))" if r["pages"] else "") if not r["problems"] else "ATS lint problems:\n- " + "\n- ".join(r["problems"]))
        return 0 if not r["problems"] else 1
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
