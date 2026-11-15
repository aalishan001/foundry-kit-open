#!/usr/bin/env python3
"""Jobs they have found and applications they have sent. Ids, dates, hashes, file moves and links between records are
done here. Statuses change only on their word, with one rule they set: a job becomes applied when an application names it.
  jobs.py add <payload> [--jd-file <file>] [--dry-run]
        one job or a list: {company, title, url?, location?, remote?, posted?, source: {tier: 1|2|3, via, ref?}}.
        A job already known (same url, or same company + title + location) is reported, not added twice
  jobs.py jd <j-id> --file <file>           save the posting's text (min 200 characters; phone numbers masked)
  jobs.py check <payload>                   {name?, jobs: [{id, fit: {level, pay, location, match, likeliness,
                                            verdict, top_facts?, gaps?}}]} -> data/checks/<ts>.json, fit on each job
  jobs.py status <j-id> <new|shortlisted|dismissed|closed> [--note T] [--date D]
  jobs.py triage <j-id> <high|medium|low> "<one line>"   the /sweep rating of a new job (once ranked, it stops waiting)
  jobs.py waiting                           new jobs not yet ranked by /sweep, oldest first
  jobs.py list [--status S[,S]] [--all] [--by fit] [--company C]   new and shortlisted by default; --by fit lists them
                                            in apply order (match, then likeliness)
  jobs.py show <j-id|a-id>
  jobs.py applied <payload> (--resume <inbox file> | --tailored <j-id>/v<N>) [--jd-file <file>] [--dry-run]
        --backfill: an application sent before setup (no JD copy or resume needed; marked as backfilled)
        {job?, company?, role?, link?, date, channel, referrer?, notes?}; channel: careers_site | referral |
        recruiter | email | job_board | other. The resume sent is stored once by hash (data/resumes/<sha256>.<ext>)
  jobs.py app <a-id> <status> [--round R] [--note T] [--date D] [--next YYYY-MM-DD]
        a status they reported: applied oa screen interviewing offer accepted declined rejected withdrawn ghosted
        (interviewing needs --round; --next records the date of the next interview or call)
  jobs.py apps [--status S[,S]] [--all]     open applications by default, most recently changed first
"""
import hashlib, json, pathlib, shutil, sys
from _common import (HOME, DATA, INBOX, HTTPS, PHONE, load, save, read_jsonl, payload, opt, die, today, stamp,
                     ts_name, date_arg, next_id, days_since, rel, read_text, norm, slug, unique_path, search_rules)
from validate import JOB_STATUSES, APP_STATUSES, APP_CLOSED, CHANNELS, jobs_errors

JOBS, APPS = DATA / "jobs.json", DATA / "apps.json"
JDS, CHECKS, RESUMES, RES_INDEX, RENDERS = DATA / "jds", DATA / "checks", DATA / "resumes", DATA / "resumes" / "index.json", DATA / "renders.jsonl"
MANUAL = {"new", "shortlisted", "dismissed", "closed", "parked"}
REPOST_REVIVE_DAYS = 60

def load_jobs(): return load(JOBS, {"jobs": []})
def load_apps(): return load(APPS, {"apps": []})
def find(rows, i): return next((r for r in rows if r["id"] == i), None)

def dedupe_key(company, title, location):
    return "|".join(norm(x or "") for x in (company, title, location))

# ---------------------------------------------------------------- JD copies
def jd_copy(job, text, source):
    text = (text or "").replace("\r\n", "\n").strip()
    if len(text) < 200: die("the JD text is under 200 characters: paste the full posting (never guess a JD)")
    masked = len(PHONE.findall(text))
    text = PHONE.sub("[phone number removed]", text)
    body = (f"# {job['company']}: {job['title']}\n\n- link: {job.get('url') or 'none (pasted)'}\n- saved: {today().isoformat()}\n"
            f"- source: {source}\n\n---\n\n{text}\n")
    p = JDS / f"{job['id']}.md"; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8", newline="\n")
    job["jd"] = rel(p)
    return masked

def jd_text_of(job):
    if not job.get("jd"): return None
    t = read_text(HOME / job["jd"])
    return t.split("\n---\n", 1)[1].strip() if "\n---\n" in t else t

# ---------------------------------------------------------------- jobs
def new_job(rows, d):
    for k in ("company", "title"):
        if not str(d.get(k) or "").strip(): die(f"{k} is required for every job")
    if d.get("url") and not HTTPS.match(d["url"]): die(f"url must be https: {d['url']}")
    src = d.get("source") or {}
    if src.get("tier") not in (1, 2, 3): die("source.tier must be 1, 2 or 3")
    return {"id": next_id(rows, "j"), "company": d["company"].strip(), "title": d["title"].strip(),
            "location": (d.get("location") or "").strip(), "remote": bool(d.get("remote")), "url": d.get("url") or None,
            "source": {"tier": src["tier"], "via": src.get("via") or "", "ref": src.get("ref")}, "posted": d.get("posted"),
            "first_seen": today().isoformat(), "jd": None, "check": None, "fit": None, "status": "new",
            "snippet": (d.get("snippet") or None), "triage": None,
            "history": [{"date": today().isoformat(), "status": "new", "note": f"found via {src.get('via') or 'tier ' + str(src['tier'])}"}],
            "dedupe_key": dedupe_key(d["company"], d["title"], d.get("location"))}

def existing(rows, d):
    key = dedupe_key(d.get("company"), d.get("title"), d.get("location"))
    by_url = next((r for r in rows if d.get("url") and r.get("url") == d["url"]), None)   # an exact link wins over a key match
    return by_url or next((r for r in rows if r.get("dedupe_key") == key), None)

def add_jobs(items, jd_texts=None, dry=False):
    """-> (added jobs, [(item, existing id)]). jd_texts: {index: text} saved with each new job."""
    data = load_jobs(); rows = data["jobs"]
    added, dupes = [], []
    for i, d in enumerate(items):
        hit = existing(rows + added, d)
        repost = None
        swept = (d.get("source") or {}).get("tier") in (1, 2)   # a job pasted again by hand is reported as known, not as a repost
        if swept and hit and d.get("url") and hit.get("url") and d["url"] != hit["url"] and hit.get("dedupe_key") == dedupe_key(d.get("company"), d.get("title"), d.get("location")):
            repost = hit   # same company, title and place under a new posting: a repost of a known job
        elif hit: dupes.append((d, hit["id"])); continue
        j = new_job(rows + added, d)
        if repost:
            old = repost.get("repost_of") and find(rows + added, repost["repost_of"]) or repost
            stale = old["status"] == "dismissed" and days_since(old["history"][-1]["date"]) > REPOST_REVIVE_DAYS
            if not stale:
                j.update(status="repost", repost_of=old["id"])
                j["history"] = [{"date": today().isoformat(), "status": "repost", "note": f"repost of {old['id']} (same title and place, new posting)"}]
            else: j["history"][0]["note"] += f"; a repost of {old['id']}, dismissed over {REPOST_REVIVE_DAYS} days ago"
            j["dedupe_key"] = dedupe_key(d["company"], d["title"], d.get("location")) + f"|{j['id']}"
        if jd_texts and jd_texts.get(i) and not dry: jd_copy(j, jd_texts[i], j["source"]["via"] or "fetched")
        added.append(j)
    if not dry and added:
        data["jobs"] = rows + added
        errs = jobs_errors(data)
        if errs: die("; ".join(errs))
        save(JOBS, data)
    return added, dupes

def cmd_add(raw, args):
    d = payload(raw); items = d if isinstance(d, list) else [d]
    jd_file = opt(args, "--jd-file")
    texts = {0: read_text(jd_file)} if jd_file and len(items) == 1 else None
    added, dupes = add_jobs(items, texts, "--dry-run" in args)
    for j in added: print(f"{j['id']}  {j['company']} · {j['title']}  {j['location']}" + ("  [dry run]" if "--dry-run" in args else ""))
    for d, i in dupes: print(f"already {i}: {d.get('company')} · {d.get('title')}")
    return 0

def cmd_jd(jid, args):
    f = opt(args, "--file") or die("jd needs --file <file with the posting's text>")
    data = load_jobs(); j = find(data["jobs"], jid) or die(f"no job {jid}")
    masked = jd_copy(j, read_text(f), "pasted" if j["source"]["tier"] == 3 else "fetched")
    save(JOBS, data)
    print(f"{jid}: JD saved to {j['jd']}" + (f" ({masked} phone number(s) masked)" if masked else ""))
    return 0

def cmd_check(raw):
    d = payload(raw)
    rows = d.get("jobs") or die("check needs jobs: [{id, fit}]")
    data = load_jobs()
    for r in rows:
        j = find(data["jobs"], r.get("id")) or die(f"no job {r.get('id')}")
        fit = r.get("fit") or {}
        for k in ("match", "likeliness"):
            if not (isinstance(fit.get(k), int) and 0 <= fit[k] <= 100): die(f"{j['id']}: fit.{k} must be an integer 0-100")
        if not str(fit.get("verdict") or "").strip(): die(f"{j['id']}: fit.verdict is required (one line)")
        if not j.get("jd"): die(f"{j['id']}: save the JD first (jobs.py jd {j['id']} --file ...): a check needs the posting's text")
    name = f"{ts_name()}" + (f"-{slug(d['name'])}" if d.get("name") else "")
    p = unique_path(CHECKS, name, "json")
    save(p, {"ts": stamp(), "jobs": rows})
    for r in rows:
        j = find(data["jobs"], r["id"])
        if j.get("fit"): j.setdefault("fit_history", []).append({"date": today().isoformat(), "check": j.get("check"), "fit": j["fit"]})   # a re-check keeps the old fit
        j["fit"] = r["fit"]; j["check"] = rel(p)
    save(JOBS, data)
    for r in sorted(rows, key=lambda r: (-r["fit"]["match"], -r["fit"]["likeliness"])):
        j = find(data["jobs"], r["id"])
        print(f"{j['id']}  match {r['fit']['match']:>3}  likeliness {r['fit']['likeliness']:>3}  {j['company']} · {j['title']}  {r['fit']['verdict']}")
    print(f"saved {rel(p)}")
    return 0

def cmd_status(jid, status, args):
    if status not in MANUAL: die(f"status must be one of {sorted(MANUAL)} (applied is set by jobs.py applied)")
    data = load_jobs(); j = find(data["jobs"], jid) or die(f"no job {jid}")
    if j["status"] == status: die(f"{jid} is already {status}")
    when = date_arg(args)
    if when < j["history"][-1]["date"]: die(f"{when} is before the last change ({j['history'][-1]['date']})")
    note = (opt(args, "--note") or "").strip()
    if status == "shortlisted":
        cap = (search_rules().get("rules") or {}).get("company_app_cap")
        open_n = sum(1 for a in load_apps()["apps"] if a["company"].lower() == j["company"].lower() and a["status"] not in APP_CLOSED)
        if cap is not None and open_n >= cap:
            status, note = "parked", f"{j['company']} already has {open_n} open application(s), their cap is {cap}: parked, still swept" + (f"; {note}" if note else "")
    j["status"] = status
    j["history"].append({"date": when, "status": status, "note": note})
    save(JOBS, data)
    print(f"{jid}  {j['company']} · {j['title']}: {status}")
    return 0

def cmd_list(args):
    want = set((opt(args, "--status") or "").split(",")) - {""}
    rows = [j for j in load_jobs()["jobs"] if (j["status"] in want if want else ("--all" in args or j["status"] in ("new", "shortlisted")))]
    if opt(args, "--company"): rows = [j for j in rows if j["company"].lower() == opt(args, "--company").lower()]
    if opt(args, "--by") == "fit":   # apply order: the best fits first, unchecked last
        rows = sorted(rows, key=lambda j: (-((j.get("fit") or {}).get("match") or -1), -((j.get("fit") or {}).get("likeliness") or -1), j["id"]))
        for n, j in enumerate(rows, 1):
            fit = j.get("fit") or {}
            print(f"{n:>2}. {j['id']}  {j['status']:<11} {j['company']} · {j['title']}  " + (f"match {fit['match']}, likeliness {fit['likeliness']}" if fit else "not checked yet"))
        return 0
    if not rows: print("No jobs" + (" with that status." if want else " waiting.")); return 0
    order = {s: i for i, s in enumerate(JOB_STATUSES)}
    for j in sorted(rows, key=lambda j: (order[j["status"]], -((j.get("fit") or {}).get("match") or -1), j["id"])):
        fit = j.get("fit") or {}
        print(f"{j['id']}  {j['status']:<11} {j['company']} · {j['title']}  {j['location'] or '-'}"
              + (f"  match {fit['match']}" if fit else "") + f"  (seen {j['first_seen']}, tier {j['source']['tier']})")
    return 0

def cmd_show(i):
    rows = load_jobs()["jobs"] if i.startswith("j-") else load_apps()["apps"]
    r = find(rows, i) or die(f"no record {i}")
    print(json.dumps(r, indent=1, ensure_ascii=False))
    return 0

# ---------------------------------------------------------------- resumes they sent
def sha256(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()

def kind_of(p):
    b = pathlib.Path(p).read_bytes()[:5]
    if b.startswith(b"%PDF-"): return "pdf"
    if b.startswith(b"PK") and pathlib.Path(p).suffix.lower() == ".docx": return "docx"
    return None

def store_resume(src, render=None, move=False, dry=False):
    """Store a sent resume once, by hash. -> (sha256, note)."""
    src = pathlib.Path(src)
    if not src.is_file(): die(f"no file {src}")
    ext = kind_of(src) or die(f"{src.name} is not a PDF or DOCX: drop the exact resume file you sent")
    h = sha256(src)
    idx = load(RES_INDEX, {"resumes": []})
    row = next((r for r in idx["resumes"] if r["sha256"] == h), None)
    if row: note = f"already stored as {row['file']}"
    else:
        if render is None:
            render = next(({k: r[k] for k in ("job", "version", "format", "file")} for r in reversed(read_jsonl(RENDERS)) if r.get("sha256") == h), None)
        row = {"sha256": h, "file": f"data/resumes/{h}.{ext}", "original_name": src.name, "added": today().isoformat(), "render": render}
        note = f"stored as {row['file']}" + (f" (render {render['job']} v{render['version']})" if render else " (not a render of this kit)")
    if dry: return h, note + " [dry run]"
    dest = HOME / row["file"]
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        (shutil.move if move else shutil.copyfile)(str(src), str(dest))
        if sha256(dest) != h: die("the stored copy doesn't match its hash; nothing linked")
    elif move: src.unlink()
    if row not in idx["resumes"]: idx["resumes"].append(row); save(RES_INDEX, idx)
    return h, note

def tailored_file(ref):
    """'j-0007/v3' -> (the rendered file for that version, render row). PDF preferred."""
    if "/v" not in ref: die("--tailored takes <job-id>/v<N>, e.g. j-0007/v3")
    jid, v = ref.split("/v", 1)
    rows = [r for r in read_jsonl(RENDERS) if r.get("job") == jid and str(r.get("version")) == v]
    if not rows: die(f"no render of {ref}: run render.py first, or pass --resume with the file you sent")
    r = sorted(rows, key=lambda r: r.get("format") != "pdf")[0]
    p = HOME / r["file"]
    if not p.is_file(): die(f"{r['file']} is gone; pass --resume with the file you sent")
    if sha256(p) != r["sha256"]: die(f"{r['file']} changed after it was rendered; pass --resume with the exact file you sent")
    return p, {k: r[k] for k in ("job", "version", "format", "file")}

# ---------------------------------------------------------------- applications
def cmd_applied(raw, args):
    d, dry = payload(raw), "--dry-run" in args
    jobs = load_jobs(); job = None
    if d.get("job"):
        job = find(jobs["jobs"], d["job"]) or die(f"no job {d['job']}")
        if job["status"] == "applied": die(f"{job['id']} is already applied")
        d.setdefault("company", job["company"]); d.setdefault("role", job["title"]); d.setdefault("link", job.get("url"))
    for k in ("company", "role", "date", "channel"):
        if not str(d.get(k) or "").strip(): die(f"{k} is required")
    if d.get("link") and not HTTPS.match(d["link"]): die("link must be https")
    date = date_arg(["--date", d["date"]])
    if d["channel"] not in CHANNELS: die(f"channel must be one of {CHANNELS}")
    if d.get("referrer") and d["channel"] != "referral": die("a referrer goes with channel referral")
    jd_file = opt(args, "--jd-file")
    backfill = "--backfill" in args
    if not backfill and not ((job and job.get("jd")) or jd_file): die("a JD copy is required: --jd-file <file with the posting's text>, or apply to a job with a saved JD")
    if opt(args, "--tailored"):
        src, render = tailored_file(opt(args, "--tailored")); move = False
    elif opt(args, "--resume"):
        src, render = pathlib.Path(opt(args, "--resume")), None
        move = src.resolve().parent == INBOX.resolve()
    elif backfill: src = render = None; move = False
    else: die("say which resume was sent: --tailored <job-id>/v<N> or --resume <file in inbox>")
    apps = load_apps()
    aid = next_id(apps["apps"], "a")
    h, note = store_resume(src, render, move, dry) if src else (None, "backfilled: sent before setup, resume not on file")
    app = {"id": aid, "job": job["id"] if job else None, "company": d["company"].strip(), "role": d["role"].strip(),
           "link": d.get("link"), "applied": date, "channel": d["channel"], "referrer": (d.get("referrer") or "").strip() or None,
           "notes": (d.get("notes") or "").strip(), "resume": h, "tailored": opt(args, "--tailored"), "status": "applied",
           "round": None, "next": None, "history": [{"date": date, "status": "applied", "round": None, "note": "logged", "source": "user"}],
           "created": stamp(), "source": "user", **({"backfill": True} if backfill else {})}
    if dry:
        print(json.dumps(app, indent=1, ensure_ascii=False)); print(f"resume: {note}"); return 0
    if job:
        if jd_file and not job.get("jd"): jd_copy(job, read_text(jd_file), "pasted")
        on = max(date, job["history"][-1]["date"])
        job["status"] = "applied"; job["history"].append({"date": on, "status": "applied", "note": f"application {aid}"})
        save(JOBS, jobs)
    elif jd_file:
        job_stub = {"id": aid, "company": app["company"], "title": app["role"], "url": app["link"]}
        jd_copy(job_stub, read_text(jd_file), "pasted"); app["jd"] = job_stub["jd"]
    apps["apps"].append(app); save(APPS, apps)
    print(f"{aid}  {app['company']} · {app['role']}  applied {date} via {app['channel']}" + (f" (referred by {app['referrer']})" if app["referrer"] else ""))
    print(f"  resume: {note}" + (f"\n  job {job['id']} -> applied" if job else ""))
    return 0

def cmd_app(aid, status, args):
    if status not in APP_STATUSES: die(f"status must be one of {APP_STATUSES}")
    rnd = opt(args, "--round")
    if status == "interviewing" and not rnd: die("interviewing needs --round (e.g. --round 2, or --round 'technical')")
    if rnd and status != "interviewing": die("--round goes with interviewing only")
    when = date_arg(args)
    nxt = date_arg(args, "--next", allow_future=True) if opt(args, "--next") else None
    apps = load_apps(); a = find(apps["apps"], aid) or die(f"no application {aid}")
    if when < a["history"][-1]["date"]: die(f"{when} is before the last change ({a['history'][-1]['date']})")
    if (a["status"], a.get("round")) == (status, rnd) and not nxt: die(f"{aid} is already {status}")
    a.update(status=status, round=rnd, next=nxt if status not in APP_CLOSED else None)
    a["history"].append({"date": when, "status": status, "round": rnd, "note": (opt(args, "--note") or "").strip(), "source": "user"})
    save(APPS, apps)
    print(f"{aid}  {a['company']} · {a['role']}: {status}" + (f" (round {rnd})" if rnd else "") + f" on {when}" + (f"; next on {nxt}" if nxt else ""))
    return 0

def last_change(r): return r["history"][-1]["date"]

def cmd_apps(args):
    want = set((opt(args, "--status") or "").split(",")) - {""}
    rows = [a for a in load_apps()["apps"] if (a["status"] in want if want else ("--all" in args or a["status"] not in APP_CLOSED))]
    if not rows: print("No applications" + (" with that status." if want else " open.")); return 0
    for a in sorted(rows, key=lambda a: (last_change(a), a["id"]), reverse=True):
        st = a["status"] + (f" r{a['round']}" if a.get("round") else "")
        print(f"{a['id']}  {st:<16} {last_change(a)} ({days_since(last_change(a))} d)  {a['company']} · {a['role']}  [{a['channel']}]"
              + (f"  next {a['next']}" if a.get("next") else ""))
    return 0

TRIAGE = ("high", "medium", "low")

def cmd_triage(args):
    if len(args) < 3 or args[1] not in TRIAGE: die('usage: jobs.py triage <j-id> <high|medium|low> "<one line>"')
    data = load_jobs(); j = find(data["jobs"], args[0]) or die(f"no job {args[0]}")
    j["triage"] = {"rating": args[1], "why": args[2].strip(), "date": today().isoformat()}
    save(JOBS, data)
    print(f"{j['id']}  {args[1]}: {j['company']} · {j['title']}")
    return 0

def waiting(rows=None):
    rows = rows if rows is not None else load_jobs()["jobs"]
    return sorted((j for j in rows if j["status"] == "new" and not j.get("triage")), key=lambda j: (j["first_seen"], j["id"]))

def cmd_waiting(args):
    w = waiting()
    if not w: print("nothing waiting: every new job is ranked"); return 0
    for j in w:
        print(f"{j['id']}  {j['company']} · {j['title']}  {j['location'] or '-'}  (tier {j['source']['tier']}, via {j['source']['via'] or '-'}"
              + (", JD saved" if j.get("jd") else ", no JD") + f", seen {j['first_seen']})")
        if j.get("snippet") and not j.get("jd"): print(f"        {j['snippet'][:200]}")
    print(f"-- {len(w)} waiting to be ranked")
    return 0

def main(a):
    if not a: print(__doc__); return 1
    cmd, rest = a[0], a[1:]
    if cmd == "add" and rest: return cmd_add(rest[0], rest[1:])
    if cmd == "jd" and rest: return cmd_jd(rest[0], rest[1:])
    if cmd == "check" and rest: return cmd_check(rest[0])
    if cmd == "status" and len(rest) >= 2: return cmd_status(rest[0], rest[1], rest[2:])
    if cmd == "list": return cmd_list(rest)
    if cmd == "show" and rest: return cmd_show(rest[0])
    if cmd == "applied" and rest: return cmd_applied(rest[0], rest[1:])
    if cmd == "app" and len(rest) >= 2: return cmd_app(rest[0], rest[1], rest[2:])
    if cmd == "apps": return cmd_apps(rest)
    if cmd == "triage": return cmd_triage(rest)
    if cmd == "waiting": return cmd_waiting(rest)
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
