#!/usr/bin/env bash
set -u

source "$(dirname "$0")/_lib.bash"

tmp="$(make_tmp)"
ac_home="${tmp}/.agent-crew"
repo="${tmp}/repo"

mkdir -p "${ac_home}/setup" "${ac_home}/user/agents" "${repo}/.codex/agents"
cp "${REPO_ROOT}/core/setup/common.sh" "${ac_home}/setup/common.sh"

cat >"${ac_home}/user/agents/scout.md" <<'EOF'
---
name: Scout Agent
description: Read-only scout for Codex native subagent discovery.
reasoning_tier: light
model: gpt-5.4-mini
model_reasoning_effort: medium
sandbox_mode: read-only
nickname_candidates: Scout One, Scout Two
---

# Scout Agent

Report local source evidence and do not edit files.
EOF

(
  cd "${repo}" || exit 2
  git init -q
  AGENT_CREW_HOME="${ac_home}" bash "${REPO_ROOT}/core/setup/deploy-user-agent.sh" scout.md >/dev/null
)

toml="${repo}/.codex/agents/scout-agent.toml"

it "Codex project template defines native subagent concurrency defaults"
config="$(cat "${REPO_ROOT}/adapters/codex/template/config.toml")"
assert_contains "${config}" "max_threads = 6"

it "Codex project template keeps subagent nesting shallow by default"
assert_contains "${config}" "max_depth = 1"

it "deploy-user-agent writes a regular Codex TOML custom agent"
assert_file_exists "${toml}"

it "Codex TOML includes official required name field"
out="$(cat "${toml}")"
assert_contains "${out}" 'name = "scout-agent"'

it "Codex TOML preserves official per-agent model field"
assert_contains "${out}" 'model = "gpt-5.4-mini"'

it "Codex TOML preserves official per-agent reasoning effort field"
assert_contains "${out}" 'model_reasoning_effort = "medium"'

it "Codex TOML preserves official per-agent sandbox mode field"
assert_contains "${out}" 'sandbox_mode = "read-only"'

it "Codex TOML converts comma-separated nickname candidates"
assert_contains "${out}" 'nickname_candidates = ["Scout One", "Scout Two"]'

it "Generated Codex TOML parses as valid TOML"
python3 - "${toml}" <<'PYEOF'
import ast
import re
import sys

path = sys.argv[1]

try:
    import tomllib  # type: ignore
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:
        tomllib = None

if tomllib is not None:
    with open(path, "rb") as f:
        tomllib.load(f)
    raise SystemExit(0)

# Fallback for Python < 3.11 environments without tomli. The generated Codex
# agent TOML intentionally uses a tiny subset: string fields, one string-array
# field, and a multiline developer_instructions string.
text = open(path, encoding="utf-8").read()
lines = iter(enumerate(text.splitlines(), start=1))
seen = set()

for lineno, line in lines:
    stripped = line.strip()
    if not stripped:
        continue

    if stripped == 'developer_instructions = """':
        seen.add("developer_instructions")
        for _, inner in lines:
            if inner == '"""':
                break
        else:
            raise SystemExit("unterminated developer_instructions multiline string")
        continue

    m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$', stripped)
    if not m:
        raise SystemExit(f"invalid TOML assignment at line {lineno}: {line}")

    key, value = m.group(1), m.group(2)
    seen.add(key)
    if value.startswith("["):
        parsed = ast.literal_eval(value)
        if not isinstance(parsed, list) or not all(isinstance(x, str) for x in parsed):
            raise SystemExit(f"invalid string array at line {lineno}: {line}")
    else:
        parsed = ast.literal_eval(value)
        if not isinstance(parsed, str):
            raise SystemExit(f"invalid string value at line {lineno}: {line}")

required = {"name", "description", "developer_instructions"}
missing = required - seen
if missing:
    raise SystemExit(f"missing required keys: {sorted(missing)}")
PYEOF
assert_exit 0 $?

end_report
