"""Fields: every shipped pack is valid; choosing a field resets families and remaps the level; the software ladder and
its unclear titles; target titles for fields without a pack; the Ashby adapter; the intake's new field stage."""
import json, unittest
from sandbox import Sandbox, KIT

class Packs(unittest.TestCase):
    def setUp(self): self.sb = Sandbox(pack="software-eng")
    def tearDown(self): self.sb.close()

    def test_every_shipped_pack_is_valid(self):
        for d in (KIT / "packs").iterdir():
            if d.is_dir(): self.assertIn(": OK", self.sb.ok(self, "pack_check.py", d.name))

    def test_software_ladder(self):
        for title, want in (("Sr. SWE - Payments", "rank 4"), ("SDE II", "rank 3"), ("SMTS", "rank 4"), ("Staff Engineer, Infra", "rank 5"),
                            ("Engineering Manager", "rank 5"), ("Software Engineer III", "not on the ladder"), ("Tech Lead", "not on the ladder")):
            self.assertIn(want, self.sb.ok(self, "fit.py", "level", title), title)

    def test_choosing_a_field(self):
        self.sb.ok(self, "profile_cli.py", "init")
        s = self.sb.json("profile/search.json")
        self.assertEqual((s["pack"], s["target_families"]), ("software-eng", ["backend", "full-stack"]))   # the default field
        self.assertIn("software-eng", self.sb.ok(self, "profile_cli.py", "packs"))
        self.sb.ok(self, "profile_cli.py", "current", "Senior Software Engineer", "--ctc", "30")
        self.assertEqual(self.sb.json("profile/search.json")["current"]["ladder_rank"], 4)
        self.sb.ok(self, "profile_cli.py", "pack", "general")
        s = self.sb.json("profile/search.json")
        self.assertEqual((s["pack"], s["target_families"], s["current"]["ladder_rank"]), ("general", [], None))   # not on the generic ladder: /start asks which level it equals
        self.sb.fails(self, "profile_cli.py", "pack", "astrology", contains="no pack")

    def test_target_titles_drive_the_prefilter(self):
        self.sb.ok(self, "profile_cli.py", "init")
        self.sb.ok(self, "profile_cli.py", "pack", "general")
        self.sb.ok(self, "profile_cli.py", "titles", "supply chain manager, logistics manager")
        self.sb.ok(self, "profile_cli.py", "current", "Assistant Manager", "--ctc", "12")
        code = ("import json, fit; print(json.dumps([fit.prefilter({'title': t, 'location': 'Pune'}) for t in "
                "['Supply Chain Manager - West', 'Marketing Manager', 'Logistics Executive']]))")
        import os, subprocess, sys
        from sandbox import ENGINE
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", cwd=str(ENGINE),
                           env=dict(os.environ, FOUNDRY_HOME=str(self.sb.home), PYTHONIOENCODING="utf-8"))
        keep = [k for k, _ in json.loads(p.stdout)]
        self.assertEqual(keep, [True, False, False], p.stdout + p.stderr)   # an executive is below Assistant Manager

    def test_ashby_adapter_and_detection(self):
        self.assertIn('"ashby"', self.sb.ok(self, "radar.py", "detect", "https://jobs.ashbyhq.com/novabank"))
        fx = self.sb.root / "fx"; fx.mkdir()
        (fx / "ashby.json").write_text(json.dumps({"jobs": [
            {"id": "a1", "title": "Senior Backend Engineer", "location": "Bengaluru", "secondaryLocations": [{"location": "Remote - India"}],
             "isRemote": False, "jobUrl": "https://jobs.ashbyhq.com/novabank/a1", "publishedAt": "2026-10-30T10:00:00Z",
             "descriptionPlain": "Build payment APIs in Go and Kafka. " * 10, "isListed": True},
            {"id": "a2", "title": "Hidden role", "isListed": False}]}), encoding="utf-8")
        (fx / "index.json").write_text(json.dumps({"GET https://api.ashbyhq.com/posting-api/job-board/novabank?includeCompensation=false": "ashby.json"}), encoding="utf-8")
        self.sb.write("data/radar.json", {"companies": [{"company": "Nova Bank", "careers_url": "https://jobs.ashbyhq.com/novabank", "segment": "fintech",
            "india_office": False, "portal": {"type": "ashby", "tier": 1, "token": "novabank"}, "how": "", "families": [], "every_days": 7,
            "added": "2026-10-01", "checks": [], "source": "user"}]})
        import os, subprocess, sys
        from sandbox import ENGINE
        code = "import json, radar, sources; print(json.dumps(sources.openings(radar.find(radar.load_radar(), 'Nova Bank'))))"
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", cwd=str(ENGINE),
                           env=dict(os.environ, FOUNDRY_HOME=str(self.sb.home), FOUNDRY_FIXTURES=str(fx), PYTHONIOENCODING="utf-8"))
        rows = json.loads(p.stdout or "[]")
        self.assertEqual([r["title"] for r in rows], ["Senior Backend Engineer"], p.stderr)
        self.assertEqual(rows[0]["location"], "Bengaluru; Remote - India"); self.assertEqual(rows[0]["posted"], "2026-10-30")
        self.assertIn("Kafka", rows[0]["jd_text"])

    def test_upgrade_adds_the_field_stage(self):
        self.sb.ok(self, "profile_cli.py", "init")
        it = self.sb.json("profile/intake.json"); it["stages"].pop("field"); self.sb.write("profile/intake.json", it)
        self.sb.write("data/kit.json", {"version": "1.1.0"})
        self.assertIn("already answered", self.sb.ok(self, "upgrade.py"))
        self.assertEqual(self.sb.json("profile/intake.json")["stages"]["field"], "done")

if __name__ == "__main__":
    unittest.main()
