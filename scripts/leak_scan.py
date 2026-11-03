#!/usr/bin/env python3
"""Leak scan: personal data never enters this repo or a release.
  leak_scan.py                     every file git would track (tracked + untracked, not ignored)
  leak_scan.py <path>...           these files or folders
  leak_scan.py --staged            the staged copy of every staged file (the pre-commit hook)
Options:
  --scope kit                      treat every file as shipping (files under kit/ always are)
  --denylist <file>                a denylist to use (repeatable). Default: $FOUNDRY_LEAK_DENYLIST (os.pathsep list),
                                   else ~/.foundry-kit/denylist.txt
  --profile <dir>                  also derive terms from a kit install's profile/ folder (repeatable)
  --require-denylist               exit 2 when no denylist file exists (releases fail closed)
Exit: 0 clean, 1 hits, 2 usage or config error. Every match is masked in the report, so the report never repeats it.

What it checks, in file contents and in file names:
  built-in   email addresses (example/test domains allowed), phone numbers, user-home paths (placeholders such as
             C:\\Users\\<you> allowed), file-scheme URLs, secret-shaped tokens, LinkedIn profile URLs
  denylist   one term per line: case-insensitive whole word; '=' prefix exact case; 're:' prefix a regex;
             a 'kit:' prefix (before the others) applies the term only to shipping files; '#' starts a comment
  profile    every string in identity.json (or under an "identity" key) except location and preference fields:
             names (whole and each part of 4+ letters), emails, phone digits, links
Binary files: .docx/.xlsx/.pptx/.odt/.zip members are scanned as text; anything else by its printable ASCII runs.
"""
import io, json, os, pathlib, re, subprocess, sys, zipfile

for _s in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
    if hasattr(_s, "reconfigure"): _s.reconfigure(encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_DENYLIST = pathlib.Path.home() / ".foundry-kit" / "denylist.txt"
SKIP_DIRS = {".git", "seed", "dist", "__pycache__", "node_modules"}
ZIP_EXT = {".docx", ".xlsx", ".pptx", ".odt", ".zip"}
SAFE_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "example.in", "anthropic.com"}
SAFE_EMAIL_TLDS = (".example", ".test", ".invalid", ".localhost")
IDENTITY_SKIP_KEYS = {"location", "locations", "city", "cities", "country", "region", "regions", "preferences", "source", "updated"}

def rx_term(term, exact=False):
    """Whole word, where '_' also separates words (file names like Name_Resume.pdf)."""
    body = r"\s+".join(re.escape(w) for w in term.split())
    return re.compile(rf"(?<![^\W_]){body}(?![^\W_])", 0 if exact else re.I)

def digits_rx(value):
    d = re.sub(r"\D", "", value)[-10:]
    return re.compile(r"(?<!\d)" + r"[\s.()-]*".join(d) + r"(?!\d)") if len(d) >= 7 else None

NOREPLY_LOCAL = re.compile(r"(?i)^(?:[a-z]+-)?no-?reply$")   # system senders such as jobalerts-noreply@: nobody's address

def email_ok(m):
    local, dom = m.group(0).rsplit("@", 1); dom = dom.lower()
    if NOREPLY_LOCAL.match(local) and not dom.endswith("noreply.github.com"): return True
    return dom in SAFE_EMAIL_DOMAINS or dom.endswith(SAFE_EMAIL_TLDS) or any(dom.endswith("." + d) for d in SAFE_EMAIL_DOMAINS)

# (label, regex, allowed(match) -> bool or None)
BUILTIN = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), email_ok),
    ("phone", re.compile(r"(?<![\w+])(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\w)"), None),
    ("phone", re.compile(r"(?<![\w+])\+(?!91)\d{1,3}[\s.-]?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}(?!\d)"), None),
    ("home path", re.compile(r"(?i)\b[a-z]:[\\/]+users[\\/]+(?![<%{$]|public\b|default\b|all users\b)[^\\/\s\"'<>]+"), None),
    ("home path", re.compile(r"(?<![\w/.:-])(?:/c/[Uu]sers|/home|/Users)/(?![<%{$])[^/\s\"'<>]+"), None),
    ("file url", re.compile(r"(?i)file:/{2,3}"), None),
    ("secret", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{30,}"), None),
    ("secret", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{24,}"), None),
    ("secret", re.compile(r"\bAKIA[0-9A-Z]{16}\b|\bAIza[0-9A-Za-z_-]{35}\b|\bxox[abprs]-[A-Za-z0-9-]{10,}"), None),
    ("secret", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), None),
    ("linkedin profile", re.compile(r"(?i)linkedin\.com/in/[A-Za-z0-9_-]+"), None),
]

class Rule:
    def __init__(self, label, rx, kit_only=False, allowed=None):
        self.label, self.rx, self.kit_only, self.allowed = label, rx, kit_only, allowed

def load_denylist(path):
    rules = []
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        t = raw.strip()
        if not t or t.startswith("#"): continue
        kit_only = t.startswith("kit:")
        if kit_only: t = t[4:].strip()
        try:
            if t.startswith("re:"): rx = re.compile(t[3:])
            elif t.startswith("="): rx = rx_term(t[1:], exact=True)
            else: rx = rx_term(t)
        except re.error as e:
            print(f"CONFIG: {path.name}:{n} is not a valid regex ({e})"); sys.exit(2)
        rules.append(Rule(f"denylist {path.name}:{n}", rx, kit_only))
    return rules

def identity_strings(obj, path=""):
    """(key path, value) for every string leaf, skipping location and preference subtrees."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() not in IDENTITY_SKIP_KEYS: yield from identity_strings(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for v in obj: yield from identity_strings(v, path)
    elif isinstance(obj, str):
        yield path, obj

def find_identity(obj):
    if isinstance(obj, dict):
        if isinstance(obj.get("identity"), dict): yield obj["identity"]   # not e.g. intake.json's {"identity": "done"}
        for v in obj.values(): yield from find_identity(v)
    elif isinstance(obj, list):
        for v in obj: yield from find_identity(v)

def profile_rules(folder):
    rules, seen = [], set()
    def add(label, rx):
        if rx and rx.pattern not in seen: seen.add(rx.pattern); rules.append(Rule(label, rx))
    for p in sorted(pathlib.Path(folder).rglob("*.json")):
        try: data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError): continue
        blocks = [data] if p.name == "identity.json" else list(find_identity(data))
        for block in blocks:
            for key, v in identity_strings(block):
                v = v.strip()
                if len(v) < 3: continue
                label = f"profile {p.name}"
                if re.fullmatch(r"[+\d\s().-]{7,}", v): add(label, digits_rx(v)); continue
                if "@" in v: add(label, rx_term(v)); continue
                if re.match(r"(?i)^https?://", v):
                    add(label, re.compile(re.escape(re.sub(r"(?i)^https?://(www\.)?", "", v).rstrip("/")), re.I)); continue
                add(label, rx_term(v))
                if "name" in str(key).lower():
                    for part in re.split(r"[\s.,]+", v):
                        if len(part) >= 4: add(label, rx_term(part))
    return rules

def denylist_paths(args):
    if args: return [pathlib.Path(a) for a in args]
    env = os.environ.get("FOUNDRY_LEAK_DENYLIST")
    if env: return [pathlib.Path(p) for p in env.split(os.pathsep) if p]
    return [DEFAULT_DENYLIST]

# ---------------------------------------------------------------- reading files
def is_kit(rel): return rel.replace("\\", "/").startswith("kit/")

def texts(name, data):
    """(display name, text) pieces of one file: zip-based documents member by member, other binaries as ASCII runs."""
    ext = pathlib.PurePath(name).suffix.lower()
    if ext in ZIP_EXT:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for m in z.namelist():
                    if m.endswith("/"): continue
                    yield from texts(f"{name}!{m}", z.read(m))
            return
        except zipfile.BadZipFile:
            pass
    if b"\x00" in data[:8192] or ext in {".pdf", ".png", ".jpg", ".jpeg", ".ttf", ".otf"}:
        yield name, "\n".join(m.decode("ascii") for m in re.findall(rb"[\x20-\x7e]{4,}", data))
    else:
        yield name, data.decode("utf-8", errors="replace")

def mask(line, m):
    s, e = m.span()
    hit = line[s:e]
    shown = line[max(0, s - 40):s] + hit[:2] + "***" + line[e:e + 40]
    return shown.strip()

def scan_text(name, text, rules, kit):
    """name: the file's path below the folder being scanned (scanned too, as the first line)."""
    hits = []
    for n, line in enumerate([name] + text.splitlines()):
        for r in rules:
            if r.kit_only and not kit: continue
            for m in r.rx.finditer(line):
                if r.allowed and r.allowed(m): continue
                where = f"{name} (file name)" if n == 0 else f"{name}:{n}"
                hits.append(f"{where}: [{r.label}] {mask(line, m)[:160]}")
                break
    return hits

def scan_bytes(name, data, rules, kit):
    hits = []
    for part, text in texts(name, data):
        hits += scan_text(part, text, rules, kit)
    return hits

# ---------------------------------------------------------------- choosing files
# A target is (path, name): name is what the report shows and what the file-name check reads. Inside the repo it is the
# repo-relative path; elsewhere it starts at the folder given (or is the bare file name), so the scanner never flags
# the folders above it.
def git(*a):
    return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, check=True).stdout

def in_repo(p):
    try: return p.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError: return None

def repo_files():
    try:
        out = git("ls-files", "-z", "-co", "--exclude-standard")
        return [(ROOT / f, f) for f in out.decode("utf-8").split("\0") if f]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return walk(ROOT)

def walk(folder):
    folder = pathlib.Path(folder)
    out = []
    for p in sorted(folder.rglob("*")):
        rel = p.relative_to(folder)
        if p.is_file() and not SKIP_DIRS & set(rel.parts[:-1]):
            out.append((p, in_repo(p) or (pathlib.PurePath(folder.resolve().name) / rel).as_posix()))
    return out

def is_kit(path, name):
    """Shipping files: anything under kit/ in the repo; outside it, any file inside a folder named kit."""
    return name.startswith("kit/") if in_repo(path) else "kit" in pathlib.Path(path).resolve().parent.parts

def staged():
    names = git("diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR").decode("utf-8").split("\0")
    return [(f, git("show", f":{f}")) for f in names if f]

# ---------------------------------------------------------------- main
def opts(argv, flag):
    vals, rest, i = [], [], 0
    while i < len(argv):
        if argv[i] == flag and i + 1 < len(argv): vals.append(argv[i + 1]); i += 2
        else: rest.append(argv[i]); i += 1
    return vals, rest

def main(argv):
    if "-h" in argv or "--help" in argv: print(__doc__); return 0
    deny_args, argv = opts(argv, "--denylist")
    profiles, argv = opts(argv, "--profile")
    scope, argv = opts(argv, "--scope")
    if scope and scope[-1] not in ("kit", "repo"): print("USAGE: --scope kit|repo"); return 2
    all_kit = bool(scope) and scope[-1] == "kit"
    flags = {a for a in argv if a.startswith("--")}
    paths = [a for a in argv if not a.startswith("--")]
    unknown = flags - {"--staged", "--require-denylist", "--quiet"}
    if unknown: print(f"USAGE: unknown option {sorted(unknown)[0]}\n{__doc__}"); return 2

    rules = [Rule(l, rx, allowed=ok) for l, rx, ok in BUILTIN]
    found = [p for p in denylist_paths(deny_args) if p.is_file()]
    missing = [p for p in denylist_paths(deny_args) if not p.is_file()]
    if missing and "--require-denylist" in flags:
        print(f"CONFIG: no denylist at {', '.join(str(p) for p in missing)}; refusing to call anything clean without it"); return 2
    if missing and not found:
        print(f"WARNING: no denylist at {missing[0]}: only built-in and profile checks ran", file=sys.stderr)
    deny_files = {p.resolve() for p in found}
    for p in found: rules += load_denylist(p)
    for d in profiles:
        if not pathlib.Path(d).is_dir(): print(f"CONFIG: --profile {d} is not a folder"); return 2
        rules += profile_rules(d)

    hits, count = [], 0
    if "--staged" in flags:
        for rel, data in staged():
            count += 1; hits += scan_bytes(rel, data, rules, all_kit or rel.startswith("kit/"))
    else:
        targets = []
        for a in paths or [None]:
            if a is None: targets += repo_files(); continue
            p = pathlib.Path(a)
            if not p.exists(): print(f"USAGE: no such file or folder {a}"); return 2
            targets += walk(p) if p.is_dir() else [(p, in_repo(p) or p.name)]
        for p, name in targets:
            if p.resolve() in deny_files or not p.is_file(): continue
            count += 1
            hits += scan_bytes(name, p.read_bytes(), rules, all_kit or is_kit(p, name))
    for h in hits: print(h)
    if "--quiet" not in flags or hits:
        print(f"leak scan: {count} file(s), {len(hits)} hit(s)" + ("" if hits else ", clean"))
    return 1 if hits else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
