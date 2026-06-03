# Requirements Sufficiency Gate

Use this rule only when a `crew:run` task reaches requirements production and
no `REQUIREMENTS` block was already provided. Do not preload this rule at
command or supervisor startup.

The gate preserves the invariant that `REQUIREMENTS` exists before planning
while avoiding a requirements-agent spawn for task descriptions that already
carry enough scope, target, and constraint signal.

## Runtime Helper

The scoring and synthesis logic lives in:

```text
core/scripts/requirements-sufficiency.py
```

Installed commands should call the installed copy under
`${AGENT_CREW_HOME}/scripts/requirements-sufficiency.py`; source-tree tests may
call `core/scripts/requirements-sufficiency.py` directly.

Status check:

```bash
SUFFICIENCY=$(python3 "${AGENT_CREW_HOME}/scripts/requirements-sufficiency.py" \
  --status "${TASK}")
```

Interaction policy check:

```bash
POLICY=$(python3 "${AGENT_CREW_HOME}/scripts/requirements-sufficiency.py" \
  --policy \
  --intensity "${AGENT_CREW_INTERACTION_INTENSITY:-balanced}" \
  "${TASK}")
```

Inline synthesis:

```bash
python3 "${AGENT_CREW_HOME}/scripts/requirements-sufficiency.py" \
  --write "${TASK_DIR}/context/requirements.md" "${TASK}"
```

`SUFFICIENT` means the helper can infer:

- scope: backend, UI, full-stack, or tooling/docs/config
- target: specific file, branch, quoted object, concrete workflow surface, or
  at least two named workflow targets
- constraints: performance/latency, quality/failure guidance, MVP scope,
  dependency limits, no remote publish without approval, or explicit
  function/interface spec for script-file tasks

Question-like prompts always return `AMBIGUOUS`.

## Interaction Intensity Policy

The helper keeps the legacy `SUFFICIENT` / `AMBIGUOUS` status contract stable,
then adds an OMC-inspired policy layer for hosts and commands that need a finer
decision:

| Intensity | Policy |
|---|---|
| `light` | Question-shaped read-only work may use `direct_answer`; mutating ambiguous work still collects requirements. |
| `balanced` | Default. Preserve the current single-round requirements interview for ambiguous implementation work. |
| `deep` | If ambiguity is above the threshold, run `MODE=deep_interview`; otherwise use the single-round path. |
| `strict` | Treat the threshold as the implementation gate. Implementation is allowed only when `ambiguity <= ambiguity_threshold`; otherwise run `MODE=deep_interview` and keep implementation blocked until the gate passes. |

Configuration:

```text
AGENT_CREW_INTERACTION_INTENSITY=light|balanced|deep|strict
AGENT_CREW_AMBIGUITY_THRESHOLD=0.20
```

The default threshold is `0.20`. This is a deterministic policy threshold, not
a statistical confidence claim.

## Output Contract

When `SUFFICIENT`, the helper writes the same block shape the requirements
agent returns:

```text
REQUIREMENTS: |
  scope: {synthesized scope}
  target: {synthesized target}
  constraints: {comma-separated synthesized constraints}
  followup: (none)
  sufficiency: HIGH
  ambiguity: {0.00-1.00}
  ambiguity_threshold: {0.00-1.00}
  interaction_intensity: {light|balanced|deep|strict}
  implementation_allowed: {true|false}
  inline_synthesis: true
```

When `AMBIGUOUS`, do not synthesize. Delegate to the requirements agent in
the mode selected by the policy action: `single_round` for `balanced` and most
`light` implementation work, or `deep_interview` for high-ambiguity `deep` /
`strict` work.
