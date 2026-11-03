#!/usr/bin/env python3
"""OpenCode, the second way to use this folder (Claude's Code tab keeps working the same way).
  opencode_app.py key       in its own window: store the OpenRouter key (hidden input) in Windows Credential Manager,
                            then check it: credit left on the key, and that zero-data-retention routing works
  opencode_app.py status    key stored, credit left, OpenCode installed
  opencode_app.py launch    open OpenCode in this folder, with the key passed only to that window (OpenCode.cmd)
  opencode_app.py forget    remove the stored key
The key never goes into a file: OpenCode reads it from an environment variable that only its own window gets.
Every request asks OpenRouter for zero-data-retention, no-training endpoints only (opencode.json).
"""
import getpass, json, os, pathlib, shutil, subprocess, sys, urllib.error, urllib.request
from _common import HOME
import secrets_store as vault

KEY_NAME, ENV = "openrouter_key", "FOUNDRY_OPENROUTER_KEY"
API = "https://openrouter.ai/api/v1"

def openrouter(path, key, body=None):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read().decode("utf-8"))

def key_info(key):
    """-> (ok, line) about the key: credit limit and what's left, never the key itself."""
    try: d = openrouter("/key", key).get("data") or {}
    except urllib.error.HTTPError as e: return False, f"OpenRouter refused the key (HTTP {e.code}): check it was copied whole"
    except (urllib.error.URLError, OSError) as e: return False, f"couldn't reach OpenRouter ({type(e).__name__}): check the internet connection"
    lim, left, used = d.get("limit"), d.get("limit_remaining"), d.get("usage") or 0
    return True, (f"credit left on this key: ${left:.2f} of ${lim:.2f}" if lim is not None else f"no credit limit on this key; used ${used:.2f} so far")

def zdr_probe(key, model="anthropic/claude-haiku-5.5"):
    """One tiny request with the kit's routing rules: proves the key works and ZDR endpoints answer."""
    body = {"model": model, "max_tokens": 5, "messages": [{"role": "user", "content": "Reply with OK."}],
            "provider": {"zdr": True, "data_collection": "deny"}}
    try:
        d = openrouter("/chat/completions", key, body)
        return True, f"a test reply came back through a zero-data-retention endpoint ({d.get('provider', '?')})"
    except urllib.error.HTTPError as e:
        return False, f"the test request failed (HTTP {e.code}): {e.read().decode('utf-8', 'replace')[:160]}"
    except (urllib.error.URLError, OSError) as e: return False, f"couldn't reach OpenRouter ({type(e).__name__})"

def opencode_exe():
    exe = shutil.which("opencode")
    if exe: return exe
    p = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "opencode.exe"
    return str(p) if p.exists() else None

def set_key():
    if not sys.stdin.isatty(): print("Run this in its own window (setup.cmd asks for it)."); return 1
    print("Paste the OpenRouter key you were given (it starts with sk-or-). Typing stays hidden; press Enter.")
    key = getpass.getpass("Key: ").strip()
    if not key.startswith("sk-or-"): print("That doesn't look like an OpenRouter key. Nothing was stored."); return 1
    ok, line = key_info(key)
    if not ok: print(line + ". Nothing was stored."); return 1
    vault.put(KEY_NAME, key)
    print(f"Stored in Windows Credential Manager (foundry-kit). {line}.")
    ok2, line2 = zdr_probe(key)
    print(("OK: " if ok2 else "PROBLEM: ") + line2)
    return 0 if ok2 else 1

def status():
    try: key = vault.get(KEY_NAME)
    except vault.Missing as e: print(f"ACTION NEEDED: {e}"); return 1
    exe = opencode_exe()
    print("OpenCode: " + ("installed" if exe else "not installed (setup.cmd installs it)"))
    if not key: print("OpenRouter key: not stored (setup.cmd asks for it)"); return 1
    ok, line = key_info(key)
    print(f"OpenRouter key: stored; {line}")
    return 0 if ok and exe else 1

def launch():
    key, exe = vault.get(KEY_NAME), opencode_exe()
    if not exe: print("OpenCode isn't installed yet: double-click setup.cmd."); return 1
    if not key: print("The OpenRouter key isn't stored yet: double-click setup.cmd."); return 1
    env = dict(os.environ, **{ENV: key, "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT": "1"})
    return subprocess.call([exe, str(HOME)], cwd=str(HOME), env=env)

def forget():
    print("OpenRouter key removed" if vault.remove(KEY_NAME) else "no key was stored"); return 0

def main(a):
    cmd = a[0] if a else ""
    if cmd == "key": return set_key()
    if cmd == "status": return status()
    if cmd == "launch": return launch()
    if cmd == "forget": return forget()
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
