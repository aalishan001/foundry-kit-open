---
description: Log an application they sent. Job, date, channel, and the exact resume version they sent.
argument-hint: "<job id or company + role> [date] [channel] [referrer]"
model: sonnet
---

1. `python engine/doctor.py --quick`.

2. **Work out from `$ARGUMENTS`** (ask only for what's missing):
   - **Job:** a job id, or the company and role. If the job isn't tracked yet, it needs its JD: run the /check
     gathering step, or pass `--jd-file`.
   - **Date:** YYYY-MM-DD; today if they say "today".
   - **Channel:** careers_site, referral (with the referrer's name), recruiter, email, job_board or other.
   - **Resume they sent:** a tailored version (`<job id>/v<N>`), or the exact file they dropped in `inbox/`.
   - **Notes:** anything else they say.

3. If you had to interpret anything (the channel, the date, which version), do a dry run first:
   `python engine/jobs.py applied @data/tmp/a.json --tailored <id>/v<N> --dry-run`, or `--resume inbox/<file>`.
   Show them the row and get their yes.

4. Then run it for real, without `--dry-run`. Show the saved row: application id, company and role, date, channel,
   which resume. Say that the job moved to applied.

5. Run `python engine/backup.py commit "applied: <a-id>"`.
