"""Job-search APIs (Adzuna, Jooble, JSearch) against responses built from each API's documented shape; keys in a fake
vault (never the real Credential Manager); caps; key redaction; the prefilter and dedupe."""
import json, os, unittest
from urllib.parse import urlencode
from sandbox import Sandbox, REPO

ADZ_ID, ADZ_KEY, JOOBLE, JSEARCH = "adz-id-" + "1234", "adz-key-" + "abcd", "jooble-" + "k3y", "jsearch-" + "k3y"
TITLE = "senior backend engineer"   # an area phrase from the pack plus their level word; the APIs ignore case

def adzuna_url(title, cc="in", where=""):
    q = urlencode({"app_id": ADZ_ID, "app_key": ADZ_KEY, "what": title, "where": where, "results_per_page": 50, "max_days_old": 14,
                   "content-type": "application/json"})
    return f"GET https://api.adzuna.com/v1/api/jobs/{cc}/search/1?{q}".replace(ADZ_ID, "***").replace(ADZ_KEY, "***")

def jsearch_url(title, place, cc):
    return "GET https://jsearch.p.rapidapi.com/search?" + urlencode({"query": f"{title} in {place}", "page": 1, "num_pages": 1, "date_posted": "week", "country": cc})

ADZUNA = {"count": 3, "results": [
    {"id": "4101", "title": "<strong>Senior</strong> Backend Engineer - Payments", "company": {"display_name": "Sigma Software"},
     "location": {"display_name": "Pune, Maharashtra", "area": ["India", "Maharashtra", "Pune"]}, "created": "2026-10-20T08:00:00Z",
     "redirect_url": "https://www.adzuna.in/land/ad/4101", "description": "Own payment APIs serving 1 million users..."},
    {"id": "4102", "title": "Software Engineer 1 - Backend", "company": {"display_name": "Sigma Software"},
     "location": {"display_name": "Pune"}, "created": "2026-10-20T08:00:00Z", "redirect_url": "https://www.adzuna.in/land/ad/4102", "description": "x"},
    {"id": "4103", "title": "Senior Software Engineer - Backend", "company": {"display_name": "Tau Fintech"},
     "location": {"display_name": "Chennai, Tamil Nadu"}, "created": "2026-10-21T08:00:00Z", "redirect_url": "https://www.adzuna.in/land/ad/4103",
     "description": "Payments backend in Go"}]}
JOOBLE_RESP = {"totalCount": 2, "jobs": [
    {"title": "Senior Software Engineer - Backend", "location": "Chennai, Tamil Nadu", "snippet": "Payments <b>backend</b> in Go", "company": "Tau Fintech",
     "link": "https://jooble.org/desc/77", "updated": "2026-10-22T00:00:00", "id": 77},
    {"title": "Data Analyst – Grid", "location": "Hyderabad", "snippet": "Grid", "company": "Upsilon Data",
     "link": "https://jooble.org/desc/78", "updated": "2026-10-22T00:00:00", "id": 78}]}
JSEARCH_RESP = {"status": "OK", "data": [
    {"job_id": "js-1", "employer_name": "Phi Systems", "job_title": "Staff Engineer - Backend", "job_city": "Dubai", "job_state": None,
     "job_country": "AE", "job_apply_link": "https://www.linkedin.com/jobs/view/99", "job_is_remote": False,
     "job_posted_at_datetime_utc": "2026-10-23T00:00:00.000Z", "job_description": "Own API latency, availability and incident response for a 2,000 RPS platform. " * 6}]}

class JobApis(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(pack="software-eng")
        self.sb.setup_profile(self, title="Senior Software Engineer", ctc=30, target_families=["backend"],
                              locations={"abroad": [{"country": "AE", "cities": ["Dubai"]}]})
        self.fx = self.sb.root / "fx"; self.fx.mkdir()
        self.sb.env_extra = {"FOUNDRY_FIXTURES": str(self.fx), "PYTHON_KEYRING_BACKEND": "fake_keyring.FakeKeyring",
                             "FAKE_KEYRING_FILE": str(self.sb.root / "vault.json"),
                             "PYTHONPATH": str(REPO / "tests") + os.pathsep + os.environ.get("PYTHONPATH", "")}
        self.index = {}

    def tearDown(self): self.sb.close()

    def vault(self, **kv):
        (self.sb.root / "vault.json").write_text(json.dumps({f"foundry-kit/{k}": v for k, v in kv.items()}), encoding="utf-8")

    def serve(self, key, body):
        name = f"r{len(self.index)}.json"
        (self.fx / name).write_text(json.dumps(body), encoding="utf-8"); self.index[key] = name
        (self.fx / "index.json").write_text(json.dumps(self.index), encoding="utf-8")

    def test_queries_follow_her_places_in_order_at_her_level(self):
        out = self.sb.ok(self, "job_apis.py", "queries").splitlines()
        self.assertTrue(out[0].startswith("IN  India")); self.assertTrue(out[-1].startswith("AE  Dubai"))
        self.assertIn(TITLE, out[0])
        self.assertNotIn("software engineer 1", " ".join(out))   # a title below their level is never searched

    def test_no_keys_means_skipped_not_failed(self):
        out = self.sb.ok(self, "job_apis.py")
        self.assertEqual(out.count("no key (optional"), 3, out)

    def test_adapters_prefilter_dedupe_and_redact(self):
        self.vault(adzuna_app_id=ADZ_ID, adzuna_app_key=ADZ_KEY, jooble_key=JOOBLE, jsearch_key=JSEARCH)
        self.serve(adzuna_url(TITLE), ADZUNA)
        self.serve('POST https://jooble.org/api/*** {"keywords":"%s","location":"India","page":"1"}' % TITLE, JOOBLE_RESP)
        self.serve(jsearch_url(TITLE, "Dubai", "ae"), JSEARCH_RESP)
        out = self.sb.ok(self, "job_apis.py")
        jobs = {(j["company"], j["title"]): j for j in self.sb.json("data/jobs.json")["jobs"]}
        self.assertIn(("Sigma Software", "Senior Backend Engineer - Payments"), jobs)   # Adzuna's <strong> tags stripped
        self.assertNotIn(("Sigma Software", "Software Engineer 1 - Backend"), jobs)   # below their level
        tau = [k for k in jobs if k[0] == "Tau Fintech"]
        self.assertEqual(len(tau), 1, out)   # the same Chennai role from Adzuna and Jooble is one job
        phi = jobs[("Phi Systems", "Staff Engineer - Backend")]
        self.assertEqual((phi["source"]["tier"], phi["source"]["via"]), (2, "jsearch"))
        self.assertTrue(phi["jd"])           # JSearch carries the full description
        self.assertEqual(phi["url"], "https://www.linkedin.com/jobs/view/99")   # kept as a reference, never fetched
        sigma = jobs[("Sigma Software", "Senior Backend Engineer - Payments")]
        self.assertIsNone(sigma["jd"]); self.assertIn("1 million", sigma["snippet"])   # a snippet is not a JD
        for p in (self.sb.home / "data").rglob("*"):
            if p.is_file():
                t = p.read_text(encoding="utf-8", errors="replace")
                for k in (ADZ_ID, ADZ_KEY, JOOBLE, JSEARCH): self.assertNotIn(k, t, f"key in {p}")
        for k in (ADZ_ID, ADZ_KEY, JOOBLE, JSEARCH): self.assertNotIn(k, out)
        self.assertIn("today", self.sb.ok(self, "job_apis.py", "usage"))

    def test_caps_stop_calls(self):
        self.vault(jsearch_key=JSEARCH)
        self.sb.write("data/api_usage.json", {"jsearch": {"day": "2026-10-25", "day_calls": 0, "month": "2026-10", "month_calls": 150}})
        out = self.sb.ok(self, "job_apis.py", "--only", "jsearch")
        self.assertIn("cap reached", out)
        self.assertEqual(self.sb.json("data/api_usage.json")["jsearch"]["month_calls"], 150)

    def test_keys_status_never_shows_a_key(self):
        self.vault(jooble_key=JOOBLE)
        out = self.sb.ok(self, "keys.py", "status")
        self.assertIn("jooble   stored", out); self.assertIn("adzuna   not set", out); self.assertNotIn(JOOBLE, out)
        self.assertIn("its own window", self.sb.fails(self, "keys.py", "set", "adzuna", stdin=""))
        self.sb.ok(self, "keys.py", "remove", "jooble")
        self.assertIn("jooble   not set", self.sb.ok(self, "keys.py", "status"))

if __name__ == "__main__":
    unittest.main()
