"""scripts/leak_scan.py: every check, scopes, masking, exit codes, staged mode, and the repo itself.
Personal-looking strings are built at runtime so this file passes the scan it tests."""
import io, json, os, pathlib, shutil, subprocess, sys, tempfile, unittest, zipfile

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "leak_scan.py"
AT = "@"
PHONE = "9" + "8123 45670"
EMAIL = "zed.quorlin" + AT + "gmail.com"
WIN_PATH = "C:" + "\\Users\\" + "zquorlin\\Documents\\cv.pdf"
TOKEN = "ghp" + "_" + "a1B2" * 9

class LeakScan(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="leak-test-"))
        self.deny = self.tmp / "deny.txt"
        self.deny.write_text("# test denylist\nZed Quorlin\nQuorlin\n=ACMEX\nre:\\bproj-\\d{3}\\b\nkit:Toolname\n", encoding="utf-8")
        self.files = self.tmp / "files"; self.files.mkdir()

    def tearDown(self): shutil.rmtree(self.tmp, ignore_errors=True)

    def scan(self, *args, deny=True, env=None):
        a = [sys.executable, str(SCRIPT), *args] + (["--denylist", str(self.deny)] if deny else [])
        e = dict(os.environ, PYTHONIOENCODING="utf-8", **(env or {}))
        p = subprocess.run(a, capture_output=True, text=True, encoding="utf-8", env=e)
        return p.returncode, p.stdout + p.stderr

    def write(self, rel, text):
        p = self.files / rel; p.parent.mkdir(parents=True, exist_ok=True)
        (p.write_bytes(text) if isinstance(text, bytes) else p.write_text(text, encoding="utf-8")); return p

    def assertHit(self, text, label, rel="note.md", *args):
        p = self.write(rel, text)
        rc, out = self.scan(str(p), *args)
        self.assertEqual(rc, 1, out); self.assertIn(f"[{label}", out)
        return out

    def assertClean(self, text, rel="note.md", *args):
        p = self.write(rel, text)
        rc, out = self.scan(str(p), *args)
        self.assertEqual(rc, 0, out); self.assertIn("clean", out)

    # ---------------- built-in checks
    def test_clean_file_passes(self):
        self.assertClean("Generic kit text about backend roles in India.\n")

    def test_email_hits_but_example_domains_pass(self):
        self.assertHit(f"contact {EMAIL}\n", "email")
        self.assertClean("write to someone" + AT + "example.com or a" + AT + "corp.test\n")

    def test_github_noreply_address_hits(self):
        self.assertHit("12345678+someone" + AT + "users.noreply.github.com\n", "email")
        self.assertClean("alerts come from jobalerts-noreply" + AT + "linkedin.com and no-reply" + AT + "board.example.org\n")
        self.assertHit("write to zed-noreply.fan" + AT + "gmail.com\n", "email")

    def test_indian_and_international_phones_hit(self):
        self.assertHit(f"call {PHONE}\n", "phone")
        self.assertHit("call +91 " + PHONE + "\n", "phone")
        self.assertHit("call +" + "44 20 7946 0958\n", "phone")

    def test_home_paths_hit_but_placeholders_pass(self):
        self.assertHit(f"saved at {WIN_PATH}\n", "home path")
        self.assertHit("cd " + "/c/Users/" + "zquorlin/Desktop\n", "home path")
        self.assertClean("put it in C:\\Users\\<you>\\OneDrive or %USERPROFILE% or C:\\Users\\Public\n")
        self.assertClean("GET https://api.example.com/users/42 and /home/<you>/kit\n")

    def test_file_urls_secrets_and_linkedin_profiles_hit(self):
        self.assertHit("open file" + ":///C:/x.html\n", "file url")
        self.assertHit(f"token {TOKEN}\n", "secret")
        self.assertHit("-----BEGIN OPENSSH " + "PRIVATE KEY-----\n", "secret")
        self.assertHit("https://www.linkedin.com/in/" + "zquorlin\n", "linkedin profile")
        self.assertClean("your profile: linkedin.com/in/<you>\n")

    # ---------------- denylist
    def test_denylist_whole_word_case_insensitive(self):
        self.assertHit("written by zed  QUORLIN\n", "denylist")
        self.assertClean("Quorlinesque is a different word\n")

    def test_denylist_exact_case_and_regex(self):
        self.assertHit("worked at ACMEX\n", "denylist")
        self.assertClean("acmex in lower case is allowed by the = rule\n")
        self.assertHit("see proj-042\n", "denylist")

    def test_kit_only_terms_apply_to_shipping_files_only(self):
        self.assertClean("built from Toolname\n", "notes/dev.md")
        self.assertHit("built from Toolname\n", "denylist", "kit/CLAUDE.md")
        self.assertHit("built from Toolname\n", "denylist", "notes/dev.md", "--scope", "kit")

    def test_file_names_are_scanned(self):
        out = self.assertHit("nothing inside\n", "denylist", "Quorlin_Resume.md")
        self.assertIn("(file name)", out)

    def test_default_denylist_from_env_and_require_flag(self):
        p = self.write("note.md", "by Quorlin\n")
        rc, out = self.scan(str(p), deny=False, env={"FOUNDRY_LEAK_DENYLIST": str(self.deny)})
        self.assertEqual(rc, 1, out)
        rc, out = self.scan(str(p), "--require-denylist", deny=False, env={"FOUNDRY_LEAK_DENYLIST": str(self.tmp / "missing.txt")})
        self.assertEqual(rc, 2, out); self.assertIn("refusing", out)
        rc, out = self.scan(str(p), deny=False, env={"FOUNDRY_LEAK_DENYLIST": str(self.tmp / "missing.txt")})
        self.assertEqual(rc, 0, out); self.assertIn("WARNING", out)

    def test_bad_regex_in_denylist_is_a_config_error(self):
        self.deny.write_text("re:(unclosed\n", encoding="utf-8")
        rc, out = self.scan(str(self.write("a.md", "x\n")))
        self.assertNotIn(rc, (0, 1), out); self.assertIn("not a valid regex", out)

    # ---------------- profile-derived terms
    def test_profile_identity_terms(self):
        prof = self.tmp / "profile"; prof.mkdir()
        (prof / "identity.json").write_text(json.dumps({
            "name": {"full": "Vexa Ondrill", "preferred": "Vexa"},
            "email": "vexa.o" + AT + "mail.test.example", "phone": "+91 " + "7" + "0123 45678",
            "links": {"linkedin": "https://www.linkedin.com/in/" + "vexa-o"},
            "location": {"city": "Lucknow"}}), encoding="utf-8")
        (prof / "facts.json").write_text(json.dumps({"identity": {"name": {"full": "Brannoc Tull"}}, "company": "Acme Cloud"}), encoding="utf-8")
        (prof / "intake.json").write_text(json.dumps({"stages": {"identity": "open", "facts": "done"}}), encoding="utf-8")
        for text in ("Signed, Ondrill", "Call 7" + "0123-45678", "linkedin.com/in/" + "vexa-o", "by Brannoc"):
            p = self.write("note.md", text + "\n")
            rc, out = self.scan(str(p), "--profile", str(prof))
            self.assertEqual(rc, 1, f"{text}: {out}"); self.assertIn("[profile", out)
        # location and non-identity fields are not derived (packs list cities and companies)
        p = self.write("note.md", "Roles in Lucknow at Acme Cloud; open questions are done\n")   # intake stage names aren't identity
        rc, out = self.scan(str(p), "--profile", str(prof))
        self.assertEqual(rc, 0, out)

    # ---------------- binaries, masking, folders
    def test_docx_members_and_binary_strings_are_scanned(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z: z.writestr("word/document.xml", "<w:t>Zed Quorlin</w:t>")
        out = self.assertHit(buf.getvalue(), "denylist", "cv.docx")
        self.assertIn("cv.docx!word/document.xml", out)
        self.assertHit(b"%PDF-1.4\x00\x01/Author (Zed Quorlin)\x00", "denylist", "cv.pdf")

    def test_report_masks_the_match(self):
        out = self.assertHit(f"reach me at {EMAIL} today\n", "email")
        self.assertNotIn(EMAIL, out)
        out = self.assertHit("by Zed Quorlin\n", "denylist")
        self.assertNotIn("Quorlin", out)

    def test_folder_scan_skips_git_and_seed(self):
        self.write("seed/copied.md", "Quorlin\n"); self.write(".git/config", "Quorlin\n"); self.write("kit/ok.md", "fine\n")
        rc, out = self.scan(str(self.files))
        self.assertEqual(rc, 0, out); self.assertIn("1 file(s)", out)

    # ---------------- staged mode
    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_staged_mode_scans_the_staged_copy(self):
        repo = self.tmp / "repo"; (repo / "scripts").mkdir(parents=True)
        shutil.copy(SCRIPT, repo / "scripts" / "leak_scan.py")
        g = lambda *a: subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True)
        g("init", "-q")
        (repo / "a.md").write_text("by Quorlin\n", encoding="utf-8"); g("add", "a.md")
        (repo / "a.md").write_text("clean now, but not staged\n", encoding="utf-8")
        p = subprocess.run([sys.executable, str(repo / "scripts" / "leak_scan.py"), "--staged", "--denylist", str(self.deny)],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr); self.assertIn("a.md:1", p.stdout)

    # ---------------- the repo itself
    def test_repo_is_clean(self):
        """The real scan over this repo, with the developer's own denylist when one is configured."""
        rc, out = self.scan(deny=False)
        self.assertEqual(rc, 0, out)

if __name__ == "__main__":
    unittest.main()
