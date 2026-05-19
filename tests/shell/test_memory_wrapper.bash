#!/usr/bin/env bash
# Tests for core/bin/memory wrapper behavior.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

MEMORY="${REPO_ROOT}/core/bin/memory"

TMP=$(make_tmp)
cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = "capture" ]; then
  cat <<'OUT'
captured memory id: 0716384d-091f-4279-838f-73d54785767a
error: git command failed (rc=1): remote rejected main -> main (cannot lock ref)
error: failed to push some refs
OUT
  exit 1
fi
printf 'mnemos %s\n' "$*"
exit 0
SH
chmod +x "${TMP}/mnemos"

it "memory capture returns success when local capture id exists but vault push failed"
OUTPUT=$(PATH="${TMP}:${PATH}" bash "${MEMORY}" capture --layer session --content "probe" 2>&1)
rc=$?
assert_exit 0 "${rc}" "nonfatal sync failure"

it "memory capture emits local capture warning"
assert_contains "${OUTPUT}" "[memory] captured locally: 0716384d-091f-4279-838f-73d54785767a"

it "memory capture emits vault sync warning"
assert_contains "${OUTPUT}" "[memory] warning: vault sync failed"

cat > "${TMP}/mnemos" <<'SH'
#!/usr/bin/env bash
if [ "${1:-}" = "capture" ]; then
  echo "fatal: invalid arguments"
  exit 7
fi
exit 0
SH
chmod +x "${TMP}/mnemos"

it "memory capture preserves non-sync failures"
PATH="${TMP}:${PATH}" bash "${MEMORY}" capture --bad >/dev/null 2>&1
rc=$?
assert_exit 7 "${rc}" "non-sync capture failure"

end_report
