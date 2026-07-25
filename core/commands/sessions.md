# crew:sessions

List recent AI session candidates in a user-friendly format.

AI sessions mean real host sessions from installed AI tools such as Codex and
Claude. agent-crew task/request state may enrich project, branch, or summary
fields, but it must not create a standalone session candidate.

## CLI

```bash
crew sessions
crew sessions --limit 5
```

## Output Contract

Each candidate should show:

- AI type
- project
- branch
- recent work summary
- last activity time

Internal session ids, task ids, and relay ids are intentionally hidden from the
default output. Users select by number or natural-language description.
