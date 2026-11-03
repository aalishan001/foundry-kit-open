---
description: Timed mock interview for one job, from the pack's question bank, the JD and their resume for that job. Scored, no do-overs.
argument-hint: "<job id> [minutes]"
model: sonnet
---

1. `python engine/doctor.py --quick`. Read the job, its JD, and the final tailored version for it if one exists
   (`data/tailored/<id>/`).

2. **Plan 6–10 questions.** About two thirds come from `packs/<pack>/grill.jsonl`:
   - their target families first;
   - `level_min` at or below the job's level.

   Choose the topics (technical, commercial, people, behavioural) to match the JD's emphasis. Add 2–3 questions that
   probe their resume bullets for that job: why, how, what if. Give each question a time budget (3–6 minutes).

3. **Start the clock:** `python engine/grill_clock.py start <id> --limit <minutes, default 45>`. It prints the log
   path.

4. **For each question:**
   - Before asking, state the rubric in one line, using the bank's `what_good_looks_like` plus structure and
     clarity.
   - Run `python engine/grill_clock.py ask <log> "<question>" --budget <min>`, then show the question.
   - When they answer, run `python engine/grill_clock.py answer <log> "<their answer, verbatim>"`.
   - Score it 0–10 against the stated rubric, as given, with one line on why. Record it:
     `python engine/grill_clock.py score <log> <n> <score> --area <topic> --why "<one line>"`, where the area is the
     question's topic or skill (for example "system design", "Kafka", "behavioral"). Ask one follow-up from the
     bank when it helps.
   - No do-overs. If they want to revise an answer, note it and move on.
   - If the script says TIME UP, stop asking.

5. **End:** `python engine/grill_clock.py end <log> --score <overall>`. Then show the scorecard:
   - each question with its score;
   - their weakest areas, from `python engine/grill_clock.py weakest <log>`;
   - three specific things to practise;
   - facts they mentioned that aren't in their bank yet, offered as draft facts for them to confirm.

   End with: "Prep the weakest areas? /prep <job id> --areas <the two or three weakest>"

6. Run `python engine/backup.py commit "grill: <id>"`.
