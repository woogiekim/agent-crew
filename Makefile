# agent-crew — top-level test orchestration Makefile.
#
# Usage:
#   make test              # all suites (python + shell + integration)
#   make test-python       # pytest only
#   make test-shell        # bash tests in tests/shell/
#   make test-integration  # bash tests in tests/integration/
#   make help              # list available targets

PYTEST ?= pytest

.PHONY: help test test-python test-shell test-integration phase-1-validation

help:
	@echo "agent-crew Makefile targets:"
	@echo "  make test               run all test suites"
	@echo "  make test-python        run pytest (tests/python/)"
	@echo "  make test-shell         run shell tests (tests/shell/)"
	@echo "  make test-integration   run integration tests (tests/integration/)"
	@echo "  make phase-1-validation run first-phase validation framework"

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
