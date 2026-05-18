# Skill: {skill-name}

<!--
SKILL TEMPLATE — copy this file to create a new skill.
File naming convention: {topic}.md (kebab-case, lowercase)
Location: core/agents/skills/{skill-name}.md
-->

## Source
<!-- Canonical reference(s) this skill distills. -->
- Author, *Book / Article Title*, Year
- Author, *Book / Article Title*, Year

## When to Apply
<!--
Bullet list of concrete triggers — when should an agent load and apply
this skill? Be specific (e.g., "before writing any Kotlin data class").
-->
- Situation A
- Situation B

## Core Rules
<!--
LLM-actionable rules derived from the canonical source(s).
Each rule must be:
  - Imperative ("Prefer X", "Never Y", "Always Z")
  - Verifiable from the code alone (no subjective judgement)
  - Annotated with the source section or item it comes from
-->

### Rule 1: {short name}
> Source: {Author, Book Section / Item N}

Description. Code example where applicable:

```kotlin
// BAD
...
// GOOD
...
```

### Rule 2: {short name}
> Source: {Author, Book Section / Item N}

Description.

## Anti-Patterns
<!--
Explicit list of things NOT to do.
Mirror the "GOOD" examples above with their "BAD" counterparts.
-->
- Anti-pattern A: brief description
- Anti-pattern B: brief description

## Interaction with Other Skills
<!--
Optional. Note when this skill must be read together with another.
-->
- Works alongside `tdd.md` when …
- Supercedes `oop-principles.md` item N when …

## References
- Author, *Full Title*, Publisher, Year. ISBN / URL.
