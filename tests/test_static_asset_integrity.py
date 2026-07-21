"""Static asset integrity: referenced files exist, rendered classes are styled.

Background: 4f98904d deleted static/css/agency_reports.css (430 lines) while four
templates still linked it, so every agency-reports page loaded a 404 stylesheet
and rendered unstyled. The same commit also introduced .agency-card-usage and
.agency-card-updated in JS without ever defining them.

Both are silent failures — the page still returns 200, it just looks broken — so
they need a test rather than review attention.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"
CSS_DIR = STATIC / "css"

# Matches "/static/..." in an HTML attribute, ignoring Jinja-interpolated paths.
_STATIC_REF = re.compile(r"""["'](/static/[^"'{}]+)["']""")


def _referenced_static_paths():
    """(template, path) for every literal /static reference in any template."""
    for template in sorted(TEMPLATES.rglob("*.html")):
        text = template.read_text(encoding="utf-8", errors="replace")
        for raw in _STATIC_REF.findall(text):
            path = raw.split("?", 1)[0]  # strip cache-busting query
            yield template, path


class TestReferencedAssetsExist:
    def test_every_referenced_static_file_exists(self):
        missing = [
            f"{template.relative_to(ROOT)} -> {path}"
            for template, path in _referenced_static_paths()
            if not (ROOT / path.lstrip("/")).is_file()
        ]
        assert not missing, (
            "templates reference static files that do not exist on disk "
            f"(these 404 at runtime and fail silently):\n  " + "\n  ".join(missing)
        )

    def test_agency_reports_stylesheet_is_present_and_substantial(self):
        """Guards against re-deletion, and against a stub 'restore'."""
        css = CSS_DIR / "agency_reports.css"
        assert css.is_file(), (
            "static/css/agency_reports.css is missing; four templates link it"
        )
        assert len(css.read_text(encoding="utf-8").splitlines()) > 50, (
            "agency_reports.css looks like a stub — the real sheet carries the "
            "full agency card, table, provenance and dark-mode design"
        )

    def test_templates_linking_the_agency_stylesheet_still_resolve(self):
        linking = [
            template.relative_to(ROOT)
            for template, path in _referenced_static_paths()
            if path.endswith("agency_reports.css")
        ]
        assert linking, "expected agency templates to link agency_reports.css"


class TestRenderedClassesAreStyled:
    """Every class the agency JS builds must have a rule somewhere in static/css."""

    JS = STATIC / "js" / "admin_agency_reports.js"

    def _rendered_classes(self):
        text = self.JS.read_text(encoding="utf-8")
        classes = set()
        for value in re.findall(r"""className\s*=\s*["']([^"']+)["']""", text):
            for token in value.split():
                # Trailing-hyphen tokens are modifier prefixes built by
                # concatenation (e.g. "agency-kpi--" + variant); the base class
                # carries the styling, so check that instead.
                classes.add(token.rstrip("-"))
        return {c for c in classes if c.startswith(("agency", "lineage"))}

    def test_all_js_rendered_agency_classes_have_css_rules(self):
        css_text = "\n".join(
            p.read_text(encoding="utf-8", errors="replace")
            for p in CSS_DIR.rglob("*.css")
        )
        unstyled = sorted(
            cls for cls in self._rendered_classes() if f".{cls}" not in css_text
        )
        assert not unstyled, (
            "admin_agency_reports.js renders elements with classes that no "
            f"stylesheet defines (they render unstyled): {unstyled}"
        )
