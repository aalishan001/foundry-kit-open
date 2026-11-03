#!/usr/bin/env python3
"""Measure the OpenCode target for real: run kit commands through `opencode run` in a scratch install built from kit/
with an invented candidate, answer the interactive ones with a simulated user, and read the cost from OpenRouter's
own key usage (simulated-user calls are subtracted). Developer tool; never ships.
  measure_opencode.py probe <provider/model> ...      one tool-calling turn per model: does it call the engine?
  measure_opencode.py week [--tier T=model ...] [--only cmd,cmd] [--out notes/opencode-measure.json]
  measure_opencode.py start --model <provider/model> [--provider groq|cerebras] [--out ...]   a /start only
The OpenRouter key comes from scripts/dev_keys.py (Credential Manager); it is passed to opencode only as an
environment variable and never written anywhere. All data is invented (tests/fixtures/tailor/profile.py).
"""
import json, os, pathlib, shutil, subprocess, sys, tempfile, time, urllib.request
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import dev_keys

REPO = pathlib.Path(__file__).resolve().parent.parent
KIT = REPO / "kit"
API = "https://openrouter.ai/api/v1"
SIM_MODEL = "anthropic/claude-haiku-5.5"
MAX_TURNS = {"start": 40, "grill": 5, "prep": 4, "tailor": 4, "check": 3, "applied": 3, "update": 3, "radar": 2, "sweep": 3, "today": 2, "help": 1}
sys.path.insert(0, str(REPO / "tests" / "fixtures" / "tailor"))
import profile as persona   # noqa: E402  (the invented candidate)

def oc_exe():
    p = shutil.which("opencode") or str(pathlib.Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WinGet" / "Links" / "opencode.exe")
    return p

def openrouter(path, key, body=None):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r: return json.loads(r.read().decode("utf-8"))

def usage(key):
    """The key's all-time usage in USD, once it has settled (OpenRouter updates it a few seconds late)."""
    last, same = None, 0
    for _ in range(12):
        u = openrouter("/key", key)["data"]["usage"]
        same = same + 1 if u == last else 0
        if same >= 2: return u
        last = u; time.sleep(3)
    return last

# ---------------------------------------------------------------- scratch install
def resume_docx(path):
    import docx
    d = docx.Document()
    i = persona.IDENTITY
    d.add_paragraph(i["name"]["full"], style="Title")
    d.add_paragraph(f"{i['location']['city']} | {i['email']} | {i['phone']}")
    d.add_paragraph("Experience", style="Heading 1")
    for e in persona.EMPLOYMENT:
        d.add_paragraph(f"{e['role']}, {e['employer']} ({e['start']} – {e['end'] or 'present'}, {e['location']})")
        for f in persona.FACTS:
            if f.get("employer") == e["employer"]: d.add_paragraph(f["text"], style="List Bullet")
    d.add_paragraph("Skills and certifications", style="Heading 1")
    for f in persona.FACTS:
        if f["kind"] in ("skill", "certification"): d.add_paragraph(f["text"], style="List Bullet")
    d.add_paragraph("Education", style="Heading 1")
    for e in persona.EDUCATION: d.add_paragraph(f"{e['degree']}, {e['institution']} ({e['end'][:4]})")
    d.save(str(path))

def scratch(name, models=None):
    root = pathlib.Path(tempfile.gettempdir()) / f"fk-measure-{name}"
    if root.exists(): shutil.rmtree(root, onexc=lambda fn, p, _: (os.chmod(p, 0o666), fn(p)))
    shutil.copytree(KIT, root)
    for d in ("profile", "data", "inbox", "archive", "Resumes"): (root / d).mkdir(exist_ok=True)
    resume_docx(root / "inbox" / "Riya_Testwal_Resume.docx")
    env = dict(os.environ, FOUNDRY_HOME=str(root))
    for args in (["backup.py", "init"], ["profile_cli.py", "init"], ["radar.py", "seed"]):
        subprocess.run([sys.executable, str(root / "engine" / args[0]), *args[1:]], env=env, capture_output=True, check=True)
    if models:   # swap model ids in the generated command files (the measurement's own variants)
        for p in (root / ".opencode").rglob("*.md"):
            t = p.read_text(encoding="utf-8")
            for old, new in models.items(): t = t.replace(f"model: {old}\n", f"model: {new}\n")
            p.write_text(t, encoding="utf-8", newline="\n")
    return root

# ---------------------------------------------------------------- one opencode turn
def turn(root, key, message, command=None, session=None, model=None, extra_env=None, log=None):
    args = [oc_exe(), "run", "--format", "json", "--dir", str(root)]
    if command: args += ["--command", command]
    if session: args += ["--session", session]
    if model: args += ["-m", model]
    args.append(message or " ")
    env = dict(os.environ, FOUNDRY_OPENROUTER_KEY=key, OPENCODE_DISABLE_CLAUDE_CODE_PROMPT="1", **(extra_env or {}))
    t0 = time.time()
    p = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=str(root), timeout=1800)
    events = []
    for line in p.stdout.splitlines():
        try: events.append(json.loads(line))
        except json.JSONDecodeError: pass
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"args": args[1:-1] + [message[:200] if message else ""], "rc": p.returncode, "stderr": p.stderr[-2000:], "events": events}) + "\n")
    sid = session or next((e.get("sessionID") or (e.get("properties") or {}).get("sessionID") for e in events if e.get("sessionID") or (e.get("properties") or {}).get("sessionID")), None)
    text = "\n".join(str(((e.get("part") or {}).get("text")) or "") for e in events if (e.get("part") or {}).get("type") == "text").strip()
    tools = [((e.get("part") or {}).get("tool"), (((e.get("part") or {}).get("state") or {}).get("input") or {}).get("command"))
             for e in events if (e.get("part") or {}).get("type") == "tool"]
    errors = [e for e in events if e.get("type") == "error" or "error" in str(e.get("type", ""))]
    perms = [e for e in events if "permission" in str(e.get("type", ""))]
    return {"session": sid, "text": text, "tools": tools, "errors": errors[:3], "permission_asks": len(perms) + p.stderr.count("permission requested:"), "rc": p.returncode,
            "stderr": p.stderr[-800:] if p.returncode else "", "seconds": round(time.time() - t0, 1)}

# ---------------------------------------------------------------- simulated user
PERSONA = """You are Riya Testwal, a job seeker using a job-search assistant. Reply as Riya, briefly (one to three sentences),
to the assistant's last message. Background: Senior Software Engineer – Backend at Sunfield Cloud since April 2023
(Gurugram); before that Software Engineer 2 – Platform at Windline Payments, July 2019 to March 2023 (Pune). B.Tech
Computer Science, Example Institute of Technology, 2019. Cut checkout API p99 latency from 820 ms to 310 ms for 1.2
million daily users; automated CI/CD for 42 services in GitHub Actions; migrated 18 services onto Kubernetes; Go and
PostgreSQL; AWS Solutions Architect Associate 2022. Current CTC 14 LPA, fixed 12 LPA. Notice period 60 days. Field:
software engineering. Keep the 20% threshold, on CTC. Target families: keep the defaults. Prefers Noida or Gurugram;
nothing to avoid; open to the UAE (Dubai) and Saudi Arabia, in that order; remote yes, relocation yes. Resume: PDF and
DOCX, 2 pages, email, phone and city. Gmail: paste them in. When asked to confirm drafted facts, confirm them all. When
unsure of a number, say "I don't know". When asked which jobs to check, shortlist or tailor, pick the first one. Never
invent new achievements beyond the background above. If the assistant says the step is finished, reply exactly
"DONE"."""

def sim_reply(key, assistant_text, cost):
    d = openrouter("/chat/completions", key, {"model": SIM_MODEL, "max_tokens": 800, "reasoning": {"enabled": False}, "usage": {"include": True},
                                               "provider": {"zdr": True, "data_collection": "deny"},
                                               "messages": [{"role": "system", "content": PERSONA},
                                                            {"role": "user", "content": "The assistant said:\n\n" + assistant_text[-6000:]}]})
    cost[0] += float((d.get("usage") or {}).get("cost") or 0)
    return (d["choices"][0]["message"].get("content") or "DONE").strip()

FINISHED = ("Next: /radar", "Run /sweep", "Check which?", "Shortlist which?", "TIME UP", "scorecard", "Prep the weakest areas?",
            "Offer /grill", "/grill j-", "tell me with /applied", "moved to applied", "Saved", "Nothing was changed")

def run_command(root, key, name, args, model=None, log=None, interactive=True):
    before, sim_cost, turns, total_tools, asks, errs = usage(key), [0.0], 0, [], 0, []
    r = turn(root, key, args, command=name, model=model, log=log)
    sid, t0 = r["session"], time.time()
    while True:
        turns += 1; total_tools += r["tools"]; asks += r["permission_asks"]; errs += r["errors"] + ([r["stderr"]] if r["stderr"] else [])
        if not interactive or turns >= MAX_TURNS.get(name, 6) or not r["text"] or not sid or any(f in r["text"] for f in FINISHED): break
        reply = "final" if name == "tailor" and turns >= 1 else sim_reply(key, r["text"], sim_cost)
        if reply.strip().upper().startswith("DONE"): break
        r = turn(root, key, reply, session=sid, model=model, log=log)
    after = usage(key)
    engine_calls = [c for t, c in total_tools if t == "bash" and c and "engine/" in c.replace("\\", "/")]
    return {"command": name, "model": model, "turns": turns, "tool_calls": len(total_tools), "engine_calls": len(engine_calls),
            "permission_asks": asks, "errors": [str(e)[:300] for e in errs][:5], "cost_usd": round(after - before - sim_cost[0], 4),
            "sim_cost_usd": round(sim_cost[0], 4), "minutes": round((time.time() - t0) / 60, 1)}

# ---------------------------------------------------------------- plans
WEEK = [("start", ""), ("radar", ""), ("sweep", ""), ("check", "j-0001"), ("tailor", "j-0001"), ("prep", "j-0001"),
        ("applied", "j-0001 today via careers site, DRY RUN"), ("update", "j-0001: got a call for interview round 1 on Friday"),
        ("grill", "j-0001 10"), ("today", ""), ("help", "")]
PER_WEEK = {"sweep": 5, "today": 5, "check": 3, "tailor": 1, "prep": 1, "grill": 1, "update": 2, "applied": 1, "radar": 1, "help": 0}

def ensure_job(root):
    """A job with a JD and a seeded profile for /check etc. if the sweep or /start didn't run (invented posting)."""
    env = dict(os.environ, FOUNDRY_HOME=str(root))
    (root / "data" / "tmp").mkdir(parents=True, exist_ok=True)
    if not (root / "profile" / "facts.jsonl").exists() or not (root / "profile" / "facts.jsonl").read_text(encoding="utf-8").strip():
        for k, obj in (("identity", persona.IDENTITY), ("employment", persona.EMPLOYMENT), ("education", persona.EDUCATION)):
            (root / "data" / "tmp" / f"{k}.json").write_text(json.dumps(obj), encoding="utf-8")
            subprocess.run([sys.executable, str(root / "engine" / "profile_cli.py"), "set", k, f"@data/tmp/{k}.json"], env=env, cwd=str(root), check=True, capture_output=True)
        subprocess.run([sys.executable, str(root / "engine" / "profile_cli.py"), "current", "Senior Software Engineer", "--ctc", "14", "--fixed", "12"], env=env, cwd=str(root), check=True, capture_output=True)
        (root / "data" / "tmp" / "facts.json").write_text(json.dumps(persona.FACTS), encoding="utf-8")
        subprocess.run([sys.executable, str(root / "engine" / "facts.py"), "add", "@data/tmp/facts.json"], env=env, cwd=str(root), check=True, capture_output=True)
        subprocess.run([sys.executable, str(root / "engine" / "facts.py"), "confirm", "f-0001,f-0002,f-0003,f-0004,f-0005,f-0006"], env=env, cwd=str(root), check=True, capture_output=True)
    jobs = json.loads((root / "data" / "jobs.json").read_text(encoding="utf-8"))["jobs"] if (root / "data" / "jobs.json").exists() else []
    j0 = next((j for j in jobs if j["id"] == "j-0001"), None)
    if j0 and j0.get("jd"): return
    (root / "data" / "tmp" / "jd.txt").write_text(("Senior Backend Engineer, Acme Cloud (invented posting). Own the payments API: p99 "
        "latency, availability and error budgets for 2,000 requests per second; design services in Go and Java on Kubernetes with Kafka "
        "and PostgreSQL; run CI/CD and observability; mentor two engineers. 5+ years building backend services; AWS a plus. Gurugram, "
        "hybrid.\n") * 2, encoding="utf-8")
    if j0:
        subprocess.run([sys.executable, str(root / "engine" / "jobs.py"), "jd", "j-0001", "--file", "data/tmp/jd.txt"], env=env, cwd=str(root), check=True, capture_output=True)
        return
    (root / "data" / "tmp" / "j.json").write_text(json.dumps({"company": "Acme Cloud", "title": "Senior Backend Engineer", "location": "Gurugram, Haryana",
                                                             "source": {"tier": 3, "via": "pasted"}}), encoding="utf-8")
    subprocess.run([sys.executable, str(root / "engine" / "jobs.py"), "add", "@data/tmp/j.json", "--jd-file", "data/tmp/jd.txt"], env=env, cwd=str(root), check=True, capture_output=True)

def week(a):
    key = dev_keys.get("openrouter") or sys.exit("no dev OpenRouter key: python scripts/dev_keys.py set openrouter")
    models = {}
    for t in [x for x in a if "=" in x and not x.startswith("--")]:
        k, v = t.split("=", 1); models[k] = v
    only = (a[a.index("--only") + 1].split(",") if "--only" in a else None)
    out = pathlib.Path(a[a.index("--out") + 1]) if "--out" in a else REPO / "notes" / "opencode-measure.json"
    tiers = json.loads((REPO / "scripts" / "opencode_models.json").read_text(encoding="utf-8"))
    swap = {tiers["tiers"][t]: m for t, m in models.items()}
    root = scratch("week", swap)
    log = pathlib.Path(tempfile.gettempdir()) / (out.stem + ".events.jsonl")
    log.unlink(missing_ok=True)
    rows = []
    for name, args in WEEK:
        if only and name not in only: continue
        if name in ("check", "tailor", "prep", "applied", "update", "grill"): ensure_job(root)
        r = run_command(root, key, name, args, log=log, interactive=name not in ("help", "today"))
        r["model"] = swap.get(tiers["tiers"][tiers["commands"][name]], tiers["tiers"][tiers["commands"][name]])
        rows.append(r); print(json.dumps(r), flush=True)
        out.write_text(json.dumps({"rows": rows, "per_week": PER_WEEK}, indent=1), encoding="utf-8")
    return 0

def probe(a):
    key = dev_keys.get("openrouter") or sys.exit("no dev OpenRouter key")
    root = scratch("probe")
    for m in [x for x in a if "/" in x]:
        r = turn(root, key, "Run `python engine/today.py` and tell me in one line how many radar companies are due.", model=m)
        ok = any(t == "bash" and c and "today.py" in c for t, c in r["tools"])
        print(json.dumps({"model": m, "tool_call_ok": ok, "tools": r["tools"][:4], "answer": r["text"][:200], "errors": [str(e)[:200] for e in r["errors"]],
                          "stderr": r["stderr"][:300]}), flush=True)
    return 0

def start_other(a):
    """A real /start on Groq or Cerebras (their own keys, ZDR switched on in their consoles first). Invented data only."""
    prov = a[a.index("--provider") + 1]
    m = a[a.index("--model") + 1]
    key = dev_keys.get(prov) or sys.exit(f"no dev {prov} key: python scripts/dev_keys.py set {prov}")
    root = scratch(f"start-{prov}")
    cfg = json.loads((root / "opencode.json").read_text(encoding="utf-8"))
    env_name = f"FOUNDRY_{prov.upper()}_KEY"
    cfg["enabled_providers"] = [prov]; cfg["model"] = cfg["small_model"] = f"{prov}/{m}"
    cfg["provider"] = {prov: {"options": {"apiKey": "{env:" + env_name + "}"}, "models": {m: {}}}}
    (root / "opencode.json").write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    for f in (root / ".opencode").rglob("*.md"):
        lines = f.read_text(encoding="utf-8").split("\n")
        f.write_text("\n".join(f"model: {prov}/{m}" if l.startswith("model: ") else l for l in lines), encoding="utf-8")
    sim_key = dev_keys.get("openrouter") or sys.exit("the simulated user runs on the dev OpenRouter key")
    out = pathlib.Path(a[a.index("--out") + 1]) if "--out" in a else REPO / "notes" / f"opencode-start-{prov}.json"
    log = out.with_suffix(".events.jsonl"); log.unlink(missing_ok=True)
    t0, turns, r = time.time(), 0, turn(root, key, "", command="start", log=log, extra_env={env_name: key})
    sid, cost, rows = r["session"], [0.0], []
    while True:
        turns += 1; rows.append({"turn": turns, "tools": len(r["tools"]), "errors": [str(e)[:300] for e in r["errors"]], "stderr": r["stderr"][:300]})
        if turns >= MAX_TURNS["start"] or not r["text"] or not sid or r["errors"]: break
        reply = sim_reply(sim_key, r["text"], cost)
        if reply.upper().startswith("DONE"): break
        r = turn(root, key, reply, session=sid, log=log, extra_env={env_name: key})
    stages = json.loads((root / "profile" / "intake.json").read_text(encoding="utf-8"))["stages"]
    res = {"provider": prov, "model": m, "turns": turns, "minutes": round((time.time() - t0) / 60, 1), "stages": stages, "turn_log": rows}
    out.write_text(json.dumps(res, indent=1), encoding="utf-8"); print(json.dumps(res)[:2000])
    return 0

def main(a):
    if not a: print(__doc__); return 1
    if a[0] == "start": return start_other(a[1:])
    if a[0] == "probe": return probe(a[1:])
    if a[0] == "week": return week(a[1:])
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
