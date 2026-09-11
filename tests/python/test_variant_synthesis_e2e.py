"""결정론적 회귀: 실제 Git/테스트/CLI, symbolic host ID 사용. 실제 AI E2E 아님."""

import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import pytest

from tests.python.test_variant_review_contract import make_review

ROOT = Path(__file__).resolve().parents[2]
REQUEST = "Normalize names and preserve first occurrence order when removing duplicates."
REVIEWER = "deterministic-regression-comparison"
IMPLEMENTER = "deterministic-regression-implementation"
FINAL_REVIEWER = "deterministic-regression-final-check"
BASE = "def normalize(values):\n    return list(values)\n"
TRIM = "def normalize(values):\n    return [value.strip() for value in values]\n"
UNIQUE = "def normalize(values):\n    return list(dict.fromkeys(values))\n"
FINAL = "def normalize(values):\n    return list(dict.fromkeys(value.strip() for value in values))\n"
CHECKS = '''import unittest
from service import normalize

class Contract(unittest.TestCase):
    def test_common(self):
        self.assertEqual(normalize([]), [])
        self.assertEqual(normalize(["Ada", "Bob"]), ["Ada", "Bob"])

    def test_trim(self):
        self.assertEqual(normalize([" Ada ", "Bob "]), ["Ada", "Bob"])

    def test_unique(self):
        self.assertEqual(normalize(["Bob", "Ada", "Bob"]), ["Bob", "Ada"])

    def test_composition(self):
        values = [" Ada ", "Ada", " Bob", "Bob ", ""]
        before = list(values)
        self.assertEqual(normalize(values), ["Ada", "Bob", ""])
        self.assertEqual(values, before)
        self.assertEqual(normalize(normalize(values)), normalize(values))

if __name__ == "__main__":
    unittest.main(verbosity=2)
'''


def git(root, *args):
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def read_json(path):
    return json.loads(path.read_text())


def execute_check(root, task_dir, name, suffix=""):
    command = [sys.executable, "-B", "checks.py", "Contract.test_" + name]
    run = subprocess.run(command, cwd=root, capture_output=True, text=True)
    log = task_dir / (name + suffix + ".log")
    log.write_text(run.stdout + run.stderr)
    return {"passed": run.returncode == 0, "command": shlex.join(command), "log": str(log)}


class Scenario:
    def __init__(self, tmp_path, native=False, equal=False):
        self.root = tmp_path / "repo"
        self.root.mkdir()
        self.home = tmp_path / "crew-home"
        self.state = self.home / "state" / "repo"
        self.state.mkdir(parents=True)
        self.native = native
        self.equal = equal
        git(self.root, "init", "-qb", "main")
        git(self.root, "config", "user.name", "Deterministic Regression")
        git(self.root, "config", "user.email", "regression@example.invalid")
        (self.root / "service.py").write_text(BASE)
        (self.root / "checks.py").write_text(CHECKS)
        git(self.root, "add", ".")
        git(self.root, "commit", "-qm", "baseline")
        self.base = git(self.root, "rev-parse", "HEAD")
        self.tasks = []
        self.commits = {}
        self.candidate_checks = {}
        for task_id, source in (("trim", TRIM), ("unique", UNIQUE)):
            candidate = tmp_path / task_id
            branch = "codex/candidate-" + task_id
            start = self.commits["trim"] if equal and task_id == "unique" else self.base
            git(self.root, "worktree", "add", "-qb", branch, str(candidate), start)
            if not (equal and task_id == "unique"):
                (candidate / "service.py").write_text(FINAL if equal else source)
                git(candidate, "commit", "-qam", task_id)
            self.commits[task_id] = git(candidate, "rev-parse", "HEAD")
            task_dir = self.state / "tasks" / task_id
            task_dir.mkdir(parents=True)
            checks = {name: execute_check(candidate, task_dir, name)
                      for name in ("common", "trim", "unique", "composition")}
            self.candidate_checks[task_id] = checks
            assert checks["common"]["passed"] and checks[task_id]["passed"]
            assert checks["unique" if task_id == "trim" else "trim"]["passed"] is equal
            assert checks["composition"]["passed"] is equal
            (task_dir / "result.md").write_text(
                "STATUS: completed\nSUMMARY: deterministic fixture; no AI execution\n")
            self.tasks.append({"task_id": task_id, "status": "completed", "branch": branch,
                               "project_root": str(candidate), "base_project_root": str(self.root),
                               "task_dir": str(task_dir), "task": REQUEST})
        self.session = {"session_id": "deterministic-e2e", "session_type": "variants",
                        "status": "running", "variants_workflow_version": 2,
                        "outcome_mode": "synthesis", "pre_run_head": self.base,
                        "base_task": REQUEST, "candidate_count": 2,
                        "selection_status": "pending", "selected_task_id": None,
                        "tasks": self.tasks}
        if native:
            artifacts = self.state / "variants" / self.session["session_id"]
            artifacts.mkdir(parents=True)
            self.session["variants_dir"] = str(artifacts)
        write_json(self.state / "session.json", self.session)

    def invoke(self, action, *args, success=True):
        if self.native:
            command = ["bash", str(ROOT / "core/bin/crew"), "variants", action, *args]
        else:
            command = [sys.executable, str(ROOT / "core/scripts/variant-session-collect.py"),
                       action, "--state-dir", str(self.state), *args]
        result = subprocess.run(command, cwd=self.root, text=True, capture_output=True,
                                env={**os.environ, "AGENT_CREW_HOME": str(self.home),
                                     "PROJECT_ROOT": str(self.root), "PYTHONDONTWRITEBYTECODE": "1"})
        if success:
            assert result.returncode == 0, result.stdout + result.stderr
        else:
            assert result.returncode != 0, result.stdout + result.stderr
        return result

    def call(self, action, *args):
        return json.loads(self.invoke(action, *args).stdout)

    def resume(self):
        return self.call("resume", "--timeout", "0", "--interval", "0.01")

    def review_and_prepare(self):
        ready = self.resume()
        assert ready["next_action"] == "review_required"
        claim = self.call("review", "--claim", ready["input_hash"])
        bound = self.call("review", "--bind", claim["token"], "--host-id", REVIEWER)
        assert bound["host_id"] == REVIEWER
        document = make_review(self.commits["trim"], base_commit=self.base,
                               input_hash=ready["input_hash"], base_task=REQUEST)
        template_unit = document["candidate_analyses"][0]["units"][0]
        template_decision = document["decisions"][0]
        document["units"] = [{"unit_id": unit, "requirement_ids": ["r1"], "description": unit}
                             for unit in ("trim", "unique")]
        document["candidate_analyses"] = []
        for task in self.tasks:
            task_id = task["task_id"]
            units = []
            for unit in ("trim", "unique"):
                analysis = copy.deepcopy(template_unit)
                analysis.update(unit_id=unit, five_w_one_h=self.analysis(task_id, unit),
                                strengths=[unit + " passed"] if self.equal or task_id == unit else [],
                                weaknesses=[] if self.equal or task_id == unit else [unit + " failed; see executed test"])
                units.append(analysis)
            document["candidate_analyses"].append(
                {"task_id": task_id, "commit": self.commits[task_id], "units": units})
        document["comparison"] = [
            {"unit_id": unit, "candidate_ids": ["trim", "unique"],
             "summary": ("Equal SHA and equal executed behavior; retain trim candidate without redundant mixing."
                         if self.equal else unit + " candidate passes its strength; the other fails the same test."),
             "compatibility": "Normalize before stable deduplication; neither mutates input."}
            for unit in ("trim", "unique")]
        document["decisions"] = []
        for unit in ("trim", "unique"):
            source_id = "trim" if self.equal else unit
            decision = copy.deepcopy(template_decision)
            decision.update(decision_id="adopt-" + unit, unit_id=unit, source_task_id=source_id,
                            action="retain" if self.equal else "adopt",
                            source_commit=self.commits[source_id], five_w_one_h=self.analysis(source_id, unit),
                            target="service.py:normalize", validation="Contract.test_" + unit,
                            compatibility="Trim before stable deduplication; preserve caller input.")
            document["decisions"].append(decision)
        document["semantic_review"]["reviewer_id"] = REVIEWER
        report = self.state / "deterministic-review.json"
        write_json(report, document)
        assert self.call("review", "--complete", claim["token"], "--report", str(report))["status"] == "completed"
        assert self.resume()["next_action"] == "synthesis_required"
        prepared = self.call("synthesize", "--prepare", ready["input_hash"])
        assert git(Path(prepared["project_root"]), "rev-parse", "HEAD") == self.base
        assert self.call("synthesize", "--prepare", ready["input_hash"])["token"] == prepared["token"]
        self.call("synthesize", "--bind", prepared["token"], "--host-id", IMPLEMENTER)
        return prepared

    def analysis(self, task_id, unit, commit=None):
        evidence = {"commit": commit or self.commits[task_id], "path": "service.py", "line": 2}
        if commit is None:
            evidence["task_id"] = task_id
        statements = {
            "who": "The caller passes values to service.normalize; the caller owns the input list.",
            "when": "Each normalize call constructs a new result before returning.",
            "where": "service.py:normalize; in-process list transformation, no external storage.",
            "what": (unit + " behavior is present." if commit or self.equal or task_id == unit
                     else unit + " behavior is absent; its executable case fails."),
            "how": ("Strip values before dict.fromkeys preserves first occurrence order." if commit or self.equal
                    else "List comprehension strips whitespace." if task_id == "trim"
                    else "dict.fromkeys removes duplicates while preserving insertion order."),
            "why": "A fresh result preserves the caller-owned input contract.",
        }
        return {key: {"statement": value, "basis": "observed", "reason": "Pinned source and executed checks.",
                      "evidence": [copy.deepcopy(evidence)]} for key, value in statements.items()}

    def finish(self, prepared, source=FINAL):
        root = Path(prepared["project_root"])
        task_dir = Path(prepared["task_dir"])
        (root / "service.py").write_text(source)
        git(root, "commit", "-qam", "combine compatible strengths")
        commit = git(root, "rev-parse", "HEAD")
        checks = {name: execute_check(root, task_dir, name)
                  for name in ("common", "trim", "unique", "composition")}
        result = {"commit": commit, "implementer_id": IMPLEMENTER, "reviewer_id": FINAL_REVIEWER,
                  "verdict": "approved", "unresolved_findings": [],
                  "acceptance": [{"requirement_id": "r1", **checks["common"]}],
                  "decision_results": [
                      {"decision_id": "adopt-" + unit, "implemented": checks[unit]["passed"],
                       "evidence": [{"path": "service.py", "line": 2, "commit": commit}],
                       "validation": checks[unit]} for unit in ("trim", "unique")],
                  "composition_checks": [{"name": "normalize-before-deduplicate", **checks["composition"]}],
                  "analysis": [{"unit_id": unit, "five_w_one_h": self.analysis(unit, unit, commit)}
                               for unit in ("trim", "unique")]}
        path = task_dir / "deterministic-result.json"
        write_json(path, result)
        receipt = self.call("synthesize", "--complete", prepared["token"], "--result", str(path))
        return receipt, result

    def assert_sources_unchanged(self):
        assert git(self.root, "rev-parse", "main") == self.base
        assert git(self.root, "status", "--porcelain") == ""
        for task in self.tasks:
            assert git(self.root, "rev-parse", task["branch"]) == self.commits[task["task_id"]]
            assert git(Path(task["project_root"]), "status", "--porcelain") == ""
        session = read_json(self.state / "session.json")
        assert session["selected_task_id"] is None
        assert [task["task_id"] for task in session["tasks"]] == ["trim", "unique"]
        for actual, original in zip(session["tasks"], self.tasks):
            assert {key: actual[key] for key in original} == original
        assert session["candidate_count"] == 2


@pytest.mark.parametrize("native", [False, True], ids=["collector", "native-cli"])
def test_deterministic_whole_flow_joins_strengths(tmp_path, native):
    scenario = Scenario(tmp_path, native)
    prepared = scenario.review_and_prepare()
    receipt, result = scenario.finish(prepared)
    assert receipt["next_action"] == "ready_for_apply"
    assert scenario.resume()["next_action"] == "ready_for_apply"
    assert result["commit"] not in {scenario.base, *scenario.commits.values()}
    checks = result["acceptance"] + result["composition_checks"]
    checks += [decision["validation"] for decision in result["decision_results"]]
    for check in checks:
        assert check["passed"] is True
        log = Path(check["log"])
        assert "OK" in log.read_text()
        assert receipt["log_hashes"][str(log)] == hashlib.sha256(log.read_bytes()).hexdigest()
    preview = scenario.invoke("apply", "--artifact", "final", "--target", "main", "--dry-run")
    assert "plan_hash:" in preview.stdout
    scenario.assert_sources_unchanged()


def test_failed_real_acceptance_prevents_ready(tmp_path):
    scenario = Scenario(tmp_path)
    prepared = scenario.review_and_prepare()
    receipt, result = scenario.finish(prepared, "def normalize(values):\n    return []\n")
    assert result["acceptance"][0]["passed"] is False
    assert "FAILED" in Path(result["acceptance"][0]["log"]).read_text()
    assert receipt["status"] == "needs_changes"
    assert scenario.resume()["next_action"] != "ready_for_apply"
    scenario.invoke("apply", "--artifact", "final", "--target", "main", "--dry-run", success=False)
    scenario.assert_sources_unchanged()


def test_equal_sha_candidates_retain_one_implementation_with_reason(tmp_path):
    scenario = Scenario(tmp_path, equal=True)
    assert scenario.commits["trim"] == scenario.commits["unique"]
    assert scenario.tasks[0]["project_root"] != scenario.tasks[1]["project_root"]
    prepared = scenario.review_and_prepare()
    receipt, result = scenario.finish(prepared)
    assert receipt["next_action"] == "ready_for_apply"
    document = read_json(scenario.state / "variant-review.json")
    assert all("Equal SHA" in item["summary"] for item in document["comparison"])
    assert all(item["action"] == "retain" and item["source_task_id"] == "trim"
               for item in document["decisions"])
    assert git(scenario.root, "rev-parse", result["commit"] + "^{tree}") == git(
        scenario.root, "rev-parse", scenario.commits["trim"] + "^{tree}")
    scenario.assert_sources_unchanged()


@pytest.mark.parametrize("kind", ["acceptance", "decision", "composition"])
def test_changed_executed_log_blocks_final_apply(tmp_path, kind):
    scenario = Scenario(tmp_path)
    prepared = scenario.review_and_prepare()
    receipt, result = scenario.finish(prepared)
    assert receipt["next_action"] == "ready_for_apply"
    preview = scenario.invoke("apply", "--artifact", "final", "--target", "main", "--dry-run")
    plan_hash = next(line.split(": ", 1)[1] for line in preview.stdout.splitlines()
                     if line.startswith("plan_hash: "))
    check = {"acceptance": result["acceptance"][0],
             "decision": result["decision_results"][0]["validation"],
             "composition": result["composition_checks"][0]}[kind]
    # 실제 다른 테스트를 실행하여 기존 로그 바이트를 대체한다.
    changed = execute_check(Path(prepared["project_root"]), Path(prepared["task_dir"]), "unique", "-rerun")
    Path(check["log"]).write_bytes(Path(changed["log"]).read_bytes())
    rejected = scenario.invoke("apply", "--artifact", "final", "--target", "main", "--confirm", plan_hash, success=False)
    assert "stale" in rejected.stdout + rejected.stderr
    assert scenario.resume()["next_action"] == "stale"
    scenario.assert_sources_unchanged()


def test_v1_review_resume_never_implicitly_upgrades(tmp_path):
    scenario = Scenario(tmp_path)
    legacy = copy.deepcopy(scenario.session)
    del legacy["variants_workflow_version"]
    del legacy["outcome_mode"]
    write_json(scenario.state / "session.json", legacy)
    ready = scenario.resume()
    claim = scenario.call("review", "--claim", ready["input_hash"])
    report = scenario.state / "legacy-review.md"
    report.write_text("Legacy deterministic review; common tests passed for both candidates.\n")
    scenario.call("review", "--complete", claim["token"], "--report", str(report))
    assert scenario.resume()["next_action"] == "review_complete"
    scenario.invoke("synthesize", "--prepare", ready["input_hash"], success=False)
    assert "variants_workflow_version" not in read_json(scenario.state / "session.json")
    assert not (scenario.state / "variant-synthesis-state.json").exists()
    scenario.assert_sources_unchanged()
