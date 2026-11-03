---
description: The company radar. What's due for a check, add or drop companies, and how each portal is read.
argument-hint: "[add <company> <careers URL> [every N days] | drop <company> <reason> | every <company> <N> | new | refresh | recipes]"
model: sonnet
---

`python engine/doctor.py --quick` first. If `data/radar.json` doesn't exist, run `python engine/radar.py seed` and
say how many companies came from the pack.

What they asked (`$ARGUMENTS`), mapped to the engine:

- **nothing**: run `python engine/radar.py`. Show a table of the companies due, with columns company, last check,
  stability and how it's read: "automatic" for tier 1, "paste-in: open the link" for tier 3, with the link. List the
  later ones briefly. End with "Run /sweep to read the automatic ones."
- **add**: run `python engine/radar.py add "<company>" <url> [--every N] [--segment S]`. It detects the portal and
  refuses LinkedIn and Naukri links; if so, find the company's own careers page with a web search and ask them to
  confirm it. Report the portal type and whether it's automatic or paste-in. Then look up who owns the company and
  record it: `radar.py stability "<company>" <type> --source <https page> --basis "<one line>"` (types:
  government-owned, listed, multinational subsidiary, large group, PE-backed, startup; the first that fits). If you
  can't establish it, say so and leave it unknown.
- **drop**: run `python engine/radar.py drop "<company>" --note "<their reason>"`.
- **every**: run `python engine/radar.py every "<company>" <N>`.
- **new**: run `python engine/radar.py pack-new`. They watch the whole list, so the default is all of them: ask
  "Add all of these? (or name the ones to skip)". All: `radar.py pack-new --add-all`. Some: add each with
  `radar.py add "<company>" <careers_url> --segment <segment>`.
- **refresh**: run `python engine/radar.py refresh` (after a kit update: new stability facts, alert links, portal
  fixes). Their checks and intervals stay as they are.
- **recipes**: run `python engine/recipes.py`. Tell them **Job alerts setup.html** is in their folder (double-click it:
  it opens in the browser with clickable links), with the alerts to set up on LinkedIn, Naukri, Indeed, foundit and
  iimjobs, the company alert sign-ups, and the Gmail filter file to import first. Walk them through the first one if
  they want. They set each alert up themselves, signed in as usual; never open LinkedIn or Naukri for them.

After any change, run `python engine/backup.py commit "radar: <summary>"`.
