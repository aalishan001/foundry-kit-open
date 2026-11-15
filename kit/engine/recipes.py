#!/usr/bin/env python3
"""Job-alert recipes, so new postings come to their inbox instead of their browsing for them.
  recipes.py [--json]
Writes two files in their folder, built from the pack and their profile:
  "Job alerts setup.html"     step by step, with clickable links: saved searches and daily alerts on LinkedIn, Naukri,
                              Indeed, foundit and iimjobs (their families' search terms, their places in order, the
                              experience band for their level); the alert sign-up for every paste-in company that has
                              one; and the Gmail filter that files all of them under "Job Alerts"
  "Gmail filter (import me).xml"   that filter, for Gmail → Settings → Filters → Import filters
Nothing is fetched to build it, and nothing logs in anywhere: they set each alert up themselves, signed in as usual.
"""
import html, json, sys
from urllib.parse import quote, urlencode
from _common import HOME, search_rules, pack, die
from fit import level_of, GEO

LABEL = "Job Alerts"
OUT_HTML, OUT_XML = HOME / "Job alerts setup.html", HOME / "Gmail filter (import me).xml"
TERMS_PER_FAMILY = 2
# Senders of job alerts (the boards, and the portals companies use for their own alerts)
SENDERS = ["jobalerts-noreply@linkedin.com", "jobs-noreply@linkedin.com", "naukri.com", "indeed.com", "indeedemail.com",
           "foundit.in", "iimjobs.com", "successfactors.com", "sapsf.com", "darwinbox.in", "oraclecloud.com",
           "myworkday.com", "myworkdayjobs.com", "smartrecruiters.com", "greenhouse.io", "lever.co"]
SUBJECT_WORDS = ['"job alert"', '"jobs for you"', '"new jobs"', '"jobs matching"', '"recommended jobs"']

def terms(rules):
    """Area phrases for their target families (titles without a level word): the level comes from the experience filter."""
    fams = {f["id"]: f for f in pack().get("roles", {}).get("families", [])}
    out = []
    for fid in rules.get("target_families") or []:
        f = fams.get(fid) or {}
        picked = [t for t in f.get("titles", []) if level_of(t)[0] is None][:TERMS_PER_FAMILY]
        out += [t for t in picked if t not in out]
    out += [t for t in rules.get("target_titles") or [] if t not in out]
    return out

def years_band(rules):
    rank = (rules.get("current") or {}).get("ladder_rank")
    lv = next((l for l in pack().get("levels", []) if l["rank"] == rank), None)
    return tuple(lv["years_hint"]) if lv and lv.get("years_hint") else None

def home_places(rules):
    """Their preferred cities at home (the ones the kit recognises), then the whole country."""
    L = rules.get("locations") or {}
    cities = GEO.get("india", {}).get("cities", {})
    picked = [p for p in L.get("preferred") or [] if p.lower() in {c.lower() for c in cities}]
    return picked + ["India"]

def abroad_places(rules):
    names = GEO.get("countries", {})
    out = []
    for a in (rules.get("locations") or {}).get("abroad") or []:
        cc = str(a.get("country", "")).upper()
        country = names.get(cc, [cc])[0]
        for city in a.get("cities") or [None]:
            out.append({"country": cc, "place": f"{city}, {country}" if city else country})
    return out

def boolean_or(ts): return " OR ".join(f'"{t}"' for t in ts)

def linkedin(ts, place, band):
    # f_TPR=r86400: posted in the last 24 hours; f_E 4 = mid-senior, 5 = director
    exp = "4,5" if band and band[0] >= 8 else "4"
    return "https://www.linkedin.com/jobs/search/?" + urlencode({"keywords": boolean_or(ts), "location": place, "f_TPR": "r86400", "f_E": exp})

def naukri(ts, place, band):
    k = ", ".join(ts)
    q = {"k": k, "l": place if place != "India" else "", "experience": band[0] if band else ""}
    return f"https://www.naukri.com/{quote(ts[0].replace(' ', '-').replace('&', 'and'))}-jobs?" + urlencode({k2: v for k2, v in q.items() if v != ""})

def indeed(ts, place, domain="in.indeed.com"):
    return f"https://{domain}/jobs?" + urlencode({"q": " or ".join(f'"{t}"' for t in ts), "l": "" if place == "India" else place, "fromage": 1})

def foundit(ts, place, band):
    q = {"query": ", ".join(ts), "locations": "" if place == "India" else place}
    if band: q["experienceRanges"] = f"{band[0]}~{band[1]}"
    return "https://www.foundit.in/srp/results?" + urlencode({k: v for k, v in q.items() if v})

def iimjobs(term): return f"https://www.iimjobs.com/search/{quote(term.replace('&', 'and').replace(' ', '-'))}-jobs"

INDEED_DOMAINS = {"AE": "ae.indeed.com", "SA": "sa.indeed.com", "QA": "qa.indeed.com", "OM": "om.indeed.com", "KW": "kw.indeed.com",
                  "BH": "bh.indeed.com", "SG": "sg.indeed.com", "MY": "malaysia.indeed.com", "AU": "au.indeed.com", "GB": "uk.indeed.com",
                  "DE": "de.indeed.com", "NL": "nl.indeed.com", "US": "www.indeed.com", "CA": "ca.indeed.com"}

def plan(rules=None):
    s = rules or search_rules()
    ts, band = terms(s), years_band(s)
    if not ts: die("no target role families in their search rules yet: finish /start first")
    home, abroad = home_places(s), abroad_places(s)
    rows = []
    for p in home:
        rows.append({"board": "LinkedIn", "place": p, "url": linkedin(ts, p, band)})
        rows.append({"board": "Naukri", "place": p, "url": naukri(ts, p, band)})
        rows.append({"board": "Indeed", "place": p, "url": indeed(ts, p)})
        rows.append({"board": "foundit", "place": p, "url": foundit(ts, p, band)})
    for t in ts[:3]: rows.append({"board": "iimjobs", "place": "India", "term": t, "url": iimjobs(t)})
    for a in abroad:
        rows.append({"board": "LinkedIn", "place": a["place"], "url": linkedin(ts, a["place"], band)})
        if a["country"] in INDEED_DOMAINS: rows.append({"board": "Indeed", "place": a["place"], "url": indeed(ts, a["place"].split(",")[0], INDEED_DOMAINS[a["country"]])})
    from radar import load_radar
    companies = []
    for c in load_radar().get("companies", []):
        al = c.get("alert") or {}
        if c["portal"].get("tier") == 3 or al.get("url"):
            companies.append({"company": c["company"], "url": al.get("url"), "note": al.get("note") or ("" if al.get("url") else "no alert sign-up found: the 14-day paste-in reminder covers it"),
                              "careers": c["careers_url"]})
    return {"terms": ts, "years": band, "home": home, "abroad": [a["place"] for a in abroad], "alerts": rows, "companies": companies,
            "gmail": gmail_filter()}

def gmail_filter():
    try:
        import alerts
        own = sorted({x for v in alerts.senders().values() for x in v})
    except SystemExit: own = []
    from_q = " OR ".join(SENDERS + [x for x in own if x not in SENDERS])
    return {"from": from_q, "words": "subject:(" + " OR ".join(SUBJECT_WORDS) + ")", "label": LABEL,
            "search": f"from:({from_q}) OR subject:(" + " OR ".join(SUBJECT_WORDS) + ")"}

STEPS = {
    "LinkedIn": "Open the link (signed in as usual). Check the results look right, then switch on <b>Set alert</b> above the list. In the alert settings choose <b>Daily</b> and <b>Email</b>.",
    "Naukri": "Open the link (signed in). Check the results, then click <b>Create job alert</b> (or <b>Save search</b>). Choose a daily email.",
    "Indeed": "Open the link. Under the search box, click <b>Get new jobs for this search by email</b> and confirm your address.",
    "foundit": "Open the link (signed in). Click <b>Create Job Alert</b> on the results page and choose daily.",
    "iimjobs": "Open the link (signed in). Click <b>Create Job Alert</b> / <b>Save Search</b> and choose daily.",
}

def xml(f):
    a = lambda s: html.escape(s, quote=True)
    entry = lambda props: ("<entry><category term='filter'></category><title>Mail Filter</title><content></content>"
                           + "".join(f"<apps:property name='{k}' value='{a(v)}'/>" for k, v in props) + "</entry>")
    common = [("label", f["label"]), ("shouldNeverSpam", "true")]
    return ("<?xml version='1.0' encoding='UTF-8'?><feed xmlns='http://www.w3.org/2005/Atom' xmlns:apps='http://schemas.google.com/apps/2006'>"
            "<title>Mail Filters</title>" + entry([("from", f["from"])] + common) + entry([("hasTheWord", f["words"])] + common) + "</feed>\n")

def page(p):
    e = html.escape
    yrs = f"{p['years'][0]}–{p['years'][1]} years" if p["years"] else "their level"
    out = ["<!doctype html><meta charset='utf-8'><title>Job alerts setup</title>",
           "<style>body{font:16px/1.5 Arial,sans-serif;max-width:860px;margin:24px auto;padding:0 16px;color:#111}"
           "h1{font-size:24px}h2{font-size:19px;margin-top:28px}td,th{border-bottom:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}"
           "table{border-collapse:collapse;width:100%}code{background:#f3f3f3;padding:2px 4px;word-break:break-all}.tick{width:24px}</style>",
           "<h1>Job alerts setup</h1>",
           "<p>Do this once. After that, new postings arrive by email, the Gmail filter puts them under the <b>Job Alerts</b> label, "
           "and the kit reads that label every morning. You never log in anywhere through the kit: you set each alert up yourself, signed in as usual.</p>",
           f"<p>Search terms: <b>{e(', '.join(p['terms']))}</b>. Experience: <b>{yrs}</b>, posted in the last day. "
           f"Places, in your order: <b>{e(', '.join(p['home'] + p['abroad']))}</b>.</p>",
           "<h2>1. Gmail filter (first, so the alerts land in one place)</h2>",
           "<ol><li>Open Gmail on a computer → the gear icon → <b>See all settings</b> → <b>Filters and Blocked Addresses</b>.</li>",
           "<li>Click <b>Import filters</b> → <b>Choose file</b> → pick <b>Gmail filter (import me).xml</b> from this folder → <b>Open file</b>.</li>",
           "<li>Tick both filters, tick <b>Apply new filters to existing email</b>, then <b>Create filters</b>. The <b>Job Alerts</b> label is created for you.</li></ol>",
           f"<p>If importing doesn't work: in the Gmail search box paste the search below, click the filter icon, <b>Create filter</b>, tick "
           f"<b>Apply the label: Job Alerts</b> (new label) and <b>Never send it to Spam</b>.</p><p><code>{e(p['gmail']['search'])}</code></p>",
           "<h2>2. Job-board alerts</h2><table><tr><th class=tick>✓</th><th>Board</th><th>Place</th><th>Open, then turn the alert on</th></tr>"]
    for r in p["alerts"]:
        label = f"{r['board']}" + (f" ({e(r['term'])})" if r.get("term") else "")
        out.append(f"<tr><td class=tick>☐</td><td>{label}</td><td>{e(r['place'])}</td><td><a href='{e(r['url'])}'>open the search</a><br>{STEPS[r['board']]}</td></tr>")
    out.append("</table>")
    with_url = [c for c in p["companies"] if c["url"]]
    out.append("<h2>3. Company alerts (the companies whose sites can't be read automatically)</h2>")
    if with_url:
        out.append("<table><tr><th class=tick>✓</th><th>Company</th><th>Sign up</th></tr>")
        for c in with_url: out.append(f"<tr><td class=tick>☐</td><td>{e(c['company'])}</td><td><a href='{e(c['url'])}'>alert sign-up</a> {e(c['note'])}</td></tr>")
        out.append("</table>")
    rest = [c for c in p["companies"] if not c["url"]]
    if rest: out.append("<p>No alert sign-up for: " + e(", ".join(c["company"] for c in rest)) + ". /radar reminds you to look at these every 14 days.</p>")
    out.append("<h2>4. Then</h2><p>Tell Claude “done”. If you want the kit to read the Job Alerts label every morning, double-click "
               "<b>Gmail setup.cmd</b> in this folder (it needs 2-Step Verification on your Google account). Otherwise paste alert emails into /sweep.</p>")
    return "\n".join(out) + "\n"

def main(a):
    if a and a[0] in ("-h", "--help"): print(__doc__); return 0
    p = plan()
    if "--json" in a: print(json.dumps(p, indent=1, ensure_ascii=False)); return 0
    OUT_HTML.write_text(page(p), encoding="utf-8", newline="\n")
    OUT_XML.write_text(xml(p["gmail"]), encoding="utf-8", newline="\n")
    n = len([c for c in p["companies"] if c["url"]])
    print(f"wrote '{OUT_HTML.name}' ({len(p['alerts'])} board alerts, {n} company alert sign-ups) and '{OUT_XML.name}' (the Job Alerts filter)")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
