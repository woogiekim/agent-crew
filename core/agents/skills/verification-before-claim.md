---
name: verification-before-claim
description: Require fresh evidence before claiming work is done, fixed, reflected, deployed, updated, passing, or verified.
loaded_by: backend,frontend,devops,documenter,analyst,planner,reviewer
axis: verification-discipline
profile_type: review-policy
detection: completed OR done OR fixed OR reflected OR addressed OR passing OR verified OR verification OR evidence OR tests OR deployed OR updated OR 완료 OR 수정됨 OR 반영 OR 해결 OR 검증 OR 통과 OR 증거 OR 배포 OR 갱신
---

# Skill: verification-before-claim

## Purpose

Give agents a general, provider-neutral discipline for turning evidence into
claims. Use it to prevent summaries, review follow-ups, closeouts, and status
reports from saying "done", "fixed", "passing", "updated", or "deployed" more
strongly than the current evidence supports.

## References

Internal contracts:

- `core/rules/evidence-grounded-reasoning.md`
- `core/rules/self-verification.md`
- `core/rules/review-intent-fidelity.md`
- `core/rules/runtime-governance.md`

External references:

- Cem Kaner, Jack Falk, and Hung Q. Nguyen, *Testing Computer Software*, 2nd
  ed., 1999 — test results are evidence about scoped behavior, not blanket
  proof of correctness.
- Lisa Crispin and Janet Gregory, *Agile Testing*, 2009 — teams should make
  testing and quality information visible enough to guide release decisions.
- Martin Fowler, *Refactoring: Improving the Design of Existing Code*, 2nd ed.,
  2018 — refactoring and completion claims rely on frequent verification, not
  intent.

## When to Apply

- Before saying a task is complete, fixed, reflected, addressed, passing,
  deployed, updated, verified, or safe to merge.
- Before reporting that a review comment, requirement, bug, incident cause,
  migration, documentation update, or external note has been handled.
- Before converting a successful tool/process exit into a semantic conclusion.
- When reusing memory, old logs, prior summaries, or user-provided statements
  to support a current claim.

Skip only for tiny factual answers that make no completion, verification,
remote-state, or behavioral claim.

## Core Rules

### Rule 1: Name the claim before checking it

Write the claim in one short sentence, then identify the evidence type needed
for that exact claim.

```text
Claim: tests pass
Needs: current test command output with exit code 0

Claim: MR description was updated
Needs: current remote read after the update

Claim: review comment was reflected
Needs: reviewer intent + code evidence + semantic verification
```

If the needed evidence is unavailable, report `Unknown` or `blocked` instead of
weakening the claim into vague confidence.

### Rule 2: Fresh evidence beats memory and intention

Memory, prior summaries, task plans, old screenshots, cached logs, and intended
commands are context only. They can tell you what to check; they cannot prove
the current state.

Use fresh evidence from the current run whenever the claim is about:
- repository contents or diff;
- tests, build, lint, type check, or generated artifacts;
- remote MR/PR/issue/note/deployment state;
- runtime behavior, logs, DB state, API response, or UI state;
- review feedback being reflected.

### Rule 3: Separate transport success from semantic success

A command, bridge, workflow, API call, or script returning success only proves
that the transport or tool step completed. It does not prove the requested
behavior changed.

```text
Tool success: glab command returned 0
Semantic check: re-read the MR/note/body and compare it to the intended text

Tool success: test command exited 0
Semantic check: confirm the selected tests cover the changed behavior

Tool success: agent handoff completed
Semantic check: inspect the produced artifact or final report
```

### Rule 4: Match evidence strength to claim strength

Do not use a broad claim when the evidence is narrow.

```text
Narrow evidence                         | Allowed claim
--------------------------------------- | -------------------------------
One focused unit test passed             | focused regression passed
Package/build passed offline             | local offline build passed
Remote MR body re-read after update      | MR body reflects this text
Diff shows code path changed             | local code changed
No live traffic/log/API check             | runtime behavior unverified
```

If only local evidence exists, say local. If remote or runtime evidence is not
checked, say it is unverified.

### Rule 5: Use disposition labels for review follow-up

For each review item, use one of these labels:

```text
IMPLEMENTED      code/test evidence proves requested behavior
LOCAL_DONE       local code is done, remote MR/PR text or push is not verified
PARTIAL          some evidence exists but the reviewer intent is not fully met
DEFERRED         intentionally waiting on policy, product, owner, or external input
NOT_APPLICABLE   evidence proves the comment does not apply to this scope
UNKNOWN          current evidence is missing or ambiguous
```

Never collapse `DEFERRED`, `PARTIAL`, or `UNKNOWN` into "done" for a cleaner
summary.

### Rule 6: Report evidence in a reusable shape

Prefer short, parseable evidence lines over prose-heavy reassurance:

```text
VERIFY:
- cmd: <command>
  result: <exit/status>
  scope: <what this proves>
  gap: <what this does not prove>
```

For remote writes, include the post-write read:

```text
VERIFY:
- wrote: <remote action>
- re-read: <command or API read>
- observed: <matching field/text/status>
```

### Rule 7: If blocked, name the missing edge

State the exact edge that prevents the stronger claim:

```text
Unknown: remote MR body was not re-read in this run.
Unknown: runtime API behavior was not checked.
Blocked: policy decision is needed before implementing idempotency.
Blocked: dependency is not cached and online verification needs approval.
```

Avoid generic disclaimers such as "may need more testing" when you know the
specific missing evidence.

## Anti-Patterns

- "Should be fixed" after only reading code.
- "Tests pass" after writing a command but not running it.
- "Review reflected" after changing nearby code but not mapping reviewer intent.
- "MR updated" after composing text but not performing or re-reading the remote
  mutation.
- "Deployment succeeded" after a local build or config render only.
- Treating an agent/process success status as proof of the user's requested
  outcome.
- Hiding local-only status by omitting words like local, draft, offline,
  focused, or unverified.

## Interaction with Other Skills

- `tdd.md`: provides implementation-cycle evidence. This skill controls the
  final claim made from that evidence.
- `systematic-debugging.md`: root-cause claims must cite reproduction and code
  path evidence before recommending a fix.
- `documentation-impact.md`: documentation updates are claimed only after the
  owning document or no-owner search was checked.
- `code-review.md` and `review-intent-fidelity.md`: review follow-up claims must
  preserve reviewer intent and map each item to evidence.

## Checklist

- [ ] The final answer identifies each strong claim being made.
- [ ] Each strong claim has current-run evidence or is downgraded.
- [ ] Local, remote, runtime, and policy states are not mixed together.
- [ ] Tool/process success is not presented as semantic success.
- [ ] Missing evidence is named under `Unknown` or `Blocked`.
- [ ] The final wording is no stronger than the evidence.
