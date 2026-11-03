"""The daily engine sweep: every tier-1 company plus Gmail, prefilter and dedupe, jobs waiting to be ranked, the
report, the log, the lock and the 20-hour guard; triage; the Task Scheduler definition."""
import json, os, shutil, unittest, xml.etree.ElementTree as ET
from sandbox import Sandbox, FIXTURES, REPO

class Daily(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(pack="software-eng"); self.sb.setup_profile(self, title="Senior Software Engineer", ctc=30)
        shutil.copy(FIXTURES / "radar_test.json", self.sb.home / "data" / "radar.json")
        box = self.sb.root / "box.json"
        box.write_text(json.dumps({"password": "p" * 16, "labels": {"Job Alerts": {"uidvalidity": 3, "messages": {
            "5": (FIXTURES / "alerts" / "html_alert.eml").read_text(encoding="utf-8")}}}}), encoding="utf-8")
        (self.sb.root / "vault.json").write_text(json.dumps({"foundry-kit/gmail_app_password": "p" * 16}), encoding="utf-8")
        self.sb.env_extra = {"FOUNDRY_FIXTURES": str(FIXTURES / "http"), "FOUNDRY_IMAP_CLASS": "fake_imap.FakeIMAP", "FAKE_IMAP_BOX": str(box),
                             "FAKE_IMAP_LOG": str(self.sb.root / "imap.log"), "PYTHON_KEYRING_BACKEND": "fake_keyring.FakeKeyring",
                             "FAKE_KEYRING_FILE": str(self.sb.root / "vault.json"),
                             "PYTHONPATH": str(REPO / "tests") + os.pathsep + os.environ.get("PYTHONPATH", "")}
        self.sb.write("data/tmp/g.json", {"gmail": {"enabled": True, "mode": "imap", "address": "riya.t" + "@" + "gmail.com"}})
        self.sb.ok(self, "profile_cli.py", "set", "search", "@data/tmp/g.json")

    def tearDown(self): self.sb.close()

    def test_run_report_and_guard(self):
        self.sb.ok(self, "backup.py", "init")
        out = self.sb.ok(self, "sweep_daily.py")
        jobs = {j["title"]: j for j in self.sb.json("data/jobs.json")["jobs"]}
        self.assertIn("Senior Software Engineer – Backend", jobs)          # tier 1 (Greenhouse)
        self.assertIn("Manager – Backend Platform", jobs)                        # from the Gmail label
        self.assertEqual(jobs["Manager – Backend Platform"]["source"]["tier"], 2)
        self.assertIn("Gmail: 1 new message(s)", out); self.assertIn("Theta Logistics", out)   # paste-in reminder
        self.assertIn("HTTP 404", out)                                             # a dead board is reported, not fatal
        self.assertIn("jsearch: no key", out)
        waiting = self.sb.ok(self, "jobs.py", "waiting")
        self.assertIn(f"-- {len(jobs)} waiting", waiting)
        jid = jobs["Manager – Backend Platform"]["id"]
        self.sb.ok(self, "jobs.py", "triage", jid, "high", "backend at their level, Lucknow")
        self.assertIn(f"-- {len(jobs) - 1} waiting", self.sb.ok(self, "jobs.py", "waiting"))
        self.sb.fails(self, "jobs.py", "triage", jid, "maybe", "x", contains="usage")
        self.assertIn("daily sweep done", (self.sb.home / "data" / "logs" / "sweep_daily.log").read_text(encoding="utf-8"))
        self.assertIn("daily sweep:", self.sb.ok(self, "backup.py", "log"))
        self.assertIn("already ran at 10:00", self.sb.ok(self, "sweep_daily.py", "--if-older", "20", now="2026-10-26T05:00:00"))
        self.assertIn("Daily sweep", self.sb.ok(self, "sweep_daily.py", "--if-older", "20", now="2026-10-26T07:00:00"))
        self.assertIn("2026-10-26 07:00", self.sb.ok(self, "sweep_daily.py", "report", now="2026-10-26T07:05:00"))
        self.sb.ok(self, "validate.py")

    def test_lock_and_dry_run(self):
        self.sb.write("data/tmp/sweep_daily.lock", "123 now\n")
        self.assertIn("already running", self.sb.ok(self, "sweep_daily.py"))
        (self.sb.home / "data" / "tmp" / "sweep_daily.lock").unlink()
        self.sb.ok(self, "sweep_daily.py", "--dry-run")
        self.assertFalse((self.sb.home / "data" / "jobs.json").exists())
        self.assertFalse(list((self.sb.home / "data").glob("alerts/*.eml")))

class Schedule(unittest.TestCase):
    def test_task_definition(self):
        sb = Sandbox()
        try:
            out = sb.ok(self, "schedule.py", "xml", "--at", "07:45")
            root = ET.fromstring(out.split("?>", 1)[1])
            ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
            self.assertTrue(root.find(".//t:StartBoundary", ns).text.endswith("T07:45:00"))
            self.assertEqual(root.find(".//t:StartWhenAvailable", ns).text, "true")
            self.assertEqual(root.find(".//t:DisallowStartIfOnBatteries", ns).text, "false")
            self.assertEqual(root.find(".//t:RunLevel", ns).text, "LeastPrivilege")
            self.assertTrue(root.find(".//t:Arguments", ns).text.strip('"').endswith("sweep_daily.py"))
            self.assertEqual(root.find(".//t:WorkingDirectory", ns).text, str(sb.home))
            sb.fails(self, "schedule.py", "xml", "--at", "25:00", contains="08:30")
        finally: sb.close()

if __name__ == "__main__":
    unittest.main()
