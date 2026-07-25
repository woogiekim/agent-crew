---
name: crew-sessions
description: Use when the user invokes $crew-sessions to list recent AI session candidates for crew interact.
---

# crew-sessions

This Codex skill is an alias for:

```text
crew:sessions
```

## Execution

List recent AI session candidates as friendly cards with AI type, project,
branch, recent work summary, and last activity time. Keep internal ids hidden
from normal output.

Candidates must come from real AI host sessions. agent-crew task/request state
is enrichment only and must not appear as a session by itself.

The shell form is:

```bash
crew sessions
```
