#!/usr/bin/env python3
"""
cost-aggregate.py — Provider-neutral per-call cost aggregator.

Purpose:
  Read per-task JSONL cost records under ${STATE_DIR}/cost/*.jsonl and
  emit a per-task, per-session, or summary aggregation. Used by
  core/commands/cost.md and by the supervisor cost circuit breaker
  documented in core/rules/quality-loop.md.

Inputs:
  --state-dir DIR     Override STATE_DIR resolution (default: env-derived).
  --task-id ID        Aggregate one task.
  --session-id ID     Aggregate all tasks in one session.
  --recent N          N most-recently-modified task files.
  --format json|table Output format (default: json).
  --budget N          Token budget (for --check-breaker).
  --check-breaker     Short-circuit mode: stdout "ok"|"warn"|"exceeded",
                      exit 0|1|2. Requires --task-id and --budget.

Outputs:
  Default mode: JSON object on stdout describing the requested aggregation.
  --format=table: text table; tier breakdowns left-aligned.
  --check-breaker: single word on stdout; exit code carries the verdict.

Exit codes:
  0 — ok / success
  1 — warn (in --check-breaker mode only)
  2 — exceeded (in --check-breaker mode only)
  3 — invalid args, unreadable state dir, etc.

Schema tolerated (each line under ${STATE_DIR}/cost/${TASK_ID}.jsonl):
  ts, task_id, session_id, agent, stage, model, tier,
  input_tokens, output_tokens, total_tokens,
  cache_creation_tokens, cache_read_tokens.
  Unknown fields are preserved-but-ignored. Malformed lines are skipped
  with a stderr warning.

Schema cross-ref:
  See core/rules/capabilities/cost-tracking.md for the canonical shape.
  See adapters/claude/setup.sh (TIER_TO_MODEL) for the model→tier map
  this script falls back to when a line records tier="unknown".
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

# Defaults — overridable via AGENT_CREW_BUDGET_{TIER}.
DEFAULT_BUDGETS = {
    "xhigh":    300_000,
    "deep":     200_000,
    "balanced": 150_000,
    "light":    100_000,
}

# Fallback when a line records tier="unknown". Keep in sync with host adapter
# model maps. If multiple abstract tiers share one concrete model, use the
# highest tier as the conservative model-only fallback; explicit row tiers
# remain authoritative when the host can provide them.
MODEL_TIER_FALLBACK = {
    "claude-fable-5":    "xhigh",
    "claude-opus-4-8":   "deep",
    "claude-sonnet-5":   "balanced",
    "claude-haiku-4-5":  "light",
    "gpt-5.5":           "xhigh",
    "gpt-5.4":           "balanced",
    "gpt-5.4-mini":      "light",
    # Legacy records from before the July 2026 model refresh.
    "claude-opus-4-7":   "xhigh",
    "claude-sonnet-4-6": "balanced",
}


def resolve_state_dir(override):
    if override:
        return Path(override)
    env = os.environ.get("AGENT_CREW_STATE_DIR")
    if env:
        return Path(env)
    home = os.environ.get("AGENT_CREW_HOME", str(Path.home() / ".agent-crew"))
    project = os.environ.get("AGENT_CREW_PROJECT", "default")
    return Path(home) / "state" / project


def budget_for_tier(tier):
    env_key = f"AGENT_CREW_BUDGET_{tier.upper()}"
    raw = os.environ.get(env_key)
    if raw:
        try:
            return int(raw)
        except ValueError:
            print(f"[cost-aggregate] warning: invalid {env_key}={raw!r}", file=sys.stderr)
    return DEFAULT_BUDGETS.get(tier, DEFAULT_BUDGETS["balanced"])


def normalize_line(raw):
    """Parse one JSONL line; return a normalized dict or None if invalid."""
    try:
        d = json.loads(raw)
    except Exception as exc:
        print(f"[cost-aggregate] skip malformed line: {exc}", file=sys.stderr)
        return None
    out = {
        "ts":         d.get("ts") or "",
        "task_id":    d.get("task_id") or "",
        "session_id": d.get("session_id") or "",
        "agent":      d.get("agent") or "unknown",
        "stage":      d.get("stage"),  # may be None
        "model":      d.get("model") or "unknown",
        "tier":       d.get("tier") or "unknown",
        "in":         int(d.get("input_tokens")          or 0),
        "out":        int(d.get("output_tokens")         or 0),
        "total":      int(d.get("total_tokens")          or 0),
        "cache_w":    int(d.get("cache_creation_tokens") or 0),
        "cache_r":    int(d.get("cache_read_tokens")     or 0),
    }
    if out["total"] <= 0:
        out["total"] = out["in"] + out["out"]
    if out["tier"] == "unknown":
        out["tier"] = MODEL_TIER_FALLBACK.get(out["model"], "balanced")
    return out


def read_task_file(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        norm = normalize_line(line)
        if norm is not None:
            rows.append(norm)
    return rows


def read_jsonl_count(path):
    if not path.is_file():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError:
            continue
        count += 1
    return count


def proxy_metrics_for_task(state_dir, task_id):
    task_dir = state_dir / "tasks" / task_id
    progress_events = read_jsonl_count(task_dir / "progress.buffer.jsonl")
    tool_events = read_jsonl_count(task_dir / "tool-events.jsonl")
    delegation_events = read_jsonl_count(task_dir / "delegation.jsonl")
    total_proxy = progress_events + tool_events + delegation_events
    metrics = {
        "progress_events": progress_events,
        "tool_events": tool_events,
        "delegation_events": delegation_events,
        "total_proxy_events": total_proxy,
    }
    if total_proxy:
        return "proxy", metrics, ""
    return "unavailable", metrics, "no measured token records or proxy telemetry events were found"


def task_complexity_estimate(state_dir, task_id):
    """Estimate task complexity from available workflow metadata only."""
    task_dir = state_dir / "tasks" / task_id
    progress_events = read_jsonl_count(task_dir / "progress.buffer.jsonl")
    tool_events = read_jsonl_count(task_dir / "tool-events.jsonl")
    delegation_events = read_jsonl_count(task_dir / "delegation.jsonl")
    score = progress_events + (2 * tool_events) + (3 * delegation_events)
    if score >= 25:
        level = "high"
    elif score >= 8:
        level = "medium"
    elif score > 0:
        level = "low"
    else:
        level = "unavailable"
    return {
        "level": level,
        "score": score,
        "basis": {
            "progress_events": progress_events,
            "tool_events": tool_events,
            "delegation_events": delegation_events,
        },
    }


def routing_audit(rows):
    decisions = []
    for row in rows:
        decisions.append({
            "agent": row["agent"],
            "stage": row["stage"],
            "model": row["model"],
            "tier": row["tier"],
            "source": "measured_cost_record",
        })
    return decisions


def summarize_rows(rows):
    """Reduce a list of normalized rows to a summary dict."""
    total_in = sum(r["in"]      for r in rows)
    total_out = sum(r["out"]    for r in rows)
    total_cw = sum(r["cache_w"] for r in rows)
    total_cr = sum(r["cache_r"] for r in rows)
    grand = sum(r["total"] for r in rows)  # cache tokens excluded from the budget by convention
    by_agent = defaultdict(lambda: {"in": 0, "out": 0, "total": 0, "calls": 0})
    by_tier  = defaultdict(lambda: {"in": 0, "out": 0, "total": 0, "calls": 0})
    by_model = defaultdict(lambda: {"in": 0, "out": 0, "total": 0, "calls": 0})
    for r in rows:
        for bucket, key in ((by_agent, r["agent"]), (by_tier, r["tier"]), (by_model, r["model"])):
            bucket[key]["in"] += r["in"]
            bucket[key]["out"] += r["out"]
            bucket[key]["total"] += r["total"]
            bucket[key]["calls"] += 1
    # task-level budget = max of tier budgets that appear in this task
    tiers_used = list(by_tier.keys()) or ["balanced"]
    task_budget = max(budget_for_tier(t) for t in tiers_used)
    return {
        "calls":            len(rows),
        "input_tokens":     total_in,
        "output_tokens":    total_out,
        "cache_creation_tokens": total_cw,
        "cache_read_tokens":     total_cr,
        "total_tokens":     grand,
        "task_budget":      task_budget,
        "pct_consumed":     round(100.0 * grand / task_budget, 1) if task_budget else 0.0,
        "tiers_used":       tiers_used,
        "by_agent":         dict(by_agent),
        "by_tier":          dict(by_tier),
        "by_model":         dict(by_model),
        "routing_audit":    routing_audit(rows),
    }


def iter_task_files(state_dir):
    cost_dir = state_dir / "cost"
    if not cost_dir.is_dir():
        return []
    return sorted(cost_dir.glob("*.jsonl"))


def iter_task_dirs(state_dir):
    tasks_dir = state_dir / "tasks"
    if not tasks_dir.is_dir():
        return []
    return sorted(path for path in tasks_dir.iterdir() if path.is_dir())


def recent_task_ids(state_dir, n):
    candidates = {}
    for path in iter_task_files(state_dir):
        candidates[path.stem] = max(candidates.get(path.stem, 0), path.stat().st_mtime)
    for path in iter_task_dirs(state_dir):
        candidates[path.name] = max(candidates.get(path.name, 0), path.stat().st_mtime)
    return [
        task_id for task_id, _ in sorted(candidates.items(), key=lambda item: item[1], reverse=True)[:n]
    ]


def summarize_task(state_dir, task_id):
    rows = read_task_file(state_dir / "cost" / f"{task_id}.jsonl")
    summary = summarize_rows(rows)
    summary["task_id"] = task_id
    source, proxy, reason = proxy_metrics_for_task(state_dir, task_id)
    summary["telemetry_source"] = "measured" if rows else source
    summary["proxy_metrics"] = proxy
    summary["task_complexity_estimate"] = task_complexity_estimate(state_dir, task_id)
    if not rows and reason:
        summary["unavailable_reason"] = reason
    return summary


def aggregate_proxy_metrics(state_dir):
    totals = {
        "progress_events": 0,
        "tool_events": 0,
        "delegation_events": 0,
        "total_proxy_events": 0,
        "tasks_with_proxy_events": 0,
    }
    for task_dir in iter_task_dirs(state_dir):
        _, metrics, _ = proxy_metrics_for_task(state_dir, task_dir.name)
        if metrics["total_proxy_events"]:
            totals["tasks_with_proxy_events"] += 1
        for key in ("progress_events", "tool_events", "delegation_events", "total_proxy_events"):
            totals[key] += metrics[key]
    return totals


def mode_task(state_dir, task_id):
    summary = summarize_task(state_dir, task_id)
    return {"mode": "task", "task": summary}


def mode_session(state_dir, session_id):
    tasks = {}
    session_task_ids = set()
    for f in iter_task_files(state_dir):
        rows = [r for r in read_task_file(f) if r["session_id"] == session_id]
        if not rows:
            continue
        s = summarize_rows(rows)
        s["task_id"] = f.stem
        s["telemetry_source"] = "measured"
        s["proxy_metrics"] = proxy_metrics_for_task(state_dir, f.stem)[1]
        tasks[f.stem] = s
        session_task_ids.add(f.stem)

    session_file = state_dir / "session.json"
    try:
        session = json.loads(session_file.read_text(encoding="utf-8"))
    except Exception:
        session = {}
    if isinstance(session, dict) and session.get("session_id") == session_id:
        for item in session.get("tasks", []):
            if isinstance(item, dict) and item.get("task_id"):
                session_task_ids.add(str(item["task_id"]))

    for task_id in sorted(session_task_ids):
        tasks.setdefault(task_id, summarize_task(state_dir, task_id))

    result = {"mode": "session", "session_id": session_id, "tasks": tasks}
    if not tasks:
        result["telemetry_source"] = "unavailable"
        result["unavailable_reason"] = "no measured token records or session task proxy telemetry were found"
    return result


def mode_recent(state_dir, n):
    out = {}
    for task_id in recent_task_ids(state_dir, n):
        out[task_id] = summarize_task(state_dir, task_id)
    result = {"mode": "recent", "n": n, "tasks": out}
    if not out:
        result["telemetry_source"] = "unavailable"
        result["unavailable_reason"] = "no measured token records or task proxy telemetry were found"
    return result


def mode_default(state_dir):
    tasks = {}
    for task_id in sorted(path.stem for path in iter_task_files(state_dir)):
        tasks[task_id] = summarize_task(state_dir, task_id)
    grand_in  = sum(t["input_tokens"]  for t in tasks.values())
    grand_out = sum(t["output_tokens"] for t in tasks.values())
    grand_total = sum(t["total_tokens"] for t in tasks.values())
    measured = any(t["telemetry_source"] == "measured" for t in tasks.values())
    proxy_metrics = aggregate_proxy_metrics(state_dir)
    proxy = proxy_metrics["total_proxy_events"] > 0
    return {
        "mode": "summary",
        "task_count": len(tasks),
        "input_tokens": grand_in,
        "output_tokens": grand_out,
        "total_tokens": grand_total,
        "telemetry_source": "measured" if measured else "proxy" if proxy else "unavailable",
        "proxy_metrics": proxy_metrics,
        "unavailable_reason": "" if measured or proxy else "no measured token records or task proxy telemetry were found",
        "tasks": tasks,
    }


def format_table(result):
    """Compact text table for `crew:cost`."""
    lines = []
    mode = result.get("mode")
    if mode == "task":
        t = result["task"]
        lines.append(f"Task: {t['task_id']}")
        lines.append(f"  calls={t['calls']}  tokens={t['total_tokens']:,}"
                     f"  ({t['input_tokens']:,} in / {t['output_tokens']:,} out)")
        lines.append(f"  budget={t['task_budget']:,}  consumed={t['pct_consumed']}%")
        lines.append(f"  telemetry_source={t.get('telemetry_source', 'measured')}")
        if t.get("telemetry_source") == "proxy":
            proxy = t.get("proxy_metrics", {})
            lines.append(
                "  proxy_metrics="
                f"progress_events={proxy.get('progress_events', 0)} "
                f"tool_events={proxy.get('tool_events', 0)} "
                f"delegation_events={proxy.get('delegation_events', 0)}"
            )
        elif t.get("telemetry_source") == "unavailable":
            lines.append(f"  unavailable_reason={t.get('unavailable_reason', 'unknown')}")
        if t["by_agent"]:
            lines.append("  by agent:")
            for agent, d in sorted(t["by_agent"].items()):
                lines.append(f"    {agent:<14} calls={d['calls']:>2}"
                             f"  tokens={d['total']:>8,}"
                             f"  in={d['in']:>8,}  out={d['out']:>8,}")
    elif mode in ("session", "recent", "summary"):
        if mode == "summary":
            lines.append(f"Tasks: {result['task_count']}  tokens={result['total_tokens']:,}")
            lines.append(f"telemetry_source={result.get('telemetry_source', 'measured')}")
            if result.get("telemetry_source") == "proxy":
                proxy = result.get("proxy_metrics", {})
                lines.append(
                    "proxy_metrics="
                    f"tasks_with_proxy_events={proxy.get('tasks_with_proxy_events', 0)} "
                    f"progress_events={proxy.get('progress_events', 0)} "
                    f"tool_events={proxy.get('tool_events', 0)} "
                    f"delegation_events={proxy.get('delegation_events', 0)}"
                )
            elif result.get("telemetry_source") == "unavailable":
                lines.append(f"unavailable_reason={result.get('unavailable_reason', 'unknown')}")
        elif mode == "session":
            lines.append(f"Session: {result['session_id']}")
        else:
            lines.append(f"Recent {result['n']} tasks:")
        if not result.get("tasks") and result.get("telemetry_source") == "unavailable":
            lines.append(f"  telemetry_source=unavailable")
            lines.append(f"  unavailable_reason={result.get('unavailable_reason', 'unknown')}")
        for tid, t in sorted(result.get("tasks", {}).items(), reverse=True):
            lines.append(f"  {tid}  tokens={t['total_tokens']:>9,}"
                         f"  budget={t['task_budget']:>9,}  ({t['pct_consumed']}%)"
                         f"  telemetry_source={t.get('telemetry_source', 'measured')}")
            if t.get("telemetry_source") == "proxy":
                proxy = t.get("proxy_metrics", {})
                lines.append(
                    "    proxy_metrics="
                    f"progress_events={proxy.get('progress_events', 0)} "
                    f"tool_events={proxy.get('tool_events', 0)} "
                    f"delegation_events={proxy.get('delegation_events', 0)}"
                )
            elif t.get("telemetry_source") == "unavailable":
                lines.append(f"    unavailable_reason={t.get('unavailable_reason', 'unknown')}")
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(description="agent-crew cost aggregator")
    p.add_argument("--state-dir")
    p.add_argument("--task-id")
    p.add_argument("--session-id")
    p.add_argument("--recent", type=int)
    p.add_argument("--format", choices=["json", "table"], default="json")
    p.add_argument("--budget", type=int,
                   help="Override budget for --check-breaker. "
                        "Defaults to max(tier budget) for tiers seen in the task.")
    p.add_argument("--check-breaker", action="store_true",
                   help="Short-circuit mode; emit ok|warn|exceeded and exit 0|1|2.")
    args = p.parse_args()

    state_dir = resolve_state_dir(args.state_dir)

    # --check-breaker takes precedence; requires --task-id.
    if args.check_breaker:
        if not args.task_id:
            print("error: --check-breaker requires --task-id", file=sys.stderr)
            sys.exit(3)
        result = mode_task(state_dir, args.task_id)
        total = result["task"]["total_tokens"]
        budget = args.budget if args.budget else result["task"]["task_budget"]
        if budget <= 0:
            print("ok")
            sys.exit(0)
        pct = total / budget
        if pct >= 1.0:
            print("exceeded")
            sys.exit(2)
        if pct >= 0.5:
            print("warn")
            sys.exit(1)
        print("ok")
        sys.exit(0)

    # Mode selection — exactly one is allowed.
    chosen = [x for x in (args.task_id, args.session_id, args.recent) if x is not None]
    if len(chosen) > 1:
        print("error: --task-id, --session-id, --recent are mutually exclusive",
              file=sys.stderr)
        sys.exit(3)

    if args.task_id:
        result = mode_task(state_dir, args.task_id)
    elif args.session_id:
        result = mode_session(state_dir, args.session_id)
    elif args.recent is not None:
        result = mode_recent(state_dir, args.recent)
    else:
        result = mode_default(state_dir)

    if args.format == "table":
        sys.stdout.write(format_table(result))
    else:
        json.dump(result, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
