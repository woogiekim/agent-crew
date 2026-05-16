# Skill: conflict-resolution

## Purpose
Enables the resolver agent to semantically analyze git merge conflicts, determine the correct resolution strategy for each conflict hunk, and produce a clean commit without any residual conflict markers.

## When to Apply
- When `git merge` or `git rebase` reports conflicts
- When conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) are detected in any file
- When another agent requests conflict resolution before continuing its work
- Never apply speculatively — only when actual conflict markers exist

---

## Three-Way Merge Concepts

Git merge conflicts arise when the **common ancestor**, **HEAD (ours)**, and the **incoming branch (theirs)** all differ in the same region. Understanding the ancestor is the key to correct resolution.

```bash
# Inspect what the ancestor looked like before both sides changed
git show $(git merge-base HEAD MERGE_HEAD):{file}

# Show all three versions side-by-side
git checkout --conflict=diff3 {file}   # adds ||||||| ancestor section
```

With `diff3` style the hunk becomes:
```
<<<<<<< HEAD
our version
||||||| base
original version before either change
=======
their version
>>>>>>> feature/branch
```

Comparing all three versions avoids picking a side blindly.

---

## Conflict Type Classification

| Type | Description | Example |
|---|---|---|
| **Textual** | Same lines edited differently; content is clear | Both sides renamed a variable differently |
| **Semantic** | Syntactically OK but logically inconsistent | One side adds validation, other side removes the field being validated |
| **Phantom** | Content is identical; conflict from whitespace/EOL/formatter | Resolve immediately in favour of HEAD |
| **Structural** | Conflicting class/method boundaries | Method moved to a different class on one side |

Always classify before resolving. Phantom conflicts are safe to auto-resolve; semantic conflicts require careful analysis.

---

## Conflict File Discovery

```bash
git diff --name-only --diff-filter=U
```

Process files one at a time. Never resolve multiple conflicting hunks simultaneously without understanding each one individually.

---

## Semantic Conflict Analysis

For each conflict hunk, answer before choosing a resolution:

1. What is the HEAD change trying to achieve?
2. What is the incoming change trying to achieve?
3. Are both changes functionally necessary, or does one supersede the other?
4. If both are needed, can they be merged into a single coherent block?

```
<<<<<<< HEAD (current branch)
fun calculateTotal(items: List<Item>): Money {
    return items.sumOf { it.price.amount }.let { Money(it) }
}
||||||| base
fun calculateTotal(items: List<Item>): Int {
    return items.sumOf { it.price }
}
=======
fun calculateTotal(items: List<Item>): Money =
    items.sumOf { it.price.amount }.let { Money(it) }
>>>>>>> feature/refactor-order
```

Here both sides do the same thing — HEAD wrapped in braces, incoming uses expression body. This is a phantom/textual conflict; accept incoming (cleaner style).

---

## Resolution Strategy Selection

| Scenario | Strategy |
|---|---|
| Both sides add independent functionality | Merge both — include all changes |
| Incoming is a refactor of HEAD logic | Use incoming — it supersedes |
| HEAD is a bug fix applied to same area incoming modified | Apply the fix on top of incoming |
| Whitespace / formatter only | Accept HEAD (avoid spurious diffs) |
| Resolution is semantically ambiguous | Escalate to user via structured choice UI |

---

## Git Rerere — Reuse Recorded Resolution

(Reference: `git rerere` — reuse recorded resolution, git-scm.com)

Enable `rerere` to auto-resolve recurring conflicts in long-running branches:

```bash
git config --global rerere.enabled true
```

After manually resolving a conflict, `rerere` records the resolution. Next time the same textual conflict appears, it applies automatically. Useful when rebasing a long feature branch repeatedly onto main.

---

## Structured User Escalation

When the correct resolution cannot be determined with confidence, present options — never guess:

```
Conflict in: {file path}

Option A (current branch — HEAD):
{HEAD content}

Option B (incoming — {branch name}):
{incoming content}

Which version should be kept, or should both be merged?
```

Present using the host AI tool's structured choice UI.

---

## Post-Resolution Verification

```bash
# Verify no markers remain
grep -n "<<<<<<\|=======\|>>>>>>>" {file} && echo "MARKERS FOUND" || echo "CLEAN"

# Verify the file still compiles / parses
./gradlew compileKotlin 2>&1 | tail -5    # Kotlin
npx tsc --noEmit 2>&1 | tail -5           # TypeScript
python3 -m py_compile {file}              # Python
```

Never stage a file that still contains conflict markers or fails to parse.

---

## Commit After Resolution

```bash
git add {resolved-files}
git commit -m "merge: ${BRANCH} → ${TARGET} conflict resolution"
```

Use a descriptive commit message that identifies the source and target branches.

---

## Checklist
- [ ] All conflicted files discovered with `git diff --name-only --diff-filter=U`
- [ ] `diff3` style used to inspect the ancestor for non-obvious conflicts
- [ ] Each conflict hunk classified (textual / semantic / phantom / structural)
- [ ] Semantic intent of both sides analyzed before choosing resolution
- [ ] Resolution strategy selected per hunk (merge both / use one / escalate)
- [ ] Ambiguous semantic conflicts escalated to user via structured choice UI
- [ ] No conflict markers remain in any resolved file (verified with grep)
- [ ] Resolved file parses/compiles successfully
- [ ] All resolved files staged
- [ ] Commit created with `merge: {BRANCH} → {TARGET} conflict resolution` format
