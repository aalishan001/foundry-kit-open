#!/usr/bin/env python3
"""Render a tailored resume to PDF (Typst) and/or DOCX (python-docx) from one content source, then prove the two
hold the same text and pass the ATS lint.
  render.py <job-id>/v<N> [--format pdf,docx]
Reads data/tailored/<job-id>/v<N>/resume.json plus profile/identity.json, employment.json, education.json and
resume_prefs.json. Writes the files into that version's folder (logged in data/renders.jsonl with their hash, so
jobs.py applied --tailored can link the one they send) and copies the latest into Resumes/<Company> - <Role>/.
Run claims.py first: render refuses a version whose claim check hasn't passed.
"""
import hashlib, json, pathlib, re, shutil, sys, tempfile, unicodedata
from _common import HOME, PROFILE, DATA, RESUMES, load, die, stamp, append_jsonl, rel, safe_name, opt, kit_path
from jobs import load_jobs, find

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

def ym(s):
    if not s: return "Present"
    y, m = str(s).split("-")[:2]
    return f"{MONTHS[int(m) - 1]} {y}"

def span(a, b): return f"{ym(a)} – {ym(b)}" if a else (ym(b) if b else "")

def version_dir(ref):
    if "/v" not in ref: die("give the version as <job-id>/v<N>, e.g. j-0007/v2")
    jid, v = ref.split("/v", 1)
    d = DATA / "tailored" / jid / f"v{v}"
    if not (d / "resume.json").is_file(): die(f"no {rel(d / 'resume.json')}")
    return jid, int(v), d

def contact_line(identity, wanted):
    vals = {"email": identity.get("email"), "phone": identity.get("phone"),
            "linkedin": re.sub(r"^https?://(www\.)?", "", (identity.get("links") or {}).get("linkedin") or "").rstrip("/"),
            "city": ", ".join(x for x in ((identity.get("location") or {}).get("city"), (identity.get("location") or {}).get("state")) if x)}
    for o in (identity.get("links") or {}).get("other") or []:
        vals[o.get("label", "").lower()] = re.sub(r"^https?://(www\.)?", "", o.get("url", "")).rstrip("/")
    order = [w for w in wanted if w == "city"] + [w for w in wanted if w != "city"]
    return " | ".join(vals[w] for w in order if vals.get(w))

def build_model(resume, job):
    ident = load(PROFILE / "identity.json", {}) or {}
    emp = load(PROFILE / "employment.json", []) or []
    edu = load(PROFILE / "education.json", []) or []
    name = (ident.get("name") or {}).get("resume") or (ident.get("name") or {}).get("full")
    if not name: die("their name isn't in profile/identity.json yet (/start, identity stage)")
    prefs = load(PROFILE / "resume_prefs.json", {}) or {}
    wanted = (resume.get("header") or {}).get("contacts") or prefs.get("contacts") or ["email", "phone", "linkedin", "city"]
    sections = []
    for s in resume.get("sections", []):
        blocks = []
        for p in s.get("paragraphs", []): blocks.append({"type": "para", "text": p["text"]})
        for r in s.get("roles", []):
            i = r.get("employment_ref")
            if not isinstance(i, int) or not 0 <= i < len(emp): die(f"section {s['heading']}: employment_ref {i} isn't in employment.json")
            e = emp[i]
            meta = " | ".join(x for x in (span(e.get("start"), e.get("end")), e.get("location") or "") if x)
            blocks.append({"type": "role", "head": f"{e['role']}, {e['employer']}", "meta": meta, "bullets": [b["text"] for b in r.get("bullets", [])]})
        for l in s.get("lines", []): blocks.append({"type": "line", "label": l["label"], "text": ", ".join(l["items"])})
        if s.get("items"): blocks.append({"type": "bullets", "items": [x["text"] for x in s["items"]]})
        if s.get("from") == "education.json":
            for e in edu:
                meta = " | ".join(x for x in (span(e.get("start"), e.get("end")) if e.get("end") or e.get("start") else "", e.get("grade") or "") if x)
                blocks.append({"type": "role", "head": f"{e['degree']}, {e['institution']}", "meta": meta, "bullets": []})
        sections.append({"heading": s["heading"], "blocks": blocks})
    return {"name": name, "contact": contact_line(ident, wanted), "title": f"{name} – Resume – {job['title']}", "sections": sections}

# ---------------------------------------------------------------- renderers
def render_pdf(model, out):
    import typst
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / "model.json").write_text(json.dumps(model, ensure_ascii=False), encoding="utf-8")
        shutil.copy(kit_path("templates", "resume.typ"), d / "resume.typ")
        typst.compile(str(d / "resume.typ"), output=str(out), root=str(d))

def render_docx(model, out):
    import docx
    from docx.shared import Pt, Mm, RGBColor
    doc = docx.Document()
    sec = doc.sections[0]
    sec.page_height, sec.page_width = Mm(297), Mm(210)
    sec.left_margin = sec.right_margin = Mm(16); sec.top_margin = sec.bottom_margin = Mm(14)
    for st, size, bold in (("Normal", 10.5, False), ("Title", 17, True), ("Heading 1", 11.5, True), ("List Bullet", 10.5, False)):
        f = doc.styles[st].font; f.name, f.size, f.bold, f.color.rgb = "Arial", Pt(size), bold, RGBColor(0, 0, 0)
        rpr = doc.styles[st].element.get_or_add_rPr(); fonts = rpr.find(docx.oxml.ns.qn("w:rFonts"))
        if fonts is None: fonts = docx.oxml.OxmlElement("w:rFonts"); rpr.append(fonts)
        for k in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"): fonts.set(docx.oxml.ns.qn(k), "Arial")
    doc.add_paragraph(model["name"], style="Title")
    doc.add_paragraph(model["contact"], style="Normal")
    for s in model["sections"]:
        doc.add_paragraph(s["heading"], style="Heading 1")
        for b in s["blocks"]:
            if b["type"] == "para": doc.add_paragraph(b["text"], style="Normal")
            elif b["type"] == "role":
                p = doc.add_paragraph(style="Normal"); p.add_run(b["head"]).bold = True
                if b["meta"]: p.add_run(" | " + b["meta"])
                for x in b["bullets"]: doc.add_paragraph(x, style="List Bullet")
            elif b["type"] == "bullets":
                for x in b["items"]: doc.add_paragraph(x, style="List Bullet")
            elif b["type"] == "line":
                p = doc.add_paragraph(style="Normal"); p.add_run(b["label"] + ":").bold = True; p.add_run(" " + b["text"])
    doc.core_properties.title, doc.core_properties.author = model["title"], model["name"]
    doc.save(str(out))

# ---------------------------------------------------------------- parity
def words(text):
    t = unicodedata.normalize("NFKC", text).lower()
    t = re.sub(r"[•●▪◦·–—|]", " ", t)
    t = re.sub(r"/\s+", "/", t)   # a line may break after a slash in the PDF ("CI/ CD")
    return re.findall(r"[\w%₹.+/&@:-]+", t)

def pdf_words(p):
    from pypdf import PdfReader
    return words("\n".join(pg.extract_text() or "" for pg in PdfReader(str(p)).pages))

def docx_words(p):
    import docx
    return words("\n".join(para.text for para in docx.Document(str(p)).paragraphs))

def model_words(model):
    parts = [model["name"], model["contact"]]
    for s in model["sections"]:
        parts.append(s["heading"])
        for b in s["blocks"]:
            if b["type"] == "para": parts.append(b["text"])
            elif b["type"] == "role": parts += [b["head"], b["meta"]] + b["bullets"]
            elif b["type"] == "bullets": parts += b["items"]
            elif b["type"] == "line": parts += [b["label"] + ":", b["text"]]
    return words("\n".join(parts))

def first_diff(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y: return i, " ".join(a[max(0, i - 4):i + 4]), " ".join(b[max(0, i - 4):i + 4])
    i = min(len(a), len(b))
    return i, " ".join(a[i - 4:i + 4]), " ".join(b[i - 4:i + 4])

def parity(model, files):
    want = [w.strip(".:") for w in model_words(model)]
    out = {}
    for fmt, p in files.items():
        got = [w.strip(".:") for w in (pdf_words(p) if fmt == "pdf" else docx_words(p))]
        got, ref = [w for w in got if w], [w for w in want if w]
        if got == ref: out[fmt] = "same words, same order"
        else:
            i, x, y = first_diff(ref, got)
            out[fmt] = f"DIFFERS at word {i}: expected '{x}' / got '{y}'"
    return out

# ---------------------------------------------------------------- main
def main(a):
    if not a or a[0].startswith("-"): print(__doc__); return 1
    jid, v, d = version_dir(a[0])
    resume = load(d / "resume.json")
    checks = load(d / "checks.json", {}) or {}
    if (checks.get("claims") or {}).get("passed") is not True: die(f"run claims.py {a[0]} first: every line must trace to a confirmed fact")
    job = find(load_jobs()["jobs"], jid) or die(f"no job {jid}")
    prefs = load(PROFILE / "resume_prefs.json", {}) or {}
    fmts = (opt(a, "--format") or ",".join(resume.get("format") or prefs.get("format") or ["pdf", "docx"])).split(",")
    if not set(fmts) <= {"pdf", "docx"}: die("--format is pdf, docx or pdf,docx")
    model = build_model(resume, job)
    stem = safe_name(model["name"]).replace(" ", "_") + "_Resume"
    files = {}
    for f in fmts:
        out = d / f"{stem}.{f}"
        (render_pdf if f == "pdf" else render_docx)(model, out)
        files[f] = out
    import ats
    limit = int(resume.get("page_limit") or prefs.get("page_limit") or 2)
    lint = {f: ats.lint(p, limit) for f, p in files.items()}
    par = parity(model, files)
    checks["render"] = {"ts": stamp(), "formats": fmts, "parity": par, "lint": lint}
    from _common import save
    save(d / "checks.json", checks)
    bad = [f"{f}: {m}" for f, m in par.items() if m.startswith("DIFFERS")] + [f"{f}: {x}" for f, l in lint.items() for x in l["problems"]]
    if bad: print("RENDER PROBLEMS:\n- " + "\n- ".join(bad)); return 1
    dest = RESUMES / safe_name(f"{job['company']} - {job['title']}")
    dest.mkdir(parents=True, exist_ok=True)
    for f, p in files.items():
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        append_jsonl(DATA / "renders.jsonl", {"ts": stamp(), "job": jid, "version": v, "format": f, "file": rel(p), "sha256": h})
        shutil.copyfile(p, dest / p.name)
        pages = f"{lint[f]['pages']} page(s); " if lint[f]["pages"] else ""
        print(f"{f.upper()}: {rel(dest / p.name)}  ({pages}parity: {par[f]}; ATS lint: OK)")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
