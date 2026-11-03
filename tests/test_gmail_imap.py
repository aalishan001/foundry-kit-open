"""Gmail over IMAP against a fake server: read-only by construction (EXAMINE, BODY.PEEK[], nothing else), only the
Job Alerts label, new messages saved once, the password only in the (fake) vault; and a source check that the module
can't issue a write."""
import json, os, re, unittest
from sandbox import Sandbox, REPO, FIXTURES, ENGINE

PW = "abcd" + "efghijklmnop"
ADDR = "riya.testwal" + "@" + "gmail.com"

class Gmail(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(pack="software-eng"); self.sb.setup_profile(self, title="Senior Software Engineer", ctc=30)
        eml = (FIXTURES / "alerts" / "html_alert.eml").read_text(encoding="utf-8")
        self.box = self.sb.root / "box.json"; self.log = self.sb.root / "imap.log"
        self.box.write_text(json.dumps({"password": PW, "labels": {"Job Alerts": {"uidvalidity": 7, "messages": {"11": eml, "12": eml}},
                                                                    "INBOX": {"uidvalidity": 1, "messages": {"1": "private"}}}}), encoding="utf-8")
        self.sb.env_extra = {"FOUNDRY_IMAP_CLASS": "fake_imap.FakeIMAP", "FAKE_IMAP_BOX": str(self.box), "FAKE_IMAP_LOG": str(self.log),
                             "PYTHON_KEYRING_BACKEND": "fake_keyring.FakeKeyring", "FAKE_KEYRING_FILE": str(self.sb.root / "vault.json"),
                             "PYTHONPATH": str(REPO / "tests") + os.pathsep + os.environ.get("PYTHONPATH", "")}

    def tearDown(self): self.sb.close()

    def enable(self, pw=PW, label="Job Alerts"):
        (self.sb.root / "vault.json").write_text(json.dumps({"foundry-kit/gmail_app_password": pw}), encoding="utf-8")
        self.sb.write("data/tmp/g.json", {"gmail": {"enabled": True, "mode": "imap", "address": ADDR, "label": label}})
        self.sb.ok(self, "profile_cli.py", "set", "search", "@data/tmp/g.json")

    def calls(self): return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def test_off_by_default(self):
        self.assertIn("Gmail is off", self.sb.ok(self, "gmail_imap.py", "fetch"))
        self.assertIn("Gmail: off", self.sb.ok(self, "gmail_imap.py", "status"))
        self.assertEqual(self.calls(), [])

    def test_fetch_is_read_only_and_once(self):
        self.enable()
        out = self.sb.ok(self, "gmail_imap.py", "fetch")
        self.assertIn("2 new message(s)", out)
        self.assertEqual(sorted(p.name for p in (self.sb.home / "data" / "alerts").glob("*.eml")), ["7-11.eml", "7-12.eml"])
        c = self.calls()
        self.assertIn('SELECT "Job Alerts" readonly', c)
        self.assertFalse([l for l in c if l.startswith("SELECT") and "READ-WRITE" in l])
        self.assertFalse([l for l in c if "INBOX" in l])
        fetches = [l for l in c if l.startswith("UID FETCH")]
        self.assertTrue(fetches and all("BODY.PEEK[]" in l for l in fetches))
        self.assertFalse([l for l in c if l.startswith("FORBIDDEN")])
        self.assertIn("0 new message(s)", self.sb.ok(self, "gmail_imap.py", "fetch"))   # kept once
        for p in (self.sb.home / "data").rglob("*"):
            if p.is_file(): self.assertNotIn(PW, p.read_text(encoding="utf-8", errors="replace"))
        self.assertIn("password stored in Credential Manager", self.sb.ok(self, "gmail_imap.py", "status"))

    def test_plain_errors(self):
        self.enable(pw="wrongwrongwrongw")
        self.assertIn("refused the app password", self.sb.fails(self, "gmail_imap.py", "fetch"))
        self.enable(label="Missing Label")
        self.assertIn("import the Gmail filter first", self.sb.fails(self, "gmail_imap.py", "fetch"))
        self.assertIn("its own window", self.sb.fails(self, "gmail_imap.py", "setup", stdin="x\n"))

    def test_forget(self):
        self.enable()
        self.sb.ok(self, "gmail_imap.py", "forget")
        self.assertFalse(self.sb.json("profile/search.json")["gmail"]["enabled"])
        self.assertEqual(json.loads((self.sb.root / "vault.json").read_text(encoding="utf-8")), {})

class SourceIsReadOnly(unittest.TestCase):
    def test_no_write_commands_in_the_module(self):
        src = (ENGINE / "gmail_imap.py").read_text(encoding="utf-8")
        for bad in (r"\.store\(", r"\.copy\(", r"\.move\(", r"\.expunge\(", r"\.delete\(", r"\.append\(", r"\.create\(", r"\.rename\(",
                    r"\.close\(", r"[\"'](STORE|COPY|MOVE|EXPUNGE|DELETE|APPEND|CREATE|RENAME)[\"']", r"readonly\s*=\s*False", r"BODY\[\]"):
            self.assertIsNone(re.search(bad, src.replace("BODY.PEEK[]", "")), bad)

if __name__ == "__main__":
    unittest.main()
