"""/prep: gaps from /check, the truth rule on answers, live-checked links, the files written; grill scores and the
weakest areas that feed /prep."""
import json, unittest
from sandbox import Sandbox

PRIMER = ("A distributed cache keeps hot data in memory near the service: Redis or Memcached, with eviction policies, "
          "time-to-live, cache-aside or write-through patterns, and invalidation on writes. ") * 6
GOOD, DEAD = "https://learn.example.org/caching", "https://gone.example.org/old-guide"

class Prep(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(); self.sb.setup_profile(self)
        fx = self.sb.root / "fixtures"; fx.mkdir()
        (fx / "index.json").write_text(json.dumps({f"LINK {GOOD}": 200, f"LINK {DEAD}": 404}), encoding="utf-8")
        self.sb.env_extra = {"FOUNDRY_FIXTURES": str(fx)}
        for f in ({"kind": "achievement", "text": "Cut search API p99 latency from 900 ms to 250 ms by adding a Redis cache",
                   "employer": "Acme Cloud", "status": "confirmed", "source": "user"},
                  {"kind": "responsibility", "text": "Prepared the weekly on-call report for 12 services", "employer": "Acme Cloud",
                   "status": "confirmed", "source": "user"},
                  {"kind": "achievement", "text": "Salary 12 LPA", "status": "confirmed", "private": True, "source": "user"}):
            self.sb.write("data/tmp/f.json", f); self.sb.ok(self, "facts.py", "add", "@data/tmp/f.json")
        self.sb.write("data/tmp/j.json", {"company": "Acme Cloud", "title": "Senior Backend Engineer", "location": "Pune",
                                          "source": {"tier": 3, "via": "pasted"}})
        self.sb.write("data/tmp/jd.txt", "Senior Backend Engineer. Own the search API: p99 latency, caching with Redis or Memcached, "
                      "Kafka events and Grafana dashboards for 30 services. " * 2)
        self.sb.ok(self, "jobs.py", "add", "@data/tmp/j.json", "--jd-file", "data/tmp/jd.txt")

    def tearDown(self): self.sb.close()

    def save_check(self, gaps):
        fit = {"level": "lateral", "pay": "ask", "location": "home", "match": 70, "likeliness": 50, "verdict": "good", "gaps": gaps}
        self.sb.write("data/tmp/c.json", {"jobs": [{"id": "j-0001", "fit": fit}]})
        self.sb.ok(self, "jobs.py", "check", "@data/tmp/c.json")

    def gap(self, **over):
        g = {"gap": "Distributed caching with Redis", "primer": PRIMER,
             "expect": ["Choose cache-aside or write-through and explain why", "Measure hit rate and latency before and after"],
             "questions": [{"q": "How did you make an API faster?", "answer": "I cut search API p99 latency from 900 ms to 250 ms by adding a Redis cache.", "facts": ["f-0001"]},
                           {"q": "How do you report on reliability?", "answer": "I prepared the weekly on-call report for 12 services.", "facts": ["f-0002"]},
                           {"q": "Have you run Memcached in production?", "answer": "Not yet on my own; I would start from the eviction metrics.", "bridge": False}],
             "quiz": [{"q": f"Question {i}?", "a": f"Answer {i}."} for i in range(5)],
             "resources": [{"title": "Caching guide", "url": GOOD}]}
        g.update(over); return g

    def save(self, *gaps):
        self.sb.write("data/tmp/p.json", {"gaps": list(gaps)})
        return self.sb.run("prep.py", "save", "j-0001", "@data/tmp/p.json")

    def test_gaps_need_a_check_first(self):
        self.sb.fails(self, "prep.py", "gaps", "j-0001", contains="run /check")
        self.save_check([{"gap": "Caching", "closest": "f-0001"}, "Kafka"])
        out = self.sb.ok(self, "prep.py", "gaps", "j-0001")
        self.assertIn("gap 1: Caching  (closest: f-0001)", out); self.assertIn("gap 2: Kafka", out)

    def test_save_writes_files_and_claims(self):
        rc, out = self.save(self.gap())
        self.assertEqual(rc, 0, out)
        d = self.sb.home / "data" / "prep" / "j-0001"
        md = next(d.glob("01-distributed-caching-*.md")).read_text(encoding="utf-8")
        for part in ("## Primer", "## What interviewers expect", "**Q3.", "## Quiz", "<details>", f"]({GOOD})", "<!-- facts: f-0001 -->"):
            self.assertIn(part, md)
        claims = self.sb.json("data/prep/j-0001/claims.json")
        self.assertEqual(len(claims), 2)   # the honest no-bridge answer cites nothing and isn't a claim
        self.assertTrue(self.sb.json("data/prep/j-0001/prep.json")["links"][GOOD]["ok"])
        self.assertIn("01-distributed", self.sb.ok(self, "prep.py", "show", "j-0001"))

    def test_invented_numbers_private_facts_and_dead_links_refuse(self):
        g = self.gap()
        g["questions"][0] = {"q": "Scale?", "answer": "I cut latency across 300 services.", "facts": ["f-0001"]}
        g["questions"][1] = {"q": "Pay?", "answer": "I earn 12 LPA.", "facts": ["f-0003"]}
        g["resources"].append({"title": "Old guide", "url": DEAD})
        rc, out = self.save(g)
        self.assertEqual(rc, 1, out)
        for msg in ("NOT SAVED", "numbers not in the cited facts: 300", "f-0003 is private", f"dead link {DEAD}"):
            self.assertIn(msg, out)
        self.assertFalse((self.sb.home / "data" / "prep" / "j-0001").exists())

    def test_shape_rules(self):
        rc, out = self.save(self.gap(primer="Too short.", expect=["one"], questions=self.gap()["questions"][:2], quiz=[], resources=[]))
        self.assertEqual(rc, 1)
        for msg in ("primer is under 600", "at least 2 things", "exactly 3 likely questions", "at least 5 quiz", "at least one free resource"):
            self.assertIn(msg, out)
        g = self.gap(); g["questions"][2] = {"q": "Tools?", "answer": "I used Kafka at Beta Pay.", "bridge": False}
        rc, out = self.save(g)
        self.assertIn("cites no fact", out)   # a no-bridge answer that names things from outside the topic needs a citation

    def test_naming_the_topic_is_not_a_claim(self):
        g = self.gap()
        g["questions"][0] = {"q": "Have you used Memcached?", "answer": "Not Memcached yet; I cut search API p99 latency from 900 ms to 250 ms by adding a Redis cache.", "facts": ["f-0001"]}
        g["questions"][2] = {"q": "Where would you start?", "answer": "I would compare Redis and Memcached eviction policies first.", "bridge": False}
        rc, out = self.save(g)
        self.assertEqual(rc, 0, out)

    def test_links_and_blocked_hosts(self):
        out = self.sb.fails(self, "prep.py", "links", GOOD, DEAD)
        self.assertIn(f"ok    {GOOD}", out); self.assertIn(f"DEAD  {DEAD}", out)
        self.assertIn("never fetched", self.sb.fails(self, "fetch.py", "link", "https://www.linkedin.com/learning/x"))
        self.assertIn("only https", self.sb.fails(self, "fetch.py", "link", "http://learn.example.org/"))

class GrillScores(unittest.TestCase):
    def setUp(self): self.sb = Sandbox()
    def tearDown(self): self.sb.close()

    def test_scores_are_final_and_weakest_first(self):
        f = self.sb.ok(self, "grill_clock.py", "start", "j-0001").strip()
        for n, (area, sc) in enumerate((("Kafka", 8), ("caching", 4), ("Kafka", 6), ("commercial", 5)), 1):
            self.sb.ok(self, "grill_clock.py", "ask", f, f"Q{n}?")
            self.sb.fails(self, "grill_clock.py", "score", f, str(n), "5", "--area", area, contains="isn't logged")
            self.sb.ok(self, "grill_clock.py", "answer", f, "an answer")
            self.sb.ok(self, "grill_clock.py", "score", f, str(n), str(sc), "--area", area)
        self.sb.fails(self, "grill_clock.py", "score", f, "1", "9", "--area", "Kafka", contains="already scored")
        self.sb.fails(self, "grill_clock.py", "score", f, "2", "11", "--area", "x", contains="0-10")
        out = self.sb.ok(self, "grill_clock.py", "weakest", f).splitlines()
        self.assertEqual([l.split()[0] for l in out], ["caching", "commercial", "Kafka"])
        self.assertIn("7.0/10", out[2])

if __name__ == "__main__":
    unittest.main()
