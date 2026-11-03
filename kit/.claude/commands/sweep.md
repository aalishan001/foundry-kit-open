---
description: New openings, ranked. The morning sweep already read the careers sites, the Job Alerts label and the job-search APIs; this ranks what's waiting (and runs the sweep first if the morning one didn't happen).
argument-hint: "[now]"
model: haiku
effort: low
---

1. `python engine/doctor.py --quick`.
2. **Fetch, only if needed:** `python engine/sweep_daily.py --if-older 20` (or plain `python engine/sweep_daily.py` if
   `$ARGUMENTS` says "now"). If the morning run happened, it says so and fetches nothing. If it runs, say "Reading
   the careers sites; this takes a few minutes" first.
3. **Pasted alerts (only if Gmail is off):** read `profile/search.json` → `gmail.enabled`. If false, ask once: "Any
   job-alert emails to paste? (Paste them, or say no.)" Save each to `data/tmp/alert-<n>.txt` and run
   `python engine/sweep.py alerts data/tmp/alert-<n>.txt`. Also pick up any `.eml` or `.txt` files in `inbox/`, then
   move them with `python engine/extract.py archive inbox/<file>`. Never open LinkedIn or Naukri links: they are
   stored for reference only.
4. **Rank what's waiting:** `python engine/jobs.py waiting`. For each job, read its title, its JD if saved (else the
   snippet), and rate it **high**, **medium** or **low** against their target families, with one line. Base the rating
   only on the posting and their rules, not on guesses about the company. Record each with
   `python engine/jobs.py triage <id> <rating> "<one line>"`.
5. **Show:**
   - a table of the jobs just ranked: id, company, role, place, rating, one line (high first);
   - then `python engine/sweep_daily.py report`: the paste-in companies due (each with its link), the sources that
     couldn't be read (one line each), and how many the rules dropped. Show `python engine/sweep.py dropped` only if
     they ask.
6. Run `python engine/backup.py commit "sweep: <n> ranked"`. End with "Check which? (numbers)". Their answer goes to
   `/check`.
