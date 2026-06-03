# Harness Benchmark: agent-crew vs OMC vs ECC

Date: 2026-06-01

This benchmark compares agent-crew with two representative harness programs:

- oh-my-claudecode (OMC): https://github.com/Yeachan-Heo/oh-my-claudecode
- ECC: https://github.com/affaan-m/ECC

The comparison uses public repository metadata and README claims checked on
2026-06-01, plus local agent-crew validation artifacts.

## Positioning

| System | Primary Position |
|---|---|
| agent-crew | Local control plane for host AI workflows: state, routing, guardrails, approval gates, telemetry, recovery |
| OMC | Claude Code-first productized orchestration experience with Team, Autopilot, Ralph, UltraQA, HUD, tmux workers |
| ECC | Cross-harness operator/config system with broad skills, hooks, rules, MCP, security, and commercial surfaces |

## Public Traction

| Metric | agent-crew | OMC | ECC |
|---|---:|---:|---:|
| GitHub stars | Unknown / not benchmarked in this repo | 35,447 | 200,864 |
| GitHub forks | Unknown / not benchmarked in this repo | 3,239 | 30,823 |
| Recent public push | Local source | 2026-06-01T02:58:47Z | 2026-05-31T06:45:42Z |

Interpretation: agent-crew is not currently competitive on market signal. It
must compete on operational control, auditability, and recovery rather than
community scale.

## Capability Matrix

| Capability | agent-crew | OMC | ECC |
|---|---|---|---|
| Multi-agent orchestration | Strong: supervisor, stage agents, parallel-first tasks, resolver | Strong: Team pipeline, Autopilot, Ralph, UltraQA, tmux workers | Medium-strong: broad agent/harness workflows |
| State and recovery | Strong: deterministic task dirs, repair, resume, trace, telemetry | Medium: product workflow state/HUD, less explicit local ledger in README | Medium-strong: session/state infrastructure, SQLite in recent releases |
| Approval governance | Strong: centralized gate, plaintext approval guard, destructive action protocol | Medium: workflow guidance and quality loops | Medium: security/hooks/rules, depends on host support |
| Cross-harness support | Designed provider-neutral; hosted evidence still incomplete | Claude-first, with Codex/Gemini worker integrations | Strongest: Claude, Cursor, Codex, OpenCode, Copilot, Gemini, Zed claims |
| UX | Improving but still complex | Strong | Strong |
| Skill breadth | Focused: 29 core skill files plus adapter templates | Strong: 19 specialized agents and skill learning | Very strong: README claims 249 skills and broad language ecosystems |
| Validation evidence | Strong local tests; hosted evidence incomplete | Unknown from this local audit | Strong public claims: large internal test suites |

## agent-crew Competitive Strengths

- Better fit for auditable AI work: every task has state, progress, telemetry,
  result, and repair artifacts.
- Stronger governance model than typical skill packs: destructive operations
  flow through centralized approval.
- Provider-neutral architecture is explicit: capabilities are advertised by
  adapters rather than assumed globally.
- Better suited to regulated/team workflows where "what happened?" matters as
  much as "did code get written?"

## agent-crew Gaps

- Public hosted Codex and Claude auto-completion evidence is still deferred.
- Full E2E SLO previously depended on local memory-store contents; this has now
  been made deterministic for the control-plane check, but representative
  populated-memory hosted evidence is still needed.
- Operator UX remains heavier than polished productized harnesses. `crew run`,
  `crew status`, `crew doctor`, and `crew repair` need concise defaults and
  richer detail only on demand.
- Skill catalog breadth is far behind broad catalog-oriented harnesses.
- Market proof is far behind both competitors.

## Readiness Judgment

| Category | Score | Rationale |
|---|---:|---|
| Architecture | 8/10 | Deep state, workflow, guardrail, and recovery design |
| Product UX | 5.5/10 | Powerful but concept-heavy |
| Market proof | 2/10 | No comparable public traction evidence |
| Enterprise/control-plane fit | 7/10 | Strong auditability and approval model |

Overall: agent-crew should avoid positioning itself as a generic "everything
harness" today. The credible wedge is **auditable local control plane for AI
development workflows**.

## Benchmark Follow-Ups

1. Produce clean hosted Codex and Claude evidence without manual repair.
2. Keep full `e2e-slo-check.py` passing in CI.
3. Run a timed scenario benchmark across agent-crew and the reference
   harnesses on the same task set.
4. Measure first-run setup time, task-start time, recovery time, and evidence
   completeness for all three systems.
5. Publish the results as a dedicated benchmark artifact, not as README hero
   copy.

## Follow-Up Artifacts

- Timed scenario benchmark plan:
  `docs/harness-scenario-benchmark.md`
- Machine-readable scenario definition:
  `core/evaluations/harness-scenario-benchmark.json`
- Approval, recovery, and audit demo:
  `docs/approval-recovery-audit-demo.md`
- Hosted evidence runbook:
  `docs/hosted-validation-evidence.md`
