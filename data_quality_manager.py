"""
Data quality manager for KinJo analytics: anomaly detection and consistency checks
"""
from typing import Dict, Any
import numpy as np

class DataQualityManager:
    @staticmethod
    def detect_anomalies(series: list, threshold: float = 1.5) -> list:
        """Return indices of values > threshold std dev from mean"""
        if not series:
            return []
        arr = np.array(series)
        mean = arr.mean()
        std = arr.std()
        if std == 0:
            return []
        anomalies = [i for i, v in enumerate(arr) if abs(v - mean) > threshold * std]
        return anomalies

    @staticmethod
    def check_consistency(series: list) -> bool:
        """Check if series is non-decreasing (example rule)"""
        return all(x <= y for x, y in zip(series, series[1:]))
