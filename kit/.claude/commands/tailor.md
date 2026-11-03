---
description: Tailored resume (PDF, DOCX or both) and application notes for one job. Every line traces to a confirmed fact.
argument-hint: "<job id>"
model: opus
---

Input: one job id (`$ARGUMENTS`). It needs a saved JD and a check. If it's missing either, run the /check steps for
it first.

1. `python engine/doctor.py --quick`. Read the job (`python engine/jobs.py show <id>`), its JD, their facts
   (`python engine/facts.py list --status confirmed`), `profile/employment.json`, `education.json`,
   `resume_prefs.json`, and the pack's `keywords.json`.

2. **Choose facts** that answer the JD's must-haves first, then its nice-to-haves. Lead with analytics evidence:
   numbers, scale and outcomes.

3. **Write** `data/tailored/<id>/v<N>/resume.json`. N is the next free version number.
   - Format (SPEC 4.6): sections Summary, Experience (roles by `employment_ref`), Skills (lines with items),
     Education (`"from": "education.json"`) and Certifications.
   - Every paragraph, bullet, skills line and certification lists its `facts`.
   - Wording rules:
     - Use the JD's keywords only where a cited fact supports them.
     - Don't inflate: "contributed to" stays as is, "about 15%" stays "about 15%".
     - Use active verbs.
   - No name or contacts in the file: the renderer adds them from their identity.
   - Keep it within their page limit.

4. **Notes:** write `data/tailored/<id>/v<N>/notes.md` with these sections:
   - `## Why I fit`: three points.
   - `## Gaps and how to address them`
   - `## Questions to ask`
   - `## Message draft`: a short note to the recruiter or hiring manager.
   - `## Pay`: the "ask for at least" figure from the check, when the role is lateral.

   In Why I fit and Message draft, every line with a number or a name ends with `<!-- facts: f-000N -->`.

5. **Deterministic claim check:** `python engine/claims.py <id>/v<N>`. Fix or drop every FAIL line and re-run until
   it passes.

6. **Skeptical check:** run the `claim-checker` subagent on `data/tailored/<id>/v<N>/`. Rewrite or drop anything it
   marks STRETCHED or UNSUPPORTED, then run claims.py again.

7. **ATS check:** run `python engine/ats.py keywords <id>/v<N>`. Report the keywords covered and missing. A missing
   keyword goes into the resume only if a confirmed fact supports it; otherwise it's a gap for the notes.

8. **Render:** `python engine/render.py <id>/v<N>`. It writes PDF and/or DOCX to `Resumes/<Company> - <Role>/`,
   checks that the two files hold the same words in the same order, and runs the ATS lint. Report the file paths
   and the page count.

9. **Show them:** the resume text section by section, the notes, the keyword coverage and the claim-check result.
   Ask what to change. Each round of changes is a new version (v<N+1>) and goes through steps 5–8 again.

10. When they say it's final, record the version in notes.md (`Final: v<N>`). Run
    `python engine/backup.py commit "tailor: <id> v<N>"`, then say: "When you've applied, tell me with /applied."
