/**
 * Jordan Heat Map v2 — Leaflet-based implementation
 *
 * Replaces the pure-SVG version with a professional Leaflet map
 * including:
 * - Dark-themed tile layer (CartoDB Dark Matter)
 * - GeoJSON choropleth overlay with risk-based coloring
 * - Kindergarten point markers with custom clustering
 * - Governorate click → intelligence panel
 * - KPI status-colored circle markers
 */
(function () {
  'use strict';

  const API_BASE = '/api/admin/heat-map';

  const MAP_CENTER = [31.5, 36.5];
  const MAP_ZOOM = 8;
  const MIN_ZOOM = 7;
  const MAX_ZOOM = 11;

  const RISK_COLORS = {
    low:      '#22c55e',
    medium:   '#f59e0b',
    high:     '#f97316',
    critical: '#ef4444',
    nodata:   '#374151',
  };

  const KPI_COLORS = {
    normal:   '#22c55e',
    warning:  '#f59e0b',
    risk:     '#f97316',
    critical: '#ef4444',
    unknown:  '#94a3b8',
  };

  let state = {
    map: null,
    geojsonLayer: null,
    kgMarkers: null,
    kgData: [],
    selectedSlug: null,
    indicator: '',
    indicators: [],
    governorates: [],
    geojson: null,
    onGovSelect: null,
  };

  function currentLang() {
    const el = document.querySelector('.geo-cc');
    if (el) return el.getAttribute('lang') || 'ar';
    const stored = localStorage.getItem('kinjo_lang') || localStorage.getItem('admin_language');
    if (stored && String(stored).toLowerCase().startsWith('en')) return 'en';
    return document.documentElement.lang && String(document.documentElement.lang).toLowerCase().startsWith('en') ? 'en' : 'ar';
  }
  function t(ar, en) { return currentLang() === 'ar' ? ar : en; }

  async function apiGet(path) {
    const res = await fetch(API_BASE + path, { credentials: 'same-origin' });
    if (!res.ok) throw new Error('API ' + res.status);
    return res.json();
  }

  function riskLevel(v) {
    const s = +v || 0;
    if (s < 25) return { key: 'low',      label: t('منخفض', 'Low'),      color: RISK_COLORS.low };
    if (s < 50) return { key: 'medium',   label: t('متوسط', 'Medium'),   color: RISK_COLORS.medium };
    if (s < 75) return { key: 'high',     label: t('مرتفع', 'High'),     color: RISK_COLORS.high };
    return          { key: 'critical', label: t('حرج', 'Critical'), color: RISK_COLORS.critical };
  }

  function riskColorScore(v) {
    const s = Math.max(0, Math.min(100, +v || 0));
    if (s < 25) return RISK_COLORS.low;
    if (s < 50) return RISK_COLORS.medium;
    if (s < 75) return RISK_COLORS.high;
    return RISK_COLORS.critical;
  }

  function interpolateColor(value) {
    const s = Math.max(0, Math.min(100, +value || 0));
    if (s < 25) return '#22c55e';
    if (s < 50) return '#f59e0b';
    if (s < 75) return '#f97316';
    return '#ef4444';
  }

  function kgColor(status) {
    return KPI_COLORS[status] || KPI_COLORS.unknown;
  }

  function kgRadius(props) {
    const score = +(props.kpi_score || 50);
    return Math.max(5, Math.min(14, score / 10));
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

// ── TOOLTIP FUNCTIONS ─────────────────────────────────────────
  let ttEl = null;

  function showTooltipGov(e, gov, name) {
    if (!ttEl) ttEl = document.getElementById('geoTooltip');
    if (!ttEl) return;
    var risk = gov ? riskLevel(gov.risk_score) : null;
    ttEl.innerHTML =
      '<div class="tt-name">' + esc(name) + '</div>' +
      (risk ? '<div class="tt-badge" style="color:' + risk.color + '">' + esc(risk.label) + '</div>' : '') +
      '<div class="tt-divider"></div>' +
      '<div class="tt-row"><span>' + t('مؤشر الخطر', 'Risk Score') + '</span><strong>' + (gov ? gov.risk_score.toFixed(0) : '--') + '/100</strong></div>' +
      '<div class="tt-hint">' + t('انقر للتفاصيل', 'Click for details') + '</div>';
    ttEl.style.display = 'block';
    positionTooltip(e);
  }

  function hideTooltip() {
    if (ttEl) ttEl.style.display = 'none';
  }

  function positionTooltip(e) {
    if (!ttEl) return;
    var pad = 16, x = e.clientX + pad, y = e.clientY + pad;
    ttEl.style.display = 'block';
    var r = ttEl.getBoundingClientRect();
    if (x + r.width > window.innerWidth - 8) x = e.clientX - r.width - pad;
    if (y + r.height > window.innerHeight - 8) y = e.clientY - r.height - pad;
    ttEl.style.left = x + 'px';
    ttEl.style.top = y + 'px';
  }

// ── CUSTOM CLUSTERING ──────────────────────────────────────────
  // Groups nearby circle markers within a radius. No external dependency.
  function clusterMarkers(markers, clusterRadius) {
    const clusters = [];
    const assigned = new Array(markers.length).fill(false);
    for (let i = 0; i < markers.length; i++) {
      if (assigned[i]) continue;
      const cluster = { markers: [markers[i]], latlng: markers[i].getLatLng() };
      assigned[i] = true;
      for (let j = i + 1; j < markers.length; j++) {
        if (assigned[j]) continue;
        const dist = cluster.latlng.distanceTo(markers[j].getLatLng());
        if (dist <= clusterRadius) {
          cluster.markers.push(markers[j]);
          assigned[j] = true;
        }
      }
      // Recompute cluster center as average
      let lat = 0, lng = 0;
      for (const m of cluster.markers) {
        const ll = m.getLatLng();
        lat += ll.lat;
        lng += ll.lng;
      }
      lat /= cluster.markers.length;
      lng /= cluster.markers.length;
      cluster.latlng = L.latLng(lat, lng);
      clusters.push(cluster);
    }
    return clusters;
  }

  function renderClusterMarkers(clusters, map) {
    const fg = L.featureGroup();
    for (const cluster of clusters) {
      if (cluster.markers.length === 1) {
        fg.addLayer(cluster.markers[0]);
      } else {
        const count = cluster.markers.length;
        const avgColor = '#2F7D62';
        const r = Math.min(18, 8 + count * 2);
        const clusterCircle = L.circleMarker(cluster.latlng, {
          radius: r,
          fillColor: avgColor,
          color: 'rgba(255,255,255,0.4)',
          weight: 1.5,
          fillOpacity: 0.8,
        });
        clusterCircle.bindPopup(
          '<div style="font-family:system-ui;text-align:center;min-width:120px;">' +
          '<div style="font-weight:700;font-size:1.1rem;color:' + avgColor + '">' + count + '</div>' +
          '<div style="font-size:0.85rem;color:#94a3b8;">' + t('روضة أطفال', 'Kindergartens') + '</div>' +
          '</div>',
          { className: 'kg-popup-dark' }
        );
        fg.addLayer(clusterCircle);
      }
    }
    return fg;
  }

  // ── INIT MAP ──────────────────────────────────────────────────
  function initMap() {
    if (state.map) return;

    state.map = L.map('leafletMap', {
      center: MAP_CENTER,
      zoom: MAP_ZOOM,
      minZoom: MIN_ZOOM,
      maxZoom: MAX_ZOOM,
      zoomControl: true,
      attributionControl: false,
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 19,
    }).addTo(state.map);
  }

  // ── LOAD GEOJSON CHOROPLETH ──────────────────────────────────
  function loadGeoJSON() {
    if (!state.geojson || !state.geojson.features) {
      showError();
      return;
    }
    if (state.geojsonLayer) state.map.removeLayer(state.geojsonLayer);

    const features = state.geojson.features.filter(
      f => (f.properties && (f.properties.level === 'governorate' || !f.properties.level))
    );

    state.geojsonLayer = L.geoJSON(features, {
      style: function (feature) {
        const props = feature.properties || {};
        const code = props.admin_code || props.id || '';
        const gov = state.governorates.find(g => g.code === code);
        let fillColor = RISK_COLORS.nodata;
        if (gov) {
          if (state.indicator) {
            const v = gov.main_indicators ? gov.main_indicators[state.indicator] : null;
            fillColor = v != null ? interpolateColor(v) : RISK_COLORS.nodata;
          } else {
            fillColor = riskColorScore(gov.risk_score);
          }
        }
        return {
          fillColor: fillColor,
          fillOpacity: 0.6,
          color: 'rgba(255,255,255,0.22)',
          weight: 1.0,
        };
      },
      onEachFeature: function (feature, layer) {
        const props = feature.properties || {};
        const code = props.admin_code || props.id || '';
        const slug = props.slug || (code ? String(code).toLowerCase().replace('jo-', '') : '');
        const gov = state.governorates.find(g => g.code === code);
        const name = currentLang() === 'ar' ? (props.name_ar || props.name || slug) : (props.name || props.name_ar || slug);

        layer.on({
          mouseover: function (e) {
            const target = e.target;
            target.setStyle({ fillOpacity: 0.85, weight: 2.0, color: 'rgba(255,255,255,0.6)' });
            target.bringToFront();
            showTooltipGov(e, gov, name);
          },
          mouseout: function (e) {
            if (state.geojsonLayer) state.geojsonLayer.resetStyle(e.target);
            hideTooltip();
          },
          click: function () {
            const g = state.governorates.find(gov => gov.code === code);
            if (g && state.onGovSelect) state.onGovSelect(g.slug);
          },
        });
      },
    }).addTo(state.map);

    state.map.fitBounds(state.geojsonLayer.getBounds().pad(0.05));
  }

  // ── LOAD KINDERGARTEN MARKERS ────────────────────────────────
  async function loadKindergartenMarkers() {
    try {
      const data = await apiGet('/kindergartens/map-data');
      state.kgData = data.features || [];
    } catch (e) {
      state.kgData = [];
    }

    rebuildKGMarkers();
  }

  function rebuildKGMarkers() {
    if (state.kgMarkers) {
      state.map.removeLayer(state.kgMarkers);
      state.kgMarkers = null;
    }

    const rawMarkers = [];
    for (const feat of state.kgData) {
      const coords = feat.geometry.coordinates;
      const props = feat.properties || {};
      const status = props.kpi_status || 'unknown';
      const radius = kgRadius(props);
      const color = kgColor(status);

      const marker = L.circleMarker([coords[1], coords[0]], {
        radius: radius,
        fillColor: color,
        color: '#fff',
        weight: 1.5,
        opacity: 0.8,
        fillOpacity: 0.7,
      });

      const name = currentLang() === 'ar' ? (props.name_ar || props.name_en || '') : (props.name_en || props.name_ar || '');
      const govName = props.governorate || '';
      const score = props.kpi_score != null ? props.kpi_score.toFixed(1) : '--';
      const statusLabel = t(props.kpi_status_ar || status, status);

      marker.bindPopup(
        '<div style="font-family:system-ui;min-width:180px;">' +
        '<div style="font-weight:700;font-size:1rem;margin-bottom:4px;">' + esc(name) + '</div>' +
        '<div style="font-size:0.85rem;color:#64748b;margin-bottom:6px;">' + esc(govName) + '</div>' +
        '<div style="display:flex;justify-content:space-between;gap:12px;font-size:0.85rem;">' +
        '<span>' + t('الحالة', 'Status') + ': <strong style="color:' + color + '">' + esc(statusLabel) + '</strong></span>' +
        '<span>' + t('الدرجة', 'Score') + ': <strong>' + score + '</strong></span>' +
        '</div></div>',
        { className: 'kg-popup-dark' }
      );

      rawMarkers.push(marker);
    }

    const clusters = clusterMarkers(rawMarkers, 2500);
    state.kgMarkers = renderClusterMarkers(clusters, state.map);

    if (document.getElementById('kgToggle') && document.getElementById('kgToggle').checked) {
      state.map.addLayer(state.kgMarkers);
    }

    const badge = document.getElementById('kgCountBadge');
    if (badge) badge.textContent = rawMarkers.length;
  }

  // ── GOVERNORATE SELECTION ────────────────────────────────────
  function selectGovernorate(slug) {
    state.selectedSlug = slug;
    if (state.geojsonLayer) {
      state.geojsonLayer.resetStyle();
      state.geojsonLayer.eachLayer(function (layer) {
        const props = layer.feature && layer.feature.properties;
        if (props) {
          const code = props.admin_code || props.id || '';
          const gov = state.governorates.find(g => g.code === code);
          if (gov && gov.slug === slug) {
            layer.setStyle({ fillOpacity: 0.9, weight: 2.5, color: '#fff' });
            layer.bringToFront();
          }
        }
      });
    }
  }

// ── PUBLIC API (called from geo_intelligence.js) ──────────────
  function highlightGov(slug) {
    selectGovernorate(slug);
  }

  function showSingleMap(indKey, governorates, geojson, onGovSelectCb) {
    state.governorates = governorates || state.governorates;
    state.geojson = geojson || state.geojson;
    state.indicator = (indKey === 'overall_risk') ? '' : indKey;
    state.onGovSelect = onGovSelectCb;

    initMap();

    const loadEl = document.getElementById('singleMapLoading');
    const errEl = document.getElementById('singleMapError');
    const wrapEl = document.getElementById('singleMapWrap');

    if (loadEl) loadEl.style.display = 'none';
    if (errEl) errEl.style.display = 'none';
    if (wrapEl) wrapEl.style.display = 'block';

    // Invalidate size (Leaflet needs this when container becomes visible)
    if (state.map) setTimeout(() => state.map.invalidateSize(), 50);

    loadGeoJSON();
  }

  function showError() {
    const loadEl = document.getElementById('singleMapLoading');
    const errEl = document.getElementById('singleMapError');
    const wrapEl = document.getElementById('singleMapWrap');
    if (loadEl) loadEl.style.display = 'none';
    if (errEl) errEl.style.display = 'flex';
    if (wrapEl) wrapEl.style.display = 'none';
  }

  // ── KEYBOARD SHORTCUT ────────────────────────────────────────
  function bindKeyboard() {
    document.addEventListener('keydown', function (e) {
      if (e.key === 'r' && !e.ctrlKey && !e.metaKey && !e.target.closest('input,textarea,select')) {
        e.preventDefault();
        const refreshBtn = document.getElementById('refreshBtn');
        if (refreshBtn) refreshBtn.click();
      }
    });
  }

  // ── BIND CONTROLS ────────────────────────────────────────────
  function bindControls() {
    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', function () {
        state.kgData = [];
        if (state.kgMarkers) { state.map.removeLayer(state.kgMarkers); state.kgMarkers = null; }
        loadKindergartenMarkers();
      });
    }

    const kgToggle = document.getElementById('kgToggle');
    if (kgToggle) {
      kgToggle.addEventListener('change', function (e) {
        if (!state.kgMarkers) return;
        if (e.target.checked) {
          state.map.addLayer(state.kgMarkers);
        } else {
          state.map.removeLayer(state.kgMarkers);
        }
      });
    }

    const retrySingle = document.getElementById('retrySingleBtn');
    if (retrySingle) {
      retrySingle.addEventListener('click', function () {
        showSingleMap(state.indicator || 'overall_risk', state.governorates, state.geojson, state.onGovSelect);
      });
    }

    bindKeyboard();
  }

  // ── INIT ─────────────────────────────────────────────────────
  async function init() {
    if (!document.getElementById('leafletMap')) return;

    try {
      const [indRes, mapRes, gjRes] = await Promise.all([
        apiGet('/indicators').catch(() => ({ indicators: [] })),
        apiGet('/data'),
        apiGet('/geojson'),
      ]);

      state.indicators = indRes.indicators || [];
      state.governorates = mapRes.governorates || [];
      state.geojson = gjRes;

      initMap();

      // Load KG markers in background
      loadKindergartenMarkers();

      bindControls();
    } catch (e) {
      console.error('[Heatmap] init error:', e);
    }
  }

  // ── EXPORT ───────────────────────────────────────────────────
  const JordanHeatmap = {
    init: init,
    showSingleMap: showSingleMap,
    highlightGov: highlightGov,
  };

  window.JordanHeatmap = JordanHeatmap;

  // Auto-init on DOMContentLoaded (for direct page load)
  document.addEventListener('DOMContentLoaded', init);
})();