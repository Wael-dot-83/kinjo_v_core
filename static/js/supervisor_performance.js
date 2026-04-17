(function () {
  function tokenValue() {
    return localStorage.getItem("kinjo_token") || sessionStorage.getItem("kinjo_token") || "";
  }

  function authHeaders() {
    const headers = { "Content-Type": "application/json" };
    const token = tokenValue();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
    return headers;
  }

  async function apiRequest(url) {
    const headers = authHeaders();
    let response = null;

    if (typeof window.fetchWithAuth === "function") {
      response = await window.fetchWithAuth(url, { headers });
      if (!response) {
        throw new Error(
          "\u064a\u062a\u0637\u0644\u0628 \u062a\u0633\u062c\u064a\u0644 \u0627\u0644\u062f\u062e\u0648\u0644"
        );
      }
    } else {
      response = await fetch(url, { headers });
    }

    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(
        payload.detail ||
          "\u062a\u0639\u0630\u0631 \u062a\u062d\u0645\u064a\u0644 \u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a"
      );
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

  function defaultPeriod() {
    const endInput = document.getElementById("supervisorPeriodEnd");
    const startInput = document.getElementById("supervisorPeriodStart");
    if (!endInput || !startInput) {
      return;
    }
    const endDate = new Date();
    const startDate = new Date();
    startDate.setDate(endDate.getDate() - 29);
    endInput.value = formatDateValue(endDate);
    startInput.value = formatDateValue(startDate);
  }

  function showError(message) {
    const box = document.getElementById("supervisorPerformanceError");
    if (!box) {
      return;
    }
    if (message) {
      box.textContent = message;
      box.classList.remove("d-none");
    } else {
      box.textContent = "";
      box.classList.add("d-none");
    }
  }

  const ASPECT_LABELS_AR = {
    attendance_consistency: "\u0627\u062a\u0633\u0627\u0642 \u0627\u0644\u062d\u0636\u0648\u0631",
    report_timeliness:
      "\u0627\u0644\u0627\u0644\u062a\u0632\u0627\u0645 \u0628\u0648\u0642\u062a \u0627\u0644\u062a\u0642\u0631\u064a\u0631",
    report_quality: "\u062c\u0648\u062f\u0629 \u0627\u0644\u062a\u0642\u0627\u0631\u064a\u0631",
    engagement:
      "\u0627\u0644\u062a\u0641\u0627\u0639\u0644 \u0627\u0644\u062a\u0631\u0628\u0648\u064a",
    communication: "\u0627\u0644\u062a\u0648\u0627\u0635\u0644",
    safeguarding: "\u0627\u0644\u0633\u0644\u0627\u0645\u0629",
    overall: "\u0627\u0644\u0623\u062f\u0627\u0621 \u0627\u0644\u0639\u0627\u0645",
  };
  const NO_ASPECT_DATA_TEXT =
    "\u0644\u0627 \u062a\u0648\u062c\u062f \u0628\u064a\u0627\u0646\u0627\u062a \u0643\u0627\u0641\u064a\u0629 \u0644\u0644\u0645\u0624\u0634\u0631\u0627\u062a \u0627\u0644\u062a\u0641\u0635\u064a\u0644\u064a\u0629";
  const INSUFFICIENT_DATA_PREFIX =
    "\u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a \u0627\u0644\u062d\u0627\u0644\u064a\u0629 \u063a\u064a\u0631 \u0643\u0627\u0641\u064a\u0629";
  const FINAL_SCORE_LABEL =
    "\u0627\u0644\u062f\u0631\u062c\u0629 \u0627\u0644\u0646\u0647\u0627\u0626\u064a\u0629";
  const CHART_SERIES_LABEL = "\u0645\u0633\u062a\u0648\u0649 \u0627\u0644\u0623\u062f\u0627\u0621";
  const INVALID_PERIOD_TEXT =
    "\u062a\u0627\u0631\u064a\u062e \u0628\u062f\u0627\u064a\u0629 \u0627\u0644\u0641\u062a\u0631\u0629 \u064a\u062c\u0628 \u0623\u0646 \u064a\u0633\u0628\u0642 \u062a\u0627\u0631\u064a\u062e \u0646\u0647\u0627\u064a\u0629 \u0627\u0644\u0641\u062a\u0631\u0629";
  let performanceChart = null;

  function aspectLabel(key) {
    const normalized = String(key || "").trim();
    if (!normalized) return "\u063a\u064a\u0631 \u0645\u062d\u062f\u062f";
    if (ASPECT_LABELS_AR[normalized]) return ASPECT_LABELS_AR[normalized];
    return "\u0645\u0624\u0634\u0631 \u0625\u0636\u0627\u0641\u064a";
  }

  function renderSummary(data) {
    const finalScoreEl = document.getElementById("supervisorFinalScore");
    const bandLabelEl = document.getElementById("supervisorBandLabel");
    const coverageEl = document.getElementById("supervisorCoverage");
    const sampleSizeEl = document.getElementById("supervisorSampleSize");
    const aspectsListEl = document.getElementById("supervisorAspectsList");
    if (!finalScoreEl || !bandLabelEl || !coverageEl || !sampleSizeEl || !aspectsListEl) {
      return;
    }

    finalScoreEl.textContent =
      data.final_score === null
        ? "\u063a\u064a\u0631 \u0645\u062a\u0627\u062d"
        : formatNumber(data.final_score);
    bandLabelEl.textContent = data.band_label || "\u063a\u064a\u0631 \u0645\u0635\u0646\u0641";
    coverageEl.textContent = `${formatNumber(data.coverage_pct)}%`;
    sampleSizeEl.textContent = String(data.sample_size ?? 0);

    const aspects = data.aspects || {};
    const keys = Object.keys(aspects);
    if (keys.length === 0) {
      aspectsListEl.innerHTML = "";
      const emptyItem = document.createElement("li");
      emptyItem.className = "list-group-item text-muted";
      emptyItem.textContent = NO_ASPECT_DATA_TEXT;
      aspectsListEl.appendChild(emptyItem);
      renderPerformanceChart(data);
      return;
    }

    const fragment = document.createDocumentFragment();
    for (const key of keys) {
      const item = document.createElement("li");
      item.className = "list-group-item d-flex justify-content-between";

      const labelSpan = document.createElement("span");
      labelSpan.textContent = aspectLabel(key);

      const valueSpan = document.createElement("span");
      valueSpan.className = "fw-semibold";
      valueSpan.textContent = formatNumber(aspects[key]);

      item.append(labelSpan, valueSpan);
      fragment.appendChild(item);
    }

    aspectsListEl.innerHTML = "";
    aspectsListEl.appendChild(fragment);
    renderPerformanceChart(data);
  }

  function chartMetricValue(value) {
    const numeric = Number(value);
    if (Number.isNaN(numeric)) return 0;
    return Math.max(0, Math.min(100, numeric));
  }

  function renderPerformanceChart(data) {
    const chartEl = document.getElementById("supervisorPerformanceChart");
    if (!chartEl || typeof window.Chart !== "function") {
      return;
    }

    const aspects = data.aspects || {};
    const keys = Object.keys(aspects);

    const labels = keys.map((key) => aspectLabel(key));
    const values = keys.map((key) => chartMetricValue(aspects[key]));

    if (data.final_score !== null && data.final_score !== undefined) {
      labels.push(FINAL_SCORE_LABEL);
      values.push(chartMetricValue(data.final_score));
    }

    if (values.length === 0) {
      if (performanceChart) {
        performanceChart.destroy();
        performanceChart = null;
      }
      return;
    }

    const chartData = {
      labels,
      datasets: [
        {
          label: CHART_SERIES_LABEL,
          data: values,
          borderColor: "rgba(13, 110, 253, 0.95)",
          backgroundColor: "rgba(13, 110, 253, 0.15)",
          borderWidth: 2,
          pointRadius: 3,
          pointHoverRadius: 5,
          pointBackgroundColor: "rgba(13, 110, 253, 1)",
        },
      ],
    };

    if (performanceChart) {
      performanceChart.data = chartData;
      performanceChart.update();
      return;
    }

    performanceChart = new window.Chart(chartEl, {
      type: "radar",
      data: chartData,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 350 },
        scales: {
          r: {
            beginAtZero: true,
            suggestedMin: 0,
            suggestedMax: 100,
            angleLines: { color: "rgba(33, 37, 41, 0.1)" },
            grid: { color: "rgba(33, 37, 41, 0.15)" },
            pointLabels: {
              color: "#374151",
              font: { size: 12 },
            },
            ticks: {
              stepSize: 20,
              backdropColor: "transparent",
              color: "#6c757d",
            },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label(context) {
                return `${context.formattedValue}`;
              },
            },
          },
        },
      },
    });
  }

  function requestParams() {
    const params = new URLSearchParams();
    const periodStart = document.getElementById("supervisorPeriodStart")?.value;
    const periodEnd = document.getElementById("supervisorPeriodEnd")?.value;
    if (periodStart) params.set("period_start", periodStart);
    if (periodEnd) params.set("period_end", periodEnd);
    return params;
  }

  async function loadSummary() {
    showError("");
    try {
      const params = requestParams();
      if (
        params.has("period_start") &&
        params.has("period_end") &&
        params.get("period_start") > params.get("period_end")
      ) {
        showError(INVALID_PERIOD_TEXT);
        return;
      }
      const data = await apiRequest(`/api/supervisor/performance/summary?${params.toString()}`);
      renderSummary(data);
      if (data.insufficient_data && data.insufficient_reason) {
        showError(`${INSUFFICIENT_DATA_PREFIX}: ${data.insufficient_reason}`);
      }
    } catch (error) {
      showError(
        error.message ||
          "\u062a\u0639\u0630\u0631 \u062a\u062d\u0645\u064a\u0644 \u0645\u0644\u062e\u0635 \u0627\u0644\u0623\u062f\u0627\u0621 \u0627\u0644\u0645\u0647\u0646\u064a."
      );
    }
  }

  function init() {
    if (!document.getElementById("supervisorPerformanceRoot")) {
      return;
    }
    defaultPeriod();
    document.getElementById("supervisorPerformanceLoadBtn")?.addEventListener("click", loadSummary);
    loadSummary();
  }

  init();
})();
