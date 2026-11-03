"""Upgrading a 1.0.0 folder: their values kept, new fields added, the retired Gmail check moved to the IMAP shape,
radar facts refreshed from the pack, history before and after; idempotent; run automatically by doctor --quick."""
import json, unittest
from sandbox import Sandbox

OLD_SEARCH = {"pack": "software-eng", "target_families": ["backend"],
              "current": {"title": "Senior Software Engineer", "ladder_rank": 4, "ctc_lpa": 30.0, "fixed_lpa": None, "variable_pct": None},
              "rules": {"never_lower_level": True, "lateral_min_raise_pct": 30, "raise_basis": "ctc"},
              "locations": {"home_country": "IN", "eligible_countries": ["IN"], "preferred": ["Pune"], "avoid": [], "remote_ok": True, "relocate": True},
              "notice_period_days": 90, "deal_breakers": [],
              "gmail": {"enabled": True, "checks": {"tools": True, "search": True, "body": True, "no_prompt": True}, "checked": "2026-10-25", "query": "x"},
              "answers": [{"q": "threshold?", "a": "30%", "date": "2026-10-25"}], "source": "user", "updated": "2026-10-25"}

class Upgrade(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(pack="software-eng")
        self.sb.write("profile/search.json", OLD_SEARCH)
        self.sb.ok(self, "radar.py", "seed")
        rad = self.sb.json("data/radar.json")
        for c in rad["companies"]: c.pop("stability", None); c.pop("alert", None)
        c = rad["companies"][0]; c["checks"] = [{"date": "2026-10-20", "found": 3, "new": 1, "note": "x"}]; c["every_days"] = 3
        self.sb.write("data/radar.json", rad)
        self.sb.write("data/jobs.json", {"jobs": []})
        self.sb.ok(self, "backup.py", "init")

    def tearDown(self): self.sb.close()

    def test_upgrade(self):
        check = self.sb.ok(self, "upgrade.py", "check")
        self.assertIn("(check only)", check)
        self.assertEqual(self.sb.json("profile/search.json")["gmail"], OLD_SEARCH["gmail"])   # check changes nothing
        out = self.sb.ok(self, "upgrade.py")
        s = self.sb.json("profile/search.json")
        self.assertEqual(s["rules"]["lateral_min_raise_pct"], 30); self.assertEqual(s["notice_period_days"], 90)   # theirs, kept
        self.assertEqual(s["locations"]["preferred"], ["Pune"]); self.assertEqual(s["answers"], OLD_SEARCH["answers"])
        self.assertEqual((s["locations"]["abroad"], s["locations"]["pay_over_place"], s["rules"]["pe_min_employees"]), ([], False, 1000))
        self.assertEqual(s["gmail"], {"enabled": False, "mode": "imap", "address": "", "label": "Job Alerts", "checked": None})
        self.assertIn("Gmail setup.cmd to turn it back on", out)
        c = self.sb.json("data/radar.json")["companies"][0]
        self.assertEqual((c["every_days"], len(c["checks"])), (3, 1))                                  # their radar edits kept
        if "stability" in self.pack_first(): self.assertEqual(c["stability"], self.pack_first()["stability"])   # pack facts refreshed
        from sandbox import KIT
        self.assertEqual(self.sb.json("data/kit.json")["version"], (KIT / "VERSION").read_text(encoding="utf-8").strip())
        log = self.sb.ok(self, "backup.py", "log")
        self.assertIn("upgrade to 1.", log)   # (a "before upgrade" commit appears only when something was uncommitted)
        self.sb.ok(self, "validate.py")
        self.assertIn("already up to date", self.sb.ok(self, "upgrade.py"))                           # idempotent

    def pack_first(self):
        from sandbox import KIT
        return json.loads((KIT / "packs" / "software-eng" / "radar.json").read_text(encoding="utf-8"))["companies"][0]

    def test_doctor_quick_upgrades_once(self):
        out = self.sb.ok(self, "doctor.py", "--quick")
        self.assertIn("change(s)", out); self.assertIn("setup OK", out)
        self.assertEqual(self.sb.ok(self, "doctor.py", "--quick").strip(), "setup OK")

if __name__ == "__main__":
    unittest.main()
