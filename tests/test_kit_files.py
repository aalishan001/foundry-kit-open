"""The shipped kit: commands and their model presets, settings, runtime rules, docs."""
import json, pathlib, re, unittest
from sandbox import KIT

COMMANDS = {"start": "sonnet", "radar": "sonnet", "sweep": "haiku", "check": "sonnet", "tailor": "opus", "applied": "sonnet",
            "update": "haiku", "grill": "sonnet", "prep": "sonnet", "today": "haiku", "help": "haiku"}

def frontmatter(p):
    m = re.match(r"^---\n(.*?)\n---\n", p.read_text(encoding="utf-8"), re.S)
    return dict(l.split(":", 1) for l in m.group(1).splitlines() if ":" in l) if m else {}

class KitFiles(unittest.TestCase):
    def test_commands_and_model_presets(self):
        files = {p.stem: p for p in (KIT / ".claude" / "commands").glob("*.md")}
        self.assertEqual(set(files), set(COMMANDS))
        for name, model in COMMANDS.items():
            fm = frontmatter(files[name])
            self.assertTrue(fm.get("description", "").strip(), name)
            self.assertEqual(fm.get("model", "").strip(), model, name)
        self.assertEqual([n for n, m in COMMANDS.items() if m == "opus"], ["tailor"])   # Pro plan limits

    def test_every_engine_call_in_commands_exists(self):
        engine = {p.name for p in (KIT / "engine").glob("*.py")}
        for p in list((KIT / ".claude" / "commands").glob("*.md")) + [KIT / "CLAUDE.md"]:
            for script in re.findall(r"engine/([a-z_]+\.py)", p.read_text(encoding="utf-8")):
                self.assertIn(script, engine, f"{p.name} calls missing engine/{script}")
        for p in (KIT / ".claude" / "commands").glob("*.md"):
            for script in re.findall(r"(?<!engine/)\b([a-z_]+\.py)\b", p.read_text(encoding="utf-8")):
                self.assertIn(script, engine, f"{p.name} mentions missing {script}")

    def test_settings(self):
        s = json.loads((KIT / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]
        self.assertEqual(s["defaultMode"], "acceptEdits")
        for r in ("Edit(/**)", "Write(/**)", "Bash(python engine/*)", "PowerShell(python engine/*)"): self.assertIn(r, s["allow"])
        for r in ("WebFetch(domain:linkedin.com)", "WebFetch(domain:*.linkedin.com)", "WebFetch(domain:naukri.com)",
                  "WebFetch(domain:*.naukri.com)", "Edit(/engine/**)", "Write(/.claude/**)"): self.assertIn(r, s["deny"])
        self.assertFalse(any(r.startswith(("WebFetch", "WebSearch")) for r in s["allow"]))   # other sites ask

    def test_claim_checker_agent_is_read_only(self):
        fm = frontmatter(KIT / ".claude" / "agents" / "claim-checker.md")
        self.assertEqual({t.strip() for t in fm["tools"].split(",")}, {"Read", "Grep", "Glob"})

    def test_profile_skeleton_has_no_data_files(self):
        self.assertEqual([p.name for p in (KIT / "profile").iterdir()], ["README.md"])

    def test_runtime_rules_cover_tone_and_truth(self):
        t = (KIT / "CLAUDE.md").read_text(encoding="utf-8")
        for phrase in ("Answer first", "No preamble, no pep talk", "Never drop a detail", "only confirmed facts", "LinkedIn or Naukri", "@data/tmp/"):
            self.assertIn(phrase, t)

    def test_setup_installs_keyring_and_the_morning_sweep(self):
        self.assertIn("keyring==", (KIT / "engine" / "requirements.txt").read_text(encoding="utf-8"))
        ps = (KIT / "setup.ps1").read_text(encoding="utf-8")
        self.assertIn("import typst, docx, pypdf, keyring", ps); self.assertIn(r'engine\schedule.py") on', ps); self.assertIn(r'engine\upgrade.py")', ps)

    def test_double_click_helpers(self):
        engine = {p.name for p in (KIT / "engine").glob("*.py")}
        for name in ("setup.cmd", "Gmail setup.cmd", "API keys.cmd"):
            b = (KIT / name).read_bytes()
            self.assertTrue(all(c < 128 for c in b), name)
            self.assertEqual(b.count(b"\n"), b.count(b"\r\n"), name)   # CRLF only
            for script in re.findall(r"engine[\\/]([a-z_]+\.py)", b.decode()): self.assertIn(script, engine, name)

    def test_cheat_sheet_lists_exactly_the_commands(self):
        t = (KIT / "docs" / "COMMANDS.md").read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r"^/([a-z]+)", t, re.M)), set(COMMANDS))

if __name__ == "__main__":
    unittest.main()
