"""
Correlation analytics for KinJo: deterministic baseline and plugin interface
"""
from typing import Dict, Any, Protocol
import numpy as np

class CorrelationAnalyticsPlugin(Protocol):
    def compute(self, data: Dict[str, Any]) -> float:
        ...

class BaselinePearsonCorrelationPlugin:
    """Deterministic baseline: Pearson correlation between two series"""
    def compute(self, data: Dict[str, Any]) -> float:
        x = np.array(data["x"])
        y = np.array(data["y"])
        if len(x) < 2 or len(y) < 2:
            return 0.0
        corr = np.corrcoef(x, y)[0, 1]
        return float(corr)

CORRELATION_PLUGINS = {
    "pearson": BaselinePearsonCorrelationPlugin(),
}

def run_correlation(plugin_name: str, data: Dict[str, Any]) -> float:
    plugin = CORRELATION_PLUGINS.get(plugin_name)
    if not plugin:
        raise ValueError(f"No plugin registered for {plugin_name}")
    return plugin.compute(data)
