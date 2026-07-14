# Skill: documentation-impact

---
name: documentation-impact
description: Keep user-facing documentation aligned with behavior changes without adding proof artifacts or heavy gates.
loaded_by: backend,frontend,devops,reviewer
axis: documentation-impact
detection: documentation OR README OR changelog OR public API OR CLI OR config OR workflow
---

## Source
- agent-crew user feedback, "avoid evidence-heavy mandatory gates; prefer lightweight default behavior", 2026-07-14.
- The Diataxis documentation framework, https://diataxis.fr/
- Olivier Lacan, *Keep a Changelog*, https://keepachangelog.com/

## When to Apply
- A change affects public behavior, API shape, CLI flags, configuration, deployment workflow, user-visible UI behavior, error messages, or agent-crew workflow semantics.
- An implementation edits files whose nearby README, docs, command help, examples, or changelog already describe the changed behavior.
- A reviewer sees a diff where behavior changed but the nearest existing documentation still describes the old behavior.
- A repeated review comment suggests an existing skill needs a small rule clarification.

## Core Rules

### Rule 1: Prefer nearby existing documentation
> Source: agent-crew user feedback, 2026-07-14; Diataxis, "Reference" and "How-to guides"

When behavior changes, first update the closest existing documentation that
already owns that behavior: README section, command help, docs page, example,
workflow note, or changelog entry. Do not create a new documentation file just
to satisfy this skill.

### Rule 2: Do not add proof artifacts
> Source: agent-crew user feedback, 2026-07-14

Do not require `doc-impact.md`, extra evidence JSON, checklist files, or
separate proof notes. Use the diff itself, existing docs, and the task summary.
Documentation alignment must improve the user-facing artifact, not add process
paperwork.

### Rule 3: Update only when the contract changed
> Source: Diataxis, "Reference"; Keep a Changelog, "Guiding Principles"

Update documentation for changed contracts: endpoint fields, command syntax,
configuration keys, workflow order, error behavior, observable UI behavior, or
operator steps. Do not edit docs for purely internal refactors, formatting,
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

## Anti-Patterns
- Requiring a documentation-impact proof file for every implementation.
- Creating new docs when a nearby README, command help, or existing guide is the owner.
- Blocking internal refactors because they did not touch user documentation.
- Treating task summaries as a substitute for updating stale public docs.
- Generating a new skill or agent when a 3-5 line addition to an existing skill would solve the repeated miss.

## Interaction with Other Skills
- Works with `code-review.md`: review documentation drift from the actual diff.
- Works with `agile-xp.md`: keep the change small and shippable.
- Works with `tdd.md`: do not replace behavior tests with documentation changes.

## References
- The Diataxis documentation framework, https://diataxis.fr/
- Olivier Lacan, *Keep a Changelog*, https://keepachangelog.com/
- agent-crew user feedback captured during the 2026-07-14 lightweight documentation/self-evolution design discussion.
