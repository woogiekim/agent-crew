#!/usr/bin/env bash
# 실제 Supervisor gate, canonical classifier, 파일 상태를 조합한 오프라인 시나리오.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-${REPO_ROOT}/.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN=python3
fi

"${PYTHON_BIN}" -m pytest "${REPO_ROOT}/tests/python/test_brainstorm_supervisor_contract.py" \
  -k workflow -v

grep -q "Brainstorm :" "${REPO_ROOT}/core/commands/status.md"
grep -q "legacy tasks omit" "${REPO_ROOT}/core/commands/status.md"
grep -q "Brainstorm" "${REPO_ROOT}/core/commands/smm.md"
grep -q "combined design and plan approval" "${REPO_ROOT}/README.md"
