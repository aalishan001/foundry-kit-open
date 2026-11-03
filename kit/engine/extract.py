#!/usr/bin/env python3
"""Read documents they drop in inbox/, and file them away afterwards.
  extract.py text <file> [--out <file>]   plain text of a PDF, DOCX, TXT, MD or EML file
  extract.py inbox                         what's waiting in inbox/
  extract.py archive <file>                move a processed inbox file to archive/<YYYYMMDD-HHMM>-<name>; prints the path
"""
import email, email.policy, pathlib, shutil, sys
from _common import INBOX, ARCHIVE, die, ts_name, rel, read_text

def pdf_text(p):
    from pypdf import PdfReader
    return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)

def docx_text(p):
    import docx
    d = docx.Document(str(p))
    out = [para.text for para in d.paragraphs]
    for t in d.tables:
        for row in t.rows: out.append(" | ".join(c.text for c in row.cells))
    return "\n".join(out)

def eml_text(p):
    msg = email.message_from_bytes(pathlib.Path(p).read_bytes(), policy=email.policy.default)
    from html_text import to_text
    parts = []
    for part in msg.walk():
        ct = part.get_content_type()
        if ct == "text/plain": parts.append(part.get_content())
        elif ct == "text/html": parts.append(to_text(part.get_content()))
    return f"Subject: {msg.get('subject', '')}\nFrom: {msg.get('from', '')}\n\n" + "\n".join(parts)

def text_of(p):
    p = pathlib.Path(p)
    if not p.is_file(): die(f"no file {p}")
    ext = p.suffix.lower()
    if ext == ".pdf": return pdf_text(p)
    if ext == ".docx": return docx_text(p)
    if ext == ".eml": return eml_text(p)
    if ext in (".txt", ".md", ".html", ".htm"):
        t = read_text(p)
        if ext in (".html", ".htm"):
            from html_text import to_text
            t = to_text(t)
        return t
    if ext == ".doc": die(f"{p.name} is an old Word .doc: open it in Word or Google Docs and save it as .docx or PDF")
    die(f"can't read {p.suffix} files: save it as PDF, DOCX or TXT")

def main(a):
    if not a: print(__doc__); return 1
    if a[0] == "text" and len(a) > 1:
        t = text_of(a[1])
        if "--out" in a:
            o = pathlib.Path(a[a.index("--out") + 1]); o.parent.mkdir(parents=True, exist_ok=True)
            o.write_text(t, encoding="utf-8", newline="\n"); print(f"{len(t)} characters -> {rel(o)}")
        else: print(t)
        return 0
    if a[0] == "inbox":
        files = sorted(p for p in INBOX.glob("*") if p.is_file() and not p.name.startswith((".", "~$")))
        print("\n".join(f"{p.name}  ({p.stat().st_size // 1024} KB)" for p in files) or "inbox is empty")
        return 0
    if a[0] == "archive" and len(a) > 1:
        p = pathlib.Path(a[1]); p = p if p.is_absolute() else INBOX / p.name if not p.exists() else p
        if not p.is_file(): die(f"no file {a[1]}")
        dest = ARCHIVE / f"{ts_name()}-{p.name}"
        ARCHIVE.mkdir(parents=True, exist_ok=True); shutil.move(str(p), str(dest))
        print(rel(dest)); return 0
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
