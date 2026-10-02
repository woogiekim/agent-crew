"""Keep the review evidence style rule and its review-synthesis reference in sync."""

from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
RULE_PATH = REPO_ROOT / "core" / "rules" / "review-evidence-style.md"
COMMAND_PATH = REPO_ROOT / "core" / "user" / "commands" / "review-synthesis.md"
RULE_REFERENCE_RE = re.compile(r"`(core/rules/[A-Za-z0-9._-]+\.md)`")


def _frontmatter(text: str) -> dict[str, str]:
    matched = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert matched, "rule must start with a YAML frontmatter block"
    fields: dict[str, str] = {}
    for line in matched.group(1).splitlines():
        key, separator, value = line.partition(":")
        if separator and not line.startswith((" ", "\t")):
            fields[key.strip()] = value.strip()
    return fields


def test_rule_declares_name_and_applies_to():
    fields = _frontmatter(RULE_PATH.read_text(encoding="utf-8"))

    assert fields["name"] == "review-evidence-style"
    assert "review-synthesis" in fields["applies-to"]


def test_rule_references_only_shipped_rules():
    references = RULE_REFERENCE_RE.findall(RULE_PATH.read_text(encoding="utf-8"))

    assert references, "rule is expected to extend existing rules by reference"
    missing = [ref for ref in sorted(set(references)) if not (REPO_ROOT / ref).is_file()]
    assert not missing, "Rule references missing rule files:\n" + "\n".join(missing)


def test_review_synthesis_command_references_the_rule():
    command = COMMAND_PATH.read_text(encoding="utf-8")

    assert "core/rules/review-evidence-style.md" in command
    assert "## Review Evidence Style" in command


def test_rule_keeps_posting_behind_explicit_approval():
    rule = RULE_PATH.read_text(encoding="utf-8")

    assert "명시 승인" in rule
    assert "glab mr note create" in rule
