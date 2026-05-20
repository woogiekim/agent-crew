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
  inline_synthesis: true
```

When `AMBIGUOUS`, do not synthesize. Delegate to the requirements agent in
single-round mode.
