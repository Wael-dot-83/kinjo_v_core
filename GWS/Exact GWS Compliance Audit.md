MASTER TASK: Exact GWS Compliance Audit + Fix for Kinjo

Project root:
D:\Final Version

Checklist workbook:
D:\Final Version\GWS\kinjo_match_mismatch_checklist.xlsx

Source of truth:
Sheet: Full GWS Checklist

Use Claude Code skills, planning, subagents, and strict verification.

First:

1. Run repository discovery.
2. Detect stack, routes, templates, components, config, static assets, translations, tests, build commands, and security middleware.
3. Create or use a local Claude Code skill named gws-compliance-auditor if available:
   .claude/skills/gws-compliance-auditor/SKILL.md

Skill purpose:
Audit every GWS checklist row, prove evidence, fix mismatches, verify fixes, and produce final compliance artifacts.

Hard rules:

* Be strict.
* Do not assume compliance.
* Do not mark MATCH without exact evidence.
* Do not skip any checklist row.
* Do not claim 100% unless every applicable item is fully implemented and verified.
* If something cannot be verified, mark it PARTIAL or MISMATCH.
* If not applicable, explain why clearly.
* Fix code directly, not just recommendations.
* Preserve existing Kinjo business logic.
* Use minimal, safe, maintainable changes.
* Keep Arabic professional, government-appropriate, and RTL-correct.
* Keep English clean and consistent.
* Do not break existing features.

Use this status logic:
MATCH = fully implemented with direct evidence.
PARTIAL = partly implemented or unverified edge cases remain.
MISMATCH = missing, wrong, broken, insecure, inaccessible, unclear, or not evidenced.
N/A = genuinely not applicable to Kinjo, with reason.

Audit and fix these areas at minimum:

* Government website identity requirements
* Header, footer, navigation, breadcrumbs
* Arabic/English localization
* RTL/LTR rendering
* Accessibility and keyboard navigation
* Forms, labels, validation, error messages
* Service pages and service details
* Required documents, fees, duration, steps, department, contact channel
* Search, sitemap, robots.txt
* Page titles, metadata, SEO, Open Graph
* Privacy policy, terms, contact page
* Responsive layout and browser compatibility
* Broken links and missing assets
* Images, icons, alt text
* Authentication, authorization, session handling
* Security headers, CSRF, XSS, input validation
* File upload restrictions
* Error pages: 404, 500, unauthorized
* Performance and build quality

Execution:

PHASE 1 — Plan
Use plan mode before editing. Build a precise implementation plan from the workbook and repository scan.

PHASE 2 — Compliance Matrix
Read every row from Full GWS Checklist.
Create:
D:\Final Version\GWS_COMPLIANCE_MATRIX.csv

Columns:
ID, Requirement, Applicable, Status Before, Evidence Before, Gap, Fix Needed, Status After, Evidence After, Files Changed, Notes

PHASE 3 — Independent Review Passes
Use subagents if available:

* frontend-ui-accessibility-reviewer
* backend-security-reviewer
* localization-rtl-reviewer
* gws-checklist-mapper
* verification-test-runner

Each reviewer must return only:
Findings, Evidence, Required fixes, Risk.

PHASE 4 — Fix All Mismatch and Partial Items
For every applicable MISMATCH or PARTIAL:

* Edit the code.
* Add missing page/route/component/config/content/test.
* Add missing Arabic/English text where needed.
* Add accessibility attributes where needed.
* Add metadata/security/config where needed.
* Update links and navigation.
* Validate that the implementation matches the exact GWS requirement.

PHASE 5 — Verify
Run all available checks:

* install check if needed
* lint
* type check
* tests
* build
* app startup check
* route/page smoke check
* broken-link check if possible

If checks fail, fix and rerun.

PHASE 6 — Re-audit
Recheck every changed item.
Only upgrade to MATCH when direct evidence exists.

PHASE 7 — Final Deliverables
Create:
D:\Final Version\GWS_COMPLIANCE_AUDIT_REPORT.md

Report must include:

1. Executive summary
2. Stack detected
3. Checklist totals
4. MATCH count
5. PARTIAL count
6. MISMATCH count
7. N/A count
8. Final compliance percentage
9. All fixed items
10. Remaining unresolved items
11. Exact files changed
12. Tests/checks executed
13. Evidence for compliance
14. Risks and assumptions
15. Items that cannot honestly reach 100% without business/legal/government confirmation

Final instruction:
Work until every code-fixable mismatch is fixed. Be evidence-based, sharp, and strict. The goal is maximum real compliance, not cosmetic compliance. Do not stop at a generic report. Implement, verify, and document.
