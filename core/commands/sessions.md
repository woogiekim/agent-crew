# crew:sessions

List recent AI session candidates in a user-friendly format.

AI sessions mean real host sessions from installed AI tools such as Codex and
Claude. agent-crew task/request state may enrich project, branch, or summary
fields, but it must not create a standalone session candidate.

Codex candidates include `session_index.jsonl` plus recent rollout session
headers from the last 3 days. Rollout discovery reads only session metadata and
turn-context headers, not full transcript bodies.

## CLI

```bash
crew sessions
crew sessions --limit 5
```

## Output Contract

Each candidate should show:

- AI type
- session title or another human-readable label when available
- project or cwd-derived project hint
- branch, using `branch: -` instead of repeating `unknown`
- cwd hint, preferably home-relative
- recent work summary
- last activity time

Internal session ids, task ids, and relay ids are intentionally hidden from the
default output. Users select by number or natural-language description, so the
default list must include enough visible information to distinguish candidates
that share the same project or branch. AoE candidates must show the AoE title
or cwd hint; `AoE registered session` alone is not a sufficient candidate
description. If an opaque id is needed to disambiguate otherwise identical
candidates, expose only a short non-secret suffix, never the full id.
