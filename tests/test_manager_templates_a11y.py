"""
Manager pages — accessibility structure and language-cleanliness checks.

Renders every reachable manager page through the real routes (auth via
dependency_overrides) and statically asserts:
- exactly one <h1>
- no duplicate element IDs
- inputs/selects have an associated label, aria-label, or title
- buttons have an accessible name (text, aria-label, or title)
- html carries lang + dir
- no raw translation keys (dashboard./manager./common.) in visible text
- no raw status enum values in visible (non-script) text
"""
import re

import pytest

import models
from main import app
from dependencies import get_current_user
from frontend import get_current_user_or_redirect

MANAGER_PAGES = [
    "/dashboard",
    "/classes",
    "/children",
    "/manager/supervisors",
    "/daily-reports",
    "/manager/absence-requests",
    "/enrollments",
    "/messages",
    "/manager/kpi",
    "/manager/benchmarking",
]

RAW_ENUMS = [
    "SUBMITTED", "SENT_TO_PARENT", "PENDING_REVIEW",
    "REJECTED", "INACTIVE", "DRAFT",
]
RAW_KEY_PREFIXES = ["dashboard.", "manager.", "common."]

_SCRIPT_RE = re.compile(r"<script\b.*?</script>", re.DOTALL | re.IGNORECASE)
_STYLE_RE = re.compile(r"<style\b.*?</style>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


@pytest.fixture
def manager_pages_html(client, test_db, kg_smoke, manager_smoke):
    app.dependency_overrides[get_current_user] = lambda: manager_smoke
    app.dependency_overrides[get_current_user_or_redirect] = lambda: manager_smoke
    pages = {}
    for path in MANAGER_PAGES:
        r = client.get(path, follow_redirects=True)
        assert r.status_code == 200, f"{path} -> {r.status_code}"
        pages[path] = r.text
    app.dependency_overrides.clear()
    return pages


@pytest.fixture
def kg_smoke(test_db):
    kg = models.Kindergarten(
        name_ar="حضانة الفحص", name_en="Smoke KG",
        governorate="عمّان", district="عمّان", area="الرابية",
        address_line="شارع", contact_phone="0790000000",
        contact_email="smoke_a11y@example.com",
        status=models.KindergartenStatus.ACTIVE,
    )
    test_db.add(kg)
    test_db.commit()
    test_db.refresh(kg)
    return kg


@pytest.fixture
def manager_smoke(test_db, kg_smoke):
    from auth import get_password_hash
    u = models.User(
        username="a11y_mgr", email="a11y_mgr@example.com",
        hashed_password=get_password_hash("Test@1234"),
        full_name="مدير الفحص", role=models.UserRole.MANAGER,
        kindergarten_id=kg_smoke.id, status=models.UserStatus.ACTIVE,
    )
    test_db.add(u)
    test_db.commit()
    test_db.refresh(u)
    return u


def _visible_text(html: str) -> str:
    no_script = _SCRIPT_RE.sub(" ", html)
    no_style = _STYLE_RE.sub(" ", no_script)
    return _TAG_RE.sub(" ", no_style)


class TestManagerA11yStructure:
    def test_exactly_one_h1(self, manager_pages_html):
        for path, html in manager_pages_html.items():
            count = len(re.findall(r"<h1\b", html, re.IGNORECASE))
            assert count == 1, f"{path}: expected exactly one <h1>, found {count}"

    def test_no_duplicate_ids(self, manager_pages_html):
        for path, html in manager_pages_html.items():
            # IDs inside <script> template literals are runtime-generated,
            # not part of the static DOM.
            ids = re.findall(r'\bid="([^"]+)"', _SCRIPT_RE.sub(" ", html))
            dupes = {i for i in ids if ids.count(i) > 1}
            assert not dupes, f"{path}: duplicate ids {sorted(dupes)}"

    def test_html_lang_and_dir(self, manager_pages_html):
        for path, html in manager_pages_html.items():
            head = html[:400]
            assert re.search(r'<html[^>]+lang=', head), f"{path}: missing lang"
            assert re.search(r'<html[^>]+dir=', head), f"{path}: missing dir"

    def test_inputs_have_labels(self, manager_pages_html):
        for path, html in manager_pages_html.items():
            labelled_fors = set(re.findall(r'<label[^>]+for="([^"]+)"', html))
            for tag in re.finditer(r"<(input|select|textarea)\b[^>]*>", html, re.IGNORECASE):
                t = tag.group(0)
                if re.search(r'type="(hidden|submit|button|checkbox)"', t):
                    continue
                id_m = re.search(r'\bid="([^"]+)"', t)
                has_label = id_m and id_m.group(1) in labelled_fors
                has_aria = "aria-label" in t or "aria-labelledby" in t or "title=" in t
                assert has_label or has_aria, f"{path}: unlabelled control {t[:120]}"

    def test_buttons_have_accessible_names(self, manager_pages_html):
        for path, html in manager_pages_html.items():
            for m in re.finditer(r"<button\b[^>]*>(.*?)</button>", html, re.DOTALL | re.IGNORECASE):
                open_tag = m.group(0)[: m.group(0).index(">") + 1]
                inner_text = _TAG_RE.sub("", m.group(1)).strip()
                has_name = bool(inner_text) or "aria-label" in open_tag or "title=" in open_tag
                assert has_name, f"{path}: button without accessible name: {m.group(0)[:120]}"


class TestManagerLanguageCleanliness:
    def test_no_raw_translation_keys(self, manager_pages_html):
        for path, html in manager_pages_html.items():
            text = _visible_text(html)
            for prefix in RAW_KEY_PREFIXES:
                pattern = re.compile(re.escape(prefix) + r"[a-z_]+")
                hits = pattern.findall(text)
                assert not hits, f"{path}: raw translation keys {hits[:5]}"

    def test_no_raw_enum_values_in_visible_text(self, manager_pages_html):
        for path, html in manager_pages_html.items():
            text = _visible_text(html)
            for enum_val in RAW_ENUMS:
                assert not re.search(rf"\b{enum_val}\b", text), (
                    f"{path}: raw enum {enum_val} visible in page text"
                )

    def test_arabic_present(self, manager_pages_html):
        for path, html in manager_pages_html.items():
            text = _visible_text(html)
            assert re.search(r"[؀-ۿ]", text), f"{path}: no Arabic text found"
