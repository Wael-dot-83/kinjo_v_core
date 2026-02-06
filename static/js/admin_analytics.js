document.addEventListener("DOMContentLoaded", function () {
  // Set default date range (Current Month)
  const today = new Date();
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);

  // Format dates as YYYY-MM-DD
  const formatDate = (d) => d.toISOString().split("T")[0];

  const startInput = document.getElementById("periodStart");
  const endInput = document.getElementById("periodEnd");

  if (startInput && endInput) {
    startInput.value = formatDate(firstDay);
    endInput.value = formatDate(today);

    // Initial load
    loadAdminAnalytics();
  }

  // Setup Report Form Date Inputs
  const reportStart = document.getElementById("startDate");
  const reportEnd = document.getElementById("endDate");
  if (reportStart && reportEnd) {
    reportStart.value = formatDate(firstDay);
    reportEnd.value = formatDate(today);
  }
});

let governanceChart = null;
let trendChartInstance = null;
let governorateTableSorter = null;

async function loadAdminAnalytics() {
  const start = document.getElementById("periodStart").value;
  const end = document.getElementById("periodEnd").value;
  const btn = document.getElementById("refreshBtn");

  if (!start || !end) {
    showToast("يرجى تحديد تاريخ البداية والنهاية", "warning");
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="bi bi-arrow-clockwise me-1"></i>جاري التحديث...';
  }

  showSkeletonLoaders();

  try {
    const response = await fetchWithAuth(
      `/api/analytics/dashboard-data?period_start=${start}&period_end=${end}`,
    );
    if (!response) return;

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const errorMessage =
        errorData.detail || `HTTP ${response.status}: ${response.statusText}`;
      throw new Error(errorMessage);
    }

    const data = await response.json();

    // Update all dashboard components
    updateNetworkSummary(data.network_summary);
    updateTrendCharts(data.attendance_trend, data.incident_trend);
    updateGovernorateBreakdown(data.governorate_breakdown);
    updateRiskRadar(data.risk_radar);
    updateGovernanceChart(
      data.governance_distribution.green,
      data.governance_distribution.amber,
      data.governance_distribution.red,
    );

    // Load comparative analysis
    await loadComparativeAnalysis(start, end);

    showToast("تم تحديث البيانات بنجاح", "success");
  } catch (error) {
    console.error("Analytics load error:", error);
    const userMessage = error.message.includes("Invalid date range")
      ? "يرجى التأكد من صحة نطاق التاريخ المحدد"
      : error.message.includes("500")
        ? "خطأ في الخادم. يرجى المحاولة لاحقاً"
        : "حدث خطأ في تحميل البيانات. يرجى المحاولة مرة أخرى.";
    showToast(userMessage, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="bi bi-arrow-clockwise me-1"></i>تحديث';
    }
    hideSkeletonLoaders();
  }
}

function showSkeletonLoaders() {
  // Show skeleton for KPI cards
  document
    .querySelectorAll(
      "#totalKg, #totalChildren, #avgAttendance, #incidentRate, #enrollmentRate",
    )
    .forEach((el) => {
      el.innerHTML = '<div class="skeleton-text w-50"></div>';
    });
  document.querySelector("#enrollmentRateBar").style.width = "0%";
  document.querySelector("#kpiKgGrowth").innerHTML =
    '<div class="skeleton-text w-75"></div>';

  // Show skeleton for governorate table
  const tbody = document.getElementById("governorateTableBody");
  if (tbody) {
    tbody.innerHTML = `
            <tr class="skeleton-row">
                <td><div class="skeleton-text w-75"></div></td>
                <td><div class="skeleton-text w-50 mx-auto"></div></td>
                <td><div class="skeleton-text w-50 mx-auto"></div></td>
                <td><div class="skeleton-text w-50 mx-auto"></div></td>
                <td><div class="skeleton-text w-50 mx-auto"></div></td>
                <td><div class="skeleton-text w-75 mx-auto"></div></td>
            </tr>
            <tr class="skeleton-row">
                <td><div class="skeleton-text w-75"></div></td>
                <td><div class="skeleton-text w-50 mx-auto"></div></td>
                <td><div class="skeleton-text w-50 mx-auto"></div></td>
                <td><div class="skeleton-text w-50 mx-auto"></div></td>
                <td><div class="skeleton-text w-50 mx-auto"></div></td>
                <td><div class="skeleton-text w-75 mx-auto"></div></td>
            </tr>
            <tr class="skeleton-row">
                <td><div class="skeleton-text w-75"></div></td>
                <td><div class="skeleton-text w-50 mx-auto"></div></td>
                <td><div class="skeleton-text w-50 mx-auto"></div></td>
                <td><div class="skeleton-text w-50 mx-auto"></div></td>
                <td><div class="skeleton-text w-50 mx-auto"></div></td>
                <td><div class="skeleton-text w-75 mx-auto"></div></td>
            </tr>
        `;
  }

  // Show skeleton for risk radar
  const riskList = document.getElementById("riskList");
  if (riskList) {
    riskList.innerHTML = `
            <li class="list-group-item d-flex justify-content-between align-items-center skeleton-row">
                <div><div class="skeleton-text w-75 mb-1"></div><div class="skeleton-text w-50"></div></div>
                <div class="skeleton-text w-25"></div>
            </li>
            <li class="list-group-item d-flex justify-content-between align-items-center skeleton-row">
                <div><div class="skeleton-text w-75 mb-1"></div><div class="skeleton-text w-50"></div></div>
                <div class="skeleton-text w-25"></div>
            </li>
            <li class="list-group-item d-flex justify-content-between align-items-center skeleton-row">
                <div><div class="skeleton-text w-75 mb-1"></div><div class="skeleton-text w-50"></div></div>
                <div class="skeleton-text w-25"></div>
            </li>
        `;
  }

  // Show skeleton for comparative analysis
  document.getElementById("topPerformersList").innerHTML = `
        <div class="list-group-item text-muted text-center py-3 skeleton-row">
            <div class="skeleton-text w-75 mx-auto mb-2"></div>
            <div class="skeleton-text w-50 mx-auto"></div>
        </div>
        <div class="list-group-item text-muted text-center py-3 skeleton-row">
            <div class="skeleton-text w-75 mx-auto mb-2"></div>
            <div class="skeleton-text w-50 mx-auto"></div>
        </div>
    `;
  document.getElementById("lowPerformersList").innerHTML = `
        <div class="list-group-item text-muted text-center py-3 skeleton-row">
            <div class="skeleton-text w-75 mx-auto mb-2"></div>
            <div class="skeleton-text w-50 mx-auto"></div>
        </div>
        <div class="list-group-item text-muted text-center py-3 skeleton-row">
            <div class="skeleton-text w-75 mx-auto mb-2"></div>
            <div class="skeleton-text w-50 mx-auto"></div>
        </div>
    `;

  // Clear charts if they exist
  if (trendChartInstance) trendChartInstance.destroy();
  if (governanceChart) governanceChart.destroy();
}

function hideSkeletonLoaders() {
  // KPI cards are updated by updateNetworkSummary which will overwrite skeletons
  // Governorate table is updated by updateGovernorateBreakdown
  // Risk radar is updated by updateRiskRadar
  // Comparative analysis is updated by loadComparativeAnalysis
  // Charts are re-initialized when data loads.
}

function updateNetworkSummary(summary) {
  if (!summary) {
    console.warn("No network summary data provided");
    return;
  }

  // Update KPI cards with proper formatting
  safeSetText(
    "totalKg",
    summary.total_kindergartens?.toLocaleString("ar-JO") || "0",
  );

  const childrenCount = summary.total_children || 0;
  safeSetText("totalChildren", childrenCount.toLocaleString("ar-JO"));

  const attendanceRate = summary.attendance_rate || 0;
  safeSetText("avgAttendance", attendanceRate.toFixed(1) + "%");

  const incidentRate = summary.incident_rate || 0;
  safeSetText("incidentRate", incidentRate.toFixed(2));

  const enrollmentRate = summary.enrollment_rate || 0;
  safeSetText("enrollmentRate", enrollmentRate.toFixed(1) + "%");

  // Update progress bars
  const enrollmentBar = document.getElementById("enrollmentRateBar");
  if (enrollmentBar) {
    enrollmentBar.style.width = Math.min(enrollmentRate, 100) + "%";
    enrollmentBar.className = `progress-bar ${enrollmentRate > 90 ? "bg-success" : enrollmentRate > 70 ? "bg-info" : "bg-warning"}`;
  }

  // Add trend indicators (mock data for now - in real implementation, calculate from previous period)
  updateTrendIndicators(summary);
}

function updateTrendIndicators(summary) {
  // Mock trend calculation - in production, compare with previous period data
  const attendanceTrend = document.getElementById("attendanceTrend");
  const incidentTrend = document.getElementById("incidentTrend");
  const kgGrowth = document.getElementById("kpiKgGrowth");

  if (attendanceTrend) {
    const trend =
      summary.attendance_rate > 85
        ? "up"
        : summary.attendance_rate > 75
          ? "stable"
          : "down";
    const trendIcon =
      trend === "up"
        ? "bi-arrow-up-short text-success"
        : trend === "down"
          ? "bi-arrow-down-short text-danger"
          : "bi-dash text-warning";
    const trendText =
      trend === "up" ? "في تحسن" : trend === "down" ? "في تراجع" : "مستقر";
    attendanceTrend.innerHTML = `<i class="bi ${trendIcon} me-1"></i>${trendText}`;
  }

  if (incidentTrend) {
    const trend =
      summary.incident_rate < 0.5
        ? "down"
        : summary.incident_rate > 1.0
          ? "up"
          : "stable";
    const trendIcon =
      trend === "down"
        ? "bi-arrow-down-short text-success"
        : trend === "up"
          ? "bi-arrow-up-short text-danger"
          : "bi-dash text-warning";
    const trendText =
      trend === "down" ? "في تحسن" : trend === "up" ? "في ارتفاع" : "مستقر";
    incidentTrend.innerHTML = `<i class="bi ${trendIcon} me-1"></i>${trendText}`;
  }

  if (kgGrowth) {
    // Mock growth data - in production, calculate from previous period
    const growth = Math.random() * 10 - 2; // Random between -2% and +8%
    const growthClass = growth > 0 ? "text-success" : "text-danger";
    const growthIcon = growth > 0 ? "bi-arrow-up-short" : "bi-arrow-down-short";
    kgGrowth.innerHTML = `<i class="bi ${growthIcon}"></i> ${Math.abs(growth).toFixed(1)}%`;
    kgGrowth.className = growthClass;
  }
}

function updateTrendCharts(attendanceData, incidentData) {
  const ctx = document.getElementById("trendChart");
  if (!ctx) return;

  // Show loading overlay
  const overlay = document.getElementById("trendChartOverlay");
  if (overlay) overlay.classList.remove("d-none");

  if (trendChartInstance) {
    trendChartInstance.destroy();
  }

  // Default to attendance data
  let currentData = attendanceData;
  let currentLabel = "عدد الحضور";
  let currentColor = "#198754";
  let currentBgColor = "rgba(25, 135, 84, 0.1)";

  trendChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: currentData.map((d) => formatDateForDisplay(d.date)),
      datasets: [
        {
          label: currentLabel,
          data: currentData.map((d) => d.value),
          borderColor: currentColor,
          backgroundColor: currentBgColor,
          yAxisID: "y",
          fill: true,
          tension: 0.4,
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBackgroundColor: currentColor,
          pointBorderColor: "#fff",
          pointBorderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: {
          display: true,
          position: "top",
          labels: {
            usePointStyle: true,
            padding: 20,
            font: {
              size: 12,
              weight: "bold",
            },
          },
        },
        tooltip: {
          mode: "index",
          intersect: false,
          backgroundColor: "rgba(0,0,0,0.8)",
          titleColor: "#fff",
          bodyColor: "#fff",
          borderColor: currentColor,
          borderWidth: 1,
          cornerRadius: 8,
          displayColors: true,
          callbacks: {
            title: function (context) {
              return "تاريخ: " + context[0].label;
            },
            label: function (context) {
              return (
                context.dataset.label +
                ": " +
                context.parsed.y.toLocaleString("ar-JO")
              );
            },
          },
        },
      },
      scales: {
        y: {
          type: "linear",
          display: true,
          position: "left",
          beginAtZero: true,
          title: {
            display: true,
            text: currentLabel,
            font: {
              size: 14,
              weight: "bold",
            },
          },
          grid: {
            color: "rgba(0,0,0,0.05)",
          },
          ticks: {
            callback: function (value) {
              return value.toLocaleString("ar-JO");
            },
          },
        },
        x: {
          title: {
            display: true,
            text: "التاريخ",
            font: {
              size: 14,
              weight: "bold",
            },
          },
          grid: {
            display: false,
          },
        },
      },
      elements: {
        point: {
          hoverBorderWidth: 3,
        },
      },
    },
  });

  // Setup radio button event listeners
  setupTrendControls(attendanceData, incidentData);

  // Hide loading overlay
  setTimeout(() => {
    if (overlay) overlay.classList.add("d-none");
  }, 500);
}

function setupTrendControls(attendanceData, incidentData) {
  const attendanceRadio = document.getElementById("attendanceTrend");
  const incidentsRadio = document.getElementById("incidentsTrend");

  if (attendanceRadio && incidentsRadio) {
    attendanceRadio.addEventListener("change", () => {
      if (attendanceRadio.checked) {
        updateTrendChart("attendance");
      }
    });

    incidentsRadio.addEventListener("change", () => {
      if (incidentsRadio.checked) {
        updateTrendChart("incidents");
      }
    });
  }
}

function updateTrendChart(type) {
  if (!trendChartInstance) return;

  const attendanceRadio = document.getElementById("attendanceTrend");
  const incidentsRadio = document.getElementById("incidentsTrend");

  if (type === "attendance") {
    if (attendanceRadio) attendanceRadio.checked = true;
    // Update chart with attendance data (would need to store original data)
    trendChartInstance.data.datasets[0].label = "عدد الحضور";
    trendChartInstance.data.datasets[0].borderColor = "#198754";
    trendChartInstance.data.datasets[0].backgroundColor =
      "rgba(25, 135, 84, 0.1)";
    trendChartInstance.data.datasets[0].pointBackgroundColor = "#198754";
  } else if (type === "incidents") {
    if (incidentsRadio) incidentsRadio.checked = true;
    trendChartInstance.data.datasets[0].label = "عدد الحوادث";
    trendChartInstance.data.datasets[0].borderColor = "#fd7e14";
    trendChartInstance.data.datasets[0].backgroundColor =
      "rgba(253, 126, 20, 0.1)";
    trendChartInstance.data.datasets[0].pointBackgroundColor = "#fd7e14";
  }

  trendChartInstance.options.scales.y.title.text =
    trendChartInstance.data.datasets[0].label;
  trendChartInstance.update("active");
}

function formatDateForDisplay(dateStr) {
  try {
    const date = new Date(dateStr);
    return date.toLocaleDateString("ar-JO", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch (e) {
    return dateStr;
  }
}

function updateRiskRadar(riskData) {
  const list = document.getElementById("riskList");
  const container = document.getElementById("riskListContainer");
  const noData = document.getElementById("noRiskData");

  if (!list || !container || !noData) return;

  // Clear existing content
  list.innerHTML = "";

  if (!riskData || riskData.length === 0) {
    container.classList.add("d-none");
    noData.classList.remove("d-none");
    return;
  }

  // Show risk data
  container.classList.remove("d-none");
  noData.classList.add("d-none");

  // Sort by risk score descending
  riskData.sort((a, b) => (b.risk_score || 0) - (a.risk_score || 0));

  riskData.forEach((item) => {
    const li = document.createElement("li");
    li.className =
      "list-group-item d-flex justify-content-between align-items-center border-0 py-3";

    const riskScore = item.risk_score || 0;
    const riskColor =
      riskScore >= 80
        ? "danger"
        : riskScore >= 60
          ? "warning"
          : riskScore >= 40
            ? "orange"
            : "success";

    li.innerHTML = `
            <div class="flex-grow-1">
                <div class="d-flex align-items-center mb-1">
                    <span class="fw-bold text-dark me-2">${item.name || "غير محدد"}</span>
                    <small class="badge bg-${riskColor} text-white">${riskScore}% خطر</small>
                </div>
                <small class="text-muted d-block">${item.kindergarten || "غير محدد"}</small>
                <div class="small text-danger mt-1">${item.reason || "سبب غير محدد"}</div>
            </div>
            <div class="text-end">
                <div class="progress" style="width: 60px; height: 6px;">
                    <div class="progress-bar bg-${riskColor}" style="width: ${riskScore}%"></div>
                </div>
            </div>
        `;

    // Add click handler for drill-down
    li.style.cursor = "pointer";
    li.addEventListener("click", () => {
      if (item.kindergarten_id) {
        window.location.href = `/admin/analytics/drilldown/KINDERGARTEN/${item.kindergarten_id}`;
      }
    });

    list.appendChild(li);
  });
}

function updateGovernorateBreakdown(breakdownData) {
  const table = document.getElementById("governorateTable");
  const tbody = document.getElementById("governorateTableBody");
  if (!tbody || !table) return;

  tbody.innerHTML = "";

  if (breakdownData.length === 0) {
    tbody.innerHTML =
      '<tr><td colspan="6" class="text-center text-muted">لا توجد بيانات للفترة المحددة</td></tr>';
    if (governorateTableSorter) {
      governorateTableSorter.destroy();
      governorateTableSorter = null;
    }
    return;
  }

  let green = 0,
    amber = 0,
    red = 0;

  breakdownData.forEach((row) => {
    const tr = document.createElement("tr");
    tr.setAttribute("data-gov-id", row.governorate);
    tr.style.cursor = "pointer";
    tr.title = `انقر لعرض تفاصيل محافظة ${row.governorate}`;
    tr.addEventListener("click", () => {
      window.location.href = `/admin/analytics/drilldown/GOVERNORATE/${row.governorate}`;
    });
    tr.innerHTML = `
            <td class="fw-bold">${row.governorate}</td>
            <td class="text-center">${row.kindergarten_count}</td>
            <td class="text-center">${row.children_count}</td>
            <td class="text-center" data-sort="${row.attendance_rate}">
                <span class="badge ${row.attendance_rate >= 85 ? "bg-success-subtle text-success-emphasis" : "bg-warning-subtle text-warning-emphasis"}">
                    ${row.attendance_rate.toFixed(1)}%
                </span>
            </td>
            <td class="text-center" data-sort="${row.incident_rate}">${row.incident_rate.toFixed(2)}</td>
            <td class="text-center" data-sort="${row.governance_score}">
                <div class="d-flex align-items-center justify-content-center">
                    <span class="fw-bold me-2">${row.governance_score.toFixed(1)}</span>
                    <div class="progress" style="width: 50px; height: 4px;" role="progressbar" aria-valuenow="${row.governance_score}" aria-valuemin="0" aria-valuemax="100">
                        <div class="progress-bar ${getScoreColor(row.governance_score)}" style="width: ${row.governance_score}%"></div>
                    </div>
                </div>
            </td>
        `;
    tbody.appendChild(tr);

    if (row.governance_score >= 80) green++;
    else if (row.governance_score >= 60) amber++;
    else if (row.governance_score > 0) red++;
  });

  updateGovernanceChart(green, amber, red);

  // Initialize or refresh sorter
  if (governorateTableSorter) {
    governorateTableSorter.update();
  } else {
    governorateTableSorter = new Tablesort(table);
  }
}

async function loadComparativeAnalysis(start, end) {
  const topList = document.getElementById("topPerformersList");
  const lowList = document.getElementById("lowPerformersList");
  if (!topList || !lowList) return;

  topList.innerHTML =
    '<div class="list-group-item text-center text-muted small">Loading...</div>';
  lowList.innerHTML =
    '<div class="list-group-item text-center text-muted small">Loading...</div>';

  try {
    const [topResponse, lowResponse] = await Promise.all([
      fetchWithAuth(
        `/api/analytics/rankings/governance_score?top_n=5&period_start=${start}&period_end=${end}`,
      ),
      fetchWithAuth(
        `/api/analytics/rankings/governance_score?top_n=5&bottom=true&period_start=${start}&period_end=${end}`,
      ),
    ]);

    if (!topResponse || !lowResponse) return;

    const topData = await topResponse.json();
    const lowData = await lowResponse.json();

    renderRankingList(topList, topData.rankings, "top");
    renderRankingList(lowList, lowData.rankings, "low");
  } catch (error) {
    console.error("Comparative analysis error:", error);
    topList.innerHTML =
      '<div class="list-group-item text-danger small">Failed to load rankings.</div>';
    lowList.innerHTML =
      '<div class="list-group-item text-danger small">Failed to load rankings.</div>';
  }
}

function renderRankingList(element, rankings, type) {
  element.innerHTML = "";

  if (!rankings || rankings.length === 0) {
    const emptyItem = document.createElement("div");
    emptyItem.className =
      "list-group-item text-muted text-center py-4 border-0";
    emptyItem.innerHTML = `
            <i class="bi bi-info-circle fs-2 mb-2 ${type === "top" ? "text-success" : "text-danger"}"></i>
            <div class="small">لا توجد بيانات متاحة لهذه الفترة</div>
        `;
    element.appendChild(emptyItem);
    return;
  }

  rankings.forEach((item, index) => {
    const div = document.createElement("div");
    div.className =
      "list-group-item d-flex justify-content-between align-items-center border-0 py-3";

    const rank = index + 1;
    const score = item.value || 0;
    const scoreColor = type === "top" ? "text-success" : "text-danger";
    const rankIcon = type === "top" ? "bi-trophy" : "bi-exclamation-triangle";

    div.innerHTML = `
            <div class="d-flex align-items-center flex-grow-1">
                <div class="rank-circle ${type === "top" ? "bg-success" : "bg-danger"} text-white rounded-circle d-flex align-items-center justify-content-center me-3" style="width: 32px; height: 32px; font-size: 14px; font-weight: bold;">
                    ${rank}
                </div>
                <div class="flex-grow-1">
                    <a href="/kindergartens/${item.kindergarten_id}" class="fw-bold text-dark text-decoration-none d-block" title="انقر لعرض تفاصيل الروضة">
                        ${item.kindergarten_name || "غير محدد"}
                    </a>
                    <small class="text-muted d-block">
                        <i class="bi bi-geo-alt me-1"></i>${item.governorate || "غير محدد"}
                    </small>
                </div>
            </div>
            <div class="text-end">
                <div class="d-flex align-items-center">
                    <span class="badge ${type === "top" ? "bg-success-subtle text-success-emphasis" : "bg-danger-subtle text-danger-emphasis"} rounded-pill me-2 fs-6">
                        ${score.toFixed(1)}
                    </span>
                    <i class="bi ${rankIcon} ${scoreColor}"></i>
                </div>
            </div>
        `;

    // Add hover effect
    div.addEventListener("mouseenter", () => {
      div.style.backgroundColor =
        type === "top" ? "rgba(25, 135, 84, 0.05)" : "rgba(220, 53, 69, 0.05)";
    });

    div.addEventListener("mouseleave", () => {
      div.style.backgroundColor = "";
    });

    element.appendChild(div);
  });
}

function updateGovernanceChart(green, amber, red) {
  const ctx = document.getElementById("governancePieChart");
  if (!ctx) return;

  safeSetText("countGreen", green);
  safeSetText("countAmber", amber);
  safeSetText("countRed", red);

  if (governanceChart) governanceChart.destroy();

  governanceChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["متميز", "متوسط", "يحتاج تحسين"],
      datasets: [
        {
          data: [green, amber, red],
          backgroundColor: ["#198754", "#ffc107", "#dc3545"],
          borderWidth: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      cutout: "70%",
    },
  });
}

function refreshGovernorateData() {
  const start = document.getElementById("periodStart").value;
  const end = document.getElementById("periodEnd").value;

  if (!start || !end) {
    showToast("يرجى تحديد تاريخ البداية والنهاية", "warning");
    return;
  }

  // Show loading state
  const tbody = document.getElementById("governorateTableBody");
  if (tbody) {
    tbody.innerHTML =
      '<tr><td colspan="6" class="text-center py-4"><div class="spinner-border spinner-border-sm text-primary" role="status"></div><span class="ms-2">جاري تحديث البيانات...</span></td></tr>';
  }

  // Fetch updated data
  fetchWithAuth(
    `/api/analytics/governorate-breakdown?period_start=${start}&period_end=${end}`,
  )
    .then((response) => (response ? response.json() : null))
    .then((data) => {
      if (data) {
        updateGovernorateBreakdown(data);
        showToast("تم تحديث بيانات المحافظات", "success");
      }
    })
    .catch((error) => {
      console.error("Governorate data refresh error:", error);
      showToast("فشل في تحديث بيانات المحافظات", "error");
    });
}

function safeSetText(id, text) {
  const el = document.getElementById(id);
  if (el) el.innerText = text;
}

function showToast(message, type = "info") {
  const toastContainer =
    document.getElementById("toastContainer") || document.createElement("div");
  toastContainer.id = "toastContainer";
  toastContainer.className =
    "toast-container position-fixed bottom-0 end-0 p-3";
  document.body.appendChild(toastContainer);

  const toastEl = document.createElement("div");
  toastEl.className = `toast align-items-center text-white bg-${type} border-0`;
  toastEl.setAttribute("role", "alert");
  toastEl.setAttribute("aria-live", "assertive");
  toastEl.setAttribute("aria-atomic", "true");
  toastEl.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
  toastContainer.appendChild(toastEl);
  const toast = new bootstrap.Toast(toastEl);
  toast.show();
}

// Auth Helper
// fetchWithAuth is now defined in auth.js

document.addEventListener("DOMContentLoaded", function () {
  const exportForm = document.getElementById("exportForm");
  if (exportForm) {
    exportForm.addEventListener("submit", handleExport);
  }

  // Set initial dates for export modal
  const today = new Date();
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
  const formatDate = (d) => d.toISOString().split("T")[0];

  document.getElementById("exportStartDate").value = formatDate(firstDay);
  document.getElementById("exportEndDate").value = formatDate(today);
});

async function handleExport(event) {
  event.preventDefault();

  const reportType = document.getElementById("exportReportType").value;
  const exportFormat = document.getElementById("exportFormat").value;
  const startDate = document.getElementById("exportStartDate").value;
  const endDate = document.getElementById("exportEndDate").value;
  const exportBtn = document.querySelector(
    '#exportModal button[type="submit"]',
  );
  const exportSpinner = document.getElementById("exportSpinner");

  if (!reportType) {
    showToast("Please select a report type.", "warning");
    return;
  }

  exportBtn.disabled = true;
  exportSpinner.classList.remove("d-none");

  const url = "/api/analytics/export";
  try {
    const response = await fetchWithAuth(url, {
      method: "POST",
      body: JSON.stringify({
        report_type: reportType,
        export_format: exportFormat.toUpperCase(),
        filters: {
          period_start: startDate,
          period_end: endDate,
        },
      }),
    });

    if (!response) return; // fetchWithAuth handles 401 redirect

    // Check for job ID if async export
    // For now, assuming direct file download as per current backend /export
    const blob = await response.blob();
    const contentDisposition = response.headers.get("Content-Disposition");
    let filename = `report_${reportType}_${startDate}_${endDate}.csv`;
    if (contentDisposition) {
      const filenameMatch = contentDisposition.match(/filename="(.+)"/);
      if (filenameMatch && filenameMatch[1]) {
        filename = filenameMatch[1];
      }
    }

    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(downloadUrl);

    showToast("Report exported successfully!", "success");
    const exportModal = bootstrap.Modal.getInstance(
      document.getElementById("exportModal"),
    );
    if (exportModal) exportModal.hide();
  } catch (e) {
    console.error("Export failed:", e);
    showToast("Failed to export report. Please try again.", "error");
  } finally {
    exportBtn.disabled = false;
    exportSpinner.classList.add("d-none");
  }
}

function getScoreColor(score) {
  if (score >= 80) return "bg-success";
  else if (score >= 60) return "bg-warning";
  return "bg-danger";
}
