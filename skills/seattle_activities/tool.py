#!/usr/bin/env python3
# description: Search Seattle Parks & Recreation activities at any community center
# usage: $PYTHON $SKILLS/seattle_activities/tool.py search [options]
r"""
seattle_activities — Browse Seattle Parks & Recreation activity registrations.

Uses the logged-in browser to load and parse activities.

## URL parameters (all filters applied server-side via URL)

  time_after_str=HH:MM   — 24h start time  (e.g. 17:00 for 5pm)
  time_before_str=HH:MM  — 24h end time
  activity_keyword=TEXT  — keyword search
  site_ids=ID            — community center ID (10 = Green Lake CC)
  min_age=N / max_age=N  — age range
  viewMode=list

## Lazy loading — "View more" button
The page loads 20 activities at a time.
Strategy: click "View more" repeatedly until the pagination text disappears.

## Activity card structure (inner_text per card)
  [status badge]          ← optional: "Full" / "N space(s) left" / "In progress" / "New"
  Activity Name
  #ID/age range/Openings N
  Location
  Date range              ← "Month D, YYYY to Month D, YYYY"
  Days + time             ← "Mon,Wed 5:45 PM - 6:45 PM"
  $price
  [Enroll Now / Full / View Registration Info]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

BASE_URL = "https://anc.apm.activecommunities.com/seattle/activity/search"
DEFAULT_SITE = "10"   # Green Lake Community Center

# site_ids from the WHERE filter (scraped 2026-03-08)
SITES: dict[str, str] = {
    "Alki Bathhouse": "47",
    "Alki Community Center": "49",
    "Amy Yee Tennis Center": "3",
    "Ballard Community Center": "4",
    "Ballard High School Playfield": "64",
    "Ballard Playfield": "5",
    "Ballard Pool": "27",
    "Bitter Lake Community Center": "6",
    "Camp Long Environmental Learning Center": "7",
    "Carkeek Environmental Learning Center": "84",
    "Carkeek Park": "114",
    "Colman Pool": "88",
    "Cowen Park": "158",
    "Dakota Place Park": "136",
    "Delridge Community Center": "28",
    "Delridge Playfield": "165",
    "Discovery Park": "197",
    "Evans Pool": "500",
    "Garfield Community Center": "8",
    "Garfield Teen Life Center": "147",
    "Genesee Park and Playfield": "236",
    "Golden Gardens Park": "9",
    "Green Lake Community Center": "10",
    "Green Lake Playfield": "12",
    "Green Lake Small Craft Center": "150",
    "Hiawatha Community Center": "163",
    "High Point Community Center": "132",
    "International District/Chinatown C.C.": "23",
    "Japanese Garden": "167",
    "Jefferson Community Center": "172",
    "Jefferson Park": "173",
    "Lake City Community Center": "193",
    "Laurelhurst Community Center": "264",
    "Lincoln Park": "281",
    "Lower Woodland Playfield": "14",
    "Loyal Heights Community Center": "25",
    "Madison Pool": "307",
    "Magnolia Community Center": "317",
    "Magnolia Playfield": "321",
    "Magnuson Park": "15",
    "Magnuson Community Center": "346",
    "Meadowbrook Community Center": "225",
    "Meadowbrook Pool": "238",
    "Medgar Evers Pool": "16",
    "Miller Community Center": "29",
    "Miller Playfield": "255",
    "Montlake Community Center": "278",
    "Montlake Playfield": "279",
    "Mounger Pool": "17",
    "Mount Baker Park": "282",
    "Mount Baker Rowing & Sailing Center": "18",
    "Northgate Community Center": "304",
    "Queen Anne Community Center": "30",
    "Queen Anne Playfield": "19",
    "Queen Anne Pool": "427",
    "Rainier Beach Pool & Community Center": "20",
    "Rainier Community Center": "24",
    "Ravenna Park": "444",
    "Ravenna-Eckstein Community Center": "445",
    "Seward Park": "21",
    "South Park Community Center": "373",
    "Southwest Pool": "374",
    "Van Asselt Community Center": "388",
    "Washington Park Arboretum": "434",
    "Yesler Community Center": "399",
}

BADGES = {"Full", "New", "In progress", "Enroll Now", "View Registration Info",
          "On waitlist", "Add to waitlist"}
ID_RE = re.compile(r'^#\d+/')


class BrowserError(Exception):
    pass


# ---------------------------------------------------------------------------
# Browser helpers
# ---------------------------------------------------------------------------

def _python() -> str:
    return os.environ.get("PYTHON", sys.executable)

def _browser_tool() -> str:
    tools = os.environ.get("TOOLS", "")
    if not tools:
        sys.exit("Error: $TOOLS env var not set")
    return str(Path(tools) / "web" / "browser.py")

def _run_browser(*args: str, max_chars: int = 3000, required: bool = True) -> str:
    result = subprocess.run(
        [_python(), _browser_tool(), *args, "--max-chars", str(max_chars)],
        capture_output=True, text=True, timeout=30,
    )
    out = result.stdout.strip()
    if not out and result.returncode != 0:
        msg = f"Error: browser failed: {result.stderr.strip()}"
        if required:
            sys.exit(msg)
        raise BrowserError(msg)
    lines = out.splitlines()
    if lines and lines[0].startswith("VNC viewer"):
        out = "\n".join(lines[1:])
    return out

def _navigate(url: str, max_chars: int = 3000) -> str:
    return _run_browser("navigate", url, max_chars=max_chars)

def _click(selector: str, max_chars: int = 500) -> str:
    return _run_browser("click", selector, max_chars=max_chars)

def _get_text(max_chars: int = 3000) -> str:
    return _run_browser("get_text", max_chars=max_chars)

def _evaluate(expression: str) -> object:
    """Run JS in the browser and return the parsed JSON result."""
    result = subprocess.run(
        [_python(), _browser_tool(), "evaluate", expression],
        capture_output=True, text=True, timeout=30,
    )
    out = result.stdout.strip()
    if not out and result.returncode != 0:
        raise BrowserError(f"evaluate failed: {result.stderr.strip()}")
    lines = out.splitlines()
    if lines and lines[0].startswith("VNC viewer"):
        out = "\n".join(lines[1:])
    return json.loads(out)

def _load_all_activities() -> str:
    """Click 'View more' until all results are loaded, return full page text."""
    for _ in range(20):  # safety limit
        text = _get_text(max_chars=500000)
        m = re.search(r'viewed \d+ out of \d+ results', text)
        if not m:
            break
        _click("text=View more")
        time.sleep(1)
    return _get_text(max_chars=500000)


def _extract_links() -> dict[str, str]:
    """Return {activity_number: url} by reading card name-links from the DOM."""
    JS = (
        "Object.fromEntries("
        "  Array.from(document.querySelectorAll('.activity-card-info__name-link a'))"
        "  .map(a => {"
        "    const m = (a.getAttribute('aria-label') || '').match(/Activity number (\\d+)/);"
        "    return m ? [m[1], a.href] : null;"
        "  })"
        "  .filter(Boolean)"
        ")"
    )
    try:
        return _evaluate(JS) or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Site lookup
# ---------------------------------------------------------------------------

def _resolve_site(where: str) -> str:
    """Resolve --where to a site_ids value. Accepts ID or partial name (case-insensitive)."""
    if where.isdigit():
        return where
    needle = where.lower()
    matches = [(name, sid) for name, sid in SITES.items() if needle in name.lower()]
    if not matches:
        print(f"Unknown location: {where!r}\nRun `list-sites` to see available locations.", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        options = "\n".join(f"  {name} (id={sid})" for name, sid in matches)
        print(f"Ambiguous location {where!r}, matches:\n{options}", file=sys.stderr)
        sys.exit(1)
    return matches[0][1]


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _parse_activities(text: str, links: dict[str, str] | None = None) -> list[dict]:
    """Parse activity cards from page text. Anchors on ^#ID/ lines."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    activities = []
    i = 0
    while i < len(lines):
        if ID_RE.match(lines[i]):
            meta  = lines[i]
            parts = meta.split("/")
            act_id   = parts[0]
            age      = parts[1].strip() if len(parts) > 1 else ""
            openings = parts[-1].strip() if len(parts) > 2 else ""

            # Title: first non-badge line looking back
            name = ""
            for k in range(i - 1, max(-1, i - 4), -1):
                if lines[k] not in BADGES and not ID_RE.match(lines[k]):
                    name = lines[k]
                    break

            # Look forward for location, dates, schedule, price
            location = lines[i + 1] if i + 1 < len(lines) else ""
            dates    = lines[i + 2] if i + 2 < len(lines) else ""
            schedule = lines[i + 3] if i + 3 < len(lines) else ""
            price    = lines[i + 4] if i + 4 < len(lines) else ""

            # Status badge: line before title
            status = ""
            if i >= 2 and (lines[i - 2] in BADGES or re.search(r'\d+ space\(s\) left', lines[i - 2])):
                status = lines[i - 2]

            numeric_id = act_id.lstrip("#")
            url = (links or {}).get(numeric_id, "")
            activities.append({
                "name":      name,
                "id":        act_id,
                "url":       url,
                "age":       age,
                "openings":  openings,
                "location":  location,
                "dates":     dates,
                "schedule":  schedule,
                "price":     price,
                "status":    status,
                "available": "Openings 0" not in openings and "Full" not in status,
            })
        i += 1
    return activities


# ---------------------------------------------------------------------------
# Time parsing
# ---------------------------------------------------------------------------

def _to_24h(t: str) -> str | None:
    """Convert '5pm', '5:30pm', '17:00' → 'HH:MM'. Returns None on failure."""
    t = t.strip()
    m = re.match(r'^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$', t, re.IGNORECASE)
    if not m:
        return None
    hour = int(m.group(1))
    mins = int(m.group(2) or 0)
    ampm = (m.group(3) or "").lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    return f"{hour:02d}:{mins:02d}"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_search(args: argparse.Namespace) -> None:
    site_id = _resolve_site(args.where) if args.where else args.site

    params = f"onlineSiteId=0&site_ids={site_id}&viewMode=list"
    if args.name:
        params += f"&activity_keyword={quote(args.name)}"
    if args.after:
        t = _to_24h(args.after)
        if t:
            params += f"&time_after_str={quote(t)}"
    if args.before:
        t = _to_24h(args.before)
        if t:
            params += f"&time_before_str={quote(t)}"
    if args.min_age is not None:
        params += f"&min_age={args.min_age}"
    if args.max_age is not None:
        params += f"&max_age={args.max_age}"

    _navigate(f"{BASE_URL}?{params}")
    text = _load_all_activities()
    links = _extract_links()
    activities = _parse_activities(text, links)
    if args.available:
        activities = [a for a in activities if a["available"]]

    # Resolve site name for output
    site_name = next((n for n, sid in SITES.items() if sid == site_id), site_id)

    print(json.dumps({
        "total": len(activities),
        "filters": {
            "site": site_name,
            "name": args.name,
            "after": args.after,
            "before": args.before,
            "min_age": args.min_age,
            "max_age": args.max_age,
            "available_only": args.available,
        },
        "activities": activities,
    }, indent=2))


def _parse_detail(text: str) -> dict:
    """Parse an activity detail page into structured fields."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    def _between(start_kw: str, *stop_kws: str) -> list[str]:
        result, inside = [], False
        for line in lines:
            if not inside and start_kw.lower() in line.lower():
                inside = True
                continue
            if inside:
                if any(s.lower() in line.lower() for s in stop_kws):
                    break
                result.append(line)
        return result

    # Find key fields by label → next line pattern
    def _field(label: str) -> str:
        for i, line in enumerate(lines):
            if line.strip().lower() == label.lower() and i + 1 < len(lines):
                return lines[i + 1]
        return ""

    description = " ".join(_between("Description", "Keyboard shortcuts", "Activity meeting dates",
                                    "More Information", "Instructor", "Supervisor"))

    SKIP = {"we're sorry", "sorry!", "please contact", "please click", "skip to"}
    name = next(
        (l for l in lines
         if l and l[0].isupper() and len(l) > 3 and ">" not in l
         and not any(s in l.lower() for s in SKIP)
         and l not in {"Activity search", "Activity detail", "Go Back"}),
        ""
    )

    return {
        "name":               name,
        "description":        description,
        "meeting_dates":      _between("Activity meeting dates", "More Information", "Instructor", "Supervisor", "Registration dates"),
        "instructor":         _between("Instructor", "More Information", "Supervisor", "Number of sessions"),
        "supervisor":         _field("Supervisor"),
        "num_sessions":       _field("Number of sessions"),
        "registration_dates": _between("Registration dates", "Free", "View fee", "Enroll", "Share"),
    }


def cmd_detail(args: argparse.Namespace) -> None:
    url = args.url
    if re.match(r'^#?\d+$', url):
        # Registration number given — look it up via keyword search to get the correct URL
        numeric = url.lstrip("#")
        _navigate(f"{BASE_URL}?onlineSiteId=0&viewMode=list&activity_keyword={numeric}")
        links = _extract_links()
        url = links.get(numeric, "")
        if not url:
            sys.exit(
                f"Error: could not find activity #{numeric}. "
                "Try running search first and passing the 'url' field directly."
            )

    text = _navigate(url, max_chars=10000)
    detail = _parse_detail(text)

    # Grab name directly from DOM (more reliable than text parsing)
    try:
        name = _evaluate("document.querySelector('[data-qa-id=\"activity-detail-general-name\"]')?.innerText?.trim() || ''")
        if name:
            detail["name"] = name
    except Exception:
        pass

    detail["url"] = url
    print(json.dumps(detail, indent=2))


def cmd_list_sites(_args: argparse.Namespace) -> None:
    rows = sorted(SITES.items())
    print(json.dumps([{"id": sid, "name": name} for name, sid in rows], indent=2))


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="seattle_activities",
        description="Search Seattle Parks & Recreation activity registrations.",
    )
    subs = parser.add_subparsers(dest="command", metavar="COMMAND")
    subs.required = True

    p = subs.add_parser("search", help="Search activities")
    p.add_argument("--where", default=None, metavar="LOCATION",
                   help="Community center name or ID (default: Green Lake CC). "
                        "Partial name match supported. Run list-sites for all options.")
    p.add_argument("--site", default=DEFAULT_SITE,
                   help=argparse.SUPPRESS)  # legacy, use --where
    p.add_argument("--name", default=None, help="Filter by activity name/keyword")
    p.add_argument("--after", default=None, metavar="TIME",
                   help="Activities starting at or after this time (e.g. '5pm', '17:00')")
    p.add_argument("--before", default=None, metavar="TIME",
                   help="Activities starting before this time (e.g. '9pm', '21:00')")
    p.add_argument("--min-age", type=int, default=None, metavar="N",
                   help="Minimum age")
    p.add_argument("--max-age", type=int, default=None, metavar="N",
                   help="Maximum age")
    p.add_argument("--available", action="store_true",
                   help="Only show activities with open spots")

    pd = subs.add_parser("detail", help="Fetch full details for one activity (description, instructor, schedule, etc.)")
    pd.add_argument("url", help="Activity URL from the 'url' field in search output. "
                                "Note: the activity registration number (#87591) cannot be used here — "
                                "it differs from the internal ID in the URL. Always use the url from search.")

    subs.add_parser("list-sites", help="List all available community centers with their IDs")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "search":
        cmd_search(args)
    elif args.command == "detail":
        cmd_detail(args)
    elif args.command == "list-sites":
        cmd_list_sites(args)


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
