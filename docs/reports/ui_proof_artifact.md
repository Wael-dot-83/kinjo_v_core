# UI Proof Artifact

## RTL Alignment and Responsive Wrappers

The UI for the Health & Safety page (`templates/safety/index.html`) has been updated with proper RTL and responsive design techniques:

1. **Responsive Table Wrapper:**
   The incident data table is wrapped in a `<div class="table-responsive">` to ensure it scrolls horizontally on smaller screens rather than breaking the layout.
   *File: `templates/safety/index.html`*

2. **RTL Directionality:**
   The HTML structure ensures `dir="rtl"` is respected.
   Margin classes use Bootstrap 5 logical properties (`ms-` for margin-start, `me-` for margin-end) instead of physical properties (`ml-`, `mr-`). This ensures that icons and buttons space themselves correctly whether the interface is in Arabic (RTL) or English (LTR).

3. **Status Badges:**
   Incident statuses are displayed using badge classes (e.g., `badge bg-danger`, `badge bg-warning`) that naturally flow with text direction.

4. **Empty/Loading States:**
   The table dynamically shows a loading spinner or an "Empty" state with an icon centered within the table container, utilizing flexbox classes (`d-flex justify-content-center`) which are universally responsive.
