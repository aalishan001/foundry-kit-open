"""/radar recipes: alert links for every board and place in their order, the experience band, company alert sign-ups,
the Gmail filter file; nothing fetched."""
import json, unittest, xml.etree.ElementTree as ET
from sandbox import Sandbox

class Recipes(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(pack="software-eng")
        self.sb.setup_profile(self, title="Senior Software Engineer", ctc=30, target_families=["backend", "full-stack"],
                              locations={"preferred": ["Pune", "north India"], "abroad": [{"country": "AE", "cities": ["Dubai"]}, {"country": "SA"}]})
        self.sb.write("data/radar.json", {"companies": [
            {"company": "Rho Power", "careers_url": "https://careers.rho.example.com/", "portal": {"type": "oracle", "tier": 3}, "every_days": 14,
             "added": "2026-10-01", "checks": [], "alert": {"url": "https://careers.rho.example.com/talent", "note": "Join Talent Community"}},
            {"company": "Sigma Grid", "careers_url": "https://sigma.example.com/careers", "portal": {"type": "other", "tier": 3}, "every_days": 14,
             "added": "2026-10-01", "checks": []}]})
        self.sb.env_extra = {"FOUNDRY_FIXTURES": str(self.sb.root / "none")}   # any fetch would fail loudly

    def tearDown(self): self.sb.close()

    def test_plan(self):
        p = json.loads(self.sb.ok(self, "recipes.py", "--json"))
        self.assertEqual(p["terms"][:2], ["backend engineer", "backend developer"])
        self.assertNotIn("software engineer", p["terms"])        # level words come from the experience filter
        self.assertEqual(p["years"], [4, 9])
        self.assertEqual(p["home"], ["Pune", "India"])              # a region isn't a search place
        self.assertEqual(p["abroad"], ["Dubai, United Arab Emirates", "Saudi Arabia"])
        boards = [(r["board"], r["place"]) for r in p["alerts"]]
        for b in ("LinkedIn", "Naukri", "Indeed", "foundit"): self.assertIn((b, "Pune"), boards)
        self.assertLess(boards.index(("LinkedIn", "Pune")), boards.index(("LinkedIn", "Dubai, United Arab Emirates")))
        self.assertIn(("Indeed", "Dubai, United Arab Emirates"), boards); self.assertNotIn(("Naukri", "Saudi Arabia"), boards)
        li = next(r["url"] for r in p["alerts"] if r["board"] == "LinkedIn")
        self.assertIn("f_TPR=r86400", li); self.assertIn("%22backend+engineer%22+OR", li)
        self.assertIn("experience=4", next(r["url"] for r in p["alerts"] if r["board"] == "Naukri"))
        self.assertEqual([c["url"] for c in p["companies"]], ["https://careers.rho.example.com/talent", None])

    def test_files(self):
        self.assertIn("1 company alert sign-ups", self.sb.ok(self, "recipes.py"))
        page = (self.sb.home / "Job alerts setup.html").read_text(encoding="utf-8")
        for part in ("Import filters", "Set alert", "Rho Power", "No alert sign-up for: Sigma Grid", "Gmail setup.cmd", "2-Step Verification"):
            self.assertIn(part, page)
        root = ET.parse(self.sb.home / "Gmail filter (import me).xml").getroot()
        APPS, ATOM = "{http://schemas.google.com/apps/2006}property", "{http://www.w3.org/2005/Atom}entry"
        props = [{p.get("name"): p.get("value") for p in e.iter(APPS)} for e in root.iter(ATOM)]
        self.assertEqual(len(props), 2)
        self.assertTrue(all(p["label"] == "Job Alerts" for p in props))
        self.assertIn("jobalerts-noreply@linkedin.com", props[0]["from"]); self.assertIn('"job alert"', props[1]["hasTheWord"])

if __name__ == "__main__":
    unittest.main()
