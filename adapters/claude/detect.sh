#!/usr/bin/env bash
set -euo pipefail

[ -n "${CLAUDECODE:-}" ] || [ -n "${CLAUDE_SESSION_ID:-}" ] || [ -n "${CLAUDE_MODEL:-}" ]
