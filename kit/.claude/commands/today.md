---
description: One view of what needs them today, and the next three actions. Changes nothing.
model: haiku
effort: low
---

1. `python engine/doctor.py --quick`.
2. `python engine/today.py`. Show its sections as compact tables, skipping empty ones in a single line ("Nothing
   stale."). The sections are:
   - interviews and calls coming up;
   - radar companies due;
   - new jobs not reviewed;
   - shortlisted jobs not applied;
   - applications to follow up;
   - open profile questions.
3. End with **the next three actions**, most valuable first, each naming the command. For example: "Prepare for
   Thursday's round with /grill j-0012", "/sweep (9 companies due)", "Follow up with Acme (a-0003): 16 days without
   news".
4. Suggest only. Never set a status from here.
