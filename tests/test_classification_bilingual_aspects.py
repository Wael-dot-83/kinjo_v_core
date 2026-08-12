"""Bilingual integrity for the classification page's aspects and guidance.

The detail modal rendered backend strings verbatim, so an English admin read
Arabic aspect names and Arabic advice. Project rule: any backend string shown in
the UI supplies both an Arabic and an English variant.
"""

from pathlib import Path

import classification_service as cs

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "static" / "js" / "admin_classification.js"

ARABIC_RANGE = range(0x0600, 0x0700)


def _has_arabic(text: str) -> bool:
    return any(ord(ch) in ARABIC_RANGE for ch in text)


def test_aspect_codes_are_ascii_and_labelled_in_both_languages():
    """Aspect dict keys used to be Arabic display strings rendered raw by the UI."""
    for code, label in cs.ASPECT_LABELS.items():
        assert code.isascii(), f"aspect code {code!r} must be a stable ASCII code"
        assert label["ar"] and label["en"]
        assert _has_arabic(label["ar"])
        assert not _has_arabic(label["en"])


def test_every_action_is_bilingual():
    for code, entry in cs._ASPECT_ACTIONS.items():
        assert code in cs.ASPECT_LABELS, f"{code} has guidance but no label"
        assert _has_arabic(entry["ar"])
        assert entry["en"] and not _has_arabic(entry["en"])


def test_actions_from_aspects_returns_bilingual_pairs():
    actions = cs._actions_from_aspects({"attendance_consistency": 10.0})
    assert actions and isinstance(actions[0], dict)
    assert set(actions[0]) == {"ar", "en"}
    assert not _has_arabic(actions[0]["en"])


def test_healthy_entity_still_gets_bilingual_guidance():
    """The "keep it up" fallback was a bare Arabic string among dicts."""
    actions = cs._actions_from_aspects({"attendance_consistency": 99.0})
    assert actions and isinstance(actions[0], dict)
    assert not _has_arabic(actions[0]["en"])


def test_unknown_aspect_falls_back_without_leaking_a_raw_code():
    """The old generic branch embedded the raw key in an Arabic sentence."""
    actions = cs._actions_from_aspects({"totally_unknown": 5.0})
    assert set(actions[0]) == {"ar", "en"}
    assert "totally_unknown" in actions[0]["en"]


def test_manager_aspects_are_not_duplicated_across_languages():
    """Manager payloads carried each metric twice -- once under an English code
    and once under an Arabic one -- duplicating modal rows and double-counting
    the indicator chart."""
    source = (ROOT / "classification_service.py").read_text(encoding="utf-8")
    blocks = [chunk.split("}", 1)[0] for chunk in source.split("aspects={")[1:]]
    assert blocks, "no aspects={...} literals found"
    for block in blocks:
        assert not _has_arabic(block), f"aspect keys must be ASCII codes only: {block!r}"
    # The manager metrics survive under their code names.
    joined = "\n".join(blocks)
    for code in ("attendance_consistency", "report_completion", "report_timeliness"):
        assert code in joined


def test_indicator_explanations_carry_english():
    for entry in cs.BenchmarkingService._indicator_explanations():
        assert entry["meaning_en"] and not _has_arabic(entry["meaning_en"])
        assert entry["indicator_en"] and not _has_arabic(entry["indicator_en"])


def test_frontend_localises_labels_and_actions():
    js = JS.read_text(encoding="utf-8")
    assert "function localizedText" in js
    assert "function aspectLabel" in js
    # The modal and the chart must both go through the localisation helpers.
    assert "aspectLabel(detail, name)" in js
    assert "localizedText(action)" in js
    assert "localizedText(labels[name])" in js
