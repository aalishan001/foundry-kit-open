#!/usr/bin/env python3
"""Is everything set up? Plain-words checklist; every problem comes with its fix.
  doctor.py           full check (renders a test page, checks history)
  doctor.py --quick   the fast checks every command runs first
Exit 1 when something needs action.
"""
import importlib, os, pathlib, shutil, subprocess, sys, tempfile
from _common import HOME, KIT, PROFILE, kit_path

results = []
def ok(msg): results.append(("OK", msg))
def bad(msg, fix): results.append(("ACTION NEEDED", f"{msg}. Fix: {fix}"))
def note(msg): results.append(("NOTE", msg))

def check_python():
    v = sys.version_info
    if v >= (3, 10): ok(f"Python {v.major}.{v.minor}")
    else: bad(f"Python {v.major}.{v.minor} is too old", "run setup.cmd (it installs Python 3.12)")
    if "WindowsApps" in sys.executable: bad("Python is the Microsoft Store placeholder", "run setup.cmd")

def check_packages():
    for mod, pkg in (("typst", "typst"), ("docx", "python-docx"), ("pypdf", "pypdf"), ("keyring", "keyring")):
        try: importlib.import_module(mod); ok(f"{pkg} installed")
        except ImportError: bad(f"{pkg} is missing", "run setup.cmd")

def check_sources():
    """Optional sources: Gmail label, API keys, the morning sweep. Notes only, never ACTION NEEDED unless broken."""
    import secrets_store as vault
    from _common import search_rules
    try: vault.get("probe")
    except vault.Missing as e: bad(str(e), "run setup.cmd"); return
    g = search_rules().get("gmail") or {}
    if g.get("enabled"):
        if vault.has("gmail_app_password"): ok(f"Gmail: reading the {g.get('label', 'Job Alerts')!r} label (read-only)")
        else: bad("Gmail is on but its app password is missing", "double-click Gmail setup.cmd")
    else: note("Gmail: off (optional: Gmail setup.cmd; until then paste alert emails into /sweep)")
    import keys
    have = [a for a in keys.APIS if keys.stored(a)]
    note(f"job-search APIs: {', '.join(have)}" if have else "job-search APIs: none (optional: API keys.cmd)")
    if os.name == "nt":
        import schedule
        p = schedule.schtasks("/Query", "/TN", schedule.task_name())
        if p.returncode == 0: ok("morning sweep is scheduled")
        else: note("morning sweep isn't scheduled: run setup.cmd again to turn it on (or use /sweep by hand)")

def check_folder():
    try:
        with tempfile.NamedTemporaryFile(dir=HOME, prefix=".write-test-", delete=True): pass
        ok("folder is writable")
    except OSError as e: bad(f"can't write in this folder ({e.strerror})", "move the folder somewhere you own, such as Documents or OneDrive")
    p = str(HOME).lower()
    synced = any(s in p for s in ("onedrive", "google drive", "my drive", "googledrive")) or (os.environ.get("OneDrive") and str(HOME).startswith(os.environ["OneDrive"]))
    if synced: ok("folder is inside OneDrive or Google Drive (backed up)")
    else: note("this folder isn't inside OneDrive or Google Drive, so it isn't backed up off this computer")

def check_profile():
    p = subprocess.run([sys.executable, str(KIT / "engine" / "validate.py"), "--quiet"], capture_output=True, text=True, encoding="utf-8",
                       env=dict(os.environ, FOUNDRY_HOME=str(HOME)))
    if p.returncode == 0: ok("profile and records are valid")
    else: bad("some records don't pass validation:\n    " + p.stdout.strip().replace("\n", "\n    "), "tell Claude to fix the records listed")
    if not (PROFILE / "search.json").exists(): note("profile not started yet: type /start")

def check_pack():
    p = subprocess.run([sys.executable, str(KIT / "engine" / "pack_check.py"), "--quiet"], capture_output=True, text=True, encoding="utf-8",
                       env=dict(os.environ, FOUNDRY_HOME=str(HOME)))
    if p.returncode == 0: ok("domain pack is valid")
    else: bad("the domain pack has problems:\n    " + p.stdout.strip().replace("\n", "\n    "), "reinstall the kit (unzip it again over this folder)")

def check_fonts():
    if os.name != "nt": note("not Windows: resume font falls back to a bundled one"); return
    if (pathlib.Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arial.ttf").exists(): ok("Arial font present")
    else: bad("Arial font missing", "the resume will use a fallback font; tell the person who set this up")

def check_render():
    try:
        import typst
        with tempfile.TemporaryDirectory() as d:
            src = pathlib.Path(d) / "t.typ"; src.write_text('#set text(font: ("Arial", "Liberation Sans"))\nTest page', encoding="utf-8")
            typst.compile(str(src), output=str(pathlib.Path(d) / "t.pdf"))
            assert (pathlib.Path(d) / "t.pdf").stat().st_size > 0
        ok("PDF rendering works")
    except Exception as e: bad(f"PDF rendering failed ({type(e).__name__}: {str(e)[:120]})", "run setup.cmd again")
    try:
        import docx
        with tempfile.TemporaryDirectory() as d:
            doc = docx.Document(); doc.add_paragraph("Test"); doc.save(str(pathlib.Path(d) / "t.docx"))
        ok("DOCX rendering works")
    except Exception as e: bad(f"DOCX rendering failed ({type(e).__name__})", "run setup.cmd again")

def check_git():
    if not shutil.which("git"): bad("git isn't installed, so your history isn't kept", "run setup.cmd"); return
    if not (HOME / ".git").is_dir(): bad("history isn't started", "run: python engine/backup.py init"); return
    p = subprocess.run(["git", "-C", str(HOME), "fsck", "--no-progress"], capture_output=True, text=True)
    if p.returncode == 0: ok("history (backup) intact")
    else: bad("the history folder (.git) is damaged; your files are fine", "tell the person who set this up")

def check_upgrade():
    """After a new release is unzipped over their folder, bring their records to the new shape (idempotent)."""
    import upgrade
    if not upgrade.needed(): return
    try: upgrade.run(quiet=True)
    except SystemExit: bad(f"updating your records to kit {upgrade.kit_version()} stopped", "tell the person who set this up")

def main(a):
    quick = "--quick" in a
    check_upgrade()
    check_python(); check_packages(); check_folder(); check_profile()
    if not quick: check_pack(); check_fonts(); check_render(); check_git(); check_sources()
    need = [r for r in results if r[0] == "ACTION NEEDED"]
    if quick and not need: print("setup OK"); return 0
    for k, m in results: print(f"{k:<14} {m}")
    print("\nAll set." if not need else f"\n{len(need)} thing(s) need action (above).")
    return 1 if need else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
