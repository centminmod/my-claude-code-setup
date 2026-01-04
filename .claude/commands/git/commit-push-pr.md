---
description: Commit changes, push to remote, and optionally create a PR
---

$ARGUMENTS

## Current state

```bash
git status --short
git diff --stat
git log --oneline -3
```

## Instructions

Based on the changes shown above:

1. **Stage files** - Add all changed files except CLAUDE*.md files
   ```bash
   git add -A
   git reset CLAUDE*.md 2>/dev/null || true
   ```

2. **Commit** - Write a clear message (1-2 sentences, explain "why" not "what")
   ```bash
   git commit -m "Your message here"
   ```

3. **Push** - Push to the current branch
   ```bash
   git push -u origin HEAD
   ```

4. **Create PR** (only if user asked for it or said "pr")
   ```bash
   gh pr create --fill
   ```

## Notes

- If there's nothing to commit, say so and stop
- If push fails, try `git pull --rebase` first then push again
- Keep commit messages simple and in lowercase
