"""The OpenCode target: generated from the Claude Code sources and in sync; only OpenRouter, zero data retention and no
training on every model; no web fetch or search; kit files can't be edited; every command has a model tier."""
import json, subprocess, sys, unittest
from sandbox import REPO, KIT

class OpenCodeTarget(unittest.TestCase):
    def test_generated_files_are_in_sync(self):
        p = subprocess.run([sys.executable, str(REPO / "scripts" / "gen_opencode.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_every_command_on_both_targets(self):
        claude = {p.stem for p in (KIT / ".claude" / "commands").glob("*.md")}
        oc = {p.stem for p in (KIT / ".opencode" / "commands").glob("*.md")}
        self.assertEqual(claude, oc)
        models = json.loads((REPO / "scripts" / "opencode_models.json").read_text(encoding="utf-8"))
        self.assertEqual(set(models["commands"]), claude)
        for p in (KIT / ".opencode" / "commands").glob("*.md"):
            self.assertIn(f"model: {models['tiers'][models['commands'][p.stem]]}", p.read_text(encoding="utf-8"))

    def test_privacy_and_permissions(self):
        c = json.loads((KIT / "opencode.json").read_text(encoding="utf-8"))
        self.assertEqual(c["enabled_providers"], ["openrouter"]); self.assertEqual(c["share"], "disabled")
        self.assertEqual(c["provider"]["openrouter"]["options"]["apiKey"], "{env:FOUNDRY_OPENROUTER_KEY}")   # never the key itself
        for m, spec in c["provider"]["openrouter"]["models"].items():
            self.assertEqual(spec["options"]["provider"]["zdr"], True, m); self.assertEqual(spec["options"]["provider"]["data_collection"], "deny", m)
        used = {c["model"], c["small_model"]} | {l.split("model: ", 1)[1].strip() for p in (KIT / ".opencode").rglob("*.md")
                                                  for l in p.read_text(encoding="utf-8").splitlines() if l.startswith("model: ")}
        self.assertEqual({u.split("/", 1)[1] for u in used}, set(c["provider"]["openrouter"]["models"]))   # every model used is routed ZDR
        perm = c["permission"]
        self.assertEqual((perm["webfetch"], perm["websearch"], perm["external_directory"]), ("deny", "deny", "deny"))
        for d in ("engine/*", ".claude/*", ".opencode/*", "packs/*", "templates/*", "opencode.json", "AGENTS.md"): self.assertEqual(perm["edit"][d], "deny", d)
        self.assertEqual(perm["bash"]["python engine/*"], "allow"); self.assertEqual(perm["bash"]["*"], "ask")
        a = (KIT / ".opencode" / "agents" / "claim-checker.md").read_text(encoding="utf-8")
        for line in ("mode: subagent", "  edit: deny", "  bash: deny", "  webfetch: deny"): self.assertIn(line, a)

    def test_agents_md_carries_the_rules(self):
        t = (KIT / "AGENTS.md").read_text(encoding="utf-8")
        for phrase in ("The truth rule", "Never fetch LinkedIn or Naukri", "Web search and web fetch are off"): self.assertIn(phrase, t)

if __name__ == "__main__":
    unittest.main()
