---
name: evidence-grounded-reasoning
description: >
  Provider-neutral rule for analysis, judgment, review, and planning outputs.
  Requires first-party evidence, explicit inference, and traceable conclusions.
applies-to: all agents producing analysis, judgment, review, or planning output
---

# Evidence-Grounded Reasoning Rule

Analysis, judgment, review, and planning outputs must be grounded in cited
first-party evidence. Agents must not present unsupported assertions as facts,
and they must keep the reasoning path auditable without relying on any specific
model, host adapter, or vendor capability.

## Evidence Standard

Use first-party evidence whenever the repository, task state, or direct tool
output can answer the question:

- Repository files, cited as `path:line` or `path:start-line` when line numbers
  are available.
- Task-local artifacts, such as `{TASK_DIR}/context/requirements.md`,
  `{TASK_DIR}/context/prd.md`, `{TASK_DIR}/handoff.md`, review reports,
  quality metrics, or progress logs.
- Direct tool output, cited as `tool-output: <command or tool name>` with a
  short result summary when file lines are not applicable.

External references may provide context, but they do not replace first-party
evidence for claims about this repository, task state, tests, or implementation.

## Required Reasoning Flow

Every analysis, judgment, review, or planning output must make this flow
explicit:

```text
Evidence: {file:line, task artifact path, or tool-output summary}
Inference: {what the evidence supports, including uncertainty if any}
Conclusion: {decision, recommendation, finding, approval, rejection, or plan}
```

The exact formatting may match the artifact being written, but the three parts
must be present and distinguishable. Tables are acceptable when the columns are
equivalent to Evidence, Inference, and Conclusion.

## Mandatory Uses

Apply this rule before returning or writing:

- analysis artifacts, readiness verdicts, risk assessments, or ambiguity
  evaluations;
- pipeline plans, PRDs, action plans, or stage sequencing decisions;
- review findings, approval or rejection verdicts, quality judgments, and
  coverage conclusions;
- supervisor judgments about stage completion, blocked states, retries, and
  final task status.

## Citation Discipline

- Cite `file:line` evidence for claims derived from repository content whenever
  line numbers are available.
- Cite task artifacts by path for claims derived from task state.
- Cite direct tool output for commands, checks, tests, or generated reports.
- Mark missing evidence as `Unknown` or `Unverified`; do not fill gaps with
  speculation.
- Keep conclusions narrower than the evidence. If the evidence only supports a
  partial claim, the conclusion must say so.

## Completion Gate

A stage that produces analysis, judgment, review, or planning output is not
complete until the relevant artifact includes cited first-party evidence and an
explicit evidence-to-inference-to-conclusion flow.
