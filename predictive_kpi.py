"""
Predictive KPI baseline and plugin interface for KinJo analytics
"""
from typing import Dict, Any, Protocol
import numpy as np

class PredictiveKPIPlugin(Protocol):
    def predict(self, data: Dict[str, Any]) -> float:
        ...

class BaselineAttendanceTrendPlugin:
    """Deterministic baseline: linear regression on attendance history"""
    def predict(self, data: Dict[str, Any]) -> float:
        # data: {"dates": [...], "attendance": [...]}
        x = np.arange(len(data["attendance"]))
        y = np.array(data["attendance"])
        if len(x) < 2:
            return float(y[-1]) if len(y) else 0.0
        slope = np.polyfit(x, y, 1)[0]
        return float(slope)

# Example plugin registry for extensibility
PREDICTIVE_KPI_PLUGINS = {
    "attendance_trend": BaselineAttendanceTrendPlugin(),
}

def run_predictive_kpi(plugin_name: str, data: Dict[str, Any]) -> float:
    plugin = PREDICTIVE_KPI_PLUGINS.get(plugin_name)
    if not plugin:
        raise ValueError(f"No plugin registered for {plugin_name}")
    return plugin.predict(data)
