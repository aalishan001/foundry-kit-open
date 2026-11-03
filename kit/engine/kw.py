"""The pack's keyword map: which canonical terms a text mentions, through each term's variants.
keywords.json: {"terms": [{"id", "canonical", "variants": [...], "exact_case": [...], "group", "families": [...]}]}
Variants match case-insensitively as whole words; those also listed in exact_case (short acronyms such as PR or CMS)
match only in that exact case, so "pr" in "process" or "Pr." never counts.
"""
import re
from _common import pack

_RX = {}

def terms(p=None):
    return (p or pack()).get("keywords", {}).get("terms", [])

def _rx(term):
    key = term["id"]
    if key not in _RX:
        exact = set(term.get("exact_case") or [])
        parts = []
        for v in sorted(set(term.get("variants") or []) | {term["canonical"]}, key=len, reverse=True):
            body = r"[\s-]+".join(re.escape(w) for w in v.split())
            parts.append(("" if v in exact else "(?i:") + body + ("" if v in exact else ")"))
        _RX[key] = re.compile(r"(?<![^\W_])(?:" + "|".join(parts) + r")(?![^\W_])")
    return _RX[key]

def find(text, p=None):
    """{term id: canonical} for every term the text mentions."""
    return {t["id"]: t["canonical"] for t in terms(p) if _rx(t).search(text or "")}

def same_term(a, b, p=None):
    """True when two phrases are variants of one term (e.g. 'PR' and 'performance ratio')."""
    ta, tb = set(find(a, p)), set(find(b, p))
    return bool(ta & tb)

def mentions(text, phrase, p=None):
    """Does text mention phrase, directly or through a variant of the same term?"""
    if re.search(r"(?<![^\W_])" + re.escape(phrase) + r"(?![^\W_])", text or "", re.I): return True
    ids = set(find(phrase, p))
    return bool(ids and ids & set(find(text, p)))
