"""Shared helpers for the engine. Paths, the clock, JSON files, payloads, ids.

HOME is their folder: $FOUNDRY_HOME when set (tests), otherwise the folder above engine/. Kit files (packs, templates)
are read from HOME first, then from the kit beside this file. FOUNDRY_NOW=<ISO> fixes the clock (tests).
"""
import datetime as dt, json, os, pathlib, re, sys

for _s in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252; text holds ₹, –, →
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

KIT = pathlib.Path(__file__).resolve().parent.parent
HOME = pathlib.Path(os.environ.get("FOUNDRY_HOME") or KIT).resolve()
PROFILE, DATA, INBOX, ARCHIVE, RESUMES = (HOME / n for n in ("profile", "data", "inbox", "archive", "Resumes"))
TMP, CACHE = DATA / "tmp", DATA / "cache"

def kit_path(*parts):
    """A kit-owned file: their folder's copy if present, else the kit's."""
    p = HOME.joinpath(*parts)
    return p if p.exists() else KIT.joinpath(*parts)

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH = re.compile(r"^\d{4}-\d{2}$")
HTTPS = re.compile(r"^https://[^\s/?#]+\.[^\s]+$", re.I)
SHA = re.compile(r"^[0-9a-f]{64}$")
# Indian mobile numbers (third parties' numbers in pasted JDs never enter data/)
PHONE = re.compile(r"(?<![\w+])(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\w)")

def now():
    t = os.environ.get("FOUNDRY_NOW")
    return dt.datetime.fromisoformat(t) if t else dt.datetime.now().replace(microsecond=0)
def today(): return now().date()
def stamp(): return now().isoformat(timespec="seconds")
def ts_name(): return now().strftime("%Y%m%d-%H%M")

def unique_path(folder, stem, ext):
    """folder/<stem>.<ext>, or <stem>-2.<ext>, -3 ... when that name is taken (two runs in the same minute)."""
    p, n = pathlib.Path(folder) / f"{stem}.{ext}", 2
    while p.exists(): p, n = pathlib.Path(folder) / f"{stem}-{n}.{ext}", n + 1
    return p

def die(msg, code=1):
    print(f"REJECTED: {msg}", file=sys.stderr); sys.exit(code)

def load(p, default=None):
    p = pathlib.Path(p)
    if not p.exists(): return default
    try: return json.loads(p.read_text(encoding="utf-8-sig") or "null")
    except json.JSONDecodeError as e: die(f"{rel(p)} is not valid JSON ({e}); fix or restore it (backup.py log)")

def save(p, obj):
    p = pathlib.Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, p)   # atomic on Windows too: a crash never leaves half a file

def read_jsonl(p):
    p = pathlib.Path(p)
    if not p.exists(): return []
    rows = []
    for i, line in enumerate(p.read_text(encoding="utf-8-sig").splitlines(), 1):
        if line.strip():
            try: rows.append(json.loads(line))
            except json.JSONDecodeError as e: die(f"{rel(p)} line {i} is not valid JSON ({e})")
    return rows

def write_jsonl(p, rows):
    p = pathlib.Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")
    os.replace(tmp, p)

def append_jsonl(p, obj):
    p = pathlib.Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8", newline="\n") as f: f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def rel(p):
    p = pathlib.Path(p)
    try: return p.resolve().relative_to(HOME).as_posix()
    except ValueError: return p.as_posix()

def read_text(path):
    """A text file as written on Windows or anywhere: BOM stripped, CRLF -> LF."""
    return pathlib.Path(path).read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n")

def payload(raw):
    """A JSON payload: inline JSON, '-' for stdin, or '@<file>' (the safe form in PowerShell: write the JSON to
    data/tmp/<name>.json first)."""
    try:
        if raw == "-": return json.loads(sys.stdin.read())
        if raw.startswith("@"):
            p = pathlib.Path(raw[1:]); p = p if p.is_absolute() else HOME / p
            return json.loads(read_text(p))
        return json.loads(raw)
    except FileNotFoundError: die(f"no payload file {raw[1:]}")
    except json.JSONDecodeError as e: die(f"the payload is not valid JSON ({e})")

def opt(args, flag, default=None):
    if flag in args:
        i = args.index(flag)
        if i + 1 < len(args): return args[i + 1]
        die(f"{flag} needs a value")
    return default

def positional(args, flags_with_values=()):
    """Arguments that are neither flags nor flag values."""
    out, i = [], 0
    while i < len(args):
        if args[i] in flags_with_values: i += 2; continue
        if args[i].startswith("--"): i += 1; continue
        out.append(args[i]); i += 1
    return out

def date_arg(args, flag="--date", allow_future=False):
    d = opt(args, flag)
    if d is None: return today().isoformat()
    if not DATE.match(d): die(f"{flag} must be YYYY-MM-DD, not {d!r}")
    try: day = dt.date.fromisoformat(d)
    except ValueError: die(f"{flag} {d} is not a real date")
    if day > today() and not allow_future: die(f"{flag} {d} is in the future")
    return d

def next_id(rows, prefix):
    nums = [int(r["id"].split("-")[1]) for r in rows if str(r.get("id", "")).startswith(prefix + "-")]
    return f"{prefix}-{max(nums or [0]) + 1:04d}"

def days_since(d): return (today() - dt.date.fromisoformat(str(d)[:10])).days

def slug(text, n=40):
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s[:n].strip("-") or "item"

def safe_name(text):
    """A Windows-safe file or folder name (no <>:"/\\|?* and no trailing dot or space)."""
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(text))
    return re.sub(r"\s+", " ", s).strip(" .")[:80] or "Untitled"

def norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(text).lower())).strip()

# ---------------------------------------------------------------- profile and pack
def search_rules(): return load(PROFILE / "search.json", {}) or {}

DEFAULT_PACK = "software-eng"

def packs():
    """[(id, name, description)] for every pack in their folder or the kit."""
    seen, out = set(), []
    for base in (HOME / "packs", KIT / "packs"):
        for d in sorted(base.glob("*/pack.json")) if base.is_dir() else []:
            pid = d.parent.name
            if pid in seen: continue
            seen.add(pid); p = load(d, {}) or {}
            out.append((pid, p.get("name", pid), p.get("description", "")))
    return out

def pack_id():
    return search_rules().get("pack") or os.environ.get("FOUNDRY_PACK") or DEFAULT_PACK

def pack_dir(pid=None):
    pid = pid or pack_id()
    d = kit_path("packs", pid)
    if not d.is_dir(): die(f"no pack {pid!r} in packs/")
    return d

_PACK = {}
def pack(pid=None):
    """The pack as one dict: pack.json + roles, keywords, rubric, radar, probes (+ grill rows)."""
    pid = pid or pack_id()
    if pid in _PACK: return _PACK[pid]
    d = pack_dir(pid)
    p = load(d / "pack.json", {}) or {}
    for name in ("roles", "keywords", "rubric", "radar", "probes"):
        p[name] = load(d / f"{name}.json", {}) or {}
    p["grill"] = read_jsonl(d / "grill.jsonl")
    p["_dir"] = d
    _PACK[pid] = p
    return p
