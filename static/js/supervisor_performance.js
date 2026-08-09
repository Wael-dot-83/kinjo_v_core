(function () {
  const IS_EN = document.documentElement.lang === 'en';

  const T = {
    attendance_consistency: IS_EN ? "Attendance Consistency" : "اتساق الحضور",
    report_completion: IS_EN ? "Daily Report Completion" : "اكتمال التقارير اليومية",
    report_timeliness: IS_EN ? "Report Submission Timeliness" : "الالتزام بوقت التقرير",
    "اكتمال_الحضور": IS_EN ? "Attendance Consistency" : "اتساق الحضور",
    "اكتمال_التقارير": IS_EN ? "Daily Report Completion" : "اكتمال التقارير اليومية",
    "الالتزام_بالوقت": IS_EN ? "Report Submission Timeliness" : "الالتزام بوقت التقرير",
    overall: IS_EN ? "Overall Performance" : "الأداء العام",
    unspecified: IS_EN ? "Unspecified Metric" : "مؤشر غير محدد",
    noData: IS_EN ? "No sufficient evaluation data for this period" : "لا توجد بيانات كافية للمؤشرات التفصيلية بهذه الفترة",
    insufficientPrefix: IS_EN ? "Current data is insufficient" : "البيانات الحالية غير كافية",
    invalidPeriod: IS_EN ? "Start date must be before end date" : "تاريخ بداية الفترة يجب أن يسبق تاريخ نهاية الفترة",
    fetchError: IS_EN ? "Failed to load professional performance summary" : "تعذر تحميل ملخص الأداء المهني.",
    chartSeriesLabel: IS_EN ? "Performance Score" : "مستوى الأداء",
    notAvailable: IS_EN ? "N/A" : "غير متاح",
    unclassified: IS_EN ? "Unclassified" : "غير مصنف",
    weight: IS_EN ? "Weight" : "الوزن"
  };

  const ASPECT_METADATA = {
    attendance_consistency: { weight: "40%", icon: "bi-calendar-check" },
    report_completion: { weight: "40%", icon: "bi-journal-check" },
    report_timeliness: { weight: "20%", icon: "bi-clock-history" },
    "اكتمال_الحضور": { weight: "40%", icon: "bi-calendar-check" },
    "اكتمال_التقارير": { weight: "40%", icon: "bi-journal-check" },
    "الالتزام_بالوقت": { weight: "20%", icon: "bi-clock-history" }
  };

  let performanceChart = null;

  function authHeaders() {
    return { "Content-Type": "application/json" };
  }

  async function apiRequest(url) {
    const headers = authHeaders();
    let response = null;
    if (typeof window.fetchWithAuth === "function") {
      response = await window.fetchWithAuth(url, { headers });
    } else {
      response = await fetch(url, { headers });
    }
    if (!response || !response.ok) {
      const payload = await response?.json().catch(() => ({})) || {};
      throw new Error(payload.detail || T.fetchError);
    }
    return response.json();
  }

  function formatNumber(value, digits = 1) {
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

  function defaultPeriod(days = 30) {
    const endInput = document.getElementById("supervisorPeriodEnd");
    const startInput = document.getElementById("supervisorPeriodStart");
    if (!endInput || !startInput) return;
    const endDate = new Date();
    const startDate = new Date();
    startDate.setDate(endDate.getDate() - (days - 1));
    endInput.value = formatDateValue(endDate);
    startInput.value = formatDateValue(startDate);
  }

  function showError(message) {
    const box = document.getElementById("supervisorPerformanceError");
    if (!box) return;
    if (message) {
      box.textContent = message;
      box.classList.remove("d-none");
    } else {
      box.textContent = "";
      box.classList.add("d-none");
    }
  }

  function getBandStyle(bandCode, finalScore) {
    const code = String(bandCode || "").toUpperCase();
    const score = Number(finalScore);

    if (code === "GREEN" || score >= 85) {
      return {
        badgeBg: "bg-success",
        textColor: "text-success",
        borderColor: "border-success",
        progressClass: "bg-success"
      };
    } else if (code === "AMBER" || (score >= 65 && score < 85)) {
      return {
        badgeBg: "bg-warning text-dark",
        textColor: "text-warning-emphasis",
        borderColor: "border-warning",
        progressClass: "bg-warning"
      };
    } else if (code === "RED" || (score > 0 && score < 65)) {
      return {
        badgeBg: "bg-danger",
        textColor: "text-danger",
        borderColor: "border-danger",
        progressClass: "bg-danger"
      };
    }
    return {
      badgeBg: "bg-secondary",
      textColor: "text-secondary",
      borderColor: "border-secondary",
      progressClass: "bg-secondary"
    };
  }

  function renderSummary(data) {
    const finalScoreEl = document.getElementById("supervisorFinalScore");
    const bandLabelEl = document.getElementById("supervisorBandLabel");
    const bandSubtextEl = document.getElementById("supervisorBandSubtext");
    const coverageEl = document.getElementById("supervisorCoverage");
    const coverageBarEl = document.getElementById("supervisorCoverageProgressBar");
    const sampleSizeEl = document.getElementById("supervisorSampleSize");
    const aspectsListEl = document.getElementById("supervisorAspectsList");

    if (!finalScoreEl || !bandLabelEl || !coverageEl || !sampleSizeEl || !aspectsListEl) {
      return;
    }

    const bandStyle = getBandStyle(data.band_code, data.final_score);

    // Final Score Card
    finalScoreEl.textContent = data.final_score === null ? T.notAvailable : `${formatNumber(data.final_score)}%`;
    finalScoreEl.className = `display-6 fw-bold my-1 ${bandStyle.textColor}`;

    // Performance Band Card
    const bandText = IS_EN ? (data.band_label_en || data.band_label || T.unclassified) : (data.band_label || T.unclassified);
    bandLabelEl.textContent = bandText;
    bandLabelEl.className = `display-6 fw-bold my-1 fs-3 ${bandStyle.textColor}`;

    if (bandSubtextEl) {
      bandSubtextEl.textContent = IS_EN ? `Rating code: ${data.band_code || 'N/A'}` : `مستوى التقييم: ${data.band_label || 'غير محدد'}`;
    }

    // Data Coverage
    const coverageVal = Math.min(100, Math.max(0, Number(data.coverage_pct || 0)));
    coverageEl.textContent = `${formatNumber(coverageVal)}%`;
    if (coverageBarEl) {
      coverageBarEl.style.width = `${coverageVal}%`;
      coverageBarEl.className = `progress-bar ${coverageVal >= 80 ? 'bg-success' : coverageVal >= 50 ? 'bg-warning' : 'bg-danger'}`;
    }

    // Sample Size
    sampleSizeEl.textContent = String(data.sample_size ?? 0);

    // Render Aspects List with Progress Bars
    const aspects = data.aspects || {};

    // Deduplicate keys (support both canonical English and Arabic backend keys)
    const normalizedKeys = [];
    const seenNames = new Set();

    Object.keys(aspects).forEach(key => {
      const name = T[key] || key;
      if (!seenNames.has(name)) {
        seenNames.add(name);
        normalizedKeys.push(key);
      }
    });

    if (normalizedKeys.length === 0) {
      aspectsListEl.innerHTML = `<li class="list-group-item text-muted py-3 text-center">${T.noData}</li>`;
      renderPerformanceChart(data, []);
      return;
    }

    const fragment = document.createDocumentFragment();
    for (const key of normalizedKeys) {
      const val = Number(aspects[key] || 0);
      const aspectName = T[key] || key;
      const meta = ASPECT_METADATA[key] || { weight: "20%", icon: "bi-graph-up" };
      const itemBandStyle = getBandStyle(null, val);

      const li = document.createElement("li");
      li.className = "list-group-item border-0 px-0 py-3";

      li.innerHTML = `
        <div class="d-flex justify-content-between align-items-center mb-1">
          <div class="d-flex align-items-center">
            <i class="bi ${meta.icon} me-2 text-primary"></i>
            <span class="fw-semibold text-dark me-2">${aspectName}</span>
            <span class="badge bg-light text-secondary border small">${T.weight}: ${meta.weight}</span>
          </div>
          <span class="fw-bold ${itemBandStyle.textColor}">${formatNumber(val)}%</span>
        </div>
        <div class="progress" style="height: 8px;">
          <div class="progress-bar ${itemBandStyle.progressClass}" role="progressbar" style="width: ${Math.min(100, Math.max(0, val))}%"></div>
        </div>
      `;
      fragment.appendChild(li);
    }

    aspectsListEl.innerHTML = "";
    aspectsListEl.appendChild(fragment);

    // Render Radar Chart
    renderPerformanceChart(data, normalizedKeys);

    // Render Action Guidance Recommendations
    renderActionGuidance(data.action_guidance);

    // Render Explanations Grid
    renderExplanationsGrid(data.indicator_explanations);
  }

  function renderActionGuidance(guidanceList) {
    const card = document.getElementById("supervisorActionGuidanceCard");
    const listEl = document.getElementById("supervisorActionGuidanceList");
    if (!card || !listEl) return;

    if (!guidanceList || guidanceList.length === 0) {
      card.classList.add("d-none");
      return;
    }

    const fragment = document.createDocumentFragment();
    guidanceList.forEach(item => {
      const li = document.createElement("li");
      li.className = "mb-1";
      li.textContent = IS_EN ? (item.en || item.ar) : (item.ar || item.en);
      fragment.appendChild(li);
    });

    listEl.innerHTML = "";
    listEl.appendChild(fragment);
    card.classList.remove("d-none");
  }

  function renderExplanationsGrid(explanations) {
    const grid = document.getElementById("supervisorExplanationsGrid");
    if (!grid) return;

    if (!explanations || explanations.length === 0) {
      grid.innerHTML = `<div class="col-12 text-muted">${T.notAvailable}</div>`;
      return;
    }

    const fragment = document.createDocumentFragment();
    explanations.forEach(item => {
      const col = document.createElement("div");
      col.className = "col-md-4";

      const title = IS_EN ? (item.indicator_en || item.indicator) : (item.indicator || item.indicator_en);
      const desc = IS_EN ? (item.meaning_en || item.meaning) : (item.meaning || item.meaning_en);

      col.innerHTML = `
        <div class="p-3 bg-light rounded-3 h-100 border">
          <div class="fw-semibold text-dark mb-1">
            <i class="bi bi-check-circle-fill me-1 text-success"></i>${title}
          </div>
          <div class="text-muted small">${desc}</div>
        </div>
      `;
      fragment.appendChild(col);
    });

    grid.innerHTML = "";
    grid.appendChild(fragment);
  }

  function renderPerformanceChart(data, aspectKeys) {
    const chartEl = document.getElementById("supervisorPerformanceChart");
    if (!chartEl || typeof window.Chart !== "function") return;

    const aspects = data.aspects || {};
    const labels = aspectKeys.map(k => T[k] || k);
    const values = aspectKeys.map(k => Math.max(0, Math.min(100, Number(aspects[k] || 0))));

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
          label: T.chartSeriesLabel,
          data: values,
          borderColor: "rgba(13, 110, 253, 0.95)",
          backgroundColor: "rgba(13, 110, 253, 0.2)",
          borderWidth: 2,
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBackgroundColor: "rgba(13, 110, 253, 1)"
        }
      ]
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
        animation: { duration: 400 },
        scales: {
          r: {
            beginAtZero: true,
            suggestedMin: 0,
            suggestedMax: 100,
            angleLines: { color: "rgba(33, 37, 41, 0.1)" },
            grid: { color: "rgba(33, 37, 41, 0.15)" },
            pointLabels: {
              color: "#374151",
              font: { size: 12, weight: "600" }
            },
            ticks: {
              stepSize: 20,
              backdropColor: "transparent",
              color: "#6c757d"
            }
          }
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label(context) {
                return `${context.label}: ${context.formattedValue}%`;
              }
            }
          }
        }
      }
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
    const loadBtn = document.getElementById("supervisorPerformanceLoadBtn");
    if (loadBtn) {
      loadBtn.disabled = true;
      const textSpan = loadBtn.querySelector(".btn-text");
      if (textSpan) textSpan.textContent = IS_EN ? "Loading..." : "جاري التحميل...";
    }

    try {
      const params = requestParams();
      if (
        params.has("period_start") &&
        params.has("period_end") &&
        params.get("period_start") > params.get("period_end")
      ) {
        showError(T.invalidPeriod);
        return;
      }
      const data = await apiRequest(`/api/supervisor/performance/summary?${params.toString()}`);
      renderSummary(data);
      if (data.insufficient_data && data.insufficient_reason) {
        showError(`${T.insufficientPrefix}: ${data.insufficient_reason}`);
      }
    } catch (error) {
      showError(error.message || T.fetchError);
    } finally {
      if (loadBtn) {
        loadBtn.disabled = false;
        const textSpan = loadBtn.querySelector(".btn-text");
        if (textSpan) textSpan.textContent = IS_EN ? "Update Summary" : "تحديث الملخص";
      }
    }
  }

  function init() {
    if (!document.getElementById("supervisorPerformanceRoot")) return;

    defaultPeriod(30);

    document.getElementById("supervisorPerformanceLoadBtn")?.addEventListener("click", loadSummary);

    document.querySelectorAll(".preset-btn").forEach(btn => {
      btn.addEventListener("click", function () {
        const days = parseInt(this.getAttribute("data-days"), 10) || 30;
        defaultPeriod(days);
        loadSummary();
      });
    });

    loadSummary();
  }

  init();
})();
