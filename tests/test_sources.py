"""Sourcing: fetch allowlist, every portal adapter against recorded fixtures, sweep, alert emails, radar."""
import json, shutil, unittest
from sandbox import Sandbox, FIXTURES

class Sources(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(pack="software-eng")
        self.sb.setup_profile(self, title="Senior Software Engineer", ctc=30)
        shutil.copy(FIXTURES / "radar_test.json", self.sb.home / "data" / "radar.json")
        self.sb.env_extra = {"FOUNDRY_FIXTURES": str(FIXTURES / "http")}
    def tearDown(self): self.sb.close()

    def jobs(self): return {j["title"]: j for j in self.sb.json("data/jobs.json")["jobs"]}

    def test_allowlist(self):
        self.assertIn("never fetched", self.sb.fails(self, "fetch.py", "allowed", "https://www.linkedin.com/jobs/view/1"))
        self.sb.fails(self, "fetch.py", "allowed", "https://www.naukri.com/job-listings-x")
        self.assertIn("job-board API", self.sb.ok(self, "fetch.py", "allowed", "https://api.lever.co/v0/postings/x"))
        self.assertIn("on their radar", self.sb.ok(self, "fetch.py", "allowed", "https://www.zetalabs.example.in/careers"))
        self.assertIn("same organisation", self.sb.ok(self, "fetch.py", "allowed", "https://jobs.zetalabs.example.in/x"))
        self.sb.ok(self, "fetch.py", "allowed", "https://delta.wd3.myworkdayjobs.com/en-US/Careers/job/x")
        self.assertIn("isn't on their radar", self.sb.fails(self, "fetch.py", "allowed", "https://random.example.org/jobs"))
        self.sb.fails(self, "fetch.py", "allowed", "http://www.zetalabs.example.in/careers", contains="https")

    def test_sweep_all_portals(self):
        out = self.sb.ok(self, "sweep.py", "--all")
        j = self.jobs()
        kept = {"Senior Software Engineer – Backend", "Staff Software Engineer, APIs", "Engineering Manager - Full Stack",
                "Senior Backend Developer", "Principal Software Engineer, Payments", "Software Engineer 2 – Backend",
                "Full Stack Developer – Growth",
                "Senior Full Stack Engineer"}
        self.assertEqual(set(j), kept, out)
        for t in kept: self.assertTrue(j[t]["jd"], f"{t} has no JD")   # greenhouse/lever inline, SR/workday/static detail
        self.assertEqual(j["Principal Software Engineer, Payments"]["source"]["via"], "workday")
        self.assertEqual(j["Senior Full Stack Engineer"]["location"], "Lucknow, Uttar Pradesh")   # card before a generic link
        self.assertEqual(j["Principal Software Engineer, Payments"]["url"],
                         "https://delta.wd3.myworkdayjobs.com/Careers/job/Hyderabad/Principal-Software-Engineer--Payments_R-1001")
        self.assertIn("Theta Logistics", out)                      # tier 3 reminder
        self.assertIn("Switched to paste-in", out); self.assertIn("Eta Retail", out)
        self.assertIn("HTTP 404", out)                             # a failing board doesn't stop the sweep
        rad = {c["company"]: c for c in self.sb.json("data/radar.json")["companies"]}
        self.assertEqual(rad["Eta Retail"]["portal"]["tier"], 3)
        self.assertEqual(rad["Acme Cloud"]["checks"][-1]["new"], 2)
        drops = self.sb.ok(self, "sweep.py", "dropped")
        self.assertIn("below their level", drops); self.assertIn("ES is not a country", drops)
        self.assertIn("no target role family", drops); self.assertNotIn("Senior Analyst", drops)   # software firm: IC title unclear
        self.sb.ok(self, "validate.py")

    def test_second_sweep_adds_nothing(self):
        self.sb.ok(self, "sweep.py", "--all")
        self.sb.ok(self, "sweep.py", "--company", "Beta Pay")      # same minute: its own report, not an overwrite
        self.assertEqual(len(list((self.sb.home / "data" / "sweeps").glob("*.json"))), 2)
        n = len(self.jobs())
        out = self.sb.ok(self, "sweep.py", "--all", now="2026-11-05T10:00:00")
        self.assertEqual(len(self.jobs()), n); self.assertNotIn("New (", out)

    def test_only_due_companies_and_dry_run(self):
        self.sb.ok(self, "sweep.py", "--company", "Acme Cloud", "--dry-run")
        self.assertFalse((self.sb.home / "data" / "jobs.json").exists())
        self.assertEqual(self.sb.json("data/radar.json")["companies"][0]["checks"], [])
        self.sb.ok(self, "sweep.py", "--company", "Beta Pay")
        out = self.sb.ok(self, "sweep.py", now="2026-10-26T10:00:00")
        self.assertNotIn("Beta Pay", out.split("Paste-in")[0])     # checked yesterday, due again in 7 days
        self.assertIn("Acme Cloud", out)

    def test_alert_emails(self):
        out = self.sb.ok(self, "sweep.py", "alerts", FIXTURES / "alerts" / "pasted_alert.txt")
        j = self.jobs()
        self.assertIn("Senior Software Engineer - Backend", j)
        self.assertEqual(j["Senior Software Engineer - Backend"]["source"], {"tier": 2, "via": "linkedin.com", "ref": None})
        self.assertIn("Staff Engineer, Backend Platform", j); self.assertEqual(j["Staff Engineer, Backend Platform"]["company"], "Mu Systems")
        self.assertIn("below their level", out)                       # Software Engineer 2 – Backend
        out = self.sb.ok(self, "sweep.py", "alerts", FIXTURES / "alerts" / "html_alert.eml")
        self.assertEqual(self.jobs()["Manager – Backend Platform"]["company"], "Nu Tech Ltd")
        self.assertIn("HR Executive", out.split("dropped:")[1])
        self.assertIn("already", self.sb.ok(self, "sweep.py", "alerts", FIXTURES / "alerts" / "html_alert.eml"))

    def test_radar_detect_add_drop(self):
        d = lambda u: json.loads(self.sb.ok(self, "radar.py", "detect", u))
        self.assertEqual(d("https://boards.greenhouse.io/foo")["token"], "foo")
        self.assertEqual(d("https://jobs.eu.lever.co/bar/abc")["region"], "eu")
        w = d("https://acme.wd5.myworkdayjobs.com/en-US/External_Careers")
        self.assertEqual((w["tenant"], w["site"], w["tier"]), ("acme", "External_Careers", 1))
        self.assertEqual(d("https://career8.successfactors.com/careers?company=x")["tier"], 3)
        self.sb.fails(self, "radar.py", "detect", "https://in.linkedin.com/company/x", contains="never scraped")
        self.sb.ok(self, "radar.py", "add", "Omicron Cloud", "https://jobs.lever.co/omicron", "--every", "14")
        self.sb.fails(self, "radar.py", "add", "omicron cloud", "https://jobs.lever.co/omicron", contains="already")
        self.sb.fails(self, "radar.py", "drop", "Omicron Cloud", contains="--note")
        self.sb.ok(self, "radar.py", "drop", "Omicron Cloud", "--note", "not hiring in India")
        self.assertIn("Due (", self.sb.ok(self, "radar.py"))
        self.sb.ok(self, "radar.py", "add", "Pi Labs", "https://pilabs.darwinbox.in/ms/candidate/careers")
        self.assertEqual(json.loads(self.sb.ok(self, "radar.py", "show", "Pi Labs"))["every_days"], 14)   # paste-in default

    def test_fetch_text_of_a_job_page(self):
        out = self.sb.ok(self, "fetch.py", "text", "https://www.zetalabs.example.in/careers/jobs/123-full-stack-developer")
        self.assertIn("Full Stack Developer – Growth", out); self.assertNotIn("<p>", out)
        self.assertIn("COULDN'T FETCH", self.sb.fails(self, "fetch.py", "text", "https://www.linkedin.com/jobs/view/1"))

class PackRadarSeed(unittest.TestCase):
    def test_seed_from_pack_and_pack_new(self):
        sb = Sandbox()
        try:
            sb.write("packs/test/radar.json", {"companies": [{"company": "Rho Cloud", "segment": "ipp", "india_office": False,
                "careers_url": "https://boards.greenhouse.io/rho", "portal": {"type": "greenhouse", "tier": 1, "token": "rho", "how": "API"},
                "families": [], "verified": {"date": "2026-10-25", "result": "ok"}}]})
            self.assertIn("1 companies added", sb.ok(self, "radar.py", "seed"))
            self.assertIn("0 companies added", sb.ok(self, "radar.py", "seed"))
            sb.ok(self, "radar.py", "drop", "Rho Cloud", "--note", "x")
            self.assertIn("nothing new", sb.ok(self, "radar.py", "pack-new"))
            self.assertIn("0 companies added", sb.ok(self, "radar.py", "seed"))
        finally: sb.close()

if __name__ == "__main__":
    unittest.main()
