"""Tier-1 adapters: read a radar company's openings from its portal. Each returns a list of postings:
{company, title, location, remote, url, posted, jd_text (or None: fetched later only for postings that pass the
prefilter), ref}. All network access goes through fetch.get (allowlist, rate limit, cache, robots.txt).
"""
import datetime as dt, json, re
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode, urlunparse
from fetch import get, FetchError, org_domain, host_of
from html_text import to_text, links_with_context, unescape
from _common import today

WORKDAY_PAGE, WORKDAY_MAX_PAGES = 20, 5
SR_PAGE, SR_MAX_PAGES = 100, 3
STATIC_MAX_PAGES = 10

class Unreadable(Exception):
    """The page loaded but holds no openings we can read without a browser."""

def posting(c, **kw):
    p = {"company": c["company"], "title": "", "location": "", "remote": False, "url": None, "posted": None, "jd_text": None, "ref": None}
    p.update({k: v for k, v in kw.items() if v is not None})
    p["title"] = re.sub(r"\s+", " ", p["title"]).strip()
    if p["url"] and p["url"].startswith("http://"): p["url"] = "https://" + p["url"][7:]
    return p

def _date(s):
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(s or ""))
    return m.group(1) if m else None

# ---------------------------------------------------------------- Greenhouse
def greenhouse(c):
    tok = c["portal"]["token"]
    d = get(f"https://boards-api.greenhouse.io/v1/boards/{tok}/jobs?content=true", as_json=True)
    return [posting(c, title=j.get("title", ""), location=(j.get("location") or {}).get("name", ""), url=j.get("absolute_url"),
                    posted=_date(j.get("updated_at") or j.get("first_published")), jd_text=to_text(unescape(j.get("content", ""))) or None,
                    ref=str(j.get("id"))) for j in d.get("jobs", [])]

# ---------------------------------------------------------------- Lever
def lever(c):
    tok, base = c["portal"]["token"], "api.eu.lever.co" if c["portal"].get("region") == "eu" else "api.lever.co"
    rows = get(f"https://{base}/v0/postings/{tok}?mode=json", as_json=True)
    out = []
    for j in rows if isinstance(rows, list) else []:
        parts = [j.get("descriptionPlain") or to_text(j.get("description", ""))]
        for l in j.get("lists") or []: parts.append(f"{l.get('text', '')}\n{to_text(l.get('content', ''))}")
        parts.append(j.get("additionalPlain") or to_text(j.get("additional", "")))
        posted = dt.datetime.fromtimestamp(j["createdAt"] / 1000).date().isoformat() if j.get("createdAt") else None
        cat = j.get("categories") or {}
        out.append(posting(c, title=j.get("text", ""), location=cat.get("location") or ", ".join(cat.get("allLocations") or []),
                           remote=(j.get("workplaceType") == "remote"), url=j.get("hostedUrl"), posted=posted,
                           jd_text="\n\n".join(p for p in parts if p).strip() or None, ref=j.get("id")))
    return out

# ---------------------------------------------------------------- SmartRecruiters
def smartrecruiters(c):
    tok, out = c["portal"]["token"], []
    for page in range(SR_MAX_PAGES):
        d = get(f"https://api.smartrecruiters.com/v1/companies/{tok}/postings?limit={SR_PAGE}&offset={page * SR_PAGE}", as_json=True)
        for j in d.get("content", []):
            loc = j.get("location") or {}
            out.append(posting(c, title=j.get("name", ""), location=", ".join(x for x in (loc.get("city"), loc.get("region"), loc.get("country", "").upper()) if x),
                               remote=bool(loc.get("remote")), url=f"https://jobs.smartrecruiters.com/{tok}/{j.get('id')}",
                               posted=_date(j.get("releasedDate")), ref=j.get("ref") or f"https://api.smartrecruiters.com/v1/companies/{tok}/postings/{j.get('id')}"))
        if (page + 1) * SR_PAGE >= d.get("totalFound", 0): break
    return out

def smartrecruiters_jd(c, p):
    d = get(p["ref"], as_json=True)
    secs = ((d.get("jobAd") or {}).get("sections") or {})
    return "\n\n".join(f"{s.get('title', '')}\n{to_text(s.get('text', ''))}".strip() for s in secs.values() if isinstance(s, dict) and s.get("text"))

# ---------------------------------------------------------------- Ashby (public job-board API)
def ashby(c):
    tok = c["portal"]["token"]
    d = get(f"https://api.ashbyhq.com/posting-api/job-board/{tok}?includeCompensation=false", as_json=True)
    out = []
    for j in d.get("jobs", []):
        if j.get("isListed") is False: continue
        locs = [j.get("location") or ""] + [x.get("location", "") for x in j.get("secondaryLocations") or [] if isinstance(x, dict)]
        out.append(posting(c, title=j.get("title", ""), location="; ".join(l for l in locs if l),
                           remote=bool(j.get("isRemote")) or (j.get("workplaceType") or "").lower() == "remote", url=j.get("jobUrl"),
                           posted=_date(j.get("publishedAt")), jd_text=(j.get("descriptionPlain") or to_text(j.get("descriptionHtml") or "")) or None,
                           ref=j.get("id")))
    return out

# ---------------------------------------------------------------- Oracle HCM Candidate Experience (public REST, no login)
# portal: {type: oraclehcm, host, site, location_id?, search?, max_pages?}
ORACLE_PAGE, ORACLE_MAX_PAGES = 200, 3

def oraclehcm(c):
    from urllib.parse import quote
    p = c["portal"]; host, site = p["host"], p["site"]
    extra = (f",locationId={p['location_id']}" if p.get("location_id") else "") + (f",keyword=%22{quote(p['search'])}%22" if p.get("search") else "")
    out = []
    for page in range(p.get("max_pages", ORACLE_MAX_PAGES)):
        d = get(f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList"
                f"&finder=findReqs;siteNumber={site}{extra},limit={ORACLE_PAGE},offset={page * ORACLE_PAGE},sortBy=POSTING_DATES_DESC", as_json=True)
        it = (d.get("items") or [{}])[0]
        rows = it.get("requisitionList") or []
        for j in rows:
            out.append(posting(c, title=j.get("Title", ""), location=j.get("PrimaryLocation", ""), posted=_date(j.get("PostedDate")),
                               url=f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{j.get('Id')}", ref=str(j.get("Id")),
                               remote="remote" in (j.get("WorkplaceType") or "").lower()))
        if len(rows) < ORACLE_PAGE or (page + 1) * ORACLE_PAGE >= (it.get("TotalJobsCount") or 0): break
    return out

def oraclehcm_jd(c, p):
    pt = c["portal"]
    d = get(f"https://{pt['host']}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?expand=all&onlyData=true"
            f"&finder=ById;Id=%22{p['ref']}%22,siteNumber={pt['site']}", as_json=True)
    it = (d.get("items") or [{}])[0]
    parts = [it.get(k) for k in ("ExternalDescriptionStr", "ExternalResponsibilitiesStr", "ExternalQualificationsStr", "CorporateDescriptionStr")]
    return "\n\n".join(to_text(unescape(x)) for x in parts if x).strip() or None

# ---------------------------------------------------------------- company job APIs (a company's own careers site JSON)
# Undocumented public endpoints: each is read with robots.txt checked, and may change without notice. A failure turns
# the company to paste-in for that sweep, like an unreadable static page.

# amazon.jobs search.json. portal: {type: amazon, loc_query, country, city?, categories?: [...], search?, max_pages?}
AMAZON_PAGE, AMAZON_MAX_PAGES = 100, 5

def amazon(c):
    from urllib.parse import urlencode
    p, out = c["portal"], []
    for page in range(p.get("max_pages", AMAZON_MAX_PAGES)):
        q = [("base_query", p.get("search", "")), ("loc_query", p.get("loc_query", "")), ("country", p.get("country", "")),
             ("city", p.get("city", "")), ("sort", "recent"), ("result_limit", AMAZON_PAGE), ("offset", page * AMAZON_PAGE)]
        q += [("category[]", x) for x in p.get("categories", [])]
        try: d = get("https://www.amazon.jobs/en/search.json?" + urlencode(q), as_json=True, robots=True)
        except FetchError as e: raise Unreadable(f"the amazon.jobs API didn't answer ({e})")
        rows = d.get("jobs") or []
        for j in rows:
            try: posted = dt.datetime.strptime(re.sub(r"\s+", " ", j.get("posted_date", "")), "%B %d, %Y").date().isoformat()
            except ValueError: posted = None
            text = "\n\n".join(f"{h}\n{to_text(j.get(k) or '')}" for h, k in (("Description", "description"),
                     ("Basic qualifications", "basic_qualifications"), ("Preferred qualifications", "preferred_qualifications")) if j.get(k))
            out.append(posting(c, title=j.get("title", ""), location=j.get("normalized_location") or j.get("location", ""),
                               url="https://www.amazon.jobs" + (j.get("job_path") or ""), posted=posted, ref=j.get("id_icims"), jd_text=text or None))
        if len(rows) < AMAZON_PAGE or (page + 1) * AMAZON_PAGE >= (d.get("hits") or 0): break
    return out

# Eightfold PCS careers sites (/api/pcsx). portal: {type: eightfold, host, domain, search?, location?, max_pages?}
EIGHTFOLD_MAX_PAGES, EIGHTFOLD_BACKOFF = 10, 40

def _eightfold_get(url, tries=3):
    """Eightfold answers 429 to quick bursts: back off and try again."""
    import time
    for i in range(tries):
        try: return get(url, as_json=True, robots=True)
        except FetchError as e:
            if "429" not in str(e) or i == tries - 1: raise
            time.sleep(EIGHTFOLD_BACKOFF)

def eightfold(c):
    from urllib.parse import urlencode
    p, out, start = c["portal"], [], 0
    for _ in range(p.get("max_pages", EIGHTFOLD_MAX_PAGES)):
        q = urlencode({"domain": p["domain"], "query": p.get("search", ""), "location": p.get("location", ""), "start": start, "sort_by": "timestamp"})
        try: d = (_eightfold_get(f"https://{p['host']}/api/pcsx/search?{q}") or {}).get("data") or {}
        except FetchError as e:
            if out: break
            raise Unreadable(f"the careers API didn't answer ({e})")
        rows = d.get("positions") or []
        for j in rows:
            ts = j.get("postedTs")
            out.append(posting(c, title=j.get("name", ""), location="; ".join(j.get("locations") or []), ref=str(j.get("id")),
                               url=f"https://{p['host']}/careers/job/{j.get('id')}", remote=(j.get("workLocationOption") or "") == "remote",
                               posted=dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat() if ts else None))
        start += len(rows)
        if not rows or start >= (d.get("count") or 10**9): break
    return out

def eightfold_jd(c, p):
    pt = c["portal"]
    d = (_eightfold_get(f"https://{pt['host']}/api/pcsx/position_details?position_id={p['ref']}&domain={pt['domain']}&hl=en") or {}).get("data") or {}
    return to_text(unescape(d.get("jobDescription") or "")) or None

# ---------------------------------------------------------------- Workday (public jobs endpoint, no login)
def _workday_posted(text):
    t = (text or "").lower()
    if "today" in t: return today().isoformat()
    if "yesterday" in t: return (today() - dt.timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\+?\s*days?", t)
    return (today() - dt.timedelta(days=int(m.group(1)))).isoformat() if m else None

def workday(c):
    p = c["portal"]; host, tenant, site = p["host"], p["tenant"], p["site"]
    api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    out = []
    for page in range(p.get("max_pages", WORKDAY_MAX_PAGES)):   # a location facet reads the whole board, not a keyword's top 100
        body = {"appliedFacets": p.get("facets") or {}, "limit": WORKDAY_PAGE, "offset": page * WORKDAY_PAGE, "searchText": p.get("search", "")}
        d = get(api, method="POST", body=body, as_json=True)
        rows = d.get("jobPostings") or []
        for j in rows:
            path = j.get("externalPath") or ""
            out.append(posting(c, title=j.get("title", ""), location=j.get("locationsText", ""), url=f"https://{host}/{site}{path}",
                               posted=_workday_posted(j.get("postedOn")), ref=path,
                               remote="remote" in (j.get("remoteType") or j.get("locationsText") or "").lower()))
        if len(rows) < WORKDAY_PAGE: break
    return out

def workday_jd(c, p):
    pt = c["portal"]
    d = get(f"https://{pt['host']}/wday/cxs/{pt['tenant']}/{pt['site']}{p['ref']}", as_json=True)
    info = d.get("jobPostingInfo") or {}
    if info.get("location") and not p.get("location"): p["location"] = info["location"]
    return to_text(info.get("jobDescription", ""))

# ---------------------------------------------------------------- static careers pages
JOB_HREF = re.compile(r"(?i)(/jobs?/|/careers?/.+|/openings?/|/positions?/|/vacanc|/requisition|/job-details|/jobdetail|jobid=|job_id=|/apply/)")
CARD_NOISE = re.compile(r"(?i)(\byears?\b|\bexperience\b|full[- ]time|part[- ]time|^(contract|contractual|permanent|internship|onroll|offroll|on-roll|off-roll)$|^\d+$|\bposted\b|\bago$|openings?$|jobs? available)")
JOB_HOSTS = ("ashbyhq.com", "greenhouse.io", "lever.co", "smartrecruiters.com", "myworkdayjobs.com", "keka.com", "darwinbox.in", "zohorecruit.com",
             "zohorecruit.in", "turbohire.co", "workable.com", "bamboohr.com", "freshteam.com", "peoplestrong.com")

def card_title(before):
    """The job title in a card's text before a generic link: the nearest chunk that isn't a place, a tenure or a tag
    line. -> (title, location)."""
    from fit import place
    title, loc = "", ""
    for t in reversed(before):
        if CARD_NOISE.search(t) or len(t) > 120: continue
        if place(t)["country"]: loc = loc or t; continue
        if not title: title = t
    return title, loc

NOT_JOB = re.compile(r"(?i)^(apply( now)?|view( all)?( jobs| openings| details)?|see all|learn more|read more|careers?|jobs?|search|home|login|sign in|back|next|previous|\d+)$")

def jsonld_jobs(html):
    out = []
    for m in re.finditer(r'(?is)<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html):
        try: data = json.loads(m.group(1).strip())
        except json.JSONDecodeError: continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, list): stack.extend(x); continue
            if not isinstance(x, dict): continue
            t = x.get("@type"); t = t if isinstance(t, list) else [t]
            if "JobPosting" in t: out.append(x)
            stack.extend(v for k, v in x.items() if k in ("@graph", "itemListElement", "item", "mainEntity"))
    return out

def _ld_location(j):
    locs = j.get("jobLocation") or []
    locs = locs if isinstance(locs, list) else [locs]
    names = []
    for l in locs:
        a = (l or {}).get("address") or {}
        if isinstance(a, str): names.append(a); continue
        country = a.get("addressCountry"); country = country.get("name") if isinstance(country, dict) else country
        names.append(", ".join(x for x in (a.get("addressLocality"), a.get("addressRegion"), country) if x))
    return "; ".join(n for n in names if n)

def static_page(c, url, html):
    """The postings on one listing page."""
    found = jsonld_jobs(html)
    if found:
        return [posting(c, title=unescape(j.get("title", "")), location=_ld_location(j), url=urljoin(url, j.get("url") or "") if j.get("url") else url,
                        posted=_date(j.get("datePosted")), jd_text=to_text(unescape(j.get("description", ""))) or None,
                        remote=(j.get("jobLocationType") == "TELECOMMUTE")) for j in found]
    dom, seen, out = org_domain(host_of(url)), set(), []
    for href, text, before in links_with_context(html):
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")): continue
        full = urljoin(url, href)
        h = host_of(full)
        if not h or (org_domain(h) != dom and not h.endswith(JOB_HOSTS)): continue
        u = urlparse(full)
        if not (JOB_HREF.search(u.path) or (u.query and JOB_HREF.search("?" + u.query))) or full.rstrip("/") == url.rstrip("/"): continue
        t, loc = re.sub(r"\s+", " ", text).strip(), ""
        if NOT_JOB.match(t) or not t: t, loc = card_title(before)
        if not (4 <= len(t) <= 120) or NOT_JOB.match(t) or full in seen: continue
        seen.add(full); out.append(posting(c, title=t, url=full, location=loc))
    return out

# ---------------------------------------------------------------- static pagination
SHOWING = re.compile(r"(?i)showing\s+(\d+)\s*(?:-|to|–)\s*(\d+)\s+of\s+(\d+)")
NEXT_TEXT = re.compile(r"(?i)^(next( page)?|›|»|>|>>|older( posts)?|more (search )?results)$")

def _with_param(url, key, value):
    u = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if k != key] + [(key, str(value))]
    return urlunparse(u._replace(query=urlencode(q)))

def startrow_plan(url, html):
    """SuccessFactors-style "Showing 1 to 10 of 66": every later page's URL (startrow=10, 20 ...), up to the cap."""
    s = SHOWING.search(to_text(html)) if "howing" in html else None
    if not s: return []
    first, last, total = map(int, s.groups())
    size = last - first + 1
    if first != 1 or size < 1 or last >= total: return []
    return [_with_param(url, "startrow", k) for k in range(size, total, size)][:STATIC_MAX_PAGES - 1]

def next_page(url, html, page_no, visited):
    """The next listing page's URL, or None: rel=next, a "Next" link, then ?page=N or /page/N/ on the same path."""
    from html_text import links
    cands = []
    m = re.search(r'(?is)<(?:a|link)\b[^>]*\brel=["\']?next["\']?[^>]*\bhref=["\']([^"\']+)', html) or \
        re.search(r'(?is)<(?:a|link)\b[^>]*\bhref=["\']([^"\']+)["\'][^>]*\brel=["\']?next', html)
    if m: cands.append(urljoin(url, unescape(m.group(1))))
    rows = links(html)
    cands += [urljoin(url, h) for h, t in rows if h and not h.startswith(("#", "javascript:")) and NEXT_TEXT.match(t)]
    path, want = urlparse(url).path, page_no + 1
    for h, _ in rows:
        full = urljoin(url, h or ""); u = urlparse(full)
        if host_of(full) != host_of(url): continue
        if u.path == path and dict(parse_qsl(u.query)).get("page") == str(want): cands.append(full)
        elif re.search(rf"/page/{want}/?$", u.path): cands.append(full)
    return next((x for x in dict.fromkeys(cands) if x.rstrip("/") != url.rstrip("/") and x not in visited), None)

def static(c):
    first = c["portal"].get("jobs_url") or c["careers_url"]
    html = get(first, robots=True)
    out = static_page(c, first, html)
    if not out: raise Unreadable("no openings readable without a browser")
    seen, visited, plan, url = {p["url"] for p in out}, {first}, startrow_plan(first, html), first
    planned = bool(plan)
    for n in range(1, STATIC_MAX_PAGES):
        nxt = plan.pop(0) if plan else (None if planned else next_page(url, html, n, visited))
        if not nxt: break
        visited.add(nxt)
        try: html = get(nxt, robots=True)
        except FetchError: break   # page 1 is what counts; a failing later page ends the walk
        new = [p for p in static_page(c, nxt, html) if p["url"] not in seen]
        if not new: break
        seen |= {p["url"] for p in new}; out += new; url = nxt
    return out

def static_jd(c, p):
    from fetch import page_text
    return page_text(p["url"]) if p.get("url") else None

ADAPTERS = {"greenhouse": greenhouse, "lever": lever, "smartrecruiters": smartrecruiters, "ashby": ashby, "workday": workday, "static": static,
            "oraclehcm": oraclehcm, "amazon": amazon, "eightfold": eightfold}
JD = {"smartrecruiters": smartrecruiters_jd, "workday": workday_jd, "static": static_jd, "oraclehcm": oraclehcm_jd, "eightfold": eightfold_jd}

def openings(c):
    t = c["portal"]["type"]
    if t not in ADAPTERS: raise FetchError(f"{t} portals are paste-in (tier 3)")
    return ADAPTERS[t](c)

def jd_text(c, p):
    """The posting's full text, fetching it if the listing didn't include it."""
    if p.get("jd_text"): return p["jd_text"]
    fn = JD.get(c["portal"]["type"])
    return fn(c, p) if fn else None
