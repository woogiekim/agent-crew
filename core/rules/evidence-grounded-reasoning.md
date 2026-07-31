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

When the output responds to feedback, review comments, automation results,
refactoring suggestions, or migration follow-up, also apply
`core/rules/contract-first-feedback-fidelity.md`: treat external input as a
hypothesis, verify it against explicit and implicit contracts, and keep the
conclusion narrower than the evidence.

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

## Evidence-First Verification Protocol

Bug reports, incident analysis, and root-cause reports must use this stricter
reporting structure whenever they explain a defect, production symptom,
integration failure, or suspected regression.

### Step 1: Hypothesis

State the suspected cause as a hypothesis, not as a conclusion. A useful
hypothesis names the component, condition, and expected failure mode.

### Step 2: Evidence Collection

Collect first-party evidence before reporting the cause:

- code evidence from the actual method, class, adapter, rule, or config;
- test evidence that reproduces, falsifies, or narrows the hypothesis;
- git evidence when the timing or origin of a behavior matters;
- log, error, trace, or HTTP evidence when runtime behavior is the claim;
- integration or end-to-end evidence when a boundary between systems is the
  suspected fault.

If the report cannot collect required evidence, keep the item in Needed
Evidence and do not promote it into Proven Facts or Conclusion.

### Step 3: Classify Evidence

Use these report sections:

```text
## Proven Facts
- {fact supported by file, test, log, trace, git, or tool-output evidence}

## Unverified Hypotheses
- {hypothesis that remains plausible but lacks enough evidence}

## Falsified Hypotheses
- {hypothesis contradicted by current evidence, when applicable}

## Needed Evidence
- {specific command, file, log, test, trace, HAR, or runtime check still needed}

## Conclusion
- {narrow conclusion supported only by Proven Facts}
```

Do not put an unverified hypothesis in Conclusion. A conclusion may say
"Unknown" or "not yet proven" when the evidence is incomplete.

### Step 4: Report

Report proven facts first, then unverified or falsified hypotheses, then needed
evidence, then the narrow conclusion. The conclusion must not recommend code or
configuration changes whose necessity is still only hypothetical.

## Citation Discipline

- Cite `file:line` evidence for claims derived from repository content whenever
  line numbers are available.
- Cite task artifacts by path for claims derived from task state.
- Cite direct tool output for commands, checks, tests, or generated reports.
- Mark missing evidence as `Unknown` or `Unverified`; do not fill gaps with
  speculation.
- Keep conclusions narrower than the evidence. If the evidence only supports a
  partial claim, the conclusion must say so.

## Absence-Proof Discipline

Any claim that a feature, wiring, configuration, rule, or item is **ABSENT** or
constitutes a **GAP** requires evidence of an exhaustive search across adjacent,
sibling, and cross-referenced files. Declaring absence from a single file's
line-range alone is forbidden.

Four obligations when claiming absence:

1. **Search the sibling set.** Before claiming a rule is absent from
   `core/rules/`, list the directory and `grep` for the concept across all
   sibling files. The rule may live in an adjacently named file.

2. **Follow every cross-reference.** When the inspected file contains a pointer
   like "see `other-file.md` § X" or "applies the discipline from
   `path/foo.md`", open the referenced file before any absence claim. A pointer
   is a load-bearing dependency, not commentary.

3. **Search by surface, not by file.** Use concept keywords (the rule name, the
   function name, the symbol, the feature label) with `grep -rln` or `find`
   across the whole repository or the relevant subtree — not only the file you
   started from.

4. **Record the search in evidence.** The absence claim's Evidence column must
   enumerate the directories listed, the grep patterns run, and the
   cross-references followed — not just the single file inspected.

Forbidden patterns (must be flagged as a contract violation):

- "X is absent because lines N–M of `file.md` do not mention it"
  (single-file line-range claim).
- "There is no Y in the codebase" with no `grep -rln` / `find` evidence cited.
- An absence claim that cites a file containing a "see also" pointer without
  showing that the referenced file was opened.

The Evidence Standard (§ Evidence Standard above) and the Completion Gate
(below) enforce this discipline.

## Completion Gate

A stage that produces analysis, judgment, review, or planning output is not
complete until the relevant artifact includes cited first-party evidence and an
explicit evidence-to-inference-to-conclusion flow.
