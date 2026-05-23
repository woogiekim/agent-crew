# Framework Review Round 10

Date: 2026-05-23

Task ID: `20260523-152836-0`

Memory context path: `/Users/wook/.agent-crew/state/agent-crew/tasks/20260523-152836-0/context/memory.md`

## Scope

This round reviewed runtime governance and deterministic control surfaces across
architecture, performance, quality, reliability, memory governance, security,
observability, cost efficiency, developer experience, and maintainable runtime
structure.

## High-Risk Priorities

The highest-risk items are now represented as explicit policy or static
diagnostic controls:

- memory governance and retrieval scoring
- tool sandboxing and command-bound approvals
- context compression and handoff page-out
- structured outputs and machine-readable state
- explicit workflow states and replay fixtures
- observability through structured progress and trace files
- cost-aware routing and budget blockers
- prompt injection defense for retrieved and external content
- automatic issue reporting for runtime infrastructure issues

## Changes

- Added `core/rules/runtime-governance.md` as the cross-cutting runtime control
  contract.
- Added `core/rules/tool-sandboxing.md` to separate workflow sandboxing claims
  from OS-level host sandbox capabilities.
- Extended `core/scripts/framework-review-check.py` with round-10 controls for
  runtime governance, context compression, structured outputs, tool sandboxing,
  retrieval scoring, deterministic state replay, and prompt-injection/issue
  reporting integration.
- Extended framework review tests so future regressions fail when these priority
  controls disappear.

## Validation

Validation should include:

- `python3 core/scripts/framework-review-check.py --format text`
- `pytest tests/python/test_framework_review_check.py`
- targeted replay, telemetry, memory, and issue-reporter tests when adjacent
  runtime behavior changes.

## Residual Risk

The framework still depends on host adapters for actual tool execution,
background task surfaces, and OS-level sandboxing. Core policy now documents the
fallback boundary, but host-specific hardening must continue to be validated per
adapter.
