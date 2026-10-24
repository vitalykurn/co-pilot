"""Knowledge base: the committed snapshots under kb/pages.

Phase 1: the whole KB (four pages, ~1.5k tokens) goes into the prompt. No
retrieval. `context_for()` is the one seam where a retriever plugs in later
(Phase 2) without touching the rest of the pipeline.

`find_quote()` is the deterministic grounding check: a citation is valid only
if its quote is literally present in a snapshot page.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB_DIR = ROOT / "kb"
PAGES_DIR = KB_DIR / "pages"
MANIFEST = KB_DIR / "manifest.json"

_FRONT = re.compile(r"^---\n(.*?)\n---\n\n?", re.S)
_WS = re.compile(r"\s+")
_QUOTES = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u00a0": " "})


def normalize(text: str) -> str:
    """Whitespace- and quote-insensitive form used for substring matching."""
    return _WS.sub(" ", text.translate(_QUOTES)).strip().lower()


_QUOTE_CHARS = "'\u2018\u2019\"\u201c\u201d"


def locate(body: str, quote: str) -> tuple[int, int] | None:
    """Character span of `quote` in `body`, matching the way `find_quote` does.

    Whitespace runs and straight-vs-curly quotes are interchangeable, case is
    ignored, nothing else is. Used to highlight a citation on the page.
    """
    tokens = quote.split()
    if not tokens:
        return None
    any_quote = "[" + re.escape(_QUOTE_CHARS) + "]"
    parts = ["".join(any_quote if ch in _QUOTE_CHARS else re.escape(ch) for ch in tok) for tok in tokens]
    m = re.search(r"\s+".join(parts), body, re.I)
    return (m.start(), m.end()) if m else None


@dataclass(frozen=True)
class Page:
    slug: str
    title: str
    url: str
    sha256: str
    body: str

    @property
    def normalized(self) -> str:
        return normalize(self.body)


class KnowledgeBase:
    def __init__(self, pages: list[Page]):
        self.pages = {p.slug: p for p in pages}
        self.version = hashlib.sha256("".join(p.sha256 for p in pages).encode()).hexdigest()[:12]

    @classmethod
    def load(cls, pages_dir: Path = PAGES_DIR) -> "KnowledgeBase":
        pages: list[Page] = []
        for path in sorted(pages_dir.glob("*.md")):
            raw = path.read_text(encoding="utf-8")
            m = _FRONT.match(raw)
            if not m:
                raise ValueError(f"{path} has no front matter; run kb/fetch.py")
            meta = dict(line.split(": ", 1) for line in m.group(1).splitlines())
            pages.append(
                Page(
                    slug=meta["slug"],
                    title=meta["title"],
                    url=meta["url"],
                    sha256=meta["sha256"],
                    body=raw[m.end():],
                )
            )
        if not pages:
            raise FileNotFoundError(f"no KB pages in {pages_dir}; run kb/fetch.py")
        return cls(pages)

    def context_for(self, ticket_text: str | None = None) -> str:
        """Text block handed to the model. Phase 1 ignores the ticket and returns all pages."""
        blocks = []
        for p in self.pages.values():
            blocks.append(f'<page slug="{p.slug}" url="{p.url}">\n{p.body.strip()}\n</page>')
        return "\n\n".join(blocks)

    def find_quote(self, quote: str, page: str | None = None) -> str | None:
        """Return the slug of the page that literally contains `quote`, else None.

        If `page` is given, only that page is checked. Matching ignores case,
        whitespace runs and curly-vs-straight quotes; nothing else.
        """
        q = normalize(quote)
        if len(q) < 8:
            return None  # too short to count as grounding
        candidates = [self.pages[page]] if page in self.pages else self.pages.values()
        for p in candidates:
            if q in p.normalized:
                return p.slug
        return None

    def url_for(self, slug: str) -> str | None:
        p = self.pages.get(slug)
        return p.url if p else None

    def manifest(self) -> list[dict]:
        if MANIFEST.exists():
            return json.loads(MANIFEST.read_text(encoding="utf-8"))
        return [{"slug": p.slug, "url": p.url, "sha256": p.sha256} for p in self.pages.values()]
