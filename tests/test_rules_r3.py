"""Revision 3 rules: years read from postings (a fit input, never an exclusion), max_steps_up, home_cities_only, and the
alert parser's badge lines, company · place split, saved-search id and header row."""
import json, unittest
from sandbox import Sandbox

ALERT = """Your job alert for backend engineer
Senior Backend Engineer
Omega Pay · Bengaluru, Karnataka, India
Top applicant
View job: https://www.linkedin.com/comm/jobs/view/111/?trackingId=x&refId=ssid_4242
Staff Software Engineer
Zeta Labs · Pune, Maharashtra, India
Fast growing
3 connections
View job: https://www.linkedin.com/comm/jobs/view/112/?trackingId=y
"""

class Rules(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(pack="software-eng"); self.sb.setup_profile(self, title="Senior Software Engineer", ctc=30)
        self.sb.write("profile/employment.json", [{"employer": "Acme Cloud", "role": "Engineer", "start": "2020-10", "end": None, "source": "user"}])
    def tearDown(self): self.sb.close()

    def rules(self, **d):
        self.sb.write("data/tmp/r.json", d)
        rc, out = self.sb.run("fit.py", "rules", "@data/tmp/r.json"); self.assertEqual(rc, 0, out)
        return json.loads(out[:out.rindex("}") + 1])

    def test_years(self):
        r = self.rules(title="Senior Backend Engineer", jd_text="We need 8+ years of backend experience, or 7+ years of experience with a Master's.")
        self.assertEqual((r["years"]["asked"], r["years"]["verdict"]), (7, "close")); self.assertFalse(r["excluded"])
        self.assertEqual(self.rules(title="Senior Backend Engineer (10-12 years)")["years"]["verdict"], "short")
        self.assertIn("rank 4", self.sb.ok(self, "fit.py", "level", "Senior Software Engineer (3 - 5 years)"))   # years aren't a level number

    def test_max_steps_up_and_home_cities_only(self):
        self.assertEqual(self.rules(title="Principal Engineer")["level"]["verdict"], "step up")
        self.sb.write("data/tmp/s.json", {"rules": {"max_steps_up": 2}, "locations": {"home_cities_only": ["Bengaluru"]}})
        self.sb.ok(self, "profile_cli.py", "set", "search", "@data/tmp/s.json")
        r = self.rules(title="Principal Engineer")
        self.assertEqual(r["level"]["verdict"], "too senior"); self.assertTrue(r["excluded"])
        self.assertEqual(self.rules(title="Staff Engineer")["level"]["verdict"], "step up")
        self.assertEqual(self.rules(title="Staff Engineer", location="Pune")["location"]["verdict"], "excluded")
        self.assertEqual(self.rules(title="Staff Engineer", location="Bengaluru, Karnataka")["location"]["verdict"], "home")
        self.assertEqual(self.rules(title="Staff Engineer", location="India, Karnataka, Bangalore")["location"]["verdict"], "home")   # the old name too
        self.assertEqual(self.rules(title="Staff Engineer", location="Pune", remote=True)["location"]["verdict"], "home")

    def test_alert_badges_split_and_ssid(self):
        p = self.sb.write("data/tmp/alert.txt", ALERT)
        rows = json.loads(self.sb.ok(self, "alerts.py", "parse", p, "--json"))
        self.assertEqual([(r["title"], r["company"], r["location"]) for r in rows],
                         [("Senior Backend Engineer", "Omega Pay", "Bengaluru, Karnataka, India"), ("Staff Software Engineer", "Zeta Labs", "Pune, Maharashtra, India")])
        self.assertEqual([r["ssid"] for r in rows], ["4242", None])

    def test_company_senders(self):
        self.sb.write("data/radar.json", {"companies": [{"company": "Omega Pay", "careers_url": "https://careers.omegapay.example.com/", "portal": {"type": "workday", "tier": 1,
            "host": "omegapay.wd3.myworkdayjobs.com", "tenant": "omegapay", "site": "C"}, "every_days": 7, "added": "2026-11-01", "checks": [], "alert": {"senders": ["talent" + "@" + "omegapay-mail.example.com"]}}]})
        self.assertEqual(self.sb.ok(self, "alerts.py", "company-of", "Jobs <omegapay" + "@" + "myworkday.com>").strip(), "Omega Pay")
        self.assertEqual(self.sb.ok(self, "alerts.py", "company-of", "x" + "@" + "jobs.omegapay.example.com").strip(), "Omega Pay")
        self.assertIn("not a radar company", self.sb.fails(self, "alerts.py", "company-of", "news" + "@" + "other.example.org"))

if __name__ == "__main__":
    unittest.main()
