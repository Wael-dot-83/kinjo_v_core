"""Canonical metric registry — single source of truth for metric *metadata*.

This module is a **catalog**, deliberately DRY (see docs/reports/ADMIN_ANALYTICS_BASELINE_AUDIT.md):

  * Metric *values* are computed by ``analytics_gap_service.AnalyticsGapService``
    (the ``producer`` field names the method). The registry never re-implements math.
  * Metric *thresholds / bands / cited sources* live in ``kpi_standards.STANDARDS``
    (linked via ``kpi_standard_key``). The registry never re-declares thresholds.

The registry adds what neither of those owns: a stable ``metric_key`` -> canonical
bilingual title, layer, supported dimensions, value type / direction, privacy level,
and the data-state contract (``minimum_denominator``). ``AREA`` is surfaced to users
as *"City"* (see ``DIMENSION_LABELS``).

Definitions are stored in ``metric_definitions.json`` alongside this file so the
catalog is editable by non-developers and translatable without touching code.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

_DEFINITIONS_PATH = Path(__file__).with_name("metric_definitions.json")

# AREA is a real analytics dimension surfaced to users under the label "City"
# (no City model exists; Kindergarten.area is the finest geographic level).
DIMENSION_LABELS: Dict[str, Dict[str, str]] = {
    "NETWORK":      {"en": "Country",     "ar": "المملكة"},
    "GOVERNORATE":  {"en": "Governorate", "ar": "المحافظة"},
    "DISTRICT":     {"en": "District",    "ar": "اللواء"},
    "AREA":         {"en": "City",        "ar": "المدينة"},
    "KINDERGARTEN": {"en": "Nursery",     "ar": "الحضانة"},
    "CLASS":        {"en": "Class",       "ar": "الصف"},
    "CHILD":        {"en": "Child",       "ar": "الطفل"},
}

# Ordered drill-down path. Country -> Governorate -> City(=Area) -> Nursery -> Class -> Child.
# DISTRICT sits between Governorate and Area in the data model and is available, but the
# default user journey (per plan + Area=City decision) collapses to the levels below.
DRILLDOWN_PATH: List[str] = ["NETWORK", "GOVERNORATE", "AREA", "KINDERGARTEN", "CLASS", "CHILD"]

REQUIRED_FIELDS = (
    "metric_key", "layer", "title_en", "title_ar", "value_type",
    "direction", "supported_dimensions", "producer", "privacy_level",
)

_lock = threading.Lock()
_REGISTRY: Dict[str, Dict[str, Any]] = {}
_META: Dict[str, Any] = {}
_loaded = False


def load_registry(path: Optional[str] = None, force: bool = False) -> None:
    """Load metric definitions from JSON into memory (idempotent, thread-safe)."""
    global _loaded
    with _lock:
        if _loaded and not force:
            return
        p = Path(path) if path else _DEFINITIONS_PATH
        with p.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        # Support both the wrapped {"_meta":..,"metrics":..} shape and a flat dict.
        if isinstance(raw, dict) and "metrics" in raw:
            _META.clear(); _META.update(raw.get("_meta", {}))
            metrics = raw["metrics"]
        else:
            metrics = raw
        _REGISTRY.clear()
        _REGISTRY.update(metrics)
        _loaded = True


def _ensure_loaded() -> None:
    if not _loaded:
        load_registry()


def _kpi_standard(kpi_key: Optional[str]) -> Optional[Dict[str, Any]]:
    """Fetch the linked kpi_standards entry as a plain dict, or None.

    Imported lazily so the registry stays importable even if kpi_standards is
    unavailable (e.g. in isolated unit tests)."""
    if not kpi_key:
        return None
    try:
        import kpi_standards  # top-level module
    except Exception:
        return None
    std = kpi_standards.STANDARDS.get(kpi_key)
    if std is None:
        return None
    # KPIStandard is a dataclass-like object; expose the threshold-bearing fields.
    fields = ("kpi_key", "name_en", "name_ar", "unit", "direction", "target",
              "thresholds", "source", "confidence")
    return {f: getattr(std, f) for f in fields if hasattr(std, f)}


def get_metric(metric_key: str) -> Dict[str, Any]:
    """Return the definition for ``metric_key``, enriched with dimension labels and
    the linked kpi_standards entry (``kpi_standard`` key). Raises KeyError if unknown."""
    _ensure_loaded()
    if metric_key not in _REGISTRY:
        raise KeyError(f"Metric '{metric_key}' not found in registry")
    d = dict(_REGISTRY[metric_key])  # shallow copy — never mutate the cached dict
    d["dimension_labels"] = {
        dim: DIMENSION_LABELS.get(dim, {"en": dim, "ar": dim})
        for dim in d.get("supported_dimensions", [])
    }
    std = _kpi_standard(d.get("kpi_standard_key"))
    if std is not None:
        d["kpi_standard"] = std
    return d


# Back-compat alias for the original scaffolding name.
get_metric_definition = get_metric


def list_metrics(layer: Optional[str] = None,
                 dimension: Optional[str] = None,
                 privacy_level: Optional[str] = None) -> List[str]:
    """Return metric keys, optionally filtered by layer / supported dimension / privacy."""
    _ensure_loaded()
    keys = []
    for k, d in _REGISTRY.items():
        if layer and d.get("layer") != layer:
            continue
        if dimension and dimension not in d.get("supported_dimensions", []):
            continue
        if privacy_level and d.get("privacy_level") != privacy_level:
            continue
        keys.append(k)
    # stable order by ordinal when present
    keys.sort(key=lambda k: _REGISTRY[k].get("ordinal", 1_000))
    return keys


def all_definitions() -> Dict[str, Dict[str, Any]]:
    """Return a deep-ish copy of every raw definition (no enrichment)."""
    _ensure_loaded()
    return {k: dict(v) for k, v in _REGISTRY.items()}


def meta() -> Dict[str, Any]:
    _ensure_loaded()
    return dict(_META)


def dimension_label(dimension: str, lang: str = "en") -> str:
    return DIMENSION_LABELS.get(dimension, {}).get(lang, dimension)


def validate_registry() -> List[str]:
    """Return a list of human-readable problems. Empty list == healthy registry.

    Checks: required fields present, unique ordinals, kpi_standard_key links resolve,
    supported_dimensions are known, privacy levels valid.
    """
    _ensure_loaded()
    problems: List[str] = []
    seen_ordinals: Dict[int, str] = {}
    valid_privacy = {"internal", "restricted", "public"}
    for k, d in _REGISTRY.items():
        if k != d.get("metric_key"):
            problems.append(f"{k}: metric_key field '{d.get('metric_key')}' != registry key")
        for f in REQUIRED_FIELDS:
            if not d.get(f):
                problems.append(f"{k}: missing required field '{f}'")
        for dim in d.get("supported_dimensions", []):
            if dim not in DIMENSION_LABELS:
                problems.append(f"{k}: unknown dimension '{dim}'")
        if d.get("privacy_level") not in valid_privacy:
            problems.append(f"{k}: invalid privacy_level '{d.get('privacy_level')}'")
        ordn = d.get("ordinal")
        if ordn is not None:
            if ordn in seen_ordinals:
                problems.append(f"{k}: ordinal {ordn} collides with {seen_ordinals[ordn]}")
            seen_ordinals[ordn] = k
        kpi = d.get("kpi_standard_key")
        if kpi and _kpi_standard(kpi) is None:
            problems.append(f"{k}: kpi_standard_key '{kpi}' does not resolve in kpi_standards.STANDARDS")
    return problems


# Eager-load on import so callers can use the module functions immediately.
load_registry()
