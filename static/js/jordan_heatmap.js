/**
 * Jordan Heat Map — Admin client.
 *
 * Consumes the `/api/admin/heat-map/*` API surface and renders an interactive
 * SVG-based heat map of Jordan's 12 governorates. The feature is called
 * "Heat Map" throughout the UI; no internal term "GeoMap" is exposed.
 *
 * Data flow:
 *   1. GET /api/admin/heat-map/indicators            — main + sub indicators
 *   2. GET /api/admin/heat-map/data                  — full map payload
 *   3. GET /api/admin/heat-map/governorate/{slug}    — drill-down payload
 *   4. GET /api/admin/heat-map/correlations          — Pearson matrix
 *   5. GET /api/admin/heat-map/regression            — OLS weights
 *   6. GET /api/admin/heat-map/daily-update          — last update metadata
 */
(function () {
  'use strict';

  const API_BASE = '/api/admin/heat-map';
  const SVG_NS = 'http://www.w3.org/2000/svg';

  // Public Jordan bounding box used to map (lon, lat) to SVG (x, y).
  // The real boundary data covers roughly 34.9-39.4 lon / 29.0-33.4 lat.
  const BBOX = { minLon: 34.85, maxLon: 39.50, minLat: 28.95, maxLat: 33.45 };
  const SVG_W = 800;
  const SVG_H = 760;

  const ZOOM_MIN = 1.0;
  const ZOOM_MAX = 6.0;
  const ZOOM_STEP = 1.4;

  // UI state
  let state = {
    zoom: 1.0,
    pan: { x: 0, y: 0 },
    indicator: '',            // '' = composite risk
    selectedSlug: null,
    geojson: null,
    mapData: null,
    indicators: [],
    governorates: [],
    detail: null,
    detailLoading: false,
    initialized: false,
  };

  // -------------------------------------------------------------------------
  // Language helpers
  // -------------------------------------------------------------------------
  function currentLang() {
    const stored = localStorage.getItem('kinjo_lang') || localStorage.getItem('admin_language');
    if (stored && String(stored).toLowerCase().startsWith('en')) return 'en';
    const html = document.documentElement.lang;
    return String(html || '').toLowerCase().startsWith('en') ? 'en' : 'ar';
  }
  function t(en, ar) { return currentLang() === 'en' ? en : ar; }
  function dir() { return currentLang() === 'en' ? 'ltr' : 'rtl'; }

  // -------------------------------------------------------------------------
  // Fetch helpers
  // -------------------------------------------------------------------------
  async function apiGet(path) {
    const headers = { 'Accept': 'application/json' };
    const res = await fetch(`${API_BASE}${path}`, { headers, credentials: 'same-origin' });
    if (!res.ok) {
      let detail = '';
      try { detail = (await res.json()).detail || ''; } catch (_) { /* noop */ }
      throw new Error(`API ${res.status}: ${detail || res.statusText}`);
    }
    return res.json();
  }

  // -------------------------------------------------------------------------
  // Color helpers (D3-style linear interpolation + risk scale)
  // -------------------------------------------------------------------------
  function hexToRgb(hex) {
    var r = parseInt(hex.slice(1, 3), 16);
    var g = parseInt(hex.slice(3, 5), 16);
    var b = parseInt(hex.slice(5, 7), 16);
    return [r, g, b];
  }

  function rgbToHex(r, g, b) {
    return '#' + [r, g, b].map(function (v) {
      return Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0');
    }).join('');
  }

  function lerpColor(c1, c2, t) {
    var a = hexToRgb(c1);
    var b = hexToRgb(c2);
    return rgbToHex(
      a[0] + (b[0] - a[0]) * t,
      a[1] + (b[1] - a[1]) * t,
      a[2] + (b[2] - a[2]) * t
    );
  }

  var COLOR_STOPS = [
    { pct: 0, color: '#22C55E' },
    { pct: 25, color: '#F59E0B' },
    { pct: 50, color: '#FD7E14' },
    { pct: 75, color: '#EF4444' },
    { pct: 100, color: '#7F1D1D' }
  ];

  function interpolateColor(value) {
    if (value <= 0) return COLOR_STOPS[0].color;
    if (value >= 100) return COLOR_STOPS[COLOR_STOPS.length - 1].color;
    var i = 0;
    while (i < COLOR_STOPS.length - 1 && value > COLOR_STOPS[i + 1].pct) i++;
    var lower = COLOR_STOPS[i];
    var upper = COLOR_STOPS[i + 1];
    var t = (value - lower.pct) / (upper.pct - lower.pct);
    return lerpColor(lower.color, upper.color, t);
  }

  const RISK_COLORS = [
    { max: 25,  color: '#22C55E', name_en: 'Low',      name_ar: 'منخفض'  },
    { max: 50,  color: '#F59E0B', name_en: 'Medium',   name_ar: 'متوسط'  },
    { max: 75,  color: '#FD7E14', name_en: 'High',     name_ar: 'مرتفع'  },
    { max: 999, color: '#EF4444', name_en: 'Critical', name_ar: 'حرج'    },
  ];
  function riskColorForScore(score) {
    if (score === null || score === undefined) return '#9CA3AF';
    return interpolateColor(Math.max(0, Math.min(100, score)));
  }
  function riskLevelForScore(score) {
    const s = Number(score || 0);
    for (const r of RISK_COLORS) if (s <= r.max) return r;
    return RISK_COLORS[RISK_COLORS.length - 1];
  }
  function riskIconForLevel(key) {
    switch (key) {
      case 'low': return 'bi-check-circle';
      case 'medium': return 'bi-exclamation-triangle';
      case 'high': return 'bi-exclamation-diamond-fill';
      case 'critical': return 'bi-x-octagon-fill';
      default: return 'bi-question-circle';
    }
  }
  function colorForIndicator(value, min, max) {
    if (value === null || value === undefined) return '#9CA3AF';
    var pct = max > min ? ((value - min) / (max - min)) * 100 : 50;
    return interpolateColor(Math.max(0, Math.min(100, pct)));
  }

  // -------------------------------------------------------------------------
  // GeoJSON → SVG projection (simple equirectangular)
  // -------------------------------------------------------------------------
  function project(lon, lat) {
    const x = ((lon - BBOX.minLon) / (BBOX.maxLon - BBOX.minLon)) * SVG_W;
    // SVG y axis grows downward — invert latitude
    const y = ((BBOX.maxLat - lat) / (BBOX.maxLat - BBOX.minLat)) * SVG_H;
    return { x, y };
  }
  function ringToPath(ring) {
    if (!ring || ring.length === 0) return '';
    return ring
      .map((coord, i) => {
        const p = project(coord[0], coord[1]);
        return `${i === 0 ? 'M' : 'L'}${p.x.toFixed(2)},${p.y.toFixed(2)}`;
      })
      .join(' ') + ' Z';
  }
  function featureToPath(feature) {
    const g = feature.geometry;
    if (!g) return '';
    if (g.type === 'Polygon') {
      return g.coordinates.map(ringToPath).join(' ');
    }
    if (g.type === 'MultiPolygon') {
      return g.coordinates
        .map((poly) => poly.map(ringToPath).join(' '))
        .join(' ');
    }
    return '';
  }
  function featureCentroid(feature) {
    const g = feature.geometry;
    if (!g) return null;
    let ring = null;
    if (g.type === 'Polygon') ring = g.coordinates[0];
    else if (g.type === 'MultiPolygon') ring = g.coordinates[0][0];
    if (!ring || ring.length === 0) return null;
    let sx = 0, sy = 0;
    for (const c of ring) { sx += c[0]; sy += c[1]; }
    return { lon: sx / ring.length, lat: sy / ring.length };
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------
  const JordanHeatmap = {
    init,
    resetZoom,
    zoomIn,
    zoomOut,
  };

  function init() {
    if (state.initialized) return;
    const canvas = document.getElementById('heatmapCanvas');
    if (!canvas) return;
    state.initialized = true;

    bindControls();
    showSkeleton(true);
    Promise.all([
      apiGet('/indicators').catch(() => ({ indicators: [] })),
      apiGet('/data').catch((e) => { console.error('data load failed', e); throw e; }),
      apiGet('/geojson').catch(() => ({ features: [] })),
      apiGet('/daily-update').catch(() => ({})),
    ])
      .then(([indRes, mapRes, gjRes, dailyRes]) => {
        state.indicators = indRes.indicators || [];
        state.mapData = mapRes;
        state.governorates = mapRes.governorates || [];
        state.geojson = gjRes;
        renderLastUpdate(dailyRes);
        populateIndicatorSelect();
        populateGovFilter();
        renderMap();
        bindGovernorateEvents();
        showSkeleton(false);
        syncAnalyticsFilterState();
      })
      .catch((err) => {
        console.error('Heat map init failed', err);
        showError(true);
        showSkeleton(false);
      });
  }

  function bindControls() {
    document.getElementById('zoomIn')?.addEventListener('click', zoomIn);
    document.getElementById('zoomOut')?.addEventListener('click', zoomOut);
    document.getElementById('zoomReset')?.addEventListener('click', resetZoom);
    document.getElementById('heatmapRefresh')?.addEventListener('click', () => {
      state.initialized = false; state.geojson = null; state.mapData = null;
      init();
    });
    document.getElementById('heatmapIndicator')?.addEventListener('change', (e) => {
      state.indicator = e.target.value || '';
      paintGovernorates();
      updateMapTitle();
    });
    var govFilter = document.getElementById('heatmapGovFilter');
    if (govFilter) {
      govFilter.addEventListener('change', function () {
        var val = govFilter.value;
        if (window.AnalyticsFilterState) {
          window.AnalyticsFilterState.setState({ governorate: val || 'all' }, 'heatmap');
        }
        if (val && val !== 'all') {
          selectGovernorate(val);
        } else {
          state.selectedSlug = null;
          resetSidePanel();
          resetZoom();
        }
      });
    }
  }

  function populateIndicatorSelect() {
    const sel = document.getElementById('heatmapIndicator');
    if (!sel) return;
    const indicators = state.indicators || [];
    sel.innerHTML = '';
    const composite = document.createElement('option');
    composite.value = '';
    composite.textContent = t('Overall risk (composite)', 'الخطر الإجمالي (مركّب)');
    sel.appendChild(composite);
    indicators.forEach((ind) => {
      const opt = document.createElement('option');
      opt.value = ind.key;
      opt.textContent = currentLang() === 'en' ? ind.name_en : ind.name_ar;
      sel.appendChild(opt);
    });
  }

  function populateGovFilter() {
    var sel = document.getElementById('heatmapGovFilter');
    if (!sel) return;
    while (sel.options.length > 1) sel.remove(1);
    (state.governorates || []).forEach(function (g) {
      var opt = document.createElement('option');
      opt.value = g.slug || g.id || '';
      opt.textContent = currentLang() === 'ar' ? (g.name_ar || g.name || g.slug) : (g.name_en || g.name || g.slug);
      sel.appendChild(opt);
    });
  }

  function updateMapTitle() {
    // Title is now the h1 in the page header; update subtitle area if present
  }

  function renderLastUpdate(daily) {
    const el = document.getElementById('heatmapLastUpdate');
    if (!el) return;
    if (daily && daily.last_update) {
      el.textContent = t('Last update: ', 'آخر تحديث: ') + formatDate(daily.last_update);
    } else if (state.mapData && state.mapData.last_update) {
      el.textContent = t('Last update: ', 'آخر تحديث: ') + formatDate(state.mapData.last_update);
    }
  }

  function formatDate(iso) {
    try {
      const d = new Date(iso);
      return d.toLocaleString(currentLang() === 'en' ? 'en-US' : 'ar-JO',
        { dateStyle: 'medium', timeStyle: 'short' });
    } catch (_) { return iso || '--'; }
  }

  function renderMap() {
    const canvas = document.getElementById('heatmapCanvas');
    if (!canvas) return;
    // Remove any existing SVG
    const existing = canvas.querySelector('svg');
    if (existing) existing.remove();
    if (!state.geojson || !state.geojson.features || state.geojson.features.length === 0) {
      showError(true);
      return;
    }
    // Filter to governorate level only (skip qada' subdivisions)
    const features = state.geojson.features.filter(
      (f) => (f.properties && (f.properties.level === 'governorate' || !f.properties.level))
    );

    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 ' + SVG_W + ' ' + SVG_H);
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    svg.setAttribute('id', 'jordanMapSvg');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', t('Jordan governorate map', 'خريطة محافظات الأردن'));

    const govByCode = {};
    (state.governorates || []).forEach((g) => { govByCode[g.code] = g; });

    // 1. Draw governorate polygons
    const pathsGroup = document.createElementNS(SVG_NS, 'g');
    pathsGroup.setAttribute('id', 'governoratePaths');
    features.forEach((feature) => {
      const props = feature.properties || {};
      const code = props.admin_code || props.id;
      const gov = govByCode[code] || {};
      const slug = gov.slug || (props.id ? String(props.id).toLowerCase().replace('jo-','') : '');
      const path = document.createElementNS(SVG_NS, 'path');
      path.setAttribute('d', featureToPath(feature));
      path.setAttribute('class', 'gov-path');
      path.setAttribute('data-gov-slug', slug);
      path.setAttribute('data-gov-code', code);
      path.setAttribute('data-gov-name-en', props.name || gov.name_en || slug);
      path.setAttribute('data-gov-name-ar', props.name_ar || gov.name_ar || slug);
      pathsGroup.appendChild(path);
    });
    svg.appendChild(pathsGroup);

    // 2. Draw labels
    const labelsGroup = document.createElementNS(SVG_NS, 'g');
    labelsGroup.setAttribute('id', 'governorateLabels');
    features.forEach((feature) => {
      const c = featureCentroid(feature);
      if (!c) return;
      const p = project(c.lon, c.lat);
      const props = feature.properties || {};
      const label = document.createElementNS(SVG_NS, 'text');
      label.setAttribute('class', 'gov-label');
      label.setAttribute('x', p.x);
      label.setAttribute('y', p.y - 4);
      label.setAttribute('text-anchor', 'middle');
      label.textContent = currentLang() === 'en' ? props.name : (props.name_ar || props.name);
      labelsGroup.appendChild(label);
    });
    svg.appendChild(labelsGroup);

    // 3. Draw numeric value badges (only when zoomed)
    const valuesGroup = document.createElementNS(SVG_NS, 'g');
    valuesGroup.setAttribute('id', 'governorateValues');
    features.forEach((feature) => {
      const c = featureCentroid(feature);
      if (!c) return;
      const p = project(c.lon, c.lat);
      const props = feature.properties || {};
      const code = props.admin_code || props.id;
      const gov = govByCode[code];
      if (!gov) return;
      const bg = document.createElementNS(SVG_NS, 'rect');
      bg.setAttribute('x', p.x - 16);
      bg.setAttribute('y', p.y + 4);
      bg.setAttribute('width', 32);
      bg.setAttribute('height', 14);
      bg.setAttribute('rx', 3);
      bg.setAttribute('class', 'gov-value-bg');
      bg.setAttribute('data-gov-code', code);
      const txt = document.createElementNS(SVG_NS, 'text');
      txt.setAttribute('class', 'gov-value-badge');
      txt.setAttribute('x', p.x);
      txt.setAttribute('y', p.y + 14);
      txt.setAttribute('text-anchor', 'middle');
      txt.textContent = '--';
      txt.setAttribute('data-gov-code', code);
      valuesGroup.appendChild(bg);
      valuesGroup.appendChild(txt);
    });
    svg.appendChild(valuesGroup);

    canvas.appendChild(svg);

    paintGovernorates();
    renderLegend();
    bindGovernorateEvents();
  }

  function renderLegend() {
    var legend = document.getElementById('heatmapLegend');
    if (!legend) return;
    var items = [
      { color: '#22C55E', label: t('Low (0-25)', '\u0645\u0646\u062E\u0641\u0636 (0-25)') },
      { color: '#F59E0B', label: t('Medium (25-50)', '\u0645\u062A\u0648\u0633\u0637 (25-50)') },
      { color: '#FD7E14', label: t('High (50-75)', '\u0645\u0631\u062A\u0641\u0639 (50-75)') },
      { color: '#EF4444', label: t('Critical (75-100)', '\u062D\u0631\u062C (75-100)') },
    ];
    legend.innerHTML = items.map(function (item) {
      return '<div class="legend-item"><span class="legend-swatch" style="background:' + item.color + '"></span> ' + escapeHtml(item.label) + '</div>';
    }).join('');
  }

  function paintGovernorates() {
    const paths = document.querySelectorAll('#governoratePaths .gov-path');
    const govByCode = {};
    (state.governorates || []).forEach((g) => { govByCode[g.code] = g; });

    paths.forEach((path) => {
      const code = path.getAttribute('data-gov-code');
      const gov = govByCode[code];
      let color = '#9CA3AF';
      let displayValue = '--';
      if (gov) {
        if (state.indicator) {
          const v = gov.main_indicators ? gov.main_indicators[state.indicator] : null;
          color = colorForIndicator(v);
          displayValue = v == null ? '--' : Number(v).toFixed(1);
        } else {
          color = riskColorForScore(gov.risk_score);
          displayValue = Number(gov.risk_score || 0).toFixed(0);
        }
      }
      path.setAttribute('fill', color);
      const badge = document.querySelector(`#governorateValues text.gov-value-badge[data-gov-code="${code}"]`);
      if (badge) badge.textContent = displayValue;
      const bg = document.querySelector(`#governorateValues rect.gov-value-bg[data-gov-code="${code}"]`);
      if (bg) {
        bg.setAttribute('fill', color);
        bg.setAttribute('opacity', state.zoom > 1.5 ? '0.95' : '0');
      }
    });
  }

  function bindGovernorateEvents() {
    const tooltip = document.getElementById('heatmapTooltip');
    document.querySelectorAll('.gov-path').forEach((path) => {
      var slug = path.getAttribute('data-gov-slug');
      var govNameEn = path.getAttribute('data-gov-name-en') || slug;
      var govNameAr = path.getAttribute('data-gov-name-ar') || slug;
      path.setAttribute('tabindex', '0');
      path.setAttribute('role', 'button');
      path.setAttribute('aria-label', currentLang() === 'en' ? govNameEn : govNameAr);
      path.addEventListener('mouseenter', (e) => showTooltip(e, path, tooltip));
      path.addEventListener('mousemove', (e) => moveTooltip(e, tooltip));
      path.addEventListener('mouseleave', () => hideTooltip(tooltip));
      path.addEventListener('click', () => selectGovernorate(slug));
      path.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          selectGovernorate(slug);
        }
      });
      path.addEventListener('focus', (e) => showTooltip(e, path, tooltip));
      path.addEventListener('blur', () => hideTooltip(tooltip));
    });
  }

  function showTooltip(e, path, tooltip) {
    if (!tooltip) return;
    const code = path.getAttribute('data-gov-code');
    const slug = path.getAttribute('data-gov-slug');
    const gov = (state.governorates || []).find((g) => g.code === code);
    const risk = gov ? riskLevelForScore(gov.risk_score) : null;
    const indicatorLabel = state.indicator
      ? ((state.indicators || []).find((i) => i.key === state.indicator) || {}).name_en || state.indicator
      : t('Composite risk', 'الخطر المركّب');
    const value = state.indicator
      ? (gov ? gov.main_indicators?.[state.indicator] : null)
      : (gov ? gov.risk_score : null);
    const lang = currentLang();
    const name = lang === 'en'
      ? (path.getAttribute('data-gov-name-en') || code)
      : (path.getAttribute('data-gov-name-ar') || code);
    var tooltipRiskKey = risk ? (risk.max <= 25 ? 'low' : risk.max <= 50 ? 'medium' : risk.max <= 75 ? 'high' : 'critical') : '';
    tooltip.innerHTML = `
      <div class="tt-title">
        <span>${escapeHtml(name)}</span>
        ${risk ? `<span class="badge-risk ${tooltipRiskKey}"><i class="bi ${riskIconForLevel(tooltipRiskKey)}" aria-hidden="true"></i> ${escapeHtml(lang === 'en' ? risk.name_en : risk.name_ar)}</span>` : ''}
      </div>
      <div class="tt-row"><span class="lbl">${escapeHtml(indicatorLabel)}</span><span>${value == null ? '--' : Number(value).toFixed(1)}</span></div>
      <div class="tt-row"><span class="lbl">${t('Risk score', 'مؤشر الخطر')}</span><span>${gov ? Number(gov.risk_score || 0).toFixed(0) : '--'}</span></div>
      <div class="tt-sep"></div>
      <div class="small opacity-75">${t('Click for full breakdown', 'انقر للاطلاع على التفاصيل')}</div>
    `;
    tooltip.style.display = 'block';
    tooltip.setAttribute('aria-hidden', 'false');
    moveTooltip(e, tooltip);
  }
  function moveTooltip(e, tooltip) {
    if (!tooltip) return;
    const offset = 14;
    let x = e.clientX + offset;
    let y = e.clientY + offset;
    const rect = tooltip.getBoundingClientRect();
    if (x + rect.width > window.innerWidth - 8) x = e.clientX - rect.width - offset;
    if (y + rect.height > window.innerHeight - 8) y = e.clientY - rect.height - offset;
    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${y}px`;
  }
  function hideTooltip(tooltip) {
    if (!tooltip) return;
    tooltip.style.display = 'none';
    tooltip.setAttribute('aria-hidden', 'true');
  }

  function selectGovernorate(pathOrSlug) {
    var slug = typeof pathOrSlug === 'string' ? pathOrSlug : pathOrSlug.getAttribute('data-gov-slug');
    state.selectedSlug = slug;
    document.querySelectorAll('.gov-path').forEach((p) => p.classList.remove('selected'));
    var pathEl = document.querySelector('.gov-path[data-gov-slug="' + slug + '"]');
    if (pathEl) pathEl.classList.add('selected');
    loadGovernorateDetail(slug);
    flyToGov(slug);
  }

  function flyToGov(slug) {
    var feature = (state.geojson && state.geojson.features || []).find(function (f) {
      return f.properties && f.properties.slug === slug;
    });
    if (!feature) return;
    var centroid = featureCentroid(feature);
    if (!centroid) return;

    var svgEl = document.querySelector('.heatmap-canvas svg');
    if (!svgEl) return;

    var cp = project(centroid.lon, centroid.lat);
    var svgW = 800, svgH = 760;
    var viewSize = 200;
    var targetViewBox = [
      cp.x - viewSize / 2,
      cp.y - viewSize / 2,
      viewSize,
      viewSize
    ];

    var startViewBox = (svgEl.getAttribute('viewBox') || '0 0 800 760').split(' ').map(Number);
    var duration = 600;
    var startTime = null;

    function easeInOutCubic(t) {
      return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    }

    function animate(timestamp) {
      if (!startTime) startTime = timestamp;
      var elapsed = timestamp - startTime;
      var t = Math.min(elapsed / duration, 1);
      var e = easeInOutCubic(t);
      var vb = startViewBox.map(function (s, i) {
        return s + (targetViewBox[i] - s) * e;
      });
      svgEl.setAttribute('viewBox', vb.join(' '));
      if (t < 1) requestAnimationFrame(animate);
    }

    requestAnimationFrame(animate);
  }

  async function loadGovernorateDetail(slug) {
    if (!slug) return;
    renderSideLoading(slug);
    try {
      const [detail, correlations, regression] = await Promise.all([
        apiGet(`/governorate/${encodeURIComponent(slug)}`),
        apiGet('/correlations').catch(() => ({ matrix: [] })),
        apiGet('/regression').catch(() => ({ weights: [] })),
      ]);
      state.detail = detail;
      renderSideDetail(detail, correlations, regression);
    } catch (err) {
      console.error('Detail load failed', err);
      renderSideError(slug);
    }
  }

  // -------------------------------------------------------------------------
  // Side panel rendering
  // -------------------------------------------------------------------------
  function getSidePanel() { return document.getElementById('heatmapSidePanel'); }

  function renderSideEmpty() {
    var panel = getSidePanel();
    if (!panel) return;
    panel.innerHTML = '<div class="heatmap-skeleton" id="sideSkeleton">' +
      '<div class="skeleton-line" style="width:80%"></div>' +
      '<div class="skeleton-line" style="width:60%"></div>' +
      '<div class="skeleton-line" style="width:90%"></div>' +
      '</div>';
  }
  function renderSideLoading(slug) {
    var panel = getSidePanel();
    if (!panel) return;
    var gov = (state.governorates || []).find((g) => g.slug === slug) || {};
    var name = currentLang() === 'en' ? (gov.name_en || slug) : (gov.name_ar || slug);
    panel.innerHTML = '<div class="side-header">' + escapeHtml(name) + '</div>' +
      '<div style="padding:var(--space-16);display:flex;align-items:center;color:var(--admin-text-muted);">' +
      '<div class="spinner-border spinner-border-sm me-2" role="status"></div>' +
      '<span>' + t('Loading details…', 'جاري تحميل التفاصيل…') + '</span></div>';
  }
  function renderSideError(slug) {
    var panel = getSidePanel();
    if (!panel) return;
    panel.innerHTML = '<div class="heatmap-error">' +
      '<p>' + t('Failed to load details. Please try again.', 'تعذر تحميل التفاصيل. يرجى المحاولة مرة أخرى.') + '</p>' +
      '<button class="btn btn-sm btn-outline-primary mt-2" onclick="window.JordanHeatmap && window.JordanHeatmap.retryDetail && window.JordanHeatmap.retryDetail(\'' + escapeAttr(slug) + '\')">' + t('Retry', 'إعادة') + '</button></div>';
  }

  function renderSideDetail(detail, correlations, regression) {
    const lang = currentLang();
    const name = lang === 'en' ? detail.name_en : detail.name_ar;
    var panel = getSidePanel();
    if (!panel) return;

    const indicators = (state.indicators || []);
    const mainKeys = indicators.map((i) => i.key);

    const mainHtml = mainKeys.map((key) => {
      const meta = indicators.find((i) => i.key === key) || {};
      const val = (detail.main_indicators || {})[key];
      const trend = (detail.trends || {})[key] || {};
      const indRisk = (detail.risk_by_indicator || {})[key] || {};
      const trendIcon = trend.direction === 'up' ? '↑' : trend.direction === 'down' ? '↓' : '→';
      const trendColor = trend.direction === 'up' ? '#22C55E' : trend.direction === 'down' ? '#EF4444' : '#6b7280';
      return `
        <li>
          <span>${escapeHtml(lang === 'en' ? (meta.name_en || key) : (meta.name_ar || key))}</span>
          <span>
            <strong>${val == null ? '--' : Number(val).toFixed(1)}</strong>
            <span style="color:${trendColor}; margin-inline-start: 0.4rem;">${trendIcon} <span dir="ltr">${trend.pct ? Math.abs(trend.pct) + '%' : ''}</span></span>
            ${indRisk.key ? `<span class="badge-risk ${escapeAttr(indRisk.key)}" style="margin-inline-start: 0.4rem;"><i class="bi ${riskIconForLevel(indRisk.key)}" aria-hidden="true"></i> ${escapeHtml(lang === 'en' ? (indRisk.name_en || '') : (indRisk.name_ar || ''))}</span>` : ''}
          </span>
        </li>
      `;
    }).join('');

    // Sub-indicators: show one block per main indicator
    const subsHtml = indicators.map((meta) => {
      const subs = meta.sub_indicators || [];
      if (!subs.length) return '';
      const items = subs.map((s) => {
        const v = (detail.sub_indicators || {})[s.key];
        const lbl = lang === 'en' ? s.name_en : s.name_ar;
        return `<li><span>${escapeHtml(lbl)}</span><span>${v == null ? '--' : formatNumber(v)}</span></li>`;
      }).join('');
      return `
        <div class="sub-section">
          <h6>${escapeHtml(lang === 'en' ? meta.name_en : meta.name_ar)}</h6>
          <ul class="sub-list">${items}</ul>
        </div>
      `;
    }).join('');

    // Correlation rows for this governorate — color-coded by strength
    const corrRows = (correlations.matrix || []).filter((r) => r.row === detail.slug || r.column === detail.slug).slice(0, 6);
    const corrHtml = corrRows.length
      ? corrRows.map((r) => {
          const partner = r.row === detail.slug ? r.column : r.row;
          const partnerMeta = indicators.find((i) => i.key === partner) || {};
          const partnerName = lang === 'en' ? (partnerMeta.name_en || partner) : (partnerMeta.name_ar || partner);
          const v = r.value == null ? null : Number(r.value);
          const color = r.color || (v == null ? '#94A3B8' : (v > 0 ? '#22C55E' : '#EF4444'));
          const vHtml = v == null ? '--' : `<span dir="ltr">${v.toFixed(2)}</span>`;
          return `<li><span>${escapeHtml(partnerName)}</span><span><span class="corr-pill" style="background:${color}">${vHtml}</span></span></li>`;
        }).join('')
      : `<li class="text-muted">${t('Not enough data for correlation.', 'لا توجد بيانات كافية للارتباط.')}</li>`;

    // Regression rows — show as horizontal bars
    const regRows = (regression.weights || []).filter((w) => w.main_indicator).slice(0, 6);
    const regHtml = regRows.length
      ? regRows.map((w) => {
          const beta = Number(w.beta_std || 0);
          const absBeta = Math.abs(beta);
          const meta = indicators.find((i) => i.key === w.main_indicator) || {};
          const metaName = lang === 'en' ? (meta.name_en || w.main_indicator) : (meta.name_ar || w.main_indicator);
          const barColor = absBeta >= 0.20 ? '#F59E0B' : '#94A3B8';
          const widthPct = Math.min(100, absBeta * 100);
          const arrow = lang === 'en' ? '→' : '←';
          const betaHtml = w.beta_std == null ? '--' : `<span dir="ltr">${beta.toFixed(2)}</span>`;
          return `<li class="reg-row">
            <div class="reg-row-head">
              <span>${escapeHtml(w.sub_indicator)} <span class="text-muted">${arrow}</span> ${escapeHtml(metaName)}</span>
              <span>${betaHtml}${w.high_impact ? ' ★' : ''}</span>
            </div>
            <div class="reg-bar-track"><div class="reg-bar-fill" style="width:${widthPct}%; background:${barColor}"></div></div>
          </li>`;
        }).join('')
      : `<li class="text-muted">${t('No regression weights available.', 'لا توجد أوزان انحدار متاحة.')}</li>`;

    // Alerts
    var alertSeverityIcon = function (sev) {
      switch (sev) {
        case 'critical': return 'bi-x-octagon-fill';
        case 'high': return 'bi-exclamation-diamond-fill';
        case 'medium': return 'bi-exclamation-triangle-fill';
        case 'low': return 'bi-check-circle';
        default: return 'bi-info-circle';
      }
    };
    const alertsHtml = (detail.alerts || []).length
      ? detail.alerts.map((a) => `
        <div class="alert-row">
          <i class="bi ${alertSeverityIcon(a.severity)}" aria-hidden="true"></i>
          <span>${escapeHtml(a.message || a.metric || '')}</span>
          <span class="sev ${escapeAttr(a.severity)}">${escapeHtml(a.severity)}</span>
        </div>`).join('')
      : `<div class="text-muted small">${t('No active alerts.', 'لا توجد تنبيهات نشطة.')}</div>`;

    const risk = detail.risk_level || {};
    const action = detail.recommended_action || {};

    // Risk-score sparkline (loaded async after panel renders)
    const sparklinePlaceholderId = `spark-${detail.slug}`;

    panel.innerHTML = `
      <div class="side-header">${escapeHtml(name)}</div>
      <div class="kpi-grid">
        <div class="kpi-item">
          <div class="kpi-label">${t('Composite risk', 'الخطر المركّب')}</div>
          <div class="kpi-value">${Number(detail.risk_score || 0).toFixed(1)}</div>
        </div>
        <div class="kpi-item">
          <div class="kpi-label">${t('Risk level', 'مستوى الخطر')}</div>
          <div class="kpi-value">
            <span class="badge-risk ${escapeAttr(risk.key || 'low')}"><i class="bi ${riskIconForLevel(risk.key || 'low')}" aria-hidden="true"></i> ${escapeHtml(lang === 'en' ? (risk.name_en || '') : (risk.name_ar || ''))}</span>
          </div>
        </div>
      </div>
      <div class="alert alert-light border small mb-2" role="status">
        <strong>${t('Recommended action:', 'الإجراء الموصى به:')}</strong>
        ${escapeHtml(lang === 'en' ? (action.en || '') : (action.ar || ''))}
      </div>
      <div class="sub-section">
        <h6>${t('Risk trend (30 days)', 'اتجاه الخطر (30 يوماً)')}</h6>
        <div id="${sparklinePlaceholderId}" class="risk-sparkline">
          <span class="text-muted small">${t('Loading…', 'جاري التحميل…')}</span>
        </div>
      </div>
      <h6 class="text-uppercase small fw-bold text-secondary">${t('Main indicators', 'المؤشرات الرئيسية')}</h6>
      <ul class="sub-list">${mainHtml}</ul>
      ${subsHtml}
      <div class="sub-section">
        <h6>${t('Correlation (vs other indicators)', 'الارتباط (مقارنة بالمؤشرات الأخرى)')}</h6>
        <ul class="sub-list">${corrHtml}</ul>
      </div>
      <div class="sub-section">
        <h6>${t('Regression weights', 'أوزان الانحدار')}</h6>
        <ul class="sub-list">${regHtml}</ul>
      </div>
      <div class="sub-section">
        <h6>${t('Related alerts', 'التنبيهات المرتبطة')}</h6>
        ${alertsHtml}
      </div>
      <div class="sub-section">
        <small class="text-muted">${t('Last update:', 'آخر تحديث:')} ${escapeHtml(formatDate(detail.last_update))}</small>
      </div>
    `;
    if (detail.recommended_actions && detail.recommended_actions.length > 0) {
      var actionsHtml = '<div class="sub-section"><h6 style="font:var(--type-card-title);color:#0E334F;margin-bottom:8px;">' +
        (currentLang() === 'ar' ? 'إجراءات موصى بها' : 'Recommended Actions') + '</h6><ul class="sub-list">';
      detail.recommended_actions.forEach(function (action) {
        var icon = action.priority === 'high' ? '\u26A0\uFE0F' : (action.priority === 'medium' ? '\uD83D\uDCCB' : '\uD83D\uDCA1');
        actionsHtml += '<li>' + icon + ' ' + escapeHtml(action.text || action.description || action) + '</li>';
      });
      actionsHtml += '</ul></div>';
      panel.insertAdjacentHTML('beforeend', actionsHtml);
    }
    // Load the historical risk trend asynchronously
    loadRiskSparkline(detail.slug, sparklinePlaceholderId);
  }

  /**
   * Fetch the historical risk-score time series for a governorate and
   * render it as an SVG sparkline inside the given container.
   */
  async function loadRiskSparkline(slug, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    try {
      const data = await apiGet(`/governorate/${encodeURIComponent(slug)}/history?days=30`);
      const history = data.history || [];
      if (history.length < 2) {
        container.innerHTML = `<span class="text-muted small">${t('Not enough history yet.', 'لا يوجد تاريخ كافٍ بعد.')}</span>`;
        return;
      }
      const w = container.clientWidth || 280;
      const h = 60;
      const padL = 4, padR = 4, padT = 6, padB = 6;
      const x0 = padL, y0 = padT;
      const x1 = w - padR, y1 = h - padB;
      const xs = history.map((p) => p.risk_score);
      const minR = Math.min(...xs);
      const maxR = Math.max(...xs);
      const rangeR = Math.max(maxR - minR, 1);
      const points = history.map((p, i) => {
        const x = x0 + (x1 - x0) * (i / (history.length - 1));
        const y = y0 + (y1 - y0) * (1 - (p.risk_score - minR) / rangeR);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      });
      const lastPoint = history[history.length - 1];
      const lastColor = interpolateColor(lastPoint.risk_score);
      container.innerHTML = `
        <svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none" class="risk-sparkline-svg">
          <polyline points="${points.join(' ')}" fill="none" stroke="${lastColor}" stroke-width="1.5" />
          <circle cx="${points[points.length - 1].split(',')[0]}" cy="${points[points.length - 1].split(',')[1]}" r="2.5" fill="${lastColor}" />
        </svg>
        <div class="d-flex justify-content-between small text-muted mt-1">
          <span>${escapeHtml(history[0].date)}</span>
          <span><strong style="color:${lastColor}">${lastPoint.risk_score.toFixed(1)}</strong> <span class="text-muted">·</span> ${escapeHtml(lastPoint.date)}</span>
        </div>
      `;
    } catch (err) {
      container.innerHTML = `<span class="text-muted small">${t('Trend unavailable.', 'الاتجاه غير متاح.')}</span>`;
    }
  }

  // -------------------------------------------------------------------------
  // Zoom controls
  // -------------------------------------------------------------------------
  function zoomIn() {
    const next = Math.min(state.zoom * ZOOM_STEP, ZOOM_MAX);
    setZoom(next, true);
  }
  function zoomOut() {
    const next = Math.max(state.zoom / ZOOM_STEP, ZOOM_MIN);
    setZoom(next, true);
  }
  function resetZoom() {
    state.zoom = 1.0;
    state.pan = { x: 0, y: 0 };
    var svgEl = document.querySelector('.heatmap-canvas svg');
    if (svgEl) {
      svgEl.setAttribute('viewBox', '0 0 ' + SVG_W + ' ' + SVG_H);
    }
  }
  function setZoom(value, animated) {
    state.zoom = value;
    if (state.selectedSlug) {
      // Optionally pan to selected governorate centroid
      const path = document.querySelector(`.gov-path[data-gov-slug="${state.selectedSlug}"]`);
      if (path) {
        const bbox = path.getBBox();
        const cx = bbox.x + bbox.width / 2;
        const cy = bbox.y + bbox.height / 2;
        const targetX = (SVG_W / 2 - cx) * (value - 1);
        const targetY = (SVG_H / 2 - cy) * (value - 1);
        state.pan = { x: targetX, y: targetY };
      }
    }
    applyZoom(animated);
  }
  function applyZoom(animated) {
    var svgEl = document.querySelector('.heatmap-canvas svg');
    if (!svgEl) return;
    var cx = SVG_W / 2 + state.pan.x;
    var cy = SVG_H / 2 + state.pan.y;
    var vw = SVG_W / state.zoom;
    var vh = SVG_H / state.zoom;
    svgEl.setAttribute('viewBox', (cx - vw / 2) + ' ' + (cy - vh / 2) + ' ' + vw + ' ' + vh);
    paintGovernorates();
  }

  // -------------------------------------------------------------------------
  // UI state helpers
  // -------------------------------------------------------------------------
  function showSkeleton(show) {
    var canvas = document.getElementById('heatmapCanvas');
    if (!canvas) return;
    var sk = canvas.querySelector('.heatmap-skeleton');
    if (sk) sk.style.display = show ? 'flex' : 'none';
  }
  function showError(show) {
    var canvas = document.getElementById('heatmapCanvas');
    if (!canvas) return;
    var err = canvas.querySelector('.heatmap-error');
    if (err) err.style.display = show ? 'block' : 'none';
  }

  function formatNumber(v) {
    const n = Number(v);
    if (Number.isNaN(n)) return '--';
    const locale = currentLang() === 'en' ? 'en-US' : 'ar-JO';
    if (n >= 1000) return n.toLocaleString(locale);
    return n.toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  }
  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
  function escapeAttr(s) { return escapeHtml(s); }

  function resetSidePanel() {
    var panel = document.getElementById('heatmapSidePanel');
    if (!panel) return;
    panel.innerHTML = '<div class="heatmap-skeleton" id="sideSkeleton">' +
      '<div class="skeleton-line" style="width:80%"></div>' +
      '<div class="skeleton-line" style="width:60%"></div>' +
      '<div class="skeleton-line" style="width:90%"></div>' +
      '</div>';
    document.querySelectorAll('.gov-path').forEach(function (p) { p.classList.remove('selected'); });
    var svgEl = document.querySelector('.heatmap-canvas svg');
    if (svgEl) svgEl.setAttribute('viewBox', '0 0 ' + SVG_W + ' ' + SVG_H);
  }

  function syncAnalyticsFilterState() {
    if (!window.AnalyticsFilterState) return;
    var filterState = window.AnalyticsFilterState.getState();
    if (filterState.indicator && filterState.indicator !== 'all') {
      var indSel = document.getElementById('heatmapIndicator');
      if (indSel) {
        indSel.value = filterState.indicator;
        state.indicator = filterState.indicator;
      }
    }
    if (filterState.governorate && filterState.governorate !== 'all') {
      selectGovernorate(filterState.governorate);
    }
    window.AnalyticsFilterState.subscribe(function (s) {
      if (s.source === 'heatmap') return;
      if (s.indicator && s.indicator !== state.indicator) {
        state.indicator = s.indicator;
        var indSel = document.getElementById('heatmapIndicator');
        if (indSel) indSel.value = s.indicator;
        paintGovernorates();
        updateMapTitle();
      }
      if (s.governorate && s.governorate !== state.selectedSlug) {
        var heatGovFilter = document.getElementById('heatmapGovFilter');
        if (heatGovFilter) heatGovFilter.value = s.governorate === 'all' ? 'all' : s.governorate;
        if (s.governorate === 'all') {
          state.selectedSlug = null;
          resetSidePanel();
          resetZoom();
        } else {
          selectGovernorate(s.governorate);
        }
      }
    });
    var indSel = document.getElementById('heatmapIndicator');
    if (indSel) {
      indSel.addEventListener('change', function () {
        if (window.AnalyticsFilterState) {
          window.AnalyticsFilterState.setState({ indicator: indSel.value }, 'heatmap');
        }
      });
    }
  }

  // -------------------------------------------------------------------------
  // Export
  // -------------------------------------------------------------------------
  window.JordanHeatmap = JordanHeatmap;
  JordanHeatmap.retryDetail = function(slug) { loadGovernorateDetail(slug); };
  document.addEventListener('DOMContentLoaded', init);
})();
