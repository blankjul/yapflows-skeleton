#!/usr/bin/env python3
# description: Fetch a URL and return readable text — no JS, no cookies, no browser
# usage: {python} {path} --help
"""
Simple HTTP fetch — no browser, no JS execution.
Extracts readable text from HTML using markdownify (if installed) or stdlib html.parser.

WHEN TO USE:
- Static web pages (blogs, articles, documentation)
- Public APIs and endpoints
- Fast content retrieval when JavaScript is not needed
- When you don't need authentication or cookies
- Pages that work without client-side rendering

DO NOT USE FOR:
- Sites requiring login/authentication (use web_browser.py instead)
- Dynamic content loaded by JavaScript (use web_browser.py instead)
- Interactive pages (use web_browser.py instead)
"""

from __future__ import annotations

import argparse
import os
import sys


_SKIP_TAGS = {"script", "style", "head", "noscript", "nav", "footer", "header", "aside", "form", "iframe", "svg", "button"}


def _clean_html(html: str) -> str:
    """Remove noisy tags before text extraction."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(_SKIP_TAGS):
            tag.decompose()
        return str(soup)
    except ImportError:
        # Fallback: strip tags via simple replacement (best-effort)
        return html


def _strip_html(html: str) -> str:
    """Basic HTML → text via stdlib html.parser (fallback when markdownify not installed)."""
    from html.parser import HTMLParser

    class _Stripper(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self._parts: list[str] = []
            self._skip = False
            self._skip_depth: int = 0

        def handle_starttag(self, tag: str, attrs: list) -> None:
            if tag in _SKIP_TAGS:
                self._skip_depth += 1
                self._skip = True

        def handle_endtag(self, tag: str) -> None:
            if tag in _SKIP_TAGS:
                self._skip_depth = max(0, self._skip_depth - 1)
                if self._skip_depth == 0:
                    self._skip = False

        def handle_data(self, data: str) -> None:
            if not self._skip:
                stripped = data.strip()
                if stripped:
                    self._parts.append(stripped)

        def get_text(self) -> str:
            return "\n".join(self._parts)

    stripper = _Stripper()
    stripper.feed(html)
    return stripper.get_text()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="web.py",
        description=(
            "Fetch a URL and return readable text.\n\n"
            "No JavaScript execution — use browser.py for JS-heavy pages.\n"
            "Uses markdownify for text extraction if installed, otherwise stdlib html.parser."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python web.py https://example.com\n"
            "  python web.py https://example.com --max-chars 8000\n"
            "  python web.py https://example.com --offset 5000 --max-chars 5000\n"
            "  python web.py https://example.com --download\n"
            "  python web.py https://raw.githubusercontent.com/user/repo/main/README.md"
        ),
    )
    parser.add_argument("url", help="URL to fetch.")
    parser.add_argument(
        "--max-chars",
        type=int,
        default=5000,
        metavar="N",
        help="Maximum characters of text to return (default: 5000).",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        metavar="N",
        help="Skip the first N characters before slicing (default: 0). Use to page through truncated output.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Save the raw HTML to $USER_DIR/scratchpad/<uuid>.html and print the path.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Fetch: httpx preferred, fall back to urllib
    html: str
    try:
        import httpx

        resp = httpx.get(
            args.url,
            follow_redirects=True,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 yapflows/2"},
        )
        resp.raise_for_status()
        html = resp.text
    except ImportError:
        try:
            from urllib.request import Request, urlopen

            req = Request(args.url, headers={"User-Agent": "Mozilla/5.0 yapflows/2"})
            with urlopen(req, timeout=15) as r:
                html = r.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"Error fetching {args.url}: {e}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Error fetching {args.url}: {e}", file=sys.stderr)
        sys.exit(1)

    # Optionally save raw HTML
    if args.download:
        import uuid
        from pathlib import Path

        scratchpad = Path(os.environ["USER_DIR"]) / "scratchpad"
        scratchpad.mkdir(parents=True, exist_ok=True)
        out_path = scratchpad / f"{uuid.uuid4().hex}.html"
        out_path.write_text(html, encoding="utf-8")
        print(f"Downloaded HTML to: {out_path}")

    # Clean then extract text
    cleaned = _clean_html(html)
    try:
        import markdownify

        text = markdownify.markdownify(cleaned, heading_style="ATX")
    except ImportError:
        text = _strip_html(cleaned)

    # Apply offset then slice
    start = args.offset
    end = start + args.max_chars
    chunk = text[start:end]

    if end < len(text):
        next_offset = end
        chunk += (
            f"\n...(truncated, {len(text) - end} chars omitted. "
            f"Use --offset {next_offset} --max-chars {args.max_chars} to read more.)"
        )

    print(chunk)


if __name__ == "__main__":
    main()
