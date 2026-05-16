# Skill: deployment-ops

## Purpose
Enables the devops agent to safely plan, validate, and execute deployments and infrastructure changes by following a pre-flight → build → tag → deploy → verify sequence with mandatory approval gates.

## When to Apply
- When a deployment or release is requested after feature implementation
- When setting up or modifying CI/CD pipelines
- When managing containers, IaC (Terraform, Kubernetes), or shared modules
- When creating a release tag or GitHub Release
- After the supervisor pipeline reaches the deploy stage

---

## Semantic Versioning (semver.org)

Given a version `MAJOR.MINOR.PATCH`:

| Increment | When | Example |
|---|---|---|
| `MAJOR` | Breaking, backwards-incompatible changes | `1.4.2 → 2.0.0` |
| `MINOR` | New backwards-compatible features | `1.4.2 → 1.5.0` |
| `PATCH` | Backwards-compatible bug fixes | `1.4.2 → 1.4.3` |

Pre-release: `1.5.0-alpha.1`, `1.5.0-rc.2`. Build metadata: `1.5.0+build.42`.

Always read the current version before proposing a new tag:

```bash
# Gradle
grep "^version" build.gradle | head -1

# Node
node -p "require('./package.json').version"

# Fallback
cat VERSION 2>/dev/null || git describe --tags --abbrev=0
```

---

## Deployment Strategies

Choose based on risk tolerance and infrastructure capability:

| Strategy | Description | Rollback speed | Risk |
|---|---|---|---|
| **In-place** | Replace running instances directly | Slow (redeploy old) | High |
| **Rolling** | Replace instances one-by-one | Medium (drain old) | Medium |
| **Blue-Green** | Two identical envs; switch traffic | Instant (switch back) | Low |
| **Canary** | Route small % of traffic to new version | Instant | Very low |
| **Feature Flag** | Deploy code but gate with a flag | Instant (flip flag) | Very low |

**Blue-Green:**
```bash
# Point load balancer from blue → green
aws elbv2 modify-listener --listener-arn ${LB_ARN} \
  --default-actions Type=forward,TargetGroupArn=${GREEN_TG_ARN}

# Rollback: swap back to blue
aws elbv2 modify-listener --listener-arn ${LB_ARN} \
  --default-actions Type=forward,TargetGroupArn=${BLUE_TG_ARN}
```

---

## Approval Ownership

Do not issue deployment, push, merge, rollback, or branch-cleanup approvals from inside the devops agent. Write the planned actions to `{TASK_DIR}/context/action-plan.md`, return a `PLAN:` block, and wait for the approval signal. The supervisor owns approval for single-task runs; the crew orchestrator owns approval for parallel runs.

The approval signal is delivered through **two paths**:

1. **File-based (always available)**: Poll `approval.md` for `APPROVED` or `CANCELLED` every 5 seconds up to 60 seconds.
2. **Capability-gated wakeup (`task_tools=true`)**: When `${TASK_DIR}/host-task-id.txt` exists, long-poll `TaskGet(taskId).status` instead of sleeping. Always re-read `approval.md` for the final verdict after either path resolves.

Never execute `git push`, create remote tags, run deployment scripts, or modify production infrastructure before `APPROVED` is present.

---

## Pre-flight Validation

```bash
# Clean working tree
git status --short
git diff --stat HEAD

# Correct branch
git branch --show-current

# Required scripts present
ls deploy.sh scripts/deploy.sh Makefile docker-compose.yml 2>/dev/null
```

Block deployment if: uncommitted changes exist, unmerged PRs are open, build scripts are missing, or approval has not been written to `{TASK_DIR}/context/approval.md`.

---

## Build Tool Auto-Detection

| Detected File | Build Command | Test Command |
|---|---|---|
| `gradlew` / `build.gradle` | `./gradlew build -x test` | `./gradlew test` |
| `package.json` | `npm run build` | `npm test` |
| `Makefile` | `make build` | `make test` |
| `Dockerfile` | `docker build .` | — |

Never proceed to deployment if tests fail.

---

## Git Tagging and Release

After approval, create an annotated local tag. Record remote tag pushes and GitHub Release creation in the action plan for orchestrator-owned execution:

```bash
git tag -a v{VERSION} -m "Release v{VERSION}: {summary}"
# Remote push is orchestrator-owned; include in action-plan.md, not executed here
```

---

## Deployment Script Priority

Execute in this order:

1. `deploy.sh`
2. `scripts/deploy.sh`
3. `make deploy` (if Makefile has a deploy target)
4. `docker-compose up -d`

If no script exists, write the missing deployment method to the action plan and return `STATUS: plan_ready`.

---

## Health Verification

```bash
# HTTP health check
curl -sf "${HEALTH_URL}/health" || exit 1

# Docker
docker ps --filter "name={SERVICE_NAME}" --filter "status=running"

# Kubernetes
kubectl rollout status deployment/{DEPLOYMENT_NAME} --timeout=120s

# Kubernetes — detailed pod status
kubectl get pods -l app={APP_LABEL} -o wide
```

Treat non-zero exit codes as deployment failure. Never mark deployment as successful without verification.

---

## Rollback Decision Matrix

| Condition | Action |
|---|---|
| Health check fails immediately after deploy | Rollback immediately; no manual escalation needed |
| Error rate rises above baseline within 5 min | Rollback or route traffic back to stable version |
| DB migration ran with data loss risk | Halt; escalate to operator before rollback |
| Blue-green swap performed | Swap LB back to blue; blue is already running |
| Rolling deploy in progress | Stop rollout, drain new instances, rollout old image |

---

## DORA Four Key Metrics (Reference: Google DORA Research)

Capture these in the deployment report when data is available:

| Metric | Elite | High | Medium | Low |
|---|---|---|---|---|
| Deployment Frequency | On-demand | Daily | Weekly | Monthly |
| Lead Time for Changes | < 1 hour | < 1 day | 1 week | 1 month |
| Change Failure Rate | < 5% | < 10% | 10–15% | > 15% |
| Time to Restore | < 1 hour | < 1 day | 1 day | 1 week |

---

## 12-Factor App Compliance (Reference: 12factor.net)

When writing or modifying CI/CD configs, check:

| Factor | Check |
|---|---|
| III. Config | All env-specific values from environment variables, not hardcoded |
| V. Build/Release/Run | Build, release, and run stages strictly separated |
| XI. Logs | App writes to stdout; log aggregation outside the app |
| XII. Admin processes | One-off tasks (migrations) run as isolated processes |

---

## Checklist
- [ ] Action plan written to `{TASK_DIR}/context/action-plan.md`
- [ ] Approval observed in `{TASK_DIR}/context/approval.md` before any destructive action
- [ ] Pre-flight check completed (clean tree, correct branch, scripts found)
- [ ] Deployment strategy chosen and documented (in-place / rolling / blue-green / canary)
- [ ] Build executed and all tests pass
- [ ] Deployment blocked if tests fail
- [ ] SemVer increment justified (MAJOR / MINOR / PATCH)
- [ ] Version detected from project version file
- [ ] Local git tag created when required; remote tag push recorded for orchestrator-owned execution
- [ ] Deployment script executed in priority order
- [ ] Health check verified after deployment; rollback plan ready if check fails
- [ ] No secrets hardcoded in any config file
- [ ] `handoff.md` updated with deployment result, version, timestamp, and notes
