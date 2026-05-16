#!/usr/bin/env bash
# Integration: SSOT roundtrip — verify that adding a marker via mnemos
# (mocked) flows into all host AI md files on --apply, and that removing
# the marker results in the marker being removed from all hosts.
#
# This test uses a MOCK mnemos so it never touches the user's real
# ~/.mnemos store. The mock supports stateful list/read/edit just enough
# for sync-instructions to operate.

set -u
source "$(dirname "$0")/../shell/_lib.bash"

SCRIPT="${SCRIPTS_DIR}/sync-instructions.sh"

# --------------------------------------------------------------------------- #
# Stateful mock mnemos                                                        #
# --------------------------------------------------------------------------- #

make_stateful_mock_mnemos() {
  local tmp="$1"
  local store="${tmp}/mnemos-store"
  local index="${tmp}/mnemos-index"
  mkdir -p "${store}"
  : > "${index}"  # text list of rule ids
  local stub="${tmp}/mnemos"
  cat > "${stub}" <<EOF
#!/usr/bin/env bash
STORE="${store}"
INDEX="${index}"
cmd="\$1"
shift || true

ID=""
CONTENT=""
POS=()
while [ \$# -gt 0 ]; do
  case "\$1" in
    --id)      ID="\$2"; shift 2 ;;
    --content) CONTENT="\$2"; shift 2 ;;
    --layer|--tag|--limit) shift 2 ;;
    --quiet|--id-only) shift ;;
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
  capture)
    if [ -z "\$ID" ]; then exit 1; fi
    f="\${STORE}/\${ID//[\\/]/_}"
    printf '%s' "\$CONTENT" > "\$f"
    # Add to index
    grep -qxF "[global] \${ID}:" "\$INDEX" 2>/dev/null || \
      echo "[global] \${ID}:" >> "\$INDEX"
    ;;
  edit)
    rid="\${ID:-\${POS[0]:-}}"
    f="\${STORE}/\${rid//[\\/]/_}"
    printf '%s' "\$CONTENT" > "\$f"
    ;;
  delete)
    rid="\${ID:-\${POS[0]:-}}"
    f="\${STORE}/\${rid//[\\/]/_}"
    rm -f "\$f"
    # Remove from index
    grep -vxF "[global] \${rid}:" "\$INDEX" > "\${INDEX}.new" 2>/dev/null || true
    mv "\${INDEX}.new" "\$INDEX" 2>/dev/null || true
    ;;
  list)
    cat "\$INDEX" 2>/dev/null || true
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
# Setup: hermetic hosts + mock mnemos with one seeded rule                    #
# --------------------------------------------------------------------------- #

TMP=$(make_tmp)
MNEMOS=$(make_stateful_mock_mnemos "${TMP}")

CLAUDE_HOME_T="${TMP}/claude-home"
CODEX_HOME_T="${TMP}/codex-home"
AGENT_CREW_HOME_T="${TMP}/agent-crew-home"
mkdir -p "${CLAUDE_HOME_T}" "${CODEX_HOME_T}" "${AGENT_CREW_HOME_T}"

# Seed each host with some user-content outside the marker block
for hosts_path in \
  "${CLAUDE_HOME_T}/CLAUDE.md" \
  "${CODEX_HOME_T}/AGENTS.md" \
  "${AGENT_CREW_HOME_T}/AGENTS.md"
do
  cat > "${hosts_path}" <<'EOF'
# User custom intro
This is outside the marker block.
EOF
done

# Seed mnemos with rule:test-structured-choice
"${MNEMOS}" capture --layer global --tag instruction-rule \
  --id "rule:test-structured-choice" \
  --content "---
title: Test Structured Choice
applies_to: [all]
priority: 50
---

This is the BASELINE content."

run_sync() {
  MNEMOS_BIN="${MNEMOS}" \
  CLAUDE_HOME="${CLAUDE_HOME_T}" \
  CODEX_HOME="${CODEX_HOME_T}" \
  AGENT_CREW_HOME="${AGENT_CREW_HOME_T}" \
    bash "${SCRIPT}" --apply --hosts claude,codex,generic
}

# --------------------------------------------------------------------------- #
# Step 1: initial --apply propagates baseline content into all 3 hosts        #
# --------------------------------------------------------------------------- #

it "initial sync --apply exits 0"
run_sync >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}"

for h in "${CLAUDE_HOME_T}/CLAUDE.md" "${CODEX_HOME_T}/AGENTS.md" \
         "${AGENT_CREW_HOME_T}/AGENTS.md"; do
  base=$(basename "${h}")
  it "host ${base} contains baseline content after initial sync"
  content=$(cat "${h}")
  assert_contains "${content}" "BASELINE content"
  it "host ${base} preserved user-intro content"
  assert_contains "${content}" "User custom intro"
done

# --------------------------------------------------------------------------- #
# Step 2: edit mnemos rule (add marker), sync, verify marker in all hosts     #
# --------------------------------------------------------------------------- #

"${MNEMOS}" edit "rule:test-structured-choice" --content "---
title: Test Structured Choice
applies_to: [all]
priority: 50
---

This is the BASELINE content.

INTEGRATION_TEST_MARKER_XYZ"

it "post-edit sync --apply exits 0"
run_sync >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}"

for h in "${CLAUDE_HOME_T}/CLAUDE.md" "${CODEX_HOME_T}/AGENTS.md" \
         "${AGENT_CREW_HOME_T}/AGENTS.md"; do
  base=$(basename "${h}")
  it "host ${base} now contains INTEGRATION_TEST_MARKER_XYZ"
  content=$(cat "${h}")
  assert_contains "${content}" "INTEGRATION_TEST_MARKER_XYZ"
done

# --------------------------------------------------------------------------- #
# Step 3: revert mnemos rule, sync, verify marker gone from all hosts         #
# --------------------------------------------------------------------------- #

"${MNEMOS}" edit "rule:test-structured-choice" --content "---
title: Test Structured Choice
applies_to: [all]
priority: 50
---

This is the BASELINE content."

it "post-revert sync --apply exits 0"
run_sync >/dev/null 2>&1
rc=$?
assert_exit 0 "${rc}"

for h in "${CLAUDE_HOME_T}/CLAUDE.md" "${CODEX_HOME_T}/AGENTS.md" \
         "${AGENT_CREW_HOME_T}/AGENTS.md"; do
  base=$(basename "${h}")
  it "host ${base} no longer contains INTEGRATION_TEST_MARKER_XYZ"
  content=$(cat "${h}")
  assert_not_contains "${content}" "INTEGRATION_TEST_MARKER_XYZ"
  it "host ${base} still contains BASELINE content (regression guard)"
  assert_contains "${content}" "BASELINE content"
  it "host ${base} still contains user-intro (outside-marker preservation)"
  assert_contains "${content}" "User custom intro"
done

end_report
