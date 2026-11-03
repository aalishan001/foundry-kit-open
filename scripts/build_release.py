#!/usr/bin/env python3
"""Build a release: a zip of kit/ that a user extracts into their job-search folder. Refuses on any leak-scan hit.
  build_release.py [--kit <dir>] [--out <dir>] [--skip-tests] [--rc]
--rc builds a release candidate for maintainers' dry runs: foundry-kit-<version>-rc.zip, allowed while the
measured OpenCode cost table is still a placeholder. Never hand an -rc zip to a user.
Steps: unit tests (unless --skip-tests); leak scan of the kit at kit scope with --require-denylist, plus the test
install's profile terms (path from ~/.foundry-kit/dev.json); a staging copy without caches; docs/SETUP.md rendered
to "Start here.pdf"; a structure check (no personal folders, the profile skeleton only); the zip; a second leak scan
of the zip itself. Output: <out>/foundry-kit-<version>.zip (default out: dist/).
"""
import json, os, pathlib, re, shutil, subprocess, sys, tempfile, zipfile

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCAN = ROOT / "scripts" / "leak_scan.py"
DEV = pathlib.Path(os.environ.get("FOUNDRY_DEV_CONFIG") or pathlib.Path.home() / ".foundry-kit" / "dev.json")
SKIP = {"__pycache__", ".pytest_cache"}
FORBIDDEN_TOP = {"data", "inbox", "archive", "Resumes", "seed", ".git"}

def fail(msg): print(f"RELEASE REFUSED: {msg}"); sys.exit(1)

def opt(a, flag, default=None): return a[a.index(flag) + 1] if flag in a and a.index(flag) + 1 < len(a) else default

def profile_args():
    try: ti = json.loads(DEV.read_text(encoding="utf-8")).get("test_install")
    except (OSError, json.JSONDecodeError): return []
    p = pathlib.Path(ti) / "profile" if ti else None
    return ["--profile", str(p)] if p and p.is_dir() else []

def scan(target, extra=()):
    p = subprocess.run([sys.executable, str(SCAN), str(target), "--scope", "kit", "--require-denylist", *profile_args(), *extra],
                       capture_output=True, text=True, encoding="utf-8")
    print(p.stdout.strip().splitlines()[-1] if p.stdout.strip() else p.stderr.strip())
    if p.returncode != 0: fail("leak scan:\n" + (p.stdout + p.stderr).strip())

def md_blocks(md):
    """Enough Markdown for the setup guide: headings, numbered and bulleted lists, paragraphs, **bold**, `code`."""
    blocks, para = [], []
    def flush():
        if para: blocks.append({"t": "p", "x": " ".join(para)}); para.clear()
    for line in md.splitlines():
        s = line.strip()
        if not s: flush(); continue
        m = re.match(r"^(#{1,3})\s+(.*)", s)
        if m: flush(); blocks.append({"t": f"h{len(m.group(1))}", "x": m.group(2)}); continue
        m = re.match(r"^(\d+)\.\s+(.*)", s) or re.match(r"^[-*]\s+(.*)", s)
        if m and not line.startswith("   "):
            flush(); blocks.append({"t": "li" if s[0] in "-*" else "ol", "x": m.group(m.lastindex)}); continue
        if blocks and blocks[-1]["t"] in ("li", "ol") and not para and line.startswith("   "): blocks[-1]["x"] += " " + s; continue
        para.append(s)
    flush()
    return blocks

TYP = r'''#let b = json("doc.json")
#set page(paper: "a4", margin: 18mm)
#set text(font: ("Arial", "Liberation Sans"), size: 10.5pt, hyphenate: false)
#let inline(s) = {
  let parts = s.split("**")
  for (i, p) in parts.enumerate() {
    let q = p.split("`").enumerate().map(((j, x)) => if calc.odd(j) { raw(x) } else { x }).join()
    if calc.odd(i) { strong(q) } else { q }
  }
}
#for x in b {
  if x.t == "h1" { text(size: 18pt, weight: "bold", inline(x.x)); v(4pt) }
  else if x.t == "h2" { v(6pt); text(size: 12.5pt, weight: "bold", inline(x.x)); v(2pt) }
  else if x.t == "h3" { text(weight: "bold", inline(x.x)) }
  else if x.t == "li" { list(inline(x.x)) }
  else if x.t == "ol" { enum(inline(x.x)) }
  else { par(inline(x.x)) }
}
'''

def render_setup_pdf(md_path, out):
    import typst
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / "doc.json").write_text(json.dumps(md_blocks(md_path.read_text(encoding="utf-8")), ensure_ascii=False), encoding="utf-8")
        (d / "doc.typ").write_text(TYP, encoding="utf-8")
        typst.compile(str(d / "doc.typ"), output=str(out), root=str(d))

def structure(stage, rc=False):
    top = {p.name for p in stage.iterdir()}
    bad = top & FORBIDDEN_TOP
    if bad: fail(f"personal or dev folders in the release: {sorted(bad)}")
    prof = sorted(p.name for p in (stage / "profile").iterdir()) if (stage / "profile").is_dir() else []
    if prof != ["README.md"]: fail(f"profile/ must hold only the README skeleton, found {prof}")
    for need in ("CLAUDE.md", "setup.cmd", "setup.ps1", "VERSION", ".claude/settings.json", "engine/doctor.py", "docs/COMMANDS.md", "Start here.pdf"):
        if not (stage / need).exists(): fail(f"missing {need}")
    for need in ("AGENTS.md", "opencode.json", "OpenCode.cmd", ".opencode/agents/claim-checker.md"):
        if not (stage / need).exists(): fail(f"missing {need} (the OpenCode target)")
    for md in (stage / "docs").glob("*.md"):
        if "COSTS_TABLE" in md.read_text(encoding="utf-8") and not rc:
            fail(f"docs/{md.name} still has the COSTS_TABLE placeholder: fill it from the measured costs")

def main(a):
    kit = pathlib.Path(opt(a, "--kit", ROOT / "kit")).resolve()
    out_dir = pathlib.Path(opt(a, "--out", ROOT / "dist")).resolve()
    version = (kit / "VERSION").read_text(encoding="utf-8").strip()
    if "--skip-tests" not in a:
        p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests")], capture_output=True, text=True, encoding="utf-8")
        tail = (p.stdout + p.stderr).strip().splitlines()[-1]
        print(f"tests: {tail}")
        if p.returncode != 0: fail("tests fail:\n" + (p.stdout + p.stderr)[-3000:])
    scan(kit)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        stage = pathlib.Path(tmp) / f"foundry-kit-{version}"
        shutil.copytree(kit, stage, ignore=shutil.ignore_patterns(*SKIP, "*.pyc", "*.tmp"))
        render_setup_pdf(stage / "docs" / "SETUP.md", stage / "Start here.pdf")
        structure(stage, rc="--rc" in a)
        z = out_dir / f"foundry-kit-{version}{'-rc' if '--rc' in a else ''}.zip"
        if z.exists(): z.unlink()
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(stage.rglob("*")):
                if p.is_file(): zf.write(p, p.relative_to(stage).as_posix())
    scan(z)
    with zipfile.ZipFile(z) as zf: n = len(zf.namelist())
    print(f"release: {z.relative_to(ROOT) if z.is_relative_to(ROOT) else z}  ({n} files, {z.stat().st_size // 1024} KB)")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
