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

Block deployment if: uncommitted changes exist, unmerged PRs are open, or build scripts are missing.

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
Create an annotated tag and push it. Optionally create a GitHub Release:

```bash
git tag -a v{VERSION} -m "Release v{VERSION}: {summary}"
git push origin v{VERSION}

# GitHub Release (if gh CLI available)
gh release create v{VERSION} \
  --title "v{VERSION}" \
  --notes "{changelog or commit summary}"
```

### Deployment Script Priority
Execute deployment scripts in this priority order:

1. `deploy.sh`
2. `scripts/deploy.sh`
3. `make deploy` (if Makefile has a deploy target)
4. `docker-compose up -d`

If no script exists, ask the user for the deployment method before proceeding.

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
- [ ] Plan summary presented and approved via structured choice UI before any changes
- [ ] Pre-flight check completed (clean tree, correct branch, scripts found)
- [ ] Build executed and all tests pass
- [ ] Deployment blocked if tests fail
- [ ] Version detected from project version file
- [ ] Git tag created and pushed
- [ ] GitHub Release created (if gh CLI available)
- [ ] Deployment script executed in priority order
- [ ] Health check verified after deployment
- [ ] No secrets hardcoded in any config file
- [ ] `handoff.md` updated with deployment result, version, timestamp, and notes
