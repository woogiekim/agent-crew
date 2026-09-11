#!/usr/bin/env bash
# 결정론적 Git/CLI 회귀 전용. 실제 AI/host multiagent 검증은 별도 수행한다.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/../shell/_lib.bash"

cd "${REPO_ROOT}" || exit 1
it "deterministic native CLI joins compatible strengths with executed validation (no AI)"
python3 -m pytest 'tests/python/test_variant_synthesis_e2e.py::test_deterministic_whole_flow_joins_strengths[native-cli]' -q
rc=$?
assert_exit 0 "${rc}"
end_report
