---
name: documentation-impact
description: Keep user-facing documentation aligned with behavior changes without adding proof artifacts or heavy gates.
loaded_by: backend,frontend,devops,reviewer
axis: documentation-impact
profile_type: review-policy
detection: documentation OR README OR changelog OR public API OR CLI OR config OR workflow
---

# Skill: documentation-impact

## Source
- agent-crew user feedback, "avoid evidence-heavy mandatory gates; prefer lightweight default behavior", 2026-07-14.
- agent-crew user feedback, "documentation is part of continuous integration of shared understanding, not only CI build output", 2026-07-18.
- The Diataxis documentation framework, https://diataxis.fr/
- Olivier Lacan, *Keep a Changelog*, https://keepachangelog.com/

## When to Apply
- A change affects public behavior, API shape, CLI flags, configuration, deployment workflow, user-visible UI behavior, error messages, or agent-crew workflow semantics.
- A change affects domain language, bounded-context ownership, migration parity, API payload/response contracts, operator workflows, or cross-repository integration contracts.
- An implementation edits files whose nearby README, docs, command help, examples, or changelog already describe the changed behavior.
- A reviewer sees a diff where behavior changed but the nearest existing documentation still describes the old behavior.
- A repeated review comment suggests an existing skill needs a small rule clarification.

## Core Rules

### Rule 1: Prefer nearby existing documentation
> Source: agent-crew user feedback, 2026-07-14; Diataxis, "Reference" and "How-to guides"

When behavior changes, first update the closest existing documentation that
already owns that behavior: README section, command help, docs page, example,
workflow note, migration note, contract table, or changelog entry. Do not
create a new documentation file just to satisfy this skill.

### Rule 2: Do not add proof artifacts
> Source: agent-crew user feedback, 2026-07-14

Do not require `doc-impact.md`, extra evidence JSON, checklist files, or
separate proof notes. Use the diff itself, existing docs, and the task summary.
Documentation alignment must improve the user-facing artifact, not add process
paperwork.

### Rule 3: Update only when the contract changed
> Source: Diataxis, "Reference"; Keep a Changelog, "Guiding Principles"

Update documentation for changed contracts: endpoint fields, command syntax,
configuration keys, workflow order, error behavior, observable UI behavior,
operator steps, domain ownership, migration parity, or cross-repo integration
responsibility. Do not edit docs for purely internal refactors, formatting,
renames that do not leak into the contract, or temporary repair work.

### Rule 4: Review documentation drift from the diff
> Source: agent-crew user feedback, 2026-07-14

During review, compare changed public behavior against existing documentation.
Flag drift only when the diff proves a user-facing contract changed and a
nearby existing document still says otherwise. Do not ask for a separate proof
file or block merely because no documentation artifact was produced.

### Rule 5: Prefer small patches to existing skills
> Source: agent-crew self-evolution direction, 2026-07-14

When repeated review comments expose an agent behavior gap, prefer a small
patch to the closest existing skill over generating a new skill, agent, or
workflow. New assets are a last resort after an existing asset cannot own the
rule cleanly.

### Rule 6: Treat documentation as continuous integration
> Source: agent-crew user feedback, 2026-07-18; Agile/XP continuous integration; DDD ubiquitous language

Before closeout, perform a lightweight documentation sync pass for the actual
diff:

1. List changed externally visible concepts: endpoints, GraphQL fields, request
   or response payloads, config keys, commands, operator steps, domain terms,
   ownership boundaries, and migration parity decisions.
2. Search nearby documentation and repository docs for those exact concepts.
3. If an owning document exists and would become stale, update it in the same
   change.
4. If no owning document exists, do not create a proof file; mention in the
   final summary that no existing documentation owner was found.

The goal is continuous integration of code, tests, documentation, and shared
domain language. A green build is not enough when the shared contract document
still teaches the old behavior.

### Rule 7: Make missing documentation a review finding when it is real drift
> Source: agent-crew user feedback, 2026-07-18

Reviewer agents should classify documentation drift as `IMPORTANT` when all of
these are true:

- the diff changes a public contract, operator workflow, cross-repo contract,
  or domain ownership decision;
- an existing nearby document already owns that contract; and
- the document would mislead the next implementer, reviewer, operator, or
  client integrator if left unchanged.

If the change is internal-only or no existing documentation owner is found
after a focused search, do not block. Report the no-doc-owner fact in the
summary instead.

## Anti-Patterns
- Requiring a documentation-impact proof file for every implementation.
- Creating new docs when a nearby README, command help, or existing guide is the owner.
- Blocking internal refactors because they did not touch user documentation.
- Treating task summaries as a substitute for updating stale public docs.
- Marking a change "CI green" when tests pass but the owned contract document still describes the old behavior.
- Generating a new skill or agent when a 3-5 line addition to an existing skill would solve the repeated miss.

## Interaction with Other Skills
- Works with `code-review.md`: review documentation drift from the actual diff and block real stale-contract docs as `IMPORTANT`.
- Works with `agile-xp.md`: keep the change small and shippable while continuously integrating shared knowledge.
- Works with `domain-driven-design.md`: keep ubiquitous language, ownership boundaries, and domain contracts aligned with code.
- Works with `tdd.md`: do not replace behavior tests with documentation changes.

## References
- The Diataxis documentation framework, https://diataxis.fr/
- Olivier Lacan, *Keep a Changelog*, https://keepachangelog.com/
- agent-crew user feedback captured during the 2026-07-14 lightweight documentation/self-evolution design discussion.
