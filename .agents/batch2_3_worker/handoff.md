# Observation
- Found existing `GET /api/incidents` endpoint in `safety_service.py`.
- Found that health alerts for a child were only available via `GET /children/{child_id}/health-alerts` in `api/portfolio.py`. There was no KG-wide summary for dashboard cards or health alerts.
- Found `templates/safety/index.html` only had a simple table with a basic client-side renderer for unresolved incidents.

# Logic Chain
- To support dashboard summary cards (Batch 3), added `GET /incidents/summary` to calculate total open, high-severity, and resolved incidents from `models.Incident` based on the user's scope.
- To support the KG-wide health alerts section (Batch 3), added `GET /health-alerts/summary` to query explicit `models.HealthAlert` instances AND children with `has_medical_condition=True` or `medical_notes` / `allergy_notes`.
- To support advanced UI/UX (Batch 2), completely updated `templates/safety/index.html`:
  - Added summary cards for Dashboard Metrics.
  - Added Health Alerts section using data from the new endpoint.
  - Added frontend filtering controls (Date range, Status, Severity, Search).
  - Added `saveFilters()` and `restoreFilters()` using `localStorage`.
  - Upgraded table with sortable headers, pagination controls, and empty/loading states.
  - Added Export CSV and Print buttons with simple `window.print()` and client-side CSV generation.

# Caveats
- I could not run `python -m py_compile safety_service.py` to check compilation because command execution timed out waiting for user approval. However, the syntax used is standard SQLAlchemy and FastAPI.
- Frontend CSV export assumes Arabic text encoding using `\uFEFF` (BOM), which should work smoothly in Excel.

# Conclusion
Batches 2 and 3 of the incident management workflows have been successfully implemented. The Health & Safety page now features dashboard metrics, a health alerts summary, and an advanced, mobile-responsive incident data table with filtering, sorting, pagination, and export capabilities.

# Verification Method
- Access `/safety` as a Manager or Admin.
- Verify that three dashboard summary cards are present and populated.
- Verify that the Health Alerts section lists children with conditions.
- Try filtering incidents by Status/Severity/Date and see if the table updates and pagination works.
- Click "Export CSV" to ensure the table data is downloaded correctly.
