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

# Each provider's system review is a distinct viewpoint, so the two shipped
# lenses must not share a duplicate group — otherwise discovery promotes only
# the higher-priority provider and suppresses the other.
claude_group=$(grep -A1 '"lens_id": "claude-system-review"' -m1 "${REPO_ROOT}/adapters/claude/setup.sh" >/dev/null 2>&1; \
  sed -n 's/.*"duplicate_group": "\([^"]*\)".*/\1/p' "${REPO_ROOT}/adapters/claude/setup.sh" | head -1)
codex_group=$(sed -n 's/.*"duplicate_group": "\([^"]*\)".*/\1/p' "${REPO_ROOT}/adapters/codex/setup.sh" | head -1)

it "the two shipped system-review lenses use distinct duplicate groups"
if [ -n "${claude_group}" ] && [ "${claude_group}" != "${codex_group}" ]; then
  _pass
else
  _fail "claude_group='${claude_group}' codex_group='${codex_group}' must differ and be non-empty"
fi

# End-to-end: both providers registered, both reachable by discovery.
python3 - "${ST}/review-lenses.json" "${codex_group}" <<'PYEOF'
import json, sys
path, codex_group = sys.argv[1], sys.argv[2]
data = json.load(open(path))
data["lenses"] = [l for l in data["lenses"] if l.get("lens_id") != "codex-system-review"]
data["lenses"].append({
    "lens_id": "codex-system-review", "name": "Codex system review",
    "provider": "codex", "surface": "host-native", "read_only": True,
    "mutates": False, "default_enabled": True, "requires_mr": "optional",
    "requires_remote_read": "none", "requires_supervisor_context": False,
    "timeout_seconds": 120, "duplicate_group": codex_group,
    "path": "/tmp/codex/review", "runner": "codex-system-skill",
    "result_source_label": "source_lens=codex-system-review",
})
json.dump(data, open(path, "w"), indent=2)
PYEOF

lens_status() {
  python3 "${REPO_ROOT}/core/scripts/review-lens-discovery.py" \
    --root "${ACHOME}/user/commands" \
    --host-lens-manifest "${ST}/review-lenses.json" --format json 2>/dev/null \
    | python3 -c '
import json,sys
want=sys.argv[1]
for l in json.load(sys.stdin)["lenses"]:
    if l["lens_id"]==want:
        print(l["status"]); break
else:
    print("absent")
' "$1"
}

it "codex system review is eligible"
assert_eq "eligible" "$(lens_status codex-system-review)"

it "claude system review is eligible alongside it"
assert_eq "eligible" "$(lens_status claude-system-review)"

end_report
