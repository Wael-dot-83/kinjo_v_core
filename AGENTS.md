# Agent Operating Rules — Admin Module Production-Readiness Task Force

This file defines how an AI coding agent (Claude Code, or any compatible agent reading
`AGENTS.md`) must approach Admin module production-readiness work in this repository.

## Agent isolation — one worktree and one branch per agent

**This reverses the 2026-07-03 "no worktrees, work in the root on `main`" rule.** That rule
was written because abandoned worktrees accumulated stale, superseded diffs. The problem
was real, but banning worktrees only moved it: it forced every concurrent agent into the
same checkout, and on 2026-07-14 that produced both failure modes at once — two agents
mutating `d:\Final Version` simultaneously (28 files churning mid-session, a branch
switched out from under an in-flight task, a rebase blocked by another agent's dirty
files), *and* a four-day-old worktree still holding 1055 lines of uncommitted work with an
unresolved merge conflict. The fix for stale worktrees is a lifecycle, not a ban.

Rules:

- Each autonomous agent uses a **dedicated git worktree and feature branch**.
- Agents must **not** modify the primary checkout (`d:\Final Version`) directly.
- Agents must **not** work directly on `main`.
- **Keep the human git author identity** and add agent attribution as commit trailers:

  ```
  Agent: Claude-Code
  Agent-Run-ID: <unique-session-id>
  ```

  Do not invent per-agent author identities: the author field carries repository
  ownership, signing and contribution history, and forging it there to gain traceability
  costs more than it buys. Trailers make concurrent work distinguishable
  (`git log --grep='Agent-Run-ID: …'`) while ownership stays correct. Today every agent
  commits as the same author with no trailer, so git cannot attribute concurrent work at all.
- Before rebasing, merging or switching branches, an agent verifies **its own** worktree is
  clean. Never run destructive git operations against a tree you do not own.
- Generated files and diagnostics are not committed unless explicitly required.

Worktree lifecycle — this is what the old rule was protecting against, so it is mandatory:

- Remove the worktree when its branch **merges or is abandoned**: `git worktree remove <path>`,
  then `git worktree prune`.
- **A worktree is stale when it has had no recorded activity for 72 hours AND has no open PR
  and no identified active owner.** Age alone is not the test: a week-old worktree behind an
  open PR is alive, while a one-day-old abandoned tree holding an unresolved conflict already
  needs attention.
- Audit `git worktree list` at session start and triage every stale tree before starting
  parallel work.

### Never abandon a worktree with uncommitted work — and rescue it completely

`git diff HEAD > rescue.patch` is **not** a rescue. It captures tracked changes (staged and
unstaged together) but **silently omits untracked files**, loses the staged-vs-unstaged
distinction, and does not record conflict stages. Untracked is the dangerous gap: a file
git has never seen leaves no trace in any diff, so the loss is invisible.

Honest note on the 2026-07-14 rescue of `D:/Final Version-dashboard-uswds`, because the
near-miss is the lesson: its unique file, `tests/test_admin_dashboard_redesign.py`, existed
nowhere else, and `git diff HEAD` *did* capture it — but only because it happened to be
**staged** (`A `). Had it been one keystroke behind, untracked (`??`), the same command
would have dropped it without a word. Do not rely on that luck; `git ls-files --others
--exclude-standard` is the only thing that finds those files.

Land the work, or export a complete package before removing anything:

```bash
git status --porcelain=v1 > rescue-status.txt          # full state, incl. UU conflicts
git diff --binary HEAD > rescue-working-tree.patch     # tracked, unstaged (binary-safe)
git diff --cached --binary > rescue-index.patch        # staged/index state
git ls-files -u > rescue-conflicts.txt                 # unresolved conflict stages
git ls-files --others --exclude-standard > rescue-untracked.txt
# then COPY every path listed in rescue-untracked.txt into the rescue directory
```

Safest of all: snapshot the whole working directory, excluding only the `.git` link.

**Restore with the working-tree patch alone — do not apply both.** `rescue-working-tree.patch`
is HEAD → working tree and *already contains* the staged changes, so applying
`rescue-index.patch` as well double-applies and fails (`patch does not apply`), leaving a
**partial** restore that still looks like it worked. Keep the index patch only as a record of
*which* changes were staged. Verified on 2026-07-15: applying both restored 6 files/832
insertions; the working-tree patch alone restored all 7/1055.

**A rescue is not proven until it is restored.** Before removing the source worktree: create
a disposable worktree at the original commit, apply the patch, copy the untracked files back,
and compare **disk to disk by hash** — every shared file byte-identical, nothing missing but
regenerable artifacts (`.env`, caches, local DB). Only then `git worktree remove` +
`git worktree prune`. "A backup appears to exist" is not recoverability.

Compare disk to disk, **not** with `git diff`: `git diff HEAD --name-only` does not list
untracked files, so a restored-but-unstaged file reports as "missing" while sitting on disk
byte-identical. That artifact cost a full round of false alarm on 2026-07-15 — the same blind
spot that makes `git diff HEAD` an unsafe rescue in the first place.

Historical audit/readiness reports live in `docs/reports/`; manually-run diagnostic and
data scripts live in `scripts/manual-diagnostics/` (the former `scripts/one_off/` was
merged into it).

## Tooling reality check (read this before following the workflow below)

This workflow describes a four-role task force ("lead implementer," "broad-sweep
automation," "independent reviewer," "test/static-analysis automation"). It does **not**
assume four separate AI products are installed and callable. Verified state of this
machine as of this writing:

| Name in the workflow      | Real status on this machine                                                                                   |
|----------------------------|------------------------------------------------------------------------------------------------------------|
| Claude CodeAgent            | Real — this is the agent executing this file.                                                                |
| "Kilo"                       | `.kilo/` exists but is only a Kilo Code *VS Code extension* workspace config (`kilo.jsonc`, `@kilocode/plugin`). It has no CLI entry point and cannot be invoked from a terminal/Bash session. |
| "Blackbox"                   | `@blackbox_ai/blackbox-cli` is installed globally via npm, but its entry file (`bundle/gemini.js`) is missing — running `blackbox` fails with `MODULE_NOT_FOUND`. It is also unauthenticated. It is **not currently runnable**. |
| "Codex"                      | Not installed; no `codex` binary on PATH. |

Because of this, every role below is fulfilled using tools that genuinely exist in a
Claude Code session: the `Agent` tool (subagent types `general-purpose`, `Explore`,
`Plan`, `claude`), and Bash-driven test/lint/static-analysis commands. **Do not claim to
have run Kilo, Blackbox, or Codex unless they have been independently re-verified as
installed, working, and authenticated in the environment at hand.** If a future
environment does have one of these tools working, it may be substituted in for the
corresponding role — but its availability must be checked the same way (run it, read
the error if any) before being relied upon, never assumed from this document alone.

## Required multi-pass orchestration

Claude Code must not work as a single-pass assistant on Admin module production-readiness
tasks. It must orchestrate multiple independent passes using its own subagents and local
verification tooling, structured as a task force with the following roles.

### 1. Lead implementer/orchestrator (Claude Code, main thread)

Responsible for:

* Understanding the full Admin module architecture (`main.py` router composition,
  `admin_endpoints.py`, `admin_security.py`, `audit_service.py`, `dashboard_api.py`).
* Creating the implementation plan.
* Delegating focused investigation/review passes to subagents spawned via the `Agent`
  tool (see roles 2 and 3 below).
* Applying final code changes.
* Resolving conflicts between subagent findings.
* Ensuring the final implementation is clean, minimal, consistent, and production-ready.
* Running final verification before declaring completion.

The lead orchestrator owns the final result and must not blame a subagent's incomplete
output for an incomplete task — if a delegated pass came back shallow, that is a reason
to re-delegate or do the work directly, not a reason to ship gaps.

### 2. Broad-sweep automation role (`Agent` tool, subagent_type: `general-purpose` or `Explore`)

Spawn one or more subagents to perform a full Admin module sweep:

* Search the entire repository for admin templates, routes, API calls, forms, CSRF
  usage, broken links, and duplicated paths.
* Identify repetitive-but-careful edits needed across multiple files.
* Flag duplicated admin endpoint logic that could be refactored into a canonical
  implementation (do not refactor unilaterally inside this pass — report it back to the
  orchestrator).
* Audit route namespacing under `/api/admin/...` for consistency.
* Check templates for consistent API paths and CSRF-safe calls.
* Check static references — favicon, JS, CSS, admin assets — actually exist.
* Produce a structured report of findings (files, line numbers, concrete issue
  description) back to the orchestrator.

This pass must continue until the full sweep is done, not stop after the first issue
found. The orchestrator decides what to fix; the sweep's job is full coverage.

### 3. Independent adversarial reviewer role (`Agent` tool, fresh subagent with no prior context)

After the orchestrator implements a fix batch, spawn a **new** subagent with no memory of
the implementation discussion (a fresh `Agent` call, not a continuation) to review
critically:

* Re-scan the repository after implementation, independently of the implementer's own
  account of what changed.
* Verify that the known P1/P2/P3 issues are actually fixed, by reading the code — not by
  trusting the implementer's summary.
* Search for new regressions introduced by the changes.
* Check admin pages don't depend on missing JS globals.
* Check all unsafe (state-changing) admin requests carry CSRF support.
* Check forms submit to routes that are actually registered.
* Check links point to pages that are actually registered.
* Check admin-only APIs are consistently namespaced, or that any deviation is an
  intentional, documented compatibility alias.
* Check for duplicate registered `(method, path)` FastAPI route pairs.
* Assess security impact, especially CSRF and admin role/IDOR protection.
* Give an explicit verdict on whether the Admin module is production-ready, with
  evidence (file:line references), not a rubber stamp.

If this pass finds a defect, the orchestrator must fix it and send the affected area back
for another adversarial pass. Do not accept the first review as final if it identifies
any production-blocking issue.

### 4. Test / static-analysis / verification role (Bash, run directly by the orchestrator)

Concrete, runnable checks — not delegated to a separate product, since none is available:

* Write or update tests for the changed behavior.
* Write small route-inspection utilities if needed (e.g. a script that imports the
  FastAPI `app` and dumps `app.routes` to check for duplicate `(method, path)` pairs).
* Run `python -m py_compile` on changed files.
* Run `ruff` (or the project's configured equivalent) for bug-class lint checks.
* Run the admin-relevant test suites, split by file/group if a combined run times out.
* Verify no duplicate route registrations exist.
* Verify static template asset assumptions (referenced files exist on disk).
* Produce machine-checkable evidence (command + output), not a narrative claim.

Verification must not stop at happy-path tests — it must specifically target the
production failures under review (the P1/P2/P3 list for the task at hand).

## Workflow

Follow this sequence without skipping steps:

1. Orchestrator performs an initial repository scan and builds an internal checklist.
2. Broad-sweep subagent performs the full Admin module audit (role 2).
3. Orchestrator implements the first fix batch.
4. Orchestrator adds/updates focused tests and runs static analysis (role 4).
5. Orchestrator runs focused verification on the fix batch.
6. A fresh subagent performs an independent adversarial review (role 3).
7. Orchestrator fixes every valid finding from step 6.
8. Repeat steps 3–7 until the adversarial review finds no production-blocking issue.
9. Run final full verification (role 4, full suite).
10. Produce the final production-readiness report.

Do not stop after one pass says "done." Completion requires implementation, automated
tests, static checks, **and** an independent adversarial review pass that found nothing
further.

## Automation requirements

Use scripts/CLI checks — not manual eyeballing — to verify:

* All admin templates calling `api.*` actually load the JS dependency that defines it.
* All admin forms using POST/PUT/PATCH/DELETE include CSRF support, or submit through a
  CSRF-aware API helper.
* All admin `fetch` calls include CSRF support directly or indirectly.
* All internal admin links resolve to registered frontend routes.
* All admin API calls resolve to registered backend routes.
* No duplicate registered FastAPI `(method, path)` pairs exist.
* All referenced admin static assets exist on disk.
* No `ReferenceError`-causing globals are used without being loaded first.

If no existing script performs a check, write a temporary or test-local inspection
utility for it. Keep it permanently only if it stays useful and clean; otherwise remove
it once its job is done.

## Non-stop completion rule

Do not stop until the task is complete. Valid reasons to stop early:

* Required repository files are missing.
* The environment cannot run any verification commands.
* A required secret, credential, database, or external service is unavailable and cannot
  be mocked.
* A destructive production action would be required.
* A test failure is proven unrelated to the Admin module and is documented as such.

Otherwise, continue implementing, testing, reviewing, and fixing until the Admin module
reaches production-ready quality.

## Final judgment

The final report must end with an explicit verdict:

* `PRODUCTION READY`, or
* `NOT PRODUCTION READY`

Only mark `PRODUCTION READY` when the implementation pass, the broad-sweep pass, the
independent adversarial review pass, and the test/static-analysis pass all agree that:

* P1 issues are fixed.
* P2 issues are resolved, or safely preserved as a documented compatibility alias.
* P3 issues are cleaned up.
* Admin-relevant tests pass.
* Compile checks (`py_compile`) pass.
* Bug-class lint checks (`ruff` or equivalent) pass.
* No duplicate routes exist.
* CSRF protection remains intact.
* Admin links, forms, API calls, and static assets are mutually consistent.

Do not hallucinate that a check passed. If a check could not be run, say so explicitly
and name the blocking reason instead of asserting a result.
