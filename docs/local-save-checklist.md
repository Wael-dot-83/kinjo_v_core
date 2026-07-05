# Local Save Checklist

Reusable end-of-session checklist to confirm all work is committed to
the local repo before pushing or switching contexts. Pair with
[admin-audit-prompt.md](admin-audit-prompt.md) for audit-series work.

## Steps

1. **Check status**
   - `git status --short` — list every modified, added, and untracked file.
   - Also run `git diff --stat` for staged+unstaged changes and `git log -5 --oneline` to match this repo's commit style.

2. **Attribute every change before touching anything**
   - This repo often has more than one agent working in it concurrently. Before staging, confirm which files are actually yours to commit — cross-check against any "explicitly excluded" list from the current task (e.g. `/admin/heatmap`, `/admin/daily-reports-organization` are owned by another agent as of 2026-07).
   - If a file you didn't intend to touch shows as modified, investigate before assuming it's safe to include or discard.

3. **Stage explicitly — never blanket-add**
   - Add files by exact path: `git add path/to/file1 path/to/file2`.
   - **Never** use `git add -A` or `git add .` — this repo's rule exists specifically to avoid sweeping up another agent's in-progress files, secrets (`.env`, credentials), or large/generated artifacts into your commit.
   - Never commit secrets, API keys, `.env` files, or other sensitive data.
   - Generated/temporary files (`*.pyc`, `__pycache__/`, logs, scratch scripts) belong in `.gitignore`, not in a commit — if they're untracked and appear in status, that's a signal something is misconfigured, not something to `git add` anyway.

4. **Verify staged content matches intent**
   - `git status --short` again — confirm *only* the intended files show `A`/`M` with no stray extras.

5. **Write the commit message**
   - Conventional format: `<type>(<scope>): <subject>` title (~50 chars), blank line, body explaining *why*, not just *what*.
   - Split unrelated changes into separate commits rather than one grab-bag commit.

6. **Commit — but only when asked**
   - Per this project's working agreement: **do not commit unless the user has explicitly asked for a commit in this turn.** "Save your progress" from the user counts as asking; silently committing on your own initiative does not.
   - Use a heredoc for multi-line messages (avoids quoting issues), and never skip hooks (`--no-verify`) or bypass signing.

7. **Verify after committing**
   - `git status` → should read "working tree clean" (aside from any explicitly-excluded concurrent-agent files).
   - `git log -1` → confirm the resulting hash and message.

8. **Push is a separate, separately-confirmed step**
   - Committing locally and pushing to `origin` are different trust levels. Even when the user's instructions include a `git push` command, confirm before running it unless the user has already established (earlier in the session, or in a durable file like `CLAUDE.md`) that pushes in this repo don't need per-instance confirmation.

## Output

Report: which files were committed (or confirmation the tree was already clean), the commit message and hash, and explicitly call out anything left uncommitted on purpose (e.g., another agent's files, or work-in-progress the user asked to hold back).
