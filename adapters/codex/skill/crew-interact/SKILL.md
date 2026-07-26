---
name: crew-interact
description: Use when the user invokes $crew-interact to start a natural-language interaction with another AI session. This is a thin Codex wrapper for crew:interact.
---

# crew-interact

This Codex skill is an alias for:

```text
crew:interact
```

## Execution

1. Treat any user text after `$crew-interact` as a natural-language interaction request.
2. List friendly AI session candidates before any send step.
3. Hide opaque relay/session ids unless debugging requires them.
4. Preserve the selected target and request as input for the relay internals.
5. Treat a follow-up selection of `1` as the recommended first candidate.
6. Treat `--select` without `--send` as selection only (`STATUS: selected`).
7. When `--send` is explicit, report `STATUS: sent` only if the host/session
   delivery adapter returns explicit success.
8. If direct delivery is unsupported, create a relay package and report
   `STATUS: packaged`.
9. Clipboard fallback is opt-in only with `--copy`; do not copy by default.

Session candidates must come from real AI host sessions. agent-crew task/request
state is enrichment only and must not appear as a session by itself.

The shell form is:

```bash
crew interact "{natural language request}"
crew interact --to "{session description}" --select 1 --send "{prompt}"
```
