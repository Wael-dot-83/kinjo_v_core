/**
 * jordan_cesium_map.js  —  v5
 * Cesium 3D globe for KinJo heatmap admin page.
 *
 * v5 additions vs v4:
 *  - 6-card KPI strip (covered, avg risk, high+critical, critical, facilities, children)
 *  - Rankings table: 8 columns incl. facility count, children, comparison vs national avg
 *  - Client-side CSV export + print-to-PDF
 *  - Per-governorate report export
 *  - Sort & debounced search for rankings table
 *  - Enhanced intel panel: national-avg comparison, action buttons (view / export)
 *  - Page-load timestamp badge
 *  - aria-pressed on risk filter pills
 */

// ── Constants ─────────────────────────────────────────────────────────────────
const JORDAN_CENTER   = { lon: 36.2, lat: 31.0, height: 520000 };
const CLUSTER_HEIGHT  = 280000;   // metres — KG pins hidden above this
const GOVS_GEOJSON    = '/static/data/jordan_governorates.geojson';
const API_MAP_DATA    = '/api/admin/heat-map/data';
const API_GOV_DETAIL  = '/api/admin/heat-map/governorate/';
const API_KG_MAPDATA  = '/api/admin/heat-map/kindergartens/map-data';
const API_GOV_HISTORY = slug => `/api/admin/heat-map/governorate/${slug}/history`;
const API_CITY_DATA   = slug => `/api/admin/heat-map/governorate/${slug}/cities`;
const WS_URL          = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/heatmap`;

const IND_RISK_GETTER = {
  'overall_risk':          g => g.risk_score ?? 0,
  'nursery_status':        g => 100 - (g.main_indicators?.nursery_status        ?? 100),
  'children_registration': g => 100 - (g.main_indicators?.children_registration ?? 100),
  'staff_classrooms':      g => 100 - (g.main_indicators?.staff_classrooms       ?? 100),
  'safety_incidents':      g => 100 - (g.main_indicators?.safety_incidents       ?? 100),
  'reports_attendance':    g => 100 - (g.main_indicators?.reports_attendance     ?? 100),
  'tasks_governance':      g => 100 - (g.main_indicators?.tasks_governance       ?? 100),
};

const IND_LABELS = {
  nursery_status:        { ar: 'حالة الحضانات ورياض الأطفال', color: '#0E334F' },
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

function riskColor(score, alpha) {
  const a = alpha ?? 0.60;
  if (score >= 75) return Cesium.Color.fromCssColorString('#ef4444').withAlpha(a);
  if (score >= 50) return Cesium.Color.fromCssColorString('#f97316').withAlpha(a);
  if (score >= 25) return Cesium.Color.fromCssColorString('#f59e0b').withAlpha(a);
  return Cesium.Color.fromCssColorString('#22c55e').withAlpha(a);
}
function riskHex(score) {
  if (score >= 75) return '#ef4444';
  if (score >= 50) return '#f97316';
  if (score >= 25) return '#f59e0b';
  return '#22c55e';
}
function riskClass(score) { return getRiskLevel(score); }
function riskAr(score) {
  const level = getRiskLevel(score);
  return { low: 'منخفض', medium: 'متوسط', high: 'مرتفع', critical: 'حرج' }[level];
}
function esc(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
function jsString(value) {
  return JSON.stringify(String(value ?? ''));
}

// ── App State ─────────────────────────────────────────────────────────────────
const CsApp = {
  viewer:        null,
  govDS:         null,
  kgEntities:    [],
  mapData:       null,
  selectedGov:   null,
  selectedCity:  null,
  currentInd:    'overall_risk',
  riskFilter:    'all',
  ws:            null,
  wsTimer:       null,
  highlighted:   null,
  warnings:      [],
  kgLoaded:      false,
  dataLoaded:    false,
  _clusterState: null,
  _avgRisk:      0,
};

// ── Rankings state ────────────────────────────────────────────────────────────
let _rankSort   = { col: 'risk', dir: 'desc' };
let _rankSearch = '';
let _rankSearchTimer = null;

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Stamp page-load time
  const ptEl = document.getElementById('pageLoadTime');
  if (ptEl) ptEl.textContent = new Date().toLocaleTimeString('ar-JO');

  if (typeof Cesium === 'undefined') {
    showFallback('Cesium JS failed to load. Check your internet connection.');
    return;
  }
  initCesium().catch(err => {
    console.error('[Cesium] init error:', err);
    showFallback(err.message || 'Failed to initialize 3D globe.');
  });
  bindUiEvents();
});

// ── Cesium Initialisation ─────────────────────────────────────────────────────
async function initCesium() {
  const token = window.CESIUM_ION_TOKEN || '';
  if (token) Cesium.Ion.defaultAccessToken = token;

  // Force Google Earth Satellite Imagery as requested
  const imageryProvider = googleSatelliteImagery();

  let terrainProvider;
  if (token) {
    try { terrainProvider = await Cesium.createWorldTerrainAsync(); }
    catch { terrainProvider = new Cesium.EllipsoidTerrainProvider(); }
  } else {
    terrainProvider = new Cesium.EllipsoidTerrainProvider();
  }

  const viewer = new Cesium.Viewer('cesiumContainer', {
    terrainProvider,
    imageryProvider:      false,
    animation:            false,
    timeline:             false,
    baseLayerPicker:      false,
    homeButton:           false,
    sceneModePicker:      true,
    geocoder:             false,
    navigationHelpButton: false,
    selectionIndicator:   false,
    infoBox:              false,
    shadows:              false,
    shouldAnimate:        false,
    creditContainer:      document.createElement('div'),
  });

  viewer.imageryLayers.addImageryProvider(imageryProvider);
  viewer.scene.backgroundColor      = Cesium.Color.fromCssColorString('#0a0f1a');
  viewer.scene.globe.enableLighting = false;
  viewer.scene.globe.baseColor      = Cesium.Color.fromCssColorString('#0d1b2a');
  viewer.scene.skyBox.show          = false;
  viewer.scene.sun.show             = false;
  viewer.scene.moon.show            = false;

  viewer.camera.setView({
    destination:  Cesium.Cartesian3.fromDegrees(JORDAN_CENTER.lon, JORDAN_CENTER.lat, JORDAN_CENTER.height),
    orientation:  { pitch: Cesium.Math.toRadians(-50) },
  });

  CsApp.viewer = viewer;
  setupInteraction(viewer);
  setupClustering(viewer);
  await loadGovPolygons(viewer);
  await fetchMapData();
  startWebSocket();
}

function googleSatelliteImagery() {
  return new Cesium.UrlTemplateImageryProvider({
    url: 'https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}',
    maximumLevel: 20,
    credit: 'Imagery © Google'
  });
}

function createPinSvg(colorHex, isPulse) {
  const encColor = encodeURIComponent(colorHex);
  const pulseAnim = isPulse ? '<animate attributeName="r" values="4;8;4" dur="1s" repeatCount="indefinite"/>' : '';
  return `data:image/svg+xml;charset=utf-8,%3Csvg width='32' height='40' viewBox='0 0 32 40' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M16 0C7.163 0 0 7.163 0 16c0 11.2 16 24 16 24s16-12.8 16-24C32 7.163 24.837 0 16 0zm0 24c-4.418 0-8-3.582-8-8s3.582-8 8-8 8 3.582 8 8-3.582 8-8 8z' fill='${encColor}' stroke='%23ffffff' stroke-width='2'/%3E%3Ccircle cx='16' cy='16' r='4' fill='%23ffffff'%3E${pulseAnim}%3C/circle%3E%3C/svg%3E`;
}

// ── Camera-height Clustering ──────────────────────────────────────────────────
function setupClustering(viewer) {
  viewer.camera.changed.addEventListener(() => {
    const h     = viewer.camera.positionCartographic?.height ?? 0;
    const inRng = true; // Force pins to always be visible (no clustering)
    const lblRng = h < 120000;
    const prev  = CsApp._clusterState;
    if (prev && prev.range === inRng && prev.label === lblRng) return;
    CsApp._clusterState = { range: inRng, label: lblRng };
    _applyKgVisibility();
  });
}

function _applyKgVisibility() {
  const kgOn  = document.getElementById('kgToggle')?.checked ?? true;
  const h     = CsApp.viewer?.camera.positionCartographic?.height ?? 0;
  const inRng = h < CLUSTER_HEIGHT;
  const lblRng = h < 80000;
  CsApp.kgEntities.forEach(e => {
    if (!e._kgData) return;
    const cityOk = !CsApp.selectedCity || e._kgData.city === CsApp.selectedCity;
    const govOk  = !CsApp.selectedCity || !CsApp.selectedGov?.slug ||
                   e._kgData.governorate === CsApp.selectedGov.slug;
    const vis = kgOn && inRng && cityOk && govOk;
    if (e.point) e.point.show = new Cesium.ConstantProperty(vis);
    if (e.billboard) e.billboard.show = new Cesium.ConstantProperty(vis);
    if (e.label) e.label.show = new Cesium.ConstantProperty(vis && lblRng && !e._isPulseRing);
  });
}

// ── GeoJSON Governorate Polygons ──────────────────────────────────────────────
async function loadGovPolygons(viewer) {
  try {
    const ds = await Cesium.GeoJsonDataSource.load(GOVS_GEOJSON, {
      stroke:        Cesium.Color.WHITE.withAlpha(0.5),
      strokeWidth:   2,
      fill:          Cesium.Color.fromCssColorString('#0EA5E9').withAlpha(0.40),
      clampToGround: true,
    });
    viewer.dataSources.add(ds);
    CsApp.govDS = ds;
  } catch (err) {
    console.error('[Cesium] GeoJSON load failed:', err);
    addWarning('تعذر تحميل حدود المحافظات من ملف الخريطة.');
  }
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
    // Signal supplemental scripts that map data is ready
    document.dispatchEvent(new CustomEvent('heatmapDataReady', { detail: data }));

    await fetchKgPins();
  } catch (err) {
    console.error('[Cesium] map data fetch error:', err);
    addWarning('تعذر تحميل بيانات الخريطة. يرجى التحقق من الاتصال بالخادم.');
    setStatusError();
    renderWarnings();

    // Show retry state in rankings
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
    if (!res.ok) { addWarning('تعذر تحميل بيانات الحضانات ورياض الأطفال على الخريطة.'); return; }
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
    addWarning('تعذر تحميل مواقع الحضانات ورياض الأطفال.');
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
    `<div class="dq-warning"><i class="bi bi-exclamation-triangle-fill" aria-hidden="true"></i> ${esc(w)}</div>`
  ).join('');
}

// ── Colour Governorate Polygons ───────────────────────────────────────────────
function colorGovPolygons(govs) {
  if (!CsApp.govDS) return;
  const byNorm = {};
  govs.forEach(g => {
    if (g.name_en) byNorm[normName(g.name_en)] = g;
    if (g.slug)    byNorm[g.slug.toLowerCase()] = g;
  });

  CsApp.govDS.entities.values.forEach(entity => {
    const props = entity.properties;
    if (!props) return;
    const rawName = String(props.GOVERNORATE_A?.getValue() || '');
    const gov = byNorm[normName(rawName)] || byNorm[rawName.toLowerCase()];
    if (!gov) return;

    entity._govData = gov;
    applyGovColor(entity, gov);

    const center = props.center?.getValue();
    if (center && Array.isArray(center) && center.length >= 2 && !entity._labelAdded) {
      entity.position = Cesium.Cartesian3.fromDegrees(center[0], center[1]);
      entity.label    = new Cesium.LabelGraphics({
        text:                     gov.name_ar || rawName,
        font:                     'bold 13px system-ui,sans-serif',
        fillColor:                Cesium.Color.WHITE,
        outlineColor:             Cesium.Color.fromCssColorString('#0a0f1a'),
        outlineWidth:             3,
        style:                    Cesium.LabelStyle.FILL_AND_OUTLINE,
        heightReference:          Cesium.HeightReference.CLAMP_TO_GROUND,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        scaleByDistance:          new Cesium.NearFarScalar(8e4, 1.0, 9e5, 0.0),
        translucencyByDistance:   new Cesium.NearFarScalar(8e4, 1.0, 9e5, 0.0),
      });
      entity._labelAdded = true;
    }
  });
}

function applyGovColor(entity, gov) {
  if (!entity.polygon) return;
  const getter  = IND_RISK_GETTER[CsApp.currentInd] || IND_RISK_GETTER['overall_risk'];
  const riskVal = getter(gov);
  entity.polygon.material     = new Cesium.ColorMaterialProperty(riskColor(riskVal, 0.55));
  entity.polygon.outlineWidth = new Cesium.ConstantProperty(riskVal >= 50 ? 2.5 : 1.5);
}

function normName(s) {
  return s.toLowerCase().trim().replace(/[\s\-']/g, '_');
}

function govNameAr(slug) {
  if (!slug) return '';
  const gov = CsApp.mapData?.governorates?.find(g => g.slug === slug);
  return gov?.name_ar || slug;
}

// ── Kindergarten Pin Entities ─────────────────────────────────────────────────
function addKgPins(kgs) {
  const viewer = CsApp.viewer;
  CsApp.kgEntities.forEach(e => viewer.entities.remove(e));
  CsApp.kgEntities = [];

  kgs.forEach(kg => {
    const score    = parseFloat(kg.kpi_score) || 0;
    const riskSc   = 100 - score;
    const label    = kg.name_ar || kg.name_en || '';
    const isCrit   = riskSc >= 75;
    const isHigh   = riskSc >= 50;
    const baseSize = isCrit ? 15 : isHigh ? 11 : riskSc >= 25 ? 9 : 7;
    const hexClr   = riskHex(riskSc);
    const c        = Cesium.Color.fromCssColorString(hexClr);

    const pinSize = isCrit
      ? new Cesium.CallbackProperty(
          () => baseSize + 4 * Math.abs(Math.sin(Date.now() / 900)), false)
      : baseSize;

    const pinColor = isCrit
      ? new Cesium.CallbackProperty(
          () => new Cesium.Color(c.red, c.green, c.blue,
                                 0.85 + 0.15 * Math.abs(Math.sin(Date.now() / 900))), false)
      : new Cesium.Color(c.red, c.green, c.blue, isHigh ? 0.95 : 0.88);

    const entity = viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(kg.longitude, kg.latitude, 0),
            billboard: {
        image: '/static/img/real_school_pin.png',
        color: pinColor, // Tint the real image with the risk color
        verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
        heightReference: Cesium.HeightReference.CLAMP_TO_GROUND,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        scale: isCrit ? 1.1 : isHigh ? 0.9 : 0.8,
        scaleByDistance: new Cesium.NearFarScalar(5e3, 1.2, 8e6, 0.4),
      },
      label: {
        text:                     label,
        font:                     '10px system-ui,sans-serif',
        fillColor:                Cesium.Color.WHITE,
        outlineColor:             Cesium.Color.BLACK,
        outlineWidth:             2,
        style:                    Cesium.LabelStyle.FILL_AND_OUTLINE,
        heightReference:          Cesium.HeightReference.CLAMP_TO_GROUND,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        pixelOffset:              new Cesium.Cartesian2(0, -18),
        scaleByDistance:          new Cesium.NearFarScalar(3e3, 1.0, 6e4, 0.0),
        translucencyByDistance:   new Cesium.NearFarScalar(3e3, 1.0, 6e4, 0.0),
      },
    });
    entity._kgData = kg;
    CsApp.kgEntities.push(entity);

    if (isCrit) {
      const halo = viewer.entities.add({
        position: Cesium.Cartesian3.fromDegrees(kg.longitude, kg.latitude, 0),
        point: {
          pixelSize: new Cesium.CallbackProperty(
            () => 34 + 18 * (1 - Math.abs(Math.sin(Date.now() / 900))), false),
          color: new Cesium.CallbackProperty(
            () => new Cesium.Color(1, 0.27, 0.27,
                                   0.45 * (1 - Math.abs(Math.sin(Date.now() / 900)))), false),
          heightReference:          Cesium.HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          scaleByDistance:          new Cesium.NearFarScalar(5e3, 1.8, 5e5, 0.5),
        },
      });
      halo._kgData      = kg;
      halo._isPulseRing = true;
      CsApp.kgEntities.push(halo);
    }
  });

  _setEl('kgCountBadge', kgs.length);
}

// ── Mouse Interaction ─────────────────────────────────────────────────────────
function setupInteraction(viewer) {
  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  const tooltip = document.getElementById('geoTooltip');

  handler.setInputAction(movement => {
    const picked = viewer.scene.pick(movement.endPosition);
    if (!Cesium.defined(picked?.id)) { tooltip.style.display = 'none'; return; }
    const ent = picked.id;
    let html  = '';

    if (ent._govData) {
      const g     = ent._govData;
      const score = g.risk_score ?? 0;
      const getter = IND_RISK_GETTER[CsApp.currentInd];
      const ind   = CsApp.currentInd !== 'overall_risk' && getter ? CsApp.currentInd : null;
      let indRow  = '';
      if (ind && g.main_indicators?.[ind] != null) {
        const v   = g.main_indicators[ind];
        const lbl = IND_LABELS[ind];
        indRow = `<div class="tt-row"><span>${lbl?.ar || ind}</span><b style="color:${riskHex(100-v)}">${v.toFixed(1)}</b></div>`;
      }
      html = `
        <div class="tt-name">${esc(g.name_ar || g.name_en)}</div>
        <div class="tt-badge"><span class="rank-badge risk-${riskClass(score)}">${riskAr(score)}</span></div>
        <div class="tt-divider"></div>
        <div class="tt-row"><span>درجة الخطر</span><b style="color:${riskHex(score)}">${score.toFixed(1)}/100</b></div>
        ${indRow}
        <div class="tt-row"><span>إجمالي المنشآت</span><b>${esc(g.kg_count ?? '--')}</b></div>
        <div class="tt-row"><span>الأطفال النشطون</span><b>${esc(g.student_count ?? '--')}</b></div>
        <div class="tt-hint">انقر للتفاصيل الكاملة</div>`;

    } else if (ent._kgData && !ent._isPulseRing) {
      const k      = ent._kgData;
      const score  = parseFloat(k.kpi_score) || 0;
      const riskSc = 100 - score;
      const govAr  = govNameAr(k.governorate) || k.governorate_name_en || '';
      const cityTxt = k.city ? `<div class="tt-row"><span>المدينة</span><b>${esc(k.city)}</b></div>` : '';
      html = `
        <div class="tt-name">${esc(k.name_ar || k.name_en || 'منشأة')}</div>
        <div class="tt-badge"><span class="rank-badge risk-${riskClass(riskSc)}">${riskAr(riskSc)}</span></div>
        <div class="tt-divider"></div>
        <div class="tt-row"><span>المحافظة</span><b>${esc(govAr)}</b></div>
        ${cityTxt}
        <div class="tt-row"><span>مؤشر الخطر المباشر</span><b style="color:${riskHex(riskSc)}">${riskSc.toFixed(1)}/100</b></div>
        <div class="tt-hint" style="color:#0ea5e9;font-weight:bold;margin-top:8px;">
           <i class="bi bi-broadcast" style="animation: pulse 1.5s infinite"></i> عرض بيانات المراقبة الحية
        </div>`;
    }

    if (html) {
      tooltip.innerHTML       = html;
      tooltip.style.display   = 'block';
      tooltip.setAttribute('aria-hidden', 'false');
      const { x, y }          = movement.endPosition;
      tooltip.style.left      = `${x + 14}px`;
      tooltip.style.top       = `${y - 10}px`;
    } else {
      tooltip.style.display   = 'none';
      tooltip.setAttribute('aria-hidden', 'true');
    }
  }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

  handler.setInputAction(click => {
    tooltip.style.display = 'none';
    const picked = viewer.scene.pick(click.position);
    if (!Cesium.defined(picked?.id)) return;
    const ent = picked.id;
    if (ent._govData)                selectGovernorate(ent._govData);
    else if (ent._kgData && !ent._isPulseRing) showKgDetail(ent._kgData);
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
}

// ── Governorate Selection ─────────────────────────────────────────────────────
function selectGovernorate(gov) {
  CsApp.selectedGov  = gov;
  CsApp.selectedCity = null;

  document.querySelectorAll('.cs-gov-item').forEach(el =>
    el.classList.toggle('selected', el.dataset.slug === gov.slug)
  );

  // Update selected row in rankings
  document.querySelectorAll('#rankingsTable tbody tr').forEach(tr =>
    tr.classList.toggle('rank-selected', tr.dataset.slug === gov.slug)
  );

  const entity = CsApp.govDS?.entities.values.find(e => e._govData?.slug === gov.slug);
  const center = entity?.properties?.center?.getValue();
  const lon    = gov.center?.[0] ?? center?.[0];
  const lat    = gov.center?.[1] ?? center?.[1];
  if (lon != null && lat != null && CsApp.viewer) {
    CsApp.viewer.camera.flyTo({
      destination:  Cesium.Cartesian3.fromDegrees(lon, lat, 120000),
      orientation:  { pitch: Cesium.Math.toRadians(-40) },
      duration:     1.4,
    });
  }

  highlightGovEntity(gov.slug);
  loadGovDetail(gov.slug);
  loadGovTimeSeries(gov.slug);
}

function highlightGovEntity(slug) {
  if (CsApp.highlighted) {
    applyGovColor(CsApp.highlighted, CsApp.highlighted._govData);
    if (CsApp.highlighted.polygon) {
      CsApp.highlighted.polygon.outline      = new Cesium.ConstantProperty(false);
      CsApp.highlighted.polygon.outlineWidth = new Cesium.ConstantProperty(1);
    }
    CsApp.highlighted = null;
  }
  const entity = CsApp.govDS?.entities.values.find(e => e._govData?.slug === slug);
  if (entity?.polygon) {
    entity.polygon.material     = new Cesium.ColorMaterialProperty(Cesium.Color.WHITE.withAlpha(0.22));
    entity.polygon.outline      = new Cesium.ConstantProperty(true);
    entity.polygon.outlineColor = new Cesium.ConstantProperty(Cesium.Color.WHITE.withAlpha(0.95));
    entity.polygon.outlineWidth = new Cesium.ConstantProperty(3);
    CsApp.highlighted = entity;
  }
}

// ── Governorate Detail Panel ──────────────────────────────────────────────────
async function loadGovDetail(slug) {
  const panel = document.getElementById('intelPanel');
  const retrySlug = jsString(slug);
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
        <button class="cc-btn" onclick="loadGovDetail(${retrySlug})">
          <i class="bi bi-arrow-clockwise" aria-hidden="true"></i> إعادة المحاولة
        </button>
      </div>`;
  }
}

// ── SVG Radar Chart ───────────────────────────────────────────────────────────
function renderRadarChart(perfIndicators) {
  const SZ = 148, CX = SZ / 2, CY = SZ / 2, MAX_R = SZ * 0.36;
  const N   = IND_ORDER.length;
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

  const vals = IND_ORDER.map(k => perfIndicators?.[k] ?? 0);
  const poly = vals.map((v, i) => { const p = pt(MAX_R * v / 100, i); return `${p.x},${p.y}`; }).join(' ');
  const avg  = vals.reduce((s, v) => s + v, 0) / vals.length;
  const fc   = riskHex(100 - avg);

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
    const perf  = d.main_indicators?.[key] ?? 0;
    const meta  = IND_LABELS[key] || {};
    const trend = d.trends?.[key];
    const color = meta.color || riskHex(100 - perf);
    const trendIcon = !trend ? '' :
      trend.direction === 'up'   ? `<i class="bi bi-arrow-up-short" style="color:#22c55e" aria-hidden="true"></i><small style="color:#22c55e;font-size:.65rem">${trend.pct != null ? trend.pct.toFixed(1)+'%' : ''}</small>` :
      trend.direction === 'down' ? `<i class="bi bi-arrow-down-short" style="color:#ef4444" aria-hidden="true"></i><small style="color:#ef4444;font-size:.65rem">${trend.pct != null ? trend.pct.toFixed(1)+'%' : ''}</small>` : '';
    return `
      <div class="intel-ind-row" style="flex-direction:column;align-items:stretch;margin-bottom:.625rem">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:2px">
          <span class="intel-ind-label">${meta.ar || key}</span>
          <span style="display:flex;align-items:center;gap:.15rem;font-size:.75rem;font-weight:700;color:${color}">${perf.toFixed(1)}${trendIcon}</span>
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
         ${esc(action.ar || action.en)}
       </div>` : '';

  const sub          = d.sub_indicators || {};
  const kgCount      = sub.active_nurseries    ?? d.kg_count      ?? 'غير متوفر';
  const studentCount = sub.registered_children ?? d.student_count ?? 'غير متوفر';
  const govScore     = sub.governance_score     != null ? sub.governance_score.toFixed(1) : 'غير متوفر';
  const safeSlug     = jsString(d.slug || d.code || '');
  const safeName     = jsString(d.name_ar || d.name_en || '');
  const safeNameHtml = esc(d.name_ar || d.name_en || '');

  panel.innerHTML = `
    <div class="intel-gov-header">
      <div class="intel-gov-namerow">
        <h3 class="intel-gov-name">${esc(d.name_ar || d.name_en || '')}</h3>
        <span class="intel-gov-code">${esc((d.code || d.slug || '').toUpperCase())}</span>
      </div>
      <div class="intel-gov-name-sub">${esc(d.name_en || '')}</div>
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
                onclick="window.location.href='/admin/kindergartens?governorate=' + encodeURIComponent(${safeSlug})"
                aria-label="عرض منشآت ${safeNameHtml}">
          <i class="bi bi-building" aria-hidden="true"></i> عرض المنشآت
        </button>
        <button class="cc-btn intel-action-btn"
                onclick="exportGovReport(${safeSlug}, ${safeName})"
                aria-label="تصدير تقرير ${safeNameHtml}">
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
          <span class="intel-loading-spinner" style="width:14px;height:14px;border-width:1.5px" aria-hidden="true"></span>
          جاري التحميل…
        </div>
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
      <div style="font-size:.7rem;color:#475569">المصدر: قاعدة بيانات كينجو المركزية</div>
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

  if (errorMsg) {
    body.innerHTML = `<div class="intel-no-alerts">${esc(errorMsg)}</div>`;
    return;
  }

  const cities   = cityData?.cities || [];
  const warnings = cityData?.warnings || [];

  if (counter) counter.textContent = cities.length ? `(${cities.length})` : '';

  if (!cities.length) {
    const msg = warnings[0] || (cityData?.data_status === 'empty'
      ? 'لا تتوفر بيانات المدن لهذه المحافظة حالياً.'
      : 'لا توجد مدن مسجلة لهذه المحافظة.');
    body.innerHTML = `<div class="intel-no-alerts">${esc(msg)}</div>`;
    return;
  }

  body.innerHTML = cities.map(c => {
    const riskSc   = c.risk_score ?? 0;
    const cls      = riskClass(riskSc);
    const kgLabel  = `${esc(c.kindergarten_count)} منشأة`;
    const stLabel  = c.children_count ? `· ${esc(c.children_count)} طفل` : '';
    const critLabel = c.critical_kindergartens
      ? `<span style="color:#ef4444;font-size:.7rem"> — ${c.critical_kindergartens} حرجة</span>` : '';
    const safeCity = jsString(c.city || '');
    const cityName = esc(c.city || '');
    return `
      <div class="city-row" data-city="${cityName}"
           role="button" tabindex="0"
           aria-label="${cityName} — خطر: ${riskAr(riskSc)}"
           onclick="selectCity(${safeCity})"
           onkeydown="if(event.key==='Enter'||event.key===' ')selectCity(${safeCity})">
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
  const govSlug = CsApp.selectedGov?.slug || null;

  const cityKgs = CsApp.kgEntities.filter(e =>
    !e._isPulseRing && e._kgData?.city === cityName &&
    (!govSlug || e._kgData?.governorate === govSlug)
  );
  if (cityKgs.length && CsApp.viewer) {
    const avgLon = cityKgs.reduce((s, e) => s + (e._kgData.longitude || 0), 0) / cityKgs.length;
    const avgLat = cityKgs.reduce((s, e) => s + (e._kgData.latitude  || 0), 0) / cityKgs.length;
    CsApp.viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(avgLon, avgLat, 55000),
      orientation: { pitch: Cesium.Math.toRadians(-45) },
      duration:    1.2,
    });
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
  const name    = esc(kg.name_ar || kg.name_en || 'منشأة');
  const govAr   = esc(govNameAr(kg.governorate) || kg.governorate_name_en || '');
  const cityTxt = kg.city ? ` • ${esc(kg.city)}` : '';
  const sc      = kg.supporting_counts || {};
  const mainInds = kg.main_indicators || {};

  const indHtml = IND_ORDER.map(key => {
    const ind   = mainInds[key];
    const perf  = ind?.score ?? 0;
    const meta  = IND_LABELS[key] || {};
    const color = ind?.color || meta.color || riskHex(100 - perf);
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
      <div class="intel-section-title" style="color:#0ea5e9;font-size:1rem;display:flex;align-items:center;gap:0.5rem;">
          <div class="live-dot" aria-hidden="true" style="background:#0ea5e9;width:10px;height:10px;"></div> 
          بيانات المراقبة الحية
        </div>
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

// ── Time-Series ───────────────────────────────────────────────────────────────
async function loadGovTimeSeries(slug) {
  try {
    const res = await fetch(API_GOV_HISTORY(slug), { credentials: 'include' });
    if (!res.ok) return;
    const data   = await res.json();
    const points = data.history || [];
    if (points.length < 2 || !CsApp.viewer) return;

    const viewer = CsApp.viewer;
    const now    = Cesium.JulianDate.now();
    const start  = Cesium.JulianDate.addDays(now, -6, new Cesium.JulianDate());
    viewer.clock.startTime   = start;
    viewer.clock.stopTime    = now;
    viewer.clock.currentTime = now;
    viewer.clock.clockRange  = Cesium.ClockRange.LOOP_STOP;
    viewer.clock.multiplier  = 86400;

    const entity = CsApp.govDS?.entities.values.find(e => e._govData?.slug === slug);
    if (!entity?.polygon) return;

    const colorProp = new Cesium.SampledProperty(Cesium.Color);
    colorProp.setInterpolationOptions({
      interpolationDegree:    1,
      interpolationAlgorithm: Cesium.LinearApproximation,
    });
    points.forEach(pt => {
      try {
        const t = Cesium.JulianDate.fromIso8601(pt.date + 'T00:00:00Z');
        const c = riskColor(pt.risk_score ?? 0, 0.65);
        colorProp.addSample(t, c);
      } catch { /* skip malformed dates */ }
    });
    entity.polygon.material = new Cesium.ColorMaterialProperty(colorProp);
  } catch { /* time-series is optional */ }
}

// ── Left Panel — Governorate List ─────────────────────────────────────────────
function populateGovList(govs) {
  const list = document.getElementById('govListBody');
  if (!list) return;
  list.innerHTML = govs.map(g => {
    const score   = g.risk_score ?? 0;
    const cls     = riskClass(score);
    const govJson = esc(JSON.stringify(g));
    const kgLabel = g.kg_count != null
      ? `<span style="font-size:.7rem;color:#64748b">${g.kg_count} منشأة</span>` : '';
    return `
      <div class="cs-gov-item" data-slug="${esc(g.slug)}" data-risk-class="${cls}"
           tabindex="0" role="button"
           aria-label="${esc(g.name_ar || g.name_en)} — ${riskAr(score)}"
           onclick="selectGovernorate(${govJson})"
           onkeydown="if(event.key==='Enter'||event.key===' ')selectGovernorate(${govJson})">
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

// ── KPI Strip — 6 heatmap-specific cards ──────────────────────────────────────
function updateKpiStrip(data) {
  const govs     = data.governorates || [];
  const sum      = data.summary || {};

  const avgRisk  = sum.average_risk    != null ? sum.average_risk
    : govs.length ? govs.reduce((s, g) => s + (g.risk_score || 0), 0) / govs.length : 0;
  const highRisk = sum.high_risk_count != null ? sum.high_risk_count
    : govs.filter(g => (g.risk_score || 0) >= 50).length;
  const totalSt  = govs.reduce((s, g) => s + (g.student_count || 0), 0);
  const covered  = govs.filter(g => g.risk_score != null).length || govs.length;

  // Top governorate by risk score
  const topGov   = govs.length
    ? [...govs].sort((a, b) => (b.risk_score || 0) - (a.risk_score || 0))[0]
    : null;

  // Incident proxy: deficit of safety_incidents indicator × kg density
  const totalInc = govs.reduce((s, g) => {
    const si = Math.max(0, 100 - (g.main_indicators?.safety_incidents ?? 100));
    return s + Math.round((si / 100) * (g.kg_count || 1) * 1.8);
  }, 0);

  CsApp._avgRisk = avgRisk;

  // Populate new command-center KPI element IDs
  _setEl('kpiTotalIncidents',    totalInc > 0 ? totalInc.toLocaleString('ar-JO') : '--');
  _setEl('kpiTotalIncidentsSub', totalInc > 0 ? 'حادثة مسجلة' : 'لا توجد بيانات');
  if (topGov) {
    _setEl('kpiTopGov',      topGov.name_ar || topGov.name_en || '--');
    _setEl('kpiTopGovScore', `مؤشر الخطر: ${(topGov.risk_score || 0).toFixed(1)}`);
  }
  _setEl('kpiNeedFollowup',    highRisk || '--');
  _setEl('kpiOverallRisk',     avgRisk.toFixed(1));
  _setEl('kpiPendingApps',     totalSt > 0 ? totalSt.toLocaleString('ar-JO') : '--');
  _setEl('kpiDataQuality',     `${Math.round((covered / 12) * 100)}%`);
  _setEl('kpiDataQualitySub',  `${covered} من 12 محافظة`);

  _setEl('alertCountStatus',
    `<i class="bi bi-shield-exclamation" aria-hidden="true"></i> ${highRisk} محافظة مرتفعة أو حرجة الخطر`);

  // Populate last-update timestamp in risk legend
  if (data.summary?.last_update) {
    _setEl('lastMapUpdate', new Date(data.summary.last_update).toLocaleString('ar-JO'));
  }
}

// KPI click handler — also used by heatmap_cc.js
window.handleKpiClick = function (type) {
  if (type === 'incidents') {
    document.getElementById('chartsSection')
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } else if (type === 'topgov') {
    const govs  = CsApp.mapData?.governorates || [];
    const top   = govs.length
      ? [...govs].sort((a, b) => (b.risk_score || 0) - (a.risk_score || 0))[0]
      : null;
    if (top) selectGovernorate(top);
  } else if (type === 'followup') {
    // Reset sidebar filter to "all" so both high AND critical govs are visible,
    // then scroll to the rankings table where they appear sorted by risk score desc.
    const allBtn = document.querySelector('.risk-filter-btn[data-risk="all"]');
    if (allBtn) allBtn.click();
    document.querySelector('.rankings-section')
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } else if (type === 'apps') {
    document.querySelector('.rankings-section')
      ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
};

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

  // Search filter
  if (q) {
    list = list.filter(g =>
      (g.name_ar || '').includes(q) ||
      (g.name_en || '').toLowerCase().includes(q)
    );
  }

  // Sort
  list.sort((a, b) => {
    if (_rankSort.col === 'name') {
      const na = a.name_ar || a.name_en || '';
      const nb = b.name_ar || b.name_en || '';
      return _rankSort.dir === 'asc'
        ? na.localeCompare(nb, 'ar')
        : nb.localeCompare(na, 'ar');
    }
    const va = _rankSort.col === 'kgs'
      ? (a.kg_count || 0)
      : (a.risk_score || 0);
    const vb = _rankSort.col === 'kgs'
      ? (b.kg_count || 0)
      : (b.risk_score || 0);
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
      ? `<small style="color:#64748b">${esc(IND_LABELS[CsApp.currentInd]?.ar || CsApp.currentInd)}: ${indVal.toFixed(0)}</small>`
      : '';

    // Compare to national average
    const diff = score - avgRisk;
    const compHtml = avgRisk > 0
      ? diff > 2
        ? `<span class="compare-up" title="أعلى من المتوسط بـ ${diff.toFixed(1)}">↑ ${diff.toFixed(1)}</span>`
        : diff < -2
        ? `<span class="compare-dn" title="أقل من المتوسط بـ ${Math.abs(diff).toFixed(1)}">↓ ${Math.abs(diff).toFixed(1)}</span>`
        : `<span class="compare-eq">≈</span>`
      : '<span class="compare-eq">--</span>';

    const kgCount = g.kg_count      != null ? g.kg_count      : '--';
    const stCount = g.student_count != null ? g.student_count : '--';
    const govJson = esc(JSON.stringify(g));
    const safeName = jsString(g.name_ar || g.name_en || '');
    const safeSlug = jsString(g.slug || '');

    const tr = document.createElement('tr');
    tr.dataset.slug = g.slug;
    if (CsApp.selectedGov?.slug === g.slug) tr.classList.add('rank-selected');
    tr.onclick = () => selectGovernorate(g);

    tr.innerHTML = `
      <td><span class="rank-num ${numCls}">${rank}</span></td>
      <td>
        <div class="rank-name">${esc(g.name_ar || g.name_en)}</div>
        <div class="rank-code">${esc(g.name_en || '')} ${indCell}</div>
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
      <td>
        <span class="rank-badge risk-${cls}">
          ${riskAr(score)}
        </span>
      </td>
      <td style="font-size:.8rem">${compHtml}</td>
      <td>
        <div class="rank-actions">
          <button class="rank-drill"
                  onclick="event.stopPropagation();selectGovernorate(${govJson})"
                  title="عرض التفاصيل"
                  aria-label="عرض تفاصيل ${esc(g.name_ar || '')}">
            <i class="bi bi-info-circle" aria-hidden="true"></i>
          </button>
          <button class="rank-drill"
                  onclick="event.stopPropagation();selectGovernorate(${govJson})"
                  title="تحليل المحافظة"
                  aria-label="تحليل ${esc(g.name_ar || '')}">
            <i class="bi bi-graph-up" aria-hidden="true"></i>
          </button>
          <button class="rank-drill"
                  onclick="event.stopPropagation();exportGovReport(${safeSlug}, ${safeName})"
                  title="تصدير التقرير"
                  aria-label="تصدير تقرير ${esc(g.name_ar || '')}">
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
      toast:            true,
      position:         'top-end',
      icon:             type || 'info',
      title:            message,
      showConfirmButton: false,
      timer:            3000,
      timerProgressBar: true,
    });
    return;
  }
  // Fallback: update status chip
  const chip = document.getElementById('lastUpdateStatus');
  if (!chip) return;
  const old = chip.innerHTML;
  chip.innerHTML = `<i class="bi bi-info-circle" aria-hidden="true"></i> ${esc(message)}`;
  setTimeout(() => { if (chip) chip.innerHTML = old; }, 3500);
}

function _downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a   = document.createElement('a');
  a.href     = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function exportAllCSV() {
  if (!CsApp.mapData?.governorates?.length) {
    showHeatmapToast('لا توجد بيانات للتصدير', 'warning');
    return;
  }
  showHeatmapToast('جاري تجهيز التقرير...', 'info');

  const govs    = CsApp.mapData.governorates;
  const avgRisk = CsApp._avgRisk || 0;
  const headers = [
    'المحافظة', 'الاسم الإنجليزي', 'إجمالي المنشآت',
    'الأطفال النشطون', 'مؤشر الخطر', 'مستوى الخطر', 'مقارنة بالمتوسط الوطني',
  ];
  const rows = govs
    .sort((a, b) => (b.risk_score || 0) - (a.risk_score || 0))
    .map(g => [
      g.name_ar || '',
      g.name_en || '',
      g.kg_count      ?? '',
      g.student_count ?? '',
      (g.risk_score || 0).toFixed(1),
      riskAr(g.risk_score || 0),
      avgRisk > 0 ? ((g.risk_score || 0) - avgRisk).toFixed(1) : '',
    ]);

  const csv = '﻿' + [headers, ...rows]
    .map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
    .join('\r\n');

  _downloadBlob(
    new Blob([csv], { type: 'text/csv;charset=utf-8;' }),
    `kinjo_heatmap_${new Date().toISOString().split('T')[0]}.csv`
  );
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
  if (!gov) {
    setTimeout(() => showHeatmapToast('تعذر تجهيز التقرير، جرب مجدداً', 'error'), 800);
    return;
  }

  const avgRisk = CsApp._avgRisk || 0;
  const diff    = (gov.risk_score || 0) - avgRisk;
  const lines   = [
    '=== تقرير محافظة: ' + (gov.name_ar || gov.name_en) + ' ===',
    '',
    'الاسم بالعربية   : ' + (gov.name_ar || 'غير متوفر'),
    'الاسم بالإنجليزية: ' + (gov.name_en || 'غير متوفر'),
    'مؤشر الخطر      : ' + (gov.risk_score || 0).toFixed(1) + ' / 100',
    'مستوى الخطر     : ' + riskAr(gov.risk_score || 0),
    'إجمالي المنشآت  : ' + (gov.kg_count      ?? 'غير متوفر'),
    'الأطفال النشطون  : ' + (gov.student_count ?? 'غير متوفر'),
    avgRisk > 0
      ? 'مقارنة بالمتوسط  : ' + (diff >= 0 ? '+' : '') + diff.toFixed(1) + ' نقطة'
      : '',
    '',
    '--- المؤشرات الرئيسية ---',
    ...Object.entries(gov.main_indicators || {}).map(([k, v]) =>
      (IND_LABELS[k]?.ar || k) + ': ' + (typeof v === 'number' ? v.toFixed(1) : (v ?? 'غير متوفر'))
    ),
    '',
    '--- معلومات التقرير ---',
    'تاريخ التصدير : ' + new Date().toLocaleString('ar-JO'),
    'المصدر        : قاعدة بيانات كينجو المركزية',
    'وزارة التنمية الاجتماعية — المملكة الأردنية الهاشمية',
  ].filter(l => l !== null && l !== undefined);

  _downloadBlob(
    new Blob(['﻿' + lines.join('\r\n')], { type: 'text/plain;charset=utf-8;' }),
    `kinjo_gov_${slug}_${new Date().toISOString().split('T')[0]}.txt`
  );
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
          colorGovPolygons(msg.governorates);
          updateKpiStrip({ governorates: msg.governorates });
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
  if (chip) {
    chip.className = 'status-chip live';
    chip.innerHTML = '<div class="live-dot" aria-hidden="true"></div> بيانات مباشرة';
  }
  _setEl('lastUpdateStatus',
    `<i class="bi bi-clock" aria-hidden="true"></i> ${new Date().toLocaleTimeString('ar-JO')}`);
}
function setStatusError() {
  const chip = document.getElementById('dataStatus');
  if (chip) {
    chip.className = 'status-chip error';
    chip.innerHTML = '<i class="bi bi-exclamation-triangle" aria-hidden="true"></i> خطأ في الاتصال';
  }
}

// ── UI Event Bindings ─────────────────────────────────────────────────────────
function bindUiEvents() {

  _on('indicatorViewSelect', 'change', () => {
    const sel         = document.getElementById('indicatorViewSelect');
    CsApp.currentInd  = sel?.value || 'overall_risk';
    if (CsApp.govDS && CsApp.mapData) {
      colorGovPolygons(CsApp.mapData.governorates || []);
      if (CsApp.highlighted?._govData) highlightGovEntity(CsApp.highlighted._govData.slug);
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

  // KG pins toggle
  _on('kgToggle', 'change', _applyKgVisibility);

  // Governorate label toggle
  _on('govBadgeToggle', 'change', () => {
    const show = document.getElementById('govBadgeToggle')?.checked ?? true;
    CsApp.govDS?.entities.values.forEach(e => {
      if (e.label) e.label.show = new Cesium.ConstantProperty(show);
    });
  });

  // Governorate polygon overlay toggle
  _on('govOverlayToggle', 'change', () => {
    if (CsApp.govDS) CsApp.govDS.show = document.getElementById('govOverlayToggle')?.checked ?? true;
  });

  // Governorate list search (debounced)
  let govSearchTimer;
  _on('govSearch', 'input', () => {
    clearTimeout(govSearchTimer);
    govSearchTimer = setTimeout(applyGovListFilter, 250);
  });

  // Risk level filter pills
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

  _on('csColumbusBtn', 'click', () => {
    const viewer = CsApp.viewer;
    if (!viewer) return;
    const btn = document.getElementById('csColumbusBtn');
    if (viewer.scene.mode === Cesium.SceneMode.COLUMBUS_VIEW) {
      viewer.scene.morphTo3D(1.0);
      if (btn) btn.innerHTML = '<i class="bi bi-layers" aria-hidden="true"></i> 2.5D';
    } else {
      viewer.scene.morphToColumbusView(1.0);
      if (btn) btn.innerHTML = '<i class="bi bi-globe2" aria-hidden="true"></i> 3D';
    }
  });

  _on('csPlayBtn', 'click', () => {
    const viewer = CsApp.viewer;
    if (!viewer) return;
    viewer.clock.shouldAnimate = !viewer.clock.shouldAnimate;
    const btn = document.getElementById('csPlayBtn');
    if (btn) btn.innerHTML = viewer.clock.shouldAnimate
      ? '<i class="bi bi-pause-fill" aria-hidden="true"></i>'
      : '<i class="bi bi-play-fill" aria-hidden="true"></i>';
  });

  _on('tileToggleBtn', 'click', () => {
    const viewer = CsApp.viewer;
    if (!viewer || viewer.imageryLayers.length === 0) return;
    const layer = viewer.imageryLayers.get(0);
    layer.show  = !layer.show;
    const btn   = document.getElementById('tileToggleBtn');
    if (btn) btn.innerHTML = layer.show
      ? '<i class="bi bi-globe2" aria-hidden="true"></i> صورة القمر الاصطناعي'
      : '<i class="bi bi-map" aria-hidden="true"></i> خريطة بسيطة';
  });

  // Rankings: debounced search
  _on('rankSearch', 'input', () => {
    clearTimeout(_rankSearchTimer);
    _rankSearchTimer = setTimeout(() => {
      _rankSearch = document.getElementById('rankSearch')?.value || '';
      if (CsApp.mapData) populateRankings(CsApp.mapData.governorates || []);
    }, 300);
  });

  // Rankings: sort buttons
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

  // Export buttons
  _on('exportCsvBtn', 'click', exportAllCSV);
  _on('exportPdfBtn', 'click', exportToPDF);
  _on('printPageBtn', 'click', () => window.print());
}

function flyToJordan() {
  CsApp.viewer?.camera.flyTo({
    destination:  Cesium.Cartesian3.fromDegrees(JORDAN_CENTER.lon, JORDAN_CENTER.lat, JORDAN_CENTER.height),
    orientation:  { pitch: Cesium.Math.toRadians(-50) },
    duration:     1.5,
  });
}

// ── Fallback ──────────────────────────────────────────────────────────────────
function showFallback(msg) {
  const c = document.getElementById('cesiumContainer');
  if (c) {
    c.innerHTML = `
      <div class="page-error-state" style="min-height:400px" role="alert">
        <i class="bi bi-exclamation-octagon" style="font-size:3rem;color:#ef4444" aria-hidden="true"></i>
        <h2>تعذر تحميل خريطة Cesium ثلاثية الأبعاد</h2>
        <p style="max-width:380px">${esc(msg || 'يرجى التحقق من الاتصال بالإنترنت وإعادة المحاولة.')}</p>
        <button class="cc-btn" onclick="location.reload()">
          <i class="bi bi-arrow-clockwise" aria-hidden="true"></i> إعادة المحاولة
        </button>
        <p style="margin-top:1rem;font-size:.8rem;color:#475569">
          ملاحظة: جدول التصنيف ومؤشرات الأداء تعمل بشكل مستقل عن الخريطة
        </p>
      </div>`;
    // Still try to load data for the table/KPIs
    fetchMapData();
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function _setEl(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = String(html ?? '--');
}
function _on(id, ev, fn) {
  document.getElementById(id)?.addEventListener(ev, fn);
}

// ── Public API ────────────────────────────────────────────────────────────────
window.selectGovernorate  = selectGovernorate;
window.selectCity         = selectCity;
window.resetCityFilter    = resetCityFilter;
window.loadGovDetail      = loadGovDetail;
window.populateRankings   = populateRankings;
window.fetchMapData       = fetchMapData;
window.retryFetchMapData  = retryFetchMapData;
window.exportAllCSV       = exportAllCSV;
window.exportToPDF        = exportToPDF;
window.exportGovReport    = exportGovReport;
window.CsApp              = CsApp;
