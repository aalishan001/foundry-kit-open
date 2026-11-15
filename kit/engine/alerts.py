#!/usr/bin/env python3
"""Job-alert emails -> rows {title, company, location, url, via}. Pasted text, .txt or .eml files.
  alerts.py parse <file> [--json]      what the email holds; read the result before adding anything
  alerts.py senders [--json]           the alert senders of every radar company (its careers domain, its Workday tenant,
                                       and alert.senders from the pack)
  alerts.py company-of <sender>        which radar company an alert email's sender belongs to, if any
Best effort and deterministic: alert formats vary, so Claude reviews the rows (and fixes or drops them) before
sweep.py alerts adds them. Links from LinkedIn or Naukri are kept as references only; they are never fetched.
"""
import email, email.policy, json, pathlib, re, sys
from urllib.parse import urlparse
from html_text import parse as html_parse
from _common import read_text, die

URL = re.compile(r"https?://[^\s<>\"')\]]+")
JOBLIKE = re.compile(r"(?i)(/jobs?/view|/jobs?/|/job-listings|/viewjob|[?&]jk=|/careers?/job|/jobdetail|/job-details|myworkdayjobs\.com|"
                     r"greenhouse\.io|lever\.co|smartrecruiters\.com|/openings?/|/positions?/|/vacanc)")
SKIP = re.compile(r"(?i)(unsubscribe|preferences|settings|privacy|help|terms|/feed|/search\?|manage[-_ ]alerts|/notifications|/profile|/mynetwork|"
                  r"/messaging|/premium|app\.|/apps/|tracking-pixel|/email/|/legal)")
GENERIC = re.compile(r"(?i)^(view( this)? job|apply( now)?|see (all|more) jobs|see job|view details|easy apply|more jobs|view|apply|learn more)$")
NOISE = re.compile(r"(?i)^(new|promoted|actively recruiting|actively hiring|hiring now|easy apply|be an early applicant|top applicant|"
                   r"fast[- ]growing|in your network|your profile matches.*|\d+ (applicants?|connections?)|view job|apply now|"
                   r"posted .*|just posted|\d+ (days?|hours?|weeks?) ago|today|reposted.*|.*alumni work here|.*school alumni.*|"
                   r"\d+ (benefits?|company alumni|connections? work here)|your job alert for .*|\d+ new jobs? match.*)$")   # badge lines between a title and its link
SSID = re.compile(r"ssid_(\d+)")   # LinkedIn's saved-search id in each job link's tracking: which alert sent the row

def eml_parts(raw):
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    text, anchors = [], []
    for part in msg.walk():
        ct = part.get_content_type()
        try: body = part.get_content()
        except (LookupError, KeyError): continue
        if ct == "text/plain": text.append(body)
        elif ct == "text/html":
            t, a = html_parse(body); text.append(t); anchors += a
    return msg.get("from", ""), "\n".join(text), anchors

def clean_lines(text):
    return [l.strip(" -•·|\t") for l in text.replace("\r\n", "\n").split("\n")]

def canonical(url):
    u = urlparse(url.rstrip(".,;"))
    q = "&".join(x for x in u.query.split("&") if x.split("=")[0].lower() in ("jk", "jobid", "job_id", "gh_jid", "id")) if u.query else ""
    return f"https://{u.netloc}{u.path.rstrip('/')}" + (f"?{q}" if q else "")

def context(lines, i):
    """Up to three meaningful lines just above line i: title, company, location (LinkedIn and most boards)."""
    out, j = [], i - 1
    while j >= 0 and len(out) < 3:
        l = lines[j]
        if l and not URL.search(l) and not NOISE.match(l) and not GENERIC.match(l) and len(l) <= 120: out.append(l)
        elif URL.search(l) and out: break
        j -= 1
    return list(reversed(out))

def split_title(line):
    m = re.match(r"^(.*?)\s+(?:at|@)\s+(.+?)$", line)
    return (m.group(1), m.group(2)) if m and len(m.group(1)) > 3 else (line, "")

def ssid_of(url):
    m = SSID.search(url or "")
    return m.group(1) if m else None

def split_company(rows):
    """LinkedIn puts "Company · Place" on one line: split it when the place is empty; drop its header row."""
    rows[:] = [r for r in rows if not r["title"].lower().startswith("your job alert for")]
    for r in rows:
        if not r["location"] and " · " in r["company"]:
            r["company"], r["location"] = (x.strip() for x in r["company"].split(" · ", 1))
    return rows

def rows_from(text, anchors=(), sender=""):
    lines = clean_lines(text)
    out, seen = [], set()
    anchor_text = {}
    for href, t in anchors:
        if href and href.startswith("http") and t and not GENERIC.match(t): anchor_text.setdefault(canonical(href), t)
    for i, line in enumerate(lines):
        for m in URL.finditer(line):
            url = m.group(0)
            if not JOBLIKE.search(url) or SKIP.search(url): continue
            key = canonical(url)
            if key in seen: continue
            seen.add(key)
            ctx = context(lines, i)
            if ctx and split_title(ctx[0])[1]:   # "Title at Company", then the place
                (title, company), location = split_title(ctx[0]), (ctx[1] if len(ctx) > 1 else "")
            else:
                title = ctx[0] if ctx else ""
                company = ctx[1] if len(ctx) > 1 else ""
                location = ctx[2] if len(ctx) > 2 else ""
            title = anchor_text.get(key) or title
            if title: out.append({"title": title, "company": company, "location": location, "url": key,
                                  "via": urlparse(key).netloc.replace("www.", "") or sender, "ssid": ssid_of(url)})
    for href, t in anchors:   # html alerts: the link text is the title; the lines after it usually name company and place
        if not href or not href.startswith("http") or not JOBLIKE.search(href) or SKIP.search(href): continue
        key = canonical(href)
        if key in seen or not t or GENERIC.match(t): continue
        seen.add(key)
        title, company = split_title(t)
        location = ""
        if t in lines:
            after = [l for l in lines[lines.index(t) + 1:lines.index(t) + 6] if l and not NOISE.match(l) and not GENERIC.match(l) and len(l) <= 120]
            if not company and after: company = after.pop(0)
            if after: location = after[0]
        out.append({"title": title, "company": company, "location": location, "url": key, "via": urlparse(key).netloc.replace("www.", ""),
                    "ssid": ssid_of(href)})
    return out

def parse_file(path):
    p = pathlib.Path(path)
    if not p.is_file(): die(f"no file {path}")
    if p.suffix.lower() == ".eml":
        sender, text, anchors = eml_parts(p.read_bytes())
        return split_company(rows_from(text, anchors, sender))
    t = read_text(p)
    if "<html" in t.lower() or "<a " in t.lower():
        text, anchors = html_parse(t); return split_company(rows_from(text, anchors))
    return split_company(rows_from(t))

# ---------------------------------------------------------------- companies' own alert emails
SHARED_HOSTS = ("oraclecloud.com",)   # careers sites hosted for many companies: never a sender of their own

def senders():
    """{company: [sender address or domain]} for every radar company: its careers site's own domain, its Workday
    tenant's address, and the pack's alert.senders."""
    from _common import DATA, load
    from fetch import host_of, org_domain, JOB_PLATFORMS
    out = {}
    for c in (load(DATA / "radar.json", {}) or {}).get("companies", []):
        s = []
        h = host_of(c.get("careers_url") or "")
        if h and not h.endswith(JOB_PLATFORMS + SHARED_HOSTS): s.append(org_domain(h))
        pt = c.get("portal") or {}
        if pt.get("type") == "workday" and pt.get("tenant"): s.append(f"{pt['tenant']}@myworkday.com")
        s += [x.lower() for x in (c.get("alert") or {}).get("senders") or []]
        out[c["company"]] = sorted(set(s))
    return out

def company_of(sender):
    """The radar company an alert sender belongs to, or None."""
    m = re.search(r"[\w.+-]+@[\w.-]+", sender or "")
    addr = (m.group(0) if m else (sender or "")).lower()
    dom = addr.split("@")[-1]
    for name, pats in senders().items():
        for p in pats:
            if ("@" in p and addr == p) or ("@" not in p and (dom == p or dom.endswith("." + p))): return name
    return None

def main(a):
    if a and a[0] == "senders":
        s = senders()
        if "--json" in a: print(json.dumps(s, indent=1, ensure_ascii=False)); return 0
        for k, v in s.items(): print(f"{k:<28} {', '.join(v) or '-'}")
        return 0
    if len(a) >= 2 and a[0] == "company-of":
        c = company_of(a[1]); print(c or "not a radar company"); return 0 if c else 1
    if len(a) >= 2 and a[0] == "parse":
        rows = parse_file(a[1])
        if "--json" in a: print(json.dumps(rows, indent=1, ensure_ascii=False)); return 0
        for n, r in enumerate(rows, 1): print(f"{n:>2}. {r['title']} | {r['company'] or '?'} | {r['location'] or '?'} | {r['via']}"
                                              + (f" | alert {r['ssid']}" if r.get("ssid") else ""))
        print(f"-- {len(rows)} job(s) found in the email")
        return 0
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
