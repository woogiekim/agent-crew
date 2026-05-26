# agent-crew — top-level test orchestration Makefile.
#
# Usage:
#   make test              # all suites (python + shell + integration)
#   make test-python       # pytest only
#   make test-shell        # bash tests in tests/shell/
#   make test-integration  # bash tests in tests/integration/
#   make help              # list available targets

PYTEST ?= pytest
COVERAGE_BASE_REF ?= origin/main

.PHONY: help test test-python coverage-python test-shell test-integration phase-1-validation phase-2-validation release-checksums readiness-metrics commercialization-ci

help:
	@echo "agent-crew Makefile targets:"
	@echo "  make test               run all test suites"
	@echo "  make test-python        run pytest (tests/python/)"
	@echo "  make coverage-python    run all suites with changed-surface 100% and full policy enforcement"
	@echo "  make test-shell         run shell tests (tests/shell/)"
	@echo "  make test-integration   run integration tests (tests/integration/)"
	@echo "  make phase-1-validation run first-phase validation framework"
	@echo "  make phase-2-validation run second-phase validation framework"
	@echo "  make release-checksums  generate installer/update checksums"
	@echo "  make readiness-metrics  aggregate commercial readiness metrics"
	@echo "  make commercialization-ci run full suite + phase validations + checksums"

test:
	@bash tests/run-all.sh

test-python:
	@bash tests/run-all.sh python

coverage-python:
	@python3 -m coverage erase
	@rm -f coverage.json .coverage.json
	@AGENT_CREW_SUBPROCESS_COVERAGE=1 python3 -m coverage run -p -m pytest tests/python -q
	@set -e; \
		tmp_wrap="$$(mktemp -d)"; \
		trap 'rm -rf "$${tmp_wrap}"' EXIT; \
		coverage_site="$$(python3 -c 'from pathlib import Path; import coverage; print(Path(coverage.__file__).resolve().parent.parent)')"; \
		cp tests/coverage-python-wrapper "$${tmp_wrap}/python3"; \
		chmod +x "$${tmp_wrap}/python3"; \
		AGENT_CREW_REAL_PYTHON="$$(command -v python3)" \
		AGENT_CREW_COVERAGE_SITE="$${coverage_site}" \
		AGENT_CREW_CORE_SCRIPTS="$$(pwd)/core/scripts" \
		PATH="$${tmp_wrap}:$${PATH}" \
		bash tests/run-all.sh shell integration
	@python3 -m coverage combine -q
	@python3 -m coverage json -o coverage.json
	@python3 core/scripts/coverage-changed-surface.py \
		--coverage-json coverage.json \
		--base-ref "$(COVERAGE_BASE_REF)" \
		--minimum 100 \
		--format text
	@python3 core/scripts/coverage-total-policy.py \
		--coverage-json coverage.json \
		--exceptions core/coverage/python-coverage-exceptions.json \
		--minimum 100 \
		--format text

test-shell:
	@bash tests/run-all.sh shell

test-integration:
	@bash tests/run-all.sh integration

phase-1-validation:
	@python3 core/scripts/phase-1-validation.py

phase-2-validation:
	@python3 core/scripts/phase-2-validation.py

release-checksums:
	@python3 core/scripts/generate-release-checksums.py \
		--output dist/release-checksums.json \
		--sha256sums dist/SHA256SUMS

readiness-metrics:
	@python3 core/scripts/readiness-metrics.py \
		--format text

commercialization-ci: test phase-1-validation phase-2-validation release-checksums
	@python3 core/scripts/generate-release-checksums.py \
		--verify dist/release-checksums.json
