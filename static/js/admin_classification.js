(function () {
  const state = {
    entityType: "KINDERGARTEN",
    trendChart: null,
    filters: null,
  };

  // ui_lang is injected by the template as window.KINJO_LANG (falls back to "ar")
  const lang = window.KINJO_LANG === "en" ? "en" : "ar";

  const T = {
    all:            lang === "en" ? "All"                     : "الكل",
    loading:        lang === "en" ? "Loading classification data..." : "جار تحميل بيانات التصنيف...",
    noData:         lang === "en" ? "Not enough data within the current filters." : "لا توجد بيانات كافية ضمن الفلاتر الحالية.",
    loadError:      lang === "en" ? "Failed to load the leaderboard. Please check filters and retry." : "تعذر تحميل قائمة التصنيف. يرجى التحقق من الفلاتر أو إعادة المحاولة.",
    detailError:    lang === "en" ? "Failed to load detail for the selected entity." : "تعذر تحميل تفاصيل الكيان المحدد.",
    initError:      lang === "en" ? "Failed to initialise the classification page. Please refresh." : "تعذر تهيئة صفحة التصنيف. يرجى تحديث الصفحة.",
    viewDetail:     lang === "en" ? "View Details"            : "عرض التفاصيل",
    unavailable:    lang === "en" ? "N/A"                     : "غير متاح",
    unclassified:   lang === "en" ? "Unclassified"            : "غير مصنف",
    stable:         lang === "en" ? "Stable"                  : "مستقر",
    up:             lang === "en" ? "Rising"                  : "صاعد",
    down:           lang === "en" ? "Falling"                 : "هابط",
    noTrend:        lang === "en" ? "—"                       : "—",
    finalScore:     lang === "en" ? "Final Score"             : "الدرجة النهائية",
    band:           lang === "en" ? "Band"                    : "المجال",
    dataCoverage:   lang === "en" ? "Data Coverage"           : "تغطية البيانات",
    period:         lang === "en" ? "Period"                  : "الفترة",
    periodTo:       lang === "en" ? "to"                      : "إلى",
    chartScore:     lang === "en" ? "Final Score"             : "الدرجة النهائية",
    chartYAxis:     lang === "en" ? "Score"                   : "قيمة المؤشر",
    chartXAxis:     lang === "en" ? "Period"                  : "الفترة",
    governorate:    lang === "en" ? "Governorate"             : "المحافظة",
  };

  function tokenValue() {
    return localStorage.getItem("kinjo_token") || sessionStorage.getItem("kinjo_token") || "";
  }

  async function apiRequest(url) {
    const token = tokenValue();
    const headers = { "Content-Type": "application/json" };
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    const response = await fetch(url, { headers });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || T.loadError);
    }
    return response.json();
  }

  function formatNumber(value, digits = 2) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return "--";
    }
    return Number(value).toFixed(digits);
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
    if (!endInput || !startInput) {
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
      parts.push(`<option value="">${escapeHtml(T.all)}</option>`);
    }
    options.forEach((item) => {
      if (typeof item === "string") {
        parts.push(`<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`);
      } else {
        parts.push(`<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`);
      }
    });
    select.innerHTML = parts.join("");
  }

  function filterParams() {
    const params = new URLSearchParams();
    const periodStart = document.getElementById("periodStart")?.value;
    const periodEnd = document.getElementById("periodEnd")?.value;
    const level = document.getElementById("levelSelect")?.value;
    const sizeMode = document.getElementById("sizeModeSelect")?.value;
    const sizeBand = document.getElementById("sizeBandSelect")?.value;
    const country = document.getElementById("countrySelect")?.value;
    const governorate = document.getElementById("governorateSelect")?.value;
    const city = document.getElementById("citySelect")?.value;
    const area = document.getElementById("areaSelect")?.value;
    const minSampleDays = document.getElementById("minSampleDays")?.value;

    if (periodStart) params.set("period_start", periodStart);
    if (periodEnd) params.set("period_end", periodEnd);
    if (level) params.set("level", level);
    if (sizeMode) params.set("size_mode", sizeMode);
    if (sizeBand) params.set("size_band", sizeBand);
    if (country) params.set("country", country);
    if (governorate) params.set("governorate", governorate);
    if (city) params.set("city", city);
    if (area) params.set("area", area);
    if (minSampleDays) params.set("min_sample_days", minSampleDays);
    return params;
  }

  function setLoading(isLoading) {
    const loading = document.getElementById("classificationLoading");
    if (!loading) {
      return;
    }
    loading.classList.toggle("d-none", !isLoading);
  }

  function setError(message) {
    const errorBox = document.getElementById("classificationError");
    if (!errorBox) {
      return;
    }
    if (message) {
      errorBox.textContent = message;
      errorBox.classList.remove("d-none");
    } else {
      errorBox.textContent = "";
      errorBox.classList.add("d-none");
    }
  }

  function setEmpty(isEmpty) {
    const empty = document.getElementById("classificationEmpty");
    if (!empty) {
      return;
    }
    empty.classList.toggle("d-none", !isEmpty);
  }

  function bandBadgeClass(code) {
    if (code === "GREEN") return "bg-success";
    if (code === "AMBER") return "bg-warning text-dark";
    if (code === "RED") return "bg-danger";
    return "bg-secondary";
  }

  // Compare against stable direction codes emitted by the backend
  function trendText(row) {
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
    const percentile = row.percentile === null ? "--" : `${formatNumber(row.percentile)}%`;
    const coverage = `${formatNumber(row.coverage_pct)}%`;
    const rank = row.rank === null ? "--" : row.rank;
    // Fix 1: escape display_name and insufficient_reason to prevent XSS
    const info =
      row.insufficient_data && row.insufficient_reason
        ? `<div class="small text-danger">${escapeHtml(row.insufficient_reason)}</div>`
        : "";
    const disabled = row.insufficient_data ? "disabled" : "";
    const govText = (row.geography && row.geography.governorate)
      ? `<div class="small text-muted">${escapeHtml(T.governorate)}: ${escapeHtml(row.geography.governorate)}</div>`
      : "";

    return `
      <tr>
        <td>${rank}</td>
        <td>
          <div class="fw-semibold">${escapeHtml(row.display_name)}</div>
          ${govText}${info}
        </td>
        <td>${score}</td>
        <td>${percentile}</td>
        <td><span class="badge ${bandBadgeClass(row.band_code)}">${escapeHtml(row.band_label || T.unclassified)}</span></td>
        <td>${trendText(row)}</td>
        <td>${coverage}</td>
        <td>
          <button class="btn btn-sm btn-outline-primary" data-detail-entity="${escapeHtml(row.entity_type)}" data-detail-id="${row.entity_id}" ${disabled}>
            ${escapeHtml(T.viewDetail)}
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

  function renderRows(rows) {
    const tbody = document.getElementById("classificationTableBody");
    if (!tbody) {
      return;
    }
    if (!rows || rows.length === 0) {
      tbody.innerHTML = "";
      setEmpty(true);
      return;
    }
    setEmpty(false);
    tbody.innerHTML = rows.map((row) => tableRowHtml(row)).join("");
  }

  async function loadLeaderboard() {
    setLoading(true);
    setError("");
    try {
      const params = filterParams();
      const endpoint = endpointForEntityType();
      const data = await apiRequest(`${endpoint}?${params.toString()}`);
      renderRows(data.rows || []);
    } catch (error) {
      setError(T.loadError);
      renderRows([]);
    } finally {
      setLoading(false);
    }
  }

  function drawTrendChart(points) {
    const canvas = document.getElementById("classificationTrendChart");
    if (!canvas || typeof window.Chart === "undefined") {
      return;
    }
    if (state.trendChart) {
      state.trendChart.destroy();
    }
    const labels = points.map((point) => `${point.period_start} ← ${point.period_end}`);
    const values = points.map((point) => point.final_score ?? null);
    state.trendChart = new window.Chart(canvas, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: T.chartScore,
            data: values,
            borderColor: "#1F5E47",
            backgroundColor: "rgba(31, 94, 71, 0.15)",
            borderWidth: 2,
            tension: 0.25,
            fill: true,
            spanGaps: true,
          },
        ],
      },
      options: {
        responsive: true,
        scales: {
          y: {
            beginAtZero: true,
            max: 100,
            title: { display: true, text: T.chartYAxis },
          },
          x: { title: { display: true, text: T.chartXAxis } },
        },
      },
    });
  }

  function detailSummaryHtml(detail) {
    return `
      <div class="row g-3">
        <div class="col-md-3">
          <div class="border rounded p-3">
            <div class="text-muted small">${escapeHtml(T.finalScore)}</div>
            <div class="h4 mb-0">${detail.final_score === null ? escapeHtml(T.unavailable) : formatNumber(detail.final_score)}</div>
          </div>
        </div>
        <div class="col-md-3">
          <div class="border rounded p-3">
            <div class="text-muted small">${escapeHtml(T.band)}</div>
            <div class="h4 mb-0">${escapeHtml(detail.band_label || T.unclassified)}</div>
          </div>
        </div>
        <div class="col-md-3">
          <div class="border rounded p-3">
            <div class="text-muted small">${escapeHtml(T.dataCoverage)}</div>
            <div class="h4 mb-0">${formatNumber(detail.coverage_pct)}%</div>
          </div>
        </div>
        <div class="col-md-3">
          <div class="border rounded p-3">
            <div class="text-muted small">${escapeHtml(T.period)}</div>
            <div class="small fw-semibold">${escapeHtml(detail.period_start)} ${escapeHtml(T.periodTo)} ${escapeHtml(detail.period_end)}</div>
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

      titleEl.textContent = `${detail.display_name}`;
      summaryEl.innerHTML = detailSummaryHtml(detail);

      const aspects = detail.aspects || {};
      const aspectRows = Object.keys(aspects).map(
        (name) =>
          `<li class="list-group-item d-flex justify-content-between"><span>${escapeHtml(name)}</span><span class="fw-semibold">${formatNumber(aspects[name])}</span></li>`
      );
      aspectsEl.innerHTML = aspectRows.join("");

      const actions = detail.action_guidance || [];
      actionsEl.innerHTML = actions.map((action) => `<li>${escapeHtml(action)}</li>`).join("");

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

  function bindEvents() {
    document.getElementById("applyClassificationFiltersBtn")?.addEventListener("click", () => {
      loadLeaderboard();
    });
    document.getElementById("refreshClassificationBtn")?.addEventListener("click", () => {
      loadLeaderboard();
    });

    document.querySelectorAll("#classificationTabs button[data-entity-type]").forEach((button) => {
      button.addEventListener("click", () => {
        const selectedType = button.getAttribute("data-entity-type");
        if (!selectedType) {
          return;
        }
        state.entityType = selectedType;
        document
          .querySelectorAll("#classificationTabs button[data-entity-type]")
          .forEach((item) => {
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
  }

  async function init() {
    try {
      updateDefaultPeriod();
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
