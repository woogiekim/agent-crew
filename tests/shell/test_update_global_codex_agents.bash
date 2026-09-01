#!/usr/bin/env bash
# Verify update-global-adapters refreshes and prunes ~/.codex/agents.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

TMP=$(make_tmp)
ACHOME="${TMP}/agent-crew-home"
CODEX_HOME="${TMP}/codex-home"
CLAUDE_DIR="${TMP}/claude-home"
mkdir -p "${ACHOME}/skills" "${ACHOME}/system/agents/skills" "${ACHOME}/setup" \
  "${ACHOME}/hooks" "${ACHOME}/system/hooks" \
  "${ACHOME}/scripts" "${CODEX_HOME}/skills/agent-crew" "${CODEX_HOME}/agent-crew/skills" \
  "${CODEX_HOME}/agents"

cp "${SETUP_DIR}/setup-host.sh" "${ACHOME}/setup/setup-host.sh"
mkdir -p "${ACHOME}/adapters/generic"
cat > "${ACHOME}/adapters/generic/setup.sh" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "${ACHOME}/adapters/generic/setup.sh"

echo 'developer_instructions = """This is a Codex adapter bootstrap for the agent-crew system agent."""' > "${CODEX_HOME}/agents/task-runner.toml"
echo 'name = "input-normalizer" owner = "user"' > "${CODEX_HOME}/agents/input-normalizer.toml"
echo 'name = "my-custom"' > "${CODEX_HOME}/agents/my-custom.toml"
echo "stale" > "${CODEX_HOME}/agent-crew/skills/stale.md"
mkdir -p "${CODEX_HOME}/skills/crew-run"
echo "stale skill" > "${CODEX_HOME}/skills/crew-run/SKILL.md"
mkdir -p "${CODEX_HOME}/skills/crew-task" "${CODEX_HOME}/skills/crew-workflow"
echo "stale skill" > "${CODEX_HOME}/skills/crew-task/SKILL.md"
echo "stale skill" > "${CODEX_HOME}/skills/crew-workflow/SKILL.md"
echo "stale hook" > "${ACHOME}/hooks/auto-route.sh"
echo "skill" > "${ACHOME}/skills/current.md"
cat > "${CODEX_HOME}/hooks.json" <<JSON
{
  "custom_top": {"keep": true},
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "custom",
        "hooks": [
          {"type": "command", "command": "bash /tmp/user/hooks/auto-route.sh", "timeout": 3},
          {"type": "command", "command": "bash '${ACHOME}/hooks/auto-route.sh'", "timeout": 1}
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {"type": "command", "command": "bash /tmp/custom-stop.sh", "timeout": 4}
        ]
      }
    ]
  }
}
JSON
cat > "${CODEX_HOME}/config.toml" <<'TOML'
model = "gpt-test"

[agents]
max_threads = 2
custom_mode = "keep"
TOML

it "update-global-adapters exits 0"
AGENT_CREW_HOME="${ACHOME}" \
CODEX_HOME="${CODEX_HOME}" \
CLAUDE_DIR="${CLAUDE_DIR}" \
SOURCE_ROOT="${REPO_ROOT}" \
  bash "${SCRIPTS_DIR}/update-global-adapters.sh" >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}" "update-global-adapters"

it "global Codex agents include supervisor"
assert_file_exists "${CODEX_HOME}/agents/supervisor.toml"

it "global Codex supervisor delegates to canonical markdown"
supervisor_toml="$(cat "${CODEX_HOME}/agents/supervisor.toml")"
assert_contains "${supervisor_toml}" 'Read `'"${ACHOME}"'/system/agents/supervisor.md`'

it "global Codex supervisor does not inline stale pipeline instructions"
assert_not_contains "${supervisor_toml}" "### Phase 1: Spawn planner"

it "global Codex agents include documenter"
assert_file_exists "${CODEX_HOME}/agents/documenter.toml"

it "global Codex agents prune task-runner"
assert_file_absent "${CODEX_HOME}/agents/task-runner.toml"

it "global Codex agents preserve unmarked known-name collisions"
assert_file_exists "${CODEX_HOME}/agents/input-normalizer.toml"
assert_contains "$(cat "${CODEX_HOME}/agents/input-normalizer.toml")" 'owner = "user"'

it "global Codex agents preserve unknown custom TOMLs"
assert_file_exists "${CODEX_HOME}/agents/my-custom.toml"
assert_contains "$(cat "${CODEX_HOME}/agents/my-custom.toml")" 'name = "my-custom"'

it "Codex global hooks merge preserves user-owned hooks and top-level keys"
hooks_out="$(cat "${CODEX_HOME}/hooks.json")"
assert_contains "${hooks_out}" '"custom_top"'
assert_contains "${hooks_out}" "/tmp/user/hooks/auto-route.sh"
assert_contains "${hooks_out}" "/tmp/custom-stop.sh"
assert_contains "${hooks_out}" "auto-route.sh"
managed_auto_route_count="$(python3 - "${CODEX_HOME}/hooks.json" "${ACHOME}" <<'PY'
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
needle = str(Path(sys.argv[2]) / "hooks" / "auto-route.sh")
print(json.dumps(data).count(needle))
PY
)"
assert_eq "1" "${managed_auto_route_count}" "managed auto-route deduplicated"

it "Codex global config merge preserves user-owned agents keys"
config_out="$(cat "${CODEX_HOME}/config.toml")"
assert_contains "${config_out}" 'custom_mode = "keep"'
assert_contains "${config_out}" "max_threads = 6"
assert_contains "${config_out}" "max_depth = 1"

it "Codex crew skills mirror prunes stale skill"
assert_file_absent "${CODEX_HOME}/agent-crew/skills/stale.md"

it "Codex crew skills mirror copies unified current skill"
assert_file_exists "${CODEX_HOME}/agent-crew/skills/current.md"

it "Codex command skills prune legacy crew dash prefix"
assert_file_absent "${CODEX_HOME}/skills/crew-run/SKILL.md"
assert_file_absent "${CODEX_HOME}/skills/crew-task/SKILL.md"
assert_file_absent "${CODEX_HOME}/skills/crew-workflow/SKILL.md"

it "Codex command skills prune old agent-crew bootstrap skill"
assert_file_absent "${CODEX_HOME}/skills/agent-crew"

it "Codex command skills install crew colon prefix"
assert_file_exists "${CODEX_HOME}/skills/crew:run/SKILL.md"

it "update-global-adapters refreshes installed auto-route hook"
hook_out="$(cat "${ACHOME}/hooks/auto-route.sh")"
assert_contains "${hook_out}" 'explicit {command} invocation detected'

BAD_TMP=$(make_tmp)
BAD_ACHOME="${BAD_TMP}/agent-crew-home"
BAD_CODEX_HOME="${BAD_TMP}/codex-home"
BAD_CLAUDE_DIR="${BAD_TMP}/claude-home"
mkdir -p "${BAD_ACHOME}/skills" "${BAD_ACHOME}/system/agents" "${BAD_ACHOME}/setup" \
  "${BAD_ACHOME}/hooks" "${BAD_ACHOME}/system/hooks" \
  "${BAD_ACHOME}/scripts" "${BAD_CODEX_HOME}/agents"
cp "${SETUP_DIR}/setup-host.sh" "${BAD_ACHOME}/setup/setup-host.sh"
mkdir -p "${BAD_ACHOME}/adapters/generic"
cat > "${BAD_ACHOME}/adapters/generic/setup.sh" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "${BAD_ACHOME}/adapters/generic/setup.sh"
echo "stale hook" > "${BAD_ACHOME}/hooks/auto-route.sh"
echo "{not-json" > "${BAD_CODEX_HOME}/hooks.json"

it "update-global-adapters refuses malformed Codex hooks without overwriting"
AGENT_CREW_HOME="${BAD_ACHOME}" \
CODEX_HOME="${BAD_CODEX_HOME}" \
CLAUDE_DIR="${BAD_CLAUDE_DIR}" \
SOURCE_ROOT="${REPO_ROOT}" \
  bash "${SCRIPTS_DIR}/update-global-adapters.sh" >/dev/null 2>"${BAD_TMP}/stderr.log"
bad_rc=$?
assert_exit 1 "${bad_rc}" "update-global-adapters malformed hooks"
assert_contains "$(cat "${BAD_CODEX_HOME}/hooks.json")" "{not-json"
assert_contains "$(cat "${BAD_TMP}/stderr.log")" "Refusing to overwrite non-object or malformed Codex hooks.json"

SCHEMA_TMP=$(make_tmp)
SCHEMA_ACHOME="${SCHEMA_TMP}/agent-crew-home"
SCHEMA_CODEX_HOME="${SCHEMA_TMP}/codex-home"
SCHEMA_CLAUDE_DIR="${SCHEMA_TMP}/claude-home"
mkdir -p "${SCHEMA_ACHOME}/skills" "${SCHEMA_ACHOME}/system/agents" "${SCHEMA_ACHOME}/setup" \
  "${SCHEMA_ACHOME}/hooks" "${SCHEMA_ACHOME}/system/hooks" \
  "${SCHEMA_ACHOME}/scripts" "${SCHEMA_CODEX_HOME}/agents"
cp "${SETUP_DIR}/setup-host.sh" "${SCHEMA_ACHOME}/setup/setup-host.sh"
mkdir -p "${SCHEMA_ACHOME}/adapters/generic"
cat > "${SCHEMA_ACHOME}/adapters/generic/setup.sh" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "${SCHEMA_ACHOME}/adapters/generic/setup.sh"
echo "stale hook" > "${SCHEMA_ACHOME}/hooks/auto-route.sh"
echo '{"hooks": []}' > "${SCHEMA_CODEX_HOME}/hooks.json"

it "update-global-adapters refuses non-object Codex hooks schema without overwriting"
AGENT_CREW_HOME="${SCHEMA_ACHOME}" \
CODEX_HOME="${SCHEMA_CODEX_HOME}" \
CLAUDE_DIR="${SCHEMA_CLAUDE_DIR}" \
SOURCE_ROOT="${REPO_ROOT}" \
  bash "${SCRIPTS_DIR}/update-global-adapters.sh" >/dev/null 2>"${SCHEMA_TMP}/stderr.log"
schema_rc=$?
assert_exit 1 "${schema_rc}" "update-global-adapters hooks schema"
assert_contains "$(cat "${SCHEMA_CODEX_HOME}/hooks.json")" '{"hooks": []}'
assert_contains "$(cat "${SCHEMA_TMP}/stderr.log")" "Refusing to overwrite unsupported Codex hooks.json schema"

BLOCK_TMP=$(make_tmp)
BLOCK_ACHOME="${BLOCK_TMP}/agent-crew-home"
BLOCK_CODEX_HOME="${BLOCK_TMP}/codex-home"
BLOCK_CLAUDE_DIR="${BLOCK_TMP}/claude-home"
mkdir -p "${BLOCK_ACHOME}/skills" "${BLOCK_ACHOME}/system/agents" "${BLOCK_ACHOME}/setup" \
  "${BLOCK_ACHOME}/hooks" "${BLOCK_ACHOME}/system/hooks" \
  "${BLOCK_ACHOME}/scripts" "${BLOCK_CODEX_HOME}/agents"
cp "${SETUP_DIR}/setup-host.sh" "${BLOCK_ACHOME}/setup/setup-host.sh"
mkdir -p "${BLOCK_ACHOME}/adapters/generic"
cat > "${BLOCK_ACHOME}/adapters/generic/setup.sh" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "${BLOCK_ACHOME}/adapters/generic/setup.sh"
echo "stale hook" > "${BLOCK_ACHOME}/hooks/auto-route.sh"
echo '{"hooks": {"UserPromptSubmit": [{"hooks": ["not-object"]}]}}' > "${BLOCK_CODEX_HOME}/hooks.json"

it "update-global-adapters refuses malformed required hook block without overwriting"
AGENT_CREW_HOME="${BLOCK_ACHOME}" \
CODEX_HOME="${BLOCK_CODEX_HOME}" \
CLAUDE_DIR="${BLOCK_CLAUDE_DIR}" \
SOURCE_ROOT="${REPO_ROOT}" \
  bash "${SCRIPTS_DIR}/update-global-adapters.sh" >/dev/null 2>"${BLOCK_TMP}/stderr.log"
block_rc=$?
assert_exit 1 "${block_rc}" "update-global-adapters hook block schema"
assert_contains "$(cat "${BLOCK_CODEX_HOME}/hooks.json")" '"not-object"'
assert_contains "$(cat "${BLOCK_TMP}/stderr.log")" "Refusing to overwrite unsupported Codex hooks.json schema"

end_report
