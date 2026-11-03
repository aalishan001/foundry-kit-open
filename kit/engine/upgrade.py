#!/usr/bin/env python3
"""Bring their records up to this kit version after they unzip a new release over their folder. Safe to re-run: each
step only adds what's missing or moves an old field to its new shape, never removes their own values.
  upgrade.py           apply (setup.cmd and doctor.py --quick run it); prints each change, then a backup commit
  upgrade.py check     what would change, without changing anything
Their folder's version is kept in data/kit.json. History is committed before and after, so any step can be undone.
"""
import sys
from _common import KIT, DATA, PROFILE, load, save, today, stamp, pack

STATE = DATA / "kit.json"

def kit_version(): return (KIT / "VERSION").read_text(encoding="utf-8").strip()

def her_version(): return (load(STATE, {}) or {}).get("version", "1.0.0")

# ---------------------------------------------------------------- steps: each (description, apply(dry) -> [changes])
def search_rules_shape(dry):
    from fit import ESTABLISHED, PE_MIN_EMPLOYEES, PE_MIN_YEARS
    p = PROFILE / "search.json"; s = load(p)
    if s is None: return []
    out, r, L = [], s.setdefault("rules", {}), s.setdefault("locations", {})
    for k, v, what in (("abroad_stability", list(ESTABLISHED), "abroad: established companies only (no startups)"),
                       ("pe_min_employees", PE_MIN_EMPLOYEES, "PE-backed abroad: 1,000+ employees"),
                       ("pe_min_years", PE_MIN_YEARS, "PE-backed abroad: 10+ years old")):
        if k not in r: r[k] = v; out.append(f"search rules: added {what}")
    for k, v, what in (("abroad", [], "an ordered abroad list (empty until they name countries)"), ("pay_over_place", False, "pay over place (off)")):
        if k not in L: L[k] = v; out.append(f"search rules: added {what}")
    g = s.get("gmail") or {}
    if "checks" in g or "query" in g or "mode" not in g:
        was_on = bool(g.get("enabled"))
        s["gmail"] = {"enabled": False, "mode": "imap", "address": "", "label": "Job Alerts", "checked": None}
        out.append("Gmail: the connector check is retired; the kit now reads a Job Alerts label over IMAP"
                   + (" (it was on: double-click Gmail setup.cmd to turn it back on)" if was_on else " (off until Gmail setup.cmd)"))
    if out and not dry: save(p, s)
    return out

def radar_refresh(dry):
    import radar
    rad = radar.load_radar()
    if not rad["companies"]: return []
    by = {p["company"].lower(): p for p in pack().get("radar", {}).get("companies", [])}
    n = sum(1 for c in rad["companies"] if c.get("source") == "pack" and (p := by.get(c["company"].lower()))
            and any(k in p and c.get(k) != p[k] for k in radar.PACK_FIELDS))
    if not n: return []
    if not dry:
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()): radar.refresh()
    return [f"radar: {n} companies updated from the pack (stability, alert sign-ups); their checks and intervals unchanged"]

def backup_ignore(dry):
    p = DATA.parent / ".gitignore"
    if not p.exists(): return []
    t = p.read_text(encoding="utf-8")
    add = [x for x in ("/data/logs/",) if x not in t]
    if add and not dry: p.write_text(t.rstrip("\n") + "\n" + "\n".join(add) + "\n", encoding="utf-8", newline="\n")
    return ["history: the daily sweep log isn't kept in history"] if add else []

def jobs_shape(dry):
    p = DATA / "jobs.json"; d = load(p)
    if not d: return []
    miss = [j for j in d["jobs"] if "triage" not in j]
    if not miss: return []
    for j in miss: j["triage"] = None; j.setdefault("snippet", None)
    if not dry: save(p, d)
    waiting = sum(1 for j in miss if j["status"] == "new")
    return [f"jobs: {len(miss)} records gained a ranking field ({waiting} new ones will be ranked once by /sweep)"]

def intake_field(dry):
    """1.2: /start asks for the field first; a profile that already has a pack has answered it."""
    p = PROFILE / "intake.json"; d = load(p)
    if not d or "field" in (d.get("stages") or {}): return []
    has = bool((load(PROFILE / "search.json", {}) or {}).get("pack"))
    d["stages"] = {"field": "done" if has else "open", **d["stages"]}
    if not dry: save(p, d)
    return ["intake: the new field stage is " + ("already answered (the pack is set)" if has else "open")]

STEPS = [intake_field, search_rules_shape, radar_refresh, backup_ignore, jobs_shape]

def needed(): return her_version() != kit_version()

def run(dry=False, quiet=False):
    import backup
    if not dry and backup.is_repo():
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()): backup.commit(f"before upgrade to {kit_version()}")
    changes = []
    for step in STEPS: changes += step(dry)
    if not dry:
        save(STATE, {"version": kit_version(), "upgraded": stamp(), "from": her_version()})
        if backup.is_repo():
            import io, contextlib
            with contextlib.redirect_stdout(io.StringIO()): backup.commit(f"upgrade to {kit_version()}: " + ("; ".join(changes)[:200] or "no record changes"))
    if not quiet or changes:
        print(f"kit {kit_version()}" + (" (check only)" if dry else "") + (": " + str(len(changes)) + " change(s)" if changes else ": records already up to date"))
        for c in changes: print(f"  - {c}")
    return changes

def main(a):
    if a and a[0] in ("-h", "--help"): print(__doc__); return 0
    run(dry=bool(a and a[0] == "check"))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
