"""A throwaway install for engine tests: a temp folder whose path has spaces, a OneDrive-style segment and a
non-ASCII character (as theirs may), with the test pack installed. Engine scripts run from the repo's kit/engine with
FOUNDRY_HOME pointing at the sandbox and a fixed clock."""
import json, os, pathlib, shutil, subprocess, sys, tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
KIT = REPO / "kit"
ENGINE = KIT / "engine"
FIXTURES = REPO / "tests" / "fixtures"

class Sandbox:
    def __init__(self, pack="test", now="2026-10-25T10:00:00"):
        self.root = pathlib.Path(tempfile.mkdtemp(prefix="fk-"))
        self.home = self.root / "OneDrive - Contoso" / "Job Search – Ä"
        for d in ("profile", "data", "inbox", "archive"): (self.home / d).mkdir(parents=True)
        if pack == "test": shutil.copytree(FIXTURES / "packs" / "test", self.home / "packs" / "test")
        self.now, self.pack = now, pack
        self.env_extra = {}

    def close(self): shutil.rmtree(self.root, ignore_errors=True)

    def run(self, script, *args, now=None, stdin=None, env=None):
        e = dict(os.environ, FOUNDRY_HOME=str(self.home), FOUNDRY_NOW=now or self.now, PYTHONIOENCODING="utf-8",
                 FOUNDRY_PACK=self.pack, **self.env_extra, **(env or {}))
        p = subprocess.run([sys.executable, str(ENGINE / script), *map(str, args)], capture_output=True, text=True,
                           encoding="utf-8", env=e, input=stdin, cwd=str(self.home))
        return p.returncode, p.stdout + p.stderr

    def ok(self, test, script, *args, **kw):
        rc, out = self.run(script, *args, **kw)
        test.assertEqual(rc, 0, f"{script} {' '.join(map(str, args))}\n{out}")
        return out

    def fails(self, test, script, *args, contains=None, **kw):
        rc, out = self.run(script, *args, **kw)
        test.assertNotEqual(rc, 0, f"{script} {' '.join(map(str, args))} should fail\n{out}")
        if contains: test.assertIn(contains, out)
        return out

    def write(self, rel, content):
        p = self.home / rel; p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, (dict, list)): content = json.dumps(content, ensure_ascii=False)
        (p.write_bytes(content) if isinstance(content, bytes) else p.write_text(content, encoding="utf-8", newline=""))
        return p

    def json(self, rel): return json.loads((self.home / rel).read_text(encoding="utf-8"))

    def jsonl(self, rel):
        p = self.home / rel
        return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []

    def setup_profile(self, test, title="Assistant Manager", ctc=12, **search):
        self.ok(test, "profile_cli.py", "init")
        self.write("data/tmp/search.json", {"pack": self.pack, **search})
        self.ok(test, "profile_cli.py", "set", "search", "@data/tmp/search.json")
        self.ok(test, "profile_cli.py", "current", title, "--ctc", ctc)

JD = ("We are hiring a Senior Backend Engineer for our payments platform. You will own API latency (p99) and SLA targets, build "
      "services in Go and Java on Kubernetes, use Kafka for events and PostgreSQL for the ledger, and run CI/CD and observability "
      "with Grafana. Requirements: 5+ years building backend services. Contact the "
      "recruiter on " + "9" + "8123 45670 with questions.")
