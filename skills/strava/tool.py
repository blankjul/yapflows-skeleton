#!/usr/bin/env python3
# description: Read Strava activities, athlete profile, and activity details
# usage: {python} {path} <command> [options] — run with --help for full usage
"""
strava — Strava API CLI for yapflows agents.

Commands:
  auth        OAuth2 setup via VNC browser (extracts credentials + authorizes)
  activities  List recent activities
  activity    Get full details for a specific activity
  athlete     Get your athlete profile
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKILL_DIR = Path(__file__).parent
ENV_FILE = SKILL_DIR / ".env"

STRAVA_BASE_URL = "https://www.strava.com/api/v3"
TOKEN_URL = "https://www.strava.com/oauth/token"
AUTH_BASE_URL = "https://www.strava.com/oauth/authorize"
STRAVA_SETTINGS_URL = "https://www.strava.com/settings/api"
REDIRECT_PORT = 8765
SCOPE = "activity:read_all"


# ---------------------------------------------------------------------------
# .env helpers
# ---------------------------------------------------------------------------

def _parse_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env


def _load_env() -> dict[str, str]:
    """Load global ~/.yapflows/.env then skill .env (local overrides global)."""
    global_env = _parse_env_file(Path(os.environ["USER_DIR"]) / ".env")
    local_env = _parse_env_file(ENV_FILE)
    return {**global_env, **local_env}


def _save_env(env: dict[str, str]) -> None:
    lines = [f"{k}={v}" for k, v in env.items()]
    ENV_FILE.write_text("\n".join(lines) + "\n")


def _get(key: str, env: dict | None = None) -> str:
    if env is None:
        env = _load_env()
    return env.get(key, "")


def _set_tokens(access_token: str, refresh_token: str, expires_at: int) -> None:
    env = _load_env()
    env["STRAVA_ACCESS_TOKEN"] = access_token
    env["STRAVA_REFRESH_TOKEN"] = refresh_token
    env["STRAVA_EXPIRES_AT"] = str(expires_at)
    _save_env(env)


def _get_credentials() -> tuple[str, str]:
    env = _load_env()
    client_id = _get("STRAVA_CLIENT_ID", env)
    client_secret = _get("STRAVA_CLIENT_SECRET", env)
    if not client_id or not client_secret:
        sys.exit(
            f"Error: Strava credentials not configured.\n"
            f"Run: python {__file__} auth\n"
            f"Or add STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET to {ENV_FILE}"
        )
    return client_id, client_secret


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _tokens_expired() -> bool:
    expires_at = int(_get("STRAVA_EXPIRES_AT") or 0)
    return time.time() >= expires_at - 300


def _refresh_tokens() -> str:
    import httpx
    client_id, client_secret = _get_credentials()
    refresh_token = _get("STRAVA_REFRESH_TOKEN")
    if not refresh_token:
        sys.exit("Error: Not authenticated. Run: python {__file__} auth")
    resp = httpx.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    })
    resp.raise_for_status()
    data = resp.json()
    _set_tokens(data["access_token"], data["refresh_token"], data["expires_at"])
    return data["access_token"]


def _access_token() -> str:
    token = _get("STRAVA_ACCESS_TOKEN")
    if not token:
        sys.exit(f"Error: Not authenticated. Run: python {__file__} auth")
    if _tokens_expired():
        token = _refresh_tokens()
    return token


# ---------------------------------------------------------------------------
# API helper
# ---------------------------------------------------------------------------

def _api_get(path: str, params: dict | None = None) -> dict | list:
    import httpx

    def _do(token: str) -> httpx.Response:
        return httpx.get(
            f"{STRAVA_BASE_URL}{path}",
            params=params or {},
            headers={"Authorization": f"Bearer {token}"},
        )

    resp = _do(_access_token())

    if resp.status_code == 401:
        resp = _do(_refresh_tokens())

    if resp.status_code == 429:
        sys.exit("Error: Strava API rate limit exceeded. Try again later.")

    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Auth flow
# ---------------------------------------------------------------------------

def _run_browser(subcommand: str, *args: str) -> str:
    cmd = [os.environ["PYTHON"], str(Path(os.environ["TOOLS"]) / "web" / "browser.py"), subcommand, *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.stdout + result.stderr


def _extract_credentials_from_browser() -> tuple[str, str]:
    import re
    print("  Navigating to Strava API settings page...")
    text = _run_browser("navigate", STRAVA_SETTINGS_URL)

    m = re.search(r'Client ID\s*\n+(\d+)', text)
    if not m:
        sys.exit(
            "Error: Could not find Client ID on Strava settings page.\n"
            "Make sure you are logged into Strava in the VNC browser.\n"
            f"See {SKILL_DIR}/assets/signup.md for setup instructions."
        )
    client_id = m.group(1).strip()
    print(f"  Found Client ID: {client_id}")

    secret_m = re.search(r'Client Secret\s*\n+([a-f0-9]{40})', text)
    if not secret_m:
        print("  Secret hidden — clicking Show...")
        text = _run_browser("click", 'a[data-field="client_secret"]')
        secret_m = re.search(r'Client Secret\s*\n+([a-f0-9]{40})', text)

    if not secret_m:
        sys.exit(
            f"Error: Could not extract Client Secret.\n"
            f"Add STRAVA_CLIENT_SECRET manually to {ENV_FILE}"
        )
    client_secret = secret_m.group(1).strip()
    print(f"  Found Client Secret: {client_secret[:6]}...")
    return client_id, client_secret


def cmd_auth(_args: argparse.Namespace) -> None:
    import httpx

    print("=== Strava Auth ===")

    # Step 1: credentials
    env = _load_env()
    client_id = env.get("STRAVA_CLIENT_ID", "")
    client_secret = env.get("STRAVA_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        print("\n[1/4] Extracting credentials from Strava settings page...")
        client_id, client_secret = _extract_credentials_from_browser()
        env["STRAVA_CLIENT_ID"] = client_id
        env["STRAVA_CLIENT_SECRET"] = client_secret
        _save_env(env)
        print(f"  Saved to {ENV_FILE}")
    else:
        print(f"\n[1/4] Using existing credentials (client_id={client_id})")

    # Step 2: callback server
    print(f"\n[2/4] Starting OAuth callback server on port {REDIRECT_PORT}...")
    code_result: list[str] = []
    server_ready = threading.Event()

    def run_server():
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                params = parse_qs(urlparse(self.path).query)
                if "code" in params:
                    code_result.append(params["code"][0])
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"<h2>Strava auth complete! You can close this tab.</h2>")
                else:
                    code_result.append("")
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"<h2>Auth error</h2>")

            def log_message(self, format, *args):
                pass

        server = HTTPServer(("localhost", REDIRECT_PORT), Handler)
        server.timeout = 120
        server_ready.set()
        server.handle_request()
        server.server_close()

    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    server_ready.wait(timeout=5)

    # Step 3: navigate browser to auth URL
    auth_url = AUTH_BASE_URL + "?" + urlencode({
        "client_id": client_id,
        "redirect_uri": f"http://localhost:{REDIRECT_PORT}/callback",
        "response_type": "code",
        "approval_prompt": "force",
        "scope": SCOPE,
    })
    print("\n[3/4] Opening Strava authorization page in VNC browser...")
    _run_browser("navigate", auth_url)

    print("  Clicking Authorize...")
    try:
        httpx.post(
            "http://localhost:8000/api/browser/click",
            json={"selector": 'input[type="submit"], button.btn-primary, a.btn-primary'},
            timeout=15,
        )
    except Exception:
        pass

    t.join(timeout=30)
    if not code_result or not code_result[0]:
        sys.exit("Error: Did not receive auth code. Try re-running auth.")

    # Step 4: exchange code for tokens
    print("\n[4/4] Exchanging auth code for tokens...")
    resp = httpx.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code_result[0],
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    data = resp.json()
    _set_tokens(data["access_token"], data["refresh_token"], data["expires_at"])

    athlete = data.get("athlete") or {}
    name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
    print(json.dumps({
        "status": "authenticated",
        "athlete": name or "unknown",
        "env": str(ENV_FILE),
    }, indent=2))


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def _strip_maps(obj: dict | list) -> dict | list:
    if isinstance(obj, list):
        return [_strip_maps(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _strip_maps(v) for k, v in obj.items() if k != "map"}
    return obj


def cmd_activities(args: argparse.Namespace) -> None:
    params: dict = {"per_page": args.limit}
    if args.before:
        params["before"] = args.before
    if args.after:
        params["after"] = args.after
    print(json.dumps(_strip_maps(_api_get("/athlete/activities", params)), indent=2))


def cmd_activity(args: argparse.Namespace) -> None:
    print(json.dumps(_strip_maps(_api_get(f"/activities/{args.id}")), indent=2))


def cmd_athlete(_args: argparse.Namespace) -> None:
    print(json.dumps(_api_get("/athlete"), indent=2))


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="strava",
        description="Strava API CLI for yapflows agents.",
    )
    subs = parser.add_subparsers(dest="command", metavar="COMMAND")
    subs.required = True

    subs.add_parser("auth", help="OAuth2 setup via VNC browser")

    p_acts = subs.add_parser("activities", help="List recent activities")
    p_acts.add_argument("--limit", type=int, default=30, metavar="N")
    p_acts.add_argument("--before", type=int, metavar="UNIX_TS")
    p_acts.add_argument("--after", type=int, metavar="UNIX_TS")

    p_act = subs.add_parser("activity", help="Get full details for a specific activity")
    p_act.add_argument("id", help="Activity ID")

    subs.add_parser("athlete", help="Get your athlete profile")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "auth":
        cmd_auth(args)
    elif args.command == "activities":
        cmd_activities(args)
    elif args.command == "activity":
        cmd_activity(args)
    elif args.command == "athlete":
        cmd_athlete(args)


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
