"""Board watch: an open application's posting missing from its board on two sweeps, or answering 404, is flagged for
the user to confirm; it never closes the application; a 403 alone is not enough."""
import json, os, shutil, subprocess, sys, unittest
from sandbox import Sandbox, FIXTURES, ENGINE

class BoardWatch(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(pack="software-eng"); self.sb.setup_profile(self, title="Senior Software Engineer", ctc=30)
        shutil.copy(FIXTURES / "radar_test.json", self.sb.home / "data" / "radar.json")
        self.sb.env_extra = {"FOUNDRY_FIXTURES": str(FIXTURES / "http")}
        self.sb.ok(self, "sweep.py", "--company", "Acme Cloud")
        j = next(j for j in self.sb.json("data/jobs.json")["jobs"] if j["company"] == "Acme Cloud")
        self.sb.write("inbox/cv.pdf", b"%PDF-1.4\n%%EOF\n")
        self.sb.write("data/tmp/a.json", {"job": j["id"], "date": "2026-10-25", "channel": "careers_site"})
        self.sb.ok(self, "jobs.py", "applied", "@data/tmp/a.json", "--resume", "inbox/cv.pdf")
        self.job = j

    def tearDown(self): self.sb.close()

    def update(self, posts, code, now):
        code_s = ("import json, sys, board_watch; posts = json.loads(sys.argv[1]); code = sys.argv[2];"
                  "print(json.dumps(board_watch.update({'Acme Cloud': posts}, probe_fn=lambda u: None if code == 'none' else int(code))))")
        p = subprocess.run([sys.executable, "-c", code_s, json.dumps(posts), code], capture_output=True, text=True, encoding="utf-8", cwd=str(ENGINE),
                           env=dict(os.environ, FOUNDRY_HOME=str(self.sb.home), FOUNDRY_NOW=now, PYTHONIOENCODING="utf-8"))
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_two_misses_flag_and_seen_clears(self):
        self.assertEqual(self.update([], "403", "2026-10-26T08:00:00"), [])                       # one miss, and a 403: not yet
        self.assertEqual(self.update([], "403", "2026-10-26T18:00:00"), [])                       # same day: still one miss
        f = self.update([], "none", "2026-10-27T08:00:00")
        self.assertEqual((len(f), f[0]["new"]), (1, True)); self.assertIn("missing from 2 sweeps", f[0]["why"])
        self.assertIn("no longer on its board", self.sb.ok(self, "today.py", now="2026-10-27T09:00:00"))
        self.assertEqual(self.sb.json("data/apps.json")["apps"][0]["status"], "applied")         # never closed
        self.assertEqual(self.update([{"url": self.job["url"]}], "200", "2026-10-28T08:00:00"), [])   # back on the board
        self.assertNotIn("no longer on its board", self.sb.ok(self, "today.py", now="2026-10-28T09:00:00"))

    def test_404_flags_at_once(self):
        f = self.update([], "404", "2026-10-26T08:00:00")
        self.assertIn("HTTP 404", f[0]["why"])

if __name__ == "__main__":
    unittest.main()
