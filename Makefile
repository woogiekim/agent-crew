# agent-crew — top-level test orchestration Makefile.
#
# Usage:
#   make test              # all suites (python + shell + integration)
#   make test-python       # pytest only
#   make test-shell        # bash tests in tests/shell/
#   make test-integration  # bash tests in tests/integration/
#   make help              # list available targets

PYTEST ?= pytest

.PHONY: help test test-python test-shell test-integration phase-1-validation phase-2-validation release-checksums readiness-metrics commercialization-ci

help:
	@echo "agent-crew Makefile targets:"
	@echo "  make test               run all test suites"
	@echo "  make test-python        run pytest (tests/python/)"
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
