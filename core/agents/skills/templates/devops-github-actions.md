---
name: devops-github-actions
description: >
  Adapter skill for the `devops` dispatcher (Wave C exemplar). Loaded when
  the dispatcher detects a `.github/workflows/` directory in PROJECT_ROOT.
  Captures the GitHub Actions workflow layout + `gh release create` release
  flow that `core/agents/devops.md` historically documented inline, now
  extracted into a Channel B seed template per
  `core/rules/agent-tool-dispatch.md`.
loaded_by: devops
axis: github-actions
detection: .github/workflows/ directory present in PROJECT_ROOT
---

# devops-github-actions — Adapter Skill

This skill is the **Channel B seed template** for the `devops` dispatcher
when the detected CI / deployment-target axis is `github-actions`. It is
faithfully re-packaged from the GitHub Actions + release CLI content that
`core/agents/devops.md` documented prior to the Wave C refactor — see
`core/rules/agent-tool-dispatch.md` § Channel B template seeding for the
runtime contract (`crew:setup` copy-if-absent; never overwrites a user
edit).

## Tools Required

| Tool | Purpose |
|---|---|
| Repository write access to `.github/workflows/` | Author CI / CD / release workflow YAML files |
| `gh` GitHub CLI (recommended) | Publish a Release after tag push (`gh release create`) |
| `git tag` / `git push origin <tag>` | Create and push the release tag the workflow keys off |

The `gh` CLI is preferred for Release creation because it produces the same
artifact as `actions/create-release` and is host-agnostic (works the same
in CI and on a developer's machine). When `gh` is unavailable, the
tag-only path still triggers any release workflow keyed on `on: push:
tags:` — but the human-readable Release entry must then be created
through another path (manual web UI, REST API, or workflow that calls
`actions/create-release`).

## Inputs (GitHub Actions-specific)

In addition to the abstract dispatcher inputs (`TASK_DIR`, `PROJECT_ROOT`,
the supervisor-owned approval gate), this adapter consumes:

- `VERSION` — semantic version string for the release (e.g. `1.2.3`). The
  dispatcher derives this from `package.json`, `build.gradle`, a `VERSION`
  file, or whichever manifest matches the project. The leading `v` is
  added by the tag command.
- `RELEASE_NOTES` — summary of changes for `gh release create --notes`.
  When absent, fall back to the most recent commit message body.

---

## Step 0 — Authenticate

GitHub Actions runs server-side authenticate themselves via the workflow's
`${{ secrets.GITHUB_TOKEN }}` (per-repo default token) or an explicit
OIDC / PAT secret. The adapter's responsibility on the developer side is
limited to verifying `gh` is logged in for the release path:

```bash
gh auth status 2>/dev/null
```

If `gh` is not authenticated, the release-publication step in Step 3 below
becomes tag-only — emit a warning line and continue:

```
[devops-github-actions] gh CLI not authenticated — release tag will be pushed but Release entry must be created manually.
```

No interactive auth prompt — see the dispatcher's YOU MUST NOT rule about
the host's interactive question mechanism.

---

## Step 1 — Workflow Layout

GitHub Actions workflow files live at `.github/workflows/`. The dispatcher's
declared workflow shape (CI on PR, CD on main, release on tag) maps to three
canonical files:

| File | Trigger | Purpose |
|---|---|---|
| `.github/workflows/ci.yml` | `on: pull_request` | PR build & test gate (required for branch-protection) |
| `.github/workflows/cd.yml` | `on: push: branches: [main]` | Deploy on merge to `main` |
| `.github/workflows/release.yml` | `on: push: tags: ['v*']` | Tag-based release (artifact publish, Release entry) |

A repo MAY combine `ci.yml` + `cd.yml` into a single workflow with two
top-level `jobs:` filtered by `if: github.event_name == ...`, but the
three-file layout is the documented default because it keeps the
branch-protection required-check list stable.

### Common Configuration Principles (12-Factor)

- Inject configuration through `env:` blocks at the workflow / job level,
  not hardcoded inside `run:` steps.
- Use `secrets:` for credentials; never inline tokens in YAML.
- Cache language toolchains using `actions/setup-*` (e.g.
  `actions/setup-node`, `actions/setup-java`, `actions/setup-python`)
  with `cache: <pkg-manager>` set so dependency resolution is incremental.
- Cache build output via `actions/cache@v4` keyed on the lockfile hash so
  the cache invalidates correctly across dependency changes.
- Mark jobs `fail-fast: true` (the default for `strategy.matrix`) so a
  single language/version failure short-circuits the matrix.
- Set `permissions:` to the minimum scope the job needs (default to
  `contents: read`; escalate to `contents: write` only inside the release
  workflow).

### Reusable Workflow Boundary

When more than one repo in the org runs the same CI shape, extract the
shared steps into a reusable workflow under `.github/workflows/_shared.yml`
and invoke it via `uses: ${{ github.repository_owner }}/<repo>/.github/workflows/_shared.yml@<ref>`.
Do **not** copy-paste full workflow YAML across repos — drift is the
default failure mode.

---

## Step 2 — Build & Test

The build/test command set is owned by the dispatcher's Deploy Step 2
table (`./gradlew build -x test`, `npm run build`, `make build`,
`docker build .`, etc.). This adapter's only obligation is to invoke those
commands inside the GitHub Actions runner with the right setup action
chain:

```yaml
# Example shape — ci.yml jobs.build
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-{lang}@v4
        with:
          {lang}-version: '<pinned-version>'
          cache: '<pkg-manager>'
      - run: <dispatcher-supplied build command>
      - run: <dispatcher-supplied test command>
```

**If tests fail, the workflow exits non-zero. Do not proceed with
deployment.** This mirrors the dispatcher's hard rule.

---

## Step 3 — Git Tagging & Release

The dispatcher's Deploy Step 3 owns the tag-creation workflow:

```bash
git tag -a v${VERSION} -m "Release v${VERSION}"
git push origin v${VERSION}
```

The release-publication call is delegated to this adapter. When `gh` CLI
is authenticated (verified in Step 0 above), create the Release entry:

```bash
gh release create v${VERSION} \
  --title "v${VERSION}" \
  --notes "${RELEASE_NOTES}"
```

Additional `gh release create` flags worth knowing for this axis:

- `--draft` — publish as a draft. Use when the release notes need
  out-of-band editing before users see the entry.
- `--prerelease` — mark the release as a pre-release. The Releases page
  filter treats these separately from production releases.
- `--latest=false` — explicitly opt the release out of the "Latest
  release" badge. Useful for security backports to old major versions.
- `--target <ref>` — pin the release to a specific commit / branch when
  it must not be the tag's commit (rare; usually the tag is on the
  correct ref already).
- `--notes-file <path>` — read release notes from a file rather than
  inline. Prefer this when notes span multiple paragraphs or include
  markdown lists.

When `gh` is unavailable or not authenticated (Step 0 emitted the warning
line), the tag push alone still triggers `release.yml` (if the workflow
exists), so any artifact-publish job inside it runs. The human-readable
Release entry must then be created through another path.

---

## Step 4 — Deployment Trigger

GitHub Actions supports several deployment triggers; pick the one that
matches the workflow shape the dispatcher wrote in Step 1:

| Trigger | Use case |
|---|---|
| `on: push: branches: [main]` (cd.yml) | Continuous deployment from main |
| `on: push: tags: ['v*']` (release.yml) | Tag-based release deployment |
| `on: workflow_dispatch` | Manual button-press deploy (operator-initiated) |
| `on: deployment` | External system creates a deployment (e.g. Vercel, Render) and Actions reacts |

For `workflow_dispatch`, declare `inputs:` so the operator picks the
target environment, version, or any optional toggle (e.g.
`dry_run: type: boolean default: false`).

---

## Step 5 — Result Verification

GitHub Actions surfaces job status through the Checks API. The dispatcher's
Deploy Step 5 (HTTP health check via `curl -f`) runs inside the deploy job
itself, not as a separate adapter step. The adapter's verification
responsibility is limited to ensuring the workflow exposes the right
artifacts:

- Upload build artifacts via `actions/upload-artifact@v4` so they are
  visible in the Actions UI run summary.
- Annotate failures with `::error::` workflow commands so the failure
  surfaces inline in the PR Conversation tab.
- For deploys that produce a preview URL (Vercel, Netlify), comment the
  URL back to the PR via `actions/github-script` so the reviewer can
  click through.

---

## Step 6 — Workflow Quirks To Know

| Quirk | Symptom | Fix |
|---|---|---|
| Cache key collisions across branches | Cache restored from an unexpected branch's snapshot, breaking the build | Prefix the cache key with `${{ github.ref_name }}` or `${{ runner.os }}-{lang}-${{ hashFiles('**/lockfile') }}` |
| `permissions: contents: write` missing in release workflow | `gh release create` fails with HTTP 403 | Add `permissions: contents: write` at the job level in release.yml |
| Concurrent deploys to the same env | Two CD runs racing on the same target | Use `concurrency: group: deploy-${{ github.ref }} cancel-in-progress: false` to serialize |
| Workflow doesn't run on tag push | `on: push: tags:` not matching | Verify the tag pattern (`'v*'` requires the leading `v`); workflows on the **default branch only** are eligible for tag triggers |
| OIDC token not minted | Cloud provider rejects the workflow's federated identity | Add `permissions: id-token: write` at the job level |
| Self-hosted runner not picked up | Job sits queued indefinitely | Verify the `runs-on:` label matches the runner's labels exactly, including case |
| Re-run from failed step loses env vars | Step's `env:` block reset on re-run | Re-runs always restart the failed job from scratch — they do not resume — so any in-job state must be re-derived |

---

## Step 7 — Output Contract (per release run)

After the workflow completes the dispatcher's Deploy Step 6, surface the
following back to the dispatcher for inclusion in `handoff.md`:

```text
## Deployment Result (github-actions)

- Version: v{VERSION}
- Timestamp: {datetime}
- Branch: {branch}
- Tag: v{VERSION} pushed: {yes|no}
- Release entry: {gh release URL | tag-only (gh not authenticated)}
- Workflow runs:
    - ci.yml: {success|failure} (run URL)
    - release.yml: {success|failure} (run URL)
- Build: Success / Failure
- Test: Success / Failure
- Deployment: Success / Failure
- Notes: {issues or special remarks}
```

The dispatcher takes that block and merges it into `handoff.md` under its
own Deploy Step 6 reporting contract — this adapter MUST NOT write to
`handoff.md` directly.

---

## See also

- `core/agents/devops.md` — the dispatcher contract that loads this skill
- `core/rules/agent-tool-dispatch.md` § Channel B template seeding — the
  copy-if-absent runtime contract that ships this template
- `core/setup/seed-skill-templates.sh` — the install/update seed helper
- `~/.agent-crew/system/agents/skills/deployment-ops.md` — language-agnostic
  pre-flight / rollback / verification framework loaded by the dispatcher
  alongside this adapter
