#!/usr/bin/env python3
# description: Read and search yapflows chat history
# usage: {python} {path} <command> [options] — run with --help for full usage
"""
chat — Yapflows chat history reader CLI.

WHEN TO USE:
- Review past conversations and context
- Search through chat history for specific topics
- Find previous solutions or discussions
- Get conversation statistics

Commands:
  list     Browse sessions
  read     Show a conversation
  search   Grep across chats
  stats    Usage overview
  recent   Quick shorthand for list --last N
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data dir + loading
# ---------------------------------------------------------------------------

def get_data_dir() -> Path:
    env = os.environ.get("USER_DIR")
    if env:
        return Path(env)
    base = Path.home() / "yapflows"
    settings = base / "settings.json"
    if settings.exists():
        try:
            data = json.loads(settings.read_text())
            custom = data.get("data_dir") or data.get("base_dir")
            if custom:
                return Path(custom)
        except Exception:
            pass
    return base


def load_sessions(data_dir: Path) -> list[dict]:
    chats_dir = data_dir / "chats"
    if not chats_dir.exists():
        return []
    sessions = []
    for f in chats_dir.glob("*.json"):
        try:
            s = json.loads(f.read_text())
            sessions.append(s)
        except Exception:
            pass
    return sessions


def parse_since(since: str) -> datetime:
    """Parse --since value: 30m / 2h / 3d / 1w / ISO date."""
    now = datetime.now(timezone.utc)
    m = re.fullmatch(r"(\d+)([mhdw])", since)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {"m": timedelta(minutes=n), "h": timedelta(hours=n),
                 "d": timedelta(days=n), "w": timedelta(weeks=n)}[unit]
        return now - delta
    # ISO date
    try:
        dt = datetime.fromisoformat(since)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        sys.exit(f"Invalid --since value: {since!r}. Use 30m, 2h, 3d, 1w, or YYYY-MM-DD.")


def parse_dt(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

USE_COLOR = sys.stdout.isatty()

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"
BLUE   = "\033[34m"
MAGENTA = "\033[35m"
RED    = "\033[31m"


def c(code: str, text: str) -> str:
    return f"{code}{text}{RESET}" if USE_COLOR else text


def fmt_dt(ts: str | None) -> str:
    dt = parse_dt(ts)
    if not dt:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# Session filtering helpers
# ---------------------------------------------------------------------------

def filter_sessions(
    sessions: list[dict],
    *,
    since: str | None = None,
    last: int | None = None,
    agent: str | None = None,
    source: str | None = None,
    archived: bool = False,
    only_archived: bool = False,
    unread: bool = False,
    sticky: bool = False,
) -> list[dict]:
    result = sessions

    if only_archived:
        result = [s for s in result if s.get("archived")]
    elif not archived:
        result = [s for s in result if not s.get("archived")]

    if agent:
        result = [s for s in result if s.get("agent_id") == agent]
    if source:
        result = [s for s in result if s.get("source") == source]
    if unread:
        result = [s for s in result if s.get("unread")]
    if sticky:
        result = [s for s in result if s.get("sticky")]

    if since:
        cutoff = parse_since(since)
        result = [s for s in result if (parse_dt(s.get("updated_at")) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff]

    # Sort by updated_at desc
    result.sort(key=lambda s: s.get("updated_at") or "", reverse=True)

    if last is not None:
        result = result[:last]

    return result


def resolve_session(sessions: list[dict], id_or_alias: str) -> dict | None:
    """Find session by exact id prefix or alias (case-insensitive)."""
    alias_lower = id_or_alias.lower()
    for s in sessions:
        if s.get("id", "").startswith(id_or_alias):
            return s
        if (s.get("alias") or "").lower() == alias_lower:
            return s
    return None


# ---------------------------------------------------------------------------
# Message rendering
# ---------------------------------------------------------------------------

def render_tool_call(tc: dict, indent: str = "  ") -> list[str]:
    lines = []
    tool_name = tc.get("tool", "tool")
    inp = tc.get("input")
    out = tc.get("output") or ""
    err = tc.get("error") or ""

    # Input: bash commands are stored as {"__arg1": "cmd"} or plain dict
    if isinstance(inp, dict):
        cmd = inp.get("__arg1") or inp.get("command") or inp.get("cmd")
        if cmd:
            inp_str = str(cmd)
        elif inp:
            inp_str = json.dumps(inp, ensure_ascii=False)
        else:
            inp_str = ""
    else:
        inp_str = str(inp) if inp else ""

    header = c(DIM, f"{indent}[{tool_name}]")
    if inp_str:
        header += c(DIM, f" {inp_str[:120]}")
    lines.append(header)

    if out:
        for line in out.splitlines()[:10]:
            lines.append(c(DIM, f"{indent}  {line}"))
        if len(out.splitlines()) > 10:
            lines.append(c(DIM, f"{indent}  … ({len(out.splitlines())} lines)"))
    if err:
        lines.append(c(RED, f"{indent}  ERROR: {err[:200]}"))
    return lines


def render_message(msg: dict, *, no_tools: bool = False, role_filter: str | None = None) -> list[str]:
    role = msg.get("role", "")
    if role_filter and role != role_filter:
        return []

    lines = []
    ts = fmt_dt(msg.get("timestamp"))
    if role == "user":
        header = c(GREEN, f"[user]") + c(DIM, f" {ts}")
    else:
        header = c(CYAN, f"[assistant]") + c(DIM, f" {ts}")
    lines.append(header)

    content = msg.get("content") or ""
    if content:
        for line in content.splitlines():
            lines.append(f"  {line}")

    if not no_tools:
        for tc in msg.get("tool_calls") or []:
            lines.extend(render_tool_call(tc))

    return lines


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace, sessions: list[dict]) -> None:
    filtered = filter_sessions(
        sessions,
        since=args.since,
        last=args.last,
        agent=args.agent,
        source=args.source,
        archived=args.archived,
        only_archived=args.only_archived,
        unread=args.unread,
        sticky=args.sticky,
    )

    if args.json:
        print(json.dumps(filtered, ensure_ascii=False, indent=2))
        return

    if args.ids:
        for s in filtered:
            print(s.get("id", ""))
        return

    if not filtered:
        print("No sessions found.")
        return

    col_id    = 14
    col_dt    = 17
    col_agent = 14
    col_src   = 10

    header = (
        c(BOLD, f"{'SESSION_ID':<{col_id}}")
        + "  "
        + c(BOLD, f"{'UPDATED':<{col_dt}}")
        + "  "
        + c(BOLD, f"{'AGENT':<{col_agent}}")
        + "  "
        + c(BOLD, f"{'SOURCE':<{col_src}}")
        + "  "
        + c(BOLD, "TITLE")
    )
    print(header)
    print(c(DIM, "-" * 80))

    for s in filtered:
        sid     = (s.get("id") or "")[:col_id]
        updated = fmt_dt(s.get("updated_at"))[:col_dt]
        agent   = (s.get("agent_id") or "—")[:col_agent]
        source  = (s.get("source") or "—")[:col_src]
        title   = s.get("title") or "Untitled"
        alias   = s.get("alias")

        title_str = title[:60]
        if alias:
            title_str = c(YELLOW, f"[{alias}]") + " " + title_str
        if s.get("sticky"):
            title_str = c(MAGENTA, "* ") + title_str
        if s.get("unread"):
            title_str = c(GREEN, "● ") + title_str

        row = (
            c(CYAN, f"{sid:<{col_id}}")
            + "  "
            + f"{updated:<{col_dt}}"
            + "  "
            + f"{agent:<{col_agent}}"
            + "  "
            + f"{source:<{col_src}}"
            + "  "
            + title_str
        )
        print(row)


def cmd_read(args: argparse.Namespace, sessions: list[dict]) -> None:
    session = resolve_session(sessions, args.id_or_alias)
    if not session:
        sys.exit(f"Session not found: {args.id_or_alias!r}")

    if args.json:
        print(json.dumps(session, ensure_ascii=False, indent=2))
        return

    messages = session.get("messages") or []
    if args.tail:
        messages = messages[-args.tail:]

    if not args.raw:
        sid   = session.get("id", "")
        title = session.get("title") or "Untitled"
        agent = session.get("agent_id") or "—"
        env   = session.get("environment_id") or "—"
        alias = session.get("alias")
        print(c(BOLD, f"{'─'*60}"))
        print(c(BOLD, f"  {title}"))
        alias_str = f"  alias: {alias}" if alias else ""
        print(c(DIM, f"  id: {sid}  agent: {agent}  env: {env}{alias_str}"))
        print(c(BOLD, f"{'─'*60}"))

    for msg in messages:
        lines = render_message(
            msg,
            no_tools=args.no_tools,
            role_filter=args.role,
        )
        if not lines:
            continue
        if args.raw:
            content = msg.get("content") or ""
            if content:
                print(content)
        else:
            for line in lines:
                print(line)
            print()


def cmd_search(args: argparse.Namespace, sessions: list[dict]) -> None:
    filtered = filter_sessions(
        sessions,
        since=args.since,
        last=args.last,
        agent=args.agent,
    )

    flags = re.IGNORECASE if args.i else 0
    try:
        pattern = re.compile(args.pattern, flags)
    except re.error as e:
        sys.exit(f"Invalid regex: {e}")

    results: list[dict] = []

    for session in filtered:
        session_matches: list[dict] = []

        for msg in session.get("messages") or []:
            role = msg.get("role", "")
            if args.role and role != args.role:
                continue

            hit_content = False
            hit_tools = False

            content = msg.get("content") or ""
            if pattern.search(content):
                hit_content = True

            tool_matches = []
            if not args.no_tools:
                for tc in msg.get("tool_calls") or []:
                    tc_text = ""
                    inp = tc.get("input")
                    if isinstance(inp, dict):
                        tc_text += json.dumps(inp)
                    elif inp:
                        tc_text += str(inp)
                    tc_text += " " + (tc.get("output") or "")
                    tc_text += " " + (tc.get("error") or "")
                    if pattern.search(tc_text):
                        hit_tools = True
                        tool_matches.append(tc)

            if hit_content or hit_tools:
                session_matches.append({
                    "msg": msg,
                    "hit_content": hit_content,
                    "tool_matches": tool_matches,
                })

        if session_matches:
            results.append({"session": session, "matches": session_matches})

    if args.json:
        out = []
        for r in results:
            s = r["session"]
            out.append({
                "id": s.get("id"),
                "title": s.get("title"),
                "agent_id": s.get("agent_id"),
                "updated_at": s.get("updated_at"),
                "match_count": len(r["matches"]),
                "matches": [
                    {
                        "role": m["msg"].get("role"),
                        "timestamp": m["msg"].get("timestamp"),
                        "content_snippet": m["msg"].get("content", "")[:200] if m["hit_content"] else None,
                    }
                    for m in r["matches"]
                ],
            })
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    if not results:
        print(f"No matches for: {args.pattern!r}")
        return

    ctx = args.C or 0

    for r in results:
        s = r["session"]
        sid   = s.get("id", "")[:14]
        title = s.get("title") or "Untitled"

        if args.session_only:
            print(c(CYAN, sid) + "  " + title)
            continue

        print(c(BOLD, f"── {title} ") + c(DIM, f"[{sid}]"))

        for m in r["matches"]:
            msg = m["msg"]
            role = msg.get("role", "")
            ts   = fmt_dt(msg.get("timestamp"))
            role_color = GREEN if role == "user" else CYAN
            print(c(role_color, f"  [{role}]") + c(DIM, f" {ts}"))

            if m["hit_content"]:
                content = msg.get("content") or ""
                _print_context(content, pattern, ctx)

            for tc in m["tool_matches"]:
                tool_name = tc.get("tool", "tool")
                inp = tc.get("input")
                if isinstance(inp, dict):
                    inp_str = json.dumps(inp)
                else:
                    inp_str = str(inp) if inp else ""
                full_text = inp_str + " " + (tc.get("output") or "")
                print(c(DIM, f"    [{tool_name}]"))
                _print_context(full_text, pattern, ctx, indent="    ")

        print()


def _print_context(text: str, pattern: re.Pattern, ctx: int, indent: str = "  ") -> None:
    lines = text.splitlines()
    printed = set()
    for i, line in enumerate(lines):
        if pattern.search(line):
            start = max(0, i - ctx)
            end   = min(len(lines), i + ctx + 1)
            for j in range(start, end):
                if j not in printed:
                    prefix = ">" if j == i else " "
                    highlighted = pattern.sub(lambda m: c(YELLOW + BOLD, m.group()), lines[j]) if USE_COLOR else lines[j]
                    print(f"{indent}{prefix} {highlighted}")
                    printed.add(j)
            if ctx and i + ctx + 1 < len(lines):
                print(c(DIM, f"{indent}  ---"))


def cmd_stats(args: argparse.Namespace, sessions: list[dict]) -> None:
    filtered = sessions
    if args.since:
        cutoff = parse_since(args.since)
        filtered = [s for s in filtered if (parse_dt(s.get("updated_at")) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff]

    total_sessions  = len(filtered)
    total_messages  = 0
    total_tools     = 0
    archived_count  = sum(1 for s in filtered if s.get("archived"))
    sticky_count    = sum(1 for s in filtered if s.get("sticky"))
    by_agent: dict[str, int] = {}
    by_source: dict[str, int] = {}
    by_env: dict[str, int] = {}

    for s in filtered:
        agent = s.get("agent_id") or "unknown"
        source = s.get("source") or "unknown"
        env = s.get("environment_id") or "unknown"
        by_agent[agent] = by_agent.get(agent, 0) + 1
        by_source[source] = by_source.get(source, 0) + 1
        by_env[env] = by_env.get(env, 0) + 1

        for msg in s.get("messages") or []:
            total_messages += 1
            total_tools += len(msg.get("tool_calls") or [])

    if args.json:
        print(json.dumps({
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "total_tool_calls": total_tools,
            "archived": archived_count,
            "sticky": sticky_count,
            "by_agent": by_agent,
            "by_source": by_source,
            "by_environment": by_env,
        }, indent=2))
        return

    print(c(BOLD, "Yapflows Stats"))
    if args.since:
        print(c(DIM, f"  Since: {args.since}"))
    print()
    print(f"  Sessions:    {c(CYAN, str(total_sessions))}")
    print(f"  Messages:    {c(CYAN, str(total_messages))}")
    print(f"  Tool calls:  {c(CYAN, str(total_tools))}")
    print(f"  Archived:    {archived_count}")
    print(f"  Sticky:      {sticky_count}")

    if by_agent:
        print()
        print(c(BOLD, "  By agent:"))
        for k, v in sorted(by_agent.items(), key=lambda x: -x[1]):
            print(f"    {k:<20} {v}")

    if by_source:
        print()
        print(c(BOLD, "  By source:"))
        for k, v in sorted(by_source.items(), key=lambda x: -x[1]):
            print(f"    {k:<20} {v}")

    if by_env:
        print()
        print(c(BOLD, "  By environment:"))
        for k, v in sorted(by_env.items(), key=lambda x: -x[1]):
            print(f"    {k:<20} {v}")


def cmd_send(args: argparse.Namespace) -> None:
    import urllib.request
    import urllib.error

    port = int(os.environ.get("YAPFLOWS_PORT", "8000"))
    url = f"http://localhost:{port}/api/sessions/by-alias/{args.id_or_alias}/append"
    payload = json.dumps({"content": args.content}).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print("ok" if resp.status == 200 else f"Error {resp.status}")
    except urllib.error.HTTPError as e:
        sys.exit(f"Error {e.code}: {e.read().decode()}")
    except Exception as e:
        sys.exit(f"Error: {e}")


def cmd_recent(args: argparse.Namespace, sessions: list[dict]) -> None:
    n = args.n if args.n else 10
    filtered = filter_sessions(sessions, last=n)

    if not filtered:
        print("No sessions found.")
        return

    for s in filtered:
        sid   = (s.get("id") or "")[:14]
        title = s.get("title") or "Untitled"
        updated = fmt_dt(s.get("updated_at"))
        agent = s.get("agent_id") or "—"

        # First user message preview
        preview = ""
        for msg in s.get("messages") or []:
            if msg.get("role") == "user":
                preview = (msg.get("content") or "").replace("\n", " ")[:80]
                break

        print(c(CYAN, sid) + "  " + c(DIM, updated) + "  " + c(BOLD, title[:40]))
        if preview:
            print(c(DIM, f"  {preview}"))
        print()


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yap",
        description="Read and search yapflows chat history.",
    )

    subs = parser.add_subparsers(dest="command", metavar="COMMAND")
    subs.required = True

    # --- list ---
    p_list = subs.add_parser("list", help="Browse sessions")
    p_list.add_argument("--since",        help="Only sessions updated since (30m, 2h, 3d, 1w, or ISO date)")
    p_list.add_argument("--last",         type=int, default=20, metavar="N", help="Max results (default 20)")
    p_list.add_argument("--agent",        help="Filter by agent_id")
    p_list.add_argument("--source",       help="Filter by source (manual, task, telegram, …)")
    p_list.add_argument("--archived",     action="store_true", help="Include archived sessions")
    p_list.add_argument("--only-archived",action="store_true", help="Show only archived sessions")
    p_list.add_argument("--unread",       action="store_true", help="Show only unread sessions")
    p_list.add_argument("--sticky",       action="store_true", help="Show only sticky sessions")
    p_list.add_argument("--json",         action="store_true", help="Output JSON")
    p_list.add_argument("--ids",          action="store_true", help="Print only session IDs")

    # --- read ---
    p_read = subs.add_parser("read", help="Show a conversation")
    p_read.add_argument("id_or_alias",    help="Session ID (or prefix) or alias")
    p_read.add_argument("--tail",         type=int, metavar="N", help="Show only last N messages")
    p_read.add_argument("--no-tools",     action="store_true", help="Hide tool calls")
    p_read.add_argument("--role",         choices=["user", "assistant"], help="Show only messages of this role")
    p_read.add_argument("--json",         action="store_true", help="Output raw session JSON")
    p_read.add_argument("--raw",          action="store_true", help="Plain text content only (pipeable)")

    # --- search ---
    p_search = subs.add_parser("search", help="Grep across chats")
    p_search.add_argument("pattern",      help="Regex pattern")
    p_search.add_argument("-i",           action="store_true", help="Case-insensitive")
    p_search.add_argument("-C",           type=int, default=0, metavar="N", help="Context lines around match")
    p_search.add_argument("--role",       choices=["user", "assistant"], help="Restrict to role")
    p_search.add_argument("--no-tools",   action="store_true", help="Exclude tool calls from search")
    p_search.add_argument("--since",      help="Only sessions updated since (30m, 2h, 3d, 1w, or ISO date)")
    p_search.add_argument("--last",       type=int, metavar="N", help="Max sessions to search")
    p_search.add_argument("--agent",      help="Filter by agent_id")
    p_search.add_argument("--session-only", action="store_true", help="Report only session titles, not lines")
    p_search.add_argument("--json",       action="store_true", help="Output JSON")

    # --- stats ---
    p_stats = subs.add_parser("stats", help="Usage overview")
    p_stats.add_argument("--since",       help="Only sessions updated since")
    p_stats.add_argument("--json",        action="store_true", help="Output JSON")

    # --- send ---
    p_send = subs.add_parser("send", help="Append an assistant message to a session by alias")
    p_send.add_argument("id_or_alias",    help="Session ID (or prefix) or alias")
    p_send.add_argument("content",        help="Message content to append")

    # --- recent ---
    p_recent = subs.add_parser("recent", help="Quick list with preview (alias for list --last N)")
    p_recent.add_argument("n",            type=int, nargs="?", default=10, help="Number of sessions (default 10)")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    data_dir = get_data_dir()
    sessions = load_sessions(data_dir)

    if args.command == "list":
        cmd_list(args, sessions)
    elif args.command == "read":
        cmd_read(args, sessions)
    elif args.command == "search":
        cmd_search(args, sessions)
    elif args.command == "stats":
        cmd_stats(args, sessions)
    elif args.command == "send":
        cmd_send(args)
    elif args.command == "recent":
        cmd_recent(args, sessions)


if __name__ == "__main__":
    try:
        main()
    except (BrokenPipeError, KeyboardInterrupt):
        sys.exit(0)
    finally:
        # Suppress Python's "Exception ignored" message when piped to head/tail
        try:
            sys.stdout.flush()
        except BrokenPipeError:
            pass
        try:
            sys.stderr.close()
        except Exception:
            pass
