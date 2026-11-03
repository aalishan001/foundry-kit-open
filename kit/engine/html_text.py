"""HTML -> readable plain text and links, stdlib only (used for careers pages, JD pages and alert emails)."""
import html, re
from html.parser import HTMLParser

BLOCK = {"p", "div", "br", "li", "ul", "ol", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "table", "header", "footer"}
SKIP = {"script", "style", "noscript", "svg", "head", "template"}

class _P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.links, self.skip, self._a, self.chunks = [], [], 0, None, []
    def handle_starttag(self, tag, attrs):
        if tag in SKIP: self.skip += 1
        if tag in BLOCK: self.out.append("\n")
        if tag == "li": self.out.append("- ")
        if tag == "a":
            href = dict(attrs).get("href")
            self._a = [href, [], self.chunks[-6:]] if href else None
    def handle_endtag(self, tag):
        if tag in SKIP and self.skip: self.skip -= 1
        if tag in BLOCK: self.out.append("\n")
        if tag == "a" and self._a:
            self.links.append((self._a[0], re.sub(r"\s+", " ", "".join(self._a[1])).strip(), self._a[2])); self._a = None
    def handle_data(self, data):
        if self.skip: return
        self.out.append(data)
        if self._a is not None: self._a[1].append(data)
        elif data.strip(): self.chunks.append(re.sub(r"\s+", " ", data).strip())

def parse(markup):
    p = _P()
    try: p.feed(markup or ""); p.close()
    except Exception: pass   # malformed pages still give whatever was read
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.out))
    text = re.sub(r"\n\s*\n+", "\n\n", re.sub(r" *\n *", "\n", text)).strip()
    return text, [(h, t) for h, t, _ in p.links]

def to_text(markup): return parse(markup)[0]
def links(markup): return parse(markup)[1]

def links_with_context(markup):
    """[(href, anchor text, the up-to-6 text chunks just before the link)]: job cards often put the title before a
    generic 'View job' link."""
    p = _P()
    try: p.feed(markup or ""); p.close()
    except Exception: pass
    return p.links
def unescape(s): return html.unescape(s or "")
