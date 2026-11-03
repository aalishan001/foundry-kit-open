# Packs: what the kit knows about a field

A pack is a folder of plain JSON and Markdown that tells the engine about one field: its job levels, role families,
keywords, how to judge fit, what to ask in `/start`, interview questions, and a starter list of companies. The engine
itself names no field; adding one means adding a folder.

| Pack | For |
|---|---|
| `software-eng` | software engineers and engineering managers (the default) |
| `general` | any other field: a generic ladder, your own target titles, your own companies |

`/start` asks for your field and stores the choice in `profile/search.json` → `pack`. `python engine/profile_cli.py
packs` lists the installed packs.

## Files

| File | What it holds |
|---|---|
| `pack.json` | id, name, description, the level ladder (rank, titles, typical years), title abbreviations, `unclear_titles` (titles that mean different levels at different companies), the company `segments`, and `level_words` used to build job searches |
| `roles.json` | role families: titles, synonyms, must and nice keywords, adjacent families, `default` |
| `keywords.json` | the keyword map: each term's canonical name and variants (Postgres = PostgreSQL); short acronyms go in `exact_case` |
| `rubric.json`, `rubric.md` | the fit rubric `/check` follows; the weights sum to 100 |
| `radar.json` | starter companies: careers URL, portal type and tier, a live-check result, and a sourced ownership (`stability`) record |
| `probes.json` | the gap questions `/start` asks, common and per family |
| `grill.jsonl` | the mock-interview bank, one question per line with what a good answer covers |

## Writing a pack for another field

1. Copy `software-eng/` to `packs/<new-id>/` and set `pack.json` → `id` to the folder name.
2. Rewrite the ladder, families, keywords, rubric, probes and interview bank for that field. Keep the field names.
3. Build `radar.json` from the field's leading employers. Check each careers portal live and record the result in
   `verified`, with a source for each company's ownership.
4. Run `python engine/pack_check.py <new-id>` until it reports OK.

A pack never holds anything personal. Your facts live in `profile/`.
