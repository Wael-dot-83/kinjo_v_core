/**
 * Jordan Heat Map v3 — Satellite Leaflet implementation
 *
 * - ESRI World Imagery satellite tiles + CartoDB label overlay
 * - Tile-style toggle: Satellite ↔ Street
 * - Custom pin DivIcons for kindergartens (jittered within governorate)
 * - Governorate centroid badge markers (name + risk score)
 * - GeoJSON choropleth with risk-based fill opacity
 */
(function () {
  'use strict';

  const API_BASE = '/api/admin/heat-map';
  const MAP_CENTER = [31.0, 36.2];
  const MAP_ZOOM   = 7;
  const MIN_ZOOM   = 6;
  const MAX_ZOOM   = 17;

  const RC = { low:'#22c55e', medium:'#f59e0b', high:'#f97316', critical:'#ef4444', nodata:'#1e293b' };

  // Governorate centroid coordinates for badge placement [lat, lng]
  const CODE_CENTER = {
    'JO-AM':[31.95,35.95], 'JO-IR':[32.55,35.85], 'JO-ZA':[32.07,36.10],
    'JO-MA':[32.34,36.20], 'JO-JA':[32.28,35.90], 'JO-AJ':[32.33,35.75],
    'JO-BA':[32.04,35.78], 'JO-MD':[31.72,35.79], 'JO-KA':[31.18,35.70],
    'JO-TA':[30.83,35.60], 'JO-MN':[30.20,35.73], 'JO-AQ':[29.53,35.00],
  };

  let state = {
    map: null, baseTile: null, labelTile: null,
    geojsonLayer: null, kgLayer: null, govLayer: null,
    kgData: [], governorates: [], geojson: null,
    selectedSlug: null, indicator: '',
    onGovSelect: null, tileStyle: 'satellite', showKG: true,
  };

  // ── HELPERS ──────────────────────────────────────────────────────
  function lang() {
    const el = document.querySelector('.geo-cc');
    return el ? (el.getAttribute('lang') || 'ar') : 'ar';
  }
  function t(ar, en) { return lang() === 'ar' ? ar : en; }
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  async function api(path) {
    const r = await fetch(API_BASE + path, { credentials: 'same-origin' });
    if (!r.ok) throw new Error('API ' + r.status);
    return r.json();
  }

  function riskColor(v) {
    const s = +v || 0;
    return s < 25 ? RC.low : s < 50 ? RC.medium : s < 75 ? RC.high : RC.critical;
  }
  function riskLabel(v) {
    const s = +v || 0;
    const K = { low:'low', medium:'medium', high:'high', critical:'critical' };
    const k = s<25?'low':s<50?'medium':s<75?'high':'critical';
    const AR = {low:'منخفض',medium:'متوسط',high:'مرتفع',critical:'حرج'};
    const EN = {low:'Low',medium:'Medium',high:'High',critical:'Critical'};
    return { key: k, color: RC[k], label: t(AR[k], EN[k]) };
  }
  function kpiColor(status) {
    return ({normal:'#22c55e',warning:'#f59e0b',risk:'#f97316',critical:'#ef4444'})[status] || '#94a3b8';
  }

  // Seeded PRNG for deterministic per-KG jitter
  function prng(seed) {
    let s = (seed ^ 0xdeadbeef) >>> 0;
    s = (Math.imul(s ^ (s >>> 16), 0x45d9f3b)) >>> 0;
    s = (Math.imul(s ^ (s >>> 16), 0x45d9f3b)) >>> 0;
    return ((s ^ (s >>> 16)) >>> 0) / 4294967296;
  }

  // ── TILE LAYERS ──────────────────────────────────────────────────
  function setTiles(style) {
    state.tileStyle = style;
    if (!state.map) return;
    if (state.baseTile)  { state.map.removeLayer(state.baseTile);  state.baseTile  = null; }
    if (state.labelTile) { state.map.removeLayer(state.labelTile); state.labelTile = null; }

    if (style === 'satellite') {
      state.baseTile = L.tileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        { maxZoom: 19, attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP' }
      ).addTo(state.map);
      state.labelTile = L.tileLayer(
        'https://{s}.basemaps.cartocdn.com/rastertiles/voyager_only_labels/{z}/{x}/{y}{r}.png',
        { maxZoom: 19, attribution: '&copy; CartoDB', opacity: 0.9, zIndex: 10 }
      ).addTo(state.map);
    } else {
      state.baseTile = L.tileLayer(
        'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
        { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; CartoDB' }
      ).addTo(state.map);
    }

    const btn = document.getElementById('tileToggleBtn');
    if (btn) {
      btn.innerHTML = style === 'satellite'
        ? '<i class="bi bi-map" aria-hidden="true"></i> ' + t('خريطة الطرق', 'Street Map')
        : '<i class="bi bi-globe2" aria-hidden="true"></i> ' + t('صورة القمر الاصطناعي', 'Satellite');
    }
  }

  // ── CUSTOM ICONS ─────────────────────────────────────────────────
  function kgIcon(color) {
    return L.divIcon({
      className: 'kj-pin-icon',
      html:
        '<div class="kj-pin-body" style="background:' + color + ';box-shadow:0 2px 8px ' + color + '88">' +
          '<i class="bi bi-building" aria-hidden="true"></i>' +
        '</div>' +
        '<div class="kj-pin-tip" style="border-top-color:' + color + '"></div>',
      iconSize:    [28, 38],
      iconAnchor:  [14, 38],
      popupAnchor: [0, -40],
    });
  }

  function govBadgeIcon(nameAr, nameEn, score, color) {
    const nm = lang() === 'ar' ? (nameAr || nameEn) : (nameEn || nameAr);
    return L.divIcon({
      className: 'kj-gov-icon',
      html:
        '<div class="kj-gov-wrap">' +
          '<div class="kj-gov-name">' + esc(nm || '') + '</div>' +
          '<div class="kj-gov-score" style="background:' + color + '">' + Math.round(+score || 0) + '</div>' +
        '</div>',
      iconSize:   [0, 0],
      iconAnchor: [0, 0],
    });
  }

  // ── TOOLTIP ──────────────────────────────────────────────────────
  let ttEl = null;
  function showTT(e, gov, name) {
    if (!ttEl) ttEl = document.getElementById('geoTooltip');
    if (!ttEl) return;
    const rl = gov ? riskLabel(gov.risk_score) : null;
    ttEl.innerHTML =
      '<div class="tt-name">' + esc(name) + '</div>' +
      (rl ? '<div class="tt-badge" style="color:' + rl.color + '">' + esc(rl.label) + '</div>' : '') +
      '<div class="tt-divider"></div>' +
      '<div class="tt-row"><span>' + t('مؤشر الخطر', 'Risk Score') + '</span>' +
        '<strong>' + (gov ? (+gov.risk_score || 0).toFixed(0) : '--') + '/100</strong></div>' +
      '<div class="tt-hint">' + t('انقر للتفاصيل', 'Click for details') + '</div>';
    ttEl.style.display = 'block';
    moveTT(e);
  }
  function hideTT() { if (ttEl) ttEl.style.display = 'none'; }
  function moveTT(e) {
    if (!ttEl) return;
    const pad = 16;
    let x = e.clientX + pad, y = e.clientY + pad;
    ttEl.style.display = 'block';
    const r = ttEl.getBoundingClientRect();
    if (x + r.width  > window.innerWidth  - 8) x = e.clientX - r.width  - pad;
    if (y + r.height > window.innerHeight - 8) y = e.clientY - r.height - pad;
    ttEl.style.left = x + 'px';
    ttEl.style.top  = y + 'px';
  }

  // ── INIT MAP ─────────────────────────────────────────────────────
  function initMap() {
    if (state.map) return;
    state.map = L.map('leafletMap', {
      center: MAP_CENTER, zoom: MAP_ZOOM,
      minZoom: MIN_ZOOM, maxZoom: MAX_ZOOM,
      zoomControl: false,
      attributionControl: true,
    });
    L.control.zoom({ position: 'bottomright' }).addTo(state.map);
    setTiles('satellite');
  }

  // ── GEOJSON CHOROPLETH ───────────────────────────────────────────
  function loadGeoJSON() {
    if (!state.geojson || !state.geojson.features) { showError(); return; }
    if (state.geojsonLayer) state.map.removeLayer(state.geojsonLayer);

    const feats = state.geojson.features.filter(f => {
      const lv = f.properties && f.properties.level;
      return !lv || lv === 'governorate';
    });

    state.geojsonLayer = L.geoJSON(feats, {
      style: function (feature) {
        const code = (feature.properties || {}).admin_code || (feature.properties || {}).id || '';
        const gov  = state.governorates.find(g => g.code === code);
        let fill   = RC.nodata;
        if (gov) {
          if (state.indicator) {
            const v = gov.main_indicators && gov.main_indicators[state.indicator];
            fill = v != null ? riskColor(v) : RC.nodata;
          } else {
            fill = riskColor(gov.risk_score);
          }
        }
        return { fillColor: fill, fillOpacity: 0.38, color: 'rgba(255,255,255,0.6)', weight: 1.8 };
      },
      onEachFeature: function (feature, layer) {
        const props = feature.properties || {};
        const code  = props.admin_code || props.id || '';
        const gov   = state.governorates.find(g => g.code === code);
        const name  = lang() === 'ar'
          ? (props.name_ar || props.name || code)
          : (props.name    || props.name_ar || code);
        layer.on({
          mouseover: function (e) {
            e.target.setStyle({ fillOpacity: 0.62, weight: 2.8, color: '#ffffff' });
            e.target.bringToFront();
            showTT(e, gov, name);
          },
          mouseout: function (e) {
            if (state.geojsonLayer) state.geojsonLayer.resetStyle(e.target);
            hideTT();
          },
          mousemove: moveTT,
          click: function () {
            const g = state.governorates.find(gv => gv.code === code);
            if (g && state.onGovSelect) state.onGovSelect(g.slug);
          },
        });
      },
    }).addTo(state.map);

    state.map.fitBounds(state.geojsonLayer.getBounds().pad(0.04));
    buildGovBadges();
  }

  // ── GOVERNORATE CENTROID BADGES ──────────────────────────────────
  function buildGovBadges() {
    if (state.govLayer) { state.map.removeLayer(state.govLayer); state.govLayer = null; }
    const fg = L.featureGroup();

    for (const gov of state.governorates) {
      const center = CODE_CENTER[gov.code];
      if (!center) continue;
      const score = +(gov.risk_score || 0);
      const color = riskColor(score);
      const icon  = govBadgeIcon(gov.name_ar || '', gov.name_en || '', score, color);
      const m     = L.marker(center, { icon, interactive: true, keyboard: false, zIndexOffset: 900 });
      m.on('click', function () {
        if (state.onGovSelect) state.onGovSelect(gov.slug);
      });
      m.bindTooltip(
        '<strong>' + esc(lang() === 'ar' ? (gov.name_ar || gov.name_en) : (gov.name_en || gov.name_ar)) + '</strong>' +
        ' &mdash; ' + t('مؤشر الخطر', 'Risk') + ': ' + score.toFixed(0),
        { className: 'kj-gov-tt', sticky: true }
      );
      fg.addLayer(m);
    }

    state.govLayer = fg;
    state.map.addLayer(fg);
  }

  // ── KINDERGARTEN PIN MARKERS ─────────────────────────────────────
  async function loadKGMarkers() {
    try {
      const data   = await api('/kindergartens/map-data');
      state.kgData = data.features || [];
    } catch (_) {
      state.kgData = [];
    }
    rebuildKG();
  }

  function rebuildKG() {
    if (state.kgLayer) { state.map.removeLayer(state.kgLayer); state.kgLayer = null; }
    const fg = L.featureGroup();

    for (const feat of state.kgData) {
      const coords = feat.geometry && feat.geometry.coordinates;
      if (!coords || coords[0] == null || coords[1] == null) continue;
      const props  = feat.properties || {};
      const id     = feat.id || (props.id || 0);

      // Deterministic jitter within ~10 km of governorate center
      const dlat = (prng(id * 7 + 1) - 0.5) * 0.20;
      const dlng = (prng(id * 13 + 2) - 0.5) * 0.20;
      const lat  = coords[1] + dlat;
      const lng  = coords[0] + dlng;

      const color = kpiColor(props.kpi_status);
      const icon  = kgIcon(color);
      const m     = L.marker([lat, lng], { icon });

      const name  = lang() === 'ar'
        ? (props.name_ar  || props.name_en || '')
        : (props.name_en  || props.name_ar || '');
      const gov   = props.governorate || '';
      const score = props.kpi_score != null ? (+props.kpi_score).toFixed(1) : '--';
      const st    = props.kpi_status || '--';

      m.bindPopup(
        '<div class="kj-popup">' +
          '<div class="kj-popup-title"><i class="bi bi-buildings" aria-hidden="true"></i> ' + esc(name) + '</div>' +
          '<div class="kj-popup-gov"><i class="bi bi-geo-alt-fill" style="color:#f59e0b" aria-hidden="true"></i> ' + esc(gov) + '</div>' +
          '<div class="kj-popup-row">' +
            '<span>' + t('الحالة','Status') + ': <b style="color:' + color + '">' + esc(st) + '</b></span>' +
            '<span>' + t('الدرجة','Score') + ': <b>' + score + '</b></span>' +
          '</div>' +
        '</div>',
        { className: 'kg-popup-dark', maxWidth: 230 }
      );

      fg.addLayer(m);
    }

    state.kgLayer = fg;
    if (state.showKG) state.map.addLayer(state.kgLayer);

    const badge = document.getElementById('kgCountBadge');
    if (badge) badge.textContent = state.kgData.length;
  }

  // ── HIGHLIGHT GOVERNORATE ────────────────────────────────────────
  function highlightGov(slug) {
    state.selectedSlug = slug;
    if (!state.geojsonLayer) return;
    state.geojsonLayer.resetStyle();
    state.geojsonLayer.eachLayer(function (l) {
      const code = ((l.feature && l.feature.properties) || {}).admin_code || '';
      const g    = state.governorates.find(g => g.code === code);
      if (g && g.slug === slug) {
        l.setStyle({ fillOpacity: 0.72, weight: 3.5, color: '#fff' });
        l.bringToFront();
      }
    });
  }

  // ── ERROR STATE ──────────────────────────────────────────────────
  function showError() {
    const wrapEl = document.getElementById('singleMapWrap');
    const errEl  = document.getElementById('singleMapError');
    if (wrapEl) wrapEl.style.display = 'none';
    if (errEl)  errEl.style.display  = 'flex';
  }

  // ── PUBLIC API ───────────────────────────────────────────────────
  function showSingleMap(indKey, governorates, geojson, onGovSelectCb) {
    state.governorates = governorates || state.governorates;
    state.geojson      = geojson      || state.geojson;
    state.indicator    = (indKey === 'overall_risk') ? '' : (indKey || '');
    state.onGovSelect  = onGovSelectCb;

    initMap();

    const wrapEl = document.getElementById('singleMapWrap');
    const loadEl = document.getElementById('singleMapLoading');
    const errEl  = document.getElementById('singleMapError');
    if (wrapEl) wrapEl.style.display = 'block';
    if (loadEl) loadEl.style.display = 'none';
    if (errEl)  errEl.style.display  = 'none';

    if (state.map) setTimeout(function () { state.map.invalidateSize(); }, 80);
    loadGeoJSON();
  }

  // ── CONTROLS ─────────────────────────────────────────────────────
  function bindControls() {
    const tileBtn = document.getElementById('tileToggleBtn');
    if (tileBtn) {
      tileBtn.addEventListener('click', function () {
        setTiles(state.tileStyle === 'satellite' ? 'street' : 'satellite');
        // Refresh choropleth opacity for current tile style
        if (state.geojsonLayer) {
          state.geojsonLayer.eachLayer(function (l) {
            if (l.feature) state.geojsonLayer.resetStyle(l);
          });
        }
      });
    }

    const kgToggle = document.getElementById('kgToggle');
    if (kgToggle) {
      kgToggle.addEventListener('change', function (e) {
        state.showKG = e.target.checked;
        if (!state.kgLayer) return;
        if (state.showKG) state.map.addLayer(state.kgLayer);
        else state.map.removeLayer(state.kgLayer);
      });
    }

    const govToggle = document.getElementById('govBadgeToggle');
    if (govToggle) {
      govToggle.addEventListener('change', function (e) {
        if (!state.govLayer) return;
        if (e.target.checked) state.map.addLayer(state.govLayer);
        else state.map.removeLayer(state.govLayer);
      });
    }

    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', function () {
        state.kgData = [];
        if (state.kgLayer) { state.map.removeLayer(state.kgLayer); state.kgLayer = null; }
        loadKGMarkers();
      });
    }

    const retrySingle = document.getElementById('retrySingleBtn');
    if (retrySingle) {
      retrySingle.addEventListener('click', function () {
        showSingleMap(state.indicator || 'overall_risk', state.governorates, state.geojson, state.onGovSelect);
      });
    }
  }

  // ── INIT ─────────────────────────────────────────────────────────
  async function init() {
    if (!document.getElementById('leafletMap')) return;
    try {
      const [, mapRes, gjRes] = await Promise.all([
        api('/indicators').catch(function () { return { indicators: [] }; }),
        api('/data'),
        api('/geojson'),
      ]);
      state.governorates = (mapRes && mapRes.governorates) || [];
      state.geojson      = gjRes;
      initMap();
      loadKGMarkers();
      bindControls();
    } catch (e) {
      console.error('[Heatmap] init error:', e);
    }
  }

  window.JordanHeatmap = { init: init, showSingleMap: showSingleMap, highlightGov: highlightGov };
  document.addEventListener('DOMContentLoaded', init);
})();
