# Skill: deployment-ops

## Purpose
Plan and validate deployments and infrastructure changes. Follow pre-flight → build → tag → deploy → verify, with mandatory approval gates.

## When to Apply
- Deployment or release after implementation, including release tags and GitHub Releases
- CI/CD setup or changes, containers, IaC (Terraform, Kubernetes), or shared modules
- Supervisor pipeline deploy stage

---

## Semantic Versioning (semver.org)

Use `MAJOR.MINOR.PATCH`.

| Increment | When | Example |
|---|---|---|
| `MAJOR` | Breaking, backwards-incompatible changes | `1.4.2 → 2.0.0` |
| `MINOR` | New backwards-compatible features | `1.4.2 → 1.5.0` |
| `PATCH` | Backwards-compatible bug fixes | `1.4.2 → 1.4.3` |

Pre-release: `1.5.0-alpha.1`, `1.5.0-rc.2`. Build metadata: `1.5.0+build.42`.

Read the current version before proposing a tag.

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

Choose for the risk tolerance and infrastructure capabilities.

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

The supervisor approves single-task runs. The crew orchestrator approves parallel runs. DevOps cannot approve deployments, pushes, merges, rollbacks, or branch cleanup.

Write `{TASK_DIR}/context/action-plan.md`, return a `PLAN:` block, and wait:

- Poll `approval.md` every 5 seconds for up to 60 seconds for `APPROVED` or `CANCELLED`.
- With `task_tools=true` and `${TASK_DIR}/host-task-id.txt`, long-poll `TaskGet(taskId).status` instead.

Re-read `approval.md` for the final verdict after either path. Require `APPROVED` before `git push`, remote tags, deployment scripts, or production infrastructure changes.

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

Block deployment for uncommitted changes, open unmerged PRs, missing build scripts, or missing approval in `{TASK_DIR}/context/approval.md`.

---

## Build Tool Auto-Detection

| Detected File | Build Command | Test Command |
|---|---|---|
| `gradlew` / `build.gradle` | `./gradlew build -x test` | `./gradlew test` |
| `package.json` | `npm run build` | `npm test` |
| `Makefile` | `make build` | `make test` |
| `Dockerfile` | `docker build .` | — |

Block deployment if tests fail.

---

## Git Tagging and Release

After approval, create an annotated local tag. Record remote tag pushes and GitHub Releases in the action plan for the orchestrator.

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

If no script exists, record the missing deployment method in the action plan and return `STATUS: plan_ready`.

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

Non-zero exits mean deployment failure. Claim success only after verification.

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

Report available metrics.

| Metric | Elite | High | Medium | Low |
|---|---|---|---|---|
| Deployment Frequency | On-demand | Daily | Weekly | Monthly |
| Lead Time for Changes | < 1 hour | < 1 day | 1 week | 1 month |
| Change Failure Rate | < 5% | < 10% | 10–15% | > 15% |
| Time to Restore | < 1 hour | < 1 day | 1 day | 1 week |

---

## 12-Factor App Compliance (Reference: 12factor.net)

Check when editing CI/CD configs.

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
