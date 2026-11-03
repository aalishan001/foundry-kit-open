# Your profile

`/start` fills this folder. Every file here is yours, and the kit never overwrites it when it is updated.

| File | What it holds |
|---|---|
| `facts.jsonl` | your facts bank: one line per fact, each confirmed by you before any resume can use it |
| `identity.json` | your name, contacts and city |
| `search.json` | your search rules: current level and pay, the pay-rise threshold for same-level moves, places, role families |
| `employment.json`, `education.json` | titles, employers and dates exactly as they appear on resumes |
| `resume_prefs.json` | PDF, DOCX or both; page limit; which contacts to show |
| `intake.json` | how far `/start` got, and open questions |

Every change is kept in a local history (`engine/backup.py log`), so nothing is ever lost.
