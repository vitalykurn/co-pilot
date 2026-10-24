"""Snapshot the four public Valetax help pages into kb/pages/*.md.

The snapshots are the knowledge base. They are committed to git so that every
eval run and every ticket result can point at an exact KB version (sha256).
Re-run this script to refresh; a changed hash means the KB changed and the eval
set should be re-run.

Usage: python kb/fetch.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

PAGES = {
    "how-to-deposit": "https://valetax.com/how-to-deposit/",
    "how-to-withdraw": "https://valetax.com/how-to-withdraw/",
    "how-to-open-an-account": "https://valetax.com/how-to-open-an-account/",
    "how-to-verify-account": "https://valetax.com/how-to-verify-account/",
}

HERE = Path(__file__).resolve().parent
PAGES_DIR = HERE / "pages"
MANIFEST = HERE / "manifest.json"

HEADING_LEVEL = {"h1": "#", "h2": "##", "h3": "###", "h4": "####"}


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (support-copilot kb snapshot)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def extract_markdown(html: bytes) -> tuple[str, str]:
    """Return (title, markdown body) from the page's <main> element.

    Only text is kept. Layout, images and payment-channel logos are dropped,
    which is why the 'Payment Channels' section in the snapshot is empty: on the
    live page it is a row of logos with no text.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    main = soup.find("main") or soup.body
    title = ""
    lines: list[str] = []
    for el in main.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        text = " ".join(el.get_text(" ", strip=True).split())
        if not text:
            continue
        if el.name in HEADING_LEVEL:
            if el.name == "h1" and not title:
                title = text
            lines.append(f"{HEADING_LEVEL[el.name]} {text}")
        elif el.name == "li":
            lines.append(f"- {text}")
        else:
            lines.append(text)
    # Collapse consecutive duplicates (the theme repeats some headings).
    deduped: list[str] = []
    for line in lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)
    return title, "\n\n".join(deduped) + "\n"


def write_page(slug: str, url: str, title: str, body: str, fetched_at: str) -> dict:
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    front = (
        "---\n"
        f"slug: {slug}\n"
        f"title: {title}\n"
        f"url: {url}\n"
        f"fetched_at: {fetched_at}\n"
        f"sha256: {sha}\n"
        "---\n\n"
    )
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    (PAGES_DIR / f"{slug}.md").write_text(front + body, encoding="utf-8", newline="\n")
    return {"slug": slug, "title": title, "url": url, "fetched_at": fetched_at, "sha256": sha}


def main() -> int:
    fetched_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    manifest = []
    for slug, url in PAGES.items():
        html = download(url)
        title, body = extract_markdown(html)
        entry = write_page(slug, url, title, body, fetched_at)
        manifest.append(entry)
        print(f"{slug:24s} {entry['sha256'][:12]}  {len(body):6d} chars")
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
