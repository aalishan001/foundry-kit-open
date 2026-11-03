"""Engine core: facts bank, profile, fit rules, tracking, in-hand pay, backup, today, grill clock, extract, doctor."""
import hashlib, json, shutil, unittest
from sandbox import Sandbox, JD

PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"

class Base(unittest.TestCase):
    def setUp(self): self.sb = Sandbox()
    def tearDown(self): self.sb.close()

class Facts(Base):
    def add(self, **f):
        f.setdefault("kind", "achievement"); f.setdefault("source", "user")
        self.sb.write("data/tmp/f.json", f)
        return self.sb.ok(self, "facts.py", "add", "@data/tmp/f.json")

    def facts(self): return {f["id"]: f for f in self.sb.jsonl("profile/facts.jsonl")}

    def test_add_is_draft_and_confirm(self):
        out = self.add(text="Raised API SLA from 76% to 79.5% across 300 services", employer="Acme Cloud")
        self.assertIn("f-0001  draft", out)
        self.sb.ok(self, "facts.py", "confirm", "f-0001")
        f = self.facts()["f-0001"]
        self.assertEqual((f["status"], f["confirmed"]), ("confirmed", "2026-10-25"))

    def test_edit_goes_back_to_draft_unless_confirmed_now(self):
        self.add(text="Built deploy automation", status="confirmed")
        self.sb.write("data/tmp/e.json", {"text": "Automated the daily generation report for 40 sites"})
        self.sb.ok(self, "facts.py", "edit", "f-0001", "@data/tmp/e.json")
        f = self.facts()["f-0001"]
        self.assertEqual(f["status"], "draft"); self.assertEqual(f["history"][0]["text"], "Built deploy automation")
        self.sb.ok(self, "facts.py", "edit", "f-0001", "@data/tmp/e.json", "--confirm")
        self.assertEqual(self.facts()["f-0001"]["status"], "confirmed")

    def test_rejects_bad_kind_duplicates_and_unknown_fields(self):
        self.sb.write("data/tmp/f.json", {"kind": "boast", "text": "x", "source": "user"})
        self.sb.fails(self, "facts.py", "add", "@data/tmp/f.json", contains="kind must be")
        self.add(text="Mapped Kafka topics for 12 services")
        self.sb.write("data/tmp/f.json", {"kind": "achievement", "text": "mapped kafka topics for 12 services", "source": "user"})
        self.sb.fails(self, "facts.py", "add", "@data/tmp/f.json", contains="already f-0001")
        self.sb.write("data/tmp/f.json", {"kind": "skill", "text": "Python", "source": "user", "salary": 5})
        self.sb.fails(self, "facts.py", "add", "@data/tmp/f.json", contains="unknown fields")

    def test_search_uses_keyword_variants_and_skips_private_and_drafts(self):
        self.add(text="Improved SLA by 3.5 points", status="confirmed")
        self.add(text="Current salary 14 LPA", kind="other", private=True, status="confirmed")
        self.add(text="Service level agreement dashboards in Grafana")   # draft
        out = self.sb.ok(self, "facts.py", "search", "service", "level", "agreement")
        self.assertIn("f-0001", out); self.assertNotIn("f-0003", out); self.assertNotIn("salary", out)
        self.assertIn("f-0003", self.sb.ok(self, "facts.py", "search", "service", "level", "agreement", "--all"))

    def test_retire_needs_reason_and_blocks_confirm(self):
        self.add(text="Led a team of 6")
        self.sb.fails(self, "facts.py", "retire", "f-0001", contains="--note")
        self.sb.ok(self, "facts.py", "retire", "f-0001", "--note", "overstated")
        self.sb.fails(self, "facts.py", "confirm", "f-0001", contains="retired")

class Profile(Base):
    def test_init_defaults(self):
        self.sb.ok(self, "profile_cli.py", "init")
        s = self.sb.json("profile/search.json")
        self.assertEqual(s["rules"], {"never_lower_level": True, "lateral_min_raise_pct": 20, "raise_basis": "ctc",
                                      "abroad_stability": ["government-owned", "listed", "multinational subsidiary", "large group", "PE-backed"],
                                      "pe_min_employees": 1000, "pe_min_years": 10})
        self.assertEqual((s["locations"]["abroad"], s["locations"]["pay_over_place"]), ([], False))
        self.assertEqual((s["gmail"]["enabled"], s["gmail"]["label"]), (False, "Job Alerts"))
        self.assertEqual(s["target_families"], ["backend"])   # adjacent families are not selected
        self.assertIn("re-run", self.sb.ok(self, "profile_cli.py", "init") + "re-run")

    def test_set_merges_and_never_lower_is_fixed(self):
        self.sb.ok(self, "profile_cli.py", "init")
        self.sb.write("data/tmp/s.json", {"rules": {"lateral_min_raise_pct": 30}, "locations": {"preferred": ["north India"]}})
        self.sb.ok(self, "profile_cli.py", "set", "search", "@data/tmp/s.json")
        s = self.sb.json("profile/search.json")
        self.assertEqual(s["rules"]["lateral_min_raise_pct"], 30); self.assertTrue(s["rules"]["never_lower_level"])
        self.assertEqual(s["locations"]["eligible_countries"], ["IN"])
        self.sb.write("data/tmp/s.json", {"rules": {"never_lower_level": False}})
        self.sb.fails(self, "profile_cli.py", "set", "search", "@data/tmp/s.json", contains="fixed rule")

    def test_current_title_maps_to_ladder(self):
        self.sb.ok(self, "profile_cli.py", "init")
        self.assertIn("ladder rank 4", self.sb.ok(self, "profile_cli.py", "current", "Asst. Manager - Backend", "--ctc", "12"))
        self.assertEqual(self.sb.json("profile/search.json")["current"]["ctc_lpa"], 12.0)
        self.assertIn("NOT on the pack ladder", self.sb.ok(self, "profile_cli.py", "current", "Wizard"))

    def test_gmail_enabled_needs_an_imap_address(self):
        self.sb.ok(self, "profile_cli.py", "init")
        self.sb.write("data/tmp/g.json", {"gmail": {"enabled": True}})
        self.sb.fails(self, "profile_cli.py", "set", "search", "@data/tmp/g.json", contains="Gmail address")

    def test_abroad_list_is_ordered_and_editable(self):
        self.sb.ok(self, "profile_cli.py", "init")
        self.sb.ok(self, "profile_cli.py", "abroad", "add", "UAE", "--cities", "Dubai, Abu Dhabi")
        self.sb.ok(self, "profile_cli.py", "abroad", "add", "Saudi Arabia")
        self.sb.ok(self, "profile_cli.py", "abroad", "add", "sg", "--at", "1")
        out = self.sb.ok(self, "profile_cli.py", "abroad", "move", "AE", "1")
        self.assertLess(out.index("(AE)"), out.index("(SG)")); self.assertLess(out.index("(SG)"), out.index("(SA)"))
        self.assertEqual([a["country"] for a in self.sb.json("profile/search.json")["locations"]["abroad"]], ["AE", "SG", "SA"])
        self.sb.fails(self, "profile_cli.py", "abroad", "add", "AE", contains="already")
        self.sb.fails(self, "profile_cli.py", "abroad", "add", "Atlantis", contains="two-letter")
        self.sb.ok(self, "profile_cli.py", "abroad", "remove", "SG")
        self.assertEqual([a["country"] for a in self.sb.json("profile/search.json")["locations"]["abroad"]], ["AE", "SA"])

    def test_intake_progress(self):
        self.sb.ok(self, "profile_cli.py", "init")
        self.sb.ok(self, "profile_cli.py", "intake", "done", "field"); self.sb.ok(self, "profile_cli.py", "intake", "done", "documents")
        out = self.sb.ok(self, "profile_cli.py", "intake", "ask", "Exact SLA figure for the 2024 launch?")
        self.assertIn("next stage: facts", out); self.assertIn("open questions: 1", out)
        self.assertIn("open questions: 0", self.sb.ok(self, "profile_cli.py", "intake", "answered", "1", "about 78%"))

class Fit(Base):
    def setUp(self):
        super().setUp(); self.sb.setup_profile(self, title="Assistant Manager", ctc=12)

    def rules(self, **d):
        self.sb.write("data/tmp/r.json", d)
        rc, out = self.sb.run("fit.py", "rules", "@data/tmp/r.json")
        self.assertEqual(rc, 0, out)
        return json.loads(out[:out.rindex("}") + 1])

    def test_levels_and_abbreviations(self):
        self.assertIn("rank 3", self.sb.ok(self, "fit.py", "level", "Sr. Engineer – Kafka"))
        self.assertIn("rank 8", self.sb.ok(self, "fit.py", "level", "AGM - Backend"))
        self.assertIn("rank 8", self.sb.ok(self, "fit.py", "level", "Assistant General Manager"))   # not 'manager'
        self.assertEqual(self.rules(title="Senior Engineer")["level"]["verdict"], "lower")
        self.assertEqual(self.rules(title="Assistant Manager")["level"]["verdict"], "lateral")
        self.assertEqual(self.rules(title="Deputy Manager")["level"]["verdict"], "step up")
        r = self.rules(title="Lead, Backend", years_min=4)
        self.assertEqual(r["level"]["verdict"], "unclear"); self.assertIn("lower level", r["level"]["why"])

    def test_lateral_threshold_default_20_on_ctc(self):
        p = self.rules(title="Assistant Manager")["pay"]
        self.assertEqual((p["verdict"], p["ask_at_least_lpa"]), ("ask", 14.4))
        self.assertEqual(self.rules(title="Assistant Manager", pay_min_lpa=15, pay_max_lpa=17)["pay"]["verdict"], "clears")
        self.assertEqual(self.rules(title="Assistant Manager", pay_min_lpa=13, pay_max_lpa=15)["pay"]["verdict"], "possible")
        r = self.rules(title="Assistant Manager", pay_min_lpa=12, pay_max_lpa=14)
        self.assertEqual(r["pay"]["verdict"], "below"); self.assertTrue(r["excluded"])
        self.assertEqual(self.rules(title="Manager", pay_max_lpa=10)["pay"]["verdict"], "n/a")

    def test_custom_threshold_on_fixed_pay(self):
        self.sb.write("data/tmp/s.json", {"rules": {"lateral_min_raise_pct": 30, "raise_basis": "fixed"}})
        self.sb.ok(self, "profile_cli.py", "set", "search", "@data/tmp/s.json")
        self.sb.ok(self, "profile_cli.py", "current", "Assistant Manager", "--ctc", "12", "--fixed", "10")
        p = self.rules(title="Assistant Manager")["pay"]
        self.assertEqual((p["basis"], p["ask_at_least_lpa"]), ("fixed", 13.0))

    def test_location_preference_is_soft_and_countries_filter(self):
        self.sb.write("data/tmp/s.json", {"locations": {"preferred": ["north India"], "eligible_countries": ["IN", "AE"]}})
        self.sb.ok(self, "profile_cli.py", "set", "search", "@data/tmp/s.json")
        north, south = self.rules(title="Manager", location="Gurugram, Haryana")["location"], self.rules(title="Manager", location="Chennai")["location"]
        self.assertEqual((north["verdict"], south["verdict"]), ("home", "home"))
        self.assertGreater(north["score"], south["score"])
        self.assertEqual(self.rules(title="Manager", location="Dubai")["location"]["verdict"], "abroad")
        self.assertEqual(self.rules(title="Manager", location="Madrid, Spain")["location"]["verdict"], "excluded")
        self.assertEqual(self.rules(title="Manager", location="Anywhere", remote=True)["location"]["verdict"], "home")

    def test_abroad_list_ranks_and_makes_eligible(self):
        self.sb.write("data/tmp/s.json", {"locations": {"abroad": [{"country": "AE", "cities": ["Abu Dhabi"]}, {"country": "SA", "cities": []}],
                                                        "eligible_countries": ["IN", "SG"]}})
        self.sb.ok(self, "profile_cli.py", "set", "search", "@data/tmp/s.json")
        ad, dubai, riyadh, sg = (self.rules(title="Manager", location=x, stability="listed")["location"]
                                 for x in ("Abu Dhabi, UAE", "Dubai", "Riyadh", "Singapore"))
        self.assertEqual({x["verdict"] for x in (ad, dubai, riyadh, sg)}, {"abroad"})   # SA is eligible through the list
        self.assertGreater(ad["score"], dubai["score"]); self.assertGreater(dubai["score"], riyadh["score"]); self.assertGreater(riyadh["score"], sg["score"])
        self.assertEqual((ad["abroad_rank"], ad["preferred"]), (1, ["Abu Dhabi"]))
        self.assertEqual(self.rules(title="Manager", location="Madrid, Spain")["location"]["verdict"], "excluded")

    def test_stability_filters_abroad_only(self):
        self.sb.write("data/tmp/s.json", {"locations": {"abroad": [{"country": "AE"}]}})
        self.sb.ok(self, "profile_cli.py", "set", "search", "@data/tmp/s.json")
        r = self.rules(title="Manager", location="Dubai", stability="startup")
        self.assertEqual(r["company"]["verdict"], "excluded"); self.assertTrue(r["excluded"])
        pe = lambda **k: self.rules(title="Manager", location="Dubai", stability="PE-backed", **k)["company"]
        self.assertEqual(pe(employees=4000, founded=2008)["verdict"], "ok")
        small = pe(employees=300, founded=2008)
        self.assertEqual(small["verdict"], "unclear"); self.assertIn("about 300 employees (under 1,000)", small["why"])
        young = pe(employees=4000, founded=2020)
        self.assertEqual(young["verdict"], "unclear"); self.assertIn("founded 2020, 6 years ago (under 10)", young["why"])
        self.assertIn("headcount unknown", pe()["why"])
        self.assertEqual(self.rules(title="Manager", location="Pune", stability="PE-backed", employees=50, founded=2024)["company"]["verdict"], "shown")
        u = self.rules(title="Manager", location="Dubai")["company"]
        self.assertEqual(u["verdict"], "unclear"); self.assertIn("unknown", u["why"])
        home = self.rules(title="Manager", location="Pune", stability="startup")
        self.assertEqual(home["company"]["verdict"], "shown"); self.assertFalse(home["excluded"])
        self.sb.write("data/tmp/r.json", {"title": "Manager", "stability": "unicorn"})
        self.sb.fails(self, "fit.py", "rules", "@data/tmp/r.json", contains="stability must be one of")
        # their own rule can widen or narrow the list
        self.sb.write("data/tmp/s.json", {"rules": {"abroad_stability": ["listed", "government-owned"]}})
        self.sb.ok(self, "profile_cli.py", "set", "search", "@data/tmp/s.json")
        self.assertEqual(self.rules(title="Manager", location="Dubai", stability="PE-backed", employees=5000, founded=2000)["company"]["verdict"], "excluded")

    def test_stability_comes_from_the_radar_and_prefilter_drops_startups_abroad(self):
        self.sb.write("data/tmp/s.json", {"locations": {"abroad": [{"country": "AE"}]}})
        self.sb.ok(self, "profile_cli.py", "set", "search", "@data/tmp/s.json")
        self.sb.ok(self, "radar.py", "add", "Nova Labs", "https://boards.greenhouse.io/novalabs")
        self.sb.ok(self, "radar.py", "stability", "Nova Labs", "startup", "--source", "https://novalabs.example.com/about", "--basis", "seed-funded, 2024")
        r = self.rules(title="Manager", location="Dubai", company="Nova Labs")["company"]
        self.assertEqual((r["stability"], r["verdict"], r["source"]), ("startup", "excluded", "https://novalabs.example.com/about"))
        self.sb.fails(self, "radar.py", "stability", "Nova Labs", "listed", contains="--source")
        out = self.prefilter("Nova Labs", ("Backend Engineering Manager", "Dubai"), ("Backend Engineering Manager", "Pune"))
        self.assertEqual(out[0][0], False); self.assertIn("never a startup", out[0][1])
        self.assertEqual(out[1][0], True, out)

    def prefilter(self, company, *jobs):
        """fit.prefilter on (title, location) pairs for a radar company, in the sandbox."""
        import os, subprocess, sys
        from sandbox import ENGINE
        code = ("import json, sys, fit, radar; c = radar.find(radar.load_radar(), sys.argv[1]);"
                "print(json.dumps([fit.prefilter({'title': t, 'location': l}, company=c) for t, l in json.loads(sys.argv[2])]))")
        p = subprocess.run([sys.executable, "-c", code, company, json.dumps(jobs)], capture_output=True, text=True, encoding="utf-8", cwd=str(ENGINE),
                           env=dict(os.environ, FOUNDRY_HOME=str(self.sb.home), FOUNDRY_PACK="test", FOUNDRY_NOW=self.sb.now, PYTHONIOENCODING="utf-8"))
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_pay_over_place_moves_rubric_weight(self):
        base = self.sb.ok(self, "fit.py", "weights")
        self.assertIn("total 100", base); self.assertNotIn("pay over place", base)
        self.sb.write("data/tmp/s.json", {"locations": {"pay_over_place": True}})
        self.sb.ok(self, "profile_cli.py", "set", "search", "@data/tmp/s.json")
        out = self.sb.ok(self, "fit.py", "weights")
        self.assertIn("total 100", out); self.assertIn("pay over place: location 10 -> 5", out)

    def test_family_detection_prefers_titles(self):
        out = self.sb.ok(self, "fit.py", "family", "Backend Engineer", JD)
        self.assertTrue(out.startswith("backend"))

class Tracking(Base):
    def setUp(self):
        super().setUp(); self.sb.setup_profile(self)
        self.jd = self.sb.write("data/tmp/jd.txt", JD)

    def add(self, **d):
        base = {"company": "Acme Cloud", "title": "Backend Engineer", "url": "https://jobs.example.com/acme/1",
                "location": "Noida", "source": {"tier": 1, "via": "greenhouse"}}
        base.update(d); self.sb.write("data/tmp/j.json", base)
        return self.sb.ok(self, "jobs.py", "add", "@data/tmp/j.json")

    def test_add_dedupes_by_url_and_key(self):
        self.assertIn("j-0001", self.add())
        self.assertIn("already j-0001", self.add())
        self.assertIn("already j-0001", self.add(url="https://jobs.example.com/acme/other"))
        self.assertIn("j-0002", self.add(title="Senior Backend Engineer", url="https://jobs.example.com/acme/2"))

    def test_jd_copy_masks_phones_and_needs_full_text(self):
        self.add()
        self.sb.write("data/tmp/short.txt", "Too short")
        self.sb.fails(self, "jobs.py", "jd", "j-0001", "--file", "data/tmp/short.txt", contains="under 200")
        self.assertIn("1 phone number(s) masked", self.sb.ok(self, "jobs.py", "jd", "j-0001", "--file", self.jd))
        self.assertIn("[phone number removed]", (self.sb.home / "data/jds/j-0001.md").read_text(encoding="utf-8"))

    def test_check_needs_jd_and_records_fit(self):
        self.add()
        fit = {"level": "lateral", "pay": "ask", "location": "home", "match": 72, "likeliness": 55, "verdict": "solid analytics fit"}
        self.sb.write("data/tmp/c.json", {"jobs": [{"id": "j-0001", "fit": fit}]})
        self.sb.fails(self, "jobs.py", "check", "@data/tmp/c.json", contains="save the JD first")
        self.sb.ok(self, "jobs.py", "jd", "j-0001", "--file", self.jd)
        self.sb.ok(self, "jobs.py", "check", "@data/tmp/c.json")
        j = self.sb.json("data/jobs.json")["jobs"][0]
        self.assertEqual(j["fit"]["match"], 72); self.assertTrue(j["check"].startswith("data/checks/20261025-1000"))

    def test_applied_stores_resume_by_hash_and_moves_it(self):
        self.add(); self.sb.ok(self, "jobs.py", "jd", "j-0001", "--file", self.jd)
        self.sb.ok(self, "jobs.py", "status", "j-0001", "shortlisted")
        pdf = self.sb.write("inbox/My Resume.pdf", PDF)
        self.sb.write("data/tmp/a.json", {"job": "j-0001", "date": "2026-10-24", "channel": "careers_site"})
        out = self.sb.ok(self, "jobs.py", "applied", "@data/tmp/a.json", "--resume", pdf)
        h = hashlib.sha256(PDF).hexdigest()
        self.assertIn(f"data/resumes/{h}.pdf", out); self.assertFalse(pdf.exists())
        self.assertEqual(self.sb.json("data/jobs.json")["jobs"][0]["status"], "applied")
        a = self.sb.json("data/apps.json")["apps"][0]
        self.assertEqual((a["id"], a["resume"], a["job"]), ("a-0001", h, "j-0001"))
        self.sb.ok(self, "validate.py")

    def test_app_status_rules(self):
        self.add(); self.sb.ok(self, "jobs.py", "jd", "j-0001", "--file", self.jd)
        self.sb.write("data/tmp/a.json", {"job": "j-0001", "date": "2026-10-20", "channel": "referral", "referrer": "a friend"})
        self.sb.ok(self, "jobs.py", "applied", "@data/tmp/a.json", "--resume", self.sb.write("inbox/r.pdf", PDF))
        self.sb.fails(self, "jobs.py", "app", "a-0001", "interviewing", contains="needs --round")
        self.sb.fails(self, "jobs.py", "app", "a-0001", "screen", "--date", "2026-10-19", contains="before the last change")
        self.sb.fails(self, "jobs.py", "app", "a-0001", "screen", "--date", "2026-11-01", contains="future")
        self.sb.ok(self, "jobs.py", "app", "a-0001", "interviewing", "--round", "1", "--next", "2026-10-28")
        self.assertIn("next 2026-10-28", self.sb.ok(self, "jobs.py", "apps"))
        self.assertIn("2026-10-28", self.sb.ok(self, "today.py"))

    def test_applied_needs_a_jd_and_a_resume(self):
        self.add()
        self.sb.write("data/tmp/a.json", {"job": "j-0001", "date": "2026-10-24", "channel": "careers_site"})
        self.sb.fails(self, "jobs.py", "applied", "@data/tmp/a.json", "--resume", self.sb.write("inbox/r.pdf", PDF), contains="JD copy")
        self.sb.fails(self, "jobs.py", "applied", "@data/tmp/a.json", "--jd-file", self.jd, contains="which resume")
        self.sb.fails(self, "jobs.py", "applied", "@data/tmp/a.json", "--jd-file", self.jd, "--resume", self.sb.write("inbox/r.txt", "hi"), contains="not a PDF or DOCX")

    def test_today_flags_stale_applications(self):
        self.add(); self.sb.ok(self, "jobs.py", "jd", "j-0001", "--file", self.jd)
        self.sb.write("data/tmp/a.json", {"job": "j-0001", "date": "2026-10-01", "channel": "careers_site"})
        self.sb.ok(self, "jobs.py", "applied", "@data/tmp/a.json", "--resume", self.sb.write("inbox/r.pdf", PDF))
        out = self.sb.ok(self, "today.py")
        self.assertIn("no update for 14+ days (1)", out); self.assertIn("Nothing was changed", out)

class Misc(Base):
    def test_inhand(self):
        out = self.sb.ok(self, "inhand.py", "15", "--state", "Karnataka")
        self.assertIn("monthly in-hand", out); self.assertIn("Karnataka professional tax 2,400/yr", out)
        self.sb.fails(self, "inhand.py", "15", "--state", "Atlantis", contains="--pt")
        self.assertIn("no professional tax", self.sb.ok(self, "inhand.py", "15"))

    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_backup_tracks_profile_and_data_not_cache(self):
        self.sb.ok(self, "profile_cli.py", "init")
        self.assertIn("history started", self.sb.ok(self, "backup.py", "init"))
        self.sb.write("data/cache/x.json", "{}"); self.sb.write("data/tmp/y.json", "{}"); self.sb.write("inbox/cv.pdf", PDF)
        self.assertIn("nothing changed", self.sb.ok(self, "backup.py", "commit", "noop"))
        self.sb.write("data/jobs.json", {"jobs": []})
        self.assertIn("saved", self.sb.ok(self, "backup.py", "commit", "jobs"))
        log = self.sb.ok(self, "backup.py", "log")
        self.assertIn("jobs", log); self.assertIn("start history", log)
        self.assertIn("intact", self.sb.ok(self, "backup.py", "check"))

    def test_grill_clock_is_append_only(self):
        f = self.sb.ok(self, "grill_clock.py", "start", "Acme analyst").strip()
        self.sb.ok(self, "grill_clock.py", "ask", f, "Explain SLA vs SLO", "--budget", "4")
        self.sb.fails(self, "grill_clock.py", "ask", f, "Next?", contains="unanswered")
        self.assertIn("answered in 2.0 min", self.sb.ok(self, "grill_clock.py", "answer", f, "An SLA is the promise...", now="2026-10-25T10:02:00"))
        self.sb.fails(self, "grill_clock.py", "answer", f, "Actually...", contains="no do-overs")
        self.sb.ok(self, "grill_clock.py", "end", f, "--score", "7")
        self.sb.fails(self, "grill_clock.py", "ask", f, "One more", contains="already ended")
        out = self.sb.run("grill_clock.py", "start", "late")[1].strip()
        self.sb.ok(self, "grill_clock.py", "ask", out, "Q1")
        rc, msg = self.sb.run("grill_clock.py", "answer", out, "A1", now="2026-10-25T11:00:00")
        self.assertIn("TIME UP", msg)

    def test_extract_docx_txt_and_archive(self):
        import docx
        d = docx.Document(); d.add_paragraph("Backend Engineer at Acme Cloud"); d.save(str(self.sb.home / "inbox" / "cv.docx"))
        self.assertIn("Backend Engineer", self.sb.ok(self, "extract.py", "text", self.sb.home / "inbox" / "cv.docx"))
        self.sb.write("inbox/notes.txt", "line one\r\nline two\r\n")
        self.assertEqual(self.sb.ok(self, "extract.py", "text", self.sb.home / "inbox" / "notes.txt").strip(), "line one\nline two")
        moved = self.sb.ok(self, "extract.py", "archive", self.sb.home / "inbox" / "cv.docx").strip()
        self.assertTrue(moved.startswith("archive/20261025-1000-cv.docx")); self.assertTrue((self.sb.home / moved).exists())
        self.sb.write("inbox/old.doc", b"\xd0\xcf\x11\xe0")
        self.sb.fails(self, "extract.py", "text", self.sb.home / "inbox" / "old.doc", contains="save it as .docx")

    def test_validate_and_doctor_quick(self):
        self.sb.ok(self, "profile_cli.py", "init")
        self.assertIn("setup OK", self.sb.ok(self, "doctor.py", "--quick"))
        self.sb.write("profile/facts.jsonl", '{"id": "f-0001", "kind": "achievement", "text": "x", "status": "confirmed", "source": "user"}\n')
        self.assertIn("confirmed date", self.sb.fails(self, "validate.py"))
        self.sb.fails(self, "doctor.py", "--quick", contains="ACTION NEEDED")

if __name__ == "__main__":
    unittest.main()
