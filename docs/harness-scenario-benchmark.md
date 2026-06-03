# Harness Scenario Benchmark

Date: 2026-06-01

This benchmark turns the competitiveness analysis into a repeatable workflow.
It measures the same task shapes across agent-crew and reference AI harnesses
without making the README directly target any specific program.

The machine-readable scenario list is:

```text
core/evaluations/harness-scenario-benchmark.json
```

## Method

Run each system in a fresh repository checkout with the same host model,
credentials, network policy, and time budget. Record both wall-clock timing and
evidence quality. If a system cannot run in the current environment, mark that
cell `blocked` and record the missing prerequisite instead of substituting a
different task.

## Scenarios

| ID | Scenario | What It Measures |
|---|---|---|
| `first_handoff` | Install or refresh, initialize a repository, start a read-only task, and show state | First-run usability, task-start latency, and operator confidence |
| `implementation_with_tests` | Make one scoped change and verify it | End-to-end workflow reliability, retries, and evidence completeness |
| `approval_recovery_audit` | Exercise a guarded operation and recover from a host handoff if needed | Approval discipline, recovery clarity, and auditability |

## Metrics

| Metric | Direction | Notes |
|---|---|---|
| setup elapsed time | lower is better | Include package/bootstrap time only when required for normal use |
| task-start elapsed time | lower is better | Time from operator request to visible task state or worker launch |
| completion elapsed time | lower is better | Only compare equal task scope and equal verification requirements |
| human interventions | lower is better | Count clarifications, approvals, manual repairs, and shell retries |
| evidence completeness | higher is better | Count durable state, result, trace, test, audit, and pass/fail artifacts |
| recovery clarity | higher is better | Score whether a new operator can resume from printed state alone |

## agent-crew Baseline Commands

```bash
crew update
crew setup
crew doctor --mode host

crew run "Summarize repository architecture and record evidence."
crew status --summary
crew trace --recent 1

crew run "Make a scoped documentation or fixture change and verify it."
crew status --summary
crew telemetry --recent 5

crew run "Perform a guarded local workflow and record audit evidence."
crew status --summary
crew trace --recent 1 --include-tools
crew telemetry --recent 5 --format json
```

## Reporting Template

| System | Scenario | Setup ms | Start ms | Complete ms | Interventions | Evidence Files | Result |
|---|---|---:|---:|---:|---:|---:|---|
| agent-crew | `first_handoff` | TBD | TBD | TBD | TBD | TBD | TBD |
| agent-crew | `implementation_with_tests` | TBD | TBD | TBD | TBD | TBD | TBD |
| agent-crew | `approval_recovery_audit` | TBD | TBD | TBD | TBD | TBD | TBD |
| reference harness A | `first_handoff` | TBD | TBD | TBD | TBD | TBD | TBD |
| reference harness A | `implementation_with_tests` | TBD | TBD | TBD | TBD | TBD | TBD |
| reference harness A | `approval_recovery_audit` | TBD | TBD | TBD | TBD | TBD | TBD |
| reference harness B | `first_handoff` | TBD | TBD | TBD | TBD | TBD | TBD |
| reference harness B | `implementation_with_tests` | TBD | TBD | TBD | TBD | TBD | TBD |
| reference harness B | `approval_recovery_audit` | TBD | TBD | TBD | TBD | TBD | TBD |

## Interpretation Rule

agent-crew should win only where the evidence proves it: durable state,
approval governance, recovery, telemetry, and audit trail quality. It should
not claim superiority on catalog breadth, public traction, or first-run
polish unless measured data supports that claim.
