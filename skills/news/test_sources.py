#!/usr/bin/env python3
"""Test which news sources are fetchable and return usable content."""

import sys
import re
import subprocess

SOURCES = [
    ("Hacker News",     "https://news.ycombinator.com/"),
    ("Reddit r/news",   "https://www.reddit.com/r/news/top/?t=day"),
    ("Reddit r/world",  "https://www.reddit.com/r/worldnews/top/?t=day"),
    ("BBC",             "https://www.bbc.com/news"),
    ("CNN",             "https://www.cnn.com"),
    ("Tagesschau",      "https://www.tagesschau.de"),
    ("ARD",             "https://www.ard.de"),
    ("Reuters",         "https://www.reuters.com"),
    ("Guardian",        "https://www.theguardian.com"),
    ("NYT",             "https://www.nytimes.com"),
    ("Der Spiegel",     "https://www.spiegel.de"),
    ("Zeit Online",     "https://www.zeit.de"),
]

def fetch(url):
    result = subprocess.run(
        [sys.executable, "/home/blankjul/.yapflows/tools/web_fetch.py", url, "--max-chars", "5000"],
        capture_output=True, text=True, timeout=30
    )
    return result.stdout + result.stderr

def count_links(text):
    return len(re.findall(r'\[.{10,}\]\(https?://', text))

def main():
    print(f"{'Source':<20} {'Status':<10} {'Links':<8} {'Chars':<8} Notes")
    print("-" * 70)
    for name, url in SOURCES:
        try:
            out = fetch(url)
            chars = len(out)
            links = count_links(out)
            blocked = any(kw in out.lower() for kw in ["captcha", "unusual traffic", "robot", "access denied", "blocked", "403", "enable javascript"])
            if blocked:
                status = "BLOCKED"
            elif chars < 500:
                status = "EMPTY"
            elif links < 3:
                status = "FEW"
            else:
                status = "OK"
            note = out[:80].replace('\n', ' ').strip() if status in ("EMPTY", "BLOCKED") else f"{links} links found"
            print(f"{name:<20} {status:<10} {links:<8} {chars:<8} {note}")
        except Exception as e:
            print(f"{name:<20} {'ERROR':<10} {'?':<8} {'?':<8} {e}")

if __name__ == "__main__":
    main()
