# Issuer Vendor Promotion — Tighten dispatcher prose + promote production-proven Plane skill content

**Scope:** narrow. One PR. Pure-additive on `~/.agent-crew/user/skills/issuer-plane.md`
plus a small in-place tightening of `core/agents/issuer.md` and a one-line
update to `core/rules/agent-routing.md`.

**Companion doc:** `generalized-dispatcher-primitive.md` (broad case). This
doc stands on its own evidence; do not gate it on the broader proposal.

---

## 1. What changed in production (local prototype `20260531-111840-0`)

The local prototype against `~/.agent-crew/` made three coordinated edits.
The diffs are reproduced verbatim from that task's `result.md`.

### 1.1 Dispatcher prose tightening — `core/agents/issuer.md`

Upstream `core/agents/issuer.md` is 667 lines. The local prototype version is
677 lines (+10). The added lines are concentrated in two places:

**(a) Vendor literal removal — lines 208, 223–224, 244–246.** The dispatcher's
interactive option dialogs currently contain vendor literals:

```text
| Contains `gitlab.com` ... | Set `BACKEND_ADAPTER=gitlab`. Use `mcp__gitlab` tools. |
...
  - `[B] GitLab — use mcp__gitlab (issuer-gitlab)`
  - `[C] Plane — use mcp__plane (issuer-plane)` _(default)_
...
  - `[B] GitLab (mcp__gitlab)`
  - `[C] Plane (mcp__plane)`
```

Promoted form:

```text
| Contains `gitlab.com` ... | Set `BACKEND_ADAPTER=gitlab`. Tool dispatch is owned by the `issuer-gitlab` skill. |
...
  - `[B] GitLab — issuer-gitlab skill`
  - `[C] Plane — issuer-plane skill` _(default)_
...
  - `[B] GitLab (issuer-gitlab skill)`
  - `[C] Plane (issuer-plane skill)`
```

**Why:** the dispatcher's job description is "tool-agnostic". Mentioning the
underlying MCP namespace or CLI in user-facing prompts contradicts that
contract. The skill name (`issuer-gitlab`, `issuer-plane`) is the contract;
the host MCP tool / CLI is an implementation detail owned by the skill.

**(b) Step 0.5 dispatch rail — sub-step 3, ~lines 271–285.** The current
text says "Load the skill named `issuer-{BACKEND_ADAPTER}`. The skill is
installed at `~/.agent-crew/user/skills/issuer-{BACKEND_ADAPTER}.md`. ...".
The promoted version adds an explicit Skill-tool invocation reminder for
Claude Code adapters and an enforcement rail:

> **MUST NOT execute any backend-specific tool call (e.g. `mcp__plane__*`,
> `mcp__gitlab__*`, `gh api *`) before this skill load returns.** Any such
> call before the skill is loaded indicates the dispatcher has bypassed its
> own dispatch boundary and must be treated as a workflow bug.

**Why:** without this rail the dispatcher can silently regress — the LLM has
no enforcement to prevent it from calling Plane / GitHub tools "to verify
something" before the skill is loaded. The rail makes the boundary
machine-checkable for future PR review.

### 1.2 `issuer-plane` skill enrichment — `~/.agent-crew/user/skills/issuer-plane.md`

Upstream user-layer file is 582 lines. The local prototype is 713 lines
(+131). The additions are:

**(a) Three new Tools Required rows** (lines 26–28). Adds
`mcp__plane__create_work_item_comment`, `mcp__plane__list_work_item_comments`,
and `mcp__plane__delete_work_item` to the manifest at the top of the skill
file. These tools were already in use through the agent-tools allowlist; the
manifest was simply stale.

**(b) New `## Quirks (Plane API)` section** (~lines 409–484). Four documented
quirks, each with a workaround:

| ID | Quirk | Workaround |
|----|---|---|
| Q1 | `mcp__plane__retrieve_work_item` Pydantic adapter raises validation error on certain field shapes; the error message leaks the raw response, which is itself usable. | Catch the Pydantic exception and parse the leaked raw fields. |
| Q2 | `mcp__plane__create_work_item` truncates `description_html` in bulk-creation paths. | Issue a follow-up `update_work_item` with the full HTML body. |
| Q3 | Checklist rendering requires TipTap-flavoured TaskList HTML (`<ul data-type="taskList"><li data-type="taskItem" data-checked="false">...`). Literal `[x]` / `[ ]` markdown will not render as an interactive checkbox in the Plane UI. | Generate the TaskList HTML form. Proven shape lives in shopping commit `24f9719d8` (ENRTC-437). |
| Q4 | Literal `[x]` / `[ ]` in any Plane HTML body is silently rendered as static text, never as a checkbox. | Cross-references Q3. Captured as mnemos memory `feedback-plane-checkbox-html` so future agents will not repeat the mistake. |

**(c) New `### Partial Update Discipline (Plane PATCH semantics)` subsection**
(~lines 565–617). Documents three operationally-important rules:

- **Field omit ≠ field clear.** PATCH ignores omitted fields. To clear a
  collection field (`label_ids`, `assignee_ids`) you MUST send an explicit
  empty array.
- **Set-replacement semantics on collection fields.** `label_ids` and
  `assignee_ids` are replaced wholesale; there is no add-one-label primitive.
  Read-modify-write is mandatory when an additive change is intended.
- **Canonical single-field state transition** must send exactly `{"state": "<state_uuid>"}`
  and nothing else. Sending extra fields with stale values is a common cause
  of cross-field drift.

And one verify rule:

- **Verify-after-mutation.** Every PATCH must be followed by a re-read
  (`retrieve_work_item`); if the persisted field does not match the intended
  value the skill MUST emit `STATUS=DRIFT` rather than silently returning
  `STATUS=OK`. This catches Plane backend-side rejection cases that return
  200 but do not persist the change.

### 1.3 Tool routing one-liner — `core/rules/agent-routing.md`

The issuer row's Scope column already reads:

```text
| issuer | Issue lifecycle management for creation, state transitions, and field updates (user-installed, tool-agnostic dispatcher) | ... |
```

Promoted form (line 42 only):

```text
| issuer | Issue lifecycle management (tool-agnostic dispatcher; loads issuer-<tool> skill at runtime: plane / github / ...) | ... |
```

Keywords unchanged. Safe-for-direct-invocation flag unchanged (`yes`).

---

## 2. Why these belong upstream together

The three changes form one promotion unit because:

- Removing vendor literals from the dispatcher (1.1a) without updating the
  routing-rule scope text (1.3) leaves the routing rule advertising
  "user-installed" — which is correct as far as installation goes but
  understates the architectural shift.
- The Step 0.5 rail (1.1b) is the enforcement boundary for the contract that
  the Quirks + Partial-Update content (1.2) assumes. The skill content
  describes *how* Plane works; the dispatcher rail enforces *who* gets to
  call those Plane tools.
- The Quirks/Partial-Update content (1.2) only adds value when the
  dispatcher's prose actually points at the skill (1.1). Today the dispatcher
  prose already does point at the skill, but the vendor literals in the
  prompts undermine the abstraction.

Bundling avoids a half-promoted state where users see the new docs but the
dispatcher still says `mcp__plane`.

---

## 3. Production evidence — ENRTC-437 live E2E

The ship-threshold case rests on **live regression**, not unit-test theatre.

- **Repo:** shopping (`/Users/wook/IdeaProjects/danawa/shopping`)
- **Commit:** `24f9719d8 test(ENRTC-437): 답나와 2차 - E2E 시나리오 7건 작성 + 라이브 회귀 검증 결과`
- **Coverage axis A (implementation):** 9 of 9 PASS
- **Coverage axis B (planning fidelity):** 8 of 9 PASS
- **Spec gaps closed:** 8 gaps documented in `docs/e2e-reports/ENRTC-437-e2e-result.md`
- **Surface:** ccstack shopping workspace, fixity (`:8096`) + proxy (`:8085`) + MySQL — real backing services, not mocks. See mnemos memory `reference_ccstack-local-e2e` and `feedback_prefer-live-e2e` (project rule: "통합테스트/E2E"는 mock 슬라이스가 아니라 ccstack 실서버 라이브 E2E를 의미).

Every Quirk in 1.2(b) was first observed during this E2E run. The Partial
Update Discipline rules (1.2c) were derived from `label_ids` / `assignee_ids`
PATCH failures during the same run. The fixes are already encoded in the
local-prototype skill file and re-tested against the live surface — they
work, they ship value.

---

## 4. Back-compat & ship-threshold

**Back-compat:** purely additive.
- New manifest tool rows do not remove or rename existing tools.
- The Quirks section is new content; it does not change existing skill behavior.
- The Partial Update Discipline subsection is new content; existing skill
  behavior continues unchanged.
- Dispatcher prose changes are visual-only inside interactive prompts and
  add one MUST-NOT rail — they do not change the dispatch logic flow.
- The agent-routing.md scope text is descriptive metadata; downstream
  routing keywords are unchanged.

**Ship-threshold call (honest):**
- The Quirks + Partial Update Discipline content clears the threshold on its
  own evidence (8 spec gaps closed, live E2E PASS rate). Ship it.
- The dispatcher prose tightening alone is **borderline**. It is the right
  architectural move but its standalone value is small (cosmetic + one
  enforcement rail). Bundling it with the skill enrichment is what makes it
  worth a PR cycle.
- Recommendation: ship as a single PR. Honest framing — "the prose tightening
  rides along with the production-proven skill content". Do not over-sell
  the prose change.

---

## 5. Recommended PR scope

**One PR, single commit (after upstream branch is rebased to current main):**

- `core/agents/issuer.md` — prose tightening, lines 208, 223–224, 244–246,
  271–285 (+10 net lines).
- `core/rules/agent-routing.md` — line 42 Scope text update.
- **Skill content** — `issuer-plane.md` Quirks + Partial Update Discipline +
  three Tools Required rows. **Caveat:** because the source repo deliberately
  excludes `core/agents/skills/issuer-plane.md` per commit `1f89c02`
  ("user-layer-only" policy), the skill content cannot land in the source
  tree as a regular file. Two viable channels:
  1. **Docs-as-reference (default):** add the proposed skill diff to this
     research branch under `docs/issuer-vendor-skill-layer-dip-review/issuer-plane-promotion-template.md`
     and let downstream users sync the content into their own
     `~/.agent-crew/user/skills/issuer-plane.md` manually. Preserves the
     user-layer-only policy literally.
  2. **Reference-template (recommended):** add the proposed skill content as
     `core/agents/skills/templates/issuer-plane.template.md` (note `templates/`
     prefix). Document in the policy that template files are *seeds* — never
     auto-merged into the user layer; users opt in via `crew:setup` /
     `crew:update` flows. This preserves the spirit of the user-layer-only
     policy (no automatic system→user content overrides) while giving the
     framework a canonical reference.

The PR description must explicitly call out the user-layer policy and which
channel is being adopted. This is the single design question this PR has to
answer; if reviewers prefer channel 1 we keep the PR purely to the dispatcher
+ routing edits and ship the skill content in a doc.

### 5.1 Channel B — operational design sketch

The "reference-template" idea above is thin as a one-paragraph bullet. The
remainder of § 5 expands it into a concrete operational design so it can be
evaluated against Channel A on equal footing.

**Template location.** Each tracker adapter ships as
`core/agents/skills/templates/issuer-<tool>.md` (e.g.
`core/agents/skills/templates/issuer-plane.md`,
`core/agents/skills/templates/issuer-github.md`). Extension is `.md` —
identical shape to the user-layer file at
`~/.agent-crew/user/skills/issuer-<tool>.md`. The user-layer file remains
the runtime artifact the dispatcher loads; the template is purely a *seed*.

**`crew:setup` behaviour.** On first install (or first invocation of
`crew:setup` after a fresh checkout), for each template:

- If `~/.agent-crew/user/skills/issuer-<tool>.md` does NOT exist, copy from
  the matching template.
- If it DOES exist, log `user skill already present, template not applied`
  and continue. NEVER overwrite.

This makes onboarding "drop-the-tool-list and re-run setup", with no risk
of clobbering a user's existing customisations.

**`crew:update` behaviour (the critical piece).** Updates are where
naïve template systems break the user-layer policy. The rule is:

- NEVER overwrite a user-layer skill from a template. Period.
- On every update, compare the installed user-layer skill against the
  corresponding template byte-for-byte. If they differ, surface a single
  advisory line per agent:
  `[crew:update] user skill <name> diverged from system/template (N lines); run 'crew update --reconcile-skills' to compare`.
- `crew update --reconcile-skills` is an opt-in flow: it writes a unified
  diff to `~/.agent-crew/state/{PROJECT}/reconcile/<name>.diff` and stops.
  The user reads the diff out-of-band and decides whether (and how) to
  hand-merge. No automatic write to the user layer ever happens.

**Policy alignment.** The `1f89c02` user-layer-only policy is honoured by
construction: templates live under `core/agents/skills/templates/` (a *seed*
path that is explicitly out of the dispatcher's load path), never under
`core/agents/skills/<tool>.md` (which `1f89c02` explicitly removed). The
dispatcher's runtime contract — "load `~/.agent-crew/user/skills/issuer-<tool>.md`
into prompt" — does not change.

**Implementation footprint.** Estimated ~30–60 LOC across
`core/setup/install.sh` (the seed-on-first-install branch),
`core/commands/update.md` (the diverged-advisory emit and the
`--reconcile-skills` flag), and one new helper script
`core/setup/reconcile-skills.sh` (the diff-to-state-dir flow). Wave-A scope.

**Recommended channel: B**. Channel A is rejected because runtime
knowledge-in-prompt is the whole point of the dispatcher; docs-as-reference
defeats that. Channel C remains a tactical fallback if Wave-A framework
appetite is constrained, but Channel B is the right durable shape.

---

## 6. Local prototype reference

| Artifact | Path / commit |
|---|---|
| Prototype task state | `~/.agent-crew/state/shopping/tasks/20260531-111840-0/` |
| Prototype `result.md` | same dir, `result.md` |
| Local-edited `issuer.md` (677 lines, +10 vs upstream) | `~/.agent-crew/system/agents/issuer.md` |
| Local-edited `issuer-plane.md` (713 lines, +131 vs upstream) | `~/.agent-crew/user/skills/issuer-plane.md` |
| Local-edited routing rule (line 42) | `~/.agent-crew/rules/agent-routing.md` |

The local prototype was verified through 9 grep / structural checks
(documented in the prototype's `result.md` § "Verification"). All 9 pass.

---

## 7. Citation map

| Claim | Evidence |
|---|---|
| Dispatcher exists, is backend-agnostic, lives in `core/agents/issuer.md` | Commits `89d85a1` (Step 0.5 gate), `40631f6` (Step 0 tracker resolution), `2543527` (lifecycle expansion) |
| Adapter skills deliberately excluded from source repo (user-layer-only) | Commit `1f89c02` — explicit policy with mnemos memory `711045c9-8378-41fb-88c2-d8a5e9079f36` |
| TipTap TaskList HTML requirement is non-obvious | mnemos memory `feedback-plane-checkbox-html` + shopping commit `24f9719d8` (proven shape) |
| Live E2E is the bar, not mock slices | mnemos memory `feedback_prefer-live-e2e` (project rule) |
| Research-before-implementation discipline | mnemos memory `feedback-research-before-implementation` — this doc set IS that research |
| Ship-threshold framing | mnemos memory `feedback-ship-threshold` |
| Commit-message convention examples | `0c47ce3`, `68fc277`, `f288ef0`, `d501a25` (recent main commits) |

---

## 8. Open questions for upstream

1. **User-layer-only policy literal vs. template channel** — see § 5. This is
   the single material design choice this PR forces.
2. **Where does Quirks belong long-term?** This proposal puts it in the
   adapter skill. An alternative is a separate `core/rules/plane-quirks.md`
   referenced by the skill. The skill-local placement is recommended
   (cohesion ↑, navigation ↓) but is worth a one-line reviewer poll.
3. **`STATUS=DRIFT` taxonomy.** The verify-after-mutation rule introduces a
   new status. Other adapters (GitHub, GitLab) face similar persisted-vs-200
   drift; should `STATUS=DRIFT` be standardized in the Adapter Interface
   Contract section of `core/agents/issuer.md`? Out of scope for this PR
   if reviewers want it gated; in scope as a 5-line addition if not.

---

## 9. Out of scope

- Generalizing the dispatcher + skill pattern to other agents. See
  `generalized-dispatcher-primitive.md` — that is its own design discussion.
- Removing `mcp__plane` / `mcp__gitlab` literals from anywhere outside
  `core/agents/issuer.md`. Other agents may legitimately enumerate the
  tools they bind to; only `issuer` claims tool-agnosticism.
- Filing the upstream GitHub issue. That is Phase 2 after user review of
  this doc set.
- Opening the PR. That is Phase 3 after issue direction is approved.
