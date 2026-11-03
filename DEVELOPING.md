# Working on foundry-kit

## Rules

- **Generic first.** Anything about a field goes in a pack (`kit/packs/<id>/`). Anything about a person goes in their
  own `profile/`, written at runtime by `/start`. The kit never hard-codes a person, a city preference or a pay figure.
- **Code does exact work.** Ids, dates, arithmetic, pay thresholds, level comparisons, dedupe, rendering and validation
  live in `kit/engine/`. Commands call the engine and report its output.
- **The truth rule is sacred.** Never weaken `claims.py`, the claim-checker or `prep.py`'s checks.
- **No personal data in the repo, ever.** Test fixtures use invented people, and build phone numbers, emails and paths
  at runtime so the leak scan stays clean (see `tests/test_leak_scan.py`).
- **Small installs.** Standard library first; every new dependency needs a reason.

## Everyday commands

```
python -m unittest discover -s tests          # the whole suite (Windows paths, OneDrive-style folders, CRLF input)
python scripts/leak_scan.py                   # scan the repo for personal data and secrets
python scripts/gen_opencode.py                # regenerate the OpenCode files after editing kit/.claude or kit/CLAUDE.md
python kit/engine/pack_check.py <pack-id>     # validate a pack
python scripts/build_release.py               # tests, leak scans, structure check, dist/foundry-kit-<version>.zip
```

## Leak scanning

`scripts/leak_scan.py` always checks for emails, phone numbers, home paths, file URLs, secrets and LinkedIn profile
links. Add your own terms (your name, employers, usernames) in a denylist kept **outside** the repo, one per line:
`~/.foundry-kit/denylist.txt`, or the file named by `FOUNDRY_LEAK_DENYLIST`. `build_release.py` refuses to build
without one (an empty file is allowed, but a real one is the point).

To scan every commit before it's made, add a pre-commit hook that runs `python scripts/leak_scan.py --staged`.

## Commands for two apps

`kit/.claude/commands/*.md` and `kit/CLAUDE.md` are the sources. `scripts/gen_opencode.py` renders
`kit/.opencode/`, `kit/AGENTS.md` and `kit/opencode.json` from them, with the model tiers in
`scripts/opencode_models.json`; a test fails if they drift. The OpenCode config must keep: OpenRouter as the only
provider, `zdr: true` and `data_collection: "deny"` on every model, web fetch and search denied.

## Measuring OpenCode costs

`scripts/measure_opencode.py` runs every command through `opencode run` in a scratch install with an invented
candidate, answers interactive steps with a simulated user, and reads the cost from OpenRouter's key usage. Store a
test key first with `python scripts/dev_keys.py set openrouter` (Windows Credential Manager; never a file). Put the
results in `kit/docs/SETUP.md`: the release refuses while the cost table is a placeholder.

## Packs

See `kit/packs/README.md`. Every company in a `radar.json` needs a live-checked portal (`verified`) and a sourced
ownership record (`stability`).
