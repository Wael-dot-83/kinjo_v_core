/**
 * jordan_cesium_map.js  —  v4 (visual + performance + interactivity)
 * Cesium 3D globe for KinJo heatmap admin page.
 *
 * v4 changes vs v3:
 *  - Polygon fill opacity boosted; stroke width scales with risk level
 *  - KG pin size scales by risk (7/9/11/15 px); critical pins animate via CallbackProperty
 *  - Critical KG expanding halo pulse ring (transparent point entity)
 *  - Camera-height clustering: KG pins hidden above CLUSTER_HEIGHT (280 km)
 *  - SVG radar chart rendered inside governorate / KG intel panel
 *  - Risk-level filter pills in left panel (منخفض/متوسط/مرتفع/حرج/الكل)
 *  - Governorate polygon overlay toggle (govOverlayToggle)
 *  - selectCity flies camera to city KG centroid
 *  - Centralised _applyKgVisibility() replaces duplicated show/hide logic
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
  nursery_status:        { ar: 'حالة الروضات',       color: '#0E334F' },
  children_registration: { ar: 'الأطفال والتسجيل',   color: '#28A745' },
  staff_classrooms:      { ar: 'الموظفون والفصول',   color: '#155ECF' },
  safety_incidents:      { ar: 'السلامة والحوادث',   color: '#FFC107' },
  reports_attendance:    { ar: 'التقارير والحضور',   color: '#06B6D4' },
  tasks_governance:      { ar: 'المهام والحوكمة',    color: '#8B5CF6' },
};

const IND_ORDER = [
  'nursery_status', 'children_registration', 'staff_classrooms',
  'safety_incidents', 'reports_attendance', 'tasks_governance',
];

// ── Risk helpers ──────────────────────────────────────────────────────────────
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
function riskClass(score) {
  if (score >= 75) return 'critical';
  if (score >= 50) return 'high';
  if (score >= 25) return 'medium';
  return 'low';
}
function riskAr(score) {
  if (score >= 75) return 'حرج';
  if (score >= 50) return 'مرتفع';
  if (score >= 25) return 'متوسط';
  return 'منخفض';
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
  riskFilter:    'all',       // 'all'|'low'|'medium'|'high'|'critical'
  ws:            null,
  wsTimer:       null,
  highlighted:   null,
  warnings:      [],
  kgLoaded:      false,
  dataLoaded:    false,
  _clusterState: null,        // tracks last { range, label } to avoid redundant passes
};

// ── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
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

  let imageryProvider;
  if (token) {
    try { imageryProvider = await Cesium.IonImageryProvider.fromAssetId(3); }
    catch { imageryProvider = esriImagery(); }
  } else {
    imageryProvider = esriImagery();
  }

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

function esriImagery() {
  return new Cesium.UrlTemplateImageryProvider({
    url:          'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    maximumLevel: 19,
  });
}

// ── Camera-height Clustering ──────────────────────────────────────────────────
function setupClustering(viewer) {
  viewer.camera.changed.addEventListener(() => {
    const h    = viewer.camera.positionCartographic?.height ?? 0;
    const inRng = h < CLUSTER_HEIGHT;
    const lblRng = h < 80000;
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
    if (e.label) e.label.show = new Cesium.ConstantProperty(vis && lblRng && !e._isPulseRing);
  });
}

// ── GeoJSON Governorate Polygons ──────────────────────────────────────────────
async function loadGovPolygons(viewer) {
  try {
    const ds = await Cesium.GeoJsonDataSource.load(GOVS_GEOJSON, {
      stroke:        Cesium.Color.WHITE.withAlpha(0.5),
      strokeWidth:   2,
      fill:          Cesium.Color.fromCssColorString('#2F7D62').withAlpha(0.40),
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

    await fetchKgPins();
  } catch (err) {
    console.error('[Cesium] map data fetch error:', err);
    addWarning('تعذر تحميل بيانات الخريطة. يرجى التحقق من الاتصال بالخادم.');
    setStatusError();
    renderWarnings();
  }
}

async function fetchKgPins() {
  try {
    const res = await fetch(API_KG_MAPDATA, { credentials: 'include' });
    if (!res.ok) { addWarning('تعذر تحميل بيانات الروضات على الخريطة.'); return; }
    const geojson  = await res.json();
    const features = geojson.features || [];
    const kgs = features.map(f => ({
      ...f.properties,
      longitude: f.geometry?.coordinates?.[0],
      latitude:  f.geometry?.coordinates?.[1],
    })).filter(k => k.longitude != null && k.latitude != null);

    if (geojson.missing_location_count > 0) {
      addWarning(`${geojson.missing_location_count} روضة لا تمتلك إحداثيات جغرافية ولم تُعرض على الخريطة.`);
      renderWarnings();
    }

    addKgPins(kgs);
    CsApp.kgLoaded = true;
  } catch {
    addWarning('تعذر تحميل مواقع الروضات.');
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
      point: {
        pixelSize:                pinSize,
        color:                    pinColor,
        outlineColor:             Cesium.Color.WHITE.withAlpha(isCrit ? 1.0 : 0.75),
        outlineWidth:             isCrit ? 2 : 1.5,
        heightReference:          Cesium.HeightReference.CLAMP_TO_GROUND,
        disableDepthTestDistance: Number.POSITIVE_INFINITY,
        scaleByDistance:          new Cesium.NearFarScalar(5e3, 1.8, 5e5, 0.5),
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
        <div class="tt-name">${g.name_ar || g.name_en}</div>
        <div class="tt-badge"><span class="rank-badge risk-${riskClass(score)}">${riskAr(score)}</span></div>
        <div class="tt-divider"></div>
        <div class="tt-row"><span>درجة الخطر</span><b style="color:${riskHex(score)}">${score.toFixed(1)}</b></div>
        ${indRow}
        <div class="tt-row"><span>الروضات</span><b>${g.kg_count ?? '--'}</b></div>
        <div class="tt-row"><span>الطلاب</span><b>${g.student_count ?? '--'}</b></div>
        <div class="tt-hint">انقر للتفاصيل</div>`;

    } else if (ent._kgData && !ent._isPulseRing) {
      const k      = ent._kgData;
      const score  = parseFloat(k.kpi_score) || 0;
      const riskSc = 100 - score;
      const govAr  = govNameAr(k.governorate) || k.governorate_name_en || '';
      const cityTxt = k.city ? `<div class="tt-row"><span>المدينة</span><b>${k.city}</b></div>` : '';
      html = `
        <div class="tt-name">${k.name_ar || k.name_en || 'روضة'}</div>
        <div class="tt-badge"><span class="rank-badge risk-${riskClass(riskSc)}">${riskAr(riskSc)}</span></div>
        <div class="tt-divider"></div>
        <div class="tt-row"><span>المحافظة</span><b>${govAr}</b></div>
        ${cityTxt}
        <div class="tt-row"><span>درجة الأداء</span><b style="color:${riskHex(riskSc)}">${score.toFixed(1)}</b></div>
        <div class="tt-hint">انقر للتفاصيل</div>`;
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
  panel.innerHTML = `
    <div class="intel-loading">
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
      <div class="intel-error">
        <i class="bi bi-exclamation-octagon" aria-hidden="true"></i>
        <p>تعذر تحميل بيانات المحافظة</p>
        <button class="cc-btn" onclick="loadGovDetail('${slug}')">
          <i class="bi bi-arrow-clockwise"></i> إعادة المحاولة
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

  const ABBREV = ['روضات', 'أطفال', 'موظفون', 'سلامة', 'تقارير', 'حوكمة'];
  const lbls = IND_ORDER.map((_, i) => {
    const p = pt(MAX_R + 17, i);
    return `<text x="${p.x}" y="${p.y}" text-anchor="middle" dominant-baseline="middle" font-size="8" fill="#94a3b8" font-family="system-ui,sans-serif">${ABBREV[i]}</text>`;
  }).join('');

  return `
    <div style="display:flex;flex-direction:column;align-items:center;padding:.5rem 0 .25rem">
      <div style="font-size:.7rem;color:#64748b;margin-bottom:.25rem;letter-spacing:.03em">مخطط الأداء الشعاعي</div>
      <svg width="${SZ}" height="${SZ}" viewBox="0 0 ${SZ} ${SZ}" style="overflow:visible">
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
  const panel = document.getElementById('intelPanel');
  const score = d.risk_score ?? 0;
  const cls   = riskClass(score);

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
          <span>${a.message || ''}</span>
        </div>`).join('')
    : '<div class="intel-no-alerts">لا توجد تنبيهات نشطة</div>';

  const action     = d.recommended_action;
  const actionHtml = action?.ar || action?.en
    ? `<div class="intel-action-box">
         <i class="bi bi-lightbulb-fill" aria-hidden="true"></i>
         ${action.ar || action.en}
       </div>` : '';

  const sub          = d.sub_indicators || {};
  const kgCount      = sub.active_nurseries    ?? d.kg_count      ?? '--';
  const studentCount = sub.registered_children ?? d.student_count ?? '--';
  const govScore     = sub.governance_score     != null ? sub.governance_score.toFixed(1) : '--';

  panel.innerHTML = `
    <div class="intel-gov-header">
      <div class="intel-gov-namerow">
        <h3 class="intel-gov-name">${d.name_ar || d.name_en || ''}</h3>
        <span class="intel-gov-code">${(d.code || d.slug || '').toUpperCase()}</span>
      </div>
      <div class="intel-gov-name-sub">${d.name_en || ''}</div>
      <div class="intel-risk-row">
        <div class="intel-risk-score" style="color:${riskHex(score)}">${score.toFixed(1)}</div>
        <span class="intel-risk-badge risk-${cls}">${riskAr(score)}</span>
      </div>
      ${actionHtml}
    </div>

    <div class="intel-section">
      <div class="intel-section-title">
        المؤشرات الرئيسية <span class="intel-count">(6)</span>
      </div>
      ${indHtml}
    </div>

    <div class="intel-section">
      ${renderRadarChart(d.main_indicators)}
    </div>

    <div class="intel-section">
      <div class="intel-section-title">
        التنبيهات <span class="intel-count">${alerts.length}</span>
      </div>
      ${alertHtml}
    </div>

    <div class="intel-section" id="cityDataSection">
      <div class="intel-section-title">
        المؤشرات حسب المدينة <span class="intel-count" id="citySectionCount"></span>
      </div>
      <div id="cityTableBody">
        <div class="intel-loading-inline">
          <span class="intel-loading-spinner" style="width:14px;height:14px;border-width:1.5px"></span>
          جاري التحميل…
        </div>
      </div>
    </div>

    <div class="intel-footer">
      <div>الروضات النشطة: <strong>${kgCount}</strong></div>
      <div>الطلاب المسجلون: <strong>${studentCount}</strong></div>
      <div>نقاط الحوكمة: <strong>${govScore}</strong></div>
      <div style="margin-top:.5rem;font-size:.7rem;color:#475569">
        آخر تحديث: ${d.last_update ? new Date(d.last_update).toLocaleString('ar-JO') : '--'}
      </div>
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
    body.innerHTML = `<div class="intel-no-alerts">${errorMsg}</div>`;
    return;
  }

  const cities   = cityData?.cities || [];
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
    const riskSc   = c.risk_score ?? 0;
    const cls      = riskClass(riskSc);
    const kgLabel  = c.kindergarten_count + ' روضة';
    const stLabel  = c.children_count ? `· ${c.children_count} طالب` : '';
    const critLabel = c.critical_kindergartens
      ? `<span style="color:#ef4444;font-size:.7rem"> — ${c.critical_kindergartens} حرجة</span>` : '';
    const safeCity = c.city.replace(/'/g, "\\'");
    return `
      <div class="city-row" data-city="${c.city}"
           role="button" tabindex="0"
           onclick="selectCity('${safeCity}')"
           onkeydown="if(event.key==='Enter')selectCity('${safeCity}')">
        <div class="city-row-name">
          <span>${c.city}</span>${critLabel}
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

  // Fly camera to the centroid of this city's KG pins
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
  const name    = kg.name_ar || kg.name_en || 'روضة';
  const govAr   = govNameAr(kg.governorate) || kg.governorate_name_en || '';
  const cityTxt = kg.city ? ` • ${kg.city}` : '';
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
        <span class="intel-risk-badge risk-${riskClass(riskSc)}">${riskAr(riskSc)}</span>
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
      <div>الطلاب النشطون: <strong>${sc.active_enrollments ?? '--'}</strong></div>
      <div>الفصول الدراسية: <strong>${sc.classes ?? '--'}</strong></div>
      <div>المشرفون: <strong>${sc.supervisors ?? '--'}</strong></div>
      <div>الحوادث (90 يوم): <strong>${sc.recent_incidents ?? '--'}</strong></div>
      <div>نقاط الحوكمة: <strong>${sc.governance_score != null ? sc.governance_score.toFixed(1) : '--'}</strong></div>
      ${kg.id ? `<div style="margin-top:.75rem">
        <a href="/admin/kindergartens/${kg.id}" class="cc-btn" style="display:inline-flex">
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
    const govJson = JSON.stringify(g).replace(/"/g, '&quot;');
    const kgLabel = g.kg_count != null
      ? `<span style="font-size:.7rem;color:#64748b">${g.kg_count} روضة</span>` : '';
    return `
      <div class="cs-gov-item" data-slug="${g.slug}" data-risk-class="${cls}"
           tabindex="0" role="button"
           aria-label="${g.name_ar || g.name_en}"
           onclick="selectGovernorate(${govJson})"
           onkeydown="if(event.key==='Enter')selectGovernorate(${govJson})">
        <div>
          <div class="cs-gov-name">${g.name_ar || g.name_en}</div>
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

// ── KPI Strip ─────────────────────────────────────────────────────────────────
function updateKpiStrip(data) {
  const govs     = data.governorates || [];
  const sum      = data.summary || {};
  const avgRisk  = sum.average_risk   != null ? sum.average_risk
    : govs.length ? govs.reduce((s, g) => s + (g.risk_score || 0), 0) / govs.length : 0;
  const critical = sum.critical_count != null ? sum.critical_count
    : govs.filter(g => (g.risk_score || 0) >= 75).length;
  const totalKg  = govs.reduce((s, g) => s + (g.kg_count    || 0), 0);
  const totalSt  = govs.reduce((s, g) => s + (g.student_count || 0), 0);
  const alertCnt = sum.high_risk_count ?? govs.filter(g => (g.risk_score || 0) >= 50).length;

  _setEl('kpiAvgRisk',      avgRisk.toFixed(1));
  _setEl('kpiCritical',     critical);
  _setEl('kpiInstitutions', totalKg || '--');
  _setEl('kpiStudents',     totalSt || '--');
  _setEl('alertCountStatus',
    `<i class="bi bi-shield-exclamation" aria-hidden="true"></i> ${alertCnt} محافظة عالية الخطر`);
}

function updateGovSelect(govs) {
  const sel = document.getElementById('govSelect');
  if (!sel || sel.options.length > 1) return;
  govs.forEach(g => {
    const opt = new Option(g.name_ar || g.name_en, g.slug);
    sel.add(opt);
  });
}

// ── Rankings Table ────────────────────────────────────────────────────────────
function populateRankings(govs) {
  const tbody = document.querySelector('#rankingsTable tbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  const sorted = [...govs].sort((a, b) => (b.risk_score || 0) - (a.risk_score || 0));
  sorted.forEach((g, i) => {
    const score   = g.risk_score || 0;
    const cls     = riskClass(score);
    const rank    = i + 1;
    const numCls  = rank <= 3 ? `top-${rank}` : '';
    const govJson = JSON.stringify(g).replace(/"/g, '&quot;');
    const tr      = document.createElement('tr');
    tr.onclick    = () => selectGovernorate(g);

    const indVal  = CsApp.currentInd && CsApp.currentInd !== 'overall_risk'
      ? (g.main_indicators?.[CsApp.currentInd] ?? null) : null;
    const indCell = indVal != null
      ? `<small style="color:#64748b">${IND_LABELS[CsApp.currentInd]?.ar || CsApp.currentInd}: ${indVal.toFixed(0)}</small>`
      : '';

    tr.innerHTML = `
      <td><span class="rank-num ${numCls}">${rank}</span></td>
      <td>
        <div class="rank-name">${g.name_ar || g.name_en}</div>
        <div class="rank-code">${g.name_en || ''} ${indCell}</div>
      </td>
      <td>
        <div style="display:flex;align-items:center;gap:6px">
          <div class="mini-bar-track" style="flex:1">
            <div class="mini-bar-fill" style="width:${score}%;background:${riskHex(score)}"></div>
          </div>
          <span style="color:${riskHex(score)};font-weight:600;font-size:.85rem">${score.toFixed(1)}</span>
        </div>
      </td>
      <td><span class="rank-badge risk-${cls}">${riskAr(score)}</span></td>
      <td>
        <button class="rank-drill" onclick="event.stopPropagation();selectGovernorate(${govJson})"
                aria-label="عرض تفاصيل ${g.name_ar || ''}">
          <i class="bi bi-chevron-left" aria-hidden="true"></i>
        </button>
      </td>`;
    tbody.appendChild(tr);
  });
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
    const sel        = document.getElementById('indicatorViewSelect');
    CsApp.currentInd = sel?.value || 'overall_risk';
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

  // Governorate list search
  _on('govSearch', 'input', applyGovListFilter);

  // Risk level filter pills
  document.querySelectorAll('.risk-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      CsApp.riskFilter = btn.dataset.risk || 'all';
      document.querySelectorAll('.risk-filter-btn').forEach(b =>
        b.classList.toggle('active', b === btn)
      );
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
      <div class="page-error-state" style="min-height:400px">
        <i class="bi bi-exclamation-octagon" style="font-size:3rem;color:#ef4444" aria-hidden="true"></i>
        <h2>تعذر تحميل خريطة Cesium 3D</h2>
        <p style="max-width:380px">${msg || 'يرجى التحقق من الاتصال بالإنترنت وإعادة المحاولة.'}</p>
        <button class="cc-btn" onclick="location.reload()">
          <i class="bi bi-arrow-clockwise" aria-hidden="true"></i> إعادة المحاولة
        </button>
      </div>`;
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
window.selectGovernorate = selectGovernorate;
window.selectCity        = selectCity;
window.resetCityFilter   = resetCityFilter;
window.loadGovDetail     = loadGovDetail;
window.populateRankings  = populateRankings;
window.fetchMapData      = fetchMapData;
window.CsApp             = CsApp;
