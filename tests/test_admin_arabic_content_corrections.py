"""The Arabic wording corrections mandated by the Admin content audit.

Source: docs/ADMIN_PAGE_CONTENT_AUDIT_AND_PLAN_2026-07-16.md, section 2
("Confirmed current-content defects" — corrections to production-visible content,
not optional copy improvements).

Two things make this worth a test rather than a one-off edit:

1. The copy is duplicated across templates, inline JS, i18n JSON and even Python,
   so a single string can be reintroduced from any of four places.
2. English mode is not a separate catalogue — `admin_i18n.js` matches the *Arabic
   literal* rendered in the DOM and swaps it (`addLiteralTranslationPair`), and
   `static/i18n/literal_en_overrides.json` is keyed by that Arabic text. So
   changing Arabic copy without re-keying the override silently leaves Arabic
   sitting in English mode. `test_corrected_arabic_keeps_its_english_pair` guards
   exactly that coupling.
"""
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
OVERRIDES = ROOT / "static" / "i18n" / "literal_en_overrides.json"

SCAN_EXTS = {".html", ".js", ".py"}
SKIP = (".venv", "node_modules", "/.git/", "_archived", "htmlcov", "/docs/",
        "/.kilo/", "/tests/", "/data/")

# (defective, correct) — the defective string must appear nowhere that renders.
CORRECTIONS = [
    ("لوحة المراقبة والمراقبة", "لوحة مراقبة النظام"),
    ("تقارير الدعم القرارى", "تقارير دعم القرار"),
    ("بدون وصول", "بدون موضوع"),
    ("الدور (الصلاحية)", "الدور"),
    ("لا توجد أطفال", "لا يوجد أطفال"),
    ("أطفال متكررون", "أطفال تعرضوا لحوادث متكررة"),
    ("يتطلب انتباه", "يتطلب الانتباه"),
    ("حالة قمع التحويل", "مراحل تحويل طلبات التسجيل"),
    ("قمع التسجيل", "مراحل التسجيل"),
    ("التوزيع المحافظي", "التوزيع حسب المحافظة"),
    ("كشف الشذوذات", "كشف القيم غير الاعتيادية"),
    ("تتطلب تدخل فوري", "تتطلب تدخلًا فوريًا"),
    ("تحتاج تدخلا", "تتطلب تدخلًا"),
    ("جدولات نشطة", "جداول نشطة"),
    ("مطلوب ناقص الفعلي", "العدد المطلوب مطروحًا منه العدد الفعلي"),
    ("مراجعة العمليات البرمجية", "مراجعة إجراءات النظام"),
    ("معدل نجاح الكاش", "معدل الاستفادة من ذاكرة التخزين المؤقت"),
    # No nursery type exists: models.Kindergarten has no type/category column and
    # "nursery" appears nowhere in models.py, so the spec's rule selects الحضانات.
    ("الحضانات والحضانات", "الحضانات"),
]


def _rendering_files():
    for p in ROOT.rglob("*"):
        s = p.as_posix()
        if not p.is_file() or p.suffix not in SCAN_EXTS:
            continue
        if any(x in s for x in SKIP):
            continue
        yield p


@pytest.fixture(scope="module")
def sources():
    """Every file that can render admin copy, read once.

    Undecodable files are NOT skipped. Skipping them silently drops them from
    the corpus, so `assert not hits` passes for them vacuously — and in a repo
    with a history of mojibake-corrupted templates, a file that fails to decode
    as UTF-8 is exactly the one most likely to still carry defective Arabic.
    Fall back to a lossy read so its text is still scanned, and surface the
    file through `undecodable` so it cannot hide.
    """
    out, undecodable = {}, []
    for p in _rendering_files():
        rel = p.relative_to(ROOT).as_posix()
        try:
            out[rel] = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            undecodable.append(rel)
            out[rel] = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            undecodable.append(rel)
    out["__undecodable__"] = "\n".join(undecodable)
    return out


@pytest.mark.parametrize("defective,correct", CORRECTIONS, ids=[c[1][:28] for c in CORRECTIONS])
def test_defective_arabic_is_not_rendered_anywhere(sources, defective, correct):
    hits = [f for f, txt in sources.items() if defective in txt]
    assert not hits, (
        f"{defective!r} must be {correct!r} (content audit §2) but still renders from: {hits}"
    )


def test_scan_actually_covers_the_templates(sources):
    """Anti-vacuity: if the file walk broke, every test above would pass trivially."""
    assert len(sources) > 200, f"only {len(sources)} files scanned — the walk is broken"
    assert any(f.startswith("templates/admin/") for f in sources)
    assert any(f.startswith("static/js/") for f in sources)


def test_no_rendering_file_is_unreadable(sources):
    """A file the scan cannot read is a hole in every assertion above.

    Undecodable files are now read lossily rather than skipped, so they are
    still scanned — but an unreadable one (OSError) contributes nothing and
    would let defective copy through unnoticed. Fail loudly instead.
    """
    unreadable = [f for f in sources["__undecodable__"].split("\n") if f]
    assert not unreadable, (
        f"these rendering files could not be read as UTF-8 and may hide "
        f"defective Arabic: {unreadable}"
    )


@pytest.mark.parametrize(
    "arabic,expected_en",
    [("الدور", "Role"), ("مراحل التسجيل", "Enrollment stages")],
)
def test_corrected_arabic_keeps_its_english_pair(arabic, expected_en):
    """English mode swaps the Arabic literal found in the DOM, so a corrected
    Arabic string with no override entry renders as Arabic in English mode.

    These two also had a *wrong* English side: 'الدور (الصلاحية)' mapped to
    'Role (authority)', and 'قمع التسجيل' to 'Registration suppression' — the
    literal mistranslation of قمع that the Arabic correction removes.
    """
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    assert arabic in overrides, (
        f"{arabic!r} has no entry in literal_en_overrides.json — English mode would "
        "render it as Arabic"
    )
    assert overrides[arabic] == expected_en


def test_no_override_is_keyed_by_a_defective_string():
    """A stale key is dead weight that also documents the wrong wording."""
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8"))
    stale = [d for d, _ in CORRECTIONS if d in overrides]
    assert not stale, f"literal_en_overrides.json still keyed by corrected-away text: {stale}"
