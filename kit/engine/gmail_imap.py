#!/usr/bin/env python3
"""Job-alert emails from their Gmail "Job Alerts" label, over IMAP, read-only.
  gmail_imap.py setup      in its own window (Gmail setup.cmd): the app-password walkthrough; tests the login and
                           the label; keeps the password in Windows Credential Manager, never in a file
  gmail_imap.py status     set up or not, and when it last read
  gmail_imap.py fetch [--days N] [--dry-run]   new messages in the label -> data/alerts/*.eml (default: since the last
                           read, at most 14 days back)
  gmail_imap.py forget     remove the stored app password and switch Gmail off
Read-only by construction: the label is opened with EXAMINE (select readonly), bodies are read with BODY.PEEK[] so
nothing is marked read, and only LOGIN, SELECT, LIST, UID SEARCH, UID FETCH and LOGOUT can be sent. Nothing is ever
flagged, copied, moved, deleted or expunged. Messages are kept once, keyed by the label's UIDVALIDITY and UID.
Needs 2-Step Verification on their Google account: without it Google doesn't offer app passwords.
"""
import datetime as dt, getpass, imaplib, importlib, os, re, sys, webbrowser
from _common import DATA, load, save, today, stamp, opt, die, rel
import secrets_store as vault

HOST, PORT = "imap.gmail.com", 993
ALERTS = DATA / "alerts"
STATE = ALERTS / "state.json"
PASSWORD_NAME = "gmail_app_password"
MAX_DAYS, MAX_MESSAGES = 14, 200
ALLOWED = {"LOGIN", "SELECT", "EXAMINE", "LIST", "SEARCH", "FETCH", "LOGOUT", "NOOP", "CAPABILITY"}
TWO_SV = "https://myaccount.google.com/signinoptions/twosv"
APP_PASSWORDS = "https://myaccount.google.com/apppasswords"

class GmailError(Exception): pass

class ReadOnly:
    """The only door to the mailbox. Anything but reading raises before it reaches the server."""
    def __init__(self, conn): self._c = conn
    def login(self, user, pw): return self._c.login(user, pw)
    def list(self): return self._c.list()
    def examine(self, box): return self._c.select(box, readonly=True)
    def search(self, *criteria): return self._c.uid("SEARCH", *criteria)
    def fetch(self, uid):
        return self._c.uid("FETCH", uid, "(BODY.PEEK[])")   # PEEK: reading never sets \\Seen
    def uidvalidity(self, box):
        typ, data = self._c.status(box, "(UIDVALIDITY)")
        m = re.search(rb"UIDVALIDITY (\d+)", (data or [b""])[0] or b"")
        return int(m.group(1)) if m else 0
    def logout(self):
        try: self._c.logout()
        except Exception: pass
    def __getattr__(self, name):
        raise GmailError(f"{name} is not a read-only IMAP operation: refused")

def _imap_class():
    spec = os.environ.get("FOUNDRY_IMAP_CLASS")   # tests: a fake server
    if spec:
        mod, cls = spec.rsplit(".", 1)
        return getattr(importlib.import_module(mod), cls)
    return imaplib.IMAP4_SSL

def settings():
    from _common import search_rules
    return (search_rules().get("gmail") or {})

def connect(address, password):
    try: c = _imap_class()(HOST, PORT)
    except OSError as e: raise GmailError(f"couldn't reach Gmail ({e.__class__.__name__}): check the internet connection")
    ro = ReadOnly(c)
    try: ro.login(address, password)
    except imaplib.IMAP4.error as e:
        ro.logout()
        raise GmailError("Gmail refused the app password (it may have been revoked, or the password was changed): run Gmail setup.cmd again")
    return ro

def box_name(label): return '"' + label.replace('"', '') + '"'

def open_label(ro, label):
    typ, _ = ro.examine(box_name(label))
    if typ != "OK": raise GmailError(f'the "{label}" label doesn\'t exist yet: import the Gmail filter first (Job alerts setup.html)')

# ---------------------------------------------------------------- fetch
def fetch(days=None, dry=False):
    """-> list of saved .eml paths (new messages only)."""
    g = settings()
    if not g.get("enabled"): return []
    pw = vault.get(PASSWORD_NAME)
    if not pw: raise GmailError("the Gmail app password isn't stored: run Gmail setup.cmd")
    label = g.get("label") or "Job Alerts"
    st = load(STATE, {}) or {}
    last = st.get("last_date")
    back = days if days is not None else min(MAX_DAYS, (today() - dt.date.fromisoformat(last)).days + 1) if last else MAX_DAYS
    since = (today() - dt.timedelta(days=max(1, back))).strftime("%d-%b-%Y")
    ro = connect(g["address"], pw)
    saved = []
    try:
        uv = ro.uidvalidity(box_name(label))
        open_label(ro, label)
        if st.get("uidvalidity") != uv: st = {"uidvalidity": uv, "seen": []}
        typ, data = ro.search("SINCE", since)
        uids = [u.decode() for u in (data[0] or b"").split()] if typ == "OK" and data else []
        seen = set(st.get("seen", []))
        new = [u for u in uids if u not in seen][-MAX_MESSAGES:]
        ALERTS.mkdir(parents=True, exist_ok=True)
        for u in new:
            typ, msg = ro.fetch(u)
            raw = next((part[1] for part in msg or [] if isinstance(part, tuple) and len(part) > 1), None)
            if typ != "OK" or not raw: continue
            p = ALERTS / f"{uv}-{u}.eml"
            if not dry: p.write_bytes(raw); seen.add(u)
            saved += [p]   # (no .append anywhere: the read-only source check forbids the IMAP verb)
    finally:
        ro.logout()
    if not dry:
        st.update(seen=sorted(seen, key=int)[-2000:], last_date=today().isoformat(), last_run=stamp())
        save(STATE, st)
    return saved

# ---------------------------------------------------------------- setup (interactive, its own window)
def say(msg=""): print(msg, flush=True)

def setup():
    if not sys.stdin.isatty():
        say("Run this in its own window: double-click Gmail setup.cmd in your job-search folder."); return 1
    from profile_cli import get, put
    say("Gmail setup: lets the kit read your Job Alerts label every morning (read-only).\n")
    say("Before you start:")
    say("  - Import the Gmail filter first, so the Job Alerts label exists (Job alerts setup.html, step 1).")
    say("  - Your Google account needs 2-Step Verification. Without it Google doesn't offer app passwords.\n")
    address = input("Your Gmail address: ").strip()
    if not re.match(r"^[^@\s]+@(gmail|googlemail)\.com$", address, re.I):
        say("That doesn't look like a Gmail address (…@gmail.com). Nothing was changed."); return 1
    say(f"\n1. Checking 2-Step Verification. Opening {TWO_SV}")
    say("   If it says 2-Step Verification is OFF, turn it on and follow Google's steps, then come back here.")
    webbrowser.open(TWO_SV)
    input("   Press Enter when 2-Step Verification is on... ")
    say(f"\n2. Making an app password. Opening {APP_PASSWORDS}")
    say('   Type a name such as "Job search kit" and click Create. Google shows a 16-letter password once.')
    say('   If the page says "The setting you are looking for is not available", 2-Step Verification is still off.')
    webbrowser.open(APP_PASSWORDS)
    pw = re.sub(r"\s+", "", getpass.getpass("\n3. Paste the 16-letter app password here (typing stays hidden) and press Enter: "))
    if not re.fullmatch(r"[a-zA-Z]{16}", pw):
        say("That isn't 16 letters. Nothing was stored; run Gmail setup.cmd again."); return 1
    s = get("search"); g = s.setdefault("gmail", {})
    label = g.get("label") or "Job Alerts"
    say("\n4. Testing: signing in and opening the Job Alerts label, read-only...")
    try:
        ro = connect(address, pw)
        try:
            open_label(ro, label)
            typ, data = ro.search("SINCE", (today() - dt.timedelta(days=MAX_DAYS)).strftime("%d-%b-%Y"))
            n = len((data[0] or b"").split()) if typ == "OK" and data else 0
        finally: ro.logout()
    except GmailError as e:
        say(f"   Didn't work: {e}\n   Nothing was stored."); return 1
    vault.put(PASSWORD_NAME, pw)
    g.update(enabled=True, mode="imap", address=address, label=label, checked=today().isoformat())
    for k in ("checks", "notes", "query"): g.pop(k, None)
    s["source"] = "user"; put("search", s)
    say(f"   OK: {n} message(s) in {label} from the last {MAX_DAYS} days.")
    say("\nDone. The password is kept in Windows Credential Manager (foundry-kit), not in any file.")
    say("The kit only reads the Job Alerts label; it never marks, moves or deletes anything.")
    say("To stop it any time: delete the app password at myaccount.google.com/apppasswords.")
    return 0

def status():
    g = settings()
    st = load(STATE, {}) or {}
    if not g.get("enabled"): print("Gmail: off (paste alert emails into /sweep, or double-click Gmail setup.cmd)"); return 0
    try: stored = vault.has(PASSWORD_NAME)
    except vault.Missing as e: print(f"Gmail: ACTION NEEDED: {e}"); return 1
    print(f"Gmail: on, reading the {g.get('label', 'Job Alerts')!r} label of {g.get('address')} read-only; password "
          + ("stored in Credential Manager" if stored else "MISSING: run Gmail setup.cmd again")
          + (f"; last read {st['last_run']}" if st.get("last_run") else "; not read yet"))
    return 0 if stored else 1

def forget():
    from profile_cli import get, put
    vault.remove(PASSWORD_NAME)
    s = get("search"); s.setdefault("gmail", {})["enabled"] = False; put("search", s)
    print("Gmail: off; the app password is removed from Credential Manager. Also delete it at myaccount.google.com/apppasswords.")
    return 0

def main(a):
    if not a: print(__doc__); return 1
    if a[0] == "setup": return setup()
    if a[0] == "status": return status()
    if a[0] == "forget": return forget()
    if a[0] == "fetch":
        d = opt(a, "--days")
        try: files = fetch(int(d) if d else None, "--dry-run" in a)
        except (GmailError, vault.Missing) as e: print(f"COULDN'T READ GMAIL: {e}"); return 2
        if not settings().get("enabled"): print("Gmail is off"); return 0
        for f in files: print(rel(f))
        print(f"-- {len(files)} new message(s)"); return 0
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
