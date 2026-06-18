# Geospatial Heat Map Engine Specification

## 1. Heat Map Types Catalog

### 1.1 Nursery Distribution Heat Map
- **Purpose**: Visualize nursery density across Jordan's 12 governorates
- **Data Source**: `kindergartens` table with geographic coordinates
- **Aggregation Level**: Governorate → City → Area
- **Algorithm**: DBSCAN clustering for density detection
- **Color Gradient**: High density (Red) → Low density (Green)

### 1.2 Child Population Heat Map (Age 0-5)
- **Purpose**: Show child population density for early childhood years
- **Data Source**: `children` table filtered by date_of_birth (0-5 years)
- **Aggregation Level**: Governororate → City → Area
- **Algorithm**: Kernel density estimation
- **Color Gradient**: High population (Red) → Low population (Green)

### 1.3 HR Capacity Heat Map
- **Purpose**: Monitor staffing ratios at nursery facilities
- **Data Source**: `users` table (staff) + `children` table (enrolled)
- **Ratio Formula**: Child-to-Supervisor, Child-to-Teacher ratios
- **Aggregation Level**: Governorate → Kindergarten
- **Algorithm**: Staff-to-child ratio calculation with color banding
- **Color Gradient**: Below standard (Red) → Standard compliant (Green)

### 1.4 Attendance Heat Map
- **Purpose**: Track daily attendance rates across regions
- **Data Source**: `attendance_logs` table with geographic join
- **Ratio Formula**: `(PRESENT / Total attendance) × 100`
- **Aggregation Level**: Governorate → City → Kindergarten
- **Algorithm**: Real-time attendance rate calculation
- **Color Gradient**: Low attendance (Red) → High attendance (Green)

### 1.5 Health/Epidemic Monitoring Heat Map
- **Purpose**: Detect health incident clustering and epidemic patterns
- **Data Source**: `incidents` table (health type) + `health_alerts` table
- **Ratio Formula**: Health incidents per 100 child-days
- **Aggregation Level**: Governorate → City → Kindergarten
- **Algorithm**: Spatial clustering with temporal correlation
- **Color Gradient**: High health incidents (Red) → Low health incidents (Green)

### 1.6 Geographic Risk Heat Map
- **Purpose**: Composite risk scoring for each region
- **Weight Distribution**:
  - Attendance rate: 30%
  - Incident frequency: 25%
  - Staff-to-child ratio: 20%
  - Health alert rate: 15%
  - Data completeness: 10%
- **Aggregation Level**: Governorate → City → Area
- **Algorithm**: Weighted composite scoring + z-score normalization
- **Color Gradient**: High risk (Red) → Low risk (Green)

## 2. GIS Data Sources

### 2.1 Governorate Boundary Data
```python
GOVERNORATE_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "id": 1,
                "name_ar": "عمان",
                "name_en": "Amman",
                "population": 2041000,
                "area_km2": 1761.5
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[35.6, 32.0], [36.5, 32.0], ...]]
            }
        },
        # All 12 governorates
    ]
}
```

### 2.2 Nursery Location Points
```python
NURSERY_POINTS_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "kindergarten_id": 1,
                "name_ar": "روضة الأمل",
                "name_en": "Al-Amal Kindergarten",
                "governorate": "عمان",
                "capacity": 150,
                "enrolled": 120
            },
            "geometry": {
                "type": "Point",
                "coordinates": [35.9, 31.9]
            }
        }
    ]
}
```

## 3. Heat Map Generation Pipeline

### 3.1 Data Processing Flow
```python
class HeatMapService:
    def generate_heat_map(
        self,
        heat_map_type: str,
        aggregation_level: str,
        date_range: Tuple[date, date]
    ) -> GeoJSON:
        """
        Generate heat map GeoJSON with intensity gradients.
        Steps:
        1. Fetch raw data from database
        2. Aggregate by geographic level
        3. Calculate intensity values
        4. Apply color banding (Red/Amber/Green)
        5. Return GeoJSON with styling properties
        """
        data = self._fetch_geographic_data(heat_map_type, date_range)
        aggregated = self._aggregate_by_level(data, aggregation_level)
        scored = self._calculate_intensity_scores(aggregated, heat_map_type)
        return self._build_geojson_with_styling(scored)
```

### 3.2 Color Banding Logic
```python
def calculate_color_band(value: float, thresholds: dict) -> str:
    """
    Calculate color band based on value and thresholds.
    Returns: #DC3545 (Red), #FFC107 (Amber), or #28A745 (Green)
    """
    if value >= thresholds["red"]:
        return "#DC3545"
    elif value >= thresholds["amber"]:
        return "#FFC107"
    else:
        return "#28A745"
```

### 3.3 Governorate-Level Aggregation
```python
def aggregate_governorate_metrics(db: Session, metric_type: str) -> Dict[str, float]:
    """Aggregate metrics by governorate for heat map visualization."""
    query = """
    SELECT 
        k.governorate,
        COUNT(DISTINCT k.id) as nursery_count,
        COUNT(DISTINCT c.id) as child_count,
        AVG(ar.attendance_rate) as avg_attendance
    FROM kindergartens k
    LEFT JOIN children c ON c.parent_id IN (
        SELECT u.id FROM users u WHERE u.kindergarten_id = k.id
    )
    LEFT JOIN attendance_rates ar ON ar.kindergarten_id = k.id
    GROUP BY k.governorate
    """
    return dict(db.execute(query).fetchall())
```

## 4. JavaScript Visualization Engine

### 4.1 Leaflet.js Integration
```javascript
class NurseryHeatMap {
    constructor(mapElement, options) {
        this.map = L.map(mapElement);
        this.heatMapLayers = {};
        this.currentLayer = null;
        this.initMap();
        this.loadGovernorateBoundaries();
    }
    
    initMap() {
        // Arabic map tiles with RTL support
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors',
            maxZoom: 18,
            rtl: true
        }).addTo(this.map);
        
        // Set initial view to Jordan
        this.map.setView([31.95, 35.93], 8);
    }
    
    loadHeatMapLayer(heatMapType) {
        fetch(`/api/heat-map/${heatMapType}`)
            .then(response => response.json())
            .then(data => {
                const layer = this.createGeoJsonLayer(data);
                this.heatMapLayers[heatMapType] = layer;
                this.switchLayer(heatMapType);
            });
    }
    
    createGeoJsonLayer(geojsonData) {
        return L.geoJSON(geojsonData, {
            style: (feature) => ({
                fillColor: feature.properties.color,
                weight: 2,
                opacity: 1,
                color: '#061826',
                fillOpacity: 0.7
            }),
            onEachFeature: (feature, layer) => {
                layer.bindTooltip(this.createArabicTooltip(feature));
                layer.on('click', () => this.drillDown(feature));
            }
        });
    }
    
    createArabicTooltip(feature) {
        return `
            <div dir="rtl" style="text-align: right;">
                <strong>${feature.properties.name_ar || feature.properties.name_en}</strong><br>
                القيمة: ${feature.properties.value}<br>
                الفئة: ${feature.properties.category}
            </div>
        `;
    }
}
```

### 4.2 Layer Switching Controls
```javascript
function createLayerControl(heatMapTypes) {
    const controls = L.control({ position: 'topright' });
    
    controls.onAdd = (map) => {
        const div = L.DomUtil.create('div', 'heat-map-controls');
        div.innerHTML = `
            <div dir="rtl" class="layer-selector">
                <select id="heatMapType" class="form-select">
                    <option value="nursery_distribution">توزيع الروضات</option>
                    <option value="child_population">توزع الأطفال (0-5)</option>
                    <option value="hr_capacity">نسب الموظفين</option>
                    <option value="attendance">معدلات الحضور</option>
                    <option value="health_monitoring">الصحة والتطعيمات</option>
                    <option value="geographic_risk">المخاطر الجغرافية</option>
                </select>
            </div>
        `;
        return div;
    };
    
    return controls;
}
```

## 5. Heat Map Styling Specifications

### 5.1 Color Ramp Definitions
```css
/* Heat Map Color Ramps */
.heat-map-high { 
    fill-color: #DC3545; 
    fill-opacity: 0.7; 
}
.heat-map-medium { 
    fill-color: #FFC107; 
    fill-opacity: 0.7; 
}
.heat-map-low { 
    fill-color: #28A745; 
    fill-opacity: 0.7; 
}
.heat-map-no-data { 
    fill-color: #0E334F; 
    fill-opacity: 0.3; 
}
```

### 5.2 Legend Component
```html
<div class="heat-map-legend" dir="rtl">
    <h6>خريطة الحرارة - وسيلة إيضاح</h6>
    <div class="legend-item">
        <span class="legend-color" style="background-color: #DC3545;"></span>
        <span class="legend-label">عالي (أعلى من المتوسط)</span>
    </div>
    <div class="legend-item">
        <span class="legend-color" style="background-color: #FFC107;"></span>
        <span class="legend-label">متوسط (متوسط)</span>
    </div>
    <div class="legend-item">
        <span class="legend-color" style="background-color: #28A745;"></span>
        <span class="legend-label">منخفض (أقل من المتوسط)</span>
    </div>
    <div class="legend-item">
        <span class="legend-color" style="background-color: #0E334F;"></span>
        <span class="legend-label">بدون بيانات</span>
    </div>
</div>
```

## 6. Performance Optimization

### 6.1 Spatial Indexing
- **PostgreSQL GIST Index**: For geographic coordinate queries
- **Redis Geographic Cache**: Cache frequently accessed heat map tiles
- **Pre-aggregated Materialized Views**: Daily rollups for performance

### 6.2 Tile-based Rendering
```python
def generate_heat_map_tiles(
    geojson_data: GeoJSON,
    zoom_levels: List[int] = [6, 7, 8, 9, 10, 11, 12]
) -> Dict[int, List[Tile]]:
    """Generate map tiles for different zoom levels for optimal performance."""
    tiles = {}
    for zoom in zoom_levels:
        tiles[zoom] = generate_tiles_for_zoom(geojson_data, zoom)
    return tiles
```

### 6.3 Caching Strategy
- **Tile Cache**: 24-hour TTL for heat map tiles
- **Data Cache**: 1-hour TTL for aggregated metrics
- **Boundary Cache**: 7-day TTL for governorate boundaries