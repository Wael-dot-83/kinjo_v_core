from typing import List

def calculate_gini(values: List[float]) -> float:
    """Calculate Gini coefficient."""
    if not values:
        return 0.0
    values = sorted(values)
    n = len(values)
    sum_vals = sum(values)
    if sum_vals == 0:
        return 0.0
    coef = 2.0 * sum((i + 1) * val for i, val in enumerate(values)) / (n * sum_vals) - (n + 1.0) / n
    return round(coef, 4)

def calculate_variance(values: List[float]) -> float:
    """Calculate population variance."""
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    var = sum((x - mean) ** 2 for x in values) / len(values)
    return round(var, 4)

def compute_z_scores(values: List[float]) -> List[float]:
    """Calculate Z-scores for a list of values."""
    if not values or len(values) < 2:
        return [0.0] * len(values)
    mean = sum(values) / len(values)
    var = sum((x - mean) ** 2 for x in values) / len(values)
    std_dev = var ** 0.5
    if std_dev == 0:
        return [0.0] * len(values)
    return [round((x - mean) / std_dev, 4) for x in values]
