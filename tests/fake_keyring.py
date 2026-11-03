"""A keyring backend for tests only, so no test ever touches the developer's Windows Credential Manager. Selected
with PYTHON_KEYRING_BACKEND=fake_keyring.FakeKeyring (tests/ on PYTHONPATH); entries live in FAKE_KEYRING_FILE
inside the sandbox."""
import json, os, pathlib
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError

class FakeKeyring(KeyringBackend):
    priority = 1

    def _path(self): return pathlib.Path(os.environ["FAKE_KEYRING_FILE"])

    def _all(self):
        p = self._path()
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def get_password(self, service, username): return self._all().get(f"{service}/{username}")

    def set_password(self, service, username, password):
        d = self._all(); d[f"{service}/{username}"] = password
        self._path().write_text(json.dumps(d), encoding="utf-8")

    def delete_password(self, service, username):
        d = self._all()
        if f"{service}/{username}" not in d: raise PasswordDeleteError("not found")
        del d[f"{service}/{username}"]; self._path().write_text(json.dumps(d), encoding="utf-8")
