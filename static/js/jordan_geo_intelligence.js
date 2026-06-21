/**
 * Jordan Geographic Indicator Heatmaps
 * Six SVG-based choropleth maps — no deck.gl / WebGL dependency.
 * GeoJSON loaded once, shared across all six indicator cards.
 */
(function () {
  "use strict";

  /* ── API & SVG CONSTANTS ─────────────────────────────────────── */
  const API = "/api/admin/heat-map";
  const SVG_W = 260, SVG_H = 250, SVG_PAD = 6;

  /** Equirectangular bounds for Jordan */
  const JORDAN = {
    minLon: 34.90, maxLon: 39.40,
    minLat: 29.10, maxLat: 33.45,
  };

  const CODE_TO_SLUG = {
    "JO-AM": "amman",   "JO-IR": "irbid",   "JO-ZA": "zarqa",
    "JO-MA": "mafraq",  "JO-JA": "jerash",  "JO-AJ": "ajloun",
    "JO-BA": "balqa",   "JO-MD": "madaba",  "JO-KA": "karak",
    "JO-TA": "tafileh", "JO-MN": "maan",    "JO-AQ": "aqaba",
  };

  /* ── UI LANGUAGE ─────────────────────────────────────────────── */
  const _gccEl = document.querySelector(".geo-cc");
  const UI_LANG = _gccEl ? (_gccEl.getAttribute("lang") || "ar") : "ar";
  const IS_AR = UI_LANG !== "en";

  /* ── I18N HELPER ─────────────────────────────────────────────── */
  function t(key, fallback) {
    try {
      return (window.AdminI18n && typeof window.AdminI18n.translate === "function")
        ? window.AdminI18n.translate(key, fallback)
        : (fallback || key);
    } catch (_) {
      return fallback || key;
    }
  }

  /* ── RISK COLOR SYSTEM (memoized) ────────────────────────────── */
  const _colorCache = Object.create(null);

  function riskColor(v) {
    const s = Math.max(0, Math.min(100, +v || 0));
    const b = s | 0;
    if (_colorCache[b]) return _colorCache[b];
    const c = s < 25 ? "#22c55e" : s < 50 ? "#f59e0b" : s < 75 ? "#f97316" : "#ef4444";
    return (_colorCache[b] = c);
  }

  function riskLevel(v) {
    const s = +v || 0;
    if (s < 25) return { key: "low",      ar: "منخفض", en: "Low",      color: "#22c55e" };
    if (s < 50) return { key: "medium",   ar: "متوسط", en: "Medium",   color: "#f59e0b" };
    if (s < 75) return { key: "high",     ar: "مرتفع", en: "High",     color: "#f97316" };
    return         { key: "critical", ar: "حرج",   en: "Critical", color: "#ef4444" };
  }

  function riskLevelLabel(rl) {
    return t("heatmap.risk_levels." + rl.key, IS_AR ? rl.ar : rl.en);
  }

  function govName(g, fallback) {
    return (IS_AR ? (g.name_ar || g.name_en) : (g.name_en || g.name_ar)) || (fallback || "");
  }
  function govNameAlt(g) {
    return IS_AR ? (g.name_en || "") : (g.name_ar || "");
  }

  /* ── 6 INDICATOR CONFIGURATIONS ──────────────────────────────── */
  const INDICATORS = [
    {
      key: "overall_risk",
      ar: "مؤشر الخطر العام",    en: "Overall Risk",
      descAr: "يوضح مستوى الخطر الكلي لكل محافظة.",
      descEn: "Shows overall risk level per governorate.",
      getValue: function(g) { return g.risk_score != null ? +g.risk_score : null; },
      toRisk:   function(v) { return v; },
    },
    {
      key: "attendance",
      ar: "مؤشر الحضور",         en: "Attendance",
      descAr: "يوضح مستوى الخطر المرتبط بانخفاض الحضور.",
      descEn: "Shows risk associated with low attendance.",
      getValue: function(g) { return g.main_indicators && g.main_indicators.reports_attendance != null ? +g.main_indicators.reports_attendance : null; },
      toRisk:   function(v) { return 100 - v; },
    },
    {
      key: "incidents",
      ar: "مؤشر الحوادث",        en: "Incidents",
      descAr: "يوضح مستوى الخطر المرتبط بمعدل الحوادث.",
      descEn: "Shows risk associated with incident rate.",
      getValue: function(g) { return g.main_indicators && g.main_indicators.safety_incidents != null ? +g.main_indicators.safety_incidents : null; },
      toRisk:   function(v) { return 100 - v; },
    },
    {
      key: "governance",
      ar: "مؤشر الحوكمة",        en: "Governance",
      descAr: "يوضح مستوى الخطر المرتبط بانخفاض مؤشر الحوكمة.",
      descEn: "Shows risk associated with low governance scores.",
      getValue: function(g) { return g.main_indicators && g.main_indicators.tasks_governance != null ? +g.main_indicators.tasks_governance : null; },
      toRisk:   function(v) { return 100 - v; },
    },
    {
      key: "data_quality",
      ar: "مؤشر جودة البيانات",  en: "Data Quality",
      descAr: "يوضح مستوى الخطر المرتبط بجودة واكتمال البيانات.",
      descEn: "Shows risk associated with data quality.",
      getValue: function(g) { return g.main_indicators && g.main_indicators.children_registration != null ? +g.main_indicators.children_registration : null; },
      toRisk:   function(v) { return 100 - v; },
    },
    {
      key: "occupancy",
      ar: "مؤشر الإشغال",        en: "Occupancy",
      descAr: "يوضح مستوى الخطر المرتبط بالطاقة الاستيعابية ونسبة الإشغال.",
      descEn: "Shows risk associated with capacity and occupancy rate.",
      getValue: function(g) { return g.main_indicators && g.main_indicators.nursery_status != null ? +g.main_indicators.nursery_status : null; },
      toRisk:   function(v) { return 100 - v; },
    },
  ];

  function indLabel(ind) {
    return t("heatmap.indicators." + ind.key, IS_AR ? ind.ar : ind.en);
  }
  function indDesc(ind) {
    return t("heatmap.indicator_descriptions." + ind.key, IS_AR ? ind.descAr : ind.descEn);
  }

  /* ── APPLICATION STATE ───────────────────────────────────────── */
  var state = {
    geojson:           null,
    governorates:      [],
    govLookup:         Object.create(null),
    selectedIndicator: "",
    selectedSlug:      null,
  };

  /* ── SVG PATH CACHE (computed once from GeoJSON) ─────────────── */
  var _svgPathCache = null;

  function project(lon, lat) {
    var x = SVG_PAD + (lon - JORDAN.minLon) / (JORDAN.maxLon - JORDAN.minLon) * (SVG_W - 2 * SVG_PAD);
    var y = (SVG_H - SVG_PAD) - (lat - JORDAN.minLat) / (JORDAN.maxLat - JORDAN.minLat) * (SVG_H - 2 * SVG_PAD);
    return [+(x.toFixed(1)), +(y.toFixed(1))];
  }

  function ringToPathD(ring) {
    return ring.map(function(c, i) {
      var pt = project(c[0], c[1]);
      return (i === 0 ? "M" : "L") + pt[0] + "," + pt[1];
    }).join("") + "Z";
  }

  function featureToPathD(feature) {
    var g = feature && feature.geometry;
    if (!g) return "";
    if (g.type === "Polygon")      return ringToPathD(g.coordinates[0]);
    if (g.type === "MultiPolygon") return g.coordinates.map(function(p) { return ringToPathD(p[0]); }).join(" ");
    return "";
  }

  function buildSVGPathCache(geojson, govLookup) {
    if (_svgPathCache) return _svgPathCache;
    if (!geojson || !geojson.features) return (_svgPathCache = []);
    _svgPathCache = [];
    for (var i = 0; i < geojson.features.length; i++) {
      var feat  = geojson.features[i];
      var props = feat.properties || {};
      if (props.level && props.level !== "governorate") continue;
      var code  = props.admin_code || props.id || "";
      var slug  = CODE_TO_SLUG[code] || code.replace("JO-", "").toLowerCase() || "";
      var pathD = featureToPathD(feat);
      if (!pathD) continue;
      var gov   = govLookup[code] || govLookup[slug] || null;
      _svgPathCache.push({
        pathD: pathD, slug: slug, code: code,
        nameAr: (gov && gov.name_ar) || props.name_ar || slug,
        nameEn: (gov && gov.name_en) || props.name    || slug,
        gov:    gov,
      });
    }
    return _svgPathCache;
  }

  /* ── HTML ESCAPE ─────────────────────────────────────────────── */
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  /* ── FETCH HELPER ────────────────────────────────────────────── */
  function apiGet(path) {
    return fetch(API + path, { credentials: "include" }).then(function(r) {
      if (!r.ok) throw new Error("HTTP " + r.status + " " + path);
      return r.json();
    });
  }

  /* ── SVG RENDERING ───────────────────────────────────────────── */
  function renderSVGMap(svgEl, indicator, onHover, onLeave, onClick) {
    while (svgEl.firstChild) svgEl.removeChild(svgEl.firstChild);
    var paths = buildSVGPathCache(state.geojson, state.govLookup);
    var NS    = "http://www.w3.org/2000/svg";

    for (var i = 0; i < paths.length; i++) {
      (function(entry) {
        var rawValue  = entry.gov ? indicator.getValue(entry.gov) : null;
        var riskValue = rawValue != null ? indicator.toRisk(rawValue) : null;
        var fill      = riskValue != null ? riskColor(riskValue) : "#374151";
        var fillOp    = riskValue != null ? "0.82" : "0.28";

        var el = document.createElementNS(NS, "path");
        el.setAttribute("d",            entry.pathD);
        el.setAttribute("fill",         fill);
        el.setAttribute("fill-opacity", fillOp);
        el.setAttribute("stroke",       "rgba(255,255,255,0.22)");
        el.setAttribute("stroke-width", "0.6");
        el.style.cursor = entry.gov ? "pointer" : "default";
        el.dataset.slug = entry.slug;

        if (entry.gov) {
          el.addEventListener("mousemove",  function(e) { onHover(e, entry.gov, indicator, rawValue, riskValue); });
          el.addEventListener("mouseleave", onLeave);
          el.addEventListener("click",      function()  { onClick(entry.slug, entry.gov, indicator); });
        }
        svgEl.appendChild(el);
      })(paths[i]);
    }
  }

  /* ── TOOLTIP ─────────────────────────────────────────────────── */
  var ttEl = document.getElementById("geoTooltip");

  function showTooltip(e, gov, indicator, rawValue, riskValue) {
    if (!ttEl) return;
    var rl      = riskValue != null ? riskLevel(riskValue) : null;
    var rlLabel = rl ? riskLevelLabel(rl) : "";
    var valStr  = rawValue != null ? rawValue.toFixed(1) + "%" : (IS_AR ? "لا توجد بيانات" : "No data");
    var govLabel = govName(gov);
    var indName  = indLabel(indicator);

    ttEl.innerHTML =
      '<div class="tt-name">' + esc(govLabel) + "</div>" +
      (rl ? '<div class="tt-badge" style="color:' + rl.color + '">' + esc(rlLabel) + "</div>" : "") +
      '<div class="tt-divider"></div>' +
      '<div class="tt-row"><span>' + esc(indName) + "</span><strong>" + esc(valStr) + "</strong></div>" +
      (riskValue != null
        ? '<div class="tt-row"><span>' + (IS_AR ? "مؤشر الخطر" : "Risk index") + "</span><strong style=\"color:" + (rl ? rl.color : "#94a3b8") + "\">" + riskValue.toFixed(0) + "/100</strong></div>"
        : "") +
      '<div class="tt-hint">' + (IS_AR ? "انقر للتفاصيل" : "Click for details") + "</div>";

    ttEl.style.display = "block";
    positionTooltip(e);
  }

  function hideTooltip() {
    if (ttEl) ttEl.style.display = "none";
  }

  function positionTooltip(e) {
    if (!ttEl) return;
    var pad = 16;
    var x   = e.clientX + pad;
    var y   = e.clientY + pad;
    ttEl.style.display = "block";
    var r   = ttEl.getBoundingClientRect();
    if (x + r.width  > window.innerWidth  - 8) x = e.clientX - r.width  - pad;
    if (y + r.height > window.innerHeight - 8) y = e.clientY - r.height - pad;
    ttEl.style.left = x + "px";
    ttEl.style.top  = y + "px";
  }

  /* ── MULTI-MAP CARDS ─────────────────────────────────────────── */
  function legendItem(color, label) {
    return '<span class="hm-leg-item"><i class="hm-leg-dot" style="background:' + color + '" aria-hidden="true"></i>' + esc(label) + "</span>";
  }

  function cardHTML(ind) {
    var label    = indLabel(ind);
    var desc     = indDesc(ind);
    var retryLbl = t("heatmap.retry", IS_AR ? "إعادة المحاولة" : "Retry");
    return (
      '<div class="hm-card" id="hm-card-' + ind.key + '" data-indicator="' + ind.key + '">' +
        '<div class="hm-card-header">' +
          '<h3 class="hm-card-title">' + esc(label) + "</h3>" +
          '<p class="hm-card-desc">' + esc(desc) + "</p>" +
        "</div>" +
        '<div class="hm-card-map-wrap">' +
          '<div class="hm-loading" id="hm-loading-' + ind.key + '">' +
            '<div class="hm-spinner" aria-hidden="true"></div>' +
            "<span>" + (IS_AR ? "جاري التحميل…" : "Loading…") + "</span>" +
          "</div>" +
          '<svg id="hm-svg-' + ind.key + '" viewBox="0 0 ' + SVG_W + ' ' + SVG_H + '"' +
              ' style="width:100%;height:auto;display:none"' +
              ' role="img" aria-label="' + esc(label) + '"></svg>' +
          '<div class="hm-error" id="hm-error-' + ind.key + '" style="display:none">' +
            '<i class="bi bi-exclamation-octagon" aria-hidden="true"></i>' +
            "<span>" + (IS_AR ? "تعذر تحميل خريطة " + esc(label) : "Failed to load " + esc(label)) + "</span>" +
            '<button class="hm-error-retry" onclick="window._hmRetry&&window._hmRetry(\'' + ind.key + '\')">' + esc(retryLbl) + "</button>" +
          "</div>" +
        "</div>" +
        '<div class="hm-card-legend">' +
          legendItem("#22c55e", t("heatmap.risk_levels.low",      IS_AR ? "منخفض" : "Low")) +
          legendItem("#f59e0b", t("heatmap.risk_levels.medium",   IS_AR ? "متوسط" : "Medium")) +
          legendItem("#f97316", t("heatmap.risk_levels.high",     IS_AR ? "مرتفع" : "High")) +
          legendItem("#ef4444", t("heatmap.risk_levels.critical", IS_AR ? "حرج"   : "Critical")) +
        "</div>" +
        '<div class="hm-card-stats" id="hm-stats-' + ind.key + '"></div>' +
      "</div>"
    );
  }

  function buildMultiMapGrid() {
    var grid = document.getElementById("multiMapGrid");
    if (grid) grid.innerHTML = INDICATORS.map(cardHTML).join("");
  }

  function renderCard(ind) {
    var svgEl  = document.getElementById("hm-svg-"     + ind.key);
    var loadEl = document.getElementById("hm-loading-" + ind.key);
    var errEl  = document.getElementById("hm-error-"   + ind.key);
    if (!svgEl) return;

    if (!state.geojson || !state.governorates.length) {
      if (loadEl) loadEl.style.display = "none";
      if (errEl)  errEl.style.display  = "flex";
      return;
    }
    try {
      renderSVGMap(svgEl, ind, showTooltip, hideTooltip, handleCardGovClick);
      if (loadEl) loadEl.style.display = "none";
      svgEl.style.display = "block";
      renderCardStats(ind);
    } catch (err) {
      console.error("[Heatmap] renderCard error:", ind.key, err);
      if (loadEl) loadEl.style.display = "none";
      if (errEl)  errEl.style.display  = "flex";
    }
  }

  function renderAllCards() {
    for (var i = 0; i < INDICATORS.length; i++) renderCard(INDICATORS[i]);
  }

  function renderCardStats(ind) {
    var statsEl = document.getElementById("hm-stats-" + ind.key);
    if (!statsEl) return;

    var pairs = [];
    for (var i = 0; i < state.governorates.length; i++) {
      var g = state.governorates[i];
      var r = ind.getValue(g);
      if (r != null) pairs.push({ gov: g, raw: r, risk: ind.toRisk(r) });
    }

    var covered = pairs.length;
    var avgRisk = 0;
    if (covered) {
      for (var j = 0; j < pairs.length; j++) avgRisk += pairs[j].risk;
      avgRisk /= covered;
    }

    var topGov = null;
    if (pairs.length) {
      var sorted = pairs.slice().sort(function(a, b) { return b.risk - a.risk; });
      topGov = sorted[0].gov;
    }

    var rl      = covered ? riskLevel(avgRisk) : null;
    var covLbl  = t("heatmap.covered_governorates",     IS_AR ? "المحافظات المغطاة"  : "Covered Governorates");
    var avgLbl  = t("heatmap.average_indicator",        IS_AR ? "متوسط المؤشر"        : "Average");
    var topLbl  = t("heatmap.highest_risk_governorate", IS_AR ? "أعلى محافظة خطورة"   : "Highest Risk");
    var lvlLbl  = t("heatmap.general_level",            IS_AR ? "المستوى العام"        : "Overall Level");

    var html = '<div class="hm-stat-label">' + esc(covLbl) + '</div><div class="hm-stat-value">' + covered + "/12</div>";

    if (covered) {
      html += '<div class="hm-stat-label">' + esc(avgLbl) + '</div>' +
              '<div class="hm-stat-value" style="color:' + riskColor(avgRisk) + '">' + avgRisk.toFixed(0) + "</div>";
    }
    if (topGov) {
      var topName = govName(topGov);
      html += '<div class="hm-stat-label">' + esc(topLbl) + '</div><div class="hm-stat-value">' + esc(topName) + "</div>";
    }
    if (rl) {
      html += '<div class="hm-stat-label">' + esc(lvlLbl) + '</div>' +
              '<div class="hm-stat-value" style="color:' + rl.color + '">' + esc(riskLevelLabel(rl)) + "</div>";
    }
    statsEl.innerHTML = html;
  }

  /* ── GOVERNORATE CLICK HANDLERS ──────────────────────────────── */
  function handleCardGovClick(slug, gov, indicator) {
    var sel = document.getElementById("indicatorViewSelect");
    if (sel) sel.value = indicator.key;
    state.selectedSlug = slug;
    showSingleMap(indicator.key);
    loadGovDetail(slug);
    highlightGov(slug);
  }

  function handleSingleGovClick(slug, gov, indicator) {
    state.selectedSlug = slug;
    loadGovDetail(slug);
    highlightGov(slug);
  }

  function highlightGov(slug) {
    var rows = document.querySelectorAll("#rankingsTable tbody tr");
    for (var j = 0; j < rows.length; j++) {
      rows[j].classList.toggle("selected", rows[j].dataset.slug === slug);
    }
    if (window.JordanHeatmap && window.JordanHeatmap.highlightGov) {
      window.JordanHeatmap.highlightGov(slug);
    }
  }

  /* ── VIEW SWITCHING ──────────────────────────────────────────── */
  function showMultiMap() {
    var multi  = document.getElementById("multiMapSection");
    var single = document.getElementById("singleMapSection");
    if (multi)  multi.style.display  = "";
    if (single) single.style.display = "none";
    state.selectedIndicator = "";
    state.selectedSlug      = null;
    resetIntelPanel();
  }

  function showSingleMap(indKey) {
    var ind    = null;
    for (var i = 0; i < INDICATORS.length; i++) {
      if (INDICATORS[i].key === indKey) { ind = INDICATORS[i]; break; }
    }
    if (!ind) { showMultiMap(); return; }

    var multi  = document.getElementById("multiMapSection");
    var single = document.getElementById("singleMapSection");
    if (multi)  multi.style.display  = "none";
    if (single) single.style.display = "";
    state.selectedIndicator = indKey;

    var titleEl = document.getElementById("singleMapTitle");
    var descEl  = document.getElementById("singleMapDesc");
    if (titleEl) titleEl.textContent = indLabel(ind);
    if (descEl)  descEl.textContent  = indDesc(ind);

    var loadEl = document.getElementById("singleMapLoading");
    var errEl  = document.getElementById("singleMapError");
    var wrapEl = document.getElementById("singleMapWrap");

    if (!state.geojson || !state.governorates.length) {
      if (loadEl) loadEl.style.display = "none";
      if (errEl)  errEl.style.display  = "flex";
      if (wrapEl) wrapEl.style.display = "none";
      return;
    }
    // Delegate to Leaflet-based JordanHeatmap
    if (window.JordanHeatmap && window.JordanHeatmap.showSingleMap) {
      window.JordanHeatmap.showSingleMap(indKey, state.governorates, state.geojson, function(slug) {
        loadGovDetail(slug);
        highlightGov(slug);
      });
      if (loadEl) loadEl.style.display = "none";
      if (errEl)  errEl.style.display  = "none";
      if (wrapEl) wrapEl.style.display = "block";
    } else {
      // Fallback: show loading then error
      if (loadEl) loadEl.style.display = "none";
      if (errEl)  errEl.style.display  = "flex";
      if (wrapEl) wrapEl.style.display = "none";
    }
  }

  /* ── INTEL PANEL ─────────────────────────────────────────────── */
  function resetIntelPanel() {
    var panel = document.getElementById("intelPanel");
    if (!panel) return;
    panel.innerHTML =
      '<div class="intel-placeholder">' +
        '<div class="intel-placeholder-icon"><i class="bi bi-map" style="font-size:3rem;opacity:0.18" aria-hidden="true"></i></div>' +
        '<div class="intel-placeholder-title">' + (IS_AR ? "اختر محافظة" : "Select a Governorate") + "</div>" +
        '<div class="intel-placeholder-sub">' + (IS_AR ? "انقر على أي محافظة في الخريطة لعرض تقرير المحافظة الكامل." : "Click any governorate on the map to load its full report.") + "</div>" +
      "</div>";
  }

  function loadGovDetail(slug) {
    var panel = document.getElementById("intelPanel");
    if (!panel) return;
    var gov  = state.govLookup[slug] || null;
    var name = gov ? govName(gov) : slug;

    panel.innerHTML =
      '<div class="intel-loading">' +
        '<div class="intel-loading-spinner" aria-hidden="true"></div>' +
        '<div class="intel-loading-name">' + esc(name) + "</div>" +
      "</div>";

    apiGet("/governorate/" + encodeURIComponent(slug))
      .then(function(data) { renderGovDetail(panel, data, slug); })
      .catch(function() {
        panel.innerHTML =
          '<div class="intel-error">' +
            '<i class="bi bi-exclamation-octagon" aria-hidden="true"></i>' +
            "<p>" + (IS_AR ? "تعذر تحميل بيانات المحافظة" : "Failed to load governorate data") + "</p>" +
            '<button class="cc-btn" onclick="window._hmLoadGov&&window._hmLoadGov(\'' + esc(slug) + '\')">' + (IS_AR ? "إعادة المحاولة" : "Retry") + "</button>" +
          "</div>";
      });
  }

  var FIELD_TO_IND_KEY = {
    reports_attendance:    "attendance",
    safety_incidents:      "incidents",
    tasks_governance:      "governance",
    children_registration: "data_quality",
    nursery_status:        "occupancy",
  };

  function findIndicator(key) {
    for (var i = 0; i < INDICATORS.length; i++) {
      if (INDICATORS[i].key === key) return INDICATORS[i];
    }
    return null;
  }

  function renderGovDetail(panel, data, slug) {
    var gov   = (data && data.governorate) || data || {};
    var rl    = riskLevel(gov.risk_score || 0);
    var name  = govName(gov, slug);
    var sub   = govNameAlt(gov);

    var indBars = "";
    var mi = gov.main_indicators || {};
    for (var field in mi) {
      if (!Object.prototype.hasOwnProperty.call(mi, field)) continue;
      var indKey = FIELD_TO_IND_KEY[field];
      if (!indKey) continue;
      var ind2  = findIndicator(indKey);
      if (!ind2) continue;
      var risk2 = Math.max(0, Math.min(100, ind2.toRisk(+mi[field])));
      var rl2   = riskLevel(risk2);
      indBars +=
        '<div class="intel-ind-row">' +
          '<div class="intel-ind-label">' + esc(indLabel(ind2)) + "</div>" +
          '<div class="intel-ind-bar">' +
            '<div class="intel-ind-track" role="progressbar" aria-valuenow="' + risk2.toFixed(0) + '" aria-valuemin="0" aria-valuemax="100">' +
              '<div class="intel-ind-fill" style="width:' + risk2.toFixed(0) + '%;background:' + rl2.color + '"></div>' +
            "</div>" +
            '<div class="intel-ind-score" style="color:' + rl2.color + '">' + risk2.toFixed(0) + "</div>" +
          "</div>" +
        "</div>";
    }

    var alerts    = gov.alerts || [];
    var alertsHtml = "";
    if (alerts.length) {
      for (var k = 0; k < Math.min(alerts.length, 4); k++) {
        var a   = alerts[k];
        var msg = IS_AR ? (a.message_ar || a.message || "") : (a.message || a.message_ar || "");
        alertsHtml += '<div class="intel-alert-row"><div class="intel-alert-dot" aria-hidden="true"></div><span>' + esc(msg) + "</span></div>";
      }
    } else {
      alertsHtml = '<div class="intel-no-alerts">' + (IS_AR ? "لا توجد تنبيهات نشطة" : "No active alerts") + "</div>";
    }

    var actionHtml = "";
    var action = gov.recommended_action;
    if (action) {
      var txt = typeof action === "string" ? action : (IS_AR ? (action.text_ar || action.text || "") : (action.text || action.text_ar || ""));
      if (txt) {
        actionHtml =
          '<div class="intel-action-box">' +
            '<i class="bi bi-lightning-charge" aria-hidden="true"></i>' +
            "<span>" + esc(txt) + "</span>" +
          "</div>";
      }
    }

    panel.innerHTML =
      '<div class="intel-gov-header">' +
        '<div class="intel-gov-namerow">' +
          '<h2 class="intel-gov-name">' + esc(name) + "</h2>" +
          '<span class="intel-gov-code">' + esc(gov.code || "") + "</span>" +
        "</div>" +
        (sub ? '<div class="intel-gov-name-sub">' + esc(sub) + "</div>" : "") +
        '<div class="intel-risk-row">' +
          '<span class="intel-risk-score" style="color:' + rl.color + '">' + (+gov.risk_score || 0).toFixed(0) + "</span>" +
          '<span class="intel-risk-badge risk-' + rl.key + '">' + esc(riskLevelLabel(rl)) + "</span>" +
        "</div>" +
      "</div>" +
      actionHtml +
      '<div class="intel-section">' +
        '<div class="intel-section-title">' + (IS_AR ? "مؤشرات المخاطر" : "Risk Indicators") + "</div>" +
        (indBars || '<div style="color:#64748b;font-size:0.875rem">' + (IS_AR ? "لا توجد بيانات" : "No data") + "</div>") +
      "</div>" +
      '<div class="intel-section">' +
        '<div class="intel-section-title">' + (IS_AR ? "التنبيهات النشطة" : "Active Alerts") + ' <span class="intel-count">(' + alerts.length + ")</span></div>" +
        alertsHtml +
      "</div>" +
      '<div class="intel-footer">' +
        (IS_AR ? "آخر تحديث:" : "Last update:") + " " + esc(gov.last_update || "--") + "<br>" +
        (IS_AR ? "الروضات:" : "Kindergartens:") + " " + (gov.kindergarten_count != null ? gov.kindergarten_count : "--") +
      "</div>";
  }

  /* ── KPI STRIP ───────────────────────────────────────────────── */
  function renderKPIStrip(govs) {
    var sum  = 0, crit = 0, totKG = 0;
    for (var i = 0; i < govs.length; i++) {
      var s = +govs[i].risk_score || 0;
      sum  += s;
      if (s >= 75) crit++;
      totKG += govs[i].kindergarten_count || 0;
    }
    var avg = govs.length ? sum / govs.length : 0;
    var rl  = riskLevel(avg);

    var avgEl  = document.getElementById("kpiAvgRisk");
    var critEl = document.getElementById("kpiCritical");
    var kgEl   = document.getElementById("kpiInstitutions");
    if (avgEl)  { avgEl.textContent  = avg.toFixed(0); avgEl.style.color = rl.color; }
    if (critEl) critEl.textContent   = crit;
    if (kgEl)   kgEl.textContent     = totKG;
  }

  /* ── RANKINGS TABLE ──────────────────────────────────────────── */
  var _rankSortKey = "risk_score";
  var _rankSortDir = -1;

  function renderRankings(govs) {
    var tbody = document.querySelector("#rankingsTable tbody");
    if (!tbody) return;

    var sorted = govs.slice().sort(function(a, b) {
      var av = a[_rankSortKey] != null ? a[_rankSortKey] : 0;
      var bv = b[_rankSortKey] != null ? b[_rankSortKey] : 0;
      return (typeof av === "string" ? av.localeCompare(bv) : av - bv) * _rankSortDir;
    });

    var rows = "";
    for (var i = 0; i < sorted.length; i++) {
      var g      = sorted[i];
      var rl     = riskLevel(g.risk_score || 0);
      var rlLbl  = riskLevelLabel(rl);
      var rank   = i + 1;
      var rnkCls = rank === 1 ? " top-1" : rank === 2 ? " top-2" : rank === 3 ? " top-3" : "";
      var name   = govName(g);
      var sub    = govNameAlt(g);
      var score  = +(g.risk_score || 0);
      rows +=
        '<tr data-slug="' + esc(g.slug) + '" title="' + esc(name) + '">' +
          '<td><span class="rank-num' + rnkCls + '">' + rank + "</span></td>" +
          "<td>" +
            '<div class="rank-name">' + esc(name) + "</div>" +
            (sub ? '<div class="rank-code">' + esc(sub) + "</div>" : "") +
          "</td>" +
          "<td>" +
            '<div style="display:flex;align-items:center;gap:0.375rem">' +
              '<div class="mini-bar-track" aria-hidden="true">' +
                '<div class="mini-bar-fill" style="width:' + score.toFixed(0) + "%;background:" + rl.color + '"></div>' +
              "</div>" +
              '<span style="color:' + rl.color + ";font-weight:700;min-width:28px;text-align:end\">" + score.toFixed(0) + "</span>" +
            "</div>" +
          "</td>" +
          '<td><span class="rank-badge risk-' + rl.key + '">' + esc(rlLbl) + "</span></td>" +
          "<td>" +
            '<button class="rank-drill"' +
              ' title="' + (IS_AR ? "عرض التفاصيل" : "View details") + '"' +
              ' aria-label="' + (IS_AR ? "عرض تفاصيل " : "View details for ") + esc(name) + '"' +
              ' onclick="window._hmLoadGov&&window._hmLoadGov(\'' + esc(g.slug) + '\')">' +
              '<i class="bi bi-chevron-left" aria-hidden="true"></i>' +
            "</button>" +
          "</td>" +
        "</tr>";
    }
    tbody.innerHTML = rows;

    var trs = tbody.querySelectorAll("tr");
    for (var j = 0; j < trs.length; j++) {
      (function(tr) {
        tr.addEventListener("click", function(e) {
          if (e.target.closest(".rank-drill")) return;
          var slug = tr.dataset.slug;
          if (!slug) return;
          state.selectedIndicator = "";
          goToGov(slug);
        });
      })(trs[j]);
    }
  }

  /* ── STATUS BAR UPDATES ──────────────────────────────────────── */
  function renderLastUpdate(daily) {
    var el = document.getElementById("lastUpdateStatus");
    if (!el) return;
    var ts = (daily && daily.last_run && daily.last_run.completed_at) || (daily && daily.updated_at);
    if (!ts) return;
    var d = new Date(ts);
    if (isNaN(d)) return;
    var lbl  = IS_AR ? "آخر تحديث:" : "Updated:";
    var time = d.toLocaleTimeString(IS_AR ? "ar-JO" : "en-US", { hour: "2-digit", minute: "2-digit" });
    el.innerHTML = '<i class="bi bi-clock" aria-hidden="true"></i> ' + lbl + " " + time;
  }

  function renderAlertCount(govs) {
    var el = document.getElementById("alertCountStatus");
    if (!el) return;
    var total = 0;
    for (var i = 0; i < govs.length; i++) total += (govs[i].alerts && govs[i].alerts.length) || 0;
    el.innerHTML = '<i class="bi bi-shield-exclamation" aria-hidden="true"></i> ' + total;
    if (total > 0) el.className = "status-chip alert";
  }

  /* ── GOV SELECT ──────────────────────────────────────────────── */
  function populateGovSelect(govs) {
    var sel = document.getElementById("govSelect");
    if (!sel) return;
    while (sel.options.length > 1) sel.remove(1);
    var sorted = govs.slice().sort(function(a, b) {
      return ((a.display_order || 99) - (b.display_order || 99));
    });
    for (var i = 0; i < sorted.length; i++) {
      var g   = sorted[i];
      var opt = document.createElement("option");
      opt.value       = g.slug;
      opt.textContent = govName(g);
      sel.appendChild(opt);
    }
  }

  /* ── PAGE ERROR / GRID LOADING ───────────────────────────────── */
  function showPageError(show, detail) {
    var el = document.getElementById("pageError");
    if (el) el.style.display = show ? "flex" : "none";
    if (show && detail) {
      var d = document.getElementById("pageErrorDetails");
      if (d) d.textContent = detail;
    }
    var g = document.getElementById("gridLoading");
    if (g) g.style.display = "none";
  }

  function showGridLoading(show) {
    var el   = document.getElementById("gridLoading");
    var grid = document.getElementById("multiMapGrid");
    if (el)   el.style.display        = show ? "flex" : "none";
    if (grid) grid.style.visibility   = show ? "hidden" : "visible";
  }

  /* ── GOV NAVIGATION (shared by govSelect, rankings, _hmLoadGov) ─ */
  function goToGov(slug) {
    state.selectedSlug = slug;
    if (!state.selectedIndicator) {
      var s = document.getElementById("indicatorViewSelect");
      if (s) s.value = "overall_risk";
      showSingleMap("overall_risk");
    }
    loadGovDetail(slug);
    highlightGov(slug);
  }

  /* ── CONTROLS ────────────────────────────────────────────────── */
  function bindControls() {
    var indSel = document.getElementById("indicatorViewSelect");
    if (indSel) {
      indSel.addEventListener("change", function() {
        if (indSel.value) showSingleMap(indSel.value);
        else              showMultiMap();
      });
    }

    var govSel = document.getElementById("govSelect");
    if (govSel) {
      govSel.addEventListener("change", function() {
        if (govSel.value) goToGov(govSel.value);
      });
    }

    var refreshBtn = document.getElementById("refreshBtn");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", function() {
        _svgPathCache      = null;
        state.geojson      = null;
        state.governorates = [];
        state.govLookup    = Object.create(null);
        init();
      });
    }

    var retryPage = document.getElementById("retryPageBtn");
    if (retryPage) {
      retryPage.addEventListener("click", function() {
        showPageError(false, "");
        init();
      });
    }

    var retrySingle = document.getElementById("retrySingleBtn");
    if (retrySingle) {
      retrySingle.addEventListener("click", function() {
        if (state.selectedIndicator) showSingleMap(state.selectedIndicator);
      });
    }

    var ths = document.querySelectorAll("#rankingsTable th[data-sort]");
    for (var i = 0; i < ths.length; i++) {
      (function(th) {
        th.addEventListener("click", function() {
          var key = th.dataset.sort;
          if (_rankSortKey === key) _rankSortDir = -_rankSortDir;
          else { _rankSortKey = key; _rankSortDir = -1; }
          renderRankings(state.governorates);
        });
      })(ths[i]);
    }

    window._hmRetry = function(indKey) {
      var ind = findIndicator(indKey);
      if (ind) renderCard(ind);
    };
    window._hmLoadGov = goToGov;
  }

  /* ── INIT ────────────────────────────────────────────────────── */
  function init() {
    showGridLoading(true);
    showPageError(false, "");

    Promise.allSettled([
      apiGet("/data"),
      apiGet("/geojson"),
      apiGet("/daily-update"),
    ]).then(function(results) {
      var mapRes   = results[0];
      var gjRes    = results[1];
      var dailyRes = results[2];

      if (gjRes.status === "rejected" || !gjRes.value || !gjRes.value.features || !gjRes.value.features.length) {
        showGridLoading(false);
        showPageError(true, (gjRes.reason && gjRes.reason.message) || t("heatmap.map_load_error", "GeoJSON unavailable"));
        return;
      }
      state.geojson = gjRes.value;

      var mapData       = mapRes.status === "fulfilled" ? mapRes.value : null;
      state.governorates = (mapData && mapData.governorates) || [];

      state.govLookup = Object.create(null);
      for (var i = 0; i < state.governorates.length; i++) {
        var g = state.governorates[i];
        if (g.code) state.govLookup[g.code] = g;
        if (g.slug) state.govLookup[g.slug] = g;
      }

      buildSVGPathCache(state.geojson, state.govLookup);
      buildMultiMapGrid();
      renderAllCards();

      renderKPIStrip(state.governorates);
      renderRankings(state.governorates);
      populateGovSelect(state.governorates);
      renderAlertCount(state.governorates);
      if (dailyRes.status === "fulfilled") renderLastUpdate(dailyRes.value);

      showGridLoading(false);

      // Default view: satellite Leaflet map (overall risk)
      var indSel = document.getElementById("indicatorViewSelect");
      if (indSel) indSel.value = "overall_risk";
      showSingleMap("overall_risk");
    }).catch(function(err) {
      console.error("[Heatmap] init error:", err);
      showGridLoading(false);
      showPageError(true, err.message || "");
    });
  }

  document.addEventListener("DOMContentLoaded", function() {
    bindControls();
    init();
  });
})();
