# agent-crew test suite

Hermetic, provider-neutral test coverage for the agent-crew Python
validators, shell scripts, and end-to-end integration scenarios.

## Layout

```
tests/
├── README.md            # this file
├── conftest.py          # pytest fixtures: hermetic AGENT_CREW_HOME, state_dir, task_dir
├── run-all.sh           # discovers + runs every suite; emits summary table
├── python/              # pytest-based tests
│   ├── test_validate_state_schema.py
│   ├── test_check_plaintext_approval.py
│   ├── test_telemetry_aggregate.py
│   ├── test_cost_aggregate.py
│   └── test_phase_2_validation.py
├── shell/               # bash tests (one file per script)
│   ├── _lib.bash        # shared bash assertion harness
│   ├── test_common_sh.bash
│   ├── test_detect_inject_intent.bash
│   ├── test_migrate_rm_stale.bash
│   ├── test_sync_instructions.bash
│   └── test_seed_instruction_rules.bash
└── integration/         # end-to-end scenarios across multiple scripts
    ├── test_ssot_roundtrip.bash
    ├── test_pipeline_schema_validity.bash
    ├── test_crew_status_render.bash
    └── test_cli_smokes.bash
```

## How to run

### Everything
```bash
make test
# or
bash tests/run-all.sh
```

### Individual suites
```bash
make test-python        # pytest suite
make coverage-python    # pytest + changed-surface 100% + full coverage policy
make test-shell         # bash assertions
make test-integration   # integration assertions
```

### Single file
```bash
pytest tests/python/test_validate_state_schema.py -v
bash tests/shell/test_common_sh.bash
bash tests/integration/test_pipeline_schema_validity.bash
```

### Single test (pytest)
```bash
pytest tests/python/test_cost_aggregate.py::TestCostAggregate::test_check_breaker_exceeded -v
```

### Validation passes
```bash
python3 core/scripts/phase-1-validation.py --plan-only
python3 core/scripts/phase-2-validation.py --plan-only
python3 core/scripts/phase-2-validation.py --level unit --format text
```

### Coverage policy

`make coverage-python` runs pytest under `coverage.py`, then enforces two gates:

- Changed Python execution surfaces under `core/scripts/` must be 100% covered.
- Full `core/scripts/` coverage debt must be explicit in
  `core/coverage/python-coverage-exceptions.json`; uncovered legacy files may
  not regress below their recorded baseline and must be removed from the
  exception list once they reach 100%.

## Requirements

- **Python 3.10+** with `pytest` importable by `python3`
  - `python3 -m pip install --user pytest`
  - `tests/run-all.sh` uses `pytest` from `$PATH` when present and otherwise
    falls back to `python3 -m pytest`.
  - If pytest is missing entirely, `tests/run-all.sh` skips the python suite
    with an install hint and still runs shell + integration.
- **coverage.py** for `make coverage-python`
  - `python3 -m pip install --user coverage`
- **Bash 3.2+** (tests are written for macOS / Linux default bash)
- **git** (for `test_common_sh.bash::register_local_git_excludes` —
  uses a tmp `git init` worktree).

The standard test suite has no additional dependencies. Tests never touch the real
`${HOME}/.agent-crew/` or the user's mnemos store — every suite uses
`tmp_path` (pytest) or `mktemp -d` (bash) for isolation.

## Hermeticity guarantees

- **pytest**: the `agent_crew_home`, `state_dir`, `task_dir` fixtures
  build a fresh per-test home under pytest's `tmp_path` and copy the
  in-repo `core/schemas/*.schema.json` into it. The `env_with_home`
  fixture builds an env dict that points `AGENT_CREW_HOME`,
  `AGENT_CREW_STATE_DIR`, `AGENT_CREW_PROJECT` at the hermetic dirs.
- **bash**: every test creates its own `mktemp -d` tree via the
  `make_tmp` helper in `_lib.bash`. `cleanup_tmp` runs at end + on
  EXIT trap.
- **mnemos**: `test_sync_instructions.bash`, `test_seed_instruction_rules.bash`,
  and `test_ssot_roundtrip.bash` use a **mock mnemos** stub that
  persists rule content to flat files in a tmp dir. The real mnemos
  CLI is never invoked.

## How to add a new test

### Python test
1. Create `tests/python/test_<script_name>.py`.
2. Use the `script_runner` fixture (from `conftest.py`) to invoke any
   script under `core/scripts/`. It returns a `subprocess.CompletedProcess`.
3. Use `env_with_home`, `agent_crew_home`, `state_dir`, `task_dir`
   fixtures for hermetic environment setup.
4. Run `pytest tests/python/test_<script_name>.py -v` to verify.

### Bash test
1. Create `tests/shell/test_<script_name>.bash` (or
   `tests/integration/test_<scenario>.bash`).
2. `source "$(dirname "$0")/_lib.bash"` (or
   `"$(dirname "$0")/../shell/_lib.bash"` from integration/).
3. Use `it "describes the assertion"` to name each check, then call one
   of `assert_eq`, `assert_exit`, `assert_contains`, `assert_not_contains`,
   `assert_file_exists`, `assert_file_absent`, `assert_true`.
4. Use `make_tmp` to allocate tmp dirs; the `cleanup_tmp` EXIT trap will
   reclaim them.
5. End with `end_report` — it prints the per-file summary and exits
   non-zero if any assertion failed.

## Debugging a failing test

### Python
```bash
pytest tests/python/test_<file>.py::test_<name> -v -s --tb=long
```
The `-s` flag disables output capture so you can see prints from the
script under test.

### Bash
```bash
bash -x tests/shell/test_<file>.bash 2>&1 | less
```
The `-x` flag traces every command. The `_lib.bash` harness records
failure details in `FAILED_DETAILS[]` and prints them in `end_report`.

To inspect the tmp dirs used by a test, comment out the `cleanup_tmp`
call inside the test or override the trap.

## Known issues (surfaced by the suite)

- **`register_local_git_excludes` is CWD-dependent.**
  The function in `core/setup/common.sh` uses
  `git -C "${project_root}" rev-parse --git-path info/exclude`, which
  returns a RELATIVE path. Subsequent `mkdir`, `touch`, and Python
  writes operate against the caller's CWD, not `${project_root}`. The
  function only works correctly when the caller has already `cd`'d into
  `project_root`. This matches how `install.sh` and `setup-host.sh`
  invoke it in production, but is a footgun for any other caller.
  A robust fix would be to either pass `--absolute-git-dir` to
  `git rev-parse`, or `cd "${project_root}"` inside the function.
  `tests/shell/test_common_sh.bash` pushd-s into the project root
  before calling the function to exercise the success path.

## CI hooks

`tests/run-all.sh` returns exit 0 on full success, exit 1 on any suite
failure. Wire it into your CI of choice (GitHub Actions, GitLab CI,
etc.) as a single command — no other setup steps required beyond
`pip install pytest`.
