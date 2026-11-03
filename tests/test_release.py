"""scripts/build_release.py: refuses on a planted leak or without a denylist; the zip holds the kit and nothing personal."""
import os, pathlib, shutil, subprocess, sys, tempfile, unittest, zipfile
from sandbox import REPO, KIT

class Release(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="rel-"))
        self.kit = self.tmp / "kit"
        shutil.copytree(KIT, self.kit, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.deny = self.tmp / "deny.txt"; self.deny.write_text("Zorvane Quill\n", encoding="utf-8")
        self.env = dict(os.environ, PYTHONIOENCODING="utf-8", FOUNDRY_LEAK_DENYLIST=str(self.deny), FOUNDRY_DEV_CONFIG=str(self.tmp / "none.json"))
    def tearDown(self): shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, env=None):
        p = subprocess.run([sys.executable, str(REPO / "scripts" / "build_release.py"), "--kit", str(self.kit), "--out", str(self.tmp / "dist"), "--skip-tests"],
                           capture_output=True, text=True, encoding="utf-8", env=env or self.env)
        return p.returncode, p.stdout + p.stderr

    def fill_costs(self):
        s = self.kit / "docs" / "SETUP.md"
        s.write_text(s.read_text(encoding="utf-8").replace("COSTS_TABLE", "(measured costs)"), encoding="utf-8")

    def test_refuses_an_unfilled_cost_table(self):
        s = self.kit / "docs" / "SETUP.md"
        s.write_text(s.read_text(encoding="utf-8").replace("## What OpenCode costs", "## What OpenCode costs\n\nCOSTS_TABLE"), encoding="utf-8")
        rc, out = self.build()
        self.assertEqual(rc, 1, out); self.assertIn("COSTS_TABLE placeholder", out)
        p = subprocess.run([sys.executable, str(REPO / "scripts" / "build_release.py"), "--kit", str(self.kit), "--out", str(self.tmp / "dist"),
                            "--skip-tests", "--rc"], capture_output=True, text=True, encoding="utf-8", env=self.env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual([z.name.endswith("-rc.zip") for z in (self.tmp / "dist").glob("*.zip")], [True])   # only ever an -rc zip

    def test_clean_build(self):
        self.fill_costs()
        (self.kit / "engine" / "__pycache__").mkdir(exist_ok=True); (self.kit / "engine" / "__pycache__" / "x.pyc").write_bytes(b"x")
        rc, out = self.build()
        self.assertEqual(rc, 0, out)
        z = next((self.tmp / "dist").glob("foundry-kit-*.zip"))
        names = set(zipfile.ZipFile(z).namelist())
        for n in ("CLAUDE.md", "setup.cmd", "setup.ps1", ".claude/settings.json", ".claude/commands/tailor.md", "engine/render.py",
                  "packs/software-eng/radar.json", "templates/resume.typ", "docs/COMMANDS.md", "Start here.pdf", "profile/README.md",
                  "AGENTS.md", "opencode.json", "OpenCode.cmd", ".opencode/commands/tailor.md", "Gmail setup.cmd", "API keys.cmd"):
            self.assertIn(n, names)
        self.assertFalse([n for n in names if "__pycache__" in n or n.startswith(("data/", "inbox/", "seed/"))])

    def test_refuses_on_a_planted_leak(self):
        (self.kit / "docs" / "SETUP.md").write_text("Written for Zorvane Quill.\n", encoding="utf-8")
        rc, out = self.build()
        self.assertEqual(rc, 1, out); self.assertIn("RELEASE REFUSED: leak scan", out)
        self.assertFalse((self.tmp / "dist").exists() and list((self.tmp / "dist").glob("*.zip")))

    def test_refuses_without_a_denylist(self):
        rc, out = self.build(dict(self.env, FOUNDRY_LEAK_DENYLIST=str(self.tmp / "missing.txt")))
        self.assertEqual(rc, 1, out); self.assertIn("refusing", out)

    def test_refuses_profile_data_in_the_kit(self):
        (self.kit / "profile" / "facts.jsonl").write_text("{}\n", encoding="utf-8")
        rc, out = self.build()
        self.assertEqual(rc, 1, out); self.assertIn("profile/ must hold only the README", out)

if __name__ == "__main__":
    unittest.main()
