/**
 * jordan_cesium_map.js — v6
 * Google Maps satellite view for KinJo heatmap admin page.
 * Replaced Cesium 3D globe with Google Maps satellite imagery.
 * All KPI panels, rankings table, and intelligence panel preserved.
 */

// ── Constants ─────────────────────────────────────────────────────────────────
const JORDAN_CENTER   = { lat: 31.0, lng: 36.2 };
const JORDAN_ZOOM     = 7;
const GOVS_GEOJSON    = '/static/data/jordan_governorates.geojson';
const API_MAP_DATA    = '/api/admin/heat-map/data';
const API_GOV_DETAIL  = '/api/admin/heat-map/governorate/';
const API_KG_MAPDATA  = '/api/admin/heat-map/kindergartens/map-data';
const API_GOV_HISTORY = slug => `/api/admin/heat-map/governorate/${slug}/history`;
const API_CITY_DATA   = slug => `/api/admin/heat-map/governorate/${slug}/cities`;
const WS_URL          = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/heatmap`;

// Unavailable indicators return null, never a number. `?? 100` used to make
// "no data" evaluate to 100 - 100 = 0 risk, i.e. the healthiest green on the map:
// children_registration is unavailable by design, so Jordan rendered uniformly
// healthy on that layer. riskHex() paints null in neutral grey instead.
function _indRisk(value) {
  return value == null ? null : 100 - value;
}

const IND_RISK_GETTER = {
  'overall_risk':          g => g.risk_score ?? null,
  'nursery_status':        g => _indRisk(g.main_indicators?.nursery_status),
  'children_registration': g => _indRisk(g.main_indicators?.children_registration),
  'staff_classrooms':      g => _indRisk(g.main_indicators?.staff_classrooms),
  'safety_incidents':      g => _indRisk(g.main_indicators?.safety_incidents),
  'reports_attendance':    g => _indRisk(g.main_indicators?.reports_attendance),
  'tasks_governance':      g => _indRisk(g.main_indicators?.tasks_governance),
};

const IND_LABELS = {
  nursery_status:        { ar: 'حالة الحضانات', color: '#0E334F' },
  children_registration: { ar: 'الأطفال المسجلون',            color: '#28A745' },
  staff_classrooms:      { ar: 'الموظفون والفصول',            color: '#155ECF' },
  safety_incidents:      { ar: 'السلامة والحوادث',            color: '#FFC107' },
  reports_attendance:    { ar: 'التقارير والحضور',            color: '#06B6D4' },
  tasks_governance:      { ar: 'المهام والحوكمة',             color: '#8B5CF6' },
};

const IND_ORDER = [
  'nursery_status', 'children_registration', 'staff_classrooms',
  'safety_incidents', 'reports_attendance', 'tasks_governance',
];

// ── Risk helpers ──────────────────────────────────────────────────────────────
function getRiskLevel(score) {
  if (score < 25) return 'low';
  if (score < 50) return 'medium';
  if (score < 75) return 'high';
  return 'critical';
}
const RISK_UNAVAILABLE_HEX = '#94A3B8'; // neutral grey — matches the backend's
                                        // "unavailable" colour in kindergarten_data.py
function riskHex(score) {
  // Unmeasured data must not be painted as healthy; it gets its own neutral tone.
  if (score == null || Number.isNaN(score)) return RISK_UNAVAILABLE_HEX;
  if (score >= 75) return '#ef4444';
  if (score >= 50) return '#f97316';
  if (score >= 25) return '#f59e0b';
  return '#22c55e';
}
function riskClass(score) { return getRiskLevel(score); }
function riskAr(score) {
  return { low: 'منخفض', medium: 'متوسط', high: 'مرتفع', critical: 'حرج' }[getRiskLevel(score)];
}

// XSS-safe helper for all innerHTML interpolation of server-supplied strings
function esc(value) {
  const d = document.createElement('div');
  d.textContent = String(value ?? '');
  return d.innerHTML;
}

// ── App State ─────────────────────────────────────────────────────────────────
const CsApp = {
  map:               null,   // google.maps.Map
  kgMarkers:         [],     // google.maps.Marker[]
  labelMarkers:      [],     // governorate label Marker[]
  govFeatures:       {},     // slug → google.maps.Data.Feature
  highlightedFeature: null,
  mapData:           null,
  selectedGov:       null,
  selectedCity:      null,
  currentInd:        'overall_risk',
  riskFilter:        'all',
  govOverlayVisible: true,
  satelliteMode:     true,
  ws:                null,
  wsTimer:           null,
  warnings:          [],
  kgLoaded:          false,
  dataLoaded:        false,
  _avgRisk:          0,
  _mouseX:           0,
  _mouseY:           0,
};

// ── Rankings state ────────────────────────────────────────────────────────────
let _rankSort   = { col: 'risk', dir: 'desc' };
let _rankSearch = '';
let _rankSearchTimer = null;

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const ptEl = document.getElementById('pageLoadTime');
  if (ptEl) ptEl.textContent = new Date().toLocaleTimeString('ar-JO');
  ensureMapLoadingState();
  bindUiEvents();
  // initGoogleMap() is called by _gmapsLoaded() once the API script loads
});

function _gmapsLoaded() {
  initGoogleMap().catch(err => {
    console.error('[GMaps] init error:', err);
    showFallback(err.message || 'Failed to initialize map.');
  });
}
window._gmapsLoaded = _gmapsLoaded;

function ensureMapLoadingState() {
  const mapEl = document.getElementById('googleMapContainer');
  if (!mapEl || mapEl.querySelector('.map-loading-state')) return;
  const lang = document.querySelector('.geo-cc')?.getAttribute('lang') || document.documentElement.lang || 'ar';
  const isEnglish = lang === 'en';
  mapEl.insertAdjacentHTML('beforeend', `
    <div class="map-loading-state" role="status" aria-live="polite">
      <div class="map-loading-card">
        <div class="map-loading-spinner" aria-hidden="true"></div>
        <div>
          <div class="map-loading-title">${isEnglish ? 'Loading map' : 'جاري تحميل الخريطة'}</div>
          <div class="map-loading-sub">${isEnglish ? 'Preparing governorate layers and risk indicators.' : 'يتم تجهيز طبقات المحافظات ومؤشرات المخاطر.'}</div>
        </div>
      </div>
    </div>`);
}

// ── Google Maps Initialisation ────────────────────────────────────────────────
async function initGoogleMap() {
  const mapEl = document.getElementById('googleMapContainer');
  if (!mapEl) { showFallback('Map container not found.'); return; }

  const map = new google.maps.Map(mapEl, {
    center:                JORDAN_CENTER,
    zoom:                  JORDAN_ZOOM,
    mapTypeId:             'satellite',
    mapId:                 'kinjo_admin_heatmap',
    mapTypeControl:        false,
    streetViewControl:     false,
    fullscreenControl:     false,
    rotateControl:         false,
    zoomControlOptions:    { position: google.maps.ControlPosition.RIGHT_CENTER },
    gestureHandling:       'greedy',
    tilt:                  0,
  });

  CsApp.map = map;
  mapEl.classList.add('map-ready');

  // Track cursor position for tooltip placement
  mapEl.addEventListener('mousemove', e => {
    CsApp._mouseX = e.clientX;
    CsApp._mouseY = e.clientY;
  });
  mapEl.addEventListener('mouseleave', hideTooltip);

  await loadGovPolygons();
  await fetchMapData();
  startWebSocket();
}

// ── GeoJSON Governorate Polygons ──────────────────────────────────────────────
async function loadGovPolygons() {
  const map = CsApp.map;
  if (!map) return;
  try {
    const res = await fetch(GOVS_GEOJSON);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const geojson = await res.json();
    map.data.addGeoJson(geojson);

    // Base style (updated after KPI data arrives via colorGovPolygons)
    map.data.setStyle(getFeatureStyle);

    map.data.addListener('click', event => {
      const gov = event.feature.getProperty('_gov');
      if (gov) selectGovernorate(gov);
    });

    map.data.addListener('mouseover', event => {
      const gov = event.feature.getProperty('_gov');
      if (gov) {
        map.data.overrideStyle(event.feature, {
          strokeWeight:   3,
          strokeOpacity:  0.95,
          fillOpacity:    0.55,
        });
        showGovTooltip(gov);
      }
    });

    map.data.addListener('mouseout', event => {
      // Revert hover style but keep selection highlight
      if (event.feature !== CsApp.highlightedFeature) {
        map.data.revertStyle(event.feature);
        // Re-apply highlight in case revertStyle cleared it
        if (CsApp.highlightedFeature) {
          map.data.overrideStyle(CsApp.highlightedFeature, HIGHLIGHT_STYLE);
        }
      }
      hideTooltip();
    });

    map.data.addListener('mousemove', event => {
      if (event.domEvent) positionTooltip(event.domEvent.clientX, event.domEvent.clientY);
    });

  } catch (err) {
    console.error('[GMaps] GeoJSON load failed:', err);
    addWarning('تعذر تحميل حدود المحافظات من ملف الخريطة.');
  }
}

const HIGHLIGHT_STYLE = {
  fillColor:    '#ffffff',
  fillOpacity:  0.22,
  strokeColor:  '#ffffff',
  strokeOpacity: 0.95,
  strokeWeight: 3,
};

function getFeatureStyle(feature) {
  if (!CsApp.govOverlayVisible) {
    return { fillOpacity: 0, strokeOpacity: 0, clickable: false };
  }
  const gov = feature.getProperty('_gov');
  if (!gov) {
    return { fillColor: '#2F7D62', fillOpacity: 0.30, strokeColor: '#ffffff', strokeOpacity: 0.45, strokeWeight: 1 };
  }
  const getter = IND_RISK_GETTER[CsApp.currentInd] || IND_RISK_GETTER['overall_risk'];
  const score  = getter(gov);
  return {
    fillColor:    riskHex(score),
    fillOpacity:  0.42,
    strokeColor:  '#ffffff',
    strokeOpacity: 0.55,
    strokeWeight: score >= 50 ? 2 : 1,
    clickable:    true,
  };
}

function updateGovStyles() {
  CsApp.map?.data.setStyle(getFeatureStyle);
  if (CsApp.highlightedFeature) {
    CsApp.map?.data.overrideStyle(CsApp.highlightedFeature, HIGHLIGHT_STYLE);
  }
}

// ── Colour Governorate Polygons ───────────────────────────────────────────────
// GeoJSON has exactly: GOVERNORATE_A (English), GOVERNORATE_AR (Arabic), center ([lon,lat])
function colorGovPolygons(govs) {
  if (!CsApp.map) return;

  // Build lookup by normalised English name, slug, and Arabic name
  const byNorm = {};
  govs.forEach(g => {
    if (g.name_en) byNorm[normName(g.name_en)] = g;      // "amman", "irbid" …
    if (g.slug)    byNorm[g.slug.toLowerCase()]  = g;      // same slugs
    if (g.name_ar) byNorm[normName(g.name_ar)]   = g;      // normalised Arabic
  });

  CsApp.govFeatures = {};
  CsApp.map.data.forEach(feature => {
    // GeoJSON property keys are GOVERNORATE_A (English) and GOVERNORATE_AR (Arabic)
    const engName = feature.getProperty('GOVERNORATE_A')  || '';
    const arName  = feature.getProperty('GOVERNORATE_AR') || '';
    const gov = byNorm[normName(engName)] ||
                byNorm[engName.toLowerCase()] ||
                byNorm[normName(arName)];
    if (gov) {
      feature.setProperty('_gov',  gov);
      feature.setProperty('_slug', gov.slug);
      CsApp.govFeatures[gov.slug] = feature;
    }
  });

  CsApp.map.data.setStyle(getFeatureStyle);
  if (CsApp.highlightedFeature) {
    CsApp.map.data.overrideStyle(CsApp.highlightedFeature, HIGHLIGHT_STYLE);
  }

  updateGovLabels(govs);
}

// ── Governorate Labels ────────────────────────────────────────────────────────
function updateGovLabels(govs) {
  CsApp.labelMarkers.forEach(m => { m.map = null; });
  CsApp.labelMarkers = [];

  const showLabels = document.getElementById('govBadgeToggle')?.checked ?? true;

  govs.forEach(gov => {
    const center = gov.center; // [lon, lat]
    if (!center || center.length < 2) return;

    const labelDiv = document.createElement("div");
    labelDiv.textContent = gov.name_ar || gov.name_en || '';
    labelDiv.style.color = '#ffffff';
    labelDiv.style.fontSize = '11px';
    labelDiv.style.fontWeight = 'bold';
    labelDiv.style.fontFamily = 'system-ui, sans-serif';
    labelDiv.style.textShadow = '0px 1px 3px rgba(0,0,0,0.8)';
    labelDiv.style.transform = 'translate(-50%, -50%)';

    const marker = new google.maps.marker.AdvancedMarkerElement({
      position:  { lat: center[1], lng: center[0] },
      map:       showLabels ? CsApp.map : null,
      content:   labelDiv,
      zIndex:    10,
    });
    CsApp.labelMarkers.push(marker);
  });
}

// ── Fetch KPI Data ────────────────────────────────────────────────────────────
async function fetchMapData() {
  try {
    const res = await fetch(API_MAP_DATA, { credentials: 'include' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    CsApp.mapData    = data;
    CsApp.dataLoaded = true;

    const govs = data.governorates || [];
    colorGovPolygons(govs);
    populateGovList(govs);
    populateRankings(govs);
    updateKpiStrip(data);
    updateGovSelect(govs);
    updateStatusLive();
    renderWarnings();

    await fetchKgPins();
  } catch (err) {
    console.error('[GMaps] map data fetch error:', err);
    addWarning('تعذر تحميل بيانات الخريطة. يرجى التحقق من الاتصال بالخادم.');
    setStatusError();
    renderWarnings();

    const tbody = document.querySelector('#rankingsTable tbody');
    if (tbody) {
      tbody.innerHTML = `
        <tr><td colspan="8" style="text-align:center;padding:2rem;color:#64748b">
          <div>تعذر تحميل بيانات المحافظات</div>
          <button class="cc-btn" style="margin-top:.75rem" onclick="retryFetchMapData()">
            <i class="bi bi-arrow-clockwise" aria-hidden="true"></i> إعادة المحاولة
          </button>
        </td></tr>`;
    }
  }
}

function retryFetchMapData() {
  CsApp.warnings = [];
  fetchMapData();
}

async function fetchKgPins() {
  try {
    const res = await fetch(API_KG_MAPDATA, { credentials: 'include' });
    if (!res.ok) { addWarning('تعذر تحميل بيانات الحضانات على الخريطة.'); return; }
    const geojson  = await res.json();
    const features = geojson.features || [];
    const kgs = features.map(f => ({
      ...f.properties,
      longitude: f.geometry?.coordinates?.[0],
      latitude:  f.geometry?.coordinates?.[1],
    })).filter(k => k.longitude != null && k.latitude != null);

    if (geojson.missing_location_count > 0) {
      addWarning(`${geojson.missing_location_count} منشأة لا تمتلك إحداثيات جغرافية ولم تُعرض على الخريطة.`);
      renderWarnings();
    }

    addKgPins(kgs);
    CsApp.kgLoaded = true;
  } catch {
    addWarning('تعذر تحميل مواقع الحضانات.');
    renderWarnings();
  }
}

// ── Warnings ──────────────────────────────────────────────────────────────────
function addWarning(msg) {
  if (!CsApp.warnings.includes(msg)) CsApp.warnings.push(msg);
}
function renderWarnings() {
  const strip = document.getElementById('dataQualityStrip');
  if (!strip) return;
  if (!CsApp.warnings.length) { strip.style.display = 'none'; return; }
  strip.style.display = 'flex';
  strip.innerHTML = CsApp.warnings.map(w =>
    `<div class="dq-warning"><i class="bi bi-exclamation-triangle-fill" aria-hidden="true"></i> ${w}</div>`
  ).join('');
}

// ── Kindergarten Markers ──────────────────────────────────────────────────────
function addKgPins(kgs) {
  CsApp.kgMarkers.forEach(m => { m.map = null; });
  CsApp.kgMarkers = [];

  const kgOn = document.getElementById('kgToggle')?.checked ?? true;

  kgs.forEach(kg => {
    const score    = parseFloat(kg.kpi_score) || 0;
    const riskSc   = 100 - score;
    const isCrit   = riskSc >= 75;
    const isHigh   = riskSc >= 50;
    const pixelSize = isCrit ? 9 : isHigh ? 7 : riskSc >= 25 ? 5 : 4;
    const hexClr   = riskHex(riskSc);

    const pinDiv = document.createElement("div");
    pinDiv.style.width = (pixelSize * 2) + "px";
    pinDiv.style.height = (pixelSize * 2) + "px";
    pinDiv.style.borderRadius = "50%";
    pinDiv.style.backgroundColor = hexClr;
    pinDiv.style.opacity = isCrit ? "1.0" : isHigh ? "0.95" : "0.88";
    pinDiv.style.border = (isCrit ? 2 : 1.5) + "px solid rgba(255,255,255," + (isCrit ? 1.0 : 0.75) + ")";
    pinDiv.style.transform = 'translate(-50%, -50%)';
    pinDiv.title = kg.name_ar || kg.name_en || '';

    const marker = new google.maps.marker.AdvancedMarkerElement({
      position: { lat: kg.latitude, lng: kg.longitude },
      map:      kgOn ? CsApp.map : null,
      title:    kg.name_ar || kg.name_en || '',
      content:  pinDiv,
      zIndex: isCrit ? 20 : isHigh ? 15 : 10,
    });
    marker._kgData = kg;

    // Use gmp-click for AdvancedMarkerElement
    marker.addListener('gmp-click', () => { hideTooltip(); showKgDetail(kg); });
    
    // Add hover directly on the DOM element for tooltip
    pinDiv.addEventListener('mouseenter', () => showKgTooltip(kg));
    pinDiv.addEventListener('mouseleave', hideTooltip);

    CsApp.kgMarkers.push(marker);
  });

  _setEl('kgCountBadge', kgs.length);
}

function _applyKgVisibility() {
  const kgOn = document.getElementById('kgToggle')?.checked ?? true;
  CsApp.kgMarkers.forEach(m => {
    const kg     = m._kgData;
    const cityOk = !CsApp.selectedCity || kg?.city === CsApp.selectedCity;
    m.map = (kgOn && cityOk) ? CsApp.map : null;
  });
}

// ── Tooltip ───────────────────────────────────────────────────────────────────
function showGovTooltip(gov) {
  const tooltip = document.getElementById('geoTooltip');
  if (!tooltip) return;
  const score  = gov.risk_score ?? 0;
  const getter = IND_RISK_GETTER[CsApp.currentInd];
  const ind    = CsApp.currentInd !== 'overall_risk' && getter ? CsApp.currentInd : null;
  let indRow   = '';
  if (ind && gov.main_indicators?.[ind] != null) {
    const v   = gov.main_indicators[ind];
    const lbl = IND_LABELS[ind];
    indRow = `<div class="tt-row"><span>${lbl?.ar || ind}</span><b style="color:${riskHex(100-v)}">${v.toFixed(1)}</b></div>`;
  }
  tooltip.innerHTML = `
    <div class="tt-name">${esc(gov.name_ar || gov.name_en)}</div>
    <div class="tt-badge"><span class="rank-badge risk-${riskClass(score)}">${riskAr(score)}</span></div>
    <div class="tt-divider"></div>
    <div class="tt-row"><span>درجة الخطر</span><b style="color:${riskHex(score)}">${score.toFixed(1)}/100</b></div>
    ${indRow}
    <div class="tt-row"><span>إجمالي المنشآت</span><b>${gov.kg_count ?? '--'}</b></div>
    <div class="tt-row"><span>الأطفال النشطون</span><b>${gov.student_count ?? '--'}</b></div>
    <div class="tt-hint">انقر للتفاصيل الكاملة</div>`;
  tooltip.style.display = 'block';
  tooltip.setAttribute('aria-hidden', 'false');
  positionTooltip(CsApp._mouseX, CsApp._mouseY);
}

function showKgTooltip(k) {
  const tooltip = document.getElementById('geoTooltip');
  if (!tooltip) return;
  const score  = parseFloat(k.kpi_score) || 0;
  const riskSc = 100 - score;
  const govAr  = govNameAr(k.governorate) || k.governorate_name_en || '';
  const cityTxt = k.city ? `<div class="tt-row"><span>المدينة</span><b>${esc(k.city)}</b></div>` : '';
  tooltip.innerHTML = `
    <div class="tt-name">${esc(k.name_ar || k.name_en || 'منشأة')}</div>
    <div class="tt-badge"><span class="rank-badge risk-${riskClass(riskSc)}">${riskAr(riskSc)}</span></div>
    <div class="tt-divider"></div>
    <div class="tt-row"><span>المحافظة</span><b>${esc(govAr)}</b></div>
    ${cityTxt}
    <div class="tt-row"><span>درجة الأداء</span><b style="color:${riskHex(riskSc)}">${score.toFixed(1)}</b></div>
    <div class="tt-hint">انقر للتفاصيل</div>`;
  tooltip.style.display = 'block';
  tooltip.setAttribute('aria-hidden', 'false');
  positionTooltip(CsApp._mouseX, CsApp._mouseY);
}

function positionTooltip(x, y) {
  const tooltip = document.getElementById('geoTooltip');
  if (!tooltip) return;
  tooltip.style.left = `${x + 14}px`;
  tooltip.style.top  = `${y - 10}px`;
}

function hideTooltip() {
  const tooltip = document.getElementById('geoTooltip');
  if (tooltip) { tooltip.style.display = 'none'; tooltip.setAttribute('aria-hidden', 'true'); }
}

// ── Governorate Selection ─────────────────────────────────────────────────────
function selectGovernorate(gov) {
  CsApp.selectedGov  = gov;
  CsApp.selectedCity = null;

  document.querySelectorAll('.cs-gov-item').forEach(el =>
    el.classList.toggle('selected', el.dataset.slug === gov.slug)
  );
  document.querySelectorAll('#rankingsTable tbody tr').forEach(tr =>
    tr.classList.toggle('rank-selected', tr.dataset.slug === gov.slug)
  );

  // Pan map to governorate center
  const center = gov.center; // [lon, lat]
  if (center && center.length >= 2 && CsApp.map) {
    CsApp.map.panTo({ lat: center[1], lng: center[0] });
    CsApp.map.setZoom(9);
  }

  highlightGovFeature(gov.slug);
  loadGovDetail(gov.slug);
}

function highlightGovFeature(slug) {
  if (CsApp.highlightedFeature) {
    CsApp.map?.data.revertStyle(CsApp.highlightedFeature);
    CsApp.highlightedFeature = null;
  }
  const feature = CsApp.govFeatures[slug];
  if (feature) {
    CsApp.map?.data.overrideStyle(feature, HIGHLIGHT_STYLE);
    CsApp.highlightedFeature = feature;
  }
}

// ── Governorate Detail Panel ──────────────────────────────────────────────────
async function loadGovDetail(slug) {
  const panel = document.getElementById('intelPanel');
  panel.innerHTML = `
    <div class="intel-loading" role="status" aria-live="polite">
      <div class="intel-loading-spinner" aria-hidden="true"></div>
      <div class="intel-loading-name">جاري تحميل بيانات المحافظة…</div>
    </div>`;
  try {
    const res = await fetch(`${API_GOV_DETAIL}${slug}`, { credentials: 'include' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const govData = await res.json();
    renderIntelPanel(govData);
    loadCityData(slug);
  } catch {
    panel.innerHTML = `
      <div class="intel-error" role="alert">
        <i class="bi bi-exclamation-octagon" aria-hidden="true"></i>
        <p>تعذر تحميل بيانات المحافظة، يرجى المحاولة مرة أخرى.</p>
        <button class="cc-btn" onclick="loadGovDetail('${slug}')">
          <i class="bi bi-arrow-clockwise" aria-hidden="true"></i> إعادة المحاولة
        </button>
      </div>`;
  }
}

// ── SVG Radar Chart ───────────────────────────────────────────────────────────
function renderRadarChart(perfIndicators) {
  const SZ = 148, CX = SZ / 2, CY = SZ / 2, MAX_R = SZ * 0.36;
  const N  = IND_ORDER.length;
  const ang = i => (2 * Math.PI * i / N) - Math.PI / 2;
  const pt  = (r, i) => ({ x: CX + r * Math.cos(ang(i)), y: CY + r * Math.sin(ang(i)) });

  const grid = [25, 50, 75, 100].map(lvl => {
    const r  = MAX_R * lvl / 100;
    const ps = IND_ORDER.map((_, i) => { const p = pt(r, i); return `${p.x},${p.y}`; }).join(' ');
    return `<polygon points="${ps}" fill="none" stroke="rgba(255,255,255,${lvl === 100 ? .18 : .07})" stroke-width=".75"/>`;
  }).join('');

  const axes = IND_ORDER.map((_, i) => {
    const p = pt(MAX_R, i);
    return `<line x1="${CX}" y1="${CY}" x2="${p.x}" y2="${p.y}" stroke="rgba(255,255,255,.12)" stroke-width=".75"/>`;
  }).join('');

  // Unavailable indicators collapse to the centre for geometry, but must not
  // enter the average — counting them as 0 reported a healthy governorate as
  // failing purely because one indicator is unmeasurable by design.
  const rawVals = IND_ORDER.map(k => perfIndicators?.[k]);
  const vals = rawVals.map(v => v ?? 0);
  const poly = vals.map((v, i) => { const p = pt(MAX_R * v / 100, i); return `${p.x},${p.y}`; }).join(' ');
  const measured = rawVals.filter(v => v != null);
  const avg  = measured.length ? measured.reduce((s, v) => s + v, 0) / measured.length : null;
  const fc   = avg == null ? RISK_UNAVAILABLE_HEX : riskHex(100 - avg);

  const dots = vals.map((v, i) => {
    const p = pt(MAX_R * v / 100, i);
    return `<circle cx="${p.x}" cy="${p.y}" r="2.5" fill="${riskHex(100-v)}" stroke="rgba(255,255,255,.8)" stroke-width=".75"/>`;
  }).join('');

  const ABBREV = ['منشآت', 'أطفال', 'موظفون', 'سلامة', 'تقارير', 'حوكمة'];
  const lbls = IND_ORDER.map((_, i) => {
    const p = pt(MAX_R + 17, i);
    return `<text x="${p.x}" y="${p.y}" text-anchor="middle" dominant-baseline="middle" font-size="8" fill="#94a3b8" font-family="system-ui,sans-serif">${ABBREV[i]}</text>`;
  }).join('');

  return `
    <div style="display:flex;flex-direction:column;align-items:center;padding:.5rem 0 .25rem">
      <div style="font-size:.7rem;color:#64748b;margin-bottom:.25rem;letter-spacing:.03em">مخطط الأداء الشعاعي</div>
      <svg width="${SZ}" height="${SZ}" viewBox="0 0 ${SZ} ${SZ}" style="overflow:visible" aria-hidden="true">
        ${grid}${axes}
        <polygon points="${poly}" fill="${fc}" fill-opacity=".18" stroke="${fc}" stroke-width="1.5" stroke-linejoin="round"/>
        ${dots}${lbls}
        <text x="${CX}" y="${CY}" text-anchor="middle" dominant-baseline="middle"
              font-size="12" font-weight="700" fill="${fc}" font-family="system-ui,sans-serif">${avg.toFixed(0)}</text>
      </svg>
    </div>`;
}

// ── Intel Panel Render ────────────────────────────────────────────────────────
function renderIntelPanel(d) {
  const panel   = document.getElementById('intelPanel');
  const score   = d.risk_score ?? 0;
  const cls     = riskClass(score);
  const avgRisk = CsApp._avgRisk || 0;
  const diff    = score - avgRisk;

  const compareHtml = avgRisk > 0
    ? diff > 2
      ? `<div class="intel-compare" style="color:#ef4444" aria-label="أعلى من المتوسط الوطني">
           <i class="bi bi-arrow-up-short" aria-hidden="true"></i>
           أعلى من المتوسط الوطني بـ ${diff.toFixed(1)} نقطة
         </div>`
      : diff < -2
      ? `<div class="intel-compare" style="color:#22c55e" aria-label="أقل من المتوسط الوطني">
           <i class="bi bi-arrow-down-short" aria-hidden="true"></i>
           أقل من المتوسط الوطني بـ ${Math.abs(diff).toFixed(1)} نقطة
         </div>`
      : `<div class="intel-compare" style="color:#475569">
           <i class="bi bi-dash" aria-hidden="true"></i>
           يساوي تقريباً المتوسط الوطني
         </div>`
    : '';

  const indHtml = IND_ORDER.map(key => {
    const rawPerf = d.main_indicators?.[key];
    const available = rawPerf != null;
    const perf  = available ? rawPerf : 0;
    const meta  = IND_LABELS[key] || {};
    const trend = d.trends?.[key];
    const color = available ? (meta.color || riskHex(100 - perf)) : RISK_UNAVAILABLE_HEX;
    const trendIcon = !trend ? '' :
      trend.direction === 'up'   ? `<i class="bi bi-arrow-up-short" style="color:#22c55e" aria-hidden="true"></i><small style="color:#22c55e;font-size:.65rem">${trend.pct != null ? trend.pct.toFixed(1)+'%' : ''}</small>` :
      trend.direction === 'down' ? `<i class="bi bi-arrow-down-short" style="color:#ef4444" aria-hidden="true"></i><small style="color:#ef4444;font-size:.65rem">${trend.pct != null ? trend.pct.toFixed(1)+'%' : ''}</small>` : '';
    return `
      <div class="intel-ind-row" style="flex-direction:column;align-items:stretch;margin-bottom:.625rem">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:2px">
          <span class="intel-ind-label">${meta.ar || key}</span>
          <span style="display:flex;align-items:center;gap:.15rem;font-size:.75rem;font-weight:700;color:${color}">${available ? perf.toFixed(1) : 'غير متوفر'}${trendIcon}</span>
        </div>
        <div class="intel-ind-bar">
          <div class="intel-ind-track">
            <div class="intel-ind-fill" style="width:${perf}%;background:${color}"></div>
          </div>
        </div>
      </div>`;
  }).join('');

  const alerts    = d.alerts || [];
  const alertHtml = alerts.length
    ? alerts.slice(0, 6).map(a => `
        <div class="intel-alert-row">
          <div class="intel-alert-dot" aria-hidden="true"></div>
          <span>${esc(a.message || '')}</span>
        </div>`).join('')
    : '<div class="intel-no-alerts">لا توجد تنبيهات نشطة</div>';

  const action     = d.recommended_action;
  const actionHtml = action?.ar || action?.en
    ? `<div class="intel-action-box">
         <i class="bi bi-lightbulb-fill" aria-hidden="true"></i>
         ${action.ar || action.en}
       </div>` : '';

  const sub          = d.sub_indicators || {};
  const kgCount      = sub.active_nurseries    ?? d.kg_count      ?? 'غير متوفر';
  const studentCount = sub.registered_children ?? d.student_count ?? 'غير متوفر';
  const govScore     = sub.governance_score     != null ? sub.governance_score.toFixed(1) : 'غير متوفر';
  const safeSlug     = (d.slug || d.code || '').replace(/'/g, '');
  const safeName     = (d.name_ar || d.name_en || '').replace(/'/g, '');

  panel.innerHTML = `
    <div class="intel-gov-header">
      <div class="intel-gov-namerow">
        <h3 class="intel-gov-name">${d.name_ar || d.name_en || ''}</h3>
        <span class="intel-gov-code">${(d.code || d.slug || '').toUpperCase()}</span>
      </div>
      <div class="intel-gov-name-sub">${d.name_en || ''}</div>
      <div class="intel-risk-row">
        <div class="intel-risk-score" style="color:${riskHex(score)}" aria-label="مؤشر الخطر: ${score.toFixed(1)}">${score.toFixed(1)}</div>
        <span class="intel-risk-badge risk-${cls}">
          <i class="bi bi-${cls === 'low' ? 'check-circle' : cls === 'medium' ? 'exclamation-circle' : 'x-circle'}" aria-hidden="true"></i>
          ${riskAr(score)}
        </span>
      </div>
      ${compareHtml}
      ${actionHtml}

      <div class="intel-action-row">
        <button class="cc-btn intel-action-btn"
                onclick="window.location.href='/admin/kindergartens?governorate=${safeSlug}'"
                aria-label="عرض منشآت ${safeName}">
          <i class="bi bi-building" aria-hidden="true"></i> عرض المنشآت
        </button>
        <button class="cc-btn intel-action-btn"
                onclick="exportGovReport('${safeSlug}','${safeName}')"
                aria-label="تصدير تقرير ${safeName}">
          <i class="bi bi-download" aria-hidden="true"></i>
        </button>
      </div>
    </div>

    <div class="intel-section">
      <div class="intel-section-title">
        <i class="bi bi-bar-chart-line" aria-hidden="true"></i>
        المؤشرات الرئيسية <span class="intel-count">(6)</span>
      </div>
      ${indHtml}
    </div>

    <div class="intel-section">
      ${renderRadarChart(d.main_indicators)}
    </div>

    <div class="intel-section">
      <div class="intel-section-title">
        <i class="bi bi-bell" aria-hidden="true"></i>
        التنبيهات <span class="intel-count">${alerts.length}</span>
      </div>
      ${alertHtml}
    </div>

    <div class="intel-section" id="cityDataSection">
      <div class="intel-section-title">
        <i class="bi bi-geo" aria-hidden="true"></i>
        المؤشرات حسب المدينة <span class="intel-count" id="citySectionCount"></span>
      </div>
      <div id="cityTableBody">
        <div class="intel-loading-inline">
          <span class="intel-loading-spinner" style="width:14px;height:14px;border-width:1.5px" aria-hidden="true"></span>جارٍ تحميل البيانات، يرجى الانتظار.</div>
      </div>
    </div>

    <div class="intel-footer">
      <div>إجمالي المنشآت: <strong>${kgCount}</strong></div>
      <div>الأطفال المسجلون: <strong>${studentCount}</strong></div>
      <div>نقاط الحوكمة: <strong>${govScore}</strong></div>
      ${avgRisk > 0 ? `<div>المتوسط الوطني للخطر: <strong>${avgRisk.toFixed(1)}</strong></div>` : ''}
      <div style="margin-top:.5rem;font-size:.7rem;color:#475569">
        آخر تحديث: ${d.last_update ? new Date(d.last_update).toLocaleString('ar-JO') : 'غير متوفر'}
      </div>
      <div style="font-size:.7rem;color:#475569">المصدر: قاعدة بيانات KinJo المركزية</div>
    </div>`;
}

// ── City-Level Aggregation ────────────────────────────────────────────────────
async function loadCityData(slug) {
  try {
    const res = await fetch(API_CITY_DATA(slug), { credentials: 'include' });
    if (!res.ok) { renderCitySection(null, 'تعذر تحميل بيانات المدن.'); return; }
    const data = await res.json();
    renderCitySection(data);
  } catch {
    renderCitySection(null, 'تعذر تحميل بيانات المدن.');
  }
}

function renderCitySection(cityData, errorMsg) {
  const body    = document.getElementById('cityTableBody');
  const counter = document.getElementById('citySectionCount');
  if (!body) return;

  if (errorMsg) { body.innerHTML = `<div class="intel-no-alerts">${errorMsg}</div>`; return; }

  const cities   = cityData?.cities   || [];
  const warnings = cityData?.warnings || [];

  if (counter) counter.textContent = cities.length ? `(${cities.length})` : '';

  if (!cities.length) {
    const msg = warnings[0] || (cityData?.data_status === 'empty'
      ? 'لا تتوفر بيانات المدن لهذه المحافظة حالياً.'
      : 'لا توجد مدن مسجلة لهذه المحافظة.');
    body.innerHTML = `<div class="intel-no-alerts">${msg}</div>`;
    return;
  }

  body.innerHTML = cities.map(c => {
    const riskSc    = c.risk_score ?? 0;
    const cls       = riskClass(riskSc);
    const kgLabel   = c.kindergarten_count + ' منشأة';
    const stLabel   = c.children_count ? `· ${c.children_count} طفل` : '';
    const critLabel = c.critical_kindergartens
      ? `<span style="color:#ef4444;font-size:.7rem"> — ${c.critical_kindergartens} حرجة</span>` : '';
    const cityName = esc(c.district || '');
    const safeCity  = (c.district || '').replace(/'/g, "\\'");
    return `
      <div class="city-row" data-city="${cityName}"
           role="button" tabindex="0"
           aria-label="${cityName} — خطر: ${riskAr(riskSc)}"
           onclick="selectCity('${safeCity}')"
           onkeydown="if(event.key==='Enter'||event.key===' ')selectCity('${safeCity}')">
        <div class="city-row-name">
          <span>${cityName}</span>${critLabel}
          <div style="font-size:.7rem;color:#64748b;margin-top:1px">${kgLabel}${stLabel}</div>
        </div>
        <div class="city-row-score">
          <div class="mini-bar-track" style="width:52px">
            <div class="mini-bar-fill" style="width:${riskSc}%;background:${riskHex(riskSc)}"></div>
          </div>
          <span class="rank-badge risk-${cls}" style="min-width:40px;justify-content:center">${riskAr(riskSc)}</span>
        </div>
      </div>`;
  }).join('');
}

function selectCity(cityName) {
  CsApp.selectedCity = cityName;

  // Pan to average position of KGs in this city
  const cityKgs = CsApp.kgMarkers.filter(m => m._kgData?.city === cityName);
  if (cityKgs.length && CsApp.map) {
    const avgLat = cityKgs.reduce((s, m) => s + (m._kgData.latitude  || 0), 0) / cityKgs.length;
    const avgLng = cityKgs.reduce((s, m) => s + (m._kgData.longitude || 0), 0) / cityKgs.length;
    CsApp.map.panTo({ lat: avgLat, lng: avgLng });
    CsApp.map.setZoom(11);
  }

  document.querySelectorAll('.city-row').forEach(el =>
    el.classList.toggle('selected', el.dataset.city === cityName)
  );

  _applyKgVisibility();

  if (!document.querySelector('.city-reset')) {
    const counter = document.getElementById('citySectionCount');
    if (counter) {
      const reset = document.createElement('button');
      reset.className = 'city-reset cc-btn';
      reset.style.cssText = 'padding:.1rem .4rem;font-size:.7rem;margin-inline-end:.5rem';
      reset.setAttribute('aria-label', 'إلغاء تحديد المدينة');
      reset.innerHTML = '<i class="bi bi-x" aria-hidden="true"></i>';
      reset.onclick = resetCityFilter;
      counter.insertAdjacentElement('beforebegin', reset);
    }
  }
}

function resetCityFilter() {
  CsApp.selectedCity = null;
  _applyKgVisibility();
  document.querySelectorAll('.city-row').forEach(el => el.classList.remove('selected'));
  document.querySelector('.city-reset')?.remove();
}

// ── Kindergarten Detail Panel ─────────────────────────────────────────────────
function showKgDetail(kg) {
  const panel   = document.getElementById('intelPanel');
  const score   = parseFloat(kg.kpi_score) || 0;
  const riskSc  = 100 - score;
  const name    = kg.name_ar || kg.name_en || 'منشأة';
  const govAr   = govNameAr(kg.governorate) || kg.governorate_name_en || '';
  const cityTxt = kg.city ? ` • ${kg.city}` : '';
  const sc      = kg.supporting_counts || {};
  const mainInds = kg.main_indicators || {};

  const indHtml = IND_ORDER.map(key => {
    const ind   = mainInds[key];
    const availableIntel = ind?.score != null;
    const perf  = availableIntel ? ind.score : 0;
    const meta  = IND_LABELS[key] || {};
    const color = availableIntel
      ? (ind?.color || meta.color || riskHex(100 - perf))
      : RISK_UNAVAILABLE_HEX;
    return `
      <div class="intel-ind-row" style="flex-direction:column;align-items:stretch;margin-bottom:.5rem">
        <div style="display:flex;justify-content:space-between;margin-bottom:2px">
          <span class="intel-ind-label">${meta.ar || key}</span>
          <span style="font-size:.75rem;font-weight:700;color:${color}">${perf.toFixed(1)}</span>
        </div>
        <div class="intel-ind-bar">
          <div class="intel-ind-track">
            <div class="intel-ind-fill" style="width:${perf}%;background:${color}"></div>
          </div>
        </div>
      </div>`;
  }).join('');

  const radarVals = Object.fromEntries(IND_ORDER.map(k => [k, mainInds[k]?.score ?? 0]));

  panel.innerHTML = `
    <div class="intel-gov-header">
      <div class="intel-gov-namerow">
        <h3 class="intel-gov-name" style="font-size:.95rem">${name}</h3>
      </div>
      <div class="intel-gov-name-sub">${govAr}${cityTxt}</div>
      <div class="intel-risk-row">
        <div class="intel-risk-score" style="color:${riskHex(riskSc)};font-size:1.6rem">${score.toFixed(1)}</div>
        <span class="intel-risk-badge risk-${riskClass(riskSc)}">
          <i class="bi bi-${riskClass(riskSc) === 'low' ? 'check-circle' : 'exclamation-circle'}" aria-hidden="true"></i>
          ${riskAr(riskSc)}
        </span>
      </div>
    </div>

    <div class="intel-section">
      <div class="intel-section-title">مؤشرات الأداء</div>
      ${indHtml || '<div class="intel-no-alerts">لا توجد بيانات مؤشرات</div>'}
    </div>

    <div class="intel-section">
      ${renderRadarChart(radarVals)}
    </div>

    <div class="intel-footer">
      <div>الأطفال النشطون: <strong>${sc.active_enrollments ?? 'غير متوفر'}</strong></div>
      <div>الفصول الدراسية: <strong>${sc.classes ?? 'غير متوفر'}</strong></div>
      <div>المشرفون: <strong>${sc.supervisors ?? 'غير متوفر'}</strong></div>
      <div>الحوادث (90 يوم): <strong>${sc.recent_incidents ?? 'غير متوفر'}</strong></div>
      <div>نقاط الحوكمة: <strong>${sc.governance_score != null ? sc.governance_score.toFixed(1) : 'غير متوفر'}</strong></div>
      ${kg.id ? `<div style="margin-top:.75rem">
        <a href="/admin/kindergartens/${kg.id}" class="cc-btn" style="display:inline-flex"
           aria-label="فتح ملف المنشأة الكامل">
          <i class="bi bi-box-arrow-up-right" aria-hidden="true"></i> فتح الملف الكامل
        </a>
      </div>` : ''}
    </div>`;
}

// ── Left Panel — Governorate List ─────────────────────────────────────────────
function populateGovList(govs) {
  const list = document.getElementById('govListBody');
  if (!list) return;
  list.innerHTML = govs.map(g => {
    const score   = g.risk_score ?? 0;
    const cls     = riskClass(score);
    const govJson = JSON.stringify(g).replace(/"/g, '&quot;');
    const kgLabel = g.kg_count != null
      ? `<span style="font-size:.7rem;color:#64748b">${g.kg_count} منشأة</span>` : '';
    return `
      <div class="cs-gov-item" data-slug="${g.slug}" data-risk-class="${cls}"
           tabindex="0" role="button"
           aria-label="${esc(g.name_ar || g.name_en)} — ${riskAr(score)}"
           onclick="selectGovernorate(${govJson})"
           onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault(); selectGovernorate(${govJson})}">
        <div>
          <div class="cs-gov-name">${esc(g.name_ar || g.name_en)}</div>
          ${kgLabel}
        </div>
        <span class="rank-badge risk-${cls}" style="flex-shrink:0"
              title="${riskAr(score)} (${score.toFixed(1)})">${score.toFixed(0)}</span>
      </div>`;
  }).join('');
}

function applyGovListFilter() {
  const q  = (document.getElementById('govSearch')?.value || '').toLowerCase();
  const rf = CsApp.riskFilter;
  document.querySelectorAll('.cs-gov-item').forEach(el => {
    const txt  = (el.querySelector('.cs-gov-name')?.textContent || '').toLowerCase();
    const rc   = el.dataset.riskClass || '';
    const show = (!q || txt.includes(q)) && (rf === 'all' || rc === rf);
    el.style.display = show ? '' : 'none';
  });
}

// ── KPI Strip — 6 cards ───────────────────────────────────────────────────────
function updateKpiStrip(data) {
  const govs    = data.governorates || [];
  const sum     = data.summary      || {};

  const avgRisk  = sum.average_risk   != null ? sum.average_risk
    : govs.length ? govs.reduce((s, g) => s + (g.risk_score || 0), 0) / govs.length : 0;
  const critical = sum.critical_count  != null ? sum.critical_count
    : govs.filter(g => (g.risk_score || 0) >= 75).length;
  const highRisk = sum.high_risk_count != null ? sum.high_risk_count
    : govs.filter(g => (g.risk_score || 0) >= 50).length;
  const totalKg  = govs.reduce((s, g) => s + (g.kg_count     || 0), 0);
  const totalSt  = govs.reduce((s, g) => s + (g.student_count || 0), 0);
  const covered  = govs.filter(g => g.risk_score != null).length || govs.length;

  CsApp._avgRisk = avgRisk;

  _setEl('kpiCovered',      covered || '--');
  _setEl('kpiAvgRisk',      avgRisk.toFixed(1));
  _setEl('kpiHighRisk',     highRisk);
  _setEl('kpiCritical',     critical);
  _setEl('kpiInstitutions', totalKg || '--');

  const hasStudentData = govs.some(g => g.student_count != null && g.student_count > 0);
  const studentDisplay = (hasStudentData && totalSt > 0)
    ? (totalSt < totalKg ? '—' : totalSt.toLocaleString('ar-JO'))
    : '—';
  _setEl('kpiStudents', studentDisplay);
  _setEl('alertCountStatus',
    `<i class="bi bi-shield-exclamation" aria-hidden="true"></i> ${highRisk} محافظة مرتفعة أو حرجة الخطر`);
}

function updateGovSelect(govs) {
  const sel = document.getElementById('govSelect');
  if (!sel || sel.options.length > 1) return;
  govs.forEach(g => {
    const opt = new Option(g.name_ar || g.name_en, g.slug);
    sel.add(opt);
  });
}

// ── Rankings Table — 8 columns ────────────────────────────────────────────────
function populateRankings(govs) {
  const tbody = document.querySelector('#rankingsTable tbody');
  if (!tbody) return;

  const avgRisk = CsApp._avgRisk || 0;
  const q       = _rankSearch.toLowerCase();

  let list = [...govs];

  if (q) {
    list = list.filter(g =>
      (g.name_ar || '').includes(q) ||
      (g.name_en || '').toLowerCase().includes(q)
    );
  }

  list.sort((a, b) => {
    if (_rankSort.col === 'name') {
      const na = a.name_ar || a.name_en || '';
      const nb = b.name_ar || b.name_en || '';
      return _rankSort.dir === 'asc' ? na.localeCompare(nb, 'ar') : nb.localeCompare(na, 'ar');
    }
    const va = _rankSort.col === 'kgs' ? (a.kg_count || 0) : (a.risk_score || 0);
    const vb = _rankSort.col === 'kgs' ? (b.kg_count || 0) : (b.risk_score || 0);
    return _rankSort.dir === 'asc' ? va - vb : vb - va;
  });

  if (!list.length) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:1.5rem;color:#64748b">
      لا توجد نتائج مطابقة للبحث
    </td></tr>`;
    return;
  }

  tbody.innerHTML = '';
  list.forEach((g, i) => {
    const score   = g.risk_score || 0;
    const cls     = riskClass(score);
    const rank    = i + 1;
    const numCls  = rank <= 3 ? `top-${rank}` : '';

    const indVal  = CsApp.currentInd && CsApp.currentInd !== 'overall_risk'
      ? (g.main_indicators?.[CsApp.currentInd] ?? null) : null;
    const indCell = indVal != null
      ? `<small style="color:#64748b">${IND_LABELS[CsApp.currentInd]?.ar || CsApp.currentInd}: ${indVal.toFixed(0)}</small>`
      : '';

    const diff = score - avgRisk;
    const compHtml = avgRisk > 0
      ? diff > 2
        ? `<span class="compare-up" title="أعلى من المتوسط بـ ${diff.toFixed(1)}">↑ ${diff.toFixed(1)}</span>`
        : diff < -2
        ? `<span class="compare-dn" title="أقل من المتوسط بـ ${Math.abs(diff).toFixed(1)}">↓ ${Math.abs(diff).toFixed(1)}</span>`
        : `<span class="compare-eq">≈</span>`
      : '<span class="compare-eq">--</span>';

    const kgCount  = g.kg_count      != null ? g.kg_count      : '--';
    const stCount  = g.student_count != null ? g.student_count : '--';
    const govJson  = JSON.stringify(g).replace(/"/g, '&quot;');
    const safeName = (g.name_ar || g.name_en || '').replace(/'/g, '');
    const safeSlug = (g.slug || '').replace(/'/g, '');

    const tr = document.createElement('tr');
    tr.dataset.slug = g.slug;
    if (CsApp.selectedGov?.slug === g.slug) tr.classList.add('rank-selected');
    tr.tabIndex = 0;
    tr.setAttribute('role', 'button');
    tr.onclick = () => selectGovernorate(g);
    tr.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectGovernorate(g); } };

    tr.innerHTML = `
      <td><span class="rank-num ${numCls}">${rank}</span></td>
      <td>
        <div class="rank-name">${g.name_ar || g.name_en}</div>
        <div class="rank-code">${g.name_en || ''} ${indCell}</div>
      </td>
      <td style="font-size:.85rem;color:#cbd5e1;white-space:nowrap">${kgCount}</td>
      <td style="font-size:.85rem;color:#cbd5e1;white-space:nowrap">${stCount}</td>
      <td>
        <div style="display:flex;align-items:center;gap:6px">
          <div class="mini-bar-track" style="flex:1">
            <div class="mini-bar-fill" style="width:${score}%;background:${riskHex(score)}"></div>
          </div>
          <span style="color:${riskHex(score)};font-weight:600;font-size:.85rem;min-width:32px">${score.toFixed(1)}</span>
        </div>
      </td>
      <td><span class="rank-badge risk-${cls}">${riskAr(score)}</span></td>
      <td style="font-size:.8rem">${compHtml}</td>
      <td>
        <div class="rank-actions">
          <button class="rank-drill"
                  onclick="event.stopPropagation();selectGovernorate(${govJson})"
                  title="عرض التفاصيل"
                  aria-label="عرض تفاصيل ${g.name_ar || ''}">
            <i class="bi bi-info-circle" aria-hidden="true"></i>
          </button>
          <button class="rank-drill"
                  onclick="event.stopPropagation();exportGovReport('${safeSlug}','${safeName}')"
                  title="تصدير التقرير"
                  aria-label="تصدير تقرير ${g.name_ar || ''}">
            <i class="bi bi-download" aria-hidden="true"></i>
          </button>
        </div>
      </td>`;
    tbody.appendChild(tr);
  });
}

// ── Export Functions ──────────────────────────────────────────────────────────
function showHeatmapToast(message, type) {
  if (window.Swal) {
    window.Swal.fire({
      toast: true, position: 'top-end', icon: type || 'info',
      title: message, showConfirmButton: false, timer: 3000, timerProgressBar: true,
    });
    return;
  }
  const chip = document.getElementById('lastUpdateStatus');
  if (!chip) return;
  const old = chip.innerHTML;
  chip.innerHTML = `<i class="bi bi-info-circle" aria-hidden="true"></i> ${esc(message)}`;
  setTimeout(() => { if (chip) chip.innerHTML = old; }, 3500);
}

function _downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a   = Object.assign(document.createElement('a'), { href: url, download: filename });
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function exportAllCSV() {
  if (!CsApp.mapData?.governorates?.length) { showHeatmapToast('لا توجد بيانات للتصدير', 'warning'); return; }
  showHeatmapToast('جاري تجهيز التقرير...', 'info');

  const govs    = CsApp.mapData.governorates;
  const avgRisk = CsApp._avgRisk || 0;
  const headers = ['المحافظة', 'الاسم الإنجليزي', 'إجمالي المنشآت', 'الأطفال النشطون', 'مؤشر الخطر', 'مستوى الخطر', 'مقارنة بالمتوسط الوطني'];
  const rows = govs
    .sort((a, b) => (b.risk_score || 0) - (a.risk_score || 0))
    .map(g => [
      g.name_ar || '', g.name_en || '',
      g.kg_count ?? '', g.student_count ?? '',
      (g.risk_score || 0).toFixed(1), riskAr(g.risk_score || 0),
      avgRisk > 0 ? ((g.risk_score || 0) - avgRisk).toFixed(1) : '',
    ]);

  const csv = '﻿' + [headers, ...rows]
    .map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
    .join('\r\n');

  _downloadBlob(new Blob([csv], { type: 'text/csv;charset=utf-8;' }),
    `kinjo_heatmap_${new Date().toISOString().split('T')[0]}.csv`);
  setTimeout(() => showHeatmapToast('تم تصدير التقرير بنجاح', 'success'), 600);
}

function exportToPDF() {
  showHeatmapToast('جاري تجهيز التقرير للطباعة...', 'info');
  setTimeout(() => window.print(), 800);
}

function exportGovReport(slug, name) {
  if (!slug) return;
  showHeatmapToast(`جاري تجهيز تقرير ${name || slug}...`, 'info');

  const gov = CsApp.mapData?.governorates?.find(g => g.slug === slug);
  if (!gov) { setTimeout(() => showHeatmapToast('تعذر تجهيز التقرير، جرب مجدداً', 'error'), 800); return; }

  const avgRisk = CsApp._avgRisk || 0;
  const diff    = (gov.risk_score || 0) - avgRisk;
  const lines   = [
    '=== تقرير محافظة: ' + (gov.name_ar || gov.name_en) + ' ===', '',
    'الاسم بالعربية   : ' + (gov.name_ar || 'غير متوفر'),
    'الاسم بالإنجليزية: ' + (gov.name_en || 'غير متوفر'),
    'مؤشر الخطر      : ' + (gov.risk_score || 0).toFixed(1) + ' / 100',
    'مستوى الخطر     : ' + riskAr(gov.risk_score || 0),
    'إجمالي المنشآت  : ' + (gov.kg_count      ?? 'غير متوفر'),
    'الأطفال النشطون  : ' + (gov.student_count ?? 'غير متوفر'),
    avgRisk > 0 ? 'مقارنة بالمتوسط  : ' + (diff >= 0 ? '+' : '') + diff.toFixed(1) + ' نقطة' : '',
    '', '--- المؤشرات الرئيسية ---',
    ...Object.entries(gov.main_indicators || {}).map(([k, v]) =>
      (IND_LABELS[k]?.ar || k) + ': ' + (typeof v === 'number' ? v.toFixed(1) : (v ?? 'غير متوفر'))
    ),
    '', '--- معلومات التقرير ---',
    'تاريخ التصدير : ' + new Date().toLocaleString('ar-JO'),
    'المصدر        : قاعدة بيانات KinJo المركزية',
    'وزارة التنمية الاجتماعية — المملكة الأردنية الهاشمية',
  ].filter(l => l != null);

  _downloadBlob(new Blob(['﻿' + lines.join('\r\n')], { type: 'text/plain;charset=utf-8;' }),
    `kinjo_gov_${slug}_${new Date().toISOString().split('T')[0]}.txt`);
  setTimeout(() => showHeatmapToast('تم تصدير تقرير المحافظة بنجاح', 'success'), 600);
}

// ── WebSocket ─────────────────────────────────────────────────────────────────
function startWebSocket() {
  const connect = () => {
    let ws;
    try { ws = new WebSocket(WS_URL); } catch { return; }
    CsApp.ws = ws;
    ws.onopen  = () => { updateStatusLive(); clearTimeout(CsApp.wsTimer); };
    ws.onclose = () => { CsApp.wsTimer = setTimeout(connect, 9000); };
    ws.onerror = () => setStatusError();
    ws.onmessage = ({ data }) => {
      try {
        const msg = JSON.parse(data);
        if (msg.type === 'kpi_update' && msg.governorates?.length) {
          if (CsApp.mapData) {
            const bySlug = {};
            msg.governorates.forEach(g => { bySlug[g.slug] = g; });
            CsApp.mapData.governorates = (CsApp.mapData.governorates || []).map(g =>
              bySlug[g.slug] ? { ...g, ...bySlug[g.slug] } : g
            );
          }
          colorGovPolygons(CsApp.mapData?.governorates || msg.governorates);
          updateKpiStrip({ governorates: CsApp.mapData?.governorates || msg.governorates });
          populateRankings(CsApp.mapData?.governorates || []);
          updateStatusLive();
        }
      } catch { /* ignore malformed frames */ }
    };
  };
  connect();
}

// ── Status Chips ──────────────────────────────────────────────────────────────
function updateStatusLive() {
  const chip = document.getElementById('dataStatus');
  if (chip) { chip.className = 'status-chip live'; chip.innerHTML = '<div class="live-dot" aria-hidden="true"></div> بيانات مباشرة'; }
  _setEl('lastUpdateStatus', `<i class="bi bi-clock" aria-hidden="true"></i> ${new Date().toLocaleTimeString('ar-JO')}`);
}
function setStatusError() {
  const chip = document.getElementById('dataStatus');
  if (chip) { chip.className = 'status-chip error'; chip.innerHTML = '<i class="bi bi-exclamation-triangle" aria-hidden="true"></i> خطأ في الاتصال'; }
}

// ── UI Event Bindings ─────────────────────────────────────────────────────────
function bindUiEvents() {
  _on('indicatorViewSelect', 'change', () => {
    CsApp.currentInd = document.getElementById('indicatorViewSelect')?.value || 'overall_risk';
    if (CsApp.mapData) {
      updateGovStyles();
      populateRankings(CsApp.mapData.governorates || []);
    }
  });

  _on('govSelect', 'change', () => {
    const slug = document.getElementById('govSelect')?.value;
    if (!slug) { flyToJordan(); return; }
    const gov = CsApp.mapData?.governorates?.find(g => g.slug === slug);
    if (gov) selectGovernorate(gov);
  });

  _on('refreshBtn', 'click', () => {
    const btn = document.getElementById('refreshBtn');
    btn?.classList.add('spinning');
    CsApp.warnings = [];
    fetchMapData().finally(() => btn?.classList.remove('spinning'));
  });

  _on('kgToggle', 'change', _applyKgVisibility);

  _on('govBadgeToggle', 'change', e => {
    const show = e.target.checked;
    CsApp.labelMarkers.forEach(m => { m.map = show ? CsApp.map : null; });
  });

  _on('govOverlayToggle', 'change', () => {
    CsApp.govOverlayVisible = document.getElementById('govOverlayToggle')?.checked ?? true;
    updateGovStyles();
  });

  let govSearchTimer;
  _on('govSearch', 'input', () => {
    clearTimeout(govSearchTimer);
    govSearchTimer = setTimeout(applyGovListFilter, 250);
  });

  document.querySelectorAll('.risk-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      CsApp.riskFilter = btn.dataset.risk || 'all';
      document.querySelectorAll('.risk-filter-btn').forEach(b => {
        b.classList.toggle('active', b === btn);
        b.setAttribute('aria-pressed', String(b === btn));
      });
      applyGovListFilter();
    });
  });

  _on('csHomeBtn', 'click', flyToJordan);

  _on('tileToggleBtn', 'click', () => {
    const map = CsApp.map;
    if (!map) return;
    CsApp.satelliteMode = !CsApp.satelliteMode;
    map.setMapTypeId(CsApp.satelliteMode ? 'satellite' : 'roadmap');
    const btn = document.getElementById('tileToggleBtn');
    if (btn) btn.innerHTML = CsApp.satelliteMode
      ? '<i class="bi bi-globe2" aria-hidden="true"></i> صورة القمر الاصطناعي'
      : '<i class="bi bi-map" aria-hidden="true"></i> خريطة بسيطة';
  });

  _on('rankSearch', 'input', () => {
    clearTimeout(_rankSearchTimer);
    _rankSearchTimer = setTimeout(() => {
      _rankSearch = document.getElementById('rankSearch')?.value || '';
      if (CsApp.mapData) populateRankings(CsApp.mapData.governorates || []);
    }, 300);
  });

  const sortMap = { sortByRisk: 'risk', sortByName: 'name', sortByKgs: 'kgs' };
  Object.keys(sortMap).forEach(id => {
    _on(id, 'click', () => {
      const col = sortMap[id];
      if (_rankSort.col === col) {
        _rankSort.dir = _rankSort.dir === 'desc' ? 'asc' : 'desc';
      } else {
        _rankSort = { col, dir: col === 'name' ? 'asc' : 'desc' };
      }
      document.querySelectorAll('.sort-btn').forEach(b => b.classList.remove('active'));
      document.getElementById(id)?.classList.add('active');
      if (CsApp.mapData) populateRankings(CsApp.mapData.governorates || []);
    });
  });

  _on('exportCsvBtn', 'click', exportAllCSV);
  _on('exportPdfBtn', 'click', exportToPDF);
  _on('printPageBtn', 'click', () => window.print());
}

function flyToJordan() {
  if (CsApp.map) {
    CsApp.map.setCenter(JORDAN_CENTER);
    CsApp.map.setZoom(JORDAN_ZOOM);
  }
  CsApp.selectedGov  = null;
  CsApp.selectedCity = null;
}

// ── Fallback ──────────────────────────────────────────────────────────────────
function showFallback(msg) {
  const c = document.getElementById('googleMapContainer');
  if (c) {
    c.innerHTML = `
      <div class="page-error-state" style="min-height:400px" role="alert">
        <i class="bi bi-exclamation-octagon" style="font-size:3rem;color:#ef4444" aria-hidden="true"></i>
        <h2>تعذر تحميل خريطة جوجل</h2>
        <p style="max-width:380px">${msg || 'يرجى التحقق من الاتصال بالإنترنت وإعادة المحاولة.'}</p>
        <button class="cc-btn" onclick="location.reload()">
          <i class="bi bi-arrow-clockwise" aria-hidden="true"></i> إعادة المحاولة
        </button>
        <p style="margin-top:1rem;font-size:.8rem;color:#475569">
          ملاحظة: جدول التصنيف ومؤشرات الأداء تعمل بشكل مستقل عن الخريطة
        </p>
      </div>`;
    fetchMapData();
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function normName(s) { return s.toLowerCase().trim().replace(/[\s\-']/g, '_'); }
function govNameAr(slug) {
  if (!slug) return '';
  return CsApp.mapData?.governorates?.find(g => g.slug === slug)?.name_ar || slug;
}
function _setEl(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = String(html ?? '--');
}
function _on(id, ev, fn) { document.getElementById(id)?.addEventListener(ev, fn); }

// ── Public API ────────────────────────────────────────────────────────────────
window.selectGovernorate = selectGovernorate;
window.selectCity        = selectCity;
window.resetCityFilter   = resetCityFilter;
window.loadGovDetail     = loadGovDetail;
window.populateRankings  = populateRankings;
window.fetchMapData      = fetchMapData;
window.retryFetchMapData = retryFetchMapData;
window.exportAllCSV      = exportAllCSV;
window.exportToPDF       = exportToPDF;
window.exportGovReport   = exportGovReport;
