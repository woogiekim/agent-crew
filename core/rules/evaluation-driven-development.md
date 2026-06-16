# Evaluation-Driven Development

Evaluation-Driven Development applies the Red -> Green -> Refactor discipline
to agentic workflows, prompts, retrieval, and other behavior where a normal unit
test is not enough. It is optional and activated when `pipeline.json` includes:

```json
{
  "eval_command": "python3 evals/run.py"
}
```

## Runtime Artifact

When `eval_command` is present, the completed task must write:

```text
{TASK_DIR}/context/evaluation-metrics.json
```

Minimal shape:

```json
{
  "schema_version": 1,
  "command": "python3 evals/run.py",
  "status": "passed",
  "baseline": "optional baseline id",
  "metrics": {"accuracy": 1.0},
  "regressions": []
}
```

`status` should be `passed`, `failed`, or `blocked`. Store raw eval output in a
separate artifact when it is large and reference it from the metrics JSON.

## Completion Gate

The runtime quality-loop gate rejects a completed mutating task with
`missing_evaluation_metrics` when `eval_command` is set and
`context/evaluation-metrics.json` is absent. Malformed metrics are rejected with
an explicit `*_evaluation_metrics_*` failure label.

## Relationship To Tests

EDD complements normal tests. Use it for prompt quality, retrieval precision,
agent workflow replay, benchmark scores, and other probabilistic or corpus-based
surfaces.
