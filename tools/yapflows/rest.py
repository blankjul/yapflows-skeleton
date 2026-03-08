#!/usr/bin/env python3
# description: Yapflows HTTP API client — call any endpoint; run with no args to explore the full schema
# usage: {python} {path} [METHOD /path [key=value ...]] — omit METHOD to use GET; omit all args to list API
"""
yapflows — Yapflows API proxy CLI.

WHEN TO USE:
- First run with no args to learn the full API schema
- Then call any endpoint: yapflows POST /tasks name=daily cron='0 9 * * *' ...
- All operations go through the HTTP API (server must be running)

Commands:
  (no args)         Print full API schema
  METHOD /path      Forward HTTP call (GET, POST, PUT, PATCH, DELETE)
  /path             Shorthand for GET /path
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

USE_COLOR = sys.stdout.isatty()

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
GREEN   = "\033[32m"
CYAN    = "\033[36m"
YELLOW  = "\033[33m"
BLUE    = "\033[34m"
MAGENTA = "\033[35m"
RED     = "\033[31m"


def c(code: str, text: str) -> str:
    return f"{code}{text}{RESET}" if USE_COLOR else text


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def get_base_url() -> str:
    port = int(os.environ.get("YAPFLOWS_PORT", "8000"))
    return f"http://localhost:{port}"


# ---------------------------------------------------------------------------
# Value coercion
# ---------------------------------------------------------------------------

def coerce(s: str) -> bool | int | float | dict | list | str:
    """Auto-coerce a string value to the most appropriate Python type."""
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    # Try integer
    try:
        return int(s)
    except ValueError:
        pass
    # Try float
    try:
        return float(s)
    except ValueError:
        pass
    # Try JSON object/array
    stripped = s.strip()
    if stripped and stripped[0] in "{[":
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    return s


def parse_kvs(args: list[str]) -> dict:
    """Parse key=value pairs into a dict with coerced values."""
    result = {}
    for arg in args:
        if "=" not in arg:
            sys.exit(f"Invalid argument (expected key=value): {arg!r}")
        key, _, val = arg.partition("=")
        result[key.strip()] = coerce(val)
    return result


# ---------------------------------------------------------------------------
# URL building
# ---------------------------------------------------------------------------

# Paths that should NOT get the /api prefix
_NO_API_PREFIX = {"/health", "/openapi.json", "/docs", "/redoc"}
_NO_API_PREFIX_STARTS = ("/setup/", "/api/")


def build_path(path: str) -> str:
    """Apply /api prefix logic."""
    if path in _NO_API_PREFIX:
        return path
    for prefix in _NO_API_PREFIX_STARTS:
        if path.startswith(prefix):
            return path
    return f"/api{path}"


def build_url(base: str, path: str, params: dict, method: str) -> str:
    """Build the full URL, appending query string for GET requests."""
    full_path = build_path(path)
    url = base + full_path
    if method == "GET" and params:
        url += "?" + urllib.parse.urlencode(
            {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
             for k, v in params.items()}
        )
    return url


# ---------------------------------------------------------------------------
# HTTP request
# ---------------------------------------------------------------------------

def http_request(method: str, url: str, body: dict | None) -> tuple[int, object]:
    """Execute an HTTP request and return (status, parsed_json)."""
    body_bytes = None
    headers = {}
    if body is not None and method != "GET":
        body_bytes = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        url,
        data=body_bytes,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw.decode(errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw.decode(errors="replace")
    except urllib.error.URLError as e:
        sys.exit(f"Connection error: {e.reason}")


# ---------------------------------------------------------------------------
# Result printing
# ---------------------------------------------------------------------------

def print_result(status: int, data: object, *, raw: bool = False) -> None:
    """Pretty-print the response. Exits with code 1 on non-2xx."""
    is_error = not (200 <= status < 300)
    if isinstance(data, str):
        out = data
    elif raw or not USE_COLOR:
        out = json.dumps(data)
    else:
        out = json.dumps(data, indent=2, ensure_ascii=False)

    if is_error:
        print(out, file=sys.stderr)
        sys.exit(1)
    else:
        print(out)


# ---------------------------------------------------------------------------
# Discovery: fetch OpenAPI and print grouped schema
# ---------------------------------------------------------------------------

def _schema_type(schema: dict) -> str:
    """Return a short type description for a JSON Schema node."""
    if not schema:
        return "any"
    # anyOf/oneOf — pick the first non-null variant (FastAPI nullable fields)
    any_of = schema.get("anyOf") or schema.get("oneOf")
    if any_of:
        non_null = [s for s in any_of if s.get("type") != "null"]
        return _schema_type(non_null[0]) if non_null else "any"
    t = schema.get("type", "")
    fmt = schema.get("format", "")
    enum = schema.get("enum")
    if enum:
        return "/".join(str(e) for e in enum)
    if t == "array":
        items = schema.get("items", {})
        return f"[{_schema_type(items)}]"
    if t == "object":
        return "object"
    if fmt:
        return fmt
    return t or "any"


def _resolve_ref(ref: str, components: dict) -> dict:
    """Resolve a simple $ref like '#/components/schemas/Foo'."""
    parts = ref.lstrip("#/").split("/")
    node = components
    for p in parts[1:]:  # parts[0] is "components"; node is already that dict
        node = node.get(p, {})
    return node


def _extract_params(schema_node: dict, components: dict) -> list[dict]:
    """
    Flatten a request body schema into a list of param dicts:
    [{"name": str, "required": bool, "type": str, "default": any}]
    """
    if not schema_node:
        return []

    # Resolve $ref
    if "$ref" in schema_node:
        schema_node = _resolve_ref(schema_node["$ref"], components)

    props = schema_node.get("properties", {})
    required = set(schema_node.get("required", []))
    result = []
    for name, prop in props.items():
        if "$ref" in prop:
            prop = _resolve_ref(prop["$ref"], components)
        result.append({
            "name": name,
            "required": name in required,
            "type": _schema_type(prop),
            "default": prop.get("default"),
        })
    return result


def _group_tag(path: str, tags: list[str]) -> str:
    if tags:
        return tags[0].upper()
    # Derive from path: /api/tasks/... → TASKS
    parts = [p for p in path.strip("/").split("/") if p and p != "api"]
    return parts[0].upper() if parts else "OTHER"


def cmd_discover(base: str) -> None:
    """Fetch /openapi.json and print a rich, agent-readable schema."""
    status, data = http_request("GET", base + "/openapi.json", None)
    if not isinstance(data, dict):
        sys.exit("Could not parse OpenAPI schema.")

    title   = data.get("info", {}).get("title", "Yapflows API")
    version = data.get("info", {}).get("version", "")
    paths   = data.get("paths", {})
    components = data.get("components", {})

    METHODS = ["get", "post", "put", "patch", "delete"]

    # Group routes by tag
    groups: dict[str, list[tuple[str, str, dict]]] = {}  # tag → [(method, path, op)]
    for path, path_item in paths.items():
        for method in METHODS:
            op = path_item.get(method)
            if op is None:
                continue
            tags = op.get("tags", [])
            group = _group_tag(path, tags)
            groups.setdefault(group, []).append((method.upper(), path, op))

    # Header
    ver_str = f"  v{version}" if version else ""
    print(c(BOLD, f"{title}{ver_str}  ({base})"))
    print(c(DIM,  "Run: yapflows METHOD /path [key=value ...]"))
    print(c(DIM,  "     yapflows /path           (GET shorthand)"))
    print(c(DIM,  "     yapflows                 (show this schema)"))
    print()

    for group, routes in sorted(groups.items()):
        print(c(BOLD + CYAN, group))
        for method, path, op in routes:
            summary = op.get("summary") or op.get("description") or ""
            # Trim /api prefix for display
            display_path = path
            if display_path.startswith("/api"):
                display_path = display_path[4:]

            method_color = {
                "GET":    GREEN,
                "POST":   YELLOW,
                "PUT":    BLUE,
                "PATCH":  MAGENTA,
                "DELETE": RED,
            }.get(method, "")

            method_str = c(method_color, f"{method:<7}")
            path_padded = f"{display_path:<35}"
            print(f"  {method_str} {c(BOLD, path_padded)}  {summary}")

            # Parameters from request body
            body_content = op.get("requestBody", {}).get("content", {})
            schema_node = (
                body_content.get("application/json", {}).get("schema", {})
            )
            params = _extract_params(schema_node, components)
            if params:
                required_params = [p for p in params if p["required"]]
                optional_params = [p for p in params if not p["required"]]

                for p in required_params:
                    ptype = c(DIM, f"({p['type']})")
                    print(f"           {c(BOLD, p['name']+'*')} {ptype}")

                for p in optional_params:
                    ptype = c(DIM, f"({p['type']})")
                    default_str = ""
                    if p["default"] is not None:
                        default_str = c(DIM, f"  default: {json.dumps(p['default'])}")
                    print(f"           {p['name']} {ptype}{default_str}")

            # Query parameters
            query_params = [
                qp for qp in op.get("parameters", [])
                if qp.get("in") == "query"
            ]
            if query_params:
                for qp in query_params:
                    qschema = qp.get("schema", {})
                    qtype   = c(DIM, f"({_schema_type(qschema)})")
                    req_mark = "*" if qp.get("required") else ""
                    print(f"           ?{qp['name']}{req_mark} {qtype}")

        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

KNOWN_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}


def main() -> None:
    args = sys.argv[1:]

    # Strip --raw flag
    raw_output = False
    if "--raw" in args:
        raw_output = True
        args = [a for a in args if a != "--raw"]

    base = get_base_url()

    # No args → discovery
    if not args:
        cmd_discover(base)
        return

    # Parse METHOD and PATH
    method = "GET"
    if args[0].upper() in KNOWN_METHODS:
        method = args[0].upper()
        args = args[1:]

    if not args:
        sys.exit("Usage: yapflows [METHOD] /path [key=value ...]")

    path = args[0]
    if not path.startswith("/"):
        sys.exit(f"Path must start with /: {path!r}")
    kv_args = args[1:]

    params = parse_kvs(kv_args) if kv_args else {}

    url = build_url(base, path, params, method)
    body = params if method != "GET" and params else None

    status, data = http_request(method, url, body)
    print_result(status, data, raw=raw_output)


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
