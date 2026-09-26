#!/bin/bash
# Installs the environment the AGENTS.md "Commands" checks need, in Claude Code
# on the web sessions only. Local sessions manage their own environment.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"
uv sync --locked --all-extras
