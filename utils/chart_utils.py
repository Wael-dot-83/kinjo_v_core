from schemas.chart_dto import ChartConfig, ChartDataset
from typing import List, Dict, Optional

def create_chart_config(
    chart_type: str,
    labels: List[str],
    dataset_label_en: str,
    dataset_label_ar: str,
    data: List[float],
    thresholds: Optional[Dict[str, float]] = None,
    colors_dict: Optional[Dict[str, str]] = None
) -> ChartConfig:
    """Helper to standardise chart configuration generation."""
    
    # Default semantic colors if not provided
    if not colors_dict:
        colors_dict = {
            "good": "#2ecc71",
            "warning": "#f1c40f",
            "critical": "#e74c3c"
        }
    
    # Auto-color logic based on typical thresholds if it's a bar/pie and thresholds are given
    bg_colors = []
    if thresholds and chart_type in ['bar', 'pie', 'doughnut']:
        for val in data:
            if val >= thresholds.get("warning", float('inf')):
                if val >= thresholds.get("critical", float('inf')):
                    bg_colors.append(colors_dict["critical"])
                else:
                    bg_colors.append(colors_dict["warning"])
            else:
                bg_colors.append(colors_dict["good"])
    else:
        # Just use a primary color if no thresholds
        bg_colors = ["#3498db"] * len(data)

    dataset = ChartDataset(
        label={"en": dataset_label_en, "ar": dataset_label_ar},
        data=data,
        backgroundColor=bg_colors,
        borderColor=bg_colors
    )
    
    return ChartConfig(
        type=chart_type,
        labels=labels,
        datasets=[dataset],
        thresholds=thresholds,
        colors=colors_dict
    )
