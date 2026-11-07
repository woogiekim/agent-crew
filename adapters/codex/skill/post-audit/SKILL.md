---
name: post-audit
description: Use when the user explicitly mentions $post-audit or asks for a post-implementation audit of changed code, hardening gaps, missed checks, architecture risks, contract compatibility, tests, security, operations, or KDoc/documentation after implementation.
---

# post-audit

This Codex skill delegates to the provider-neutral user workflow in
`~/.agent-crew/commands/post-audit.md`.

## Execution

1. Load `~/.agent-crew/commands/post-audit.md` in full before acting.
2. Treat text after `$post-audit` as the audit scope. Treat this wrapper as the
   target only when the user explicitly names the skill, wrapper, file, or
   `SKILL.md` as the object.
3. Keep the pass read-only unless the user explicitly asks for follow-up edits.
4. Use the canonical command's human-readable default report. Preserve the meaning of
   must-fix `AUTO FAIL` issues and heuristic `WARN` items, but render them with natural
   headings unless an explicit raw/debug mode is requested.
5. Preserve the user's output language for narrative report prose. On this PC,
   Korean default rules mean report prose should be Korean. Keep structured
   tokens and file paths in their original language.
6. Route any follow-up implementation, destructive action, push, merge, or
   deploy through the appropriate agent-crew workflow and explicit approval decision.
7. Ask follow-up decisions with friendly ordinary numbered choices such as `1.` / `2.`;
   do not use circled digit characters or mechanical approval labels in the default output.
