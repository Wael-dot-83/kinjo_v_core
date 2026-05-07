"""Date and number formatting helpers for bilingual UI output."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

try:
    from babel.dates import format_date as babel_format_date
    from babel.numbers import format_decimal
except ImportError:  # pragma: no cover - exercised only when Babel is absent.
    babel_format_date = None
    format_decimal = None


ARABIC_DIGIT_MAP = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def _coerce_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def format_date_en(value: Any) -> str:
    parsed = _coerce_date(value)
    if not parsed:
        return "" if value is None else str(value)
    return parsed.strftime("%m/%d/%Y")


def format_date_ar(value: Any) -> str:
    parsed = _coerce_date(value)
    if not parsed:
        return "" if value is None else str(value)
    formatted = parsed.strftime("%d/%m/%Y")
    return formatted.translate(ARABIC_DIGIT_MAP)


def format_number_ar(number: Any) -> str:
    return str(number).translate(ARABIC_DIGIT_MAP)


def format_number_en(number: Any) -> str:
    if format_decimal:
        try:
            return format_decimal(number, locale="en_US")
        except (TypeError, ValueError):
            pass
    return str(number)


def format_local_date(value: Any, lang: str = "en") -> str:
    return format_date_ar(value) if lang == "ar" else format_date_en(value)


def format_local_number(value: Any, lang: str = "en") -> str:
    return format_number_ar(value) if lang == "ar" else format_number_en(value)
