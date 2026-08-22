#!/usr/bin/env bash
# Focused contract tests for instruction reconciliation in native crew update.

set -u
source "$(dirname "$0")/_lib.bash"

TMP=$(make_tmp)
INSTALL="${TMP}/install"
SOURCE="${TMP}/source"
PROJECT="${TMP}/project"
CALL_LOG="${TMP}/calls.log"
MNEMOS="${TMP}/mnemos"

mkdir -p \
  "${INSTALL}/bin" \
  "${INSTALL}/commands" \
  "${INSTALL}/scripts" \
  "${SOURCE}/core/scripts" \
  "${PROJECT}"
cp "${REPO_ROOT}/core/bin/crew" "${INSTALL}/bin/crew"

cat > "${SOURCE}/core/scripts/seed-instruction-rules.sh" <<'EOF'
#!/usr/bin/env bash
printf 'seed:%s\n' "$*" >> "${UPDATE_CALL_LOG}"
if [ "${FAIL_SEED:-0}" = "1" ]; then
  exit 9
fi
EOF
cat > "${SOURCE}/core/scripts/sync-instructions.sh" <<'EOF'
#!/usr/bin/env bash
printf 'instructions:%s\n' "$*" >> "${UPDATE_CALL_LOG}"
EOF
cat > "${INSTALL}/scripts/sync-local-install.sh" <<'EOF'
#!/usr/bin/env bash
printf 'install:%s\n' "$*" >> "${UPDATE_CALL_LOG}"
EOF
cat > "${MNEMOS}" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x \
  "${INSTALL}/bin/crew" \
  "${SOURCE}/core/scripts/seed-instruction-rules.sh" \
  "${SOURCE}/core/scripts/sync-instructions.sh" \
  "${INSTALL}/scripts/sync-local-install.sh" \
  "${MNEMOS}"

it "crew update refreshes runtime instructions before installing assets"
out=$(UPDATE_CALL_LOG="${CALL_LOG}" MNEMOS_BIN="${MNEMOS}" \
  AGENT_CREW_HOME="${INSTALL}" PROJECT_ROOT="${PROJECT}" \
  bash "${INSTALL}/bin/crew" update --local "${SOURCE}" 2>&1)
rc=$?
assert_exit 0 "${rc}"

calls="$(cat "${CALL_LOG}" 2>/dev/null || true)"

it "crew update selects only the runtime command profile"
assert_contains "${calls}" "seed:--apply --profile runtime-command-surface"

it "crew update syncs host instruction mirrors"
assert_contains "${calls}" "instructions:--hosts claude,codex,generic --apply"

it "crew update orders instruction reconciliation before asset installation"
first="$(sed -n '1p' "${CALL_LOG}")"
second="$(sed -n '2p' "${CALL_LOG}")"
third="$(sed -n '3p' "${CALL_LOG}")"
assert_eq "seed:--apply --profile runtime-command-surface" "${first}"
assert_eq "instructions:--hosts claude,codex,generic --apply" "${second}"
assert_contains "${third}" "install:${SOURCE} ${PROJECT}"

it "crew update reports synchronized instruction state"
assert_contains "${out}" "update_instructions: runtime command rules and host files synchronized"

: > "${CALL_LOG}"

it "crew update skips host materialization after seed failure"
out=$(FAIL_SEED=1 UPDATE_CALL_LOG="${CALL_LOG}" MNEMOS_BIN="${MNEMOS}" \
  AGENT_CREW_HOME="${INSTALL}" PROJECT_ROOT="${PROJECT}" \
  bash "${INSTALL}/bin/crew" update --local "${SOURCE}" 2>&1)
rc=$?
assert_exit 0 "${rc}"
calls="$(cat "${CALL_LOG}" 2>/dev/null || true)"
assert_contains "${calls}" "seed:--apply --profile runtime-command-surface"
assert_not_contains "${calls}" "instructions:"
assert_contains "${calls}" "install:${SOURCE} ${PROJECT}"
assert_contains "${out}" "host instruction sync skipped"

end_report
