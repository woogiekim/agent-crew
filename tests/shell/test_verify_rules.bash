#!/usr/bin/env bash
# Tests for core/hooks/verify-rules.sh language-agnostic quality checks.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"

HOOK="${HOOKS_DIR}/verify-rules.sh"

make_payload() {
  local file_path="$1"
  python3 -c "
import json, sys
print(json.dumps({'tool_input': {'file_path': sys.argv[1]}}))
" "${file_path}"
}

run_hook() {
  local file_path="$1"
  make_payload "${file_path}" | bash "${HOOK}" 2>&1
}

run_hook_rc() {
  local file_path="$1"
  make_payload "${file_path}" | bash "${HOOK}" >/dev/null 2>&1
  echo $?
}

TMP=$(make_tmp)

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

it "JSP code is checked for language-agnostic no-else violations"
rc=$(run_hook_rc "${JSP_FILE}")
assert_exit 2 "${rc}" "JSP else violation"

it "JSP violation reports Object Calisthenics"
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

it "Python elif is not falsely flagged as else"
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

it "Python else statements are checked"
rc=$(run_hook_rc "${PY_ELSE_FILE}")
assert_exit 2 "${rc}" "Python else"

MD_FILE="${TMP}/notes.md"
cat > "${MD_FILE}" <<'EOF'
# Notes

The word else in documentation should not be treated as source code.
EOF

it "Markdown prose is not treated as source code"
rc=$(run_hook_rc "${MD_FILE}")
assert_exit 0 "${rc}" "Markdown prose"

TS_FILE="${TMP}/component.ts"
cat > "${TS_FILE}" <<'EOF'
export function read(value: any) {
  return value
}
EOF

it "Existing TypeScript any rule still applies"
rc=$(run_hook_rc "${TS_FILE}")
assert_exit 2 "${rc}" "TypeScript any"

end_report
