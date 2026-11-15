"""Sources added in revision 3: Oracle HCM Candidate Experience, company job APIs (amazon.jobs, Eightfold), Workday
location facets and page limits; detection of Candidate Experience links. Recorded responses, invented companies."""
import json, os, subprocess, sys, unittest
from urllib.parse import urlencode
from sandbox import Sandbox, ENGINE

ORA = "omega.fa.em2.oraclecloud.com"

def oracle_list(site, rows, total):
    return {"items": [{"TotalJobsCount": total, "requisitionList": rows}]}

class CompanySources(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox(pack="software-eng")
        self.fx = self.sb.root / "fx"; self.fx.mkdir(); self.index = {}

    def tearDown(self): self.sb.close()

    def serve(self, key, body):
        name = f"r{len(self.index)}.json"
        (self.fx / name).write_text(json.dumps(body), encoding="utf-8"); self.index[key] = name
        (self.fx / "index.json").write_text(json.dumps(self.index), encoding="utf-8")

    def openings(self, company, portal, jd=False):
        self.sb.write("data/radar.json", {"companies": [{"company": company, "careers_url": "https://careers.omega.example.com/", "segment": "big-tech",
                      "india_office": True, "portal": portal, "how": "", "families": [], "every_days": 7, "added": "2026-11-01", "checks": [], "source": "user"}]})
        code = ("import json, sys, radar, sources; c = radar.find(radar.load_radar(), sys.argv[1]); ps = sources.openings(c);"
                "print(json.dumps({'rows': ps, 'jd': sources.jd_text(c, ps[0]) if ps and sys.argv[2] == '1' else None}))")
        p = subprocess.run([sys.executable, "-c", code, company, "1" if jd else "0"], capture_output=True, text=True, encoding="utf-8", cwd=str(ENGINE),
                           env=dict(os.environ, FOUNDRY_HOME=str(self.sb.home), FOUNDRY_FIXTURES=str(self.fx), PYTHONIOENCODING="utf-8"))
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_detect_oracle_candidate_experience(self):
        d = json.loads(self.sb.ok(self, "radar.py", "detect", f"https://{ORA}/hcmUI/CandidateExperience/en/sites/CX_7/requisitions"))
        self.assertEqual(d, {"type": "oraclehcm", "tier": 1, "host": ORA, "site": "CX_7"})
        self.assertEqual(json.loads(self.sb.ok(self, "radar.py", "detect", f"https://{ORA}/hcmUI/"))["tier"], 3)   # no site number: paste-in

    def test_oraclehcm_pages_and_detail(self):
        base = (f"GET https://{ORA}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList"
                f"&finder=findReqs;siteNumber=CX_7,limit=200,offset={{}},sortBy=POSTING_DATES_DESC")
        page1 = [{"Id": str(100 + i), "Title": f"Senior Backend Engineer {i}", "PrimaryLocation": "Bengaluru, Karnataka, India",
                  "PostedDate": "2026-11-10", "WorkplaceType": "Hybrid"} for i in range(200)]
        self.serve(base.format(0), oracle_list("CX_7", page1, 203))
        self.serve(base.format(200), oracle_list("CX_7", [{"Id": "900", "Title": "Staff Engineer", "PrimaryLocation": "Remote, India",
                                                            "PostedDate": "2026-11-12", "WorkplaceType": "Remote"}] * 3, 203))
        self.serve(f"GET https://{ORA}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?expand=all&onlyData=true&finder=ById;Id=%22100%22,siteNumber=CX_7",
                   {"items": [{"ExternalDescriptionStr": "<p>Build payment APIs in Go.</p>", "ExternalQualificationsStr": "<ul><li>5+ years of backend experience</li></ul>"}]})
        out = self.openings("Omega Bank", {"type": "oraclehcm", "tier": 1, "host": ORA, "site": "CX_7"}, jd=True)
        rows = out["rows"]
        self.assertEqual(len(rows), 203)
        self.assertEqual(rows[0]["url"], f"https://{ORA}/hcmUI/CandidateExperience/en/sites/CX_7/job/100")
        self.assertTrue(rows[-1]["remote"]); self.assertEqual(rows[0]["posted"], "2026-11-10")
        self.assertIn("Build payment APIs in Go.", out["jd"]); self.assertIn("5+ years of backend experience", out["jd"])

    def test_amazon_style_search_api(self):
        q = urlencode([("base_query", ""), ("loc_query", "India"), ("country", "IND"), ("city", ""), ("sort", "recent"), ("result_limit", 100),
                       ("offset", 0), ("category[]", "software-development")])
        self.serve(f"GET https://www.amazon.jobs/en/search.json?{q}", {"hits": 1, "jobs": [
            {"id_icims": "777", "title": "Software Development Engineer II", "normalized_location": "Hyderabad, Telangana, IND",
             "job_path": "/en/jobs/777/sde-ii", "posted_date": "November  3, 2026", "description": "Own a fulfilment service.",
             "basic_qualifications": "- 3+ years of non-internship professional software development experience"}]})
        rows = self.openings("Omega Retail", {"type": "amazon", "tier": 1, "loc_query": "India", "country": "IND", "categories": ["software-development"]})["rows"]
        self.assertEqual(rows[0]["url"], "https://www.amazon.jobs/en/jobs/777/sde-ii"); self.assertEqual(rows[0]["posted"], "2026-11-03")
        self.assertIn("Basic qualifications", rows[0]["jd_text"])

    def test_eightfold_api_and_a_failure_turns_paste_in(self):
        host = "careers.omega.example.com"
        q = lambda start: urlencode({"domain": "omega.example.com", "query": "", "location": "India", "start": start, "sort_by": "timestamp"})
        self.serve(f"GET https://{host}/api/pcsx/search?{q(0)}", {"data": {"count": 2, "positions": [
            {"id": 11, "name": "Senior Software Engineer", "locations": ["India, Karnataka, Bangalore"], "postedTs": 1794559068, "workLocationOption": "onsite"},
            {"id": 12, "name": "Principal Engineer", "locations": ["India, Telangana, Hyderabad"], "postedTs": 1794559068, "workLocationOption": "remote"}]}})
        self.serve(f"GET https://{host}/api/pcsx/position_details?position_id=11&domain=omega.example.com&hl=en", {"data": {"jobDescription": "<p>Azure storage.</p>"}})
        portal = {"type": "eightfold", "tier": 1, "host": host, "domain": "omega.example.com", "location": "India"}
        out = self.openings("Omega Soft", portal, jd=True)
        self.assertEqual([r["title"] for r in out["rows"]], ["Senior Software Engineer", "Principal Engineer"])
        self.assertTrue(out["rows"][1]["remote"]); self.assertEqual(out["jd"], "Azure storage.")
        # the API stops answering: the sweep reports it and treats the company as paste-in for that run
        (self.fx / "index.json").write_text("{}", encoding="utf-8")
        self.sb.write("data/radar.json", {"companies": [{"company": "Omega Soft", "careers_url": f"https://{host}/careers", "segment": "big-tech", "india_office": True,
                      "portal": portal, "how": "", "families": [], "every_days": 7, "added": "2026-11-01", "checks": [], "source": "user"}]})
        self.sb.setup_profile(self, title="Senior Software Engineer", ctc=30)
        self.sb.env_extra = {"FOUNDRY_FIXTURES": str(self.fx)}
        self.assertIn("Switched to paste-in", self.sb.ok(self, "sweep.py", "--company", "Omega Soft"))

    def test_workday_facets_and_page_limit(self):
        host, body = "omega.wd3.myworkdayjobs.com", {"appliedFacets": {"locationCountry": ["c4f7"]}, "limit": 20, "offset": 0, "searchText": ""}
        self.serve(f"POST https://{host}/wday/cxs/omega/Careers/jobs " + json.dumps(body, sort_keys=True, separators=(",", ":")),
                   {"total": 40, "jobPostings": [{"title": f"Senior Backend Engineer {i}", "externalPath": f"/job/x/{i}", "locationsText": "Pune"} for i in range(20)]})
        rows = self.openings("Omega Works", {"type": "workday", "tier": 1, "host": host, "tenant": "omega", "site": "Careers",
                                             "facets": {"locationCountry": ["c4f7"]}, "max_pages": 1})["rows"]
        self.assertEqual(len(rows), 20)   # one page only: max_pages 1, read by facet with no keyword

class Robots(unittest.TestCase):
    """RFC 9309: the longest matching rule wins, allow wins a tie, and a group naming the agent beats *."""
    def check(self, lines, path):
        sys.path.insert(0, str(ENGINE))
        import fetch
        return fetch.robots_allows(fetch.robots_rules("\n".join(lines)), path)

    def test_longest_match(self):
        txt = ["User-agent: *", "Disallow: /", "Allow: /$", "Allow: /api/pcsx", "Allow: /careers"]
        self.assertTrue(self.check(txt, "/api/pcsx/search?q=x"))   # Python's robotparser says no: first rule wins there
        self.assertTrue(self.check(txt, "/"))
        self.assertFalse(self.check(txt, "/api/apply/secret"))
        self.assertFalse(self.check(["User-agent: *", "Disallow: /jobs/*.json$"], "/jobs/list.json"))
        self.assertTrue(self.check(["User-agent: *", "Disallow: /jobs/*.json$"], "/jobs/list.json?x=1"))

    def test_agent_group_and_tie(self):
        txt = ["User-agent: foundry-kit", "Disallow: /private", "", "User-agent: *", "Disallow: /"]
        self.assertTrue(self.check(txt, "/jobs")); self.assertFalse(self.check(txt, "/private/x"))
        self.assertTrue(self.check(["User-agent: *", "Allow: /a", "Disallow: /a"], "/a"))
        self.assertTrue(self.check([], "/anything"))

if __name__ == "__main__":
    unittest.main()
