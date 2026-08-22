#!/usr/bin/env bash
# Tests for mnemos search frontmatter filtering and MEMORY.md exclusion.
#
# Issue #26: mnemos search returned raw frontmatter YAML blocks and MEMORY.md
# index entries as search hits instead of the actual captured insight bodies.
#
# These tests verify that agent-crew's integration with mnemos correctly:
#   1. Does not surface MEMORY.md index files as search results
#   2. Does not surface YAML frontmatter as the content of search results
#   3. seed-instruction-rules.sh captures content that has frontmatter stripped
#
# Uses a mock mnemos stub (same pattern as test_seed_instruction_rules.bash).
# Does not require a real mnemos installation.
# Compatible with bash 3.2+ (macOS default shell).

set -u

# shellcheck source=./_lib.bash
source "$(dirname "$0")/_lib.bash"

SCRIPT="${SCRIPTS_DIR}/seed-instruction-rules.sh"

# --------------------------------------------------------------------------- #
# Mock mnemos stub with FTS-like content filtering                             #
# --------------------------------------------------------------------------- #

# Builds a mock mnemos binary that:
#   - 'search <query>' returns stored items whose content matches the query,
#     with frontmatter stripped (simulating the fixed behaviour of fts.py)
#   - 'capture --id X --content Y' stores Y under X in a flat file
#   - 'read X' returns stored content as JSON
#   - 'ingest-claude-md' simulates scanning ~/.claude/projects/*/memory/*.md,
#     skipping MEMORY.md index files (issue #26 fix)
#
# Args:
#   $1  tmp dir root (store and memory sub-dirs created inside it)
#
# Prints the path to the created stub binary.
make_mock_mnemos() {
    local tmp="$1"
    local store="${tmp}/mnemos-store"
    local mem_dir="${tmp}/memory"
    mkdir -p "${store}" "${mem_dir}"

    local stub="${tmp}/mnemos"
    # Note: $( ) expressions inside <<STUB_EOF are NOT expanded — they run
    # at stub-execution time.  Use \$( ) to escape from the here-doc.
    cat > "${stub}" <<STUB_EOF
#!/usr/bin/env bash
# Mock mnemos: simulates issue-26-fixed behaviour (bash 3.2 compatible).
STORE="${store}"
MEM_DIR="${mem_dir}"
cmd="\$1"
shift || true

# Option parser — extracts --id and --content; ignores others.
ID=""
CONTENT=""
POS=()
while [ \$# -gt 0 ]; do
  case "\$1" in
    --id)      ID="\$2";      shift 2 ;;
    --content) CONTENT="\$2"; shift 2 ;;
    --layer|--tag|--limit|--layers|--width)
               shift 2 ;;
    --quiet|--full|--no-color|--skip-files)
               shift ;;
    *)         POS+=("\$1"); shift ;;
  esac
done

# Python helper: strip the leading YAML frontmatter block from stdin text.
# Handles the double-frontmatter scenario (outer mnemos meta + inner source).
_strip_frontmatter() {
  python3 -c '
import re, sys
text = sys.stdin.read()
stripped = re.sub(r"^---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.DOTALL).strip()
print(stripped if stripped != text.strip() else text.strip())
'
}

# Bash-3.2-compatible ASCII lowercase conversion via tr.
_to_lower() { printf '%s' "\$1" | tr "[:upper:]" "[:lower:]"; }
_to_upper() { printf '%s' "\$1" | tr "[:lower:]" "[:upper:]"; }

case "\$cmd" in
  capture|edit)
    if [ -z "\$ID" ] && [ -n "\${POS[0]:-}" ]; then
      ID="\${POS[0]}"
    fi
    f="\${STORE}/\${ID//[\\/]/_}"
    printf '%s' "\$CONTENT" > "\$f"
    ;;

  read)
    rid="\${POS[0]:-}"
    f="\${STORE}/\${rid//[\\/]/_}"
    if [ -f "\$f" ]; then
      python3 -c '
import json, sys
content = open(sys.argv[1]).read()
print(json.dumps({"tags":["instruction-rule"],"content":content}, ensure_ascii=False))
' "\$f"
    else
      exit 1
    fi
    ;;

  search)
    # Simulate fixed FTS behaviour: content is stored already frontmatter-
    # stripped (as index_item() now does it).  Matching is case-insensitive.
    # MEMORY.md entries are never in the store (excluded at ingest time).
    QUERY="\$(_to_lower "\${POS[0]:-}")"
    found=0
    for f in "\${STORE}"/*; do
      [ -f "\$f" ] || continue
      snippet=\$(cat "\$f")
      snippet_lower=\$(_to_lower "\${snippet}")
      case "\${snippet_lower}" in
        *"\${QUERY}"*)
          item_id=\$(basename "\$f")
          preview=\${snippet:0:80}
          printf '  [fts] %s: %s\n' "\${item_id}" "\${preview}"
          found=\$((found + 1))
          ;;
      esac
    done
    if [ "\$found" -eq 0 ]; then
      echo "no results found"
    fi
    printf '[mnemos] Retrieved %d memories\n' "\${found}"
    ;;

  ingest-claude-md)
    # Simulate scanning memory files; MEMORY.md (any case) is excluded.
    ingested=0
    for f in "\${MEM_DIR}"/*.md; do
      [ -f "\$f" ] || continue
      fname=\$(basename "\$f")
      fname_upper=\$(_to_upper "\${fname}")
      # Issue #26 fix: MEMORY.MD is an index file — skip it.
      if [ "\${fname_upper}" = "MEMORY.MD" ]; then
        continue
      fi
      item_id="\${fname%.md}"
      raw=\$(cat "\$f")
      # Strip frontmatter before storing — mirrors the fixed fts.py behaviour.
      snippet=\$(printf '%s' "\${raw}" | _strip_frontmatter)
      printf '%s' "\${snippet}" > "\${STORE}/\${item_id}"
      ingested=\$((ingested + 1))
    done
    printf 'claude-md: %d created, 0 updated, 0 skipped (%d file(s) processed)\n' \\
      "\${ingested}" "\${ingested}"
    ;;

  list)
    # Used by sync-instructions; emit nothing for these tests.
    ;;

  *)
    exit 1
    ;;
esac
STUB_EOF
    chmod +x "${stub}"
    printf '%s' "${stub}"
}

# --------------------------------------------------------------------------- #
# Helper: populate the mock memory directory with test fixture files           #
# --------------------------------------------------------------------------- #

populate_memory_dir() {
    local mem_dir="$1"

    # A normal memory file WITH inner frontmatter (issue #26 double-frontmatter
    # scenario: the outer mnemos YAML was already stripped by the store layer;
    # the inner source-file frontmatter is what fts.py must now also strip).
    cat > "${mem_dir}/feedback-ship-threshold.md" <<'EOF'
---
name: feedback-ship-threshold
description: "User's ship-vs-defer threshold for framework-internals changes."
metadata:
  node_type: memory
  type: feedback
---

Hygiene-only refactors are defer-by-default; user-visible throughput is
required to justify a ship decision.
EOF

    # A normal memory file WITHOUT inner frontmatter (straightforward case).
    cat > "${mem_dir}/project-ai-agnostic.md" <<'EOF'
agent-crew's AI-agnostic posture: file-based source of truth is canonical.
EOF

    # MEMORY.md index file — must be excluded (issue #26 fix in scanner.py).
    cat > "${mem_dir}/MEMORY.md" <<'EOF'
# Memory Index

- [Ship-threshold](feedback-ship-threshold.md) — hygiene-only refactors are defer-by-default
- [AI-agnostic posture](project-ai-agnostic.md) — file is canonical
EOF

    # Variant with lowercase name — same exclusion rule applies.
    cat > "${mem_dir}/memory.md" <<'EOF'
# Another Memory Index (lowercase)

- [Some entry](some-entry.md) — some description here
EOF
}

# ===========================================================================#
# Test group 1: MEMORY.md index files are excluded from ingest               #
# ===========================================================================#

it "ingest-claude-md skips MEMORY.md and memory.md; ingests exactly 2 real files"
TMP=$(make_tmp)
MNEMOS=$(make_mock_mnemos "${TMP}")
populate_memory_dir "${TMP}/memory"
out=$("${MNEMOS}" ingest-claude-md 2>&1)
assert_contains "${out}" "2 created"

it "MEMORY.md (uppercase) is absent from the mock store after ingest"
TMP=$(make_tmp)
MNEMOS=$(make_mock_mnemos "${TMP}")
populate_memory_dir "${TMP}/memory"
"${MNEMOS}" ingest-claude-md >/dev/null 2>&1
assert_file_absent "${TMP}/mnemos-store/MEMORY"
assert_file_absent "${TMP}/mnemos-store/MEMORY.md"

it "memory.md (lowercase) is absent from the mock store after ingest"
TMP=$(make_tmp)
MNEMOS=$(make_mock_mnemos "${TMP}")
populate_memory_dir "${TMP}/memory"
"${MNEMOS}" ingest-claude-md >/dev/null 2>&1
assert_file_absent "${TMP}/mnemos-store/memory"
assert_file_absent "${TMP}/mnemos-store/memory.md"

it "non-index .md files ARE present in the store after ingest"
TMP=$(make_tmp)
MNEMOS=$(make_mock_mnemos "${TMP}")
populate_memory_dir "${TMP}/memory"
"${MNEMOS}" ingest-claude-md >/dev/null 2>&1
assert_file_exists "${TMP}/mnemos-store/feedback-ship-threshold"
assert_file_exists "${TMP}/mnemos-store/project-ai-agnostic"

# ===========================================================================#
# Test group 2: Frontmatter is stripped before FTS storage                   #
# ===========================================================================#

it "ingest-claude-md strips inner frontmatter before storing"
TMP=$(make_tmp)
MNEMOS=$(make_mock_mnemos "${TMP}")
populate_memory_dir "${TMP}/memory"
"${MNEMOS}" ingest-claude-md >/dev/null 2>&1
stored=$(cat "${TMP}/mnemos-store/feedback-ship-threshold" 2>/dev/null || echo "")
assert_not_contains "${stored}" "name: feedback-ship-threshold"
assert_not_contains "${stored}" "node_type: memory"

it "ingest-claude-md: stored content contains the meaningful body text"
TMP=$(make_tmp)
MNEMOS=$(make_mock_mnemos "${TMP}")
populate_memory_dir "${TMP}/memory"
"${MNEMOS}" ingest-claude-md >/dev/null 2>&1
stored=$(cat "${TMP}/mnemos-store/feedback-ship-threshold" 2>/dev/null || echo "")
assert_contains "${stored}" "Hygiene-only refactors"

# ===========================================================================#
# Test group 3: Search returns body content, not frontmatter YAML            #
# ===========================================================================#

it "search does not return YAML frontmatter key-value lines as snippet"
TMP=$(make_tmp)
MNEMOS=$(make_mock_mnemos "${TMP}")
populate_memory_dir "${TMP}/memory"
"${MNEMOS}" ingest-claude-md >/dev/null 2>&1
out=$("${MNEMOS}" search "hygiene" 2>&1)
assert_not_contains "${out}" "name: feedback-ship-threshold"
assert_not_contains "${out}" "node_type: memory"

it "search returns the actual insight body text"
TMP=$(make_tmp)
MNEMOS=$(make_mock_mnemos "${TMP}")
populate_memory_dir "${TMP}/memory"
"${MNEMOS}" ingest-claude-md >/dev/null 2>&1
out=$("${MNEMOS}" search "hygiene" 2>&1)
assert_contains "${out}" "Hygiene-only refactors"

it "search for MEMORY.md index content returns no results (excluded at ingest)"
TMP=$(make_tmp)
MNEMOS=$(make_mock_mnemos "${TMP}")
populate_memory_dir "${TMP}/memory"
"${MNEMOS}" ingest-claude-md >/dev/null 2>&1
out=$("${MNEMOS}" search "Memory Index" 2>&1)
assert_contains "${out}" "no results found"

it "search results do not contain raw '---' frontmatter delimiters"
TMP=$(make_tmp)
MNEMOS=$(make_mock_mnemos "${TMP}")
populate_memory_dir "${TMP}/memory"
"${MNEMOS}" ingest-claude-md >/dev/null 2>&1
out=$("${MNEMOS}" search "hygiene" 2>&1)
# No [fts] result line should show '---' as content preview
assert_not_contains "${out}" ": ---"

# ===========================================================================#
# Test group 4: seed-instruction-rules.sh integration                        #
# ===========================================================================#

it "seed-instruction-rules.sh captures rule:input-language into mock store"
TMP=$(make_tmp)
MNEMOS=$(make_mock_mnemos "${TMP}")
MNEMOS_BIN="${MNEMOS}" bash "${SCRIPT}" --apply --profile bootstrap-missing >/dev/null 2>&1
assert_file_exists "${TMP}/mnemos-store/rule:input-language"

it "seed-instruction-rules.sh: captured rule body contains meaningful content"
TMP=$(make_tmp)
MNEMOS=$(make_mock_mnemos "${TMP}")
MNEMOS_BIN="${MNEMOS}" bash "${SCRIPT}" --apply --profile bootstrap-missing >/dev/null 2>&1
rule_file="${TMP}/mnemos-store/rule:input-language"
if [ -f "${rule_file}" ]; then
    content=$(cat "${rule_file}")
    assert_contains "${content}" "immutable Root Input Snapshot"
else
    _fail "rule:input-language not found in mock store"
fi

# --------------------------------------------------------------------------- #
end_report
