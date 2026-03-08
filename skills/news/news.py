#!/usr/bin/env python3
"""News aggregator skill for yapflows."""

import os
import re
import sys
import argparse
import subprocess
from pathlib import Path


def run_tool(tool_name, *args):
    cmd = [os.environ["PYTHON"], str(Path(os.environ["TOOLS"]) / f"{tool_name}.py")] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout + result.stderr


def _print_results(name, items, limit):
    print(f"\n{'='*50}")
    print(f"  {name}")
    print(f"{'='*50}")
    shown = 0
    for title, url in items:
        if shown >= limit:
            break
        print(f"  {shown+1}. {title}")
        if url:
            print(f"     {url}")
        shown += 1
    if shown == 0:
        print("  (no stories found)")


def fetch_hn(limit):
    out = run_tool("web/fetch", "https://news.ycombinator.com/", "--max-chars", "50000")
    # Rows: | N. |  | [Title](https://...) (domain) | ...
    pattern = re.compile(r'\|\s*\d+\.\s*\|[^|]*\|\s*\[([^\]]+)\]\((https?://[^)]+)\)')
    items = [(m.group(1).strip(), m.group(2).strip()) for m in pattern.finditer(out)]
    _print_results("Hacker News", items, limit)


def fetch_reddit(subreddit, limit):
    out = run_tool("web/fetch", f"https://www.reddit.com/r/{subreddit}/top/?t=day", "--max-chars", "50000")
    pattern = re.compile(r'\[([^\]]{15,})\]\(/r/' + re.escape(subreddit) + r'/comments/[^\s)]+\)')
    seen, items = set(), []
    for m in pattern.finditer(out):
        title = m.group(1).strip()
        if title not in seen:
            seen.add(title)
            items.append((title, f"https://www.reddit.com/r/{subreddit}/top/?t=day"))
    _print_results(f"Reddit r/{subreddit}", items, limit)


def fetch_bbc(limit):
    out = run_tool("web_fetch", "https://www.bbc.com/news", "--max-chars", "50000")
    bbc_url = r'(https?://(?:www\.bbc\.com|www\.bbc\.co\.uk)/(?:news|sport)[^\s)"]+)'
    # Pattern 1: [## Title](url)
    p1 = re.compile(r'\[(?:LIVE\s*)?#{1,3}\s*([^\]\n]{15,})[^\]]*\]' + r'\(' + bbc_url + r'\)', re.DOTALL)
    # Pattern 2: ## Title\nDescription\n](url)
    p2 = re.compile(r'#{1,3}\s+([^\n]{15,})\n[\s\S]{0,400}?\]\(' + bbc_url + r'\)')
    # Pattern 3: [Title\n...](url) where title is plain text before newline
    p3 = re.compile(r'\[([A-Z][^\]\n]{14,})\n[^\]]*\]\(' + bbc_url + r'\)')
    seen_titles, seen_urls, items = set(), set(), []
    for p in (p1, p2, p3):
        for m in p.finditer(out):
            title = re.sub(r'\s+', ' ', m.group(1)).strip()
            url = m.group(2).strip()
            if title.startswith('!') or '![' in title:
                continue
            if title not in seen_titles and url not in seen_urls:
                seen_titles.add(title)
                seen_urls.add(url)
                items.append((title, url))
    _print_results("BBC News", items, limit)


def fetch_cnn(limit):
    out = run_tool("web_fetch", "https://www.cnn.com", "--max-chars", "50000")
    # CNN uses both relative (/YYYY/MM/DD/...) and absolute URLs
    pattern = re.compile(r'\[([^\]\n]{15,})\]\(((?:https?://(?:www|edition)\.cnn\.com)?/\d{4}/\d{2}/\d{2}/[^\s)]+)\)')
    seen, items = set(), []
    for m in pattern.finditer(out):
        title = re.sub(r'\s+', ' ', m.group(1)).strip()
        url = m.group(2).strip()
        if not url.startswith('http'):
            url = "https://www.cnn.com" + url
        if '/video/' in url:
            continue
        if title not in seen:
            seen.add(title)
            items.append((title, url))
    _print_results("CNN", items, limit)


def fetch_tagesschau(limit):
    out = run_tool("web_fetch", "https://www.tagesschau.de", "--max-chars", "50000")
    # [### Title\n...](/path/article-100.html) — relative URLs
    pattern = re.compile(r'\[(?:\*\*[^*]+\*\*\s*\n)?#{1,3}\s*([^\]\n]{10,})\n?[^\]]*\]\((/[^)]+\.html)\)')
    seen, items = set(), []
    for m in pattern.finditer(out):
        title = re.sub(r'\s+', ' ', m.group(1)).strip()
        url = "https://www.tagesschau.de" + m.group(2)
        if title not in seen:
            seen.add(title)
            items.append((title, url))
    _print_results("Tagesschau", items, limit)


def fetch_guardian(limit):
    out = run_tool("web_fetch", "https://www.theguardian.com", "--max-chars", "50000")
    # [### Section\nTitle](/world/...) or [### Title](/world/...)
    pattern = re.compile(r'\[(?:#{1,3}\s*[^\n]+\n)?#{1,3}\s*([^\]\n]{15,})\]\((/(?:world|uk-news|us-news|environment|politics|sport|business|technology|science|culture|global)[^)]+)\)')
    seen, items = set(), []
    for m in pattern.finditer(out):
        title = re.sub(r'\s+', ' ', m.group(1)).strip()
        url = "https://www.theguardian.com" + m.group(2)
        if title not in seen:
            seen.add(title)
            items.append((title, url))
    _print_results("The Guardian", items, limit)


def fetch_nyt(limit):
    out = run_tool("web_fetch", "https://www.nytimes.com", "--max-chars", "50000")
    pattern = re.compile(r'\[([^\]\n]{15,})\]\((https?://www\.nytimes\.com/\d{4}/\d{2}/\d{2}/[^)]+)\)')
    seen, items = set(), []
    for m in pattern.finditer(out):
        title = re.sub(r'\s+', ' ', m.group(1)).strip()
        url = m.group(2).strip()
        if title not in seen:
            seen.add(title)
            items.append((title, url))
    _print_results("New York Times", items, limit)


def fetch_spiegel(limit):
    out = run_tool("web_fetch", "https://www.spiegel.de", "--max-chars", "50000")
    # Spiegel links: [description](url "Title") — extract title from quoted part
    pattern = re.compile(r'\[[^\]]+\]\((https?://www\.spiegel\.de/(?:ausland|politik|wirtschaft|panorama|wissenschaft|kultur|sport|netzwelt)[^\s)"]+)\s+"([^"]{10,})"\)')
    seen, items = set(), []
    for m in pattern.finditer(out):
        url = m.group(1).strip()
        title = m.group(2).strip()
        if title not in seen:
            seen.add(title)
            items.append((title, url))
    _print_results("Der Spiegel", items, limit)


def fetch_zeit(limit):
    out = run_tool("web_fetch", "https://www.zeit.de", "--max-chars", "50000")
    # Zeit links: [### Title](url "Title") — stop URL at space/quote
    pattern = re.compile(r'\[(?:#{1,3}\s*(?:[^:]+:\s*)?)?([^\]\n]{15,})\]\((https?://www\.zeit\.de/[^\s)"]+)')
    seen_titles, seen_urls, items = set(), set(), []
    for m in pattern.finditer(out):
        title = re.sub(r'\s+', ' ', m.group(1)).strip()
        url = m.group(2).strip()
        if any(x in url for x in ['/extra', '/angebote', '/campus', '/zett', '#comment']):
            continue
        if re.match(r'^[\d.,]+ Kommentare$', title):
            continue
        if title not in seen_titles and url not in seen_urls:
            seen_titles.add(title)
            seen_urls.add(url)
            items.append((title, url))
    _print_results("Zeit Online", items, limit)


SOURCES = {
    "hn":          fetch_hn,
    "reddit-news": lambda l: fetch_reddit("news", l),
    "reddit-world":lambda l: fetch_reddit("worldnews", l),
    "bbc":         fetch_bbc,
    "cnn":         fetch_cnn,
    "tagesschau":  fetch_tagesschau,
    "guardian":    fetch_guardian,
    "nyt":         fetch_nyt,
    "spiegel":     fetch_spiegel,
    "zeit":        fetch_zeit,
}


def main():
    parser = argparse.ArgumentParser(description="News aggregator")
    subparsers = parser.add_subparsers(dest="command")

    top_parser = subparsers.add_parser("top")
    top_parser.add_argument("--limit", type=int, default=10)
    top_parser.add_argument("--source", choices=list(SOURCES.keys()), help="Fetch one source only")

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("query", nargs="+")

    args = parser.parse_args()

    if args.command == "top":
        sources = [args.source] if args.source else list(SOURCES.keys())
        for name in sources:
            SOURCES[name](args.limit)

    elif args.command == "search":
        query = " ".join(args.query)
        print(f"🔍 Searching: {query}")
        for engine in ("bing", "duckduckgo", "google"):
            out = run_tool("web/search", query, "--engine", engine)
            if "no structured results" not in out and "unusual traffic" not in out and len(out) > 200:
                print(out[:2000])
                break
            print(f"  ({engine} blocked, trying next...)")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
