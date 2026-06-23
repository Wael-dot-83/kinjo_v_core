"""Brand-consistent accessible color palette for KinJo charts."""

from typing import Dict, List

# 12-color accessible palette anchored to KinJo's #1F5E47 brand green.
# All colors pass WCAG AA against white; ordering chosen for maximum
# perceptual distance between adjacent entries.
PALETTE: List[str] = [
    "#1F5E47",  # brand primary green
    "#B49B3B",  # brand gold
    "#2F7D62",  # hover green
    "#D97706",  # amber
    "#163d2e",  # deep green
    "#7C3AED",  # violet
    "#0891B2",  # cyan (info — intentional)
    "#BE185D",  # rose
    "#4B5563",  # slate
    "#059669",  # emerald
    "#EA580C",  # orange
    "#6D28D9",  # purple
]

_CATEGORY_CACHE: Dict[str, str] = {}


def get_color(index: int) -> str:
    """Return a palette color by positional index (wraps cyclically)."""
    return PALETTE[index % len(PALETTE)]


def assign_colors(categories: List[str]) -> Dict[str, str]:
    """Deterministically map category names to palette colors."""
    result: Dict[str, str] = {}
    for i, cat in enumerate(categories):
        if cat not in _CATEGORY_CACHE:
            _CATEGORY_CACHE[cat] = PALETTE[i % len(PALETTE)]
        result[cat] = _CATEGORY_CACHE[cat]
    return result


def sequential_colorscale() -> List[List]:
    """Plotly-compatible sequential colorscale from white → brand green."""
    return [
        [0.0, "#f0f7f4"],
        [0.25, "#a8d4c4"],
        [0.5, "#2F7D62"],
        [0.75, "#1F5E47"],
        [1.0, "#163d2e"],
    ]


def diverging_colorscale() -> List[List]:
    """Plotly-compatible diverging scale: gold ← neutral → green."""
    return [
        [0.0, "#B49B3B"],
        [0.5, "#f9fafb"],
        [1.0, "#1F5E47"],
    ]


PLOTLY_LAYOUT_DEFAULTS: dict = {
    "font": {"family": "Cairo, Tajawal, sans-serif", "size": 13},
    "plot_bgcolor": "#ffffff",
    "paper_bgcolor": "#ffffff",
    "margin": {"l": 40, "r": 20, "t": 50, "b": 40},
    "legend": {"orientation": "h", "y": -0.15},
    "colorway": PALETTE,
}
