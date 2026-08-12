(function () {
  "use strict";

  const state = {
    entityType: "KINDERGARTEN",
    filters: null,
    charts: {},
  };

  let autoRefreshInterval = null;
  let sortState = { column: null, ascending: false };
  let classPage = 1;
  const CLASS_PAGE_SIZE = 25;
  let allClassRows = [];

  const lang = window.KINJO_LANG === "en" ? "en" : "ar";
  const isEn = lang === "en";

  const T = {
    all: isEn ? "All" : "\u0627\u0644\u0643\u0644",
    loading: isEn ? "Loading classification data..." : "\u062c\u0627\u0631 \u062a\u062d\u0645\u064a\u0644 \u0628\u064a\u0627\u0646\u0627\u062a \u0627\u0644\u062a\u0635\u0646\u064a\u0641...",
    noData: isEn ? "Not enough data within the current filters." : "\u0644\u0627 \u062a\u0648\u062c\u062f \u0628\u064a\u0627\u0646\u0627\u062a \u0643\u0627\u0641\u064a\u0629 \u0636\u0645\u0646 \u0627\u0644\u0641\u0644\u0627\u062a\u0631 \u0627\u0644\u062d\u0627\u0644\u064a\u0629.",
    loadError: isEn ? "Failed to load the leaderboard. Please check filters and retry." : "\u062a\u0639\u0630\u0631 \u062a\u062d\u0645\u064a\u0644 \u0642\u0627\u0626\u0645\u0629 \u0627\u0644\u062a\u0635\u0646\u064a\u0641. \u064a\u0631\u062c\u0649 \u0627\u0644\u062a\u062d\u0642\u0642 \u0645\u0646 \u0627\u0644\u0641\u0644\u0627\u062a\u0631 \u0623\u0648 \u0625\u0639\u0627\u062f\u0629 \u0627\u0644\u0645\u062d\u0627\u0648\u0644\u0629.",
    detailError: isEn ? "Failed to load detail for the selected entity." : "\u062a\u0639\u0630\u0631 \u062a\u062d\u0645\u064a\u0644 \u062a\u0641\u0627\u0635\u064a\u0644 \u0627\u0644\u0643\u064a\u0627\u0646 \u0627\u0644\u0645\u062d\u062f\u062f.",
    initError: isEn ? "Failed to initialise the classification page. Please refresh." : "\u062a\u0639\u0630\u0631 \u062a\u0647\u064a\u0626\u0629 \u0635\u0641\u062d\u0629 \u0627\u0644\u062a\u0635\u0646\u064a\u0641. \u064a\u0631\u062c\u0649 \u062a\u062d\u062f\u064a\u062b \u0627\u0644\u0635\u0641\u062d\u0629.",
    viewDetail: isEn ? "View Details" : "\u0639\u0631\u0636 \u0627\u0644\u062a\u0641\u0627\u0635\u064a\u0644",
    unavailable: isEn ? "N/A" : "\u063a\u064a\u0631 \u0645\u062a\u0627\u062d",
    unclassified: isEn ? "Unclassified" : "\u063a\u064a\u0631 \u0645\u0635\u0646\u0641",
    stable: isEn ? "Stable" : "\u0645\u0633\u062a\u0642\u0631",
    up: isEn ? "Rising" : "\u0635\u0627\u0639\u062f",
    down: isEn ? "Falling" : "\u0647\u0627\u0628\u0637",
    noTrend: "--",
    finalScore: isEn ? "Final Score" : "\u0627\u0644\u062f\u0631\u062c\u0629 \u0627\u0644\u0646\u0647\u0627\u0626\u064a\u0629",
    band: isEn ? "Band" : "\u0627\u0644\u0646\u0637\u0627\u0642",
    dataCoverage: isEn ? "Data Coverage" : "\u062a\u063a\u0637\u064a\u0629 \u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a",
    period: isEn ? "Period" : "\u0627\u0644\u0641\u062a\u0631\u0629",
    periodTo: isEn ? "to" : "\u0625\u0644\u0649",
    chartScore: isEn ? "Final Score" : "\u0627\u0644\u062f\u0631\u062c\u0629 \u0627\u0644\u0646\u0647\u0627\u0626\u064a\u0629",
    chartYAxis: isEn ? "Score" : "\u0642\u064a\u0645\u0629 \u0627\u0644\u0645\u0624\u0634\u0631",
    chartXAxis: isEn ? "Period" : "\u0627\u0644\u0641\u062a\u0631\u0629",
    governorate: isEn ? "Governorate" : "\u0627\u0644\u0645\u062d\u0627\u0641\u0638\u0629",
    total: isEn ? "Total" : "\u0627\u0644\u0625\u062c\u0645\u0627\u0644\u064a",
    ranked: isEn ? "ranked" : "\u0645\u0635\u0646\u0641",
    insufficient: isEn ? "insufficient" : "\u063a\u064a\u0631 \u0645\u0643\u062a\u0645\u0644",
    entities: isEn ? "entities" : "\u0643\u064a\u0627\u0646\u0627\u062a",
    topCount: isEn ? "Top 8 by score" : "\u0623\u0639\u0644\u0649 8 \u062d\u0633\u0628 \u0627\u0644\u062f\u0631\u062c\u0629",
    aspectAverage: isEn ? "Average score by indicator" : "\u0645\u062a\u0648\u0633\u0637 \u0627\u0644\u062f\u0631\u062c\u0629 \u062d\u0633\u0628 \u0627\u0644\u0645\u0624\u0634\u0631",
    noChartData: isEn ? "No chartable data" : "\u0644\u0627 \u062a\u0648\u062c\u062f \u0628\u064a\u0627\u0646\u0627\u062a \u0644\u0644\u0631\u0633\u0645",
    green: isEn ? "Green" : "\u0623\u062e\u0636\u0631",
    amber: isEn ? "Amber" : "\u0643\u0647\u0631\u0645\u0627\u0646\u064a",
    red: isEn ? "Red" : "\u0623\u062d\u0645\u0631",
    chartLibMissing: isEn ? "Chart library not loaded. Please check your internet connection." : "\u0644\u0645 \u064a\u062a\u0645 \u062a\u062d\u0645\u064a\u0644 \u0645\u0643\u062a\u0628\u0629 \u0627\u0644\u0631\u0633\u0648\u0645. \u064a\u0631\u062c\u0649 \u0627\u0644\u062a\u062d\u0642\u0642 \u0645\u0646 \u0627\u062a\u0635\u0627\u0644\u0643 \u0628\u0627\u0644\u0625\u0646\u062a\u0631\u0646\u062a.",
  };

  const BAND_META = {
    GREEN: { label: T.green, color: "#10b981", badge: "bg-success" },
    AMBER: { label: T.amber, color: "#f59e0b", badge: "bg-warning text-dark" },
    RED: { label: T.red, color: "#ef4444", badge: "bg-danger" },
    UNCLASSIFIED: { label: T.unclassified, color: "#94a3b8", badge: "bg-secondary" },
  };

  function escapeValue(value) {
    if (typeof window.escapeHtml === "function") {
      return window.escapeHtml(value);
    }
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  async function apiRequest(url, retries = 2) {
    let lastError;
    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        let response;
        if (typeof window.api?.get === "function") {
          return window.api.get(url);
        } else if (typeof window.fetchWithAuth === "function") {
          response = await window.fetchWithAuth(url, { method: "GET" });
        } else {
          response = await fetch(url, { method: "GET", credentials: "same-origin" });
        }
        if (!response) {
          throw new Error(T.loadError);
        }
        if (!response.ok) {
          const text = await response.text();
          throw new Error(text || T.loadError);
        }
        return response.json();
      } catch (error) {
        lastError = error;
        if (attempt < retries) {
          await new Promise(r => setTimeout(r, 500 * Math.pow(2, attempt)));
        }
      }
    }
    throw lastError;
  }

  function formatNumber(value, digits = 2) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return "--";
    }
    return Number(value).toFixed(digits);
  }

  function formatPercent(value, digits = 1) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return "--";
    }
    return `${Number(value).toFixed(digits)}%`;
  }

  function average(values) {
    const clean = values.filter((value) => value !== null && value !== undefined && !Number.isNaN(Number(value)));
    if (!clean.length) {
      return null;
    }
    return clean.reduce((total, value) => total + Number(value), 0) / clean.length;
  }

  function setText(id, value) {
    const element = document.getElementById(id);
    if (element) {
      element.textContent = value;
    }
  }

  function formatDateValue(dateObj) {
    const year = dateObj.getFullYear();
    const month = String(dateObj.getMonth() + 1).padStart(2, "0");
    const day = String(dateObj.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function updateDefaultPeriod() {
    const endInput = document.getElementById("periodEnd");
    const startInput = document.getElementById("periodStart");
    if (!endInput || !startInput || endInput.value || startInput.value) {
      return;
    }
    const endDate = new Date();
    const startDate = new Date();
    startDate.setDate(endDate.getDate() - 29);
    endInput.value = formatDateValue(endDate);
    startInput.value = formatDateValue(startDate);
  }

  function renderSelect(selectId, options, includeAll = false) {
    const select = document.getElementById(selectId);
    if (!select) {
      return;
    }
    const parts = [];
    if (includeAll) {
      parts.push(`<option value="">${escapeValue(T.all)}</option>`);
    }
    (options || []).forEach((item) => {
      if (typeof item === "string") {
        parts.push(`<option value="${escapeValue(item)}">${escapeValue(item)}</option>`);
      } else {
        parts.push(`<option value="${escapeValue(item.value)}">${escapeValue(item.label)}</option>`);
      }
    });
    select.innerHTML = parts.join("");
  }

  function filterParams() {
    const params = new URLSearchParams();
    const fields = [
      ["period_start", "periodStart"],
      ["period_end", "periodEnd"],
      ["level", "levelSelect"],
      ["size_mode", "sizeModeSelect"],
      ["size_band", "sizeBandSelect"],
      ["country", "countrySelect"],
      ["governorate", "governorateSelect"],
      ["district", "citySelect"],
      ["area", "areaSelect"],
      ["min_sample_days", "minSampleDays"],
    ];
    fields.forEach(([paramName, elementId]) => {
      const value = document.getElementById(elementId)?.value;
      if (value) {
        params.set(paramName, value);
      }
    });
    return params;
  }

  function syncUrlWithFilters() {
    const params = filterParams();
    const qs = params.toString();
    const newUrl = qs ? `${window.location.pathname}?${qs}` : window.location.pathname;
    try {
      history.replaceState({ filters: qs }, "", newUrl);
    } catch (_) {
    }
  }

  function cssVar(name, fallback) {
    try {
      return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
    } catch (_) {
      return fallback;
    }
  }

  function showToast(message, type = "error") {
    const container = document.getElementById("classificationRoot");
    if (!container) return;
    const existing = container.querySelector(".classification-toast");
    if (existing) existing.remove();
    const toast = document.createElement("div");
    toast.className = `classification-toast alert alert-${type === "error" ? "danger" : "info"} alert-dismissible fade show position-fixed bottom-0 end-0 m-3`;
    toast.style.zIndex = "9999";
    toast.style.maxWidth = "400px";
    toast.innerHTML = `${escapeValue(message)}<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="${escapeValue(isEn ? "Close" : "إغلاق")}"></button>`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 8000);
  }

  function loadFiltersFromUrl() {
    try {
      const params = new URLSearchParams(window.location.search);
      if (!params.size) return;
      const elementMap = {
        period_start: "periodStart", period_end: "periodEnd",
        level: "levelSelect", size_mode: "sizeModeSelect",
        size_band: "sizeBandSelect", country: "countrySelect",
        governorate: "governorateSelect", district: "citySelect",
        area: "areaSelect", min_sample_days: "minSampleDays",
      };
      for (const [param, elementId] of Object.entries(elementMap)) {
        const value = params.get(param);
        if (value) {
          const el = document.getElementById(elementId);
          if (el) el.value = value;
        }
      }
    } catch (_) {
    }
  }

  function startAutoRefresh(intervalMs = 300000) {
    stopAutoRefresh();
    autoRefreshInterval = setInterval(() => {
      loadLeaderboard();
    }, intervalMs);
  }

  function stopAutoRefresh() {
    if (autoRefreshInterval) {
      clearInterval(autoRefreshInterval);
      autoRefreshInterval = null;
    }
  }

  function initOfflineDetection() {
    const el = document.getElementById("classificationOffline");
    if (!el) return;
    const update = () => {
      el.classList.toggle("d-none", navigator.onLine !== false);
    };
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    update();
  }

  function setLoading(isLoading) {
    const el = document.getElementById("classificationLoading");
    if (!el) return;
    el.classList.toggle("d-none", !isLoading);
    if (isLoading) {
      const dots = window.KINJO_LANG === "en" ? "Loading" : "جار التحميل";
      let count = 0;
      const animate = () => {
        if (!el.classList.contains("d-none")) {
          el.textContent = `${dots}${".".repeat((count % 3) + 1)}`;
          count++;
        }
      };
      animate();
      el._interval = setInterval(animate, 500);
    } else if (el._interval) {
      clearInterval(el._interval);
      delete el._interval;
    }
  }

  function setError(message) {
    const errorBox = document.getElementById("classificationError");
    if (!errorBox) {
      return;
    }
    errorBox.textContent = message || "";
    errorBox.classList.toggle("d-none", !message);
    if (message) showToast(message, "error");
  }

  function setEmpty(isEmpty) {
    document.getElementById("classificationEmpty")?.classList.toggle("d-none", !isEmpty);
  }

  function bandKey(code) {
    return code && BAND_META[code] ? code : "UNCLASSIFIED";
  }

  function bandBadgeClass(code) {
    return BAND_META[bandKey(code)].badge;
  }

  function bandLabel(row) {
    const key = bandKey(row.band_code);
    return key === "UNCLASSIFIED" ? (row.band_label || T.unclassified) : BAND_META[key].label;
  }

  // Backend strings arrive as {ar, en} pairs. Fall back to Arabic, then to the
  // raw value, so an older payload still renders something readable.
  function localizedText(value) {
    if (!value) return "";
    if (typeof value === "string") return value;
    return value[lang] || value.ar || value.en || "";
  }

  // Aspect keys are stable English codes; the human-readable name comes from
  // the aspect_labels map the API sends alongside them.
  function aspectLabel(detail, code) {
    const labels = (detail && detail.aspect_labels) || {};
    return localizedText(labels[code]) || code;
  }

  function trendText(row) {
    if (row.trend_direction === "NONE") return T.noTrend;
    const delta = formatNumber(Math.abs(row.trend_vs_previous || 0));
    if (row.trend_direction === "UP") {
      return `${T.up} (+${delta})`;
    }
    if (row.trend_direction === "DOWN") {
      return `${T.down} (${formatNumber(row.trend_vs_previous || 0)})`;
    }
    if (row.trend_direction === "STABLE") {
      return T.stable;
    }
    return T.noTrend;
  }

  function tableRowHtml(row) {
    const score = row.final_score === null ? T.unavailable : formatNumber(row.final_score);
    const percentile = row.percentile === null ? "--" : formatPercent(row.percentile);
    const coverage = formatPercent(row.coverage_pct);
    const rank = row.rank === null ? "--" : row.rank;
    const info =
      row.insufficient_data && row.insufficient_reason
        ? `<div class="small text-danger">${escapeValue(row.insufficient_reason)}</div>`
        : "";
    const disabled = row.insufficient_data ? "disabled" : "";
    const govText = row.geography && row.geography.governorate
      ? `<div class="small text-muted">${escapeValue(T.governorate)}: ${escapeValue(row.geography.governorate)}</div>`
      : "";

    return `
      <tr tabindex="0" role="row">
        <td>${escapeValue(rank)}</td>
        <td>
          <div class="fw-semibold">${escapeValue(row.display_name)}</div>
          ${govText}${info}
        </td>
        <td class="fw-semibold">${escapeValue(score)}</td>
        <td>${escapeValue(percentile)}</td>
        <td><span class="badge ${bandBadgeClass(row.band_code)}">${escapeValue(bandLabel(row))}</span></td>
        <td>${escapeValue(trendText(row))}</td>
        <td>${escapeValue(coverage)}</td>
        <td>
          <button class="btn btn-sm btn-outline-primary" data-detail-entity="${escapeValue(row.entity_type)}" data-detail-id="${escapeValue(row.entity_id)}" aria-label="${escapeValue(T.viewDetail)}: ${escapeValue(row.display_name)}" ${disabled}>
            <i class="bi bi-eye me-1"></i>${escapeValue(T.viewDetail)}
          </button>
        </td>
      </tr>
    `;
  }

  function endpointForEntityType() {
    if (state.entityType === "MANAGER") return "/api/admin/classification/managers";
    if (state.entityType === "SUPERVISOR") return "/api/admin/classification/supervisors";
    return "/api/admin/classification/kindergartens";
  }

  function renderRows(rows, resetPage = true) {
    if (resetPage) classPage = 1;
    allClassRows = rows || [];
    window._classificationData = { rows: allClassRows };

    const tbody = document.getElementById("classificationTableBody");
    if (!tbody) return;

    if (!allClassRows.length) {
      tbody.innerHTML = "";
      setEmpty(true);
      const pg = document.getElementById("classificationPagination");
      if (pg) pg.innerHTML = "";
      return;
    }
    setEmpty(false);
    renderClassPage();
  }

  function renderClassPage() {
    const tbody = document.getElementById("classificationTableBody");
    if (!tbody) return;

    const start = (classPage - 1) * CLASS_PAGE_SIZE;
    const page  = allClassRows.slice(start, start + CLASS_PAGE_SIZE);
    tbody.innerHTML = page.map((row) => tableRowHtml(row)).join("");
    renderClassPagination(allClassRows.length);
  }

  function renderClassPagination(total) {
    const el = document.getElementById("classificationPagination");
    if (!el) return;
    const totalPages = Math.ceil(total / CLASS_PAGE_SIZE);
    if (totalPages <= 1) { el.innerHTML = ""; return; }

    const show = new Set([1, totalPages, classPage, classPage - 1, classPage + 1]
      .filter(p => p >= 1 && p <= totalPages));
    const pages = [...show].sort((a, b) => a - b);

    let prev = 0;
    const parts = [];
    for (const p of pages) {
      if (p - prev > 1) parts.push('<span class="text-muted px-1" aria-hidden="true">…</span>');
      parts.push(`<button class="btn btn-sm ${p === classPage ? 'btn-primary' : 'btn-outline-secondary'}"
        onclick="window.goClassPage(${p})" aria-label="${isEn ? 'Page' : 'صفحة'} ${p}">${p}</button>`);
      prev = p;
    }

    el.innerHTML = `
      <button class="btn btn-sm btn-outline-secondary" ${classPage === 1 ? 'disabled' : ''}
        onclick="window.goClassPage(${classPage - 1})" aria-label="${isEn ? 'Previous' : 'السابق'}">
        <i class="bi bi-chevron-${isEn ? 'left' : 'right'}"></i>
      </button>
      ${parts.join('')}
      <button class="btn btn-sm btn-outline-secondary" ${classPage === totalPages ? 'disabled' : ''}
        onclick="window.goClassPage(${classPage + 1})" aria-label="${isEn ? 'Next' : 'التالي'}">
        <i class="bi bi-chevron-${isEn ? 'right' : 'left'}"></i>
      </button>`;
  }

  window.goClassPage = function(p) {
    classPage = p;
    renderClassPage();
    document.getElementById("classificationTableBody")?.closest("table")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  function chartOptions(extra = {}) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, usePointStyle: true } },
        tooltip: { intersect: false },
      },
      ...extra,
    };
  }

  function replaceChart(name, config) {
    const canvas = document.getElementById(name);
    if (!canvas) {
      return;
    }
    if (typeof window.Chart === "undefined") {
      const note = document.getElementById(`${name}Note`);
      if (note) {
        note.textContent = "Chart library not loaded. Please check your internet connection.";
      }
      return;
    }
    if (state.charts[name]) {
      state.charts[name].destroy();
    }
    state.charts[name] = new window.Chart(canvas, config);
  }

  function renderSummary(data) {
    const rows = data.rows || [];
    const rankedRows = rows.filter((row) => row.final_score !== null && !row.insufficient_data);
    const redCount = rows.filter((row) => row.band_code === "RED").length;
    const averageScore = average(rankedRows.map((row) => row.final_score));
    const averageCoverage = average(rows.map((row) => row.coverage_pct));

    setText("classificationRankedCount", String(data.ranked_entities ?? rankedRows.length));
    setText(
      "classificationTotalCount",
      `${T.total}: ${data.total_entities ?? rows.length} | ${T.insufficient}: ${data.insufficient_entities ?? 0}`
    );
    setText("classificationAverageScore", averageScore === null ? "--" : formatNumber(averageScore, 1));
    setText("classificationRedCount", String(redCount));
    setText("classificationAverageCoverage", averageCoverage === null ? "--" : formatPercent(averageCoverage));
  }

  function renderBandChart(rows) {
    const counts = { GREEN: 0, AMBER: 0, RED: 0, UNCLASSIFIED: 0 };
    rows.forEach((row) => {
      counts[bandKey(row.band_code)] += 1;
    });
    const labels = Object.keys(counts).map((key) => BAND_META[key].label);
    const values = Object.values(counts);
    const colors = Object.keys(counts).map((key) => BAND_META[key].color);
    const total = values.reduce((sum, value) => sum + value, 0);
    setText("classificationBandChartNote", total ? `${total} ${T.entities}` : T.noChartData);
    replaceChart("classificationBandChart", {
      type: "doughnut",
      data: { labels, datasets: [{ data: values, backgroundColor: colors, borderWidth: 0 }] },
      options: chartOptions({ cutout: "64%" }),
    });
    const chart = state.charts["classificationBandChart"];
    if (chart) {
      chart.options.onClick = (event, elements) => {
        if (elements.length > 0) {
          const index = elements[0].datasetIndex;
          const meta = chart.getDatasetMeta(index);
          meta.hidden = !meta.hidden;
          chart.update();
        }
      };
    }
  }

  function renderScoreChart(rows) {
    const ranked = rows
      .filter((row) => row.final_score !== null && !row.insufficient_data)
      .slice()
      .sort((a, b) => Number(b.final_score || 0) - Number(a.final_score || 0))
      .slice(0, 8);
    setText("classificationScoreChartNote", ranked.length ? T.topCount : T.noChartData);
    replaceChart("classificationScoreChart", {
      type: "bar",
      data: {
        labels: ranked.map((row) => row.display_name),
        datasets: [
          {
            label: T.chartScore,
            data: ranked.map((row) => row.final_score),
            backgroundColor: ranked.map((row) => BAND_META[bandKey(row.band_code)].color),
            borderRadius: 6,
          },
        ],
      },
      options: chartOptions({
        indexAxis: "y",
        scales: {
          x: { beginAtZero: true, max: 100, grid: { color: "rgba(148, 163, 184, 0.18)" } },
          y: { ticks: { autoSkip: false } },
        },
        plugins: { legend: { display: false } },
      }),
    });
  }

  function renderAspectChart(rows, aspectLabels) {
    const labels = aspectLabels || {};
    const buckets = {};
    rows.forEach((row) => {
      Object.entries(row.aspects || {}).forEach(([name, value]) => {
        if (value === null || value === undefined || Number.isNaN(Number(value))) {
          return;
        }
        if (!buckets[name]) {
          buckets[name] = [];
        }
        buckets[name].push(Number(value));
      });
    });
    const entries = Object.entries(buckets)
      .map(([name, values]) => [name, average(values)])
      .filter(([, value]) => value !== null)
      .sort((a, b) => Number(b[1]) - Number(a[1]))
      .slice(0, 8);
    setText("classificationAspectChartNote", entries.length ? T.aspectAverage : T.noChartData);
    replaceChart("classificationAspectChart", {
      type: "bar",
      data: {
        labels: entries.map(([name]) => localizedText(labels[name]) || name),
        datasets: [
          {
            label: T.chartScore,
            data: entries.map(([, value]) => value),
            backgroundColor: cssVar('--admin-primary', '#4F46E5'),
            borderRadius: 6,
          },
        ],
      },
      options: chartOptions({
        scales: {
          y: { beginAtZero: true, max: 100, grid: { color: "rgba(148, 163, 184, 0.18)" } },
          x: { ticks: { maxRotation: 45, minRotation: 0 } },
        },
        plugins: { legend: { display: false } },
      }),
    });
  }

  function renderCharts(data) {
    const rows = data.rows || [];
    renderBandChart(rows);
    renderScoreChart(rows);
    renderAspectChart(rows, data.aspect_labels || {});
  }

  async function loadLeaderboard() {
    setLoading(true);
    setError("");
    try {
      const params = filterParams();
      syncUrlWithFilters();
      const endpoint = endpointForEntityType();
      const data = await apiRequest(`${endpoint}?${params.toString()}`);
      renderRows(data.rows || []);
      renderSummary(data);
      renderCharts(data);
    } catch (error) {
      setError(T.loadError);
      renderRows([]);
      renderSummary({ rows: [], total_entities: 0, ranked_entities: 0, insufficient_entities: 0 });
      renderCharts({ rows: [] });
    } finally {
      setLoading(false);
    }
  }

  function drawTrendChart(points) {
    const chartPoints = points || [];
    replaceChart("classificationTrendChart", {
      type: "line",
      data: {
        labels: chartPoints.map((point) => `${point.period_start} ${T.periodTo} ${point.period_end}`),
        datasets: [
          {
            label: T.chartScore,
            data: chartPoints.map((point) => point.final_score ?? null),
            borderColor: cssVar('--admin-primary', '#4F46E5'),
            backgroundColor: cssVar('--admin-primary-bg', 'rgba(31, 94, 71, 0.14)'),
            borderWidth: 2,
            pointRadius: 3,
            tension: 0.25,
            fill: true,
            spanGaps: true,
          },
        ],
      },
      options: chartOptions({
        scales: {
          y: { beginAtZero: true, max: 100, title: { display: true, text: T.chartYAxis } },
          x: { title: { display: true, text: T.chartXAxis } },
        },
      }),
    });
  }

  function detailSummaryHtml(detail) {
    return `
      <div class="row g-3">
        <div class="col-md-3">
          <div class="border rounded p-3 h-100">
            <div class="text-muted small">${escapeValue(T.finalScore)}</div>
            <div class="h4 mb-0">${detail.final_score === null ? escapeValue(T.unavailable) : escapeValue(formatNumber(detail.final_score))}</div>
          </div>
        </div>
        <div class="col-md-3">
          <div class="border rounded p-3 h-100">
            <div class="text-muted small">${escapeValue(T.band)}</div>
            <div class="h4 mb-0">${escapeValue(BAND_META[bandKey(detail.band_code)].label)}</div>
          </div>
        </div>
        <div class="col-md-3">
          <div class="border rounded p-3 h-100">
            <div class="text-muted small">${escapeValue(T.dataCoverage)}</div>
            <div class="h4 mb-0">${escapeValue(formatPercent(detail.coverage_pct))}</div>
          </div>
        </div>
        <div class="col-md-3">
          <div class="border rounded p-3 h-100">
            <div class="text-muted small">${escapeValue(T.period)}</div>
            <div class="small fw-semibold">${escapeValue(detail.period_start)} ${escapeValue(T.periodTo)} ${escapeValue(detail.period_end)}</div>
          </div>
        </div>
      </div>
    `;
  }

  async function openDetail(entityType, entityId) {
    try {
      const params = filterParams();
      params.set("entity_type", entityType);
      params.set("entity_id", String(entityId));
      const detail = await apiRequest(`/api/admin/classification/detail?${params.toString()}`);

      const modalEl = document.getElementById("classificationDetailModal");
      const titleEl = document.getElementById("classificationDetailTitle");
      const summaryEl = document.getElementById("classificationDetailSummary");
      const aspectsEl = document.getElementById("classificationAspectsList");
      const actionsEl = document.getElementById("classificationActionsList");
      if (!modalEl || !titleEl || !summaryEl || !aspectsEl || !actionsEl) {
        return;
      }

      titleEl.textContent = detail.display_name || T.unavailable;
      summaryEl.innerHTML = detailSummaryHtml(detail);

      const aspectRows = Object.entries(detail.aspects || {}).map(
        ([name, value]) =>
          `<li class="list-group-item d-flex justify-content-between gap-3"><span>${escapeValue(aspectLabel(detail, name))}</span><span class="fw-semibold">${escapeValue(formatNumber(value))}</span></li>`
      );
      aspectsEl.innerHTML = aspectRows.join("") || `<li class="list-group-item text-muted">${escapeValue(T.noChartData)}</li>`;

      const actions = detail.action_guidance || [];
      actionsEl.innerHTML = actions.length
        ? actions.map((action) => `<li>${escapeValue(localizedText(action))}</li>`).join("")
        : `<li class="text-muted">${escapeValue(T.noData)}</li>`;

      drawTrendChart(detail.trend_points || []);

      const modal = window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(modalEl) : null;
      if (modal) {
        modal.show();
      }
    } catch (error) {
      setError(T.detailError);
    }
  }

  async function loadFilters() {
    const filters = await apiRequest("/api/admin/classification/filters");
    state.filters = filters;
    renderSelect("levelSelect", filters.levels || []);
    renderSelect("sizeModeSelect", filters.size_modes || []);
    renderSelect("sizeBandSelect", [{ value: "", label: T.all }, ...(filters.size_bands || [])]);
    renderSelect("countrySelect", filters.countries || [], true);
    renderSelect("governorateSelect", filters.governorates || [], true);
    renderSelect("citySelect", filters.cities || [], true);
    renderSelect("areaSelect", filters.areas || [], true);
  }

  function bindSortableHeaders() {
    const headers = document.querySelectorAll("#classificationTable th");
    headers.forEach((th, index) => {
      th.style.cursor = "pointer";
      th.addEventListener("click", () => {
        const columnMap = { 0: "rank", 1: "display_name", 2: "final_score", 3: "percentile", 4: "band_code", 5: "trend_direction", 6: "coverage_pct" };
        const col = columnMap[index];
        if (!col) return;
        if (sortState.column === col) sortState.ascending = !sortState.ascending;
        else { sortState.column = col; sortState.ascending = false; }
        const rows = window._classificationData?.rows || [];
        const sorted = [...rows].sort((a, b) => {
          let va = a[col], vb = b[col];
          if (col === "display_name") return sortState.ascending ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
          return sortState.ascending ? (va || 0) - (vb || 0) : (vb || 0) - (va || 0);
        });
        renderRows(sorted);
      });
    });
  }

  function bindTableKeyboardNav() {
    const tbody = document.getElementById("classificationTableBody");
    if (!tbody) return;

    tbody.addEventListener("keydown", (event) => {
      const rows = [...tbody.querySelectorAll("tr")];
      const currentIndex = rows.indexOf(document.activeElement?.closest("tr"));
      if (currentIndex === -1) return;

      if (event.key === "ArrowDown") {
        event.preventDefault();
        const next = rows[currentIndex + 1];
        if (next) next.querySelector("button")?.focus();
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        const prev = rows[currentIndex - 1];
        if (prev) prev.querySelector("button")?.focus();
      } else if (event.key === "Enter") {
        event.preventDefault();
        const btn = rows[currentIndex]?.querySelector("button[data-detail-id]");
        if (btn) btn.click();
      }
    });
  }

  function bindKeyboardShortcuts() {
    document.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.altKey) && event.key === "Enter") {
        event.preventDefault();
        loadLeaderboard();
      }
      if (event.key === "r" && !event.ctrlKey && !event.metaKey && document.activeElement?.tagName !== "INPUT" && document.activeElement?.tagName !== "SELECT" && document.activeElement?.tagName !== "TEXTAREA") {
        event.preventDefault();
        loadLeaderboard();
      }
    });
  }

  function csvCell(value) {
    const str = value === null || value === undefined ? "" : String(value);
    return /[",\n]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str;
  }

  function exportClassificationCsv() {
    if (!allClassRows.length) return;
    const headers = ["rank", "display_name", "final_score", "percentile", "classification", "trend", "coverage_pct", "governorate"];
    const lines = [headers.join(",")];
    allClassRows.forEach((row) => {
      lines.push([
        row.rank ?? "",
        row.display_name ?? "",
        row.final_score ?? "",
        row.percentile ?? "",
        bandLabel(row),
        trendText(row),
        row.coverage_pct ?? "",
        (row.geography && row.geography.governorate) || "",
      ].map(csvCell).join(","));
    });
    const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `classification-${state.entityType.toLowerCase()}-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function bindEvents() {
    document.getElementById("applyClassificationFiltersBtn")?.addEventListener("click", () => {
      loadLeaderboard();
    });
    document.getElementById("refreshClassificationBtn")?.addEventListener("click", () => {
      loadLeaderboard();
    });
    document.getElementById("exportClassificationBtn")?.addEventListener("click", () => {
      exportClassificationCsv();
    });

    document.getElementById("autoRefreshCheck")?.addEventListener("change", (event) => {
      if (event.target.checked) {
        startAutoRefresh(300000);
      } else {
        stopAutoRefresh();
      }
    });

    document.querySelectorAll("#classificationTabs button[data-entity-type]").forEach((button) => {
      button.addEventListener("click", () => {
        const selectedType = button.getAttribute("data-entity-type");
        if (!selectedType) {
          return;
        }
        state.entityType = selectedType;
        document.querySelectorAll("#classificationTabs button[data-entity-type]").forEach((item) => {
          item.classList.remove("active");
        });
        button.classList.add("active");
        loadLeaderboard();
      });
    });

    document.getElementById("classificationTableBody")?.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      const button = target.closest("button[data-detail-id]");
      if (!button) {
        return;
      }
      const entityType = button.getAttribute("data-detail-entity");
      const entityId = button.getAttribute("data-detail-id");
      if (!entityType || !entityId) {
        return;
      }
      openDetail(entityType, Number(entityId));
    });

    bindSortableHeaders();
    bindTableKeyboardNav();
    bindKeyboardShortcuts();
  }

  async function init() {
    try {
      updateDefaultPeriod();
      initOfflineDetection();
      loadFiltersFromUrl();
      bindEvents();
      await loadFilters();
      await loadLeaderboard();
    } catch (error) {
      setError(T.initError);
    }
  }

  if (document.getElementById("classificationRoot")) {
    init();
  }
})();
