#!/usr/bin/env bash
# Tests for core/scripts/seed-instruction-rules.sh
#
# Uses a mock mnemos stub that persists rule content to flat files in a
# tmp dir, so we can verify create/update/skip semantics without a real
# mnemos store.
#
# The script captures one rule per `capture_rule` call. The mock
# accepts:
#   mnemos read   <id>          → emits {"content": "..."} or empty
#   mnemos capture --id <id> --content <body> ...   → writes flat file
#   mnemos edit   <id> --content <body>             → overwrites flat file

set -u
source "$(dirname "$0")/_lib.bash"

SCRIPT="${SCRIPTS_DIR}/seed-instruction-rules.sh"
EXPECTED_RULE_COUNT=$(grep -c '^[[:space:]]*capture_rule ' "${SCRIPT}" | tr -d '[:space:]')
RUNTIME_RULE_COUNT=5

# --------------------------------------------------------------------------- #
# Mock mnemos stub                                                            #
# --------------------------------------------------------------------------- #

make_mock_mnemos() {
  local tmp="$1"
  local store="${tmp}/mnemos-store"
  mkdir -p "${store}"
  local stub="${tmp}/mnemos"
  cat > "${stub}" <<EOF
#!/usr/bin/env bash
# Mock mnemos backed by flat files under ${store}.
STORE="${store}"
cmd="\$1"
shift || true

# Parse common option style: --layer X --id Y --tag Z --content W --quiet
# We only need --id and --content.
ID=""
CONTENT=""
POS=()
while [ \$# -gt 0 ]; do
  case "\$1" in
    --id)      ID="\$2"; shift 2 ;;
    --content) CONTENT="\$2"; shift 2 ;;
    --layer|--tag) shift 2 ;;
    --quiet|--limit|--id-only) shift ;;
    *) POS+=("\$1"); shift ;;
  esac
done

case "\$cmd" in
  capabilities)
    if [ "\${POS[0]:-}" = "--json" ]; then
      echo '{"capabilities":{"read_json":true}}'
    fi
    ;;
  read)
    if [ "\${POS[0]:-}" = "--json" ]; then
      shift_pos="\${POS[1]:-}"
      rid="\${shift_pos}"
    else
      echo "read must use --json" >&2
      exit 1
    fi
    f="\${STORE}/\${rid//[\\/]/_}"
    if [ -f "\$f" ]; then
      python3 -c '
import json,sys
content = open(sys.argv[1]).read()
print(json.dumps({"tags":["instruction-rule"],"content":content}, ensure_ascii=False))
' "\$f"
    else
      exit 1
    fi
    ;;
  capture|edit)
    # For 'edit', id is positional; for 'capture', it's --id.
    if [ -z "\$ID" ] && [ -n "\${POS[0]:-}" ]; then
      ID="\${POS[0]}"
    fi
    f="\${STORE}/\${ID//[\\/]/_}"
    printf '%s' "\$CONTENT" > "\$f"
    ;;
  list)
    # Used by sync-instructions; not tested here. Emit nothing.
    ;;
  *)
    exit 1
    ;;
esac
EOF
  chmod +x "${stub}"
  printf '%s' "${stub}"
}

# --------------------------------------------------------------------------- #
# MNEMOS_BIN missing → exit 1                                                 #
# --------------------------------------------------------------------------- #

it "exits 1 when MNEMOS_BIN is not executable"
out=$(MNEMOS_BIN=/nonexistent/no-such-mnemos bash "${SCRIPT}" --apply 2>&1)
rc=$?
assert_exit 1 "${rc}"

it "stderr mentions mnemos CLI not found"
assert_contains "${out}" "mnemos CLI not found"

# --------------------------------------------------------------------------- #
# Invalid mode arg → exit 2                                                   #
# --------------------------------------------------------------------------- #

it "unknown mode arg → exit 2"
out=$(MNEMOS_BIN=/bin/echo bash "${SCRIPT}" --bogus 2>&1)
rc=$?
assert_exit 2 "${rc}"

it "unknown seed profile → exit 2"
out=$(MNEMOS_BIN=/bin/echo bash "${SCRIPT}" --apply --profile unknown-profile 2>&1)
rc=$?
assert_exit 2 "${rc}"

# --------------------------------------------------------------------------- #
# Runtime command profile: selected repair without unrelated rule drift        #
# --------------------------------------------------------------------------- #

TMP=$(make_tmp)
MNEMOS=$(make_mock_mnemos "${TMP}")
printf '%s' 'newer raw-input policy' > "${TMP}/mnemos-store/rule:input-language"
printf '%s' 'newer candidate safety policy' > "${TMP}/mnemos-store/rule:parallel-first"

it "default profile reconciles only the runtime command surface"
out=$(MNEMOS_BIN="${MNEMOS}" bash "${SCRIPT}" --apply 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "profile=runtime-command-surface"

it "default profile preserves unrelated canonical rules"
assert_eq "newer raw-input policy" "$(cat "${TMP}/mnemos-store/rule:input-language")"
assert_eq "newer candidate safety policy" "$(cat "${TMP}/mnemos-store/rule:parallel-first")"

it "default profile writes only runtime command rules"
n=$(find "${TMP}/mnemos-store" -type f | wc -l | tr -d '[:space:]')
assert_eq $((RUNTIME_RULE_COUNT + 2)) "${n}" "runtime rules plus two sentinels"

TMP=$(make_tmp)
MNEMOS=$(make_mock_mnemos "${TMP}")
printf '%s' 'newer raw-input policy' > "${TMP}/mnemos-store/rule:input-language"
printf '%s' 'newer candidate safety policy' > "${TMP}/mnemos-store/rule:parallel-first"

it "runtime command profile applies successfully"
out=$(MNEMOS_BIN="${MNEMOS}" bash "${SCRIPT}" --apply --profile runtime-command-surface 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "runtime command profile preserves unrelated rules"
assert_eq "newer raw-input policy" "$(cat "${TMP}/mnemos-store/rule:input-language")"

it "runtime command profile preserves candidate safety rules"
assert_eq "newer candidate safety policy" "$(cat "${TMP}/mnemos-store/rule:parallel-first")"

it "explicit runtime command profile writes only its selected rules"
n=$(find "${TMP}/mnemos-store" -type f | wc -l | tr -d '[:space:]')
assert_eq $((RUNTIME_RULE_COUNT + 2)) "${n}" "runtime rules plus two unrelated sentinels"

it "runtime command profile restores crew run as canonical"
workflow_rule="$(cat "${TMP}/mnemos-store/rule:workflow-intents" 2>/dev/null || true)"
assert_contains "${workflow_rule}" "\`crew run\` is the native CLI execution entry"
assert_contains "${workflow_rule}" '`$crew:run`'
assert_not_contains "${workflow_rule}" "candidate-only resolver"

it "runtime command profile rejects unavailable task and workflow commands"
assert_contains "${workflow_rule}" "does not expose \`crew task\` or \`crew workflow\`"

it "runtime command fallback preserves the pinned execution"
fallback_rule="$(cat "${TMP}/mnemos-store/rule:current-session-fallback" 2>/dev/null || true)"
assert_contains "${fallback_rule}" "original Root Input Snapshot"
assert_contains "${fallback_rule}" "cannot re-resolve candidates"

it "runtime command profile preserves external skill approval"
codex_rule="$(cat "${TMP}/mnemos-store/rule:codex-routing-fallback" 2>/dev/null || true)"
assert_contains "${codex_rule}" "Domain-match alone is not approval"
assert_contains "${codex_rule}" "require explicit user approval"

# --------------------------------------------------------------------------- #
# Explicit bootstrap on empty store: creates all repository baseline rules     #
# --------------------------------------------------------------------------- #

TMP=$(make_tmp)
MNEMOS=$(make_mock_mnemos "${TMP}")

it "bootstrap-missing on empty store: exit 0"
out=$(MNEMOS_BIN="${MNEMOS}" bash "${SCRIPT}" --apply --profile bootstrap-missing 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "bootstrap-missing created all repository baseline rules"
# Count "+ CREATE" lines emitted by capture_rule
n=$(echo "${out}" | grep -c "+ CREATE")
assert_eq "${EXPECTED_RULE_COUNT}" "${n}" "rules created"

it "bootstrap-missing summary shows created count"
assert_contains "${out}" "created=${EXPECTED_RULE_COUNT}"

it "bootstrap-missing persisted raw input rule"
stored="${TMP}/mnemos-store/rule:input-language"
assert_file_exists "${stored}"
input_rule="$(cat "${stored}" 2>/dev/null || true)"
assert_contains "${input_rule}" "immutable Root Input Snapshot"
assert_contains "${input_rule}" "must not translate, summarize, normalize"

it "bootstrap source never normalizes input to English"
output_rule="$(cat "${TMP}/mnemos-store/rule:output-language" 2>/dev/null || true)"
assert_not_contains "${output_rule}" "input is normalized to English"
assert_contains "${output_rule}" "Never change the stored Root Input Snapshot"

it "--apply persisted code style context-break rule"
stored="${TMP}/mnemos-store/rule:code-style-context-breaks"
assert_file_exists "${stored}"

it "code style context-break rule applies globally"
assert_contains "$(cat "${stored}" 2>/dev/null || true)" "applies_to: [all]"

it "code style context-break rule requires breaks on context changes"
assert_contains "$(cat "${stored}" 2>/dev/null || true)" "break when the implementation context changes"

it "technical hook boundary is seeded"
stored="${TMP}/mnemos-store/rule:stop-directive"
assert_file_exists "${stored}"
stop_rule="$(cat "${stored}" 2>/dev/null || true)"
assert_contains "${stop_rule}" "Technical Hook Boundary"
assert_contains "${stop_rule}" "They must be deterministic, bounded,"
assert_contains "${stop_rule}" "traceable, and fail in a documented way"
assert_not_contains "${stop_rule}" "STOP Directive"

it "explicit scope boundary is seeded"
stored="${TMP}/mnemos-store/rule:route-directive"
assert_file_exists "${stored}"
route_rule="$(cat "${stored}" 2>/dev/null || true)"
assert_contains "${route_rule}" "Explicit Scope Boundary"
assert_contains "${route_rule}" "selects exactly one logical Registry"
assert_not_contains "${route_rule}" "ROUTE Directive"

it "current-session fallback rule applies to every host"
stored="${TMP}/mnemos-store/rule:current-session-fallback"
assert_file_exists "${stored}"
fallback_rule="$(cat "${stored}" 2>/dev/null || true)"
assert_contains "${fallback_rule}" "applies_to: [all]"
assert_contains "${fallback_rule}" "original Root Input Snapshot"
assert_contains "${fallback_rule}" "cannot re-resolve candidates"
assert_contains "${fallback_rule}" "TDD Red → Green → Refactor"
assert_contains "${fallback_rule}" "phase-note artifacts are coverage gaps"

it "workflow intents distinguish notation from native CLI"
stored="${TMP}/mnemos-store/rule:workflow-intents"
assert_file_exists "${stored}"
workflow_rule="$(cat "${stored}" 2>/dev/null || true)"
assert_contains "${workflow_rule}" "\`crew:<intent>\` is workflow notation"
assert_contains "${workflow_rule}" "native shell CLI uses space-separated commands"

it "bootstrap baseline forbids hidden routing"
hidden_routing_rule="$(cat "${TMP}/mnemos-store/rule:auto-execution-triggers" 2>/dev/null || true)"
assert_contains "${hidden_routing_rule}" "Hidden Routing Prohibition"
assert_contains "${hidden_routing_rule}" "No lifecycle hook"
assert_not_contains "${hidden_routing_rule}" "Every substantive user-facing response"

it "bootstrap baseline limits technical hooks"
hook_rule="$(cat "${TMP}/mnemos-store/rule:stop-directive" 2>/dev/null || true)"
assert_contains "${hook_rule}" "Technical Hook Boundary"
assert_not_contains "${hook_rule}" "STOP appears"

it "bootstrap baseline preserves candidate and approval boundaries"
candidate_rule="$(cat "${TMP}/mnemos-store/rule:parallel-first" 2>/dev/null || true)"
approval_rule="$(cat "${TMP}/mnemos-store/rule:approval-gate" 2>/dev/null || true)"
assert_contains "${candidate_rule}" "Candidate And Registry Boundaries"
assert_not_contains "${candidate_rule}" "Default to parallel execution"
assert_contains "${approval_rule}" "Candidate Selection and Execution Approval are distinct decisions"

# --------------------------------------------------------------------------- #
# Re-run --apply with identical content: all skipped                          #
# --------------------------------------------------------------------------- #

it "bootstrap-missing re-run with identical store: exit 0"
out=$(MNEMOS_BIN="${MNEMOS}" bash "${SCRIPT}" --apply --profile bootstrap-missing 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "bootstrap-missing re-run: summary shows skipped count"
assert_contains "${out}" "skipped=${EXPECTED_RULE_COUNT}"

it "bootstrap-missing re-run: no rules updated"
assert_contains "${out}" "updated=0"

it "bootstrap-missing re-run: no rules created"
assert_contains "${out}" "created=0"

# --------------------------------------------------------------------------- #
# Bootstrap preserves existing canonical drift; runtime profile repairs its IDs #
# --------------------------------------------------------------------------- #

echo "newer canonical raw-input policy" > "${TMP}/mnemos-store/rule:input-language"

it "bootstrap-missing preserves an existing canonical rule"
out=$(MNEMOS_BIN="${MNEMOS}" bash "${SCRIPT}" --apply --profile bootstrap-missing 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_eq "newer canonical raw-input policy" "$(cat "${TMP}/mnemos-store/rule:input-language")"
assert_contains "${out}" "PRESERVE rule:input-language"

echo "drifted" > "${TMP}/mnemos-store/rule:workflow-intents"

it "runtime profile repairs drift in an owned command rule"
out=$(MNEMOS_BIN="${MNEMOS}" bash "${SCRIPT}" --apply --profile runtime-command-surface 2>&1)
rc=$?
assert_exit 0 "${rc}"
assert_contains "${out}" "updated=1"
assert_contains "$(cat "${TMP}/mnemos-store/rule:workflow-intents")" "crew run"

# --------------------------------------------------------------------------- #
# --dry-run does not call capture/edit (store unchanged)                      #
# --------------------------------------------------------------------------- #

TMP=$(make_tmp)
MNEMOS=$(make_mock_mnemos "${TMP}")

it "--dry-run on empty store: exit 0"
out=$(MNEMOS_BIN="${MNEMOS}" bash "${SCRIPT}" --dry-run 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "--dry-run did NOT write any files (store is empty)"
n=$(find "${TMP}/mnemos-store" -type f 2>/dev/null | wc -l | tr -d '[:space:]')
assert_eq 0 "${n}" "store file count after --dry-run"

end_report
