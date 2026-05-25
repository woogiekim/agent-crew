"""Persistent AI Workforce core-objective capability ceiling helpers."""

from __future__ import annotations

from typing import Any


CORE_RUNTIME_CAPABILITIES = (
    "task_tools",
    "agent_background",
    "monitor_tool",
    "cost_tracking",
    "hook_system",
    "interactive_question",
)

CODEX_POLICY_FALLBACK_CAPABILITIES = set(CORE_RUNTIME_CAPABILITIES)


def _bool_capability(value: Any) -> bool:
    return bool(value)


def _conditional_capability(payload: dict[str, Any], adapter: str, name: str) -> bool:
    if adapter != "codex" or name != "interactive_question":
        return False
    return payload.get("interactive_question_mode") == "codex_plan_mode_conditional"


def capability_ceiling(capabilities: dict[str, Any] | None) -> dict[str, Any]:
    """Summarize host-native runtime capability coverage.

    This is deliberately separate from framework validation. A framework can
    pass its deterministic readiness gate while the active host still caps
    operational autonomy because key runtime capabilities are prompt/file
    fallbacks instead of native enforcement surfaces.
    """
    payload = capabilities or {}
    adapter = str(payload.get("adapter") or payload.get("host") or "unknown")
    native: list[str] = []
    conditional: list[str] = []
    policy_only: list[str] = []
    unavailable: list[str] = []

    for name in CORE_RUNTIME_CAPABILITIES:
        if _bool_capability(payload.get(name)):
            native.append(name)
            continue
        if _conditional_capability(payload, adapter, name):
            conditional.append(name)
            continue
        if adapter == "codex" and name in CODEX_POLICY_FALLBACK_CAPABILITIES:
            policy_only.append(name)
        else:
            unavailable.append(name)

    total = len(CORE_RUNTIME_CAPABILITIES)
    native_ratio = round(len(native) / total, 4) if total else 1.0
    if len(native) == total:
        status = "native_runtime_ready"
    elif policy_only or conditional:
        status = "host_limited_policy_fallback"
    else:
        status = "host_limited_unavailable"

    summary = summary_for_status(status)
    if conditional and status == "host_limited_policy_fallback":
        summary = (
            "Framework readiness can pass; some capabilities have "
            "mode-conditional native surfaces, while remaining capabilities "
            "use policy/file fallbacks."
        )

    return {
        "schema_version": 1,
        "active_adapter": adapter,
        "status": status,
        "native_capabilities": native,
        "conditional_capabilities": conditional,
        "policy_only_capabilities": policy_only,
        "unavailable_capabilities": unavailable,
        "native_capability_count": len(native),
        "conditional_capability_count": len(conditional),
        "policy_only_capability_count": len(policy_only),
        "unavailable_capability_count": len(unavailable),
        "total_capabilities": total,
        "host_native_runtime_capability_rate": native_ratio,
        "framework_readiness_scope": "framework_controlled",
        "operational_autonomy_scope": "host_native_runtime",
        "summary": summary,
    }


def summary_for_status(status: str) -> str:
    if status == "native_runtime_ready":
        return "Host advertises all core runtime capabilities natively."
    if status == "host_limited_policy_fallback":
        return (
            "Framework readiness can pass, but operational autonomy is capped "
            "by host capabilities implemented as policy/file fallbacks."
        )
    return (
        "Framework readiness can pass, but operational autonomy is capped by "
        "missing host-native runtime capabilities."
    )


def format_ceiling_text(ceiling: dict[str, Any]) -> str:
    conditional = ",".join(ceiling.get("conditional_capabilities") or []) or "none"
    policy = ",".join(ceiling.get("policy_only_capabilities") or []) or "none"
    unavailable = ",".join(ceiling.get("unavailable_capabilities") or []) or "none"
    return (
        f"status={ceiling.get('status')} "
        f"native={ceiling.get('native_capability_count')}/"
        f"{ceiling.get('total_capabilities')} "
        f"conditional={conditional} policy_only={policy} unavailable={unavailable}"
    )
