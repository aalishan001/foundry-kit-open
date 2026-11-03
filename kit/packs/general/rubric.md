# Fit rubric: any field

Used by `/check`. `fit.py rules` decides level, pay and location exactly. This rubric is the judgment part.

| Criterion | Weight | Scores 1 when |
|---|---|---|
| Family | 25 | the role matches one of the user's target titles or areas (responsibilities, not just keywords) |
| Skills | 30 | every must-have skill, tool and qualification in the JD is backed by a confirmed fact |
| Level | 15 | it's a step up. A lateral role that clears the pay threshold scores 0.8, lateral with pay unknown 0.5, unclear 0.4 |
| Years | 10 | relevant years meet the JD's minimum. Up to 2 years short scores 0.5; more than that scores 0 |
| Location | 10 | the role is remote. Home country scores 0.8 (1.0 in a preferred place), eligible abroad 0.6 |
| Extras | 10 | nice-to-haves are backed by facts (domain, certifications, named tools) |

Bands: **75+ strong**, **55–74 good**, **40–54 stretch**, **below 40 weak**. Likeliness starts from match: subtract for
missing hard requirements and big level jumps, add for a referral or a JD that mirrors current work; never above
match + 15.
