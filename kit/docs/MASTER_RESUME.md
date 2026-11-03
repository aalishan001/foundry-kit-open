# Your master resume: write everything down once

Before you run `/start`, put **one long document** in the folder's `inbox`: a master resume, or a plain career brain
dump. **No page limit.** Ten pages is better than one. Bullet points, rough notes and half sentences are all fine. Word,
PDF, Markdown or plain text all work.

## Why it has to be long

The kit never invents anything. Every line of every tailored resume, application note and interview answer must
trace back to a fact you confirmed, and two separate checks refuse anything that doesn't: `claims.py` (numbers and
names must appear in the cited facts) and the `claim-checker` (flags anything stretched).

So the kit can only use what you tell it. A trimmed one-page resume has already thrown away the details that win the
next job: the scale, the numbers, the incident you handled, the tool you built on a weekend. Give it all of it once,
and `/tailor` and `/prep` can pick the right facts for each role, for every application, without leaving out the one
detail that job cares about.

Nothing here leaves your folder except to the AI model you use, under the privacy rules in `SETUP.md`. Facts marked
private (pay, reasons for leaving) are never put on a resume.

## What to put in it

For **every job you've had** (and internships, freelance work, research, college projects if you're early in your
career):

- [ ] Company, your exact title(s), start and end month, city, and any promotions with dates.
- [ ] What the team or product did, and who used it.
- [ ] Every project you worked on: what it was, your part in it (built, led, owned, helped), and what came of it.
- [ ] Numbers, even rough ones: users, requests per second, latency before and after, data volume, money saved or
      earned, cost cut, time saved, error rate, team size, deadlines hit. Write "about" if you're not sure.
- [ ] Design and architecture decisions you made or argued for: the options, what you chose, why, and the outcome.
- [ ] Production incidents or crises you handled: what broke, how you found it, how long it took, what changed after.
- [ ] Your tech stack and tools in that job (languages, frameworks, databases, cloud, internal tools), and how deep
      you went with each.
- [ ] Internal tools, scripts, dashboards or automations you built, even small ones.
- [ ] People: anyone you managed, mentored, hired or interviewed; teams you worked with.
- [ ] Awards, shout-outs, ratings, performance-review highlights.

And outside work:

- [ ] Open-source contributions (with links to repos and pull requests), side projects, hackathons.
- [ ] Talks, blog posts, papers, patents.
- [ ] Certifications and courses, with the year.
- [ ] Education: degree, institution, years, grade if you'd show it.
- [ ] Links: LinkedIn, GitHub, portfolio, personal site.
- [ ] Rough notes: anything else you're proud of or think might matter, even if you're not sure how to phrase it.

For other fields, the same idea applies: every responsibility, every result with its number, every tool, every
qualification.

## Tips

- Don't polish. `/start` turns it into short facts and shows each one to you to confirm, edit or delete.
- Old resumes, performance reviews, project write-ups and LinkedIn exports can go in `inbox` too.
- You can add more any time: `/update I also led the migration to Kubernetes in 2022` becomes a new fact.
