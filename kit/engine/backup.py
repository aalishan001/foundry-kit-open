#!/usr/bin/env python3
"""Local history of their profile and records: a git repository in their folder, no remote, no account.
Tracks profile/ and data/, except data/cache/ and data/tmp/ (regenerable).
  backup.py init                 create the repository (safe to re-run)
  backup.py commit "<message>"   record what changed; prints the short id, or that nothing changed
  backup.py log [<path>] [-n N]  recent history (of one file)
  backup.py show <rev> <path>    a file as it was at that point (print only; restoring is a normal edit)
  backup.py check                git fsck: is the history intact?
Exit 3 when git isn't installed (setup installs it).
"""
import shutil, subprocess, sys
from _common import HOME, KIT, die

IGNORE = """# foundry-kit backup: only their profile and records are tracked
/*
!/.gitignore
!/profile/
!/data/
/data/cache/
/data/tmp/
*.tmp
"""

def git(*a, check=True):
    p = subprocess.run(["git", "-C", str(HOME), *a], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and p.returncode: die(f"git {a[0]} failed: {(p.stderr or p.stdout).strip()[:300]}")
    return p

def need_git():
    if not shutil.which("git"):
        print("ACTION NEEDED: git isn't installed, so history isn't being kept. Run setup.cmd again."); sys.exit(3)

def guard():
    # never turn the kit's own development repository into a backup
    if HOME == KIT and KIT.name == "kit" and (KIT.parent / ".git").exists(): die("this is the kit's source folder, not an install")

def is_repo(): return (HOME / ".git").is_dir()

def init():
    need_git(); guard()
    (HOME / "profile").mkdir(exist_ok=True); (HOME / "data").mkdir(exist_ok=True)
    made = not is_repo()
    if made: git("init", "-q")
    (HOME / ".gitignore").write_text(IGNORE, encoding="utf-8", newline="\n")
    for k, v in (("user.name", "foundry-kit"), ("user.email", "backup@foundry-kit.invalid"), ("core.autocrlf", "false"),
                 ("core.quotepath", "false"), ("commit.gpgsign", "false")):
        git("config", "--local", k, v)
    print("backup: history started" if made else "backup: already set up")
    if made: commit("start history")
    return 0

def commit(msg):
    need_git(); guard()
    if not is_repo(): init(); return 0
    git("add", "-A", "--", ".gitignore", "profile", "data")
    if not git("status", "--porcelain").stdout.strip(): print("backup: nothing changed"); return 0
    git("commit", "-q", "--no-verify", "-m", msg)
    print(f"backup: saved {git('rev-parse', '--short', 'HEAD').stdout.strip()} ({msg})")
    return 0

def log(args):
    need_git()
    if not is_repo(): print("backup: no history yet (backup.py init)"); return 0
    n = args[args.index("-n") + 1] if "-n" in args else "15"
    paths = [a for a in args if not a.startswith("-") and a != n]
    print(git("log", f"-n{n}", "--date=format:%Y-%m-%d %H:%M", "--format=%h  %ad  %s", "--", *paths).stdout.rstrip() or "no history for that")
    return 0

def show(rev, path):
    need_git()
    print(git("show", f"{rev}:{path.replace(chr(92), '/')}").stdout, end="")
    return 0

def check():
    need_git()
    if not is_repo(): print("backup: no history yet"); return 1
    p = git("fsck", "--no-progress", check=False)
    if p.returncode: print("PROBLEM: the history folder (.git) is damaged. Your files are fine; tell the person who set this up.\n" + p.stderr[:300]); return 1
    print("backup: history intact"); return 0

def main(a):
    if not a: print(__doc__); return 1
    if a[0] == "init": return init()
    if a[0] == "commit" and len(a) > 1: return commit(a[1])
    if a[0] == "log": return log(a[1:])
    if a[0] == "show" and len(a) > 2: return show(a[1], a[2])
    if a[0] == "check": return check()
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
