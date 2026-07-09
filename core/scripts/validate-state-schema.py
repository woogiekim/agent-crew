#!/usr/bin/env python3
"""
validate-state-schema.py — Provider-neutral JSON state file schema validator.

Purpose:
  Walk ${STATE_DIR} and ${TASK_DIR} and validate each known state file
  against its corresponding schema under ${AGENT_CREW_HOME}/schemas/.
  Invoked by the supervisor at Phase 0 (after path resolution, before
  capability bootstrap) and runnable standalone for diagnostics.

Inputs:
  --state-dir DIR     Override STATE_DIR resolution (default: env-derived).
  --task-dir DIR      Validate task-level files in this dir too.
                      When omitted, only project-level files are checked.
  --strict            Treat warnings as errors.
  --format json|text  Output format (default: text).

Outputs:
  text:  one line per finding, plus a one-line summary, on stdout.
  json:  a single JSON object {state_dir, task_dir, findings, summary}.

Exit codes:
  0 — all valid (no findings of either class)
  1 — warnings only (no errors)
  2 — at least one error
  3 — invalid args / unreadable schema dir / etc.

Validator scope (subset of JSON Schema draft 2020-12):
  type, required, properties, additionalProperties (bool only),
  enum, const, pattern (re.search), items, oneOf, patternProperties,
  minimum, minLength, minItems.

  Out of scope (any other keyword is silently ignored):
    if/then/else, allOf, anyOf, not, $ref, format,
    maximum/maxLength/maxItems, dependencies, etc.

Severity classes (mixed-mode validator):
  Hard errors (exit 2):
    - Schema parse failure (always abort with exit 3).
    - {TASK_DIR}/register.json malformed.
    - {TASK_DIR}/pipeline.json malformed.
    - {TASK_DIR}/progress.buffer.jsonl row violates required-fields.

  Soft warnings (exit 1):
    - {STATE_DIR}/session.json malformed (cross-task; partial corruption
      must not abort an entire run).
    - {STATE_DIR}/capabilities.json malformed (absence contract trumps
      schema; never block on this file).
    - Missing optional files (register.json on pre-F4 task dirs,
      pipeline.json on tasks still in Phase 1, etc.).
    - schema_version > 1 (forward-compat).
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


# --------------------------------------------------------------------------- #
# File -> schema mapping + severity class                                     #
# --------------------------------------------------------------------------- #

# (relative-from-base-dir, schema-filename, severity-on-violation, is-jsonl)
PROJECT_FILES = [
    ("session.json",      "session.schema.json",      "warn",  False),
    ("capabilities.json", "capabilities.schema.json", "warn",  False),
]

TASK_FILES = [
    ("register.json",          "register.schema.json",         "error", False),
    ("pipeline.json",          "pipeline.schema.json",         "error", False),
    ("progress.buffer.jsonl",  "progress-buffer.schema.json",  "error", True),
]

# Optional task files are validated when present, but absence is not a finding.
OPTIONAL_TASK_FILES = [
    ("context/quality-metrics.json", "quality-metrics.schema.json", "error", False),
    ("context/evolution-report.json", "evolution-report.schema.json", "error", False),
]


# --------------------------------------------------------------------------- #
# Findings buffer                                                             #
# --------------------------------------------------------------------------- #

class Findings:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def add(self, severity, file_path, json_path, message):
        entry = {
            "severity": severity,
            "file":     str(file_path),
            "path":     json_path,
            "message":  message,
        }
        (self.errors if severity == "error" else self.warnings).append(entry)

    def has_errors(self):
        return bool(self.errors)

    def has_warnings(self):
        return bool(self.warnings)

    def all(self):
        return self.errors + self.warnings


# --------------------------------------------------------------------------- #
# Tiny JSON Schema validator (subset)                                         #
# --------------------------------------------------------------------------- #

TYPE_MAP = {
    "string":  str,
    "integer": int,
    "number":  (int, float),
    "boolean": bool,
    "object":  dict,
    "array":   list,
    "null":    type(None),
}


def validate(instance, schema, findings, file_path, json_path="$"):
    """Recursive validator. Appends findings; returns nothing."""
    if not isinstance(schema, dict):
        return

    # type
    expected = schema.get("type")
    if expected is not None:
        py_type = TYPE_MAP.get(expected)
        if py_type is None:
            return  # unknown type — silently ignore
        if expected == "integer" and isinstance(instance, bool):
            findings.add("error", file_path, json_path,
                         "expected integer, got boolean")
            return
        if not isinstance(instance, py_type):
            findings.add("error", file_path, json_path,
                         f"expected {expected}, got {type(instance).__name__}")
            return

    # const
    if "const" in schema:
        if instance != schema["const"]:
            findings.add("warn", file_path, json_path,
                         f"const expected {schema['const']!r}, got {instance!r}")

    # enum
    if "enum" in schema:
        if instance not in schema["enum"]:
            findings.add("error", file_path, json_path,
                         f"value {instance!r} not in enum {schema['enum']}")

    # pattern (strings only)
    if "pattern" in schema and isinstance(instance, str):
        if not re.search(schema["pattern"], instance):
            findings.add("error", file_path, json_path,
                         f"value {instance!r} does not match pattern "
                         f"{schema['pattern']!r}")

    # minLength / minItems / minimum
    if "minLength" in schema and isinstance(instance, str):
        if len(instance) < schema["minLength"]:
            findings.add("error", file_path, json_path,
                         f"string length {len(instance)} < minLength "
                         f"{schema['minLength']}")
    if "minItems" in schema and isinstance(instance, list):
        if len(instance) < schema["minItems"]:
            findings.add("error", file_path, json_path,
                         f"array length {len(instance)} < minItems "
                         f"{schema['minItems']}")
    if "minimum" in schema and isinstance(instance, (int, float)):
        if not isinstance(instance, bool) and instance < schema["minimum"]:
            findings.add("error", file_path, json_path,
                         f"value {instance} < minimum {schema['minimum']}")

    # oneOf (used by pipeline.stages items)
    if "oneOf" in schema:
        matches = 0
        for sub in schema["oneOf"]:
            tmp = Findings()
            validate(instance, sub, tmp, file_path, json_path)
            if not tmp.has_errors():
                matches += 1
        if matches != 1:
            findings.add("error", file_path, json_path,
                         f"oneOf matched {matches} alternatives (expected 1)")

    # object: required + properties + additionalProperties + patternProperties
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                findings.add("error", file_path, json_path,
                             f"required field {key!r} missing")
        properties    = schema.get("properties", {})
        pattern_props = schema.get("patternProperties", {})
        additional_ok = schema.get("additionalProperties", True)
        for key, value in instance.items():
            sub_path = f"{json_path}.{key}"
            handled  = False
            if key in properties:
                validate(value, properties[key], findings, file_path, sub_path)
                handled = True
            for pat, sub_schema in pattern_props.items():
                if re.search(pat, key):
                    validate(value, sub_schema, findings, file_path, sub_path)
                    handled = True
            if not handled and additional_ok is False:
                findings.add("error", file_path, json_path,
                             f"unexpected field {key!r} "
                             f"(additionalProperties: false)")

    # array: items
    if isinstance(instance, list) and "items" in schema:
        item_schema = schema["items"]
        for i, item in enumerate(instance):
            validate(item, item_schema, findings,
                     file_path, f"{json_path}[{i}]")


# --------------------------------------------------------------------------- #
# Loaders                                                                     #
# --------------------------------------------------------------------------- #

def load_schema(schemas_dir, name):
    path = schemas_dir / name
    if not path.is_file():
        raise FileNotFoundError(f"schema not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "not_found"
    except json.JSONDecodeError as exc:
        return None, f"malformed_json: {exc}"
    except Exception as exc:
        return None, f"read_error: {exc}"


def resolve_state_dir(override):
    if override:
        return Path(override)
    env = os.environ.get("AGENT_CREW_STATE_DIR")
    if env:
        return Path(env)
    home = os.environ.get("AGENT_CREW_HOME", str(Path.home() / ".agent-crew"))
    project = os.environ.get("AGENT_CREW_PROJECT", "default")
    return Path(home) / "state" / project


def resolve_schemas_dir():
    home = Path(os.environ.get("AGENT_CREW_HOME",
                               str(Path.home() / ".agent-crew")))
    # Prefer the compat-alias path the supervisor uses; fall back to system/.
    for candidate in (home / "schemas", home / "system" / "schemas"):
        if candidate.is_dir():
            return candidate
    # Last resort: source-tree path (useful for in-repo invocation).
    repo_schemas = Path(__file__).resolve().parent.parent / "schemas"
    if repo_schemas.is_dir():
        return repo_schemas
    raise FileNotFoundError(
        f"schemas directory not found: {home/'schemas'} "
        f"or {home/'system'/'schemas'}"
    )


# --------------------------------------------------------------------------- #
# File-level validators                                                       #
# --------------------------------------------------------------------------- #

def validate_file(path, schema, severity, findings):
    """Validate a single JSON file. Severity is the violation class."""
    instance, err = load_json(path)
    if err == "not_found":
        findings.add("warn", path, "$", "file not found (skipping)")
        return
    if err is not None:
        findings.add(severity, path, "$", err)
        return
    # Forward-compat: schema_version > 1 = warn only
    sv = instance.get("schema_version") if isinstance(instance, dict) else None
    if isinstance(sv, int) and sv > 1:
        findings.add("warn", path, "$.schema_version",
                     f"schema_version={sv} > 1; forward-compat, validating "
                     f"with v1 schema")
    sub_findings = Findings()
    validate(instance, schema, sub_findings, path)
    # Downgrade errors to warns for soft-class files.
    for entry in sub_findings.errors:
        entry["severity"] = severity
        if severity == "error":
            findings.errors.append(entry)
        else:
            findings.warnings.append(entry)
    for entry in sub_findings.warnings:
        findings.warnings.append(entry)

    if path.name == "pipeline.json" and isinstance(instance, dict):
        validate_pipeline_artifact_policy(path, instance, findings)


def stage_agents(stage):
    """Return executable agents from the pipeline stage shapes."""
    if isinstance(stage, str):
        return [stage]
    if isinstance(stage, list):
        return [item for item in stage if isinstance(item, str)]
    if isinstance(stage, dict):
        agents = stage.get("agents")
        if isinstance(agents, list):
            return [item for item in agents if isinstance(item, str)]
        if isinstance(agents, str):
            return [agents]
    return []


def validate_pipeline_artifact_policy(path, pipeline, findings):
    """Warn when completed artifacts drift from current runtime policy."""
    stages = pipeline.get("stages")
    if not isinstance(stages, list):
        return

    completed = int(pipeline.get("completed_stages") or 0)
    if completed <= 0:
        return

    for index, stage in enumerate(stages):
        if "planner" in stage_agents(stage):
            findings.add(
                "warn",
                path,
                f"$.stages[{index}]",
                "completed pipeline artifact contains planner as a runtime stage; "
                "current capability policy treats planner as a non-runtime planning role",
            )


def validate_jsonl_file(path, schema, severity, findings):
    """Validate progress.buffer.jsonl — one JSON object per line."""
    if not path.is_file():
        findings.add("warn", path, "$", "file not found (skipping)")
        return
    skipped = 0
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, 1):
            line = line.rstrip("\n")
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            sub_findings = Findings()
            validate(row, schema, sub_findings,
                     path, json_path=f"$.line[{lineno}]")
            for entry in sub_findings.errors:
                entry["severity"] = severity
                if severity == "error":
                    findings.errors.append(entry)
                else:
                    findings.warnings.append(entry)
            for entry in sub_findings.warnings:
                findings.warnings.append(entry)
    if skipped:
        findings.add("warn", path, "$",
                     f"{skipped} malformed JSONL line(s) skipped")


def validate_optional_file(path, schema, severity, findings):
    """Validate an optional JSON task artifact only when it exists."""
    if not path.is_file():
        return
    validate_file(path, schema, severity, findings)


# --------------------------------------------------------------------------- #
# Driver                                                                      #
# --------------------------------------------------------------------------- #

def main():
    p = argparse.ArgumentParser(description="agent-crew state schema validator")
    p.add_argument("--state-dir")
    p.add_argument("--task-dir")
    p.add_argument("--strict", action="store_true",
                   help="treat warnings as errors")
    p.add_argument("--format", choices=["text", "json"], default="text")
    args = p.parse_args()

    try:
        schemas_dir = resolve_schemas_dir()
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    state_dir = resolve_state_dir(args.state_dir)
    task_dir  = Path(args.task_dir) if args.task_dir else None

    findings = Findings()

    # Project-level files
    for fname, schema_name, severity, is_jsonl in PROJECT_FILES:
        try:
            schema = load_schema(schemas_dir, schema_name)
        except FileNotFoundError as exc:
            findings.add("error", schemas_dir / schema_name, "$", str(exc))
            continue
        path = state_dir / fname
        (validate_jsonl_file if is_jsonl else validate_file)(
            path, schema, severity, findings)

    # Task-level files
    if task_dir is not None:
        for fname, schema_name, severity, is_jsonl in TASK_FILES:
            try:
                schema = load_schema(schemas_dir, schema_name)
            except FileNotFoundError as exc:
                findings.add("error", schemas_dir / schema_name, "$", str(exc))
                continue
            path = task_dir / fname
            (validate_jsonl_file if is_jsonl else validate_file)(
                path, schema, severity, findings)
        for fname, schema_name, severity, is_jsonl in OPTIONAL_TASK_FILES:
            try:
                schema = load_schema(schemas_dir, schema_name)
            except FileNotFoundError as exc:
                findings.add("error", schemas_dir / schema_name, "$", str(exc))
                continue
            path = task_dir / fname
            (validate_jsonl_file if is_jsonl else validate_optional_file)(
                path, schema, severity, findings)

    # Report
    if args.format == "json":
        payload = {
            "state_dir":    str(state_dir),
            "task_dir":     str(task_dir) if task_dir else None,
            "findings":     findings.all(),
            "summary": {
                "errors":   len(findings.errors),
                "warnings": len(findings.warnings),
            },
        }
        json.dump(payload, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        for entry in findings.all():
            print(f"[{entry['severity']:>5}] {entry['file']} :: "
                  f"{entry['path']} — {entry['message']}")
        print(f"-- validate-state-schema: "
              f"{len(findings.errors)} error(s), "
              f"{len(findings.warnings)} warning(s)")

    if args.strict and findings.has_warnings():
        return 2
    if findings.has_errors():
        return 2
    if findings.has_warnings():
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
