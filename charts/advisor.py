"""ChartAdvisor — statistical decision engine that selects optimal chart types.

Decision matrix:
  Input data shape + statistical profile → ranked list of ChartType suggestions
  with confidence scores and human-readable rationales.
"""

from __future__ import annotations

from typing import List, Tuple

import pandas as pd

from charts.schemas import ChartType, ChartSource, DataProfile, ChartSuggestion
from charts.stats import profile_dataframe


class ChartAdvisor:
    """Analyzes a DataFrame and returns up to N chart-type suggestions."""

    # (confidence, rationale_en) pairs for each rule
    _RULES: List[Tuple[str, ...]] = []  # filled in _score

    def suggest(
        self,
        df: pd.DataFrame,
        source: ChartSource,
        max_suggestions: int = 3,
    ) -> Tuple[List[ChartSuggestion], DataProfile]:
        """Return (suggestions, profile) given a raw DataFrame."""
        profile = profile_dataframe(df)
        scores = self._score(profile, source)
        # deduplicate, sort by confidence desc, cap at max_suggestions
        seen: set = set()
        unique: List[Tuple[float, ChartType, str]] = []
        for conf, ctype, rationale in sorted(scores, key=lambda x: -x[0]):
            if ctype not in seen:
                seen.add(ctype)
                unique.append((conf, ctype, rationale))
            if len(unique) >= max_suggestions:
                break

        suggestions = [
            ChartSuggestion(
                chart_type=ctype,
                title=self._default_title(source, ctype),
                rationale=rationale,
                confidence=round(conf, 2),
            )
            for conf, ctype, rationale in unique
        ]
        return suggestions, profile

    # ------------------------------------------------------------------
    # Decision matrix
    # ------------------------------------------------------------------

    def _score(
        self, p: DataProfile, source: ChartSource
    ) -> List[Tuple[float, ChartType, str]]:
        """Return a scored list of (confidence, ChartType, rationale) tuples."""
        scores: List[Tuple[float, ChartType, str]] = []

        # Guard: empty data
        if p.row_count == 0:
            return [(0.1, ChartType.BAR, "No data available — bar chart is a safe default.")]

        # ── Time-series rules ─────────────────────────────────────────
        if p.has_time_series:
            span = p.time_span_days or 0
            if span > 180:
                scores.append((0.95, ChartType.LINE,
                    "Long time span (>6 months) → line chart best shows trend continuity."))
                scores.append((0.70, ChartType.BAR,
                    "Bar chart complements the line to emphasize per-period magnitude."))
            elif span > 30:
                scores.append((0.88, ChartType.LINE,
                    "Multi-month time series → line chart reveals week-over-week trends."))
                scores.append((0.65, ChartType.BAR,
                    "Grouped bar chart highlights absolute counts per period."))
            else:
                scores.append((0.80, ChartType.BAR,
                    "Short time window → bar chart is clearer than a line with few points."))
                scores.append((0.60, ChartType.LINE,
                    "Line chart still usable for trend direction over a short window."))

        # ── Category distribution rules ───────────────────────────────
        if p.has_categories:
            max_card = max(p.cardinality.values(), default=0) if p.cardinality else 0

            if max_card <= 6:
                scores.append((0.92, ChartType.PIE,
                    f"Low cardinality ({max_card} categories) → pie chart shows part-to-whole clearly."))
                scores.append((0.82, ChartType.BAR,
                    "Bar chart is an alternative for precise comparison across few categories."))
            elif max_card <= 15:
                scores.append((0.88, ChartType.BAR,
                    f"Moderate cardinality ({max_card} categories) → bar chart preserves readability."))
                scores.append((0.55, ChartType.TREEMAP,
                    "Treemap encodes both hierarchy and magnitude for mid-range cardinality."))
            else:
                scores.append((0.85, ChartType.BAR,
                    f"High cardinality ({max_card} categories) → bar chart with top-N filter is clearest."))
                scores.append((0.60, ChartType.TREEMAP,
                    "Treemap can show all categories without truncation via area encoding."))

        # ── Numeric distribution rules ─────────────────────────────────
        if p.has_numeric and not p.has_time_series:
            skew = p.skewness or 0.0
            if abs(skew) > 1.5:
                scores.append((0.90, ChartType.HISTOGRAM,
                    f"High skewness ({skew:.2f}) → histogram exposes the distribution shape."))
                scores.append((0.75, ChartType.BOX,
                    "Box plot highlights median and IQR under skewed distributions."))
            else:
                scores.append((0.82, ChartType.HISTOGRAM,
                    "Near-normal distribution → histogram shows spread and central tendency."))
                scores.append((0.70, ChartType.BOX,
                    "Box plot is a compact alternative for comparing spread across groups."))

        # ── Multi-numeric → correlation heat map ─────────────────────
        if p.n_numeric_cols >= 3:
            scores.append((0.80, ChartType.HEATMAP,
                f"{p.n_numeric_cols} numeric columns → heatmap reveals pairwise correlations."))

        # ── Two-numeric → scatter ─────────────────────────────────────
        if p.n_numeric_cols == 2:
            scores.append((0.85, ChartType.SCATTER,
                "Two numeric variables → scatter plot reveals correlation or clustering."))

        # ── Source-specific boosts ────────────────────────────────────
        scores.extend(self._source_rules(source, p))

        # Fallback
        if not scores:
            scores.append((0.5, ChartType.BAR, "Default: bar chart for unknown data shape."))

        return scores

    def _source_rules(
        self, source: ChartSource, p: DataProfile
    ) -> List[Tuple[float, ChartType, str]]:
        """Domain-specific scoring adjustments per data source."""
        extras: List[Tuple[float, ChartType, str]] = []

        if source == ChartSource.INCIDENTS:
            extras.append((0.72, ChartType.BAR,
                "Incidents by type → bar chart lets staff compare frequency per category."))
            if p.has_time_series:
                extras.append((0.88, ChartType.LINE,
                    "Incident timeline → line chart shows whether events are increasing."))

        elif source == ChartSource.ATTENDANCE:
            if p.has_time_series:
                extras.append((0.90, ChartType.LINE,
                    "Daily attendance rate over time → line chart tracks trends clearly."))
            extras.append((0.68, ChartType.PIE,
                "Present/Absent/Late breakdown → pie chart shows proportion at a glance."))
            extras.append((0.80, ChartType.BAR,
                "Attendance by class or kindergarten → grouped bar enables comparison."))

        elif source == ChartSource.DAILY_REPORTS:
            extras.append((0.85, ChartType.BAR,
                "Mood distribution → bar chart shows frequencies of each mood category."))
            extras.append((0.72, ChartType.PIE,
                "Mood share → pie chart gives an at-a-glance wellbeing indicator."))
            if p.has_time_series:
                extras.append((0.78, ChartType.LINE,
                    "Mood trend over time → line chart reveals wellbeing changes."))

        elif source == ChartSource.ENROLLMENTS:
            if p.has_time_series:
                extras.append((0.88, ChartType.LINE,
                    "Enrollment volume over time → line chart highlights growth or decline."))
            extras.append((0.75, ChartType.FUNNEL,
                "Enrollment stages → funnel chart shows conversion at each step."))
            extras.append((0.70, ChartType.BAR,
                "Applications per kindergarten → bar chart enables site comparison."))

        elif source == ChartSource.KINDERGARTENS:
            extras.append((0.80, ChartType.BAR,
                "Capacity vs. enrollment per kindergarten → grouped bar shows utilization."))
            extras.append((0.65, ChartType.SCATTER,
                "Capacity vs. enrollment scatter reveals under/over-utilized sites."))

        return extras

    def _default_title(self, source: ChartSource, ctype: ChartType) -> str:
        source_label = {
            ChartSource.INCIDENTS: "Incidents",
            ChartSource.ATTENDANCE: "Attendance",
            ChartSource.DAILY_REPORTS: "Daily Reports",
            ChartSource.ENROLLMENTS: "Enrollments",
            ChartSource.KINDERGARTENS: "Kindergartens",
        }.get(source, source.value.title())
        type_label = {
            ChartType.LINE: "Trend Over Time",
            ChartType.BAR: "Breakdown",
            ChartType.SCATTER: "Correlation",
            ChartType.PIE: "Distribution",
            ChartType.HISTOGRAM: "Frequency Distribution",
            ChartType.BOX: "Statistical Spread",
            ChartType.HEATMAP: "Correlation Heatmap",
            ChartType.FUNNEL: "Funnel",
            ChartType.TREEMAP: "Treemap",
        }.get(ctype, ctype.value.title())
        return f"{source_label} — {type_label}"
