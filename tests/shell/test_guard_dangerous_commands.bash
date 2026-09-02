#!/usr/bin/env bash
# Tests for deterministic dangerous command blocking and audit trail.

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"
set +e

HOOK="${HOOKS_DIR}/guard-dangerous-commands.sh"

payload_for() {
  local cmd="$1"
  python3 -c '
import json, sys
print(json.dumps({"tool_name": "exec_command", "tool_input": {"cmd": sys.argv[1]}}))
' "${cmd}"
}

run_hook() {
  local payload="$1"
  shift
  printf '%s' "${payload}" | env "$@" bash "${HOOK}" 2>&1
}

run_hook_split() {
  local payload="$1"
  local stdout_file="$2"
  local stderr_file="$3"
  shift 3
  printf '%s' "${payload}" | env "$@" bash "${HOOK}" >"${stdout_file}" 2>"${stderr_file}"
}

write_approval() {
  local home="$1"
  local kind="$2"
  local cmd="$3"
  mkdir -p "${home}/approvals"
  python3 -c '
import json, pathlib, sys
from datetime import datetime, timedelta, timezone
path = pathlib.Path(sys.argv[1]) / "approvals" / "dangerous-commands.approved"
path.write_text(json.dumps({
    "approved": True,
    "kind": sys.argv[2],
    "command": sys.argv[3],
    "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
}) + "\n", encoding="utf-8")
' "${home}" "${kind}" "${cmd}"
}

TMP_HOME=$(make_tmp)

READ_ONLY_TASK_DIR=$(make_tmp)
cat > "${READ_ONLY_TASK_DIR}/register.json" <<'EOF'
{
  "mutation_scope": "read_only"
}
EOF

it "read-only task allows a read-only shell inspection"
out=$(run_hook "$(payload_for "git status --short")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
rc=$?
assert_exit 0 "${rc}"
assert_eq "" "${out}" "read-only inspection should remain available"

it "read-only task allows Git branch tag and stash inspection forms"
for command in "git branch --show-current" "git tag --list" "git stash list"; do
  out=$(run_hook "$(payload_for "${command}")" \
    "AGENT_CREW_HOME=${TMP_HOME}" \
    "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
  rc=$?
  if [ "${rc}" -ne 0 ] || [ -n "${out}" ]; then
    _fail "safe Git inspection was blocked: ${command}"
  else
    _pass
  fi
done

it "read-only task blocks Git branch creation"
out=$(run_hook "$(payload_for "git branch feature/read-only-escape")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: read-only-git-mutation"

it "read-only task blocks Git state mutation before specialist or approval checks"
out=$(run_hook "$(payload_for "git add core/bin/crew")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: read-only-git-mutation"

it "read-only task blocks Git mutation behind an environment assignment"
out=$(run_hook "$(payload_for "TRACE=1 git add core/bin/crew")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: read-only-git-mutation"

it "read-only task blocks Memory mutation"
out=$(run_hook "$(payload_for 'mnemos capture --content "decision" --layer session')" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: read-only-memory-mutation"

it "read-only task blocks Memory mutation behind env"
out=$(run_hook "$(payload_for 'env mnemos capture --content "decision" --layer session')" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: read-only-memory-mutation"

it "read-only task blocks filesystem redirection"
out=$(run_hook "$(payload_for "printf changed > core/bin/crew")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: read-only-filesystem-mutation"

it "read-only task allows shell writes inside its own task state directory"
mkdir -p "${READ_ONLY_TASK_DIR}/context"
out=$(run_hook "$(payload_for "printf evidence > ${READ_ONLY_TASK_DIR}/context/evidence.md")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
rc=$?
assert_exit 0 "${rc}"
assert_eq "" "${out}" "task-local evidence writes remain inside the read-only contract"

it "read-only task does not let task-local redirection hide an external file mutation"
out=$(run_hook "$(payload_for "rm project-file > ${READ_ONLY_TASK_DIR}/context/evidence.md")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: read-only-filesystem-mutation"

it "read-only task does not allow moving an external file into task state"
out=$(run_hook "$(payload_for "mv project-file ${READ_ONLY_TASK_DIR}/context/moved-file")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: read-only-filesystem-mutation"

it "read-only task blocks filesystem mutation behind env"
out=$(run_hook "$(payload_for "env rm project-file")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: read-only-filesystem-mutation"

it "read-only task allows its active marker lifecycle paths"
out=$(run_hook "$(payload_for 'touch "${TASKS_DIR}/active.${TASK_ID}"')" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
rc=$?
assert_exit 0 "${rc}"
assert_eq "" "${out}" "supervisor marker lifecycle remains task-local state"

it "read-only task rejects task directory traversal into project state"
out=$(run_hook "$(payload_for 'touch "${TASK_DIR}/../../project-file"')" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: read-only-filesystem-mutation"

it "read-only task blocks an external HTTP mutation"
out=$(run_hook "$(payload_for "curl -X POST https://example.test/items")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: read-only-external-mutation"

it "read-only task blocks external HTTP mutation behind env"
out=$(run_hook "$(payload_for "env curl -X POST https://example.test/items")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: read-only-external-mutation"

it "read-only task blocks implicit curl upload and API mutation forms"
for command in \
  "curl -d name=value https://example.test/items" \
  "curl -F file=@artifact https://example.test/items" \
  "curl -T artifact https://example.test/items" \
  "gh api repos/example/project/issues/1 --method PATCH -f title=changed" \
  "glab api projects/1/issues/1 -X DELETE"; do
  out=$(run_hook "$(payload_for "${command}")" \
    "AGENT_CREW_HOME=${TMP_HOME}" \
    "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
  rc=$?
  if [ "${rc}" -ne 2 ] || [[ "${out}" != *"Kind: read-only-external-mutation"* ]]; then
    _fail "external mutation was not blocked: ${command}"
  else
    _pass
  fi
done

it "read-only task allows external GET query forms"
for command in \
  "curl -G -d name=value https://example.test/items" \
  "gh api repos/example/project/issues --method GET -f state=open"; do
  out=$(run_hook "$(payload_for "${command}")" \
    "AGENT_CREW_HOME=${TMP_HOME}" \
    "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
  rc=$?
  if [ "${rc}" -ne 0 ] || [ -n "${out}" ]; then
    _fail "external read-only request was blocked: ${command}"
  else
    _pass
  fi
done

it "read-only task blocks external mutation in shell substitutions and env options"
for command in \
  'echo $(curl -d name=value https://example.test/items)' \
  'echo `curl -d name=value https://example.test/items`' \
  'echo "$(curl -d name=value https://example.test/items)"' \
  'cat <(curl -d name=value https://example.test/items)' \
  'printf output >(curl -d name=value https://example.test/items)' \
  'env -u TOKEN curl -d name=value https://example.test/items' \
  'env --unset=TOKEN gh api repos/example/project/issues/1 --method PATCH -f title=changed' \
  'env --split-string="curl -d name=value https://example.test/items"'; do
  out=$(run_hook "$(payload_for "${command}")" \
    "AGENT_CREW_HOME=${TMP_HOME}" \
    "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
  rc=$?
  if [ "${rc}" -ne 2 ] || [[ "${out}" != *"Kind: read-only-external-mutation"* ]]; then
    _fail "nested external mutation was not blocked: ${command}"
  else
    _pass
  fi
done

it "read-only task ignores quoted external mutation examples"
for command in \
  'printf %s '\''$(curl -d name=value https://example.test/items)'\''' \
  'printf %s '\''<(curl -d name=value https://example.test/items)'\'''; do
  out=$(run_hook "$(payload_for "${command}")" \
    "AGENT_CREW_HOME=${TMP_HOME}" \
    "AGENT_CREW_TASK_DIR=${READ_ONLY_TASK_DIR}")
  rc=$?
  if [ "${rc}" -ne 0 ] || [ -n "${out}" ]; then
    _fail "single-quoted command example was not inert: ${command}"
  else
    _pass
  fi
done

it "git push is blocked without deterministic approval"
out=$(run_hook "$(payload_for "git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"

it "git push block output identifies push kind"
assert_contains "${out}" "Kind: push"

it "git push block reason is written to stderr"
STDOUT_FILE="$(make_tmp)/stdout"
STDERR_FILE="$(make_tmp)/stderr"
run_hook_split "$(payload_for "git push origin main")" "${STDOUT_FILE}" "${STDERR_FILE}" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_APPROVED_DANGEROUS="
rc=$?
assert_exit 2 "${rc}"
assert_eq "" "$(cat "${STDOUT_FILE}")" "stdout must be empty on block"
assert_contains "$(cat "${STDERR_FILE}")" "Kind: push" "stderr contains block reason"

it "every dangerous command block path writes its reason to stderr"
while IFS='|' read -r label command expected; do
  [ -n "${label}" ] || continue
  STDOUT_FILE="$(make_tmp)/stdout"
  STDERR_FILE="$(make_tmp)/stderr"
  run_hook_split "$(payload_for "${command}")" "${STDOUT_FILE}" "${STDERR_FILE}" \
    "AGENT_CREW_HOME=${TMP_HOME}" \
    "AGENT_CREW_APPROVED_DANGEROUS="
  rc=$?
  if [ "${rc}" -ne 2 ]; then
    _fail "${label}: expected exit=2 actual=${rc}"
    continue
  fi
  if [ -s "${STDOUT_FILE}" ]; then
    _fail "${label}: stdout must be empty on block"
    continue
  fi
  stderr="$(cat "${STDERR_FILE}")"
  case "${stderr}" in
    *'"decision": "block"'*"${expected}"*) _pass ;;
    *) _fail "${label}: missing block reason on stderr: ${stderr:0:200}" ;;
  esac
done <<'EOF'
destructive root delete|rm -rf /|Kind: destructive-delete
destructive home delete|rm -rf ~|Kind: destructive-delete
destructive env home delete|rm -rf $HOME|Kind: destructive-delete
disk format|mkfs /dev/sdb|Kind: disk-format
raw disk read|dd if=/dev/zero of=/tmp/out|Kind: raw-disk-write
raw disk write redirection|printf x > /dev/sda|Kind: raw-disk-write
git push|git push origin main|Kind: push
git merge|git merge feature/example|Kind: merge
deploy script|./deploy.sh production|Kind: deploy
npm deploy|npm run deploy|Kind: deploy
EOF

it "forbidden command policy denies sudo without approval path"
out=$(run_hook "$(payload_for "sudo whoami")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Forbidden command pattern detected"
assert_contains "${out}" "Kind: sudo"

it "forbidden command policy denies git force push"
out=$(run_hook "$(payload_for "git push --force-with-lease origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: force-push"

it "forbidden command policy denies credential access"
out=$(run_hook "$(payload_for "gh auth token")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: credential-access"

it "forbidden command policy ignores quoted documentation text"
out=$(run_hook "$(payload_for 'grep "sudo" core/hooks/guard-dangerous-commands.sh')" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 0 "${rc}"
assert_eq "" "${out}" "quoted documentation search should not be blocked"

it "fork bomb block path writes its reason to stderr"
STDOUT_FILE="$(make_tmp)/stdout"
STDERR_FILE="$(make_tmp)/stderr"
run_hook_split "$(payload_for ':(){ :|:& };:')" "${STDOUT_FILE}" "${STDERR_FILE}" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_APPROVED_DANGEROUS="
rc=$?
assert_exit 2 "${rc}"
assert_eq "" "$(cat "${STDOUT_FILE}")" "stdout must be empty on block"
assert_contains "$(cat "${STDERR_FILE}")" "Kind: fork-bomb" "stderr contains block reason"

it "git push block writes audit trail"
audit=$(cat "${TMP_HOME}/audit/dangerous-commands.jsonl")
assert_contains "${audit}" '"decision": "block"'

it "environment approval does not bypass git push"
out=$(run_hook "$(payload_for "git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=1")
rc=$?
assert_exit 2 "${rc}"

it "command-bound approval marker allows git push"
write_approval "${TMP_HOME}" "push" "git push origin main"
out=$(run_hook "$(payload_for "git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 0 "${rc}"

it "command-bound approval writes allow audit trail"
audit=$(cat "${TMP_HOME}/audit/dangerous-commands.jsonl")
assert_contains "${audit}" '"decision": "allow"'

it "command-bound approval marker is consumed after use"
assert_file_absent "${TMP_HOME}/approvals/dangerous-commands.approved"

it "command-bound approval tolerates one duplicate hook invocation"
write_approval "${TMP_HOME}" "push" "git push origin main"
payload="$(payload_for "git push origin main")"
out=$(run_hook "${payload}" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 0 "${rc}" "first hook pass should use fresh approval"
out=$(run_hook "${payload}" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 0 "${rc}" "second duplicate hook pass should use consumed approval grace"
out=$(run_hook "${payload}" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}" "third hook pass must not reuse consumed approval"

it "approval JSON write containing git push literal is allowed"
approval_cmd=$(cat <<EOF
mkdir -p ${TMP_HOME}/approvals
printf '{"approved":true,"kind":"push","command":"git push origin main","expires_at":"2999-01-01T00:00:00Z"}\n' > ${TMP_HOME}/approvals/dangerous-commands.approved
EOF
)
out=$(run_hook "$(payload_for "${approval_cmd}")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 0 "${rc}"
assert_eq "" "${out}" "approval marker write should not be blocked"

it "crew run task text mentioning git push is allowed"
out=$(run_hook "$(payload_for 'crew run "Fix guard false positive for git push approval JSON"')" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 0 "${rc}"

it "shell evaluator running quoted git push is blocked"
out=$(run_hook "$(payload_for 'bash -lc "git push origin main"')" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: push"

it "inline approval env prefix does not self-approve git push"
out=$(run_hook "$(payload_for "AGENT_CREW_APPROVED_DANGEROUS=1 git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: push"

COMMIT_PROJECT="$(make_tmp)"
COMMIT_TASK_DIR="$(make_tmp)"
mkdir -p "${COMMIT_PROJECT}/.agent-crew/agents" "${COMMIT_TASK_DIR}/context"
printf '# git-committer\n' > "${COMMIT_PROJECT}/.agent-crew/agents/git-committer.md"

write_capability_result() {
  local task_dir="$1"
  local capability="$2"
  local handler="$3"
  mkdir -p "${task_dir}/context/capabilities"
  python3 -c '
import json, pathlib, sys
capability = sys.argv[2]
path = pathlib.Path(sys.argv[1]) / "context" / "capabilities" / f"{capability}.json"
path.write_text(json.dumps({
    "capability": capability,
    "handler": sys.argv[3],
    "state": "completed",
    "artifact": f"context/capabilities/{capability}.json",
}) + "\n", encoding="utf-8")
' "${task_dir}" "${capability}" "${handler}"
}

it "git commit is blocked when commit message capability dispatch is missing in task context"
out=$(run_hook "$(payload_for "git commit -m 'fix: demo'")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${COMMIT_TASK_DIR}" \
  "AGENT_CREW_PROJECT_ROOT=${COMMIT_PROJECT}" \
  "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: commit-specialist"
assert_contains "${out}" "vcs.commit.message.compose"
assert_not_contains "${out}" "selected_user_agent: git-committer"

cat > "${COMMIT_TASK_DIR}/context/specialist-dispatch.md" <<'EOF'
selected_agent: backend
selected_user_agent: git-committer
selection_reason: commit request
execution_mode: current_session_required fallback
EOF

it "git commit blocks legacy git-committer selection without capability completion"
out=$(run_hook "$(payload_for "git commit -m 'fix: demo'")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${COMMIT_TASK_DIR}" \
  "AGENT_CREW_PROJECT_ROOT=${COMMIT_PROJECT}" \
  "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Commit capability completion"

write_capability_result "${COMMIT_TASK_DIR}" "vcs.commit.message.compose" "git-committer"

it "git commit accepts legacy git-committer user-agent after capability completion"
out=$(run_hook "$(payload_for "git commit -m 'fix: demo'")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${COMMIT_TASK_DIR}" \
  "AGENT_CREW_PROJECT_ROOT=${COMMIT_PROJECT}" \
  "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 0 "${rc}"
assert_eq "" "${out}" "legacy user-agent evidence with completion should satisfy commit capability evidence"

COMMIT_TASK_DIR_WITH_CAPABILITY="$(make_tmp)"
mkdir -p "${COMMIT_TASK_DIR_WITH_CAPABILITY}/context"
cat > "${COMMIT_TASK_DIR_WITH_CAPABILITY}/context/specialist-dispatch.json" <<'EOF'
{
  "selected_agent": "supervisor",
  "selected_handlers": [
    {
      "capability": "vcs.commit.message.compose",
      "handler": "git-committer"
    },
    {
      "capability": "vcs.history.local_mutation",
      "handler": "git"
    }
  ],
  "selection_reason": "commit request capability handlers",
  "execution_mode": "current_session_required fallback"
}
EOF

it "git commit blocks selected handlers without capability completion"
out=$(run_hook "$(payload_for "git commit -m 'fix: demo'")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${COMMIT_TASK_DIR_WITH_CAPABILITY}" \
  "AGENT_CREW_PROJECT_ROOT=${COMMIT_PROJECT}" \
  "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Commit capability completion"

write_capability_result "${COMMIT_TASK_DIR_WITH_CAPABILITY}" "vcs.commit.message.compose" "git-committer"

it "git commit is allowed when commit capabilities are completed by selected handlers"
out=$(run_hook "$(payload_for "git commit -m 'fix: demo'")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${COMMIT_TASK_DIR_WITH_CAPABILITY}" \
  "AGENT_CREW_PROJECT_ROOT=${COMMIT_PROJECT}" \
  "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 0 "${rc}"
assert_eq "" "${out}" "capability handler completion should satisfy commit guard"

COMMIT_TASK_DIR_WITH_MD_CAPABILITY="$(make_tmp)"
mkdir -p "${COMMIT_TASK_DIR_WITH_MD_CAPABILITY}/context"
cat > "${COMMIT_TASK_DIR_WITH_MD_CAPABILITY}/context/specialist-dispatch.md" <<'EOF'
selected_agent: supervisor
selected_handler: vcs.commit.message.compose=git-committer
selected_handler: vcs.history.local_mutation=git
selection_reason: commit request capability handlers
execution_mode: current_session_required fallback
EOF

it "git commit blocks markdown capability handlers without completion"
out=$(run_hook "$(payload_for "git commit -m 'fix: demo'")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${COMMIT_TASK_DIR_WITH_MD_CAPABILITY}" \
  "AGENT_CREW_PROJECT_ROOT=${COMMIT_PROJECT}" \
  "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Commit capability completion"

write_capability_result "${COMMIT_TASK_DIR_WITH_MD_CAPABILITY}" "vcs.commit.message.compose" "git-committer"

it "git commit is allowed when markdown capability handlers completed"
out=$(run_hook "$(payload_for "git commit -m 'fix: demo'")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${COMMIT_TASK_DIR_WITH_MD_CAPABILITY}" \
  "AGENT_CREW_PROJECT_ROOT=${COMMIT_PROJECT}" \
  "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 0 "${rc}"
assert_eq "" "${out}" "markdown capability handler completion should satisfy commit guard"

COMMIT_TASK_DIR_WITH_ABSTRACT_CAPABILITY="$(make_tmp)"
mkdir -p "${COMMIT_TASK_DIR_WITH_ABSTRACT_CAPABILITY}/context"
cat > "${COMMIT_TASK_DIR_WITH_ABSTRACT_CAPABILITY}/context/specialist-dispatch.json" <<'EOF'
{
  "selected_agent": "supervisor",
  "selected_handlers": [
    {
      "capability": "vcs.commit.message.compose",
      "handler": "commit-message-specialist"
    }
  ],
  "selection_reason": "commit request capability handler",
  "execution_mode": "current_session_required fallback"
}
EOF

it "git commit blocks an abstract commit-message handler without completion"
out=$(run_hook "$(payload_for "git commit -m 'fix: demo'")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${COMMIT_TASK_DIR_WITH_ABSTRACT_CAPABILITY}" \
  "AGENT_CREW_PROJECT_ROOT=${COMMIT_PROJECT}" \
  "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Commit capability completion"

write_capability_result "${COMMIT_TASK_DIR_WITH_ABSTRACT_CAPABILITY}" "vcs.commit.message.compose" "commit-message-specialist"

it "git commit is allowed when an abstract commit-message capability handler completed"
out=$(run_hook "$(payload_for "git commit -m 'fix: demo'")" \
  "AGENT_CREW_HOME=${TMP_HOME}" \
  "AGENT_CREW_TASK_DIR=${COMMIT_TASK_DIR_WITH_ABSTRACT_CAPABILITY}" \
  "AGENT_CREW_PROJECT_ROOT=${COMMIT_PROJECT}" \
  "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 0 "${rc}"
assert_eq "" "${out}" "policy should require completed capability evidence, not a concrete agent name"

it "legacy APPROVED marker does not allow git push"
mkdir -p "${TMP_HOME}/approvals"
printf 'APPROVED\n' > "${TMP_HOME}/approvals/dangerous-commands.approved"
out=$(run_hook "$(payload_for "git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"

it "approval marker without expiry does not allow git push"
python3 -c '
import json, pathlib, sys
path = pathlib.Path(sys.argv[1]) / "approvals" / "dangerous-commands.approved"
path.write_text(json.dumps({
    "approved": True,
    "kind": "push",
    "command": "git push origin main",
}) + "\n", encoding="utf-8")
' "${TMP_HOME}"
out=$(run_hook "$(payload_for "git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: push"

it "expired approval marker does not allow git push"
python3 -c '
import json, pathlib, sys
path = pathlib.Path(sys.argv[1]) / "approvals" / "dangerous-commands.approved"
path.write_text(json.dumps({
    "approved": True,
    "kind": "push",
    "command": "git push origin main",
    "expires_at": "2000-01-01T00:00:00Z",
}) + "\n", encoding="utf-8")
' "${TMP_HOME}"
out=$(run_hook "$(payload_for "git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"
assert_contains "${out}" "Kind: push"

it "approval marker for different command does not allow git push"
write_approval "${TMP_HOME}" "push" "git push origin other"
out=$(run_hook "$(payload_for "git push origin main")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
rc=$?
assert_exit 2 "${rc}"

it "rm -fr root is blocked"
out=$(run_hook "$(payload_for "rm -fr /")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
assert_contains "${out}" "Kind: destructive-delete"

it "rm -rf quoted HOME is blocked"
out=$(run_hook "$(payload_for 'rm -rf "$HOME"')" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
assert_contains "${out}" "Kind: destructive-delete"

it "rm -rf braced HOME is blocked"
out=$(run_hook "$(payload_for 'rm -rf ${HOME}')" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
assert_contains "${out}" "Kind: destructive-delete"

it "git merge is blocked without deterministic approval"
rm -f "${TMP_HOME}/approvals/dangerous-commands.approved"
out=$(run_hook "$(payload_for "git merge feature/example")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
assert_contains "${out}" "Kind: merge"

it "deploy script is blocked without deterministic approval"
out=$(run_hook "$(payload_for "./deploy.sh production")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
assert_contains "${out}" "Kind: deploy"

it "read-only git status is allowed"
out=$(run_hook "$(payload_for "git status -sb")" "AGENT_CREW_HOME=${TMP_HOME}" "AGENT_CREW_APPROVED_DANGEROUS=")
assert_eq "" "${out}" "read-only command should produce no block JSON"

end_report
