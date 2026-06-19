/**
 * Jordan Geographic Risk Analysis System
 *
 * Government-grade 3D visualization using deck.gl WebGL.
 * Viewport is permanently constrained to the Hashemite Kingdom of Jordan.
 * NO neighboring country geometry is ever rendered.
 *
 * Data flow:
 *   GET /api/admin/heat-map/indicators
 *   GET /api/admin/heat-map/data
 *   GET /api/admin/heat-map/geojson
 *   GET /api/admin/heat-map/daily-update
 *   GET /api/admin/heat-map/governorate/{slug}
 *   GET /api/admin/heat-map/governorate/{slug}/history?days=30
 *   GET /api/admin/heat-map/correlations
 */
(function () {
  'use strict';

  /* =========================================================================
     CONSTANTS — Jordan absolute geographic boundaries
     These values enforce the ABSOLUTE RESTRICTION: only Jordan is displayed.
     ========================================================================= */
  const JORDAN = {
    center:  [36.2,  31.3],
    minLon:  34.90, maxLon: 39.40,
    minLat:  29.10, maxLat: 33.45,
    minZoom: 5.5,
    maxZoom: 10.5,
  };

  const INITIAL_VIEW = {
    longitude:  36.2,
    latitude:   31.3,
    zoom:       6.2,
    pitch:      48,
    bearing:   -8,
    transitionDuration: 0,
  };

  const API = '/api/admin/heat-map';

  // JO-XX code → slug mapping (from heatmap/backend/constants.py)
  const CODE_TO_SLUG = {
    'JO-AM': 'amman',   'JO-IR': 'irbid',   'JO-ZA': 'zarqa',
    'JO-MA': 'mafraq',  'JO-JA': 'jerash',  'JO-AJ': 'ajloun',
    'JO-BA': 'balqa',   'JO-MD': 'madaba',  'JO-KA': 'karak',
    'JO-TA': 'tafileh', 'JO-MN': 'maan',    'JO-AQ': 'aqaba',
  };

  /* =========================================================================
     MODULE STATE
     ========================================================================= */
  let deckgl       = null;
  let viewState    = { ...INITIAL_VIEW };
  let is3D         = true;

  const state = {
    geojson:      null,
    governorates: [],
    indicators:   [],
    mapData:      null,
    selectedSlug: null,
    indicator:    '',
    loading:      false,
    initialized:  false,
  };

  /* =========================================================================
     COLOR SYSTEM
     ========================================================================= */
  function riskRGB(score) {
    const s = Math.max(0, Math.min(100, Number(score) || 0));
    // 0=green(safe)  33=amber  66=orange  100=red(critical)
    const stops = [
      { t:   0, r:  34, g: 197, b:  94 },
      { t:  33, r: 245, g: 158, b:  11 },
      { t:  66, r: 249, g: 115, b:  22 },
      { t: 100, r: 239, g:  68, b:  68 },
    ];
    let lo = stops[0], hi = stops[stops.length - 1];
    for (let i = 0; i < stops.length - 1; i++) {
      if (s >= stops[i].t && s <= stops[i + 1].t) { lo = stops[i]; hi = stops[i + 1]; break; }
    }
    const f = hi.t === lo.t ? 0 : (s - lo.t) / (hi.t - lo.t);
    return [
      Math.round(lo.r + (hi.r - lo.r) * f),
      Math.round(lo.g + (hi.g - lo.g) * f),
      Math.round(lo.b + (hi.b - lo.b) * f),
    ];
  }

  function riskHex(score) {
    const [r, g, b] = riskRGB(score);
    return '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('');
  }

function riskLevel(score) {
     const s = Number(score) || 0;
     if (s <= 25) return { key: 'low',      en: 'Low',      ar: 'منخفض',  icon: 'bi-check-circle-fill',         color: '#4caf50' };
     if (s <= 50) return { key: 'medium',   en: 'Medium',   ar: 'متوسط',  icon: 'bi-exclamation-triangle-fill', color: '#ff9800' };
     if (s <= 75) return { key: 'high',     en: 'High',     ar: 'مرتفع',  icon: 'bi-exclamation-diamond-fill',  color: '#ff5722' };
     return              { key: 'critical', en: 'Critical', ar: 'حرج',    icon: 'bi-x-octagon-fill',            color: '#ef5350' };
   }

  function indicatorRGB(value, minV, maxV) {
    if (value == null) return [156, 163, 175];
    const pct = maxV > minV ? ((value - minV) / (maxV - minV)) * 100 : 50;
    return riskRGB(Math.max(0, Math.min(100, pct)));
  }

/* =========================================================================
      LANGUAGE HELPERS — DELEGATE TO CENTRAL auth.js
      auth.js provides: currentLanguage() and t(arText, enText)
      ========================================================================= */
   const lang = typeof currentLanguage === 'function' ? () => currentLanguage() : function() {
     const s = localStorage.getItem('kinjo_lang') || localStorage.getItem('admin_language') || '';
     return s.toLowerCase().startsWith('en') || document.documentElement.lang?.toLowerCase().startsWith('en') ? 'en' : 'ar';
   };
   function t(en, ar) { return lang() === 'ar' ? ar : en; }

  /* =========================================================================
     API HELPERS
     ========================================================================= */
  async function get(path) {
    const r = await fetch(`${API}${path}`, {
      headers: { Accept: 'application/json' },
      credentials: 'same-origin',
    });
    if (!r.ok) {
      let msg = r.statusText;
      try { msg = (await r.json()).detail || msg; } catch (_) { /* noop */ }
      throw new Error(`HTTP ${r.status}: ${msg}`);
    }
    return r.json();
  }

  /* =========================================================================
     GEOJSON ENRICHMENT
     Merges live API data (risk scores, indicators) into GeoJSON features.
     Only governorate-level features are kept — qada (sub-district) features
     are discarded. This ensures ONLY Jordan's 12 governorates render.
     ========================================================================= */
  function enrichGeoJSON(geojson, governorates) {
    const byCode = {};
    const bySlug = {};
    governorates.forEach(g => { byCode[g.code] = g; bySlug[g.slug] = g; });

    // Pre-compute indicator range once rather than O(n) per feature
    let indMinV = 0, indMaxV = 100;
    if (state.indicator) {
      const allVals = governorates
        .map(g => g.main_indicators?.[state.indicator])
        .filter(v => v != null)
        .map(Number);
      if (allVals.length) { indMinV = Math.min(...allVals); indMaxV = Math.max(...allVals); }
    }

    const features = (geojson.features || []).filter(f => {
      const lvl = f.properties && f.properties.level;
      return !lvl || lvl === 'governorate';
    }).map(f => {
      const code = f.properties.admin_code || f.properties.id;
      const slug = CODE_TO_SLUG[code] || code?.replace('JO-', '').toLowerCase() || '';
      const gov  = byCode[code] || bySlug[slug] || {};

      let colorRGB = riskRGB(gov.risk_score ?? 0);
      if (state.indicator && gov.main_indicators) {
        const v = gov.main_indicators[state.indicator];
        colorRGB = indicatorRGB(v != null ? Number(v) : null, indMinV, indMaxV);
      }

      return {
        ...f,
        properties: {
          ...f.properties,
          slug,
          admin_code: code,
          risk_score: gov.risk_score ?? 0,
          name_en:    gov.name_en  || f.properties.name    || slug,
          name_ar:    gov.name_ar  || f.properties.name_ar || slug,
          colorRGB,
          gov_data:   gov,
        },
      };
    });

    return { ...geojson, features };
  }

  /* =========================================================================
     LABEL DATA — centroid positions for TextLayer
     ========================================================================= */
  function buildLabelData(governorates) {
    return governorates.map(g => ({
      position: [g.center[0], g.center[1], is3D ? (g.risk_score || 0) * 8000 + 500 : 0],
      nameEn:   g.name_en,
      nameAr:   g.name_ar,
      slug:     g.slug,
      risk:     g.risk_score || 0,
    }));
  }

  /* =========================================================================
     DECK.GL INITIALIZATION
     ========================================================================= */
  function initDeckGL() {
    const container = document.getElementById('deckgl-container');
    if (!container || typeof deck === 'undefined') {
      console.error('[GeoIntel] deck.gl not loaded');
      showMapError(true);
      return;
    }

    deckgl = new deck.DeckGL({
      container,
      initialViewState: INITIAL_VIEW,
      controller: {
        dragPan:     true,
        dragRotate:  true,
        scrollZoom:  true,
        touchZoom:   true,
        touchRotate: true,
        keyboard:    true,
        doubleClickZoom: false,
        inertia:     true,
      },
      onViewStateChange: clampViewState,
      onHover: handleHover,
      onClick: handleClick,
      layers: [],
      getCursor: ({ isHovering }) => isHovering ? 'pointer' : 'grab',
    });

    updateCompass(INITIAL_VIEW.bearing);
  }

  // Enforce Jordan-only viewport — this is what guarantees no foreign territory
  function clampViewState({ viewState: vs }) {
    const clamped = {
      ...vs,
      longitude: Math.max(JORDAN.minLon, Math.min(JORDAN.maxLon, vs.longitude)),
      latitude:  Math.max(JORDAN.minLat, Math.min(JORDAN.maxLat, vs.latitude)),
      zoom:      Math.max(JORDAN.minZoom, Math.min(JORDAN.maxZoom, vs.zoom)),
    };
    viewState = clamped;
    updateCompass(clamped.bearing || 0);
    return clamped;
  }

  /* =========================================================================
     LAYER RENDERING
     ========================================================================= */
  function updateLayers() {
    if (!deckgl || !state.geojson || !state.governorates.length) return;

    const enriched = enrichGeoJSON(state.geojson, state.governorates);
    const labels   = buildLabelData(state.governorates);

    const govLayer = new deck.GeoJsonLayer({
      id: 'jordan-governorates',
      data: enriched,
      filled:   true,
      extruded: is3D,
      wireframe: is3D,
      getElevation:  f => is3D ? (f.properties.risk_score || 0) * 8000 : 1,
      getFillColor:  f => {
        const [r, g, b] = f.properties.colorRGB || riskRGB(f.properties.risk_score || 0);
        const alpha = f.properties.slug === state.selectedSlug ? 240 : 200;
        return [r, g, b, alpha];
      },
      getLineColor:  f => {
        if (f.properties.slug === state.selectedSlug) return [255, 255, 255, 180];
        return is3D ? [255, 255, 255, 35] : [255, 255, 255, 80];
      },
      lineWidthUnits:     'pixels',
      lineWidthMinPixels: 1,
      getLineWidth:       f => f.properties.slug === state.selectedSlug ? 2 : 1,
      pickable: true,
      autoHighlight: true,
      highlightColor: [255, 255, 255, 50],
      transitions: {
        getElevation:  { type: 'spring', stiffness: 0.05, damping: 0.5 },
        getFillColor:  { duration: 500 },
      },
      updateTriggers: {
        getElevation:  [is3D, state.indicator],
        getFillColor:  [state.indicator, state.selectedSlug, state.governorates],
        getLineColor:  [state.selectedSlug, is3D],
        getLineWidth:  [state.selectedSlug],
      },
    });

    const labelLayer = new deck.TextLayer({
      id: 'gov-labels',
      data: labels,
      getPosition:         d => d.position,
      getText:             d => lang() === 'ar' ? d.nameAr : d.nameEn,
      getSize:             14,
      sizeMaxPixels:       18,
      sizeMinPixels:       8,
      getColor:            d => [255, 255, 255, d.slug === state.selectedSlug ? 255 : 190],
      getBackgroundColor:  d => { const [r, g, b] = riskRGB(d.risk); return [r, g, b, 170]; },
      background:          true,
      backgroundPadding:   [5, 2, 5, 2],
      borderRadius:        3,
      fontFamily:          '"Cairo", "Inter", "Noto Sans Arabic", sans-serif',
      fontWeight:          '700',
      billboard:           true,
      getTextAnchor:       'middle',
      getAlignmentBaseline: 'center',
      pickable:            false,
      updateTriggers: {
        getText:            [lang()],
        getColor:           [state.selectedSlug],
        getBackgroundColor: [state.governorates],
        getPosition:        [is3D, state.indicator],
      },
    });

    // Outer Jordan border glow — drawn beneath govLayer for the blue halo effect
    const borderGlow = new deck.GeoJsonLayer({
      id: 'jordan-border',
      data: enriched,
      stroked:  true,
      filled:   false,
      extruded: false,
      getLineColor:       () => [30, 136, 229, 60],
      lineWidthMinPixels: 3,
      pickable: false,
    });

    deckgl.setProps({ layers: [borderGlow, govLayer, labelLayer] });
  }

  /* =========================================================================
     HOVER & CLICK
     ========================================================================= */
  function handleHover({ object, x, y }) {
    const tooltip = document.getElementById('geoTooltip');
    if (!tooltip) return;
    if (!object || !object.properties) {
      tooltip.style.display = 'none';
      document.getElementById('deckgl-container').style.cursor = 'grab';
      return;
    }
    document.getElementById('deckgl-container').style.cursor = 'pointer';
    const p    = object.properties;
    const name = lang() === 'ar' ? p.name_ar : p.name_en;
    const rl   = riskLevel(p.risk_score);
    const indVal = state.indicator && p.gov_data?.main_indicators
      ? p.gov_data.main_indicators[state.indicator]
      : null;
    const indMeta = state.indicators.find(i => i.key === state.indicator);
    const indName  = indMeta ? (lang() === 'ar' ? indMeta.name_ar : indMeta.name_en) : t('Composite Risk', 'الخطر المركّب');

    tooltip.innerHTML = `
      <div class="tt-name">${esc(name)}</div>
      <div class="tt-badge" style="color:${rl.color}">
        <i class="bi ${rl.icon}"></i> ${lang() === 'ar' ? rl.ar : rl.en}
      </div>
      <div class="tt-divider"></div>
      <div class="tt-row">
        <span>${esc(indName)}</span>
        <strong>${indVal != null ? Number(indVal).toFixed(1) : Number(p.risk_score).toFixed(1)}</strong>
      </div>
      <div class="tt-row">
        <span>${t('Risk Score', 'مؤشر الخطر')}</span>
        <strong style="color:${rl.color}">${Number(p.risk_score || 0).toFixed(0)}</strong>
      </div>
      <div class="tt-hint">${t('Click for full report', 'انقر لعرض التقرير الكامل')}</div>`;

    const pad = 14;
    let lx = x + pad, ly = y + pad;
    tooltip.style.display = 'block';
    const rect = tooltip.getBoundingClientRect();
    if (lx + rect.width  > window.innerWidth  - 8) lx = x - rect.width  - pad;
    if (ly + rect.height > window.innerHeight - 8) ly = y - rect.height - pad;
    tooltip.style.left = `${lx}px`;
    tooltip.style.top  = `${ly}px`;
  }

  function handleClick({ object }) {
    if (!object || !object.properties) return;
    const slug = object.properties.slug;
    if (!slug) return;
    selectGovernorate(slug);
  }

  /* =========================================================================
     GOVERNORATE SELECTION & FLY-TO
     ========================================================================= */
  function selectGovernorate(slug) {
    state.selectedSlug = slug;
    updateLayers();
    loadGovernorateDetail(slug);
    flyToGovernorate(slug);
    // sync gov filter dropdown
    const sel = document.getElementById('govSelect');
    if (sel) sel.value = slug;
    // sync rankings table
    document.querySelectorAll('#rankingsTable tbody tr').forEach(tr => {
      tr.classList.toggle('selected', tr.dataset.slug === slug);
    });
  }

  function flyToGovernorate(slug) {
    const gov = state.governorates.find(g => g.slug === slug);
    if (!gov || !deckgl) return;
    const targetZoom = Math.max(viewState.zoom, 7.8);
    deckgl.setProps({
      initialViewState: {
        longitude:          gov.center[0],
        latitude:           gov.center[1],
        zoom:               targetZoom,
        pitch:              50,
        bearing:            viewState.bearing || -8,
        transitionDuration: 800,
        transitionEasing:   easeT => easeT < 0.5 ? 4*easeT*easeT*easeT : 1 - Math.pow(-2*easeT+2,3)/2,
      },
    });
  }

  /* =========================================================================
     DETAIL PANEL
     ========================================================================= */
  async function loadGovernorateDetail(slug) {
    const panel = document.getElementById('intelPanel');
    if (!panel) return;
    const gov = state.governorates.find(g => g.slug === slug) || {};
    const name = lang() === 'ar' ? (gov.name_ar || slug) : (gov.name_en || slug);

    panel.innerHTML = `
      <div class="intel-loading">
        <div class="intel-loading-spinner"></div>
        <div class="intel-loading-name">${esc(name)}</div>
      </div>`;

    try {
      const [detail, correlations] = await Promise.all([
        get(`/governorate/${encodeURIComponent(slug)}`),
        get('/correlations').catch(() => ({ matrix: [] })),
      ]);
      renderDetailPanel(panel, detail, correlations);
      loadSparkline(slug, detail.slug || slug);
    } catch (err) {
      console.error('[GeoIntel] detail load failed', err);
      panel.innerHTML = `
        <div class="intel-error">
          <i class="bi bi-exclamation-octagon"></i>
          <p>${t('Failed to load governorate data.', 'تعذّر تحميل بيانات المحافظة.')}</p>
          <button class="intel-retry-btn" onclick="window.JordanGeoIntelligence.retryDetail('${esc(slug)}')">
            ${t('Retry', 'إعادة')}
          </button>
        </div>`;
    }
  }

  function renderDetailPanel(panel, detail, correlations) {
    const l = lang();
    const name   = l === 'ar' ? detail.name_ar : detail.name_en;
    const rl     = riskLevel(detail.risk_score);
    const action = detail.recommended_action || {};
    const actionText = l === 'ar' ? (action.ar || '') : (action.en || '');
    const indicators = state.indicators || [];

    // Indicator bars
    const indBars = indicators.map(ind => {
      const val = (detail.main_indicators || {})[ind.key];
      const trend = (detail.trends || {})[ind.key] || {};
      const tIcon = trend.direction === 'up' ? '↑' : trend.direction === 'down' ? '↓' : '→';
      const tColor = trend.direction === 'up' ? '#4caf50' : trend.direction === 'down' ? '#ef5350' : '#94a3b8';
      const barColor = riskHex(val);
      const indName  = l === 'ar' ? ind.name_ar : ind.name_en;
      const valStr   = val == null ? t('N/A', 'غير متاح') : Number(val).toFixed(1);
      return `
        <div class="ind-bar-row">
          <div class="ind-bar-label" title="${esc(indName)}">${esc(indName)}</div>
          <div class="ind-bar-track">
            <div class="ind-bar-fill" style="width:${val ?? 0}%;background:${barColor}"></div>
          </div>
          <div class="ind-bar-val">${esc(valStr)}</div>
          <span class="ind-trend" style="color:${tColor}">${tIcon}</span>
        </div>`;
    }).join('');

    // Alerts
    const alerts = detail.alerts || [];
    const alertsHtml = alerts.length
      ? alerts.slice(0, 5).map(a => {
          const dotColor = a.severity === 'critical' ? '#ef5350' : a.severity === 'high' ? '#ff5722' : a.severity === 'medium' ? '#ff9800' : '#4caf50';
          return `<div class="intel-alert-row">
            <span class="intel-alert-dot" style="background:${dotColor}"></span>
            <span class="intel-alert-msg">${esc(a.message || a.metric || '')}</span>
          </div>`;
        }).join('')
      : `<div class="intel-no-alerts">${t('No active alerts', 'لا تنبيهات نشطة')}</div>`;

    // Correlation pills (top 4)
    const corrRows = (correlations.matrix || [])
      .filter(r => r.row === detail.slug || r.column === detail.slug)
      .slice(0, 4);
    const corrHtml = corrRows.length
      ? corrRows.map(r => {
          const partner = r.row === detail.slug ? r.column : r.row;
          const pm = indicators.find(i => i.key === partner) || {};
          const pName = l === 'ar' ? (pm.name_ar || partner) : (pm.name_en || partner);
          const v = r.value != null ? Number(r.value).toFixed(2) : '--';
          const cc = r.value > 0 ? '#4caf50' : '#ef5350';
          return `<span class="corr-pill" style="border-color:${cc};color:${cc}" title="${esc(pName)}">${esc(pName.slice(0,12))} <strong dir="ltr">${v}</strong></span>`;
        }).join(' ')
      : `<span class="intel-muted">${t('Insufficient data', 'بيانات غير كافية')}</span>`;

    panel.innerHTML = `
      <div class="intel-gov-header">
          <div class="intel-gov-namerow">
          <h2 class="intel-gov-name">${esc(name)}</h2>
          ${lang() !== 'ar' ? `<span class="intel-gov-code">${esc(detail.admin_code || '')}</span>` : ''}
        </div>
        <div class="intel-gov-name-sub">${l === 'ar' ? esc(detail.name_en || '') : esc(detail.name_ar || '')}</div>
        <div class="intel-risk-row">
          <div class="intel-risk-score" style="color:${rl.color}">${Number(detail.risk_score || 0).toFixed(0)}</div>
          <div class="intel-risk-meta">
            <span class="intel-risk-badge risk-${rl.key}">
              <i class="bi ${rl.icon}"></i> ${l === 'ar' ? rl.ar : rl.en}
            </span>
            <div class="intel-risk-label-sub">${t('Risk Score / 100', 'مؤشر الخطر / 100')}</div>
          </div>
        </div>
        ${actionText ? `
        <div class="intel-action-box">
          <i class="bi bi-lightning-charge"></i>
          <span>${esc(actionText)}</span>
        </div>` : ''}
      </div>

      <div class="intel-section">
        <div class="intel-section-title">${t('Risk Trend — 30 Days', 'اتجاه الخطر — 30 يوماً')}</div>
        <div id="sparklineBox-${esc(detail.slug)}" class="sparkline-box">
          <span class="intel-muted">${t('Loading…', 'جاري التحميل…')}</span>
        </div>
      </div>

      <div class="intel-section">
        <div class="intel-section-title">${t('Key Indicators', 'المؤشرات الرئيسية')}</div>
        ${indBars}
      </div>

      <div class="intel-section">
        <div class="intel-section-title">${t('Active Alerts', 'التنبيهات النشطة')}</div>
        ${alertsHtml}
      </div>

      <div class="intel-section">
        <div class="intel-section-title">${t('Indicator Correlations', 'ارتباطات المؤشرات')}</div>
        <div class="corr-pills">${corrHtml}</div>
      </div>

      <div class="intel-actions">
        <button class="intel-btn-primary" onclick="window.JordanGeoIntelligence.exportReport('${esc(detail.slug)}')">
          <i class="bi bi-download"></i> ${t('Export Report', 'تصدير التقرير')}
        </button>
        <a href="/admin/analytics?governorate=${esc(detail.slug)}" class="intel-btn-secondary">
          <i class="bi bi-bar-chart-line"></i> ${t('Full Analytics', 'التحليلات الكاملة')}
        </a>
      </div>

      <div class="intel-footer">
        <span>${t('Last update:', 'آخر تحديث:')} ${fmtDate(detail.last_update)}</span>
      </div>`;
  }

  /* =========================================================================
     SPARKLINE
     ========================================================================= */
  async function loadSparkline(slug, detailSlug) {
    const boxId = `sparklineBox-${detailSlug}`;
    const box   = document.getElementById(boxId);
    if (!box) return;
    try {
      const data    = await get(`/governorate/${encodeURIComponent(slug)}/history?days=30`);
      const history = data.history || [];
      if (history.length < 2) {
        box.innerHTML = `<span class="intel-muted">${t('Insufficient history', 'تاريخ غير كافٍ')}</span>`;
        return;
      }
      const w = box.clientWidth || 260;
      const h = 52;
      const pL = 4, pR = 4, pT = 6, pB = 16;
      const scores = history.map(p => p.risk_score);
      const minS = Math.min(...scores);
      const maxS = Math.max(...scores);
      const rangeS = Math.max(maxS - minS, 1);
      const pts = history.map((p, i) => {
        const xFrac = history.length > 1 ? i / (history.length - 1) : 0.5;
        const x = pL + (w - pL - pR) * xFrac;
        const y = pT + (h - pT - pB) * (1 - (p.risk_score - minS) / rangeS);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      });
      const last  = history[history.length - 1];
      const lx = pts[pts.length - 1].split(',')[0];
      const ly = pts[pts.length - 1].split(',')[1];
      const lineColor = riskHex(last.risk_score);
      const area = pts.map((pt, i) => {
        const [x, y] = pt.split(',');
        return i === 0 ? `M${x},${y}` : `L${x},${y}`;
      }).join(' ') + ` L${(w - pR).toFixed(1)},${h - pB} L${pL},${h - pB} Z`;

      box.innerHTML = `
        <svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" style="display:block;overflow:visible">
          <defs>
            <linearGradient id="sparkGrad-${esc(detailSlug)}" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="${lineColor}" stop-opacity="0.3"/>
              <stop offset="100%" stop-color="${lineColor}" stop-opacity="0"/>
            </linearGradient>
          </defs>
          <path d="${area}" fill="url(#sparkGrad-${esc(detailSlug)})" />
          <polyline points="${pts.join(' ')}" fill="none" stroke="${lineColor}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>
          <circle cx="${lx}" cy="${ly}" r="3" fill="${lineColor}"/>
        </svg>
        <div class="sparkline-meta">
          <span>${esc(history[0].date)}</span>
          <span><strong style="color:${lineColor}">${last.risk_score.toFixed(1)}</strong> · ${esc(last.date)}</span>
        </div>`;
    } catch (_) {
      box.innerHTML = `<span class="intel-muted">${t('Trend unavailable', 'الاتجاه غير متاح')}</span>`;
    }
  }

  /* =========================================================================
     KPI STRIP
     ========================================================================= */
function renderKPIStrip(mapData) {
     const strip = document.getElementById('kpiStrip');
     if (!strip || !mapData) return;
     const govs = mapData.governorates || [];
     const totalInstitutions = govs.reduce((s, g) => s + (g.sub_indicators?.total_nurseries || g.kindergarten_count || 0), 0);
     const criticalCount = govs.filter(g => (g.risk_score || 0) >= 75).length;
     const avgRisk = govs.length ? (govs.reduce((s, g) => s + (g.risk_score || 0), 0) / govs.length) : 0;
     const avgColor = riskHex(avgRisk);
     const instText = totalInstitutions === 0
       ? (lang() === 'ar' ? 'لا توجد مؤسسات مسجلة' : 'No institutions registered')
       : fmtNum(totalInstitutions);

     strip.innerHTML = `
       <div class="kpi-card" style="--kpi-color:#1e88e5">
         <div class="kpi-label">${t('Governorates', 'المحافظات')}</div>
         <div class="kpi-value">12</div>
         <div class="kpi-sub">${t('Fully covered', 'مغطاة بالكامل')}</div>
       </div>
       <div class="kpi-card" style="--kpi-color:${avgColor}">
         <div class="kpi-label">${t('Avg. Risk Score', 'متوسط مؤشر الخطر')}</div>
         <div class="kpi-value" style="color:${avgColor}">${avgRisk.toFixed(0)}</div>
         <div class="kpi-sub" style="color:${avgColor}">${avgRisk < 25 ? t('Safe — No action needed', 'آمن — لا إجراء مطلوب') : avgRisk < 50 ? t('Moderate — Periodic review needed', 'متوسط — يتطلب متابعة دورية') : avgRisk < 75 ? t('Warning — Action advised', 'تحذير — يُنصح بالتدخل') : t('Critical — Immediate action', 'حرج — تدخل فوري')}</div>
       </div>
       <div class="kpi-card" style="--kpi-color:#ef5350">
         <div class="kpi-label">${t('Critical Zones', 'المناطق الحرجة')}</div>
         <div class="kpi-value" style="color:${criticalCount > 0 ? '#ef5350' : '#4caf50'}">${criticalCount}</div>
         <div class="kpi-sub" style="color:${criticalCount > 0 ? '#ef5350' : '#4caf50'}">${criticalCount === 0 ? t('No critical zones currently', 'لا مناطق حرجة حالياً') : t('Review recommended', 'يُنصح بالمراجعة')}</div>
       </div>
       <div class="kpi-card" style="--kpi-color:#1e88e5">
         <div class="kpi-label">${t('Institutions', 'المؤسسات')}</div>
         <div class="kpi-value">${instText}</div>
         <div class="kpi-sub">${t('Registered', 'مسجلة')}</div>
       </div>`;
   }

  /* =========================================================================
     RANKINGS TABLE
     ========================================================================= */
  let rankSortKey = 'risk_score';
  let rankSortDir = -1;

  function renderRankings(governorates) {
    const tbody = document.querySelector('#rankingsTable tbody');
    if (!tbody) return;
    const sorted = [...governorates].sort((a, b) => rankSortDir * ((b[rankSortKey] || 0) - (a[rankSortKey] || 0)));

    tbody.innerHTML = sorted.map((g, i) => {
      const rl = riskLevel(g.risk_score);
      const name = lang() === 'ar' ? g.name_ar : g.name_en;
      const topClass = i === 0 ? 'top-1' : i === 1 ? 'top-2' : i === 2 ? 'top-3' : '';
      const barColor = riskHex(g.risk_score);
      return `
        <tr data-slug="${esc(g.slug)}" onclick="window.JordanGeoIntelligence.selectGovernorate('${esc(g.slug)}')">
          <td><div class="rank-num ${topClass}">${i + 1}</div></td>
          <td>
            <div class="rank-name">${esc(name)}</div>
            ${lang() !== 'ar' ? `<div class="rank-code">${esc(g.code || '')}</div>` : ''}
          </td>
          <td>
            <div style="display:flex;align-items:center;gap:8px">
              <div class="mini-bar-track">
                <div class="mini-bar-fill" style="width:${g.risk_score || 0}%;background:${barColor}"></div>
              </div>
              <span style="color:${barColor};font-weight:700;font-size:.8rem;">${Number(g.risk_score || 0).toFixed(0)}</span>
            </div>
          </td>
          <td>
            <span class="rank-badge risk-${rl.key}">
              <i class="bi ${rl.icon}"></i> ${lang() === 'ar' ? rl.ar : rl.en}
            </span>
          </td>
          <td class="rank-actions">
            <button class="rank-drill" onclick="event.stopPropagation();window.JordanGeoIntelligence.selectGovernorate('${esc(g.slug)}')">
              <i class="bi bi-crosshair2"></i>
            </button>
          </td>
        </tr>`;
    }).join('');
  }

  function setupRankingSort() {
    document.querySelectorAll('#rankingsTable th[data-sort]').forEach(th => {
      th.addEventListener('click', () => {
        const key = th.dataset.sort;
        if (rankSortKey === key) { rankSortDir *= -1; }
        else { rankSortKey = key; rankSortDir = -1; }
        renderRankings(state.governorates);
      });
    });
  }

  /* =========================================================================
     INDICATOR SELECT & FILTER SYNC
     ========================================================================= */
  function populateIndicatorSelect() {
    const sel = document.getElementById('indicatorSelect');
    if (!sel) return;
    sel.innerHTML = `<option value="">${t('Overall Risk (Composite)', 'الخطر الإجمالي (مركّب)')}</option>`;
    (state.indicators || []).forEach(ind => {
      const opt = document.createElement('option');
      opt.value = ind.key;
      opt.textContent = lang() === 'ar' ? ind.name_ar : ind.name_en;
      sel.appendChild(opt);
    });
  }

  function populateGovSelect() {
    const sel = document.getElementById('govSelect');
    if (!sel) return;
    while (sel.options.length > 1) sel.remove(1);
    const sorted = [...state.governorates].sort((a, b) => (a.display_order || 0) - (b.display_order || 0));
    sorted.forEach(g => {
      const opt = document.createElement('option');
      opt.value = g.slug;
      opt.textContent = lang() === 'ar' ? g.name_ar : g.name_en;
      sel.appendChild(opt);
    });
  }

  /* =========================================================================
     ZOOM & VIEW CONTROLS
     ========================================================================= */
  function zoomIn() {
    setZoom(Math.min((viewState.zoom || 6.2) + 0.8, JORDAN.maxZoom));
  }
  function zoomOut() {
    setZoom(Math.max((viewState.zoom || 6.2) - 0.8, JORDAN.minZoom));
  }
  function setZoom(z) {
    if (!deckgl) return;
    deckgl.setProps({
      initialViewState: { ...viewState, zoom: z, transitionDuration: 300 },
    });
  }
  function resetView() {
    if (!deckgl) return;
    state.selectedSlug = null;
    updateLayers();
    deckgl.setProps({ initialViewState: { ...INITIAL_VIEW, transitionDuration: 700 } });
    const govSel = document.getElementById('govSelect');
    if (govSel) govSel.value = '';
    if (state.governorates.length) {
      renderNationalInsights(state.governorates);
    } else {
      resetDetailPanel();
    }
    document.querySelectorAll('#rankingsTable tbody tr').forEach(tr => tr.classList.remove('selected'));
  }
  function tiltMore() {
    if (!deckgl) return;
    const newPitch = Math.min((viewState.pitch || 48) + 10, 75);
    deckgl.setProps({ initialViewState: { ...viewState, pitch: newPitch, transitionDuration: 300 } });
  }
  function tiltLess() {
    if (!deckgl) return;
    const newPitch = Math.max((viewState.pitch || 48) - 10, 0);
    deckgl.setProps({ initialViewState: { ...viewState, pitch: newPitch, transitionDuration: 300 } });
  }
  function set3D(enable) {
    is3D = enable;
    document.getElementById('btn3D')?.classList.toggle('active', enable);
    document.getElementById('btn2D')?.classList.toggle('active', !enable);
    if (deckgl) {
      deckgl.setProps({
        initialViewState: {
          ...viewState,
          pitch:  enable ? 48 : 0,
          bearing: enable ? -8 : 0,
          transitionDuration: 600,
        },
      });
    }
    updateLayers();
  }

  function updateCompass(bearing) {
    const needle = document.getElementById('compassNeedle');
    if (needle) needle.style.transform = `rotate(${bearing}deg)`;
  }

  /* =========================================================================
     UI HELPERS
     ========================================================================= */
function showLoading(show) {
     const overlay = document.getElementById('mapLoadingOverlay');
     if (overlay) overlay.style.display = show ? 'flex' : 'none';
     const err = document.getElementById('mapErrorState');
     if (err) err.style.display = 'none';
     const retryBtn = document.getElementById('retryMapBtn');
     const retrySpinner = retryBtn?.querySelector('.retry-spinner');
     if (retryBtn && retrySpinner) {
       retrySpinner.style.display = show ? 'inline-block' : 'none';
       retryBtn.disabled = show;
     }
   }
function showMapError(show, errorMsg) {
     const err = document.getElementById('mapErrorState');
     if (err) {
       err.style.display = show ? 'flex' : 'none';
       if (show && errorMsg) {
         const details = err.querySelector('.map-error-details');
         if (details) details.textContent = errorMsg;
       }
     }
     const mapStatus = document.getElementById('mapStatus');
     if (mapStatus) {
       mapStatus.className = show ? 'status-chip error' : 'status-chip live';
       mapStatus.innerHTML = show
         ? `<i class="bi bi-exclamation-triangle" aria-hidden="true"></i> ${t('Map Unavailable', 'الخريطة غير متاحة')}`
         : `<i class="bi bi-map" aria-hidden="true"></i> ${t('Map Ready', 'الخريطة جاهزة')}`;
     }
   }
  function resetDetailPanel() {
    const panel = document.getElementById('intelPanel');
    if (!panel) return;
    panel.innerHTML = `
      <div class="intel-placeholder">
        <div class="intel-placeholder-icon">
          <svg viewBox="0 0 100 130" fill="none" xmlns="http://www.w3.org/2000/svg" width="72" opacity="0.25">
            <path d="M50 5 L95 95 L5 95 Z" fill="none" stroke="rgba(255,255,255,0.4)" stroke-width="3"/>
            <path d="M10 15 L90 15 L90 125 L10 125 Z" fill="none" stroke="rgba(30,136,229,0.4)" stroke-width="2"/>
            <line x1="20" y1="35" x2="80" y2="35" stroke="rgba(255,255,255,0.2)" stroke-width="2"/>
            <line x1="20" y1="50" x2="70" y2="50" stroke="rgba(255,255,255,0.15)" stroke-width="2"/>
            <line x1="20" y1="65" x2="75" y2="65" stroke="rgba(255,255,255,0.15)" stroke-width="2"/>
            <line x1="20" y1="80" x2="60" y2="80" stroke="rgba(255,255,255,0.1)" stroke-width="2"/>
          </svg>
        </div>
        <div class="intel-placeholder-title">${t('Select a Governorate', 'اختر محافظة')}</div>
        <div class="intel-placeholder-sub">${t('Click any governorate on the map or the table below to load its full report.', 'انقر على أي محافظة في الخريطة أو في الجدول أدناه لعرض التقرير الكامل.')}</div>
      </div>`;
  }

  function renderLastUpdate(daily) {
    const el = document.getElementById('lastUpdateStatus');
    if (el && daily?.last_update) {
      el.textContent = `${t('Last sync:', 'آخر مزامنة:')} ${fmtDate(daily.last_update)}`;
    }
    const alertEl = document.getElementById('alertCountStatus');
    if (alertEl) {
      const critCount = (state.governorates || []).filter(g => (g.risk_score || 0) >= 75).length;
      alertEl.textContent = `${critCount} ${t('Critical', 'حرج')}`;
      alertEl.className = `status-chip ${critCount > 0 ? 'alert' : 'info'}`;
    }
  }

  function fmtDate(iso) {
    if (!iso) return '--';
    try {
      return new Date(iso).toLocaleString(lang() === 'en' ? 'en-US' : 'ar-JO', { dateStyle: 'medium', timeStyle: 'short' });
    } catch (_) { return iso; }
  }
function fmtNum(n) {
     if (n === null || n === undefined) return t('No data', 'لا بيانات');
     if (n === 0) return '0';
     return Number(n).toLocaleString(lang() === 'en' ? 'en-US' : 'ar-JO');
   }
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
  }

  /* =========================================================================
     EXPORT
     ========================================================================= */
  function exportReport(slug) {
    const gov = state.governorates.find(g => g.slug === slug);
    if (!gov) return;
    const name = lang() === 'ar' ? gov.name_ar : gov.name_en;
    const rl = riskLevel(gov.risk_score);
    const csv = [
      ['Governorate', 'Risk Score', 'Risk Level', 'Code'],
      [name, gov.risk_score?.toFixed(1), rl.en, gov.code],
    ].map(r => r.join(',')).join('\n');
    const a = document.createElement('a');
    a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
    a.download = `jordan-risk-analysis-${slug}-${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
  }

  /* =========================================================================
     INITIALIZATION
     ========================================================================= */
  /* =========================================================================
     NATIONAL INSIGHTS PANEL
     Shown in the intel panel when no governorate is selected.
     ========================================================================= */
function renderNationalInsights(governorates) {
     const panel = document.getElementById('intelPanel');
     if (!panel) return;
     if (!governorates || !governorates.length) return;
     const critGovs = governorates.filter(g => (g.risk_score || 0) >= 75);
     const highGovs = governorates.filter(g => (g.risk_score || 0) >= 50 && (g.risk_score || 0) < 75);
     const avgRisk  = governorates.reduce((s, g) => s + (g.risk_score || 0), 0) / governorates.length;
     const l = lang();
     const riskLevelText = avgRisk < 25
       ? t('Low — System is operating within safe thresholds.', 'منخفض — النظام يعمل ضمن الحدود الآمنة.')
       : avgRisk < 50
         ? t('Moderate — Some areas need periodic review.', 'متوسط — بعض المناطق تحتاج متابعة دورية.')
         : avgRisk < 75
           ? t('High — Several governorates require urgent review.', 'مرتفع — عدة محافظات تحتاج مراجعة عاجلة.')
           : t('Critical — Immediate intervention required.', 'حرج — يلزم التدخل الفوري.');

     const critList = critGovs.length
       ? critGovs.map(g => esc(l === 'ar' ? (g.name_ar || g.name_en || g.slug) : (g.name_en || g.slug))).join('، ')
       : null;

    panel.innerHTML = `
      <div class="intel-gov-header" style="background:linear-gradient(140deg,rgba(30,136,229,0.08) 0%,transparent 70%)">
        <h2 class="intel-gov-name" style="font-size:1rem">${t('National Risk Overview', 'نظرة عامة على المخاطر الوطنية')}</h2>
        <div class="intel-gov-name-sub">${t('Hashemite Kingdom of Jordan — 12 Governorates', 'المملكة الأردنية الهاشمية — 12 محافظة')}</div>
        <div class="intel-risk-row">
          <div class="intel-risk-score" style="color:${riskHex(avgRisk)};font-size:2.2rem">${avgRisk.toFixed(0)}</div>
          <div class="intel-risk-meta">
            <span class="intel-risk-badge risk-${riskLevel(avgRisk).key}">
              <i class="bi ${riskLevel(avgRisk).icon}"></i>
              ${l === 'ar' ? riskLevel(avgRisk).ar : riskLevel(avgRisk).en}
            </span>
            <div class="intel-risk-label-sub">${t('National average / 100', 'المتوسط الوطني / 100')}</div>
          </div>
        </div>
        <div class="intel-action-box">
          <i class="bi bi-lightbulb-fill"></i>
          <span>${riskLevelText}</span>
        </div>
      </div>
      ${critGovs.length ? `
      <div class="intel-section">
        <div class="intel-section-title">${t('Critical Zones Requiring Attention', 'مناطق حرجة تحتاج تدخلاً')}</div>
        ${critGovs.slice(0, 5).map(g => {
          const gname = esc(l === 'ar' ? (g.name_ar || g.name_en || g.slug) : (g.name_en || g.slug));
          return `<div class="intel-alert-row">
            <span class="intel-alert-dot" style="background:#ef5350"></span>
            <span>${gname} — ${t('Risk', 'خطر')} <strong style="color:#ef5350">${Number(g.risk_score||0).toFixed(0)}</strong></span>
          </div>`;
        }).join('')}
      </div>` : ''}
${highGovs.length ? `
       <div class="intel-section">
         <div class="intel-section-title">${t('High-Risk Zones', 'مناطق عالية الخطر')} <span class="intel-count">(${highGovs.length})</span></div>
         ${highGovs.map(g => {
           const gname = esc(l === 'ar' ? (g.name_ar || g.name_en || g.slug) : (g.name_en || g.slug));
           return `<div class="intel-alert-row">
             <span class="intel-alert-dot" style="background:#ff5722"></span>
             <span>${gname} — ${t('Risk', 'خطر')} <strong style="color:#ff5722">${Number(g.risk_score||0).toFixed(0)}</strong></span>
           </div>`;
         }).join('')}
       </div>` : ''}
<div class="intel-actions">
         <a href="/admin/analytics" class="intel-btn-secondary">
           <i class="bi bi-bar-chart-line"></i> ${t('View Full Analytics', 'عرض التحليلات الكاملة')}
         </a>
       </div>
      <div class="intel-footer">
        <span>${t('Click a governorate to drill down.', 'انقر على محافظة للاطلاع على تفاصيلها.')}</span>
      </div>`;
  }

  async function init() {
    if (state.initialized) return;
    state.initialized = true;
    showLoading(true);

    try {
      const [indRes, mapRes, gjRes, dailyRes] = await Promise.all([
        get('/indicators').catch(() => ({ indicators: [] })),
        get('/data').catch(() => ({ governorates: [], indicators: [] })),
        get('/geojson').catch(() => ({ type: 'FeatureCollection', features: [] })),
        get('/daily-update').catch(() => ({})),
      ]);

      state.indicators   = indRes.indicators || [];
      state.governorates = mapRes.governorates || [];
      state.mapData      = mapRes;
      state.geojson      = gjRes;

      populateIndicatorSelect();
      populateGovSelect();
      initDeckGL();
      updateLayers();
      renderKPIStrip(mapRes);
      renderRankings(state.governorates);
      renderLastUpdate(dailyRes);
      setupRankingSort();
      syncFilterState();
      if (state.governorates.length && !state.selectedSlug) {
        renderNationalInsights(state.governorates);
      }
      showLoading(false);

    } catch (err) {
      console.error('[GeoIntel] initialization failed', err);
      showLoading(false);
      showMapError(true);
    }
  }

function bindControls() {
     document.getElementById('zoomInBtn')?.addEventListener('click', zoomIn);
     document.getElementById('zoomOutBtn')?.addEventListener('click', zoomOut);
     document.getElementById('resetViewBtn')?.addEventListener('click', resetView);
     document.getElementById('tiltMoreBtn')?.addEventListener('click', tiltMore);
     document.getElementById('tiltLessBtn')?.addEventListener('click', tiltLess);
     document.getElementById('btn3D')?.addEventListener('click', () => set3D(true));
     document.getElementById('btn2D')?.addEventListener('click', () => set3D(false));
     document.getElementById('compassReset')?.addEventListener('click', () => {
       if (deckgl) deckgl.setProps({ initialViewState: { ...viewState, bearing: -8, transitionDuration: 500 } });
     });
     document.getElementById('retryMapBtn')?.addEventListener('click', () => {
       showLoading(true);
       if (deckgl) { deckgl.finalize(); deckgl = null; }
       state.initialized = false;
       state.geojson = null;
       state.mapData = null;
       init();
     });

    document.getElementById('indicatorSelect')?.addEventListener('change', e => {
      state.indicator = e.target.value;
      updateLayers();
      if (window.AnalyticsFilterState) window.AnalyticsFilterState.setState({ indicator: state.indicator }, 'geo-intel');
    });

    document.getElementById('govSelect')?.addEventListener('change', e => {
      const slug = e.target.value;
      if (slug) { selectGovernorate(slug); }
      else { resetView(); }
    });

    document.getElementById('refreshBtn')?.addEventListener('click', () => {
      if (deckgl) { deckgl.finalize(); deckgl = null; }
      state.initialized = false;
      state.geojson = null;
      state.mapData = null;
      init();
    });
  }

  function syncFilterState() {
    if (!window.AnalyticsFilterState) return;
    const fs = window.AnalyticsFilterState.getState();
    if (fs.indicator && fs.indicator !== 'all') {
      state.indicator = fs.indicator;
      const sel = document.getElementById('indicatorSelect');
      if (sel) sel.value = fs.indicator;
    }
    if (fs.governorate && fs.governorate !== 'all') {
      selectGovernorate(fs.governorate);
    }
    window.AnalyticsFilterState.subscribe(fs2 => {
      if (fs2.source === 'geo-intel') return;
      if (fs2.indicator !== undefined && fs2.indicator !== state.indicator) {
        state.indicator = fs2.indicator === 'all' ? '' : fs2.indicator;
        const sel = document.getElementById('indicatorSelect');
        if (sel) sel.value = state.indicator;
        updateLayers();
      }
      if (fs2.governorate !== undefined && fs2.governorate !== state.selectedSlug) {
        if (!fs2.governorate || fs2.governorate === 'all') resetView();
        else selectGovernorate(fs2.governorate);
      }
    });
  }

  /* =========================================================================
     PUBLIC API
     ========================================================================= */
  window.JordanGeoIntelligence = {
    init,
    selectGovernorate,
    resetView,
    zoomIn,
    zoomOut,
    set3D,
    exportReport,
    retryDetail: slug => loadGovernorateDetail(slug),
  };

  document.addEventListener('DOMContentLoaded', () => {
    bindControls();
    if (typeof deck !== 'undefined') {
      init();
    } else {
      // Defer until deck.gl CDN loads
      const script = document.querySelector('script[src*="deck.gl"]');
      if (script) {
        script.addEventListener('load', () => { init(); });
      } else {
        console.warn('[GeoIntel] deck.gl script not found in DOM');
        showMapError(true);
      }
    }
  });
})();
