#!/usr/bin/env bash
# Resolve PPQ.AI credentials for astro-static agents without printing secrets.
#
# Usage from generation scripts/agents:
#   source ~/.config/opencode/astro-static/phases/ppq-auth.sh
#   ppq_require_api_key || exit 1
#   curl -H "Authorization: Bearer $PPQ_API_KEY" ...
#
# Resolution order:
#   1. Existing PPQ_API_KEY environment variable
#   2. OpenCode auth store: ~/.local/share/opencode/auth.json
#   3. OpenCode config: ~/.config/opencode/opencode.json
#
# The key is exported into the current shell only. This helper never echoes the
# token value; status output includes only the credential source label.

set -euo pipefail

ppq_resolve_api_key() {
  if [ -n "${PPQ_API_KEY:-}" ]; then
    export PPQ_API_KEY
    export PPQ_API_KEY_SOURCE="env:PPQ_API_KEY"
    return 0
  fi

  local resolved
  resolved="$(python3 - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

AUTH_PATH = Path.home() / '.local/share/opencode/auth.json'
CONFIG_PATH = Path.home() / '.config/opencode/opencode.json'


def strip_jsonc(text: str) -> str:
    out: list[str] = []
    i = 0
    in_string = False
    escape = False
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ''
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == '/' and nxt == '/':
            i += 2
            while i < len(text) and text[i] not in '\r\n':
                i += 1
            continue
        if ch == '/' and nxt == '*':
            i += 2
            while i + 1 < len(text) and not (text[i] == '*' and text[i + 1] == '/'):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return ''.join(out)


def load_json(path: Path, *, jsonc: bool = False) -> Any:
    try:
        text = path.read_text()
    except OSError:
        return None
    try:
        return json.loads(strip_jsonc(text) if jsonc else text)
    except Exception:
        return None


def candidate_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or value.startswith('{') or value.startswith('$'):
        return None
    if value in os.environ:
        return os.environ.get(value) or None
    return value


def dig(obj: Any, *path: str) -> Any:
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def find_key_in_ppq_node(node: Any) -> str | None:
    if isinstance(node, str):
        return candidate_string(node)
    if not isinstance(node, dict):
        return None
    for key_name in ('key', 'apiKey', 'apikey', 'api_key', 'token', 'accessToken'):
        found = candidate_string(node.get(key_name))
        if found:
            return found
    for value in node.values():
        found = find_key_in_ppq_node(value)
        if found:
            return found
    return None


auth = load_json(AUTH_PATH)
if isinstance(auth, dict):
    for node in (
        auth.get('ppq'),
        dig(auth, 'providers', 'ppq'),
        dig(auth, 'provider', 'ppq'),
        dig(auth, 'custom', 'ppq'),
    ):
        found = find_key_in_ppq_node(node)
        if found:
            print(found)
            raise SystemExit(0)

config = load_json(CONFIG_PATH, jsonc=True)
if isinstance(config, dict):
    for value in (
        dig(config, 'provider', 'ppq', 'options', 'apiKey'),
        dig(config, 'provider', 'ppq', 'options', 'apikey'),
        dig(config, 'provider', 'ppq', 'apiKey'),
        dig(config, 'providers', 'ppq', 'options', 'apiKey'),
        dig(config, 'providers', 'ppq', 'apiKey'),
    ):
        found = candidate_string(value)
        if found:
            print(found)
            raise SystemExit(0)

raise SystemExit(1)
PY
  )" || return 1

  if [ -n "$resolved" ]; then
    export PPQ_API_KEY="$resolved"
    export PPQ_API_KEY_SOURCE="opencode"
    return 0
  fi
  return 1
}

ppq_require_api_key() {
  if ppq_resolve_api_key; then
    echo "STATUS:PPQ_AUTH_OK source=${PPQ_API_KEY_SOURCE}" >&2
    return 0
  fi
  echo "STATUS:MISSING_PPQ_API_KEY" >&2
  return 1
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  ppq_require_api_key
fi
