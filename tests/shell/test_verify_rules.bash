#!/usr/bin/env bash
# Tests for core/hooks/verify-rules.sh language-agnostic quality checks.
#
# Spec: prd.md § "Core Feature List" / "Acceptance Criteria" AC-001..AC-005 —
# make_payload() and its siblings below emit the real flattened envelope
# shape produced by core/scripts/post-tool-use-dispatcher.py (top-level
# file_path/new_path/path, no tool_input wrapper), plus the legacy nested
# tool_input shape kept as a defensive fallback.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"

HOOK="${HOOKS_DIR}/verify-rules.sh"

# Builds a flattened top-level envelope from key=value pairs, e.g.
#   make_flat_payload file_path=/tmp/a.py new_path=/tmp/b.py
# A key that is never passed is omitted from the JSON entirely; a key passed
# as "key=" is present with an empty-string value. This distinguishes
# "absent" from "present but empty" (AC-002 / TC-006 vs TC-015).
make_flat_payload() {
  python3 -c "
import json, sys
data = {}
for pair in sys.argv[1:]:
    key, _, value = pair.partition('=')
    data[key] = value
print(json.dumps(data))
" "$@"
}

# Builds the legacy nested {'tool_input': {...}} shape — the AC-003
# defensive fallback — from key=value pairs nested under tool_input.
make_legacy_payload() {
  python3 -c "
import json, sys
data = {}
for pair in sys.argv[1:]:
    key, _, value = pair.partition('=')
    data[key] = value
print(json.dumps({'tool_input': data}))
" "$@"
}

# make_payload(): the flattened shape's minimal, single-field form —
# {"file_path": "<path>"} — matching the PRD's Core Feature List wording
# exactly. This is the shape the 5 pre-existing regression assertions below
# (TC-001..TC-005) exercise.
make_payload() {
  local file_path="$1"
  make_flat_payload "file_path=${file_path}"
}

run_payload() {
  local payload="$1"
  printf '%s' "${payload}" | bash "${HOOK}" 2>&1
}

run_payload_rc() {
  local payload="$1"
  printf '%s' "${payload}" | bash "${HOOK}" >/dev/null 2>&1
  echo $?
}

run_hook() {
  local file_path="$1"
  run_payload "$(make_payload "${file_path}")"
}

run_hook_rc() {
  local file_path="$1"
  run_payload_rc "$(make_payload "${file_path}")"
}

TMP=$(make_tmp)

it "fast-path: agent-crew state artifacts bypass source-rule scans"
AGENT_HOME="$(make_tmp)"
STATE_FILE="${AGENT_HOME}/state/project/tasks/demo/context/verification.py"
mkdir -p "$(dirname "${STATE_FILE}")"
printf 'else:\n' > "${STATE_FILE}"
FAKE_BIN="$(make_tmp)"
mkdir -p "${FAKE_BIN}"
GREP_LOG="${FAKE_BIN}/grep-called.log"
cat > "${FAKE_BIN}/grep" <<SH
#!/usr/bin/env bash
printf 'grep called\n' >> "${GREP_LOG}"
exit 1
SH
chmod +x "${FAKE_BIN}/grep"
out=$(PATH="${FAKE_BIN}:${PATH}" AGENT_CREW_HOME="${AGENT_HOME}" run_payload "$(make_payload "${STATE_FILE}")")
rc=$?
assert_exit 0 "${rc}" "agent-crew state artifact ignored"
assert_eq "" "${out}" "agent-crew state artifact emits no violation"
assert_file_absent "${GREP_LOG}"

JSP_FILE="${TMP}/legacy.jsp"
cat > "${JSP_FILE}" <<'EOF'
<%
if (value == null) {
    result = "";
} else {
    result = value.substring(0, 2);
}
%>
EOF

# --- TC-001 / AC-001 + AC-005 ---
# given: a flattened envelope whose top-level file_path points at a JSP file
#        with a bare else clause
# when:  verify-rules.sh runs against it
# then:  CHANGED_FILE resolves and the script exits 2 for the else violation
it "failure-case(validation) - JSP code with a bare else is flagged once CHANGED_FILE resolves from the flattened file_path"
rc=$(run_hook_rc "${JSP_FILE}")
assert_exit 2 "${rc}" "JSP else violation"

# then: the violation message names Object Calisthenics #2
it "failure-case(validation) - JSP else violation reports Object Calisthenics #2"
out=$(run_hook "${JSP_FILE}")
assert_contains "${out}" "Object Calisthenics #2" "JSP else output"

PY_ELIF_FILE="${TMP}/routing.py"
cat > "${PY_ELIF_FILE}" <<'EOF'
def route(value):
    if value == "a":
        return "A"
    elif value == "b":
        return "B"
    return "other"
EOF

# given: a flattened envelope's file_path points at Python using elif (no
#        bare else)
# when:  verify-rules.sh runs
# then:  no false-positive else-usage violation; exits 0
it "success-case - Python elif is not falsely flagged as else"
rc=$(run_hook_rc "${PY_ELIF_FILE}")
assert_exit 0 "${rc}" "Python elif"

PY_ELSE_FILE="${TMP}/branching.py"
cat > "${PY_ELSE_FILE}" <<'EOF'
def route(value):
    if value:
        return value
    else:
        return ""
EOF

# given: a flattened envelope's file_path points at Python with a bare else
# when:  verify-rules.sh runs
# then:  else-usage is flagged; exits 2
it "failure-case(validation) - Python else statements are checked via the flattened file_path"
rc=$(run_hook_rc "${PY_ELSE_FILE}")
assert_exit 2 "${rc}" "Python else"

MD_FILE="${TMP}/notes.md"
cat > "${MD_FILE}" <<'EOF'
# Notes

The word else in documentation should not be treated as source code.
EOF

# given: a flattened envelope's file_path points at Markdown prose containing
#        the word "else" outside of code
# when:  verify-rules.sh runs
# then:  no false-positive violation; exits 0
it "boundary-case(contract) - Markdown prose is not treated as source code"
rc=$(run_hook_rc "${MD_FILE}")
assert_exit 0 "${rc}" "Markdown prose"

TS_FILE="${TMP}/component.ts"
cat > "${TS_FILE}" <<'EOF'
export function read(value: any) {
  return value
}
EOF

# given: a flattened envelope's file_path points at TypeScript using `any`
# when:  verify-rules.sh runs
# then:  the existing TypeScript any rule still applies; exits 2
it "failure-case(validation) - existing TypeScript any rule still applies via the flattened file_path"
rc=$(run_hook_rc "${TS_FILE}")
assert_exit 2 "${rc}" "TypeScript any"

# --- TC-006 / AC-002: new_path fallback when file_path is absent ---

# given: a flattened envelope where file_path is absent entirely and new_path
#        points at the JSP else-violation file
# when:  verify-rules.sh runs
# then:  CHANGED_FILE resolves to new_path and the else-usage check runs
it "boundary-case(contract) - new_path is used when file_path is absent"
PAYLOAD=$(make_flat_payload "new_path=${JSP_FILE}")
rc=$(run_payload_rc "${PAYLOAD}")
assert_exit 2 "${rc}" "new_path fallback exit"

it "boundary-case(contract) - new_path fallback still runs the else-usage check"
out=$(run_payload "${PAYLOAD}")
assert_contains "${out}" "Object Calisthenics #2" "new_path fallback output"

# --- TC-007 / AC-002: path fallback when file_path and new_path are absent ---

# given: a flattened envelope where only path is populated
# when:  verify-rules.sh runs
# then:  CHANGED_FILE resolves to path and the else-usage check runs
it "boundary-case(contract) - path is used when both file_path and new_path are absent"
PAYLOAD=$(make_flat_payload "path=${JSP_FILE}")
rc=$(run_payload_rc "${PAYLOAD}")
assert_exit 2 "${rc}" "path fallback exit"

it "boundary-case(contract) - path fallback still runs the else-usage check"
out=$(run_payload "${PAYLOAD}")
assert_contains "${out}" "Object Calisthenics #2" "path fallback output"

# --- TC-008 / AC-002: file_path takes precedence over new_path ---

# given: a flattened envelope with file_path pointing at the JSP else
#        violation and new_path pointing at the clean Python elif file
# when:  verify-rules.sh runs
# then:  CHANGED_FILE resolves to file_path (JSP), not new_path — proven by
#        the else-usage violation firing rather than a clean exit
it "boundary-case(contract) - file_path takes precedence over new_path when both are present"
PAYLOAD=$(make_flat_payload "file_path=${JSP_FILE}" "new_path=${PY_ELIF_FILE}")
rc=$(run_payload_rc "${PAYLOAD}")
assert_exit 2 "${rc}" "file_path precedence exit"

it "boundary-case(contract) - file_path precedence resolves to the JSP else violation, not the clean new_path file"
out=$(run_payload "${PAYLOAD}")
assert_contains "${out}" "Object Calisthenics #2" "file_path precedence output"

# --- TC-009 / AC-003: legacy nested tool_input.file_path defensive fallback ---

# given: the legacy nested shape ({"tool_input": {"file_path": ...}}) with no
#        top-level file_path/new_path/path keys at all
# when:  verify-rules.sh runs
# then:  CHANGED_FILE still resolves via the defensive nested fallback
it "boundary-case(regression) - legacy nested tool_input.file_path still resolves"
PAYLOAD=$(make_legacy_payload "file_path=${JSP_FILE}")
rc=$(run_payload_rc "${PAYLOAD}")
assert_exit 2 "${rc}" "legacy nested file_path exit"

it "boundary-case(regression) - legacy nested tool_input.file_path still runs the else-usage check"
out=$(run_payload "${PAYLOAD}")
assert_contains "${out}" "Object Calisthenics #2" "legacy nested file_path output"

# --- TC-010 / AC-003: legacy nested tool_input.new_path ordering ---

# given: the legacy nested shape with only tool_input.new_path set (no
#        tool_input.file_path, no top-level keys)
# when:  verify-rules.sh runs
# then:  CHANGED_FILE resolves via the nested fallback's own file_path-first
#        preference, landing on new_path since file_path is absent
it "boundary-case(regression) - legacy nested tool_input.new_path resolves when tool_input.file_path is absent"
PAYLOAD=$(make_legacy_payload "new_path=${JSP_FILE}")
rc=$(run_payload_rc "${PAYLOAD}")
assert_exit 2 "${rc}" "legacy nested new_path exit"

it "boundary-case(regression) - legacy nested tool_input.new_path still runs the else-usage check"
out=$(run_payload "${PAYLOAD}")
assert_contains "${out}" "Object Calisthenics #2" "legacy nested new_path output"

# --- TC-011 / AC-004: no resolvable path field anywhere ---

# given: a flattened envelope with unrelated top-level fields only (no
#        file_path/new_path/path/tool_input at all)
# when:  verify-rules.sh runs
# then:  CHANGED_FILE resolves empty; the script exits 0 with no output
it "boundary-case(contract) - no resolvable path anywhere exits 0"
PAYLOAD=$(make_flat_payload "tool_name=Edit" "cwd=${TMP}")
rc=$(run_payload_rc "${PAYLOAD}")
assert_exit 0 "${rc}" "no path exit"

it "boundary-case(contract) - no resolvable path anywhere produces no output"
out=$(run_payload "${PAYLOAD}")
assert_eq "" "${out}" "no path output"

# --- TC-012 / AC-004: invalid/unparseable JSON on stdin ---

# given: unparseable JSON on stdin
# when:  verify-rules.sh runs
# then:  CHANGED_FILE resolves empty (parse failure treated as no path
#        found); the script exits 0 with no output and does not crash
it "failure-case(contract) - invalid JSON exits 0 without crashing"
rc=$(run_payload_rc 'not-valid-json{{{')
assert_exit 0 "${rc}" "invalid JSON exit"

it "failure-case(contract) - invalid JSON produces no output"
out=$(run_payload 'not-valid-json{{{')
assert_eq "" "${out}" "invalid JSON output"

# --- TC-013 / AC-004: file_path resolves but the file does not exist ---

# given: a flattened envelope whose file_path points at a path that was never
#        created on disk
# when:  verify-rules.sh runs
# then:  the untouched "! -f" existence guard still short-circuits; exits 0
#        with no output
MISSING_FILE="${TMP}/does-not-exist.py"

it "boundary-case(contract) - a resolved but nonexistent file_path exits 0"
rc=$(run_hook_rc "${MISSING_FILE}")
assert_exit 0 "${rc}" "nonexistent file exit"

it "boundary-case(contract) - a resolved but nonexistent file_path produces no output"
out=$(run_hook "${MISSING_FILE}")
assert_eq "" "${out}" "nonexistent file output"

# --- TC-015 / AC-002: file_path present but empty string still falls back ---

# given: a flattened envelope where file_path is present but set to "", and
#        new_path is populated with the JSP else-violation file
# when:  verify-rules.sh runs
# then:  the empty-string file_path is treated as absent (not resolved
#        as-is); CHANGED_FILE falls back to new_path
it "boundary-case(contract) - an empty-string file_path is treated as absent, falling back to new_path"
PAYLOAD=$(make_flat_payload "file_path=" "new_path=${JSP_FILE}")
rc=$(run_payload_rc "${PAYLOAD}")
assert_exit 2 "${rc}" "empty file_path fallback exit"

it "boundary-case(contract) - empty-string file_path fallback still runs the else-usage check"
out=$(run_payload "${PAYLOAD}")
assert_contains "${out}" "Object Calisthenics #2" "empty file_path fallback output"

end_report
