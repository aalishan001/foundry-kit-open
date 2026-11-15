"""Tracker, revision 3: a per-company cap parks extra roles (no default); apply order; a re-check keeps the old fit;
backfilled applications need no JD or resume."""
import unittest
from sandbox import Sandbox, JD

class Tracker(unittest.TestCase):
    def setUp(self):
        self.sb = sb = Sandbox(); sb.setup_profile(self)
        sb.write("data/tmp/jd.txt", JD)
        for i, t in enumerate(("Backend Engineer", "Senior Backend Engineer", "Backend Developer"), 1):
            sb.write("data/tmp/j.json", {"company": "Acme Cloud", "title": t, "url": f"https://jobs.example.com/acme/{i}", "location": "Pune", "source": {"tier": 1, "via": "greenhouse"}})
            sb.ok(self, "jobs.py", "add", "@data/tmp/j.json", "--jd-file", "data/tmp/jd.txt")
    def tearDown(self): self.sb.close()

    def check(self, jid, match):
        self.sb.write("data/tmp/c.json", {"jobs": [{"id": jid, "fit": {"level": "lateral", "pay": "ask", "location": "home", "match": match, "likeliness": match - 10, "verdict": "ok"}}]})
        self.sb.ok(self, "jobs.py", "check", "@data/tmp/c.json")

    def test_cap_parks_and_no_cap_by_default(self):
        self.sb.write("inbox/cv.pdf", b"%PDF-1.4\n%%EOF\n")
        self.sb.write("data/tmp/a.json", {"job": "j-0001", "date": "2026-10-20", "channel": "careers_site"})
        self.sb.ok(self, "jobs.py", "applied", "@data/tmp/a.json", "--resume", "inbox/cv.pdf")
        self.assertIn("shortlisted", self.sb.ok(self, "jobs.py", "status", "j-0002", "shortlisted"))   # no cap unless they set one
        self.sb.write("data/tmp/s.json", {"rules": {"company_app_cap": 1}}); self.sb.ok(self, "profile_cli.py", "set", "search", "@data/tmp/s.json")
        self.assertIn("parked", self.sb.ok(self, "jobs.py", "status", "j-0003", "shortlisted"))
        self.sb.ok(self, "validate.py")

    def test_apply_order_and_recheck_history(self):
        self.check("j-0002", 80); self.check("j-0003", 60); self.check("j-0003", 70)
        out = self.sb.ok(self, "jobs.py", "list", "--by", "fit").splitlines()
        self.assertTrue(out[0].strip().startswith("1. j-0002") and out[1].strip().startswith("2. j-0003") and "not checked" in out[2])
        j3 = next(j for j in self.sb.json("data/jobs.json")["jobs"] if j["id"] == "j-0003")
        self.assertEqual((j3["fit"]["match"], j3["fit_history"][0]["fit"]["match"]), (70, 60))

    def test_backfill(self):
        self.sb.write("data/tmp/a.json", {"company": "Old Corp", "role": "Engineer", "date": "2026-09-01", "channel": "referral", "referrer": "A friend"})
        self.sb.fails(self, "jobs.py", "applied", "@data/tmp/a.json", contains="JD copy is required")
        self.sb.ok(self, "jobs.py", "applied", "@data/tmp/a.json", "--backfill")
        self.assertTrue(self.sb.json("data/apps.json")["apps"][0]["backfill"]); self.sb.ok(self, "validate.py")

if __name__ == "__main__":
    unittest.main()
