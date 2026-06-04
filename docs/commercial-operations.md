# Commercial Operations

This document defines the minimum operating policy set for a commercial
agent-crew release. It is intentionally repository-local so release readiness
can be reviewed without depending on a private runbook.

## Support

Supported channels:

- GitHub issues for defects, compatibility reports, and reproducible workflow
  failures.
- Security disclosure channel for suspected vulnerabilities or data exposure.
- Release notes for known limitations, fixed issues, and migration steps.

Support triage requirements:

- Acknowledge commercial-impacting support reports within one business day.
- Classify each report as defect, compatibility, documentation, operator error,
  feature request, or security.
- Record the affected host adapter, agent-crew version or commit, operating
  system, shell, and whether the task required manual repair.
- Do not ask users to post secrets, tokens, proprietary prompts, or private
  task output in public issues.

## Security Disclosure

Report suspected vulnerabilities privately before public disclosure. A valid
security report should include the affected version, reproduction steps, impact,
and any suggested mitigation.

Security response requirements:

- Acknowledge receipt within one business day.
- Assign severity using impact and exploitability.
- Provide a mitigation or fix plan before public disclosure when practical.
- Publish advisory notes for confirmed vulnerabilities that affect released
  installer, update, host adapter, hook, state-file, or telemetry paths.

## Privacy And Data Handling

agent-crew stores workflow state locally under collision-safe `~/.agent-crew/state/{PROJECT_STATE_KEY}`.
Task state may contain prompts, progress logs, validation evidence, task
results, adapter status, and operator notes.

Data handling requirements:

- Keep task state local unless the operator explicitly uploads evidence,
  publishes a release artifact, or posts issue content.
- Redact tokens, credentials, customer data, private repository names, and
  proprietary prompts before sharing evidence outside the local machine.
- Treat hosted adapter validation evidence as sensitive until reviewed.
- Generated checksum manifests contain file names, sizes, and SHA-256 hashes;
  they must not include secret file contents.

## Incident Response

An incident is any released behavior that can cause data exposure, credential
leakage, destructive operation without approval, incorrect task completion,
broken update/install path, or sustained hosted workflow failure.

Incident process:

1. Freeze externally visible actions for the affected release path.
2. Preserve evidence: failing command, task id, task directory, adapter, commit,
   release artifact, checksum manifest, and relevant logs.
3. Classify severity and user impact.
4. Ship mitigation, rollback instructions, or a fixed release after approval.
5. Publish a post-incident note with scope, root cause, detection, mitigation,
   and prevention follow-up.

## Compatibility And Version Policy

Compatibility is tracked across the native CLI, Codex adapter, Claude adapter,
generic adapter, supported shells, and supported operating systems.

Version policy:

- Commercial releases must include a commit SHA, release artifact checksum
  manifest, and validation evidence bundle.
- Installer and update compatibility changes must be additive when possible.
- Breaking changes require release notes, migration instructions, and an
  explicit compatibility-matrix update.
- Host adapter behavior must preserve approval gates for merge, push, tagging,
  issue closing, release publication, deployment, overwrite, reset, and branch
  cleanup.

Release support status:

- Current release: receives defect, security, and compatibility fixes.
- Previous minor release: receives critical security and installer/update fixes
  when practical.
- Older releases: best-effort support unless a commercial contract states
  otherwise.
