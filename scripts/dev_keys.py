#!/usr/bin/env python3
"""Developer test keys for model providers, kept in Windows Credential Manager (service "foundry-kit-dev"), never in a
file and never printed. Run `set` in your own terminal: the key is typed with hidden input.
  dev_keys.py set <openrouter|groq|cerebras>
  dev_keys.py status
  dev_keys.py remove <name>
Scripts read them with dev_keys.get(name), and pass them on only as environment variables of a child process.
"""
import getpass, sys
import keyring

SERVICE = "foundry-kit-dev"
NAMES = ("openrouter", "groq", "cerebras", "openrouter_provisioning")

def get(name): return keyring.get_password(SERVICE, name)

def main(a):
    if a[:1] == ["set"] and len(a) > 1 and a[1] in NAMES:
        if not sys.stdin.isatty(): print("run this in your own terminal (hidden input)"); return 1
        v = getpass.getpass(f"{a[1]} key (hidden): ").strip()
        if not v: print("nothing stored"); return 1
        keyring.set_password(SERVICE, a[1], v); print(f"{a[1]}: stored in Credential Manager ({SERVICE})"); return 0
    if a[:1] == ["remove"] and len(a) > 1:
        try: keyring.delete_password(SERVICE, a[1]); print(f"{a[1]}: removed")
        except Exception: print(f"{a[1]}: nothing stored")
        return 0
    if not a or a[0] == "status":
        for n in NAMES: print(f"{n:<24} {'stored' if get(n) else '-'}")
        return 0
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
