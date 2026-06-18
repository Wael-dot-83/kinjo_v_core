# Agent Operating Rules — Admin Module Production-Readiness Task Force

This file defines how an AI coding agent (Claude Code, or any compatible agent reading
`AGENTS.md`) must approach Admin module production-readiness work in this repository.

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
