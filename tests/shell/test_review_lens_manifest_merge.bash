#!/usr/bin/env bash
# The review lens manifest must accumulate one entry per provider.
#
# Two separate defects used to keep it to a single lens:
#   1. Both adapters wrote the whole file with `cat >`, so whichever ran last
#      erased the other provider's lens.
#   2. The write sat behind AGENT_CREW_WRITE_CAPABILITIES, which install/update
#      set to 0 so the Claude compatibility pass could not stamp its own
#      capabilities.json over the active host's. Review lenses are additive per
#      provider, so that gate was wrong for them.
#
# capabilities.json must stay gated; review-lenses.json must not.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

TMP=$(make_tmp)
ACHOME="${TMP}/agent-crew-home"
CLAUDE_DIR_T="${TMP}/claude-home"
PROJECT_T="${TMP}/project"
mkdir -p \
  "${ACHOME}/commands" "${ACHOME}/hooks" "${ACHOME}/rules" "${ACHOME}/scripts" \
  "${ACHOME}/setup" "${ACHOME}/adapters/claude/bin" \
  "${ACHOME}/system/agents" "${ACHOME}/system/skills" \
  "${ACHOME}/user/agents" "${ACHOME}/user/commands" "${ACHOME}/user/skills" \
  "${CLAUDE_DIR_T}/commands" "${CLAUDE_DIR_T}/agent-crew" "${PROJECT_T}"
cp "${SETUP_DIR}/common.sh" "${ACHOME}/setup/common.sh"

state_dir() {
  python3 "${REPO_ROOT}/core/scripts/project_state.py" resolve \
    --agent-crew-home "${ACHOME}" --project-root "${PROJECT_T}" \
    --prefer-existing-legacy --format json \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["state_dir"])'
}

run_claude_adapter() {
  AGENT_CREW_HOME="${ACHOME}" CLAUDE_DIR="${CLAUDE_DIR_T}" SOURCE_ROOT="${REPO_ROOT}" \
    AGENT_CREW_MODE=update AGENT_CREW_WRITE_CAPABILITIES=0 \
    bash "${REPO_ROOT}/adapters/claude/setup.sh" "${PROJECT_T}" >/dev/null 2>&1
}

lens_ids() {
  python3 -c '
import json,sys
try:
    d=json.load(open(sys.argv[1]))
except Exception:
    print(""); raise SystemExit
print(",".join(sorted(l.get("lens_id","") for l in d.get("lenses",[]))))
' "$1"
}

it "claude adapter exits 0 with capabilities writing disabled"
run_claude_adapter
rc=$?
assert_exit 0 "${rc}"

ST="$(state_dir)"

it "capabilities.json stays gated off"
assert_file_absent "${ST}/capabilities.json"

it "review lens manifest is written even with capabilities gated off"
assert_file_exists "${ST}/review-lenses.json"

it "manifest registers the claude system review lens"
assert_eq "claude-system-review" "$(lens_ids "${ST}/review-lenses.json")"

# A second provider's lens must survive the Claude pass.
python3 - "${ST}/review-lenses.json" <<'PYEOF'
import json, sys
path = sys.argv[1]
data = json.load(open(path))
data["lenses"].append({
    "lens_id": "codex-system-review",
    "name": "Codex system review",
    "provider": "codex",
    "surface": "host-native",
    "read_only": True,
    "mutates": False,
    "default_enabled": True,
    "requires_mr": "optional",
    "requires_remote_read": "none",
    "requires_supervisor_context": False,
    "timeout_seconds": 120,
    "duplicate_group": "ai-system-review",
    "path": "/tmp/codex/review",
    "runner": "codex-system-skill",
    "result_source_label": "source_lens=codex-system-review",
})
json.dump(data, open(path, "w"), indent=2)
PYEOF

it "re-running the claude adapter preserves another provider's lens"
run_claude_adapter
assert_eq "claude-system-review,codex-system-review" "$(lens_ids "${ST}/review-lenses.json")"

it "repeated runs leave the manifest byte-identical"
before=$(shasum "${ST}/review-lenses.json" | cut -d' ' -f1)
run_claude_adapter
assert_eq "${before}" "$(shasum "${ST}/review-lenses.json" | cut -d' ' -f1)"

it "the claude lens entry keeps its runner metadata"
assert_contains "$(cat "${ST}/review-lenses.json")" '"runner": "claude-current-session-review"'

end_report
