"""Static careers pages: following pagination (rel=next, a Next link, SuccessFactors startrow, ?page=N), the page
cap, and stopping when a page adds nothing new."""
import json, os, subprocess, sys, unittest
from sandbox import Sandbox, ENGINE

BASE = "https://careers.omega.example.com"

def page(jobs, extra=""):
    rows = "".join(f'<li><a href="/job/{slug}/{n}/">{title}</a></li>' for n, slug, title in jobs)
    return f"<html><body><ul>{rows}</ul>{extra}</body></html>"

def jobs(a, b): return [(n, f"role-{n}", f"Senior Backend Engineer {n}") for n in range(a, b)]

class Pagination(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(pack="software-eng")
        self.fx = self.sb.root / "fx"; self.fx.mkdir()
        self.index = {}

    def tearDown(self): self.sb.close()

    def serve(self, url, html):
        name = f"p{len(self.index)}.html"
        (self.fx / name).write_text(html, encoding="utf-8")
        self.index[f"GET {url}"] = name

    def read(self, jobs_url):
        (self.fx / "index.json").write_text(json.dumps(self.index), encoding="utf-8")
        self.sb.write("data/radar.json", {"companies": [{"company": "Omega", "careers_url": BASE + "/", "segment": "ipp", "india_office": False,
                      "portal": {"type": "static", "tier": 1, "jobs_url": jobs_url}, "how": "", "families": [], "every_days": 7,
                      "added": "2026-10-01", "checks": [], "source": "user"}]})
        code = "import json, radar, sources; print(json.dumps([p['title'] for p in sources.openings(radar.find(radar.load_radar(), 'Omega'))]))"
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", cwd=str(ENGINE),
                           env=dict(os.environ, FOUNDRY_HOME=str(self.sb.home), FOUNDRY_FIXTURES=str(self.fx), PYTHONIOENCODING="utf-8"))
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_successfactors_startrow(self):
        url = BASE + "/search/?q="
        self.serve(url, page(jobs(0, 10), "<span>Showing 1 to 10 of 25 Jobs</span>"))
        self.serve(url + "&startrow=10", page(jobs(10, 20), "<span>Showing 11 to 10 of 25 Jobs</span>"))   # later labels are often wrong
        self.serve(url + "&startrow=20", page(jobs(20, 25)))
        self.assertEqual(len(self.read(url)), 25)

    def test_rel_next_and_next_link(self):
        url = BASE + "/jobs"
        self.serve(url, page(jobs(0, 5), '<a rel="next" href="/jobs?pg=2">2</a>'))
        self.serve(BASE + "/jobs?pg=2", page(jobs(5, 10), '<a href="/jobs?pg=3">Next</a>'))
        self.serve(BASE + "/jobs?pg=3", page(jobs(10, 12)))
        self.assertEqual(len(self.read(url)), 12)

    def test_page_number_links_and_stop_when_nothing_new(self):
        url = BASE + "/openings"
        self.serve(url, page(jobs(0, 5), '<a href="/openings?page=2">2</a>'))
        self.serve(BASE + "/openings?page=2", page(jobs(5, 8), '<a href="/openings?page=3">3</a>'))
        self.serve(BASE + "/openings?page=3", page(jobs(5, 8), '<a href="/openings?page=4">4</a>'))   # repeats page 2: stop here
        self.assertEqual(len(self.read(url)), 8)

    def test_cap_and_a_failing_later_page(self):
        url = BASE + "/all"
        for n in range(1, 13):
            u = url if n == 1 else f"{BASE}/all/page/{n}/"
            self.serve(u, page(jobs(n * 10, n * 10 + 3), f'<a href="/all/page/{n + 1}/">Next</a>'))
        self.assertEqual(len(self.read(url)), 30)   # 10 pages at most
        self.index.pop(f"GET {BASE}/all/page/4/")
        self.assertEqual(len(self.read(url)), 9)    # page 4 is missing: what was read so far stands

if __name__ == "__main__":
    unittest.main()
