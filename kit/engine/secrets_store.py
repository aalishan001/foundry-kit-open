"""Their keys and app passwords, kept in Windows Credential Manager through keyring. Never in a file, never printed.
Every entry is stored under the service "foundry-kit" with its name as the user name, so it shows in Credential
Manager → Windows Credentials as "foundry-kit"."""
SERVICE = "foundry-kit"

class Missing(Exception):
    """keyring isn't installed, or the vault can't be reached."""

def _kr():
    try:
        import keyring
        return keyring
    except ImportError: raise Missing("the keyring package isn't installed: run setup.cmd")

def get(name):
    try: return _kr().get_password(SERVICE, name)
    except Missing: raise
    except Exception as e: raise Missing(f"Windows Credential Manager couldn't be read ({type(e).__name__})")

def put(name, value):
    if not value: raise ValueError("nothing to store")
    try: _kr().set_password(SERVICE, name, value)
    except Missing: raise
    except Exception as e: raise Missing(f"Windows Credential Manager couldn't be written ({type(e).__name__})")

def remove(name):
    try: _kr().delete_password(SERVICE, name); return True
    except Missing: raise
    except Exception: return False

def has(name):
    try: return bool(get(name))
    except Missing: return False
