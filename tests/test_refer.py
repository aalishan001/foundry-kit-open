"""/refer: contacts and stages on the user's word, one contact locked per role (released on a decline or silence past
the nudge), the daily cap, one nudge, holds and parks, messages within their limits and the truth rule on the pitch."""
import unittest
from sandbox import Sandbox

class Refer(unittest.TestCase):
    def setUp(self):
        self.sb = sb = Sandbox(pack="software-eng"); sb.setup_profile(self, title="Senior Software Engineer", ctc=30)
        sb.write("profile/identity.json", {"name": {"full": "Riya Testwal", "preferred": "Riya", "resume": "Riya Testwal"}, "source": "user"})
        sb.write("data/tmp/f.json", {"kind": "achievement", "text": "Cut checkout API p99 latency from 820 ms to 310 ms", "status": "confirmed", "source": "user"})
        sb.ok(self, "facts.py", "add", "@data/tmp/f.json")
        sb.write("data/tmp/j.json", [{"company": "Acme Cloud", "title": "Senior Backend Engineer", "url": "https://jobs.example.com/acme/1", "location": "Pune",
                                      "source": {"tier": 1, "via": "greenhouse"}},
                                     {"company": "Beta Pay", "title": "Staff Engineer", "url": "https://jobs.example.com/beta/2", "location": "Pune",
                                      "source": {"tier": 1, "via": "lever"}}])
        sb.ok(self, "jobs.py", "add", "@data/tmp/j.json")
        for n in ("Priya Rao", "Arjun Mehta", "Sam Lee"):
            sb.write("data/tmp/c.json", {"name": n, "company": "Acme Cloud", "how_known": "old teammate"}); sb.ok(self, "refer.py", "add", "@data/tmp/c.json")

    def tearDown(self): self.sb.close()

    def test_lock_decline_and_quiet_past_the_nudge(self):
        self.sb.fails(self, "refer.py", "stage", "c-0001", "asked", contains="--job")
        self.sb.ok(self, "refer.py", "stage", "c-0001", "asked", "--job", "j-0001")
        self.sb.fails(self, "refer.py", "stage", "c-0002", "asked", "--job", "j-0001", contains="one contact per role")
        self.sb.ok(self, "refer.py", "stage", "c-0001", "declined")
        self.sb.ok(self, "refer.py", "stage", "c-0002", "asked", "--job", "j-0001")                    # released by the decline
        self.assertIn("nudge due: c-0002", self.sb.ok(self, "refer.py", "due", now="2026-10-31T10:00:00"))
        self.sb.ok(self, "refer.py", "nudged", "c-0002", now="2026-10-31T10:00:00")
        self.sb.fails(self, "refer.py", "nudged", "c-0002", now="2026-11-01T10:00:00", contains="one nudge")
        self.sb.fails(self, "refer.py", "stage", "c-0003", "asked", "--job", "j-0001", now="2026-11-02T10:00:00", contains="one contact per role")
        self.sb.ok(self, "refer.py", "stage", "c-0003", "asked", "--job", "j-0001", now="2026-11-06T10:00:00")   # quiet 5 days past the nudge
        self.sb.ok(self, "validate.py")

    def test_daily_cap_hold_and_park(self):
        self.sb.write("data/tmp/s.json", {"referrals": {"daily_cap": 1, "nudge_days": 5}})
        self.sb.ok(self, "profile_cli.py", "set", "search", "@data/tmp/s.json")
        self.sb.ok(self, "refer.py", "stage", "c-0001", "asked", "--job", "j-0001")
        self.sb.fails(self, "refer.py", "stage", "c-0002", "asked", "--job", "j-0002", contains="daily cap of 1")
        self.sb.ok(self, "refer.py", "hold", "j-0002", "--note", "Beta allows one referral per quarter")
        self.sb.fails(self, "refer.py", "stage", "c-0002", "asked", "--job", "j-0002", now="2026-10-26T10:00:00", contains="held out of outreach")
        self.sb.ok(self, "refer.py", "unhold", "j-0002"); self.sb.ok(self, "refer.py", "park", "Beta", "Pay")
        self.sb.fails(self, "refer.py", "stage", "c-0002", "asked", "--job", "j-0002", now="2026-10-26T10:00:00", contains="parked")

    def test_messages_and_the_truth_rule(self):
        self.sb.write("data/tmp/p.json", {"text": "I cut checkout API p99 latency from 820 ms to 310 ms.", "facts": ["f-0001"]})
        out = self.sb.ok(self, "refer.py", "ask", "c-0001", "--job", "j-0001", "--pitch", "@data/tmp/p.json")
        self.assertIn("Hi Priya", out); self.assertIn("Senior Backend Engineer", out); self.assertIn("310 ms", out); self.assertIn("no problem", out)
        self.assertTrue((self.sb.home / "data" / "refer" / "c-0001-j-0001-ask.md").exists())
        self.sb.write("data/tmp/p.json", {"text": "I cut latency for 50 million users.", "facts": ["f-0001"]})
        self.assertIn("truth rule", self.sb.fails(self, "refer.py", "ask", "c-0001", "--job", "j-0001", "--pitch", "@data/tmp/p.json"))
        self.sb.write("data/tmp/p.json", {"text": "I cut checkout API p99 latency from 820 ms to 310 ms. " * 6, "facts": ["f-0001"]})
        self.assertIn("keep it under 85", self.sb.fails(self, "refer.py", "ask", "c-0001", "--job", "j-0001", "--pitch", "@data/tmp/p.json"))
        out = self.sb.ok(self, "refer.py", "ask", "c-0001", "--job", "j-0001", "--kind", "connect")
        self.assertLess(len(out.split("\n-- ")[0]), 220)

if __name__ == "__main__":
    unittest.main()
