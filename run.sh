#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"
export PATH="/Library/TeX/texbin:$PATH"

if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
  printf '%s\n' 'Missing .venv/bin/python. Complete the environment setup in README.md first.' >&2
  exit 1
fi

exec "$APP_DIR/.venv/bin/python" "$APP_DIR/web_server.py" "$@"
