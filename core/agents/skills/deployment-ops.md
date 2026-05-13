# Skill: deployment-ops

## Purpose
Enables the devops agent to safely plan, validate, and execute deployments and infrastructure changes by following a pre-flight → build → tag → deploy → verify sequence with mandatory approval gates.

## When to Apply
- When a deployment or release is requested after feature implementation
- When setting up or modifying CI/CD pipelines
- When managing containers, IaC (Terraform, Kubernetes), or shared modules
- When creating a release tag or GitHub Release
- After the task-runner pipeline reaches the deploy stage

## Techniques

### Pre-flight Validation
Before any deployment action, run a structured pre-flight check to detect blockers:

```bash
# Verify clean working tree
git status --short
git diff --stat HEAD

# Verify on correct branch
git branch --show-current

# Locate deployment scripts
ls deploy.sh scripts/deploy.sh Makefile docker-compose.yml 2>/dev/null
```

Block deployment if: uncommitted changes exist, unmerged PRs are open, build
scripts are missing, or the required approval signal has not been written to
`{TASK_DIR}/context/approval.md`.

### Approval Ownership
Do not issue deployment, push, merge, rollback, or branch-cleanup approvals from
inside the devops agent. Write the planned actions to
`{TASK_DIR}/context/action-plan.md`, return a `PLAN:` block, and wait for the
approval signal. The task-runner owns approval for single-task runs; the crew
orchestrator owns approval for parallel runs.

The approval signal is delivered through **two paths that converge on the same
artifact** — `{TASK_DIR}/context/approval.md` is the contractual record:

1. **File-based primary (always available).** Poll `approval.md` for `APPROVED`
   or `CANCELLED` every 5 seconds up to 60 seconds. This is the canonical path
   for adapters without host task tools (codex, generic) and the fallback for
   any failure of the host-tool path below.
2. **Capability-gated wakeup (P1, when `capabilities.json` advertises
   `task_tools=true`).** When `${TASK_DIR}/host-task-id.txt` exists, the
   task-runner's approval gate ALSO calls
   `TaskUpdate(taskId, status="in_progress")` on APPROVED or
   `TaskUpdate(taskId, status="cancelled")` on CANCELLED. The agent can
   long-poll `TaskGet(taskId).status` for an immediate wakeup instead of
   sleeping 5 seconds at a time. After either path resolves, **always re-read
   `approval.md` for the final verdict** — the host call is the wakeup signal,
   the file is the contract.

Never run `git push`, create remote tags, execute deployment scripts, or modify
production infrastructure before approval is present. In task-runner pipelines,
remote pushes are still orchestrator-owned: record the intended push or tag push
in the action plan instead of executing it directly.

### Build Tool Auto-Detection
Detect the project build tool and run standardized commands:

| Detected File | Build Command | Test Command |
|---|---|---|
| `gradlew` / `build.gradle` | `./gradlew build -x test` | `./gradlew test` |
| `package.json` | `npm run build` | `npm test` |
| `Makefile` | `make build` | `make test` |
| `Dockerfile` | `docker build .` | — |

Never proceed to deployment if tests fail.

### Semantic Version Detection
Read the current version from the project's version file before tagging:

```bash
# Gradle
grep "^version" build.gradle | head -1

# Node
node -p "require('./package.json').version"

# Fallback
cat VERSION 2>/dev/null || git describe --tags --abbrev=0
```

### Git Tagging and Release
After approval, create an annotated local tag when the release plan requires it.
Record remote tag pushes and GitHub Release creation in the action plan for the
orchestrator-owned deployment step:

```bash
git tag -a v{VERSION} -m "Release v{VERSION}: {summary}"
```

### Deployment Script Priority
Execute deployment scripts in this priority order:

1. `deploy.sh`
2. `scripts/deploy.sh`
3. `make deploy` (if Makefile has a deploy target)
4. `docker-compose up -d`

If no script exists, write the missing deployment method to the action plan and
return `STATUS: plan_ready` so the task-runner or orchestrator can collect the
deployment decision. Include the missing command as an explicit blocker in the
`PLAN:` block; do not prompt the user directly from the devops agent.

### Health Verification
After deployment, verify the service is healthy:

```bash
# HTTP health check
curl -f "${HEALTH_URL}/health" || exit 1

# Docker
docker ps --filter "name={SERVICE_NAME}" --filter "status=running"

# Kubernetes
kubectl rollout status deployment/{DEPLOYMENT_NAME}
```

Treat non-zero exit codes as deployment failure. Never mark deployment as successful without verification.

### 12-Factor Config Compliance
When writing or modifying CI/CD configs:
- All secrets and environment-specific values must come from environment variables or secret managers — never hardcoded
- Build, test, and deploy stages must be explicitly separated
- Use layer caching to minimize build time
- Implement fail-fast: stop the pipeline on first failure

## Checklist
- [ ] Action plan written to `{TASK_DIR}/context/action-plan.md`
- [ ] Approval observed in `{TASK_DIR}/context/approval.md` before deployment, push, merge, tag push, or release
- [ ] Pre-flight check completed (clean tree, correct branch, scripts found)
- [ ] Build executed and all tests pass
- [ ] Deployment blocked if tests fail
- [ ] Version detected from project version file
- [ ] Local git tag created when required; remote tag push recorded for orchestrator-owned execution
- [ ] GitHub Release created (if gh CLI available)
- [ ] Deployment script executed in priority order
- [ ] Health check verified after deployment
- [ ] No secrets hardcoded in any config file
- [ ] `handoff.md` updated with deployment result, version, timestamp, and notes
