"""Tailoring: claim checks (truth rule), PDF + DOCX rendering from one resume.json, parity, ATS lint, render log."""
import copy, json, sys, unittest
from sandbox import Sandbox, JD, FIXTURES
sys.path.insert(0, str(FIXTURES / "tailor"))
import profile as P   # tests/fixtures/tailor/profile.py

class Tailor(unittest.TestCase):
    def setUp(self):
        self.sb = sb = Sandbox(pack="software-eng")
        sb.setup_profile(self, title="Senior Software Engineer", ctc=14)
        sb.write("profile/identity.json", P.IDENTITY)
        sb.write("profile/employment.json", P.EMPLOYMENT)
        sb.write("profile/education.json", P.EDUCATION)
        sb.write("data/tmp/f.json", P.FACTS); sb.ok(self, "facts.py", "add", "@data/tmp/f.json")
        sb.write("data/tmp/j.json", {"company": "Acme Cloud", "title": "Senior Backend Engineer", "url": "https://boards.greenhouse.io/acmecloud/jobs/9",
                                     "location": "Noida", "source": {"tier": 1, "via": "greenhouse"}})
        sb.ok(self, "jobs.py", "add", "@data/tmp/j.json", "--jd-file", sb.write("data/tmp/jd.txt", JD))
        self.v = "data/tailored/j-0001/v1"
        self.put(P.RESUME, P.NOTES)
    def tearDown(self): self.sb.close()

    def put(self, resume, notes=None):
        self.sb.write(f"{self.v}/resume.json", resume)
        if notes is not None: self.sb.write(f"{self.v}/notes.md", notes)

    def test_supported_resume_passes_and_renders_both(self):
        self.assertIn("lines trace to confirmed facts", self.sb.ok(self, "claims.py", "j-0001/v1"))
        out = self.sb.ok(self, "render.py", "j-0001/v1")
        self.assertIn("PDF: Resumes/Acme Cloud - Senior Backend Engineer/Riya_Testwal_Resume.pdf", out)
        self.assertIn("DOCX:", out); self.assertEqual(out.count("same words, same order"), 2)
        checks = self.sb.json(f"{self.v}/checks.json")
        self.assertEqual(checks["render"]["lint"]["pdf"]["problems"], []); self.assertEqual(checks["render"]["lint"]["pdf"]["pages"], 1)
        renders = self.sb.jsonl("data/renders.jsonl")
        self.assertEqual({r["format"] for r in renders}, {"pdf", "docx"})
        claims = self.sb.json(f"{self.v}/claims.json")
        self.assertEqual(claims["Migrated 18 services from VMs onto Kubernetes."], ["f-0003"])

    def test_render_refuses_before_claims_pass(self):
        self.sb.fails(self, "render.py", "j-0001/v1", contains="run claims.py")

    def test_numbers_and_names_must_be_in_cited_facts(self):
        r = copy.deepcopy(P.RESUME)
        r["sections"][1]["roles"][0]["bullets"][0]["text"] = "Cut checkout API p99 latency from 820 ms to 250 ms for 1.2 million daily users."
        r["sections"][1]["roles"][1]["bullets"][0]["text"] = "Migrated 18 services from VMs onto Kubernetes using Nomad."
        self.put(r)
        out = self.sb.fails(self, "claims.py", "j-0001/v1")
        self.assertIn("numbers not in the cited facts: 250", out); self.assertIn("names or terms not in the cited facts: Nomad", out)
        self.assertFalse(self.sb.json(f"{self.v}/checks.json")["claims"]["passed"])

    def test_synonyms_count_as_support(self):
        r = copy.deepcopy(P.RESUME)
        r["sections"][1]["roles"][1]["bullets"][0]["text"] = "Migrated 18 services from VMs onto K8s."
        self.put(r)
        self.sb.ok(self, "claims.py", "j-0001/v1")

    def test_uncited_draft_private_and_unknown_facts_fail(self):
        r = copy.deepcopy(P.RESUME)
        b = r["sections"][1]["roles"][0]["bullets"]
        b.append({"text": "Rolled out tracing on 30 services.", "facts": ["f-0007"]})
        b.append({"text": "Earns well.", "facts": ["f-0006"]})
        b.append({"text": "Strong team player.", "facts": []})
        b.append({"text": "Did more.", "facts": ["f-0099"]})
        r["sections"][2]["lines"][0]["items"].append("Tableau")
        self.put(r)
        out = self.sb.fails(self, "claims.py", "j-0001/v1")
        for msg in ("f-0007 isn't confirmed (draft)", "f-0006 is private", "cites no fact", "f-0099 doesn't exist", "this skill isn't mentioned"):
            self.assertIn(msg, out)

    def test_notes_citations_are_checked(self):
        self.put(P.RESUME, P.NOTES.replace("<!-- facts: f-0002 -->", ""))
        self.assertIn("cites no fact", self.sb.fails(self, "claims.py", "j-0001/v1"))
        self.put(P.RESUME, P.NOTES.replace("42 services <!-- facts: f-0002 -->", "60 services <!-- facts: f-0002 -->"))
        self.assertIn("numbers not in the cited facts: 60", self.sb.fails(self, "claims.py", "j-0001/v1"))

    def test_pdf_only_and_applied_with_tailored_version(self):
        self.sb.ok(self, "claims.py", "j-0001/v1")
        self.sb.ok(self, "render.py", "j-0001/v1", "--format", "pdf")
        self.sb.write("data/tmp/a.json", {"job": "j-0001", "date": "2026-10-25", "channel": "careers_site"})
        out = self.sb.ok(self, "jobs.py", "applied", "@data/tmp/a.json", "--tailored", "j-0001/v1")
        self.assertIn("(render j-0001 v1)", out)
        self.sb.ok(self, "validate.py")

    def test_ats_keywords_and_docx_lint(self):
        self.sb.ok(self, "claims.py", "j-0001/v1")
        out = self.sb.ok(self, "ats.py", "keywords", "j-0001/v1")
        self.assertIn("Kubernetes", out.split("Missing")[0]); self.assertIn("Kafka", out.split("Missing")[1])
        import docx
        d = docx.Document(); d.add_paragraph("x"); d.add_table(rows=1, cols=2); d.sections[0].header.paragraphs[0].text = "Name | phone"
        p = self.sb.home / "bad.docx"; d.save(str(p))
        out = self.sb.fails(self, "ats.py", "lint", p)
        self.assertIn("table", out); self.assertIn("header or footer", out)

if __name__ == "__main__":
    unittest.main()
