#!/usr/bin/env python3
# description: Full browser automation with VNC, cookies, and session support (navigate, click, screenshot, get_text)
# usage: {python} {path} --help
"""
Browser CLI for yapflows agents.

This tool calls the yapflows backend API to control a persistent browser instance.
The browser runs in the backend with VNC viewing enabled at http://localhost:6081/vnc.html

WHEN TO USE:
- Interactive websites that require JavaScript
- Sites that need login/authentication (supports cookies and sessions)
- Dynamic content that loads via AJAX/fetch
- When you need to click buttons, fill forms, or interact with the page
- Visual debugging via VNC viewer

All actions use the same global browser instance (no separate sessions).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print(
        "Error: httpx not installed.\n"
        "  pip install httpx",
        file=sys.stderr,
    )
    sys.exit(1)


BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


def _get_http_client() -> httpx.Client:
    """Get HTTP client with reasonable timeout."""
    return httpx.Client(timeout=30.0)


def action_navigate(url: str, max_chars: int) -> None:
    """Navigate to URL and print page text."""
    with _get_http_client() as client:
        try:
            response = client.post(
                f"{BACKEND_URL}/api/browser/navigate",
                json={"url": url, "max_chars": max_chars},
            )
            response.raise_for_status()
            data = response.json()

            # Print VNC URL if available (helpful for user)
            if data.get("vnc_url"):
                print(f"VNC viewer: {data['vnc_url']}", file=sys.stderr)

            # Print page text
            print(data["text"])

        except httpx.HTTPStatusError as e:
            error_detail = e.response.json().get("detail", str(e))
            print(f"Error: {error_detail}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


def action_get_text(max_chars: int) -> None:
    """Get current page text."""
    with _get_http_client() as client:
        try:
            response = client.get(
                f"{BACKEND_URL}/api/browser/text",
                params={"max_chars": max_chars},
            )
            response.raise_for_status()
            data = response.json()
            print(data["text"])

        except httpx.HTTPStatusError as e:
            error_detail = e.response.json().get("detail", str(e))
            print(f"Error: {error_detail}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


def action_click(selector: str, max_chars: int) -> None:
    """Click element and print updated page text."""
    with _get_http_client() as client:
        try:
            response = client.post(
                f"{BACKEND_URL}/api/browser/click",
                json={"selector": selector, "max_chars": max_chars},
            )
            response.raise_for_status()
            data = response.json()
            print(data["text"])

        except httpx.HTTPStatusError as e:
            error_detail = e.response.json().get("detail", str(e))
            print(f"Error: {error_detail}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


def action_fill(selector: str, value: str, max_chars: int) -> None:
    """Fill a text input and print updated page text."""
    with _get_http_client() as client:
        try:
            response = client.post(
                f"{BACKEND_URL}/api/browser/fill",
                json={"selector": selector, "value": value, "max_chars": max_chars},
            )
            response.raise_for_status()
            data = response.json()
            print(data["text"])

        except httpx.HTTPStatusError as e:
            error_detail = e.response.json().get("detail", str(e))
            print(f"Error: {error_detail}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


def action_scroll(direction: str, pixels: int, max_chars: int) -> None:
    """Scroll the page and print updated text."""
    with _get_http_client() as client:
        try:
            response = client.post(
                f"{BACKEND_URL}/api/browser/scroll",
                json={"direction": direction, "pixels": pixels, "max_chars": max_chars},
            )
            response.raise_for_status()
            data = response.json()
            print(data["text"])

        except httpx.HTTPStatusError as e:
            error_detail = e.response.json().get("detail", str(e))
            print(f"Error: {error_detail}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


def action_screenshot() -> None:
    """Take screenshot and save to scratchpad."""
    base = os.getenv("USER_DIR")
    root = Path(base).expanduser() if base else Path.home() / "yapflows"
    scratchpad = root / "scratchpad"
    scratchpad.mkdir(parents=True, exist_ok=True)

    with _get_http_client() as client:
        try:
            response = client.get(f"{BACKEND_URL}/api/browser/screenshot")
            response.raise_for_status()

            # Save screenshot
            import uuid
            screenshot_path = scratchpad / f"screenshot_{uuid.uuid4().hex[:8]}.png"
            screenshot_path.write_bytes(response.content)

            print(f"Screenshot saved: {screenshot_path}")

        except httpx.HTTPStatusError as e:
            try:
                error_detail = e.response.json().get("detail", str(e))
            except Exception:
                error_detail = str(e)
            print(f"Error: {error_detail}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


def action_evaluate(expression: str) -> None:
    """Evaluate JavaScript expression and print JSON result."""
    with _get_http_client() as client:
        try:
            response = client.post(
                f"{BACKEND_URL}/api/browser/evaluate",
                json={"expression": expression},
            )
            response.raise_for_status()
            data = response.json()
            print(json.dumps(data["result"]))

        except httpx.HTTPStatusError as e:
            error_detail = e.response.json().get("detail", str(e))
            print(f"Error: {error_detail}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


def action_status() -> None:
    """Get browser status."""
    with _get_http_client() as client:
        try:
            response = client.get(f"{BACKEND_URL}/api/browser/status")
            response.raise_for_status()
            data = response.json()

            print(json.dumps(data, indent=2))

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="browser.py",
        description=(
            "Browser automation via yapflows backend API.\n\n"
            "Controls a persistent browser instance running in the backend.\n"
            "Browser can be viewed via VNC at http://localhost:6081/vnc.html"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python browser.py navigate https://example.com\n"
            "  python browser.py get_text\n"
            "  python browser.py click 'button.submit'\n"
            "  python browser.py screenshot\n"
            "  python browser.py status\n"
        ),
    )

    sub = parser.add_subparsers(dest="action", metavar="action", required=True)

    # navigate
    p_nav = sub.add_parser(
        "navigate",
        help="Navigate to a URL and return page text.",
        description="Navigate to URL and return visible page text.",
    )
    p_nav.add_argument("url", help="URL to navigate to.")
    p_nav.add_argument(
        "--max-chars",
        type=int,
        default=3000,
        metavar="N",
        help="Max characters of page text to return (default: 3000).",
    )

    # get_text
    p_gt = sub.add_parser(
        "get_text",
        help="Return current page text.",
        description="Get the text of the currently loaded page.",
    )
    p_gt.add_argument(
        "--max-chars",
        type=int,
        default=3000,
        metavar="N",
        help="Max characters to return (default: 3000).",
    )

    # click
    p_click = sub.add_parser(
        "click",
        help="Click a CSS selector and return updated page text.",
        description="Click an element and return the updated page text.",
    )
    p_click.add_argument("selector", help="CSS selector of the element to click.")
    p_click.add_argument(
        "--max-chars",
        type=int,
        default=3000,
        metavar="N",
        help="Max characters of page text to return (default: 3000).",
    )

    # fill
    p_fill = sub.add_parser("fill", help="Fill a text input and return updated page text.")
    p_fill.add_argument("selector", help="CSS selector or text= locator of the input.")
    p_fill.add_argument("value", help="Value to type into the input.")
    p_fill.add_argument("--max-chars", type=int, default=3000, metavar="N",
                        help="Max characters of page text to return (default: 3000).")

    # scroll
    p_scroll = sub.add_parser("scroll", help="Scroll the page and return updated text.")
    p_scroll.add_argument(
        "direction",
        choices=["up", "down", "top", "bottom"],
        help="Scroll direction.",
    )
    p_scroll.add_argument(
        "--pixels", type=int, default=600,
        help="Pixels to scroll for up/down (default: 600).",
    )
    p_scroll.add_argument(
        "--max-chars", type=int, default=3000, metavar="N",
        help="Max characters of page text to return (default: 3000).",
    )

    # evaluate
    p_eval = sub.add_parser("evaluate", help="Evaluate a JavaScript expression and print the result as JSON.")
    p_eval.add_argument("expression", help="JavaScript expression to evaluate.")

    # screenshot
    sub.add_parser(
        "screenshot",
        help="Take a screenshot.",
        description="Take a screenshot and save to ~/.yapflows/scratchpad/",
    )

    # status
    sub.add_parser(
        "status",
        help="Get browser and VNC status.",
        description="Check if browser and VNC are running.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.action == "navigate":
        action_navigate(args.url, args.max_chars)
    elif args.action == "get_text":
        action_get_text(args.max_chars)
    elif args.action == "click":
        action_click(args.selector, args.max_chars)
    elif args.action == "fill":
        action_fill(args.selector, args.value, args.max_chars)
    elif args.action == "scroll":
        action_scroll(args.direction, args.pixels, args.max_chars)
    elif args.action == "evaluate":
        action_evaluate(args.expression)
    elif args.action == "screenshot":
        action_screenshot()
    elif args.action == "status":
        action_status()


if __name__ == "__main__":
    main()
