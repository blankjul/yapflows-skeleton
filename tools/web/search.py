#!/usr/bin/env python3
# description: Search the web via headless browser — returns ranked results with titles, URLs, and snippets
# usage: {python} {path} <query> [options] — run with --help for full usage
"""
search — Search the web using a headless browser.

Sessions are compatible with browser.py — pass --session to reuse an
existing browser session, or continue in search's session with browser.py.

Examples:
  search.py "Bayern Munich score"
  search.py "AMZN stock" --engine google --n 8
  search.py "query" --session abc123   # reuse existing browser session
  browser.py --session abc123 navigate <url>  # continue in same session
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path


# ---------------------------------------------------------------------------
# Session helpers — identical layout to browser.py
# ---------------------------------------------------------------------------

def _browser_dir() -> Path:
    base = os.getenv("USER_DIR")
    root = Path(base).expanduser() if base else Path.home() / "yapflows"
    d = root / "data" / "browser"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _session_dir(session_id: str) -> Path:
    d = _browser_dir() / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_state(sdir: Path) -> dict:
    state_file = sdir / "state.json"
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except Exception:
            pass
    return {"url": None, "cookies": []}


def _save_state(sdir: Path, url: str, cookies: list) -> None:
    (sdir / "state.json").write_text(json.dumps({"url": url, "cookies": cookies}, indent=2))


def _save_page_text(sdir: Path, text: str) -> None:
    (sdir / "page_text.txt").write_text(text)


# ---------------------------------------------------------------------------
# Search engines
# ---------------------------------------------------------------------------

ENGINES = {
    "bing":       "https://www.bing.com/search?q={query}",
    "google":     "https://www.google.com/search?q={query}&hl=en",
    "duckduckgo": "https://html.duckduckgo.com/html/?q={query}",
}


def _decode_bing_url(href: str) -> str:
    """Decode Bing's redirect URLs — extract real URL from u= param."""
    if "/ck/a?" not in href:
        return href
    from urllib.parse import urlparse, parse_qs
    import base64
    qs = parse_qs(urlparse(href).query)
    u = qs.get("u", [""])[0]
    if u.startswith("a1"):
        try:
            return base64.b64decode(u[2:] + "==").decode("utf-8", errors="ignore")
        except Exception:
            pass
    return href


def _parse_bing(page) -> list[dict]:
    results = []
    for item in page.query_selector_all("li.b_algo"):
        h2      = item.query_selector("h2 a")
        snippet = item.query_selector(".b_caption p")
        if not h2:
            continue
        title = (h2.inner_text() or "").strip()
        url   = _decode_bing_url(h2.get_attribute("href") or "")
        snip  = (snippet.inner_text() if snippet else "").strip()
        if title:
            results.append({"title": title, "url": url, "snippet": snip})
    return results


def _parse_duckduckgo(page) -> list[dict]:
    results = []
    items = page.query_selector_all(".result")
    for item in items:
        title_el   = item.query_selector(".result__title a")
        snippet_el = item.query_selector(".result__snippet")
        url_el     = item.query_selector(".result__url")
        if not title_el:
            continue
        title   = (title_el.inner_text() or "").strip()
        snippet = (snippet_el.inner_text() if snippet_el else "").strip()
        url     = (title_el.get_attribute("href") or "").strip()
        # DDG wraps URLs in a redirect — extract the real one
        if "uddg=" in url:
            from urllib.parse import unquote, urlparse, parse_qs
            qs = parse_qs(urlparse(url).query)
            url = unquote(qs.get("uddg", [url])[0])
        if title:
            results.append({"title": title, "url": url, "snippet": snippet})
    return results


def _parse_google(page) -> list[dict]:
    results = []
    # Find all h3 headings inside links — works across Google's changing layout
    headings = page.query_selector_all("h3")
    for h3 in headings:
        # Walk up to find the enclosing <a>
        link_el = h3.evaluate_handle(
            "el => el.closest('a') || el.parentElement?.closest('a')"
        ).as_element()
        if not link_el:
            continue
        url = (link_el.get_attribute("href") or "").strip()
        if not url.startswith("http"):
            continue
        title = (h3.inner_text() or "").strip()
        if not title:
            continue
        # Snippet: look for text sibling container after the link's parent
        snippet = ""
        try:
            container = link_el.evaluate_handle(
                "el => el.closest('[data-hveid]') || el.parentElement?.parentElement"
            ).as_element()
            if container:
                snippet_el = container.query_selector(".VwiC3b, [data-sncf='1'], .lyLwlc, [style*='webkit-line-clamp']")
                if snippet_el:
                    snippet = (snippet_el.inner_text() or "").strip()
        except Exception:
            pass
        results.append({"title": title, "url": url, "snippet": snippet})
    return results


# ---------------------------------------------------------------------------
# Main search action
# ---------------------------------------------------------------------------

def do_search(
    query: str,
    engine: str,
    n: int,
    sdir: Path,
    json_out: bool,
    max_chars: int,
) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright not installed. Run: pip install playwright && playwright install chromium")

    state   = _load_state(sdir)
    url_tpl = ENGINES[engine]
    search_url = url_tpl.format(query=query.replace(" ", "+"))

    # For Google: inject real Chrome cookies to bypass bot detection
    chrome_cookies = []
    if engine == "google":
        try:
            import browser_cookie3
            jar = browser_cookie3.chrome(domain_name=".google.com")
            for c in jar:
                cookie = {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
                if c.expires:
                    cookie["expires"] = c.expires
                if c.secure:
                    cookie["secure"] = True
                chrome_cookies.append(cookie)
        except Exception:
            pass  # no browser_cookie3 or Chrome not available

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        if chrome_cookies:
            ctx.add_cookies(chrome_cookies)
        elif state["cookies"]:
            ctx.add_cookies(state["cookies"])

        page = ctx.new_page()
        try:
            from playwright_stealth import Stealth
            Stealth().apply_stealth_sync(page)
        except Exception:
            pass  # stealth not available or failed, proceed without
        page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        page.wait_for_timeout(2000)  # let JS-rendered content settle

        if engine == "google":
            results = _parse_google(page)
        elif engine == "bing":
            results = _parse_bing(page)
        else:
            results = _parse_duckduckgo(page)

        page_text = page.inner_text("body")
        cookies   = ctx.cookies()
        final_url = page.url
        ctx.close()
        browser.close()

    _save_state(sdir, final_url, cookies)
    _save_page_text(sdir, page_text)

    results = results[:n]

    if not results:
        # Fall back to raw page text if parsing found nothing
        print("(no structured results parsed — raw page text follows)")
        chars = min(max_chars, len(page_text))
        print(page_text[:chars])
        return

    if json_out:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    for i, r in enumerate(results, 1):
        print(f"{i}. {r['title']}")
        print(f"   {r['url']}")
        if r["snippet"]:
            # Wrap snippet at 90 chars
            words = r["snippet"].split()
            line = "   "
            for w in words:
                if len(line) + len(w) > 92:
                    print(line)
                    line = "   " + w + " "
                else:
                    line += w + " "
            if line.strip():
                print(line)
        print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="web_search",
        description="Search the web via headless browser. Sessions are shared with browser.py.",
    )
    parser.add_argument("query",                    help="Search query")
    parser.add_argument("--engine", default="bing",
                        choices=list(ENGINES.keys()), help="Search engine (default: duckduckgo)")
    parser.add_argument("-n",       type=int, default=5, help="Number of results (default: 5)")
    parser.add_argument("--session", metavar="ID",  help="Reuse an existing browser.py session")
    parser.add_argument("--max-chars", type=int, default=3000,
                        metavar="N",                help="Max chars if falling back to raw text (default: 3000)")
    parser.add_argument("--json",   action="store_true", help="Output JSON array")
    return parser


def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    session_id = args.session or str(uuid.uuid4())[:8]
    sdir       = _session_dir(session_id)

    print(f"SESSION: {session_id}")

    do_search(
        query    = args.query,
        engine   = args.engine,
        n        = args.n,
        sdir     = sdir,
        json_out = args.json,
        max_chars= args.max_chars,
    )


if __name__ == "__main__":
    try:
        main()
    except (BrokenPipeError, KeyboardInterrupt):
        sys.exit(0)
    finally:
        try:
            sys.stdout.flush()
        except BrokenPipeError:
            pass
        try:
            sys.stderr.close()
        except Exception:
            pass
