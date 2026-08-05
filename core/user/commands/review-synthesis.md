# /review-synthesis — Parallel Review Synthesis

## Purpose

Run or collect multiple read-only review lenses in parallel and return one
combined operator-facing report.

This workflow is for receiving synthesis feedback after review-related
commands, skills, agents, and provider-native review capabilities inspect the
same scope from different angles. It does not fix code, post MR notes, update
MR descriptions, commit, push, merge, deploy, or mutate external systems.

## Review Lens Discovery

Before selecting lenses, run review lens discovery using
`core/scripts/review-lens-discovery.py` or the installed equivalent. Discovery
uses the provider-neutral contract in `core/rules/review-lens-discovery.md`.

Discovery must separate installed capability from execution result:

- classify read-only, non-mutating, context-compatible lenses as `eligible`;
- promote an `eligible` lens to `completed` only after it actually runs and
  produces an artifact or inline result in the current synthesis pass;
- report MR-only lenses as `not-run` when MR context is unavailable;
- report parity lenses as `suggested` or `blocked` when the comparison
  contract, source/target repository, or mode is missing;
- report supervisor-only agents such as the system `reviewer` as `blocked`;
- report mutating review follow-up commands as `blocked`;
- report duplicate semantic lenses as `duplicate-suppressed`.

Do not directly invoke the system `reviewer` agent. It is supervisor-spawned.

## Default Lenses

The default lens set remains:

- generic review;
- post-audit;
- MR review-rate when MR context exists;
- parity when parity or producer/consumer contract scope exists;
- domain/user skills when capability dispatch selects them.

Provider-native lenses may participate only when their metadata declares a
read-only, non-mutating review-lens contract and the host adapter reports them
available.

## Output

The synthesis report must list every discovered or configured lens with one of:
`eligible`, `completed`, `not-run`, `suggested`, `blocked`, `degraded`, or
`duplicate-suppressed`. Every finding must preserve its source lens label, and
local implementation status must stay separate from remote MR completion.
