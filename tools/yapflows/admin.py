#!/usr/bin/env python3
# description: Local yapflows admin — skills and env management, no server required; reads YAPFLOWS_DIR directly
# usage: {python} {path} <command> [options] — run with --help for full usage
"""
yapflows-local — Local yapflows CLI (no server required).

Commands:
  skills list          List all available skills
  skills read <name>   Print fully rendered SKILL.md (env vars substituted)
  env                  Show merged global + local env vars
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Env loading
# ---------------------------------------------------------------------------

YAPFLOWS_DIR = Path(os.environ.get("USER_DIR", Path.home() / "yapflows"))
GLOBAL_ENV_FILE = YAPFLOWS_DIR / ".env"


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


def load_env(skill_dir: Path | None = None) -> dict[str, str]:
    """Merge global .env then skill .env (local overrides global)."""
    env = _parse_env_file(GLOBAL_ENV_FILE)
    if skill_dir:
        env.update(_parse_env_file(skill_dir / ".env"))
    return env


def render(text: str, env: dict[str, str]) -> str:
    """Substitute {VAR} placeholders. Leaves unresolved placeholders as-is."""
    try:
        return text.format_map(env)
    except (KeyError, ValueError):
        # Partial render: substitute known keys one by one
        for k, v in env.items():
            text = text.replace(f"{{{k}}}", v)
        return text


# ---------------------------------------------------------------------------
# Skills commands
# ---------------------------------------------------------------------------

def cmd_skills_list(args: argparse.Namespace) -> None:
    skills_dir = YAPFLOWS_DIR / "skills"
    if not skills_dir.exists():
        print("[]" if args.json else "No skills found.")
        return

    skills = []
    for d in sorted(skills_dir.iterdir()):
        if not d.is_dir() or not (d / "SKILL.md").exists():
            continue
        env = load_env(d)
        # First non-empty, non-heading line of SKILL.md as description
        description = ""
        for line in (d / "SKILL.md").read_text().splitlines():
            stripped = line.strip().lstrip("#").strip()
            if stripped and stripped.lower() != d.name:
                description = stripped
                break
        skills.append({"name": d.name, "description": description, "path": str(d)})

    if args.json:
        print(json.dumps(skills, indent=2))
    else:
        for s in skills:
            print(f"  {s['name']:<20} {s['description']}")


def cmd_skills_read(args: argparse.Namespace) -> None:
    skill_dir = YAPFLOWS_DIR / "skills" / args.name
    skill_md = skill_dir / "SKILL.md"

    if not skill_dir.exists():
        sys.exit(f"Error: Skill not found: {args.name!r}")
    if not skill_md.exists():
        sys.exit(f"Error: SKILL.md missing in {skill_dir}")

    env = load_env(skill_dir)
    content = render(skill_md.read_text(), env)
    print(content)


# ---------------------------------------------------------------------------
# Env command
# ---------------------------------------------------------------------------

def cmd_env(args: argparse.Namespace) -> None:
    skill_dir = YAPFLOWS_DIR / "skills" / args.skill if args.skill else None
    env = load_env(skill_dir)

    if args.json:
        print(json.dumps(env, indent=2))
    else:
        for k, v in sorted(env.items()):
            # Mask token/secret values
            if any(x in k.lower() for x in ("secret", "token", "password", "key")):
                v = v[:6] + "..." if len(v) > 6 else "***"
            print(f"  {k}={v}")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yapflows-local",
        description="Local yapflows utilities — no server required.",
    )
    subs = parser.add_subparsers(dest="command", metavar="COMMAND")
    subs.required = True

    # --- skills ---
    p_skills = subs.add_parser("skills", help="Manage skills")
    skill_subs = p_skills.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")
    skill_subs.required = True

    p_list = skill_subs.add_parser("list", help="List all available skills")
    p_list.add_argument("--json", action="store_true", help="Output JSON")

    p_read = skill_subs.add_parser("read", help="Print fully rendered SKILL.md")
    p_read.add_argument("name", help="Skill name")

    # --- env ---
    p_env = subs.add_parser("env", help="Show merged env vars")
    p_env.add_argument("--skill", metavar="NAME", help="Also merge skill .env")
    p_env.add_argument("--json", action="store_true", help="Output JSON")

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "skills":
        if args.subcommand == "list":
            cmd_skills_list(args)
        elif args.subcommand == "read":
            cmd_skills_read(args)
    elif args.command == "env":
        cmd_env(args)


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
