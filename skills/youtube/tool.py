#!/usr/bin/env python3
# description: Browse YouTube — search, video details, channel feeds, homepage, and personal feed
# usage: $PYTHON $SKILLS/youtube/tool.py <command> [options] — run with --help for full usage
"""
youtube — YouTube CLI for yapflows agents. Uses the logged-in browser (no API key required).

Commands:
  search     Search YouTube videos
  video      Get details for a specific video
  channel    Latest videos from a channel
  homepage   Your personalised YouTube homepage
  feed       Latest videos from your saved channels
  channels   List/add/remove saved channels
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKILL_DIR = Path(__file__).parent
CHANNELS_FILE = SKILL_DIR / "channels.jsonl"

# Lines that are navigation chrome, not video content
_UI_NOISE = {
    "Skip navigation", "Create", "Home", "Shorts", "Subscriptions", "You",
    "All", "Videos", "Unwatched", "Watched", "Recently uploaded", "Live",
    "Playlists", "Filters", "Subscribe", "Join", "Now playing", "New",
    "4K", "CC", "HD", "Sponsored", "Watch", "Sign up", "Download",
    "Latest", "Popular", "Oldest", "Posts", "Store", "Search", "Share",
    "Ask", "Save", "Like", "Dislike", "Clip", "Thanks", "More",
}

_DURATION_RE = re.compile(r'^\d{1,2}:\d{2}(?::\d{2})?$')
_VIEWS_RE    = re.compile(r'^([\d,.]+[KMBkm]?)\s+views$', re.IGNORECASE)
_AGO_RE      = re.compile(r'^.+\s+ago$', re.IGNORECASE)
_SUBS_RE     = re.compile(r'^([\d,.]+[KMBkm]?)\s+subscribers$', re.IGNORECASE)
_PROGRESS_RE = re.compile(r'^\d+:\d+\s*/\s*\d+:\d+$')
_VIEWS_AGE_RE = re.compile(r'^([\d,.]+[KMBkm]?)\s+views\s+(.+?\bago\b)', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Browser helper
# ---------------------------------------------------------------------------

def _browse(url: str, max_chars: int = 8000) -> str:
    python = os.environ.get("PYTHON", sys.executable)
    tools = os.environ.get("TOOLS", "")
    if not tools:
        sys.exit("Error: $TOOLS env var not set")
    result = subprocess.run(
        [python, str(Path(tools) / "web" / "browser.py"), "navigate", url, "--max-chars", str(max_chars)],
        capture_output=True, text=True, timeout=30,
    )
    output = result.stdout.strip()
    if not output and result.returncode != 0:
        sys.exit(f"Error: browser failed: {result.stderr.strip()}")
    # Strip the VNC viewer header line if present
    lines = output.splitlines()
    if lines and lines[0].startswith("VNC viewer"):
        output = "\n".join(lines[1:])
    return output


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_video_list(text: str, limit: int = 20) -> list[dict]:
    """
    Parse a list of videos from a channel, search, or homepage.
    Handles two age formats:
      - Channel/search: views line then age on next line
      - Homepage:       views line, then "•", then age line
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    results = []
    i = 0
    while i < len(lines) and len(results) < limit:
        if _VIEWS_RE.match(lines[i]):
            views = lines[i]
            # Collect substantive lines before views (skip noise/duration/bullets)
            preceding = []
            for k in range(i - 1, max(-1, i - 8), -1):
                ln = lines[k]
                if ln in _UI_NOISE or ln == "•" or _DURATION_RE.match(ln):
                    continue
                if len(ln) > 120:
                    continue
                preceding.append(ln)
                if len(preceding) == 2:
                    break
            # If two substantive lines found: [channel, title] (closest first)
            # If only one: it's the title
            if len(preceding) >= 2:
                title = preceding[1]   # farther back = title
                channel_name = preceding[0]  # closer = channel
            elif preceding:
                title = preceding[0]
                channel_name = ""
            else:
                title = channel_name = ""
            # Age: next line (or skip "•" separator on homepage)
            age = ""
            for j in range(i + 1, min(i + 3, len(lines))):
                if lines[j] == "•":
                    continue
                if _AGO_RE.match(lines[j]):
                    age = lines[j]
                break
            if title and title not in _UI_NOISE:
                entry: dict = {"title": title, "views": views, "age": age}
                if channel_name:
                    entry["channel"] = channel_name
                results.append(entry)
        i += 1
    return results


def _parse_video_detail(text: str) -> dict:
    """
    Parse a YouTube video watch page.
    Key pattern: progress bar line (0:00 / 3:32), then title, then channel.
    Views+age appear together: "1.7B views  16 years ago"
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    title = channel = subscribers = views = age = ""
    description_lines: list[str] = []
    found_views = False

    for i, line in enumerate(lines):
        if _PROGRESS_RE.match(line) and not title:
            if i + 1 < len(lines):
                title = lines[i + 1]
            if i + 2 < len(lines):
                channel = lines[i + 2]
        elif _SUBS_RE.match(line) and not subscribers:
            subscribers = line
        elif not found_views:
            m = _VIEWS_AGE_RE.match(line)
            if m:
                views = m.group(1) + " views"
                age = m.group(2).strip()
                found_views = True
                # Collect description from following lines
                for desc_line in lines[i + 1: i + 8]:
                    if desc_line in _UI_NOISE or _VIEWS_RE.match(desc_line):
                        break
                    description_lines.append(desc_line)

    return {
        "title": title,
        "channel": channel,
        "subscribers": subscribers,
        "views": views,
        "age": age,
        "description": " ".join(description_lines)[:400],
    }


def _parse_channel_header(text: str) -> dict:
    """Extract channel name, handle, subscribers from top of channel page."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    name = handle = subscribers = ""
    for line in lines[:30]:
        if line.startswith("@") and not handle:
            handle = line
        elif _SUBS_RE.match(line) and not subscribers:
            subscribers = line
        elif not name and line not in _UI_NOISE and not line.startswith("VNC") and len(line) > 2:
            # First substantive line after nav is usually channel name
            if handle or subscribers:
                pass  # already past header
            elif not any(c in line for c in ["http", "://", "Skip"]):
                name = line
    return {"name": name, "handle": handle, "subscribers": subscribers}


# ---------------------------------------------------------------------------
# Channels file helpers
# ---------------------------------------------------------------------------

def _load_channels() -> list[dict]:
    if not CHANNELS_FILE.exists():
        return []
    channels = []
    for line in CHANNELS_FILE.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                channels.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return channels


def _save_channels(channels: list[dict]) -> None:
    CHANNELS_FILE.write_text("\n".join(json.dumps(c) for c in channels) + "\n")


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_search(args: argparse.Namespace) -> None:
    query = "+".join(args.query)
    url = f"https://www.youtube.com/results?search_query={query}"
    text = _browse(url)
    videos = _parse_video_list(text, limit=args.limit)
    print(json.dumps({"query": " ".join(args.query), "results": videos}, indent=2))


def cmd_video(args: argparse.Namespace) -> None:
    url = args.url if args.url.startswith("http") else f"https://www.youtube.com/watch?v={args.url}"
    text = _browse(url)
    print(json.dumps(_parse_video_detail(text), indent=2))


def cmd_channel(args: argparse.Namespace) -> None:
    handle = args.url.lstrip("@")
    url = args.url if args.url.startswith("http") else f"https://www.youtube.com/@{handle}"
    videos_url = url.rstrip("/") + "/videos"
    text = _browse(videos_url)
    header = _parse_channel_header(text)
    videos = _parse_video_list(text, limit=args.limit)
    print(json.dumps({"channel": header, "videos": videos}, indent=2))




def cmd_feed(args: argparse.Namespace) -> None:
    channels = _load_channels()
    if not channels:
        sys.exit(
            "No channels in feed yet.\n"
            "Add channels with: $PYTHON $SKILLS/youtube/tool.py channels add <url> --name \"Name\" --reason \"why\""
        )
    results = []
    for entry in channels:
        url = entry.get("url", "")
        if not url:
            continue
        videos_url = url.rstrip("/") + "/videos"
        try:
            text = _browse(videos_url, max_chars=5000)
            videos = _parse_video_list(text, limit=5)
            results.append({"channel": entry.get("name") or url, "url": videos_url, "videos": videos})
        except Exception as e:
            print(f"Warning: failed to fetch {url}: {e}", file=sys.stderr)
    print(json.dumps(results, indent=2))


def cmd_homepage(args: argparse.Namespace) -> None:
    text = _browse("https://www.youtube.com", max_chars=10000)
    videos = _parse_video_list(text, limit=args.limit)
    print(json.dumps({"videos": videos}, indent=2))


def cmd_channels(args: argparse.Namespace) -> None:
    channels = _load_channels()
    if args.action == "list" or not args.action:
        print(json.dumps(channels, indent=2) if channels else "No channels saved yet.")
    elif args.action == "add":
        url = args.value
        if any(c["url"] == url for c in channels):
            print(f"Already saved: {url}")
        else:
            import datetime
            entry = {"url": url, "name": args.name or "", "reason": args.reason or "", "added": datetime.date.today().isoformat()}
            channels.append(entry)
            _save_channels(channels)
            print(json.dumps(entry, indent=2))
    elif args.action == "remove":
        url = args.value
        before = len(channels)
        channels = [c for c in channels if c["url"] != url]
        if len(channels) == before:
            sys.exit(f"Not found: {url}")
        _save_channels(channels)
        print(f"Removed: {url}")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="youtube",
        description="YouTube CLI — uses the logged-in browser, no API key required.",
    )
    subs = parser.add_subparsers(dest="command", metavar="COMMAND")
    subs.required = True

    p_search = subs.add_parser("search", help="Search YouTube videos")
    p_search.add_argument("query", nargs="+")
    p_search.add_argument("--limit", type=int, default=10)

    p_video = subs.add_parser("video", help="Get details for a specific video")
    p_video.add_argument("url", help="YouTube URL or video ID")

    p_channel = subs.add_parser("channel", help="Latest videos from a channel")
    p_channel.add_argument("url", help="Channel URL or @handle")
    p_channel.add_argument("--limit", type=int, default=20)

    p_homepage = subs.add_parser("homepage", help="Your personalised YouTube homepage")
    p_homepage.add_argument("--limit", type=int, default=20)

    subs.add_parser("feed", help="Latest videos from saved channels")

    p_ch = subs.add_parser("channels", help="Manage saved channels")
    p_ch.add_argument("action", nargs="?", choices=["list", "add", "remove"], default="list")
    p_ch.add_argument("value", nargs="?", help="Channel URL (for add/remove)")
    p_ch.add_argument("--name", help="Display name (for add)")
    p_ch.add_argument("--reason", help="Why this channel is interesting (for add)")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "search": cmd_search,
        "video": cmd_video,
        "channel": cmd_channel,
        "homepage": cmd_homepage,
        "feed": cmd_feed,
        "channels": cmd_channels,
    }
    dispatch[args.command](args)


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
