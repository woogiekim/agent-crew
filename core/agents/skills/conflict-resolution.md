# Skill: conflict-resolution

## Purpose
Enables the resolver agent to semantically analyze git merge conflicts, determine the correct resolution strategy for each conflict hunk, and produce a clean commit without any residual conflict markers.

## When to Apply
- When `git merge` or `git rebase` reports conflicts
- When conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) are detected in any file
- When another agent requests conflict resolution before continuing its work
- Never apply speculatively — only when actual conflict markers exist

## Techniques

### Conflict File Discovery
Identify all files with unresolved conflicts before attempting any resolution:

```bash
git diff --name-only --diff-filter=U
```

Process files one at a time. Never resolve multiple conflicting hunks simultaneously without understanding each one individually.

### Semantic Conflict Analysis
For each conflict hunk, understand the intent of both sides before choosing a resolution:

```
<<<<<<< HEAD (current branch)
fun calculateTotal(items: List<Item>): Money {
    return items.sumOf { it.price.amount }.let { Money(it) }
}
=======
fun calculateTotal(items: List<Item>): Money =
    items.sumOf { it.price.amount }.let { Money(it) }
>>>>>>> feature/refactor-order
```

Analysis questions:
1. What is the HEAD change trying to achieve?
2. What is the incoming change trying to achieve?
3. Are both changes functionally necessary, or does one supersede the other?
4. If both are needed, can they be merged into a single coherent block?

### Resolution Strategy Selection

| Scenario | Strategy |
|---|---|
| Both sides add independent functionality | Merge both — include all changes |
| Incoming change is a refactor of HEAD | Use incoming — it supersedes HEAD |
| HEAD is a fix applied to the same area incoming modified | Combine: apply the fix on top of incoming change |
| Resolution is semantically ambiguous | Escalate to user via structured choice UI |

### Structured User Escalation
When the correct resolution cannot be determined with confidence, present both sides to the user and ask for guidance — never guess:

```
Conflict in: {file path}

Option A (current branch — HEAD):
{HEAD content}

Option B (incoming — {branch name}):
{incoming content}

Which version should be kept, or should both be merged?
```

Present options using the host AI tool's structured choice UI.

### Post-Resolution Verification
After resolving all hunks in a file, verify no conflict markers remain:

```bash
grep -n "<<<<<<\|=======\|>>>>>>>" {file} && echo "MARKERS FOUND" || echo "CLEAN"
```

Never stage a file that still contains conflict markers.

### Commit After Resolution
Only after all files are clean:

```bash
git add {resolved-files}
git commit -m "merge: ${BRANCH} → ${TARGET} conflict resolution"
```

Use a descriptive commit message that identifies the source and target branches.

## Checklist
- [ ] All conflicted files discovered with `git diff --name-only --diff-filter=U`
- [ ] Each conflict hunk analyzed for semantic intent (both sides)
- [ ] Resolution strategy selected per hunk (merge both / use one / escalate)
- [ ] Ambiguous conflicts escalated to user via structured choice UI
- [ ] No conflict markers remain in any resolved file (verified with grep)
- [ ] All resolved files staged
- [ ] Commit created with `merge: {BRANCH} → {TARGET} conflict resolution` format
- [ ] No unresolved conflict markers in the committed files
