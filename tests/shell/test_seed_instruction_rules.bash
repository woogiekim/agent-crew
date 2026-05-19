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
  read)
    rid="\${POS[0]:-}"
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

# --------------------------------------------------------------------------- #
# --apply on empty store: creates all rules                                   #
# --------------------------------------------------------------------------- #

TMP=$(make_tmp)
MNEMOS=$(make_mock_mnemos "${TMP}")

it "--apply on empty store: exit 0"
out=$(MNEMOS_BIN="${MNEMOS}" bash "${SCRIPT}" --apply 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "--apply created all rules"
# Count "+ CREATE" lines emitted by capture_rule
n=$(echo "${out}" | grep -c "+ CREATE")
assert_eq "${EXPECTED_RULE_COUNT}" "${n}" "rules created"

it "--apply summary shows created count"
assert_contains "${out}" "created=${EXPECTED_RULE_COUNT}"

it "--apply persisted at least one rule body (input-language)"
stored="${TMP}/mnemos-store/rule:input-language"
assert_file_exists "${stored}"

# --------------------------------------------------------------------------- #
# Re-run --apply with identical content: all skipped                          #
# --------------------------------------------------------------------------- #

it "--apply re-run with identical store: exit 0"
out=$(MNEMOS_BIN="${MNEMOS}" bash "${SCRIPT}" --apply 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "--apply re-run: summary shows skipped count"
assert_contains "${out}" "skipped=${EXPECTED_RULE_COUNT}"

it "--apply re-run: no rules updated"
assert_contains "${out}" "updated=0"

it "--apply re-run: no rules created"
assert_contains "${out}" "created=0"

# --------------------------------------------------------------------------- #
# --apply with edited body: detects drift → updated count > 0                 #
# --------------------------------------------------------------------------- #

# Truncate one rule's content to force drift
echo "drifted" > "${TMP}/mnemos-store/rule:input-language"

it "--apply with drift: exit 0"
out=$(MNEMOS_BIN="${MNEMOS}" bash "${SCRIPT}" --apply 2>&1)
rc=$?
assert_exit 0 "${rc}"

it "--apply with drift: updated >= 1"
# Extract updated=N count
upd=$(echo "${out}" | grep -oE 'updated=[0-9]+' | tail -1 | sed 's/updated=//')
if [ -n "${upd}" ] && [ "${upd}" -ge 1 ]; then
  _pass
else
  _fail "expected updated>=1 got '${upd}' (full output below):"$'\n'"${out}"
fi

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
