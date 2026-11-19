"""설치 입력과 PRD의 순수 상태 판단·전이 계약을 검증한다."""
from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


@pytest.fixture
def sut():
    path = ROOT / "core/scripts/execution_lifecycle.py"
    spec = importlib.util.spec_from_file_location("lifecycle_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("value", [None, 1, "", " ", "invalid", "2026-01-01T12:00:00"])
def test_boundary_case_invalid_timestamps_are_absent(sut, value):
    """boundary-case(validation) - 비정상·timezone 없는 timestamp를 거부한다."""
    assert sut.parse_utc(value) is None


def test_success_case_utc_normalization_and_clock(sut):
    """success-case(contract) - UTC 변환과 초 단위 표시를 유지한다."""
    local = datetime(2026, 1, 1, 21, 0, 0, 123, tzinfo=timezone(timedelta(hours=9)))

    assert sut.format_utc(local) == "2026-01-01T12:00:00Z"
    assert sut.parse_utc(" 2026-01-01T21:00:00+09:00 ") == NOW
    assert sut.parse_utc("2026-01-01T12:00:00Z") == NOW
    assert sut.utc_now().tzinfo == timezone.utc


@pytest.mark.parametrize("register,result,active,waiting,expected", [
    ({}, None, False, False, ("open", "idle", "legacy_unowned")),
    ({"lease_expires_at": "bad"}, None, True, False, ("open", "running", None)),
    ({}, None, True, True, ("open", "waiting_user", None)),
    ({"approval_status": "pending"}, None, True, False, ("open", "waiting_user", None)),
    ({"execution_status": "WAITING_USER"}, None, False, False, ("open", "waiting_user", None)),
    ({"execution_status": "IDLE", "idle_reason": "interrupted"}, None, False, False, ("open", "idle", "interrupted")),
    ({"lease_expires_at": ""}, None, False, False, ("open", "idle", "legacy_unowned")),
    ({"objective_status": "BLOCKED"}, "COMPLETED", True, True, ("completed", "terminal", None)),
    ({"objective_status": "CANCELLED"}, None, True, True, ("cancelled", "terminal", None)),
    ({"current_phase": "BLOCKED"}, None, True, True, ("blocked", "terminal", None)),
])
def test_boundary_case_state_precedence_is_pure(sut, register, result, active, waiting, expected):
    """boundary-case(state-transition) - terminal·대기·owner 우선순위와 입력 불변을 보존한다."""
    before = deepcopy(register)

    state = sut.derive_lifecycle(register, result, active, NOW, waiting)

    assert state == sut.LifecycleState(*expected)
    assert register == before


@pytest.mark.parametrize("seconds,expected", [
    (-1, ("open", "idle", "lease_expired")),
    (0, ("open", "idle", "lease_expired")),
    (1, ("open", "running", None)),
    (600, ("open", "running", None)),
    (601, ("open", "idle", "invalid_lease")),
])
def test_boundary_case_lease_window(sut, seconds, expected):
    """boundary-case(limit) - lease 만료·허용 최대 미래 시각을 구분한다."""
    register = {"lease_expires_at": sut.format_utc(NOW + timedelta(seconds=seconds))}

    assert sut.derive_lifecycle(register, None, False, NOW) == sut.LifecycleState(*expected)


@pytest.mark.parametrize("execution,retains_lease", [("running", True), ("idle", True), ("waiting_user", False), ("terminal", False)])
def test_boundary_case_apply_returns_copy_with_state_appropriate_ownership(sut, execution, retains_lease):
    """boundary-case(ownership) - 대기·종료는 owner를 해제하고 원본을 보존한다."""
    register = {"custom": 1, "execution_owner": {"kind": "host", "id": "one"}, "lease_expires_at": "expiry"}
    before = deepcopy(register)

    result = sut.apply_to_register(register, sut.LifecycleState("open", execution))

    assert result is not register
    assert register == before
    assert result["custom"] == 1
    assert result["execution_status"] == execution
    assert ("lease_expires_at" in result) is retains_lease
    assert ("execution_owner" in result) is retains_lease


def test_success_case_start_heartbeat_wait_and_finish_return_copies(sut, monkeypatch):
    """success-case(state-transition) - 명시적 전이를 순수 복사로 반환한다."""
    monkeypatch.setattr(sut, "utc_now", lambda: NOW)
    register = {"custom": 1}

    started = sut.start_execution(register, "host", "one")
    before = deepcopy(started)
    renewed = sut.heartbeat(started, "host", "one", NOW + timedelta(seconds=60), 30)
    waiting = sut.wait_for_user(renewed)
    finished = sut.finish_execution(renewed, "COMPLETED", "done")
    interrupted = sut.finish_execution(renewed, None, "interrupted", NOW)

    assert register == {"custom": 1}
    assert started == before
    assert started["execution_owner"] == {"kind": "host", "id": "one"}
    assert started["lease_expires_at"] == "2026-01-01T12:05:00Z"
    assert renewed["lease_expires_at"] == "2026-01-01T12:01:30Z"
    assert renewed["last_heartbeat_at"] == "2026-01-01T12:01:00Z"
    assert waiting["execution_status"] == "waiting_user"
    assert "execution_owner" not in waiting
    assert "lease_expires_at" not in waiting
    assert (finished["objective_status"], finished["execution_status"], finished["status"], finished["current_phase"]) == ("completed", "terminal", "completed", "completed")
    assert (interrupted["objective_status"], interrupted["execution_status"], interrupted["idle_reason"]) == ("open", "idle", "interrupted")
    assert "execution_owner" not in interrupted
    assert "lease_expires_at" not in interrupted
    assert interrupted["last_heartbeat_at"] == "2026-01-01T12:00:00Z"
    assert sut.derive_lifecycle(started, None, False).execution_status == "running"
    assert sut.heartbeat(started, "host", "one")["lease_expires_at"] == started["lease_expires_at"]
    assert sut.start_execution(register, "host", "two", NOW, 10)["lease_expires_at"] == "2026-01-01T12:00:10Z"


@pytest.mark.parametrize("terminal", ["completed", "blocked", "cancelled"])
def test_failure_case_terminal_cannot_restart_or_heartbeat(sut, terminal):
    """failure-case(state-transition) - 종료 objective의 재시작과 heartbeat를 차단한다."""
    register = {"objective_status": terminal, "execution_owner": {"kind": "host", "id": "one"}}
    before = deepcopy(register)

    started = sut.start_execution(register, "host", "one", NOW)
    renewed = sut.heartbeat(register, "host", "one", NOW)

    assert started == renewed == before == register
    assert started is not register
    assert renewed is not register


def test_failure_case_owner_mismatch_cannot_heartbeat(sut):
    """failure-case(ownership) - 불일치 owner는 lease를 갱신할 수 없다."""
    register = {"execution_owner": {"kind": "host", "id": "one"}}

    result = sut.heartbeat(register, "host", "other", NOW)

    assert result == register
    assert result is not register


def test_success_case_helper_is_managed_source():
    """success-case(regression) - helper를 표준 관리 source inventory에 등록한다."""
    inventory = json.loads((ROOT / "core/schemas/runtime-managed-source-inventory.json").read_text())

    assert inventory["files"].count("core/scripts/execution_lifecycle.py") == 1
