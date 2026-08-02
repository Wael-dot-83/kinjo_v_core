"""Chart colour utilities for the KinJo charting subsystem.

Provides a harmonious 12-colour palette, colour assignment, and Plotly-compatible
sequential and diverging colour scales.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Palette — 12 curated colours that work on both light and dark backgrounds
# ---------------------------------------------------------------------------

PALETTE: list[str] = [
    "#4C6EF5",  # blue
    "#F76707",  # orange
    "#2F9E44",  # green
    "#E03131",  # red
    "#7048E8",  # violet
    "#1098AD",  # cyan
    "#F59F00",  # yellow
    "#D6336C",  # pink
    "#0CA678",  # teal
    "#AE3EC9",  # grape
    "#5C7CFA",  # indigo
    "#94D82D",  # lime
]

assert len(PALETTE) == 12, "PALETTE must contain exactly 12 colours"


def get_color(index: int) -> str:
    """Return the palette colour at *index*, wrapping around if needed."""
    return PALETTE[index % len(PALETTE)]


def assign_colors(categories: list[str]) -> dict[str, str]:
    """Return a deterministic {category: colour} mapping.

    The mapping is stable as long as *categories* is the same sequence —
    colours are assigned in order, wrapping when the palette is exhausted.
    """
    return {cat: get_color(i) for i, cat in enumerate(categories)}


# ---------------------------------------------------------------------------
# Colour scales (Plotly format: list of [position, colour] pairs)
# ---------------------------------------------------------------------------

def sequential_colorscale() -> list[list[float | str]]:
    """Return a sequential blue colour scale for choropleth / heatmap charts."""
    return [
        [0.0,  "#EDF2FF"],
        [0.2,  "#BAC8FF"],
        [0.4,  "#748FFC"],
        [0.6,  "#4C6EF5"],
        [0.8,  "#3B5BDB"],
        [1.0,  "#2C44BD"],
    ]


def diverging_colorscale() -> list[list[float | str]]:
    """Return a diverging red-white-blue scale with a 0.5 midpoint."""
    return [
        [0.0,  "#E03131"],
        [0.25, "#FF8787"],
        [0.5,  "#FFFFFF"],
        [0.75, "#74C0FC"],
        [1.0,  "#1971C2"],
    ]
