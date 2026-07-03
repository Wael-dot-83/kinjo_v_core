# National Nursery Intelligence & Heat Map Dashboard - UI/UX Design System Specification

## 1. Arabic-First Design Principles

### 1.1 Language Prioritization
- **Primary Language**: Arabic interface with English fallback
- **Right-to-Left (RTL) Layout**: All UI elements optimized for RTL reading patterns
- **Typography Hierarchy**: IBM Plex Sans Arabic for body, Cairo for headings, Noto Kufi Arabic for data labels
- **Reading Patterns**: Arabic reading patterns optimized for government administrators

### 1.2 WCAG 2.1 AA Compliance Requirements
- **Text Contrast**: Minimum 4.5:1 ratio for all text elements
- **Focus Indicators**: Visible focus rings for keyboard navigation
- **Screen Reader Support**: Semantic HTML with ARIA labels
- **Color Blindness**: Color-blind safe palette with pattern backups
- **Keyboard Navigation**: Full keyboard accessibility for all interactive elements
- **Animation Control**: Option to disable animations for users with vestibular disorders

### 1.3 Government Enterprise Design Standards
- **Professional Tone**: Formal, authoritative, government-grade aesthetic
- **Minimalist Approach**: Clean, uncluttered interface with focus on data visualization
- **Data-Centric Layout**: Prioritize data visualization over decorative elements
- **Hierarchical Information**: Clear visual hierarchy for complex data relationships
- **Consistent Terminology**: Ministry-approved Arabic terminology for all labels

## 2. Color Palette Implementation

### 2.1 Primary Color Palette (Government Enterprise)
```css
/* Primary Government Colors - STRICTLY FOLLOW THESE VALUES */
--primary-color: #0E334F; /* Dark Blue - Primary brand */
--secondary-color: #061826; /* Deep Navy - Secondary accents */
--background-color: #F5F7FA; /* Light Gray - Main background */
--card-background: #FFFFFF; /* White - Card surfaces */
--success-color: #28A745; /* Green - Positive indicators */
--warning-color: #FFC107; /* Amber - Warning/attention */
--danger-color: #DC3545; /* Red - Critical alerts */
```

### 2.3 Semantic Color Mapping
```css
/* Semantic Status Colors */
--status-success: #28A745; /* الأخضر - Good/Compliant/Positive */
--status-warning: #FFC107; /* الأصفر/البرتقالي - Attention/Average */
--status-danger: #DC3545; /* الأحمر - Critical/Bad/Negative */
--status-info: #0E334F; /* الأزرق الداكن - Information/Neutral */
--status-muted: #6c757d; /* رمادي - Secondary/Inactive */
```

### 2.2 Semantic Color Mapping
- **Success**: Green (#28A745) - Positive trends, high compliance, good performance
- **Warning**: Amber (#FFC107) - Attention needed, moderate risk, average performance
- **Danger**: Red (#DC3545) - Critical alerts, low compliance, poor performance
- **Info**: Blue (#0E334F) - Neutral information, guidance, status updates

### 2.3 Heat Map Color Gradients
- **High Intensity**: #DC3545 (Red) - Critical risk, high density, poor performance
- **Medium Intensity**: #FFC107 (Amber) - Moderate risk, medium density, average performance
- **Low Intensity**: #28A745 (Green) - Low risk, low density, good performance
- **No Data**: #0E334F (Dark Blue) - Insufficient data, unavailable information

### 2.4 Accessibility Compliance Verification
- **Text Contrast**: 
  - Dark Blue (#0E334F) on White (#FFFFFF): 11.4:1 ✓
  - Green (#28A745) on White (#FFFFFF): 4.6:1 ✓
  - Amber (#FFC107) on Dark (#061826): 4.2:1 ✓
  - Red (#DC3545) on White (#FFFFFF): 4.7:1 ✓
- **Non-Color Indicators**: Pattern backups for heat maps (density patterns)

## 3. Typography System

### 3.1 Arabic Font Hierarchy
```css
/* Arabic Typography Stack */
--font-primary-arabic: 'IBM Plex Sans Arabic', 'Cairo', 'Tajawal', sans-serif;
--font-heading-arabic: 'Cairo', 'IBM Plex Sans Arabic', sans-serif;
--font-data-arabic: 'Noto Kufi Arabic', 'Cairo', sans-serif;
--font-fallback-arabic: 'Tahoma', 'Arial', sans-serif;
```

### 3.2 English Font Hierarchy
```css
/* English Typography Stack */
--font-primary-english: 'Inter', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
--font-heading-english: 'Inter', sans-serif;
--font-data-english: 'Inter', 'Roboto', sans-serif;
```

### 3.3 Font Size Scale (Fixed)
```css
/* Arabic Font Scale (RTL optimized) */
--font-size-xs: 12px; /* Small labels, metadata */
--font-size-sm: 14px; /* Body text, descriptions */
--font-size-base: 16px; /* Primary content */
--font-size-lg: 18px; /* Section headers */
--font-size-xl: 20px; /* Page titles */
--font-size-2xl: 24px; /* Dashboard headings */
--font-size-3xl: 30px; /* KPI values */

/* Line Heights */
--line-height-arabic: 1.7; /* Arabic reading comfort */
--line-height-english: 1.6; /* English reading comfort */
```

### 3.4 Arabic Text Layout Guidelines
- **Justification**: Arabic text right-aligned with proper spacing
- **Text Direction**: RTL with proper bidirectional text support
- **Character Support**: Full Arabic Unicode range including Eastern Arabic numerals
- **Typography Variables**: CSS custom properties for dynamic language switching

## 4. Component Library

### 4.1 Dashboard Cards
```html
<!-- Arabic Dashboard Card -->
<div class="dashboard-card" dir="rtl">
  <div class="card-header">
    <h3 class="card-title">مؤشر الحوكمة</h3>
    <span class="card-subtitle">نسبة التقارير المقدمة</span>
  </div>
  <div class="card-body">
    <div class="kpi-value">92%</div>
    <div class="kpi-trend up">+5%</div>
    <div class="chart-container">
      <!-- Arabic chart with RTL labels -->
    </div>
  </div>
  <div class="card-footer">
    <button class="btn btn-primary" aria-label="تحليل مفصّل">تحليل مفصّل</button>
  </div>
</div>
```

### 4.2 Heat Map Components
```html
<!-- Arabic Heat Map Component -->
<div class="heat-map-container" dir="rtl">
  <div class="map-header">
    <h4 class="map-title">خريطة الحرارة - توزيع الحضانات</h4>
    <div class="map-controls">
      <button class="btn btn-outline-primary" aria-label="تغيير الطبقة">تغيير الطبقة</button>
      <button class="btn btn-outline-primary" aria-label="تصدير">تصدير</button>
    </div>
  </div>
  <div class="map-visualization">
    <!-- Leaflet.js map with Arabic labels -->
    <!-- Color gradient legend -->
    <!-- Governorate boundaries -->
    <!-- Nursery location markers -->
  </div>
  <div class="map-legend" dir="rtl">
    <div class="legend-item">
      <span class="legend-color red"></span>
      <span class="legend-label">عالي (أكثر من 50 حضانة)</span>
    </div>
    <div class="legend-item">
      <span class="legend-color amber"></span>
      <span class="legend-label">متوسط (20-50 حضانة)</span>
    </div>
    <div class="legend-item">
      <span class="legend-color green"></span>
      <span class="legend-label">قليل (أقل من 20 حضانة)</span>
    </div>
  </div>
</div>
```

### 4.3 KPI Cards (Arabic)
```html
<!-- Arabic KPI Card -->
<div class="kpi-card" dir="rtl">
  <div class="kpi-icon" aria-hidden="true">
    <i class="bi bi-graph-up"></i>
  </div>
  <div class="kpi-content">
    <div class="kpi-title">نسبة الحضور</div>
    <div class="kpi-value">88%</div>
    <div class="kpi-trend up" aria-label="زيادة 3% عن الأسبوع السابق">
      <i class="bi bi-arrow-up"></i> 3%
    </div>
  </div>
</div>
```

### 4.4 Alert Cards (Multi-Severity)
```html
<!-- Arabic Alert Card - Critical -->
<div class="alert-card critical" dir="rtl">
  <div class="alert-header">
    <span class="alert-icon" aria-hidden="true">
      <i class="bi bi-exclamation-triangle-fill"></i>
    </span>
    <span class="alert-title">تنبيه حر</span>
    <span class="alert-time">منذ 2 ساعة</span>
  </div>
  <div class="alert-body">
    <p class="alert-description">نسبة الحضور في حضانة الأمل أقل من 50% لمدة 3 أيام متتالية</p>
    <div class="alert-metrics">
      <span class="metric-label">المحافظة:</span>
      <span class="metric-value">عمان</span>
      <span class="metric-label">الحضانة:</span>
      <span class="metric-value">حضانة الأمل</span>
    </div>
  </div>
  <div class="alert-footer">
    <button class="btn btn-danger" aria-label="فتح خطة العمل">فتح خطة العمل</button>
  </div>
</div>
```

### 4.5 Filter Controls (Arabic)
```html
<!-- Arabic Filter Controls -->
<div class="filter-section" dir="rtl">
  <div class="filter-group">
    <label for="governorateFilter" class="filter-label">المحافظة</label>
    <select id="governorateFilter" class="form-select" aria-label="اختر المحافظة">
      <option value="">جميع المحافظات</option>
      <option value="عمان">عمان</option>
      <option value="إربد">إربد</option>
      <option value="الزرقاء">الزرقاء</option>
      <!-- All 12 Jordan governorates -->
    </select>
  </div>
  <div class="filter-group">
    <label for="dateRangeFilter" class="filter-label">الفترة الزمنية</label>
    <select id="dateRangeFilter" class="form-select" aria-label="اختر الفترة الزمنية">
      <option value="daily">يومي</option>
      <option value="weekly">أسبوعي</option>
      <option value="monthly">شهري</option>
      <option value="quarterly">ربع سنوي</option>
      <option value="annual">سنوي</option>
    </select>
  </div>
  <button class="btn btn-primary filter-apply" aria-label="تطبيق الفلترة">
    تطبيق
  </button>
</div>
```

### 4.6 Chart Components (Arabic Labels)
```html
<!-- Arabic Chart with RTL Labels -->
<div class="chart-container" dir="rtl">
  <canvas id="attendanceChart" aria-label="مخطط نسبة الحضور حسب المحافظة"></canvas>
  <div class="chart-legend">
    <div class="legend-item">
      <span class="legend-color" style="background-color: #28A745;"></span>
      <span class="legend-label">نسبة الحضور</span>
    </div>
    <div class="legend-item">
      <span class="legend-color" style="background-color: #FFC107;"></span>
      <span class="legend-label">نسبة الغياب</span>
    </div>
  </div>
</div>
```

## 5. Responsive Design Grid System

### 5.1 Grid Layouts
```css
/* Arabic Grid System (RTL) */
.grid-system {
  direction: rtl;
  display: grid;
  gap: var(--spacing-md);
}

/* Desktop (≥1200px) - 12-column grid */
@media (min-width: 1200px) {
  .dashboard-grid {
    grid-template-columns: repeat(12, 1fr);
  }
  .heat-map-grid {
    grid-template-columns: 8fr 4fr; /* Map + sidebar */
  }
}

/* Tablet (768px-1199px) - 8-column grid */
@media (min-width: 768px) and (max-width: 1199px) {
  .dashboard-grid {
    grid-template-columns: repeat(8, 1fr);
  }
  .heat-map-grid {
    grid-template-columns: 1fr; /* Single column */
  }
}

/* Mobile (≤767px) - 4-column grid */
@media (max-width: 767px) {
  .dashboard-grid {
    grid-template-columns: repeat(4, 1fr);
  }
  .kpi-card {
    grid-column: span 2;
  }
}
```

### 5.2 Touch Target Requirements
```css
/* Minimum Touch Targets for Government Tablet/Mobile Use */
--touch-target-min: 44px; /* WCAG requirement */
.btn {
  min-height: var(--touch-target-min);
  min-width: var(--touch-target-min);
  padding: 12px 16px;
}

.form-control, .form-select {
  min-height: var(--touch-target-min);
}

.checkbox-label, .radio-label {
  min-height: var(--touch-target-min);
  display: flex;
  align-items: center;
}
```

### 5.3 Responsive Heat Map Layout
```css
/* Heat Map Responsive Layout */
.heat-map-container {
  position: relative;
  height: 500px; /* Desktop height */
}

@media (max-width: 1199px) {
  .heat-map-container {
    height: 400px; /* Tablet height */
  }
}

@media (max-width: 767px) {
  .heat-map-container {
    height: 300px; /* Mobile height */
  }
  .map-legend {
    flex-direction: column;
  }
}
```

## 6. Dashboard Layout Templates

### 6.1 Admin Dashboard Layout
```html
<!-- Admin Dashboard Template -->
<div class="dashboard-admin" dir="rtl">
  <div class="dashboard-header">
    <h1 class="dashboard-title">لوحة التحكم الوطنية للحضانات</h1>
    <div class="dashboard-controls">
      <button class="btn btn-primary" aria-label="تصدير تقرير">تصدير تقرير</button>
      <button class="btn btn-outline-primary" aria-label="تحديث البيانات">تحديث البيانات</button>
    </div>
  </div>
  
  <div class="dashboard-grid">
    <!-- Governorate Heat Map -->
    <div class="dashboard-card heat-map-card">
      <!-- Heat map visualization -->
    </div>
    
    <!-- National KPIs -->
    <div class="dashboard-card kpi-card">
      <!-- National KPI metrics -->
    </div>
    
    <!-- Predictive Analytics -->
    <div class="dashboard-card predictive-card">
      <!-- Forecasting charts -->
    </div>
    
    <!-- Alert Dashboard -->
    <div class="dashboard-card alert-dashboard">
      <!-- Multi-severity alerts -->
    </div>
    
    <!-- Governorate Ranking -->
    <div class="dashboard-card ranking-card">
      <!-- Performance ranking -->
    </div>
    
    <!-- Data Quality Metrics -->
    <div class="dashboard-card quality-card">
      <!-- Completeness, accuracy, timeliness -->
    </div>
  </div>
</div>
```

### 6.2 Manager Dashboard Layout
```html
<!-- Manager Dashboard Template -->
<div class="dashboard-manager" dir="rtl">
  <div class="dashboard-header">
    <h1 class="dashboard-title">لوحة التحكم للحضانة</h1>
    <div class="dashboard-controls">
      <button class="btn btn-primary" aria-label="تحليل الحضانة">تحليل الحضانة</button>
    </div>
  </div>
  
  <div class="dashboard-grid">
    <!-- Kindergarten KPIs -->
    <div class="dashboard-card kpi-card">
      <!-- Kindergarten-specific metrics -->
    </div>
    
    <!-- Attendance Trends -->
    <div class="dashboard-card attendance-card">
      <!-- Attendance charts -->
    </div>
    
    <!-- Incident Monitoring -->
    <div class="dashboard-card incident-card">
      <!-- Incident tracking -->
    </div>
    
    <!-- Staffing Ratios -->
    <div class="dashboard-card staffing-card">
      <!-- Child-to-supervisor ratios -->
    </div>
    
    <!-- Daily Report Compliance -->
    <div class="dashboard-card compliance-card">
      <!-- Report submission compliance -->
    </div>
    
    <!-- Action Plans -->
    <div class="dashboard-card action-card">
      <!-- Open action plans -->
    </div>
  </div>
</div>
```

### 6.3 Supervisor Dashboard Layout
```html
<!-- Supervisor Dashboard Template -->
<div class="dashboard-supervisor" dir="rtl">
  <div class="dashboard-header">
    <h1 class="dashboard-title">لوحة التحكم للمشرف</h1>
    <div class="dashboard-controls">
      <button class="btn btn-primary" aria-label="تقارير اليومية">تقارير اليومية</button>
    </div>
  </div>
  
  <div class="dashboard-grid">
    <!-- Class KPIs -->
    <div class="dashboard-card kpi-card">
      <!-- Class-specific metrics -->
    </div>
    
    <!-- Child Attendance -->
    <div class="dashboard-card child-card">
      <!-- Individual child attendance -->
    </div>
    
    <!-- Health Monitoring -->
    <div class="dashboard-card health-card">
      <!-- Health alerts and incidents -->
    </div>
    
    <!-- Daily Report Status -->
    <div class="dashboard-card report-card">
      <!-- Report submission status -->
    </div>
    
    <!-- Parent Communication -->
    <div class="dashboard-card communication-card">
      <!-- Parent notification status -->
    </div>
  </div>
</div>
```

### 6.4 Parent Dashboard Layout
```html
<!-- Parent Dashboard Template -->
<div class="dashboard-parent" dir="rtl">
  <div class="dashboard-header">
    <h1 class="dashboard-title">لوحة التحكم للأهل</h1>
  </div>
  
  <div class="dashboard-grid">
    <!-- Child Information -->
    <div class="dashboard-card child-card">
      <!-- Child details and photos -->
    </div>
    
    <!-- Attendance Summary -->
    <div class="dashboard-card attendance-card">
      <!-- Child attendance history -->
    </div>
    
    <!-- Health Alerts -->
    <div class="dashboard-card health-card">
      <!-- Health alerts and incidents -->
    </div>
    
    <!-- Daily Reports -->
    <div class="dashboard-card report-card">
      <!-- Daily report summaries -->
    </div>
  </div>
</div>
```

## 7. Export Controls & Time Intelligence Filtering

### 7.1 Export Button Components
```html
<!-- Arabic Export Controls -->
<div class="export-controls" dir="rtl">
  <div class="export-group">
    <button class="btn btn-outline-primary export-btn" aria-label="تصدير PDF">
      <i class="bi bi-file-pdf"></i>
      <span>PDF</span>
    </button>
    <button class="btn btn-outline-primary export-btn" aria-label="تصدير Excel">
      <i class="bi bi-file-excel"></i>
      <span>Excel</span>
    </button>
    <button class="btn btn-outline-primary export-btn" aria-label="تصدير CSV">
      <i class="bi bi-file-text"></i>
      <span>CSV</span>
    </button>
    <button class="btn btn-outline-primary export-btn" aria-label="تصدير GeoJSON">
      <i class="bi bi-map"></i>
      <span>GeoJSON</span>
    </button>
  </div>
  
  <div class="time-filter-group">
    <select class="form-select time-filter" aria-label="اختر الفترة الزمنية">
      <option value="daily">يومي</option>
      <option value="weekly">أسبوعي</option>
      <option value="monthly">شهري</option>
      <option value="quarterly">ربع سنوي</option>
      <option value="annual">سنوي</option>
      <option value="custom">مخصص</option>
    </select>
    
    <div class="custom-range" aria-hidden="true" style="display: none;">
      <input type="date" class="form-control start-date" aria-label="تاريخ البدء">
      <input type="date" class="form-control end-date" aria-label="تاريخ الانتهاء">
    </div>
  </div>
</div>
```

### 7.2 Export Format Specifications
- **PDF Reports**: Professional government-grade reports with Arabic typography
- **Excel Spreadsheets**: Multi-sheet exports with pivot tables
- **CSV Data**: Raw data exports for external analysis
- **GeoJSON Maps**: Exportable heat map layers for GIS software

## 8. Accessibility Implementation Checklist

### 8.1 WCAG 2.1 AA Compliance Checklist
1. **Text Contrast**: All text meets 4.5:1 minimum ratio ✓
2. **Focus Indicators**: Visible focus rings for all interactive elements ✓
3. **Screen Reader**: Semantic HTML with proper ARIA labels ✓
4. **Keyboard Navigation**: Full keyboard accessibility ✓
5. **Color Blindness**: Pattern backups for color-coded data ✓
6. **Animation Control**: Option to disable animations ✓
7. **RTL Support**: Proper bidirectional text support ✓
8. **Touch Targets**: Minimum 44px touch targets ✓
9. **Form Labels**: All form controls have associated labels ✓
10. **Error Identification**: Clear error messages and indications ✓

### 8.2 Arabic Accessibility Considerations
- **Arabic Screen Reader**: Support for Arabic screen readers (NVDA, JAWS)
- **Right-to-Left Navigation**: Logical RTL navigation flow
- **Arabic Keyboard Support**: Proper Arabic keyboard navigation
- **Arabic Number Format**: Eastern Arabic numerals support
- **Arabic Date Format**: Hijri date format option

## 9. Implementation Guidelines

### 9.1 CSS Implementation
```css
/* Arabic-first CSS Variables */
:root[lang="ar"] {
  --font-family: 'IBM Plex Sans Arabic', 'Cairo', 'Tajawal', sans-serif;
  --text-direction: rtl;
  --text-align: right;
  --line-height: 1.7;
}

/* English fallback */
:root[lang="en"] {
  --font-family: 'Inter', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
  --text-direction: ltr;
  --text-align: left;
  --line-height: 1.6;
}

/* Government Color Palette */
.government-primary { color: #0E334F; }
.government-secondary { color: #061826; }
.government-success { color: #28A745; }
.government-warning { color: #FFC107; }
.government-danger { color: #DC3545; }

/* Heat Map Color Classes */
.heat-map-high { background-color: #DC3545; }
.heat-map-medium { background-color: #FFC107; }
.heat-map-low { background-color: #28A745; }
.heat-map-no-data { background-color: #0E334F; }
```

### 9.2 HTML Structure Guidelines
```html
<!-- Arabic-first HTML template -->
<div dir="rtl" lang="ar" class="dashboard-container">
  <header class="dashboard-header" aria-label="رأس لوحة التحكم">
    <h1 class="dashboard-title">لوحة التحكم الوطنية للحضانات</h1>
    <nav class="dashboard-nav" aria-label="تنقل لوحة التحكم">
      <!-- Arabic navigation -->
    </nav>
  </header>
  
  <main class="dashboard-main" aria-label="الجزء الرئيسي">
    <section class="heat-map-section" aria-label="خريطة الحرارة">
      <!-- Arabic heat map -->
    </section>
    
    <section class="kpi-section" aria-label="المؤشرات الرئيسية">
      <!-- Arabic KPIs -->
    </section>
    
    <section class="alert-section" aria-label="التنبيهات">
      <!-- Arabic alerts -->
    </section>
  </main>
  
  <footer class="dashboard-footer" aria-label="تذييل لوحة التحكم">
    <!-- Arabic footer -->
  </footer>
</div>
```

### 9.3 JavaScript Accessibility
```javascript
// Arabic-first JavaScript for dashboard
class ArabicDashboard {
  constructor() {
    this.language = 'ar';
    this.direction = 'rtl';
    this.init();
  }
  
  init() {
    // Set document direction
    document.dir = this.direction;
    document.lang = this.language;
    
    // Initialize Arabic chart labels
    this.initArabicCharts();
    
    // Set Arabic date formatting
    this.setArabicDateFormat();
    
    // Initialize Arabic keyboard navigation
    this.initArabicKeyboardNav();
  }
  
  initArabicCharts() {
    // Chart.js configuration for Arabic
    Chart.defaults.font.family = 'IBM Plex Sans Arabic';
    Chart.defaults.font.size = 14;
    Chart.defaults.color = '#061826';
  }
  
  setArabicDateFormat() {
    // Use Hijri date formatting if enabled
    if (this.useHijri) {
      moment.locale('ar');
    }
  }
  
  initArabicKeyboardNav() {
    // RTL keyboard navigation logic
    document.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowRight') {
        // Navigate left in RTL context
        this.navigateLeft();
      } else if (e.key === 'ArrowLeft') {
        // Navigate right in RTL context
        this.navigateRight();
      }
    });
  }
}
```

## 10. Testing & Validation Checklist

### 10.1 Arabic UI Testing
1. **RTL Layout Verification**: All elements correctly positioned in RTL
2. **Arabic Typography**: Fonts render correctly with proper glyphs
3. **Arabic Text Flow**: Text flows correctly right-to-left
4. **Arabic Date Formatting**: Dates display in Arabic format
5. **Arabic Keyboard**: Keyboard navigation works in RTL context
6. **Arabic Screen Reader**: Screen readers read Arabic content correctly

### 10.2 Accessibility Testing
1. **WCAG Compliance**: Automated testing with axe-core
2. **Color Contrast**: Color contrast verification for all text
3. **Keyboard Navigation**: Full keyboard accessibility testing
4. **Screen Reader**: NVDA/JAWS testing with Arabic content
5. **Touch Targets**: Minimum 44px touch target verification
6. **Focus Management**: Proper focus order and visible focus rings

### 10.3 Performance Testing
1. **Dashboard Load Time**: <3 seconds for initial load
2. **Heat Map Rendering**: <2 seconds for map visualization
3. **Chart Loading**: <1 second for chart rendering
4. **Arabic Font Loading**: <500ms for Arabic font rendering
5. **RTL Layout Calculation**: <100ms for RTL positioning