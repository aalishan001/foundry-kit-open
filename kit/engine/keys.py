#!/usr/bin/env python3
"""Free job-search API keys, kept in Windows Credential Manager (never in a file, never shown).
  keys.py status                       which keys are stored, and each API's usage today
  keys.py set <adzuna|jooble|jsearch>  asks for the key with hidden input: run it in its own window (API keys.cmd)
  keys.py remove <adzuna|jooble|jsearch>
Where to get each key (all free):
  adzuna   developer.adzuna.com: register, then copy the Application ID and the Application Key
  jooble   jooble.org/api/about: fill in the form; the key arrives by email
  jsearch  rapidapi.com: sign up, open the JSearch API, subscribe to the free Basic plan, copy X-RapidAPI-Key
"""
import getpass, sys
import _common  # noqa: F401  (UTF-8 console)
import secrets_store as vault

APIS = {"adzuna": [("adzuna_app_id", "Adzuna Application ID"), ("adzuna_app_key", "Adzuna Application Key")],
        "jooble": [("jooble_key", "Jooble API key")],
        "jsearch": [("jsearch_key", "JSearch X-RapidAPI-Key")]}
HELP = {"adzuna": "https://developer.adzuna.com/signup", "jooble": "https://jooble.org/api/about",
        "jsearch": "https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch"}

def stored(api):
    return all(vault.has(n) for n, _ in APIS[api])

def status():
    from job_apis import usage_line
    try: vault.get("probe")
    except vault.Missing as e: print(f"ACTION NEEDED  {e}"); return 1
    for api in APIS:
        print(f"{api:<8} {'stored' if stored(api) else 'not set (optional)':<20} {usage_line(api)}")
    return 0

def set_key(api):
    if api not in APIS: print(f"which API? {', '.join(APIS)}"); return 1
    if not sys.stdin.isatty():
        print("Run this in its own window (double-click API keys.cmd), so the key is typed where nobody else sees it."); return 1
    print(f"Get the key here: {HELP[api]}")
    for name, label in APIS[api]:
        v = getpass.getpass(f"{label} (typing is hidden; paste and press Enter): ").strip()
        if not v: print("nothing entered; nothing stored"); return 1
        vault.put(name, v)
    print(f"{api}: stored in Windows Credential Manager (foundry-kit). The daily sweep will use it.")
    return 0

def remove(api):
    if api not in APIS: print(f"which API? {', '.join(APIS)}"); return 1
    n = sum(vault.remove(name) for name, _ in APIS[api])
    print(f"{api}: removed" if n else f"{api}: nothing was stored"); return 0

def main(a):
    if not a or a[0] == "status": return status()
    if a[0] == "set" and len(a) > 1: return set_key(a[1])
    if a[0] == "remove" and len(a) > 1: return remove(a[1])
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
