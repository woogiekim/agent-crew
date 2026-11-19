#!/usr/bin/env python3
"""파일 I/O 없이 objective와 execution 상태를 판단하고 복사 전이를 반환한다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional


LEASE_SECONDS = 300
MAX_CLOCK_SKEW_SECONDS = 300
OBJECTIVE_TERMINAL = {"completed", "blocked", "cancelled"}
EXECUTION_TERMINAL = "terminal"


@dataclass(frozen=True)
class LifecycleState:
    objective_status: str
    execution_status: str
    idle_reason: Optional[str] = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_utc(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc).replace(microsecond=0)
    return normalized.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return None

    return parsed.astimezone(timezone.utc)


def derive_lifecycle(
    register: dict[str, Any],
    result_status: Optional[str],
    active_owner: bool,
    now: Optional[datetime] = None,
    waiting_user: bool = False,
) -> LifecycleState:
    current = now or utc_now()
    terminal = str(result_status or "").lower()
    if terminal in OBJECTIVE_TERMINAL:
        return LifecycleState(terminal, EXECUTION_TERMINAL)

    objective = str(register.get("objective_status") or "open").lower()
    if objective in OBJECTIVE_TERMINAL:
        return LifecycleState(objective, EXECUTION_TERMINAL)

    legacy_phase = str(register.get("current_phase") or "").lower()
    if legacy_phase in OBJECTIVE_TERMINAL:
        return LifecycleState(legacy_phase, EXECUTION_TERMINAL)
    if waiting_user or register.get("approval_status") == "pending":
        return LifecycleState("open", "waiting_user")
    if active_owner:
        return LifecycleState("open", "running")

    execution = str(register.get("execution_status") or "").lower()
    if execution == "waiting_user":
        return LifecycleState("open", "waiting_user")
    if execution == "idle":
        return LifecycleState("open", "idle", register.get("idle_reason"))

    raw_expiry = register.get("lease_expires_at")
    expires = parse_utc(raw_expiry)
    if raw_expiry and expires is None:
        return LifecycleState("open", "idle", "invalid_lease")
    if expires is None:
        return LifecycleState("open", "idle", "legacy_unowned")
    if expires > current + timedelta(seconds=LEASE_SECONDS + MAX_CLOCK_SKEW_SECONDS):
        return LifecycleState("open", "idle", "invalid_lease")
    if expires > current:
        return LifecycleState("open", "running")
    return LifecycleState("open", "idle", "lease_expired")


def apply_to_register(
    register: dict[str, Any],
    state: LifecycleState,
) -> dict[str, Any]:
    updated = dict(register)
    updated["objective_status"] = state.objective_status
    updated["execution_status"] = state.execution_status
    updated["idle_reason"] = state.idle_reason
    if state.execution_status in {"waiting_user", EXECUTION_TERMINAL}:
        updated.pop("lease_expires_at", None)
        updated.pop("execution_owner", None)

    return updated


def start_execution(
    register: dict[str, Any],
    owner_kind: str,
    owner_id: str,
    now: Optional[datetime] = None,
    lease_seconds: int = LEASE_SECONDS,
) -> dict[str, Any]:
    current = now or utc_now()
    existing = derive_lifecycle(register, None, False, current)
    if existing.objective_status in OBJECTIVE_TERMINAL:
        return dict(register)

    updated = apply_to_register(register, LifecycleState("open", "running"))
    updated["last_heartbeat_at"] = format_utc(current)
    updated["lease_expires_at"] = format_utc(current + timedelta(seconds=lease_seconds))
    updated["execution_owner"] = {"kind": owner_kind, "id": owner_id}
    updated["idle_reason"] = None

    return updated


def heartbeat(
    register: dict[str, Any],
    owner_kind: str,
    owner_id: str,
    now: Optional[datetime] = None,
    lease_seconds: int = LEASE_SECONDS,
) -> dict[str, Any]:
    owner = register.get("execution_owner")
    if owner != {"kind": owner_kind, "id": owner_id}:
        return dict(register)
    if register.get("objective_status") in OBJECTIVE_TERMINAL:
        return dict(register)

    current = now or utc_now()
    updated = dict(register)
    updated["objective_status"] = "open"
    updated["execution_status"] = "running"
    updated["last_heartbeat_at"] = format_utc(current)
    updated["lease_expires_at"] = format_utc(current + timedelta(seconds=lease_seconds))
    updated["idle_reason"] = None

    return updated


def wait_for_user(
    register: dict[str, Any],
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    del now
    return apply_to_register(register, LifecycleState("open", "waiting_user"))


def finish_execution(
    register: dict[str, Any],
    terminal_status: Optional[str],
    reason: str,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    current = now or utc_now()
    terminal = str(terminal_status or "").lower()
    state = LifecycleState("open", "idle", reason)
    if terminal in OBJECTIVE_TERMINAL:
        state = LifecycleState(terminal, EXECUTION_TERMINAL)

    updated = apply_to_register(register, state)
    if terminal in OBJECTIVE_TERMINAL:
        updated["status"] = terminal
        updated["current_phase"] = terminal
    updated["last_heartbeat_at"] = format_utc(current)
    updated.pop("lease_expires_at", None)
    updated.pop("execution_owner", None)

    return updated
