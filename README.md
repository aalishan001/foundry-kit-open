# foundry-kit

A job-search workspace that runs in an AI coding app on your own Windows computer. You keep one folder of plain files;
eleven slash commands find roles, check fit against your own rules, tailor a resume (PDF and Word) for each job,
log applications, and prepare you for interviews.

It never invents anything about you. Every line it writes for you cites a fact you confirmed, and two independent
checks refuse anything that doesn't trace back.

- **Works with:** Claude Code (the Claude desktop app's Code tab, Claude Pro or higher), or **OpenCode** with an
  **OpenRouter** key (about $1 a week, measured).
- **Fields:** software engineering out of the box (levels, role families, a starter list of companies, interview
  questions); any other field through the general pack and your own target titles.
- **Private by design:** your files stay in your folder. With OpenCode, only paid, zero-data-retention, no-training
  model endpoints are used; free models never are.

## What it does

| Command | What it does |
|---|---|
| `/start` | interview that builds your facts bank, search rules and resume format; resumable |
| `/radar` | the companies you follow, how each careers site is read; `/radar recipes` sets up job alerts once |
| `/sweep` | ranks the new roles the morning sweep found (careers sites, your Gmail Job Alerts label, job-search APIs) |
| `/check` | deep fit check: level, pay rule, place, company stability, match, odds, gaps |
| `/tailor` | a resume (PDF, Word or both) and application notes for one job, every line traced to a fact |
| `/applied`, `/update` | log applications and what happened next |
| `/grill` | a timed mock interview, scored, no do-overs |
| `/prep` | prep for a job's gaps: a primer, likely questions with honest answers, a quiz, checked free resources |
| `/today`, `/help` | what needs you today; the cheat sheet |

A scheduled task reads careers sites and alerts every morning without any AI, so `/sweep` only ranks what's waiting.

## Your rules, enforced by code

- Never a role below your current level.
- A same-level move only when the pay rise clears your threshold (20% unless you choose another).
- Your home country first; abroad only in the countries you list, in your order, and only at an established company.
- Preferred places are a bonus, never a filter.
- LinkedIn and Naukri are never fetched or logged into: you set up their alerts yourself, and paste a posting if needed.

## Get started

1. **Download** this repository (Code → Download ZIP, or `git clone`). The part you use is the `kit` folder.
2. **Copy `kit`** into a folder in OneDrive or Google Drive, for example `OneDrive\Job Search`.
3. **Choose your app:**
   - **Claude Code:** the Claude desktop app with a Pro (or higher) plan.
   - **OpenCode + OpenRouter:** create an OpenRouter account and add credit. Then, in Settings → Privacy, **switch off
     every option that allows providers which may train on your data, and switch on Zero Data Retention for every
     model group.** These are not optional. Create an API key with a credit limit.
4. **Double-click `setup.cmd`** in your folder. It installs Python, Git, OpenCode and four small packages for your user
   only, asks whether to run the morning sweep, and stores your OpenRouter key in Windows Credential Manager (never in
   a file).
5. **Write your master resume** (below) and drop it in the folder's `inbox`.
6. **Open the folder** (the "Job search (OpenCode)" desktop shortcut, or the Claude Code tab) and type **`/start`**.

The full guide is [`kit/docs/SETUP.md`](kit/docs/SETUP.md); the cheat sheet is
[`kit/docs/COMMANDS.md`](kit/docs/COMMANDS.md).

## Your master resume: write everything down once

Before `/start`, put **one long master resume or career brain dump** in `inbox`. **No page limit**: ten pages beats
one. Rough notes are fine.

Because the kit refuses to invent claims, it can only use what you give it. A trimmed one-page resume has already
thrown away the details that win the next job. With everything written down once, `/tailor` and `/prep` pick the
right verified facts for each role.

Put in, for every job (and internships, freelance work, research, projects):

- company, exact titles, start and end months, city, promotions;
- what the team and product did, and who used it;
- every project: what it was, your part (built, led, owned, helped), and the outcome;
- numbers, even rough: users, requests per second, latency before and after, data volume, money saved, cost cut, time
  saved, error rates, team size;
- architecture and design decisions you made: the options, your choice, why, and what happened;
- production incidents you handled: what broke, how you found it, how long it took, what changed after;
- your tech stack and tools, and how deep you went with each; internal tools, scripts and dashboards you built;
- people you managed, mentored, hired or interviewed;
- open-source pull requests and repos (with links), side projects, hackathons, talks, posts, papers, patents;
- certifications and courses (with years), education, awards, review highlights, links (GitHub, LinkedIn,
  portfolio), and any rough notes you're proud of.

More detail and the reasons: [`kit/docs/MASTER_RESUME.md`](kit/docs/MASTER_RESUME.md).

## How `/start` works

One question at a time, resumable any time:

1. **Field:** software engineering, or any other field plus the job titles you're after.
2. **Documents:** it reads `inbox` and drafts short facts; you confirm, edit or delete each one.
3. **Gaps:** questions for what resumes leave out (scale, numbers, decisions, incidents). "I don't know" is fine.
4. **Identity:** name, contacts, city.
5. **Search rules:** current level and pay, your pay-rise threshold for same-level moves, target roles, preferred
   cities, places to avoid, countries abroad in order, company stability abroad, pay over place, notice period.
6. **Resume format:** PDF, Word or both, page limit, contacts.
7. **Gmail (optional):** paste alerts, or let the kit read one Gmail label read-only (needs 2-Step Verification).

## What it costs with OpenCode

Measured on real runs, zero-data-retention endpoints only (Claude Haiku 5.5 for most commands, Claude Sonnet 5.5 for
`/tailor` and `/prep`):

| | About |
|---|---|
| `/start` (once) | $0.19 with a short resume; more with a long master resume |
| `/today`, `/radar`, `/update`, `/check`, `/grill` | $0.01–$0.03 each |
| `/sweep`, `/applied` | $0.03–$0.05 |
| `/prep` | $0.34 |
| `/tailor` (one pass) | $0.41 |
| A typical week | about $1.04, so $10 lasts about 9 weeks |

## Privacy

- Everything lives in your folder (OneDrive or Drive backs it up); a local git history keeps every change.
- Keys and app passwords live in Windows Credential Manager, never in files.
- OpenCode is configured to use OpenRouter only, and every request asks for zero-data-retention, no-training providers.
  Web search and web fetch are off in OpenCode; careers pages are read by the kit's own fetcher, which never touches
  LinkedIn or Naukri.
- Gmail access, if you turn it on, reads one label, read-only, and never marks, moves or deletes mail.

## Repository layout

| Path | What it is |
|---|---|
| `kit/` | everything a user installs: the engine (Python), commands for Claude Code and OpenCode, packs, templates, docs |
| `kit/packs/` | field knowledge: `software-eng`, `general` (and how to write your own: `kit/packs/README.md`) |
| `scripts/` | maintainer tools: leak scan, release build, the OpenCode generator and cost measurement |
| `tests/` | the test suite: `python -m unittest discover -s tests` |

See [`DEVELOPING.md`](DEVELOPING.md) to work on the kit.

## Licence

MIT: see [`LICENSE`](LICENSE).
