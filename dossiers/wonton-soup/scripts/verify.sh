#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_python="$repo_root/.venv/bin/python"

if [[ ! -x "$venv_python" ]]; then
  echo "[wonton-soup] missing venv interpreter: $venv_python" >&2
  exit 1
fi

bootstrap_check() {
  local module="$1"
  local stdout_file stderr_file pid rc

  stdout_file="$(mktemp)"
  stderr_file="$(mktemp)"

  "$venv_python" -S -c "import ${module}; print('ok')" >"$stdout_file" 2>"$stderr_file" &
  pid=$!

  for _ in {1..50}; do
    if ! kill -0 "$pid" 2>/dev/null; then
      break
    fi
    sleep 0.1
  done

  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
    rm -f "$stdout_file" "$stderr_file"
    echo "[wonton-soup] verification bootstrap failed: importing ${module} timed out after 5s" >&2
    exit 1
  fi

  if wait "$pid"; then
    :
  else
    rc=$?
    if [[ -s "$stderr_file" ]]; then
      cat "$stderr_file" >&2
    fi
    rm -f "$stdout_file" "$stderr_file"
    echo "[wonton-soup] verification bootstrap failed: importing ${module} exited ${rc}" >&2
    exit "$rc"
  fi

  rm -f "$stdout_file" "$stderr_file"
}

cd "$repo_root"
bootstrap_check contextvars
bootstrap_check decimal

"$repo_root/.venv/bin/ruff" check .
"$repo_root/.venv/bin/ty" check .
"$repo_root/.venv/bin/python" -m pytest
