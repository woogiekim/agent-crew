#!/usr/bin/env bash
# sync-instructions.sh — Assemble host AI instruction files from the mnemos
# global-layer instruction rules.
#
# Default mode is --dry-run (prints unified diffs; mutates nothing). Use
# --apply to actually rewrite host files. Idempotent: a second --apply
# run against an unchanged mnemos store produces zero file changes.
#
# Usage:
#   bash core/scripts/sync-instructions.sh             # default: --dry-run
#   bash core/scripts/sync-instructions.sh --apply     # rewrite host files
#   bash core/scripts/sync-instructions.sh --hosts claude,codex --apply
#
# Environment:
#   MNEMOS_BIN       path to mnemos CLI (default: ~/.local/bin/mnemos)
#   CODEX_HOME       Codex home (default: ~/.codex)
#   CLAUDE_HOME      Claude Code home (default: ~/.claude)
#   AGENT_CREW_HOME  agent-crew home (default: ~/.agent-crew)
#
# Exit codes:
#   0  success (or no diffs in --dry-run mode)
#   1  mnemos CLI not found
#   2  invalid args or fatal write failure
#   3  --dry-run found pending diffs (informational; not an error)

set -u

MNEMOS_BIN="${MNEMOS_BIN:-${HOME}/.local/bin/mnemos}"
CLAUDE_HOME="${CLAUDE_HOME:-${HOME}/.claude}"
CODEX_HOME="${CODEX_HOME:-${HOME}/.codex}"
AGENT_CREW_HOME="${AGENT_CREW_HOME:-${HOME}/.agent-crew}"

MODE="--dry-run"
HOSTS="claude,codex,generic,repo"

while [ $# -gt 0 ]; do
  case "$1" in
    --apply)    MODE="--apply"; shift ;;
    --dry-run)  MODE="--dry-run"; shift ;;
    --hosts)    HOSTS="$2"; shift 2 ;;
    --help|-h)  sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "sync-instructions: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ ! -x "${MNEMOS_BIN}" ]; then
  echo "ERROR: mnemos CLI not found or not executable at: ${MNEMOS_BIN}" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Resolve host file path. Bash 3.2 compatible (no associative arrays).
host_path() {
  case "$1" in
    claude)  echo "${CLAUDE_HOME}/CLAUDE.md" ;;
    codex)   echo "${CODEX_HOME}/AGENTS.md" ;;
    generic) echo "${AGENT_CREW_HOME}/AGENTS.md" ;;
    repo)    echo "${REPO_ROOT}/core/global-agents.md" ;;
    *)       echo "" ;;
  esac
}

START_MARKER="<!-- agent-crew-start -->"
END_MARKER="<!-- agent-crew-end -->"

echo "[sync-instructions] mode=${MODE} mnemos=${MNEMOS_BIN}"
echo "[sync-instructions] hosts=${HOSTS}"

# Collect rules from mnemos as JSON-list on stdout.
# Each row: {"id":..., "tags":[...], "content":..., "front":..., "applies_to":[], "priority":..., "title":..., "section":...}
# NOTE on shell wiring: we cannot use `cmd | python3 - "$ARG" <<EOF ... EOF`
# because the heredoc commandeers stdin and the pipe is lost. We instead
# capture the rule-id list into a variable first, then pass it to Python
# as a single argv string.
RULE_IDS="$(
  "${MNEMOS_BIN}" list --layer global --limit 9999 2>/dev/null \
    | grep -oE '\[global\] rule:[a-z0-9-]+:' \
    | sed -E 's/^\[global\] //; s/:$//' \
    | sort -u
)"

COLLECTED_JSON="$(
  python3 - "${MNEMOS_BIN}" "${RULE_IDS}" <<'PYEOF'
import json, re, subprocess, sys
mnemos = sys.argv[1]
ids = [line.strip().rstrip(":") for line in sys.argv[2].splitlines() if line.strip()]
out = []
for rid in ids:
    if not rid.startswith("rule:"):
        continue
    try:
        raw = subprocess.check_output([mnemos, "read", rid], stderr=subprocess.DEVNULL, text=True)
        data = json.loads(raw)
    except Exception:
        continue
    if "instruction-rule" not in (data.get("tags") or []):
        continue
    content = data.get("content", "")
    # Strip leading blank lines before YAML front matter.
    body = content.lstrip("\n")
    front = {}
    rule_body = body
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", body, re.DOTALL)
    if m:
        front_text = m.group(1)
        rule_body  = m.group(2)
        try:
            for line in front_text.splitlines():
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                if ":" in line:
                    k, _, v = line.partition(":")
                    k = k.strip()
                    v = v.strip()
                    # Inline list [a, b, c]
                    if v.startswith("[") and v.endswith("]"):
                        front[k] = [x.strip().strip("'\"") for x in v[1:-1].split(",") if x.strip()]
                    elif v.startswith("- ") or v == "":
                        pass  # block list — handle below
                    else:
                        front[k] = v.strip("'\"")
            # Block list parse (applies_to:\n  - foo\n  - bar)
            cur_key = None
            for line in front_text.splitlines():
                if re.match(r"^\S", line) and line.endswith(":"):
                    cur_key = line[:-1].strip()
                    front.setdefault(cur_key, [])
                elif cur_key and re.match(r"^\s*-\s+", line):
                    val = re.sub(r"^\s*-\s+", "", line).strip().strip("'\"")
                    if isinstance(front.get(cur_key), list):
                        front[cur_key].append(val)
        except Exception:
            front = {}
    applies = front.get("applies_to") or []
    if isinstance(applies, str):
        applies = [applies]
    try:
        priority = int(front.get("priority", 100))
    except Exception:
        priority = 100
    out.append({
        "id":       rid,
        "title":    front.get("title", rid.removeprefix("rule:")),
        "section":  front.get("section", front.get("title", rid.removeprefix("rule:"))),
        "applies_to": applies or ["all"],
        "priority": priority,
        "body":     rule_body.rstrip() + "\n",
    })
out.sort(key=lambda r: (r["priority"], r["id"]))
print(json.dumps(out, ensure_ascii=False))
PYEOF
)"


if [ -z "${COLLECTED_JSON}" ] || [ "${COLLECTED_JSON}" = "[]" ]; then
  echo "WARN: no instruction-rule items found in mnemos global layer." >&2
  echo "      Run: bash ${SCRIPT_DIR}/seed-instruction-rules.sh --apply" >&2
  exit 1
fi

RULE_COUNT="$(echo "${COLLECTED_JSON}" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')"
echo "[sync-instructions] collected ${RULE_COUNT} rules from mnemos"

# Build the assembled block per host, then write/diff per host file.
PENDING_DIFFS=0
for host in $(echo "${HOSTS}" | tr ',' ' '); do
  dest="$(host_path "${host}")"
  if [ -z "${dest}" ]; then
    echo "WARN: unknown host '${host}' (skipping)" >&2
    continue
  fi

  echo ""
  echo "--- host: ${host} -> ${dest} ---"

  if [ ! -e "$(dirname "${dest}")" ]; then
    echo "WARN: parent dir ${dest%/*} does not exist (skipping)" >&2
    continue
  fi

  python3 - "${dest}" "${host}" "${MODE}" "${START_MARKER}" "${END_MARKER}" "${COLLECTED_JSON}" <<'PYEOF'
import json, os, re, sys, tempfile, datetime, subprocess, difflib

dest, host, mode, start, end, rules_json = sys.argv[1:7]
rules = json.loads(rules_json)

# Filter to rules that apply to this host.
applicable = [r for r in rules if host in r["applies_to"] or "all" in r["applies_to"] or host == "repo"]

# Build the managed block. Use timezone-aware datetime per Python 3.12+ guidance.
ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
# Marker comment text is a list of plain Python strings — no backticks in
# the literal text (the docstring word "mnemos capture" reads clearly
# enough without the inline-code formatting and avoids shell/Python escape
# headaches inside this nested heredoc).
lines = [
    start,
    "<!-- MANAGED BLOCK - DO NOT EDIT HERE.",
    "     Edit rules via: mnemos capture --layer global --id <id> --content '...'",
    "     Then run: crew:sync-instructions --apply",
    "     Manual edits inside this block will be overwritten on next sync. -->",
    f"<!-- Assembled: {ts} from {len(applicable)} mnemos rules (host={host}) -->",
    "",
    "# agent-crew - Global Rules",
    "",
]
for r in applicable:
    # Promote rule.title to H2 unless the rule body already starts with a top-level heading.
    # An H3 (`### ...`) inside the body is treated as a subsection of the rule, so we still
    # emit the H2 title above it.
    body = r["body"].strip()
    first_line = body.splitlines()[0] if body else ""
    has_own_top_heading = bool(re.match(r"^#{1,2} ", first_line))
    if not has_own_top_heading:
        lines.append(f"## {r['title']}")
        lines.append("")
    lines.append(body)
    lines.append("")
lines.append(end)
new_block = "\n".join(lines).rstrip() + "\n"

# Read existing file (or empty).
existing = ""
if os.path.exists(dest):
    with open(dest, "r", encoding="utf-8") as f:
        existing = f.read()

# Per-host write strategy:
#   - host == "repo": the repo's core/global-agents.md IS the rendered output.
#     Replace the whole file with the managed block (no host-specific tail).
#   - other hosts: preserve any content outside the marker block (e.g. Codex's
#     Korean conversational rules). If markers absent, wrap by prepending the
#     managed block above the existing file, keeping all existing content
#     verbatim under a "host-specific" delimiter.
pat = re.escape(start) + r".*?" + re.escape(end)
if host == "repo":
    proposed = new_block
elif re.search(pat, existing, re.DOTALL):
    proposed = re.sub(pat, new_block.rstrip("\n"), existing, count=1, flags=re.DOTALL)
elif existing.strip():
    proposed = (
        new_block.rstrip("\n")
        + "\n\n<!-- host-specific content below - preserved verbatim -->\n"
        + existing.lstrip("\n")
    )
else:
    proposed = new_block

# Strip the Assembled: timestamp from BOTH sides before comparing,
# so timestamp-only deltas don't trigger writes (idempotency).
strip_ts = lambda s: re.sub(r"<!-- Assembled: [^>]*-->\n?", "", s)
existing_norm = strip_ts(existing)
proposed_norm = strip_ts(proposed)

if existing_norm == proposed_norm:
    print(f"  = no-op (already in sync)")
    sys.exit(0)

# Diffs detected.
if mode == "--dry-run":
    diff = list(difflib.unified_diff(
        existing.splitlines(keepends=True),
        proposed.splitlines(keepends=True),
        fromfile=f"{dest} (current)",
        tofile=f"{dest} (proposed)",
        n=2,
    ))
    sys.stdout.writelines(diff[:200])
    if len(diff) > 200:
        print(f"... [{len(diff)-200} more diff lines truncated]")
    print(f"  ~ pending: {len(diff)} diff lines")
    sys.exit(3)
else:
    # Atomic write: tempfile in same dir + os.rename.
    fd, tmp = tempfile.mkstemp(prefix=".sync-instructions.", suffix=".tmp",
                                dir=os.path.dirname(dest) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(proposed)
        os.rename(tmp, dest)
    except Exception:
        try: os.unlink(tmp)
        except Exception: pass
        raise
    print(f"  + wrote {dest} ({len(proposed)} bytes)")
PYEOF
  rc=$?
  if [ "${rc}" = "3" ]; then
    PENDING_DIFFS=$((PENDING_DIFFS + 1))
  elif [ "${rc}" != "0" ]; then
    echo "FATAL: sync of ${dest} failed (rc=${rc})" >&2
    exit 2
  fi
done

echo ""
if [ "${MODE}" = "--dry-run" ]; then
  if [ "${PENDING_DIFFS}" -gt 0 ]; then
    echo "[sync-instructions] ${PENDING_DIFFS} host(s) have pending diffs."
    echo "                    Re-run with --apply to write."
    exit 3
  fi
  echo "[sync-instructions] all hosts in sync (no diffs)."
fi
exit 0
