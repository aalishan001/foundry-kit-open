"""A fake Gmail IMAP server for tests: a mailbox from FAKE_IMAP_BOX (JSON), and every call logged to FAKE_IMAP_LOG so
tests can prove the engine only reads."""
import imaplib, json, os

def _log(*parts):
    with open(os.environ["FAKE_IMAP_LOG"], "a", encoding="utf-8") as f: f.write(" ".join(map(str, parts)) + "\n")

class FakeIMAP:
    def __init__(self, host, port):
        _log("CONNECT", host, port)
        self.box = json.load(open(os.environ["FAKE_IMAP_BOX"], encoding="utf-8"))
        self.selected = None

    def login(self, user, pw):
        _log("LOGIN", user)
        if pw != self.box["password"]: raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")
        return "OK", [b"logged in"]

    def status(self, box, what):
        _log("STATUS", box, what)
        lb = self.box["labels"].get(box.strip('"'))
        return ("OK", [f'{box} (UIDVALIDITY {lb["uidvalidity"]})'.encode()]) if lb else ("NO", [b"no such label"])

    def select(self, box, readonly=False):
        _log("SELECT", box, "readonly" if readonly else "READ-WRITE")
        lb = self.box["labels"].get(box.strip('"'))
        if not lb: return "NO", [b"[NONEXISTENT] Unknown Mailbox"]
        self.selected = lb
        return "OK", [str(len(lb["messages"])).encode()]

    def uid(self, command, *args):
        _log("UID", command, *args)
        if command == "SEARCH": return "OK", [" ".join(sorted(self.selected["messages"], key=int)).encode()]
        if command == "FETCH":
            raw = self.selected["messages"][args[0]].encode()
            return "OK", [(f"{args[0]} (UID {args[0]} BODY[] {{{len(raw)}}}".encode(), raw), b")"]
        raise AssertionError(f"unexpected UID {command}")

    def logout(self): _log("LOGOUT"); return "BYE", [b""]

    def __getattr__(self, name):
        _log("FORBIDDEN", name)
        raise AssertionError(f"the engine called {name}")
