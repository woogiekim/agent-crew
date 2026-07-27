# Rule: Output Language

## Principle

**User-facing output should appear in the AI's natural response language
for the conversation** (which, in practice, means the language the user
used in their input). Input task text is preserved verbatim in internal
artifacts; it is not translated to English before planning or handoff.

A Korean-speaking user submitting `crew:run "주문 API 구현해"` should:

- See progress emits, approval prompts, summary tables, and result
  narratives in Korean (matches their input).
- Have the original Korean task text preserved in `pipeline.json.task`,
  `register.json.task`, `handoff.md`, and agent-to-agent prompts.

## What This Rule Covers

**In scope (output language follows user's language):**

- Stage agent narrative output (devops PLAN explanation, reviewer
  report notes, custom agent prose)
- `crew:status` snapshot labels and field values
- `crew:run` progress messages (the human-readable side)
- Approval prompt question text (when the host's
  `interactive_question` capability renders it; option labels stay
  in English — see invariant below)
- Hook stderr messages routed to the user (where the message is
  freeform prose)
- `result.md` narrative content (the DESCRIPTION, CHANGES per-file
  notes; not the STATUS / BRANCH / COMMITS field names)

**Out of scope (always English):**

- All status keywords and parser-owned schema keys inside structured state
  files: `pipeline.json`, `register.json`, `session.json`,
  `capabilities.json`, `progress.buffer.jsonl`
- All status keywords and structured-block headers (see invariant)

## English-Only Status Invariant

The supervisor's stage-result parser is regex-based and matches
English keywords. Stage agents MUST return the following tokens
verbatim in English, regardless of input language:

| Token | Where |
|---|---|
| `STATUS: completed` | every stage agent terminal line |
| `STATUS: blocked` | every BLOCKED outcome |
| `STATUS: plan_ready` | devops + any stage that submits a PLAN block |
| `REVIEW: APPROVED` / `REVIEW: NEEDS_CHANGES` | reviewer agent |
| `PLAN:` | PLAN block header in devops and devops-style stages |
| `BLOCKER:` | first line of blocker detail in result.md |
| `BRANCH:` / `COMMITS:` / `STATUS:` field labels | result.md field labels |

If an agent returns localized status keywords (e.g., `상태: 완료`),
the supervisor classifies the response as a crash and applies the
Stage Retry Rule (up to 5 attempts). The narrative AROUND these
tokens may be in the user's language; the tokens themselves are an
invariant.

## Where Applied

This rule is enforced at three layers:

| Layer | Output |
|---|---|
| `crew:run` orchestrator | Progress emits, approval prompts narrative, final summary |
| Supervisor + stage agents | result.md narrative, review.md narrative, action-plan.md narrative |
| Hooks | stderr messages fed back to the model (Claude PostToolUse exit-2) |

Detector scripts (`core/scripts/detect-inject-intent.sh`,
`core/scripts/check-plaintext-approval.py`) inspect the user's
INPUT and AGENT RESPONSES in either language — that is independent
of output-language enforcement.

## Adapter Notes

- **claude** — Claude naturally responds in the user's input language
  (no extra configuration). The English-only status keywords still
  flow correctly because they're literal strings inside structured
  output blocks; the surrounding narrative localizes naturally.
- **codex** — `adapters/codex/skill/agent-crew/SKILL.md` should
  reference this rule. Codex's response language depends on
  configuration; document that the same input/output split applies.
- **generic** — `adapters/generic/invocation.md` documents both rules
  as best-effort.

## Specialist Agent Exception

A specialist agent's **prompt definition** may include localized
content if the agent's audience is language-specific (e.g.,
`core/agents/mentor.md` includes Korean trigger phrases and pedagogical
guidance because it mentors and teaches Korean-speaking learners).
The OUTPUT-language rule above still applies to that specialist's
runtime behavior — it produces output in the user's language, with
internal handoff content in English.

## Examples

| Scenario | Internal artifact | User-facing output |
|---|---|---|
| Korean user: `crew:run "주문 API 구현"` | `pipeline.json.task = "주문 API 구현"` | `crew:status` shows `Task: 주문 API 구현` |
| Korean user devops PLAN review | `STATUS: plan_ready` keyword (English) | "다음 작업을 실행할 예정입니다: ..." (Korean narrative) |
| English user devops PLAN review | `STATUS: plan_ready` keyword (English) | "The following actions will be performed: ..." (English narrative) |
| Reviewer terminal status | `REVIEW: APPROVED` (English) | "구현이 PRD 요건을 모두 충족합니다" (Korean narrative around the keyword) |

## Cross-References

- `core/global-agents.md` — Raw Input Preservation section + this rule's pointer
- `core/agents/supervisor.md` — invariant on status keywords (the regex parser)
- `core/agents/devops.md` — PLAN block format (English keywords, localized narrative)
- `core/agents/reviewer.md` — REVIEW: keyword (English)
- `core/scripts/check-plaintext-approval.py` — bilingual detection (independent of output rule)
