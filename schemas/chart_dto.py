from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Union

class ChartDataset(BaseModel):
    label: Dict[str, str] = Field(description="Localized label map (en/ar)")
    # Allow None for sparse multi-series line charts (e.g., forecast + historical)
    data: List[Optional[float]] = Field(description="Data points (None = gap in series)")
    backgroundColor: Optional[List[str]] = None
    borderColor: Optional[List[str]] = None
    
class ChartConfig(BaseModel):
    type: str = Field(description="Chart type (e.g., bar, line, pie, gauge, heatmap, radar, timeline)")
    labels: List[str] = Field(description="X-axis or segment labels")
    datasets: List[ChartDataset]
    thresholds: Optional[Dict[str, float]] = None
    colors: Optional[Dict[str, str]] = None
    
class MetricResponse(BaseModel):
    metric: str
    value: Any
    chart: ChartConfig
    locale: str = "en"
    
class LayerMetricsResponse(BaseModel):
    layer: str
    metrics: List[MetricResponse]
    locale: str
