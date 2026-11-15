#!/usr/bin/env python3
"""Every tier-1 fetch goes through here: an allowlist, a polite user agent, a 20-second timeout, one request per
second per host, robots.txt for careers pages, and a 6-hour cache in data/cache/. LinkedIn and Naukri are refused.
  fetch.py text <url> [--out <file>]   a posting's page as plain text (for /check); refused hosts mean: ask them to paste
  fetch.py allowed <url>               is this host allowed, and why
  fetch.py link <url>                  does a link answer (for /prep resources); any https host but LinkedIn and Naukri
Allowed: the public ATS APIs (Greenhouse, Lever, SmartRecruiters), the job-search APIs they have keys for (Adzuna,
Jooble, JSearch), and any host on their radar (its careers page, its Workday site, and other hosts of the same
organisation's domain). FOUNDRY_FIXTURES=<dir> serves recorded responses from <dir>/index.json instead of the network
(tests and dry runs). API keys are passed as `secrets` and replaced by *** in cache keys, fixture keys and errors.
"""
import hashlib, json, os, pathlib, sys, time, urllib.error, urllib.request
from urllib.parse import urlparse
from _common import CACHE, DATA, load, save, die, rel

UA = "foundry-kit/1.0 (personal job search; one request per second; respects robots.txt)"
TIMEOUT, MIN_GAP, CACHE_HOURS = 20, 1.0, 6
BLOCKED = ("linkedin.com", "naukri.com")
ATS_HOSTS = {"api.ashbyhq.com", "jobs.ashbyhq.com", "boards-api.greenhouse.io", "boards.greenhouse.io", "job-boards.greenhouse.io", "api.lever.co", "api.eu.lever.co",
             "jobs.lever.co", "jobs.eu.lever.co", "api.smartrecruiters.com", "jobs.smartrecruiters.com", "careers.smartrecruiters.com"}
API_HOSTS = {"api.adzuna.com", "jooble.org", "jsearch.p.rapidapi.com"}
# Public job pages on hosted job platforms (the companies' own listings), fetched like careers sites
JOB_PLATFORMS = ("ashbyhq.com", "myworkdayjobs.com", "greenhouse.io", "lever.co", "smartrecruiters.com", "keka.com", "darwinbox.in", "zohorecruit.com",
                 "zohorecruit.in", "turbohire.co", "workable.com", "bamboohr.com", "freshteam.com", "peoplestrong.com")
TWO_LEVEL = {"co.in", "org.in", "net.in", "gov.in", "ac.in", "firm.in", "gen.in", "ind.in", "co.uk", "org.uk", "com.au", "com.br",
             "co.jp", "co.za", "com.sg", "com.my", "com.cn", "co.nz"}

PORTAL_HOSTS = {"amazon": "www.amazon.jobs"}   # company job APIs whose host is fixed by the portal type

class FetchError(Exception): pass

_last, _robots = {}, {}

def host_of(url): return (urlparse(url).hostname or "").lower()

def is_blocked(host): return any(host == b or host.endswith("." + b) for b in BLOCKED)

def org_domain(host):
    parts = host.split(".")
    n = 3 if ".".join(parts[-2:]) in TWO_LEVEL else 2
    return ".".join(parts[-n:])

def radar_hosts():
    hosts = set()
    for c in load(DATA / "radar.json", {"companies": []}).get("companies", []):
        for u in (c.get("careers_url"), (c.get("portal") or {}).get("jobs_url")):
            if u: hosts.add(host_of(u))
        if (c.get("portal") or {}).get("host"): hosts.add(c["portal"]["host"].lower())
        if (c.get("portal") or {}).get("type") in PORTAL_HOSTS: hosts.add(PORTAL_HOSTS[c["portal"]["type"]])
    return hosts

def allowed(url):
    h = host_of(url)
    if not h: return False, "not a web address"
    if is_blocked(h): return False, f"{h} is never fetched (LinkedIn and Naukri are off limits): ask them to paste the posting"
    if urlparse(url).scheme != "https": return False, "only https addresses are fetched"
    if h in ATS_HOSTS: return True, "public job-board API"
    if h in API_HOSTS: return True, "job-search API (their key)"
    rh = radar_hosts()
    if h in rh: return True, "on their radar"
    if h.endswith(".myworkdayjobs.com") and any(x.endswith(".myworkdayjobs.com") and x.split(".")[0] == h.split(".")[0] for x in rh):
        return True, "their radar company's Workday site"
    if org_domain(h) in {org_domain(x) for x in rh if not x.endswith(JOB_PLATFORMS)}:
        return True, "same organisation as a radar company"
    if h.endswith(JOB_PLATFORMS) and not h.endswith("myworkdayjobs.com"): return True, "a company's page on a public job platform"
    return False, f"{h} isn't on their radar: add the company with /radar add, or ask them to paste the posting"

# ---------------------------------------------------------------- fixtures, cache, network
def _key(method, url, body, secrets=()):
    k = f"{method} {url}" + (" " + json.dumps(body, sort_keys=True, separators=(",", ":")) if body is not None else "")
    for s in secrets:
        if s: k = k.replace(s, "***")
    return k

def _fixture(key):
    d = pathlib.Path(os.environ["FOUNDRY_FIXTURES"])
    idx = load(d / "index.json", {}) or {}
    if key not in idx: raise FetchError(f"no recorded response for {key}")
    entry = idx[key]
    if isinstance(entry, dict) and entry.get("status", 200) != 200: raise FetchError(f"HTTP {entry['status']}")
    return (d / (entry["file"] if isinstance(entry, dict) else entry)).read_text(encoding="utf-8")

def _polite(host):
    gap = time.monotonic() - _last.get(host, -MIN_GAP)
    if gap < MIN_GAP: time.sleep(MIN_GAP - gap)
    _last[host] = time.monotonic()

AGENT = "foundry-kit"

def robots_rules(text, agent=AGENT):
    """[(allow?, path pattern)] for this agent from a robots.txt: the group naming it, else the * group (RFC 9309)."""
    groups, cur, last_was_agent = [], None, False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line: continue
        k, v = (x.strip() for x in line.split(":", 1)); k = k.lower()
        if k == "user-agent":
            if not last_was_agent: cur = {"agents": [], "rules": []}; groups.append(cur)
            cur["agents"].append(v.lower()); last_was_agent = True
        elif k in ("allow", "disallow") and cur is not None:
            last_was_agent = False
            if v: cur["rules"].append((k == "allow", v))
        else: last_was_agent = False
    mine = [g for g in groups if any(a != "*" and a in agent.lower() for a in g["agents"])]
    pick = mine or [g for g in groups if "*" in g["agents"]]
    return [r for g in pick for r in g["rules"]]

def _match(pattern, path):
    import re as _re
    rx = "".join(".*" if ch == "*" else ("$" if ch == "$" and i == len(pattern) - 1 else _re.escape(ch)) for i, ch in enumerate(pattern))
    return _re.match(rx, path) is not None

def robots_allows(rules, path):
    """The longest matching rule wins; on a tie, allow wins; no rule means allowed (RFC 9309)."""
    best = None
    for allow, pat in rules:
        if _match(pat, path) and (best is None or len(pat) > len(best[1]) or (len(pat) == len(best[1]) and allow)): best = (allow, pat)
    return True if best is None else best[0]

def _robots_ok(url):
    u = urlparse(url); base = f"{u.scheme}://{u.netloc}"
    if base not in _robots:
        try:
            if os.environ.get("FOUNDRY_FIXTURES"): raise OSError("fixtures: no robots.txt")
            _polite(u.hostname)
            req = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r: rules = robots_rules(r.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, OSError, ValueError):
            rules = []   # no robots.txt (or unreachable): allowed
        _robots[base] = rules
    path = u.path or "/"
    if u.query: path += "?" + u.query
    return robots_allows(_robots[base], path)

def get(url, method="GET", body=None, as_json=False, robots=False, cache_hours=CACHE_HOURS, headers=None, secrets=()):
    """The response body (text, or parsed JSON). Raises FetchError with a plain reason."""
    ok, why = allowed(url)
    if not ok: raise FetchError(why)
    key = _key(method, url, body, secrets)
    if os.environ.get("FOUNDRY_FIXTURES"):
        text = _fixture(key)
        return json.loads(text) if as_json else text
    cfile = CACHE / (hashlib.sha1(key.encode()).hexdigest() + ".json")
    c = load(cfile) if cfile.exists() else None
    if c and time.time() - c["t"] < cache_hours * 3600:
        return json.loads(c["body"]) if as_json else c["body"]
    if robots and not _robots_ok(url): raise FetchError("the site's robots.txt asks tools not to read this page: open it yourself and paste")
    h = host_of(url); _polite(h)
    data = json.dumps(body).encode() if body is not None else None
    hdr = {"User-Agent": UA, "Accept": "application/json" if as_json else "text/html,application/json;q=0.9,*/*;q=0.8", "Accept-Language": "en-US,en;q=0.8"}
    if data is not None: hdr["Content-Type"] = "application/json"
    hdr.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read(); charset = r.headers.get_content_charset() or "utf-8"
            final = r.geturl()
    except urllib.error.HTTPError as e: raise FetchError(f"HTTP {e.code} from {h}")
    except urllib.error.URLError as e: raise FetchError(f"couldn't reach {h} ({e.reason})")
    except (TimeoutError, OSError) as e: raise FetchError(f"{h} didn't answer in {TIMEOUT} s ({type(e).__name__})")
    if is_blocked(host_of(final)): raise FetchError("the page redirected to a site that's never fetched: ask them to paste the posting")
    text = raw.decode(charset, errors="replace")
    if as_json:
        try: parsed = json.loads(text)
        except json.JSONDecodeError: raise FetchError(f"{h} didn't return JSON (the board may have moved)")
    save(cfile, {"t": time.time(), "url": _key("", url, None, secrets).strip(), "body": text})
    return parsed if as_json else text

LINK_DAYS = 7

def check_link(url):
    """(ok, detail) for a resource link: one polite request, any https host except the blocked ones. Nothing is kept
    but the result (data/cache/links.json, a week)."""
    h = host_of(url)
    if not h or urlparse(url).scheme != "https": return False, "only https links"
    if is_blocked(h): return False, "LinkedIn and Naukri are never fetched: use another resource"
    if os.environ.get("FOUNDRY_FIXTURES"):
        idx = load(pathlib.Path(os.environ["FOUNDRY_FIXTURES"]) / "index.json", {}) or {}
        st = idx.get(f"LINK {url}")
        return (st == 200, f"HTTP {st}") if st is not None else (False, "no recorded response")
    cache = CACHE / "links.json"
    seen = load(cache, {}) or {}
    c = seen.get(url)
    if c and time.time() - c["t"] < LINK_DAYS * 86400: return c["ok"], c["detail"]
    _polite(h)
    ok, detail = False, ""
    for method in ("HEAD", "GET"):   # some sites refuse HEAD
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.8"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                final = r.geturl()
                ok = not is_blocked(host_of(final))
                detail = f"HTTP {r.status}" + (f", ends at {host_of(final)}" if host_of(final) != h else "") + ("" if ok else ": redirects to a blocked site")
            break
        except urllib.error.HTTPError as e:
            detail = f"HTTP {e.code}"
            if e.code not in (403, 405, 501) or method == "GET": break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            detail = f"couldn't reach {h} ({getattr(e, 'reason', type(e).__name__)})"; break
    seen[url] = {"t": time.time(), "ok": ok, "detail": detail}
    save(cache, seen)
    return ok, detail

def page_text(url):
    from html_text import to_text
    return to_text(get(url, robots=True))

def main(a):
    if len(a) >= 2 and a[0] == "allowed":
        ok, why = allowed(a[1]); print(("allowed: " if ok else "refused: ") + why); return 0 if ok else 1
    if len(a) >= 2 and a[0] == "link":
        ok, why = check_link(a[1]); print(("ok: " if ok else "DEAD: ") + why); return 0 if ok else 1
    if len(a) >= 2 and a[0] == "text":
        try: t = page_text(a[1])
        except FetchError as e: print(f"COULDN'T FETCH: {e}"); return 2
        if "--out" in a:
            o = pathlib.Path(a[a.index("--out") + 1]); o.parent.mkdir(parents=True, exist_ok=True)
            o.write_text(t, encoding="utf-8", newline="\n"); print(f"{len(t)} characters -> {rel(o)}")
        else: print(t)
        return 0
    print(__doc__); return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
