// @ts-nocheck
/**
 * KinJo Analytics Module
 * Handles admin analytics dashboard functionality
 */
function analyticsLangCode() {
  return (
    window.AppI18n?.currentLang ||
    window.AdminI18n?.getCurrentLanguage?.().code ||
    localStorage.getItem("kinjo_lang") ||
    localStorage.getItem("admin_language") ||
    document.documentElement.lang ||
    "ar"
  );
}

function analyticsText(arText, enText) {
  return String(analyticsLangCode()).toLowerCase().startsWith("en") ? enText : arText;
}

function analyticsLocale() {
  return analyticsText("ar-JO", "en-US");
}

function analyticsLiteral(value) {
  const raw = String(value ?? "");
  if (!raw) return "";
  let result = raw;
  if (typeof window.AppI18n?.replaceLiteralSegments === "function") {
    result = window.AppI18n.replaceLiteralSegments(raw);
  } else if (typeof window.AdminI18n?.replaceLiteralSegments === "function") {
    result = window.AdminI18n.replaceLiteralSegments(raw);
  }
  return typeof window.escapeHtml === "function" ? window.escapeHtml(result) : result;
}

const Analytics = {
  // State
  startDate: null,
  endDate: null,
  governorateFilter: null,
  charts: {},

  /**
   * Initialize the analytics module
   */
  init: function () {
    // Set default date range (last 30 days)
    const today = new Date();
    const thirtyDaysAgo = new Date(today);
    thirtyDaysAgo.setDate(today.getDate() - 30);

    this.endDate = today.toISOString().split("T")[0];
    this.startDate = thirtyDaysAgo.toISOString().split("T")[0];

    // Set form values
    document.getElementById("startDate").value = this.startDate;
    document.getElementById("endDate").value = this.endDate;

    // Check if user is authenticated before loading data
    if (api.isAuthenticated()) {
      this.loadOverview();
      this.setupTabHandlers();
    } else {
      // Wait for authentication and then load data
      this.waitForAuthentication();
    }
  },

  /**
   * Wait for user authentication before loading data
   */
  waitForAuthentication: function () {
    const self = this;
    let attempts = 0;
    const maxAttempts = 20; // 10 seconds max wait

    const checkAuth = function () {
      attempts++;
      if (api.isAuthenticated()) {
        self.loadOverview();
        self.setupTabHandlers();
      } else if (attempts >= maxAttempts) {
        window.location.href = "/login?next=" + encodeURIComponent(window.location.pathname);
      } else {
        // Check again in 500ms
        setTimeout(checkAuth, 500);
      }
    };
    checkAuth();
  },

  /**
   * Setup tab change event handlers
   */
  setupTabHandlers: function () {
    const tabElements = document.querySelectorAll('#analyticsTabs button[data-bs-toggle="pill"]');
    tabElements.forEach(
      function (tab) {
        tab.addEventListener(
          "shown.bs.tab",
          function (event) {
            const targetId = event.target.getAttribute("data-bs-target").replace("#", "");
            this.onTabChange(targetId);
          }.bind(this)
        );
      }.bind(this)
    );
  },

  /**
   * Handle tab changes
   */
  onTabChange: function (tabId) {
    // Check authentication before loading tab data
    if (!api.isAuthenticated()) {
      showToast(analyticsText("يجب تسجيل الدخول أولاً", "Please sign in first"), "warning");
      return;
    }

    switch (tabId) {
      case "enrollments":
        this.loadEnrollmentData();
        break;
      case "attendance":
        this.loadAttendanceData();
        break;
      case "reports":
        this.loadReportsData();
        break;
      case "safety":
        this.loadSafetyData();
        break;
      case "staffing":
        this.loadStaffingData();
        break;
    }
  },

  /**
   * Apply date/governorate filters
   */
  applyFilters: function () {
    // Check authentication before applying filters
    if (!api.isAuthenticated()) {
      showToast(analyticsText("يجب تسجيل الدخول أولاً", "Please sign in first"), "warning");
      return;
    }

    this.startDate = document.getElementById("startDate").value;
    this.endDate = document.getElementById("endDate").value;
    this.governorateFilter = document.getElementById("governorateFilter").value;

    // Reload current tab data
    const activeTab = document.querySelector("#analyticsTabs .nav-link.active");
    if (activeTab) {
      const targetId = activeTab.getAttribute("data-bs-target").replace("#", "");
      if (targetId === "overview") {
        this.loadOverview();
      } else {
        this.onTabChange(targetId);
      }
    }
  },

  /**
   * Get query parameters for API calls
   */
  getQueryParams: function () {
    const params = new URLSearchParams();
    if (this.startDate) params.append("start_date", this.startDate);
    if (this.endDate) params.append("end_date", this.endDate);
    if (this.governorateFilter) params.append("governorate", this.governorateFilter);
    return params.toString();
  },

  /**
   * Show error state in a container
   */
  showError: function (containerId, message) {
    const container = document.getElementById(containerId);
    if (container) {
      container.innerHTML =
        '<div class="alert alert-danger text-center py-3" role="alert">' +
        '<i class="bi bi-exclamation-triangle me-2"></i>' +
        (message || analyticsText("حدث خطأ في تحميل البيانات", "Failed to load data")) +
        `<br><small class="text-muted">${analyticsText("يرجى المحاولة مرة أخرى", "Please try again")}</small>` +
        "</div>";
    }
  },

  /**
   * Show loading state in a container
   */
  showLoading: function (containerId) {
    const container = document.getElementById(containerId);
    if (container) {
      container.innerHTML =
        '<div class="text-center py-4">' +
        '<div class="spinner-border text-primary" role="status">' +
        `<span class="visually-hidden">${analyticsText("جاري التحميل...", "Loading...")}</span>` +
        "</div>" +
        `<p class="text-muted mt-2">${analyticsText("جاري التحميل...", "Loading...")}</p>` +
        "</div>";
    }
  },

  /**
   * Load overview data
   */
  loadOverview: async function () {
    // Check authentication before loading data
    if (!api.isAuthenticated()) {
      showToast(analyticsText("يجب تسجيل الدخول أولاً", "Please sign in first"), "warning");
      return;
    }

    // Show loading states
    this.showLoading("governorateBreakdown");
    this.showLoading("topRankings");
    this.showLoading("bottomRankings");

    try {
      const response = await api.get("/api/analytics/overview?" + this.getQueryParams());

      if (response.summary) {
        this.updateSummaryCards(response.summary);
      } else {
        this.updateSummaryCards({});
      }

      if (response.governorates) {
        this.renderGovernorateBreakdown(response.governorates);
        this.populateGovernorateFilter(response.governorates);
      } else {
        this.showError(
          "governorateBreakdown",
          analyticsText("لا توجد بيانات للمحافظات", "No governorate data")
        );
      }

      // Load rankings
      this.loadRankings();

      // Load trend chart
      this.loadTrendChart();
    } catch (error) {
      console.error("Error loading overview:", error);
      showToast(analyticsText("خطأ في تحميل البيانات", "Failed to load data"), "error");
      // Show error states in all sections
      this.updateSummaryCards({});
      this.showError(
        "governorateBreakdown",
        analyticsText("فشل تحميل بيانات المحافظات", "Failed to load governorate data")
      );
      this.showError(
        "topRankings",
        analyticsText("فشل تحميل التصنيفات", "Failed to load rankings")
      );
      this.showError(
        "bottomRankings",
        analyticsText("فشل تحميل التصنيفات", "Failed to load rankings")
      );
    }
  },

  /**
   * Update summary metric cards
   */
  updateSummaryCards: function (summary) {
    document.getElementById("totalKindergartens").textContent = summary.total_kindergartens || 0;
    document.getElementById("totalChildren").textContent = summary.total_children || 0;
    document.getElementById("attendanceRate").innerHTML =
      (summary.attendance_rate || 0) + "<small>%</small>";
    document.getElementById("governanceScore").textContent = summary.governance_avg_score || 0;
  },

  /**
   * Render governorate breakdown
   */
  renderGovernorateBreakdown: function (governorates) {
    const container = document.getElementById("governorateBreakdown");

    if (!governorates || governorates.length === 0) {
      container.innerHTML = `<p class="text-muted text-center py-4">${analyticsText("لا توجد بيانات", "No data")}</p>`;
      return;
    }

    const maxScore = Math.max(
      ...governorates.map(function (g) {
        return g.governance_score || 0;
      }),
      1
    );

    var html = '<div class="list-group list-group-flush">';
    governorates.forEach(function (gov) {
      const percentage = (gov.governance_score / maxScore) * 100;
      const bandClass =
        gov.governance_score >= 80
          ? "bg-success"
          : gov.governance_score >= 60
            ? "bg-warning"
            : "bg-danger";

      html +=
        "<div class=\"list-group-item drilldown-btn\" onclick=\"Analytics.drilldown('GOVERNORATE', '" +
        gov.governorate +
        "')\">" +
        '<div class="d-flex justify-content-between align-items-center mb-1">' +
        '<span class="fw-medium">' +
        gov.governorate +
        "</span>" +
        '<span class="badge ' +
        bandClass +
        '">' +
        (gov.governance_score ?? 0).toFixed(1) +
        "</span>" +
        "</div>" +
        '<div class="progress" style="height: 6px;">' +
        '<div class="progress-bar ' +
        bandClass +
        '" style="width: ' +
        percentage +
        '%"></div>' +
        "</div>" +
        '<small class="text-muted">' +
        gov.kindergarten_count +
        ` ${analyticsText("روضة", "kindergartens")} | ` +
        gov.children_count +
        ` ${analyticsText("طفل", "children")}</small>` +
        "</div>";
    });
    html += "</div>";

    container.innerHTML = html;
  },

  /**
   * Populate governorate filter dropdown
   */
  populateGovernorateFilter: function (governorates) {
    const select = document.getElementById("governorateFilter");
    select.innerHTML = `<option value="">${analyticsText("جميع المحافظات", "All governorates")}</option>`;

    governorates.forEach(function (gov) {
      const option = document.createElement("option");
      option.value = gov.governorate;
      option.textContent = gov.governorate;
      select.appendChild(option);
    });
  },

  /**
   * Load trend chart data
   */
  loadTrendChart: async function () {
    // Check authentication before loading data
    if (!api.isAuthenticated()) {
      return;
    }

    const metric = document.getElementById("trendMetric").value;
    const chartContainer = document.getElementById("trendChart").parentElement;

    try {
      const response = await api.get(
        "/api/analytics/time-series?metric=" +
          metric +
          "&dimension_type=NETWORK&granularity=daily&" +
          this.getQueryParams()
      );

      if (response.data && response.data.length > 0) {
        this.renderTrendChart(response.data, metric);
      } else {
        // Show empty state
        if (this.charts.trend) {
          this.charts.trend.destroy();
          this.charts.trend = null;
        }
        chartContainer.innerHTML =
          '<canvas id="trendChart"></canvas>' +
          '<div class="text-center text-muted py-4">' +
          `<i class="bi bi-graph-up me-2"></i>${analyticsText("لا توجد بيانات للفترة المحددة", "No data for the selected period")}` +
          "</div>";
      }
    } catch (error) {
      console.error("Error loading trend chart:", error);
      if (this.charts.trend) {
        this.charts.trend.destroy();
        this.charts.trend = null;
      }
      chartContainer.innerHTML =
        '<canvas id="trendChart"></canvas>' +
        '<div class="alert alert-danger text-center py-3">' +
        `<i class="bi bi-exclamation-triangle me-2"></i>${analyticsText("فشل تحميل بيانات الاتجاه", "Failed to load trend data")}` +
        "</div>";
    }
  },

  /**
   * Render trend chart
   */
  renderTrendChart: function (data, metric) {
    const ctx = document.getElementById("trendChart");

    // Destroy existing chart
    if (this.charts.trend) {
      this.charts.trend.destroy();
    }

    const labels = data.map(function (d) {
      const date = new Date(d.date);
      return date.toLocaleDateString(analyticsLocale(), {
        month: "short",
        day: "numeric",
      });
    });

    const values = data.map(function (d) {
      return d.value;
    });

    const metricLabels = {
      attendance_rate: analyticsText("نسبة الحضور (%)", "Attendance rate (%)"),
      incident_count: analyticsText("عدد الحوادث", "Incident count"),
      enrollment_count: analyticsText("التسجيلات الجديدة", "New enrollments"),
    };

    this.charts.trend = new Chart(ctx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: metricLabels[metric] || metric,
            data: values,
            borderColor: "#0d6efd",
            backgroundColor: "rgba(13, 110, 253, 0.1)",
            fill: true,
            tension: 0.4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false,
          },
        },
        scales: {
          y: {
            beginAtZero: true,
          },
        },
      },
    });
  },

  /**
   * Load rankings data
   */
  loadRankings: async function () {
    // Check authentication before loading data
    if (!api.isAuthenticated()) {
      return;
    }

    try {
      // Load top rankings
      const topResponse = await api.get(
        "/api/analytics/rankings/governance_score?top_n=5&" + this.getQueryParams()
      );
      this.renderRankings("topRankings", topResponse.rankings, false);
    } catch (error) {
      console.error("Error loading top rankings:", error);
      this.showError(
        "topRankings",
        analyticsText("فشل تحميل أفضل الروضات", "Failed to load top kindergartens")
      );
    }

    try {
      // Load bottom rankings
      const bottomResponse = await api.get(
        "/api/analytics/rankings/governance_score?top_n=5&bottom=true&" + this.getQueryParams()
      );
      this.renderRankings("bottomRankings", bottomResponse.rankings, true);
    } catch (error) {
      console.error("Error loading bottom rankings:", error);
      this.showError(
        "bottomRankings",
        analyticsText(
          "فشل تحميل الروضات التي تحتاج تحسين",
          "Failed to load underperforming kindergartens"
        )
      );
    }
  },

  /**
   * Render rankings list
   */
  renderRankings: function (containerId, rankings, _isBottom) {
    const container = document.getElementById(containerId);

    if (!rankings || rankings.length === 0) {
      container.innerHTML = `<p class="text-muted text-center py-3">${analyticsText("لا توجد بيانات", "No data")}</p>`;
      return;
    }

    var html = '<div class="list-group list-group-flush">';
    rankings.forEach(function (item, index) {
      const badgeClass = index < 3 ? "ranking-" + (index + 1) : "bg-secondary";
      const bandClass =
        item.band === "GREEN" ? "band-green" : item.band === "AMBER" ? "band-amber" : "band-red";

      html +=
        '<div class="list-group-item d-flex align-items-center drilldown-btn" ' +
        "onclick=\"Analytics.drilldown('KINDERGARTEN', '" +
        item.kindergarten_id +
        "')\">" +
        '<span class="ranking-badge ' +
        badgeClass +
        ' me-3">' +
        item.rank +
        "</span>" +
        '<div class="flex-grow-1">' +
        '<div class="fw-medium">' +
        analyticsLiteral(item.kindergarten_name) +
        "</div>" +
        '<small class="text-muted">' +
        analyticsLiteral(item.governorate) +
        "</small>" +
        "</div>" +
        '<span class="badge ' +
        bandClass +
        '">' +
        (item.value ?? 0).toFixed(1) +
        "</span>" +
        "</div>";
    });
    html += "</div>";

    container.innerHTML = html;
  },

  /**
   * Drill down into a dimension
   */
  drilldown: async function (dimensionType, dimensionId) {
    // Check authentication before loading drilldown data
    if (!api.isAuthenticated()) {
      showToast(analyticsText("يجب تسجيل الدخول أولاً", "Please sign in first"), "warning");
      return;
    }

    try {
      const modal = new bootstrap.Modal(document.getElementById("drilldownModal"));
      const modalTitle = document.getElementById("drilldownModalTitle");
      const modalBody = document.getElementById("drilldownModalBody");

      modalBody.innerHTML =
        '<div class="text-center py-4">' +
        '<div class="spinner-border text-primary" role="status"></div>' +
        "</div>";
      modal.show();

      const response = await api.get(
        "/api/analytics/drilldown/" +
          dimensionType +
          "/" +
          dimensionId +
          "?" +
          this.getQueryParams()
      );

      modalTitle.textContent = response.dimension_name || dimensionId;

      // Render drilldown content based on type
      if (dimensionType === "GOVERNORATE") {
        this.renderGovernorateDrilldown(modalBody, response);
      } else if (dimensionType === "KINDERGARTEN") {
        this.renderKindergartenDrilldown(modalBody, response);
      } else if (dimensionType === "CLASS") {
        this.renderClassDrilldown(modalBody, response);
      }
    } catch (error) {
      console.error("Error loading drilldown:", error);
      showToast(analyticsText("خطأ في تحميل التفاصيل", "Failed to load details"), "error");
    }
  },

  /**
   * Render governorate drilldown
   */
  renderGovernorateDrilldown: function (container, data) {
    var html =
      `<p class="text-muted mb-3">${analyticsText("الفترة", "Period")}: ` +
      data.period_start +
      ` ${analyticsText("إلى", "to")} ` +
      data.period_end +
      "</p>" +
      '<table class="table table-hover">' +
      "<thead>" +
      "<tr>" +
      `<th>${analyticsText("الروضة", "Kindergarten")}</th>` +
      `<th>${analyticsText("الأطفال", "Children")}</th>` +
      `<th>${analyticsText("الحضور %", "Attendance %")}</th>` +
      `<th>${analyticsText("الحوكمة", "Governance")}</th>` +
      "</tr>" +
      "</thead>" +
      "<tbody>";

    if (data.children) {
      data.children.forEach(function (kg) {
        const bandClass =
          kg.governance_band === "GREEN"
            ? "band-green"
            : kg.governance_band === "AMBER"
              ? "band-amber"
              : "band-red";
        html +=
          "<tr class=\"drilldown-btn\" onclick=\"Analytics.drilldown('KINDERGARTEN', '" +
          kg.id +
          "')\">" +
          "<td>" +
          analyticsLiteral(kg.name) +
          "</td>" +
          "<td>" +
          kg.children_count +
          "/" +
          kg.capacity +
          "</td>" +
          "<td>" +
          kg.attendance_rate +
          "%</td>" +
          '<td><span class="badge ' +
          bandClass +
          '">' +
          kg.governance_score +
          "</span></td>" +
          "</tr>";
      });
    }

    html += "</tbody></table>";
    container.innerHTML = html;
  },

  /**
   * Render kindergarten drilldown
   */
  renderKindergartenDrilldown: function (container, data) {
    const metrics = data.metrics || {};
    const bandClass =
      metrics.governance_band === "GREEN"
        ? "band-green"
        : metrics.governance_band === "AMBER"
          ? "band-amber"
          : "band-red";

    var html =
      '<div class="row g-3 mb-4">' +
      '<div class="col-md-3 text-center">' +
      '<div class="h4 mb-0">' +
      (metrics.children_count || 0) +
      "/" +
      (metrics.capacity || 0) +
      "</div>" +
      `<small class="text-muted">${analyticsText("الأطفال/السعة", "Children/Capacity")}</small>` +
      "</div>" +
      '<div class="col-md-3 text-center">' +
      '<div class="h4 mb-0">' +
      (metrics.attendance_rate || 0) +
      "%</div>" +
      `<small class="text-muted">${analyticsText("نسبة الحضور", "Attendance rate")}</small>` +
      "</div>" +
      '<div class="col-md-3 text-center">' +
      '<div class="h4 mb-0">' +
      (metrics.ratio_compliance || 0) +
      "%</div>" +
      `<small class="text-muted">${analyticsText("نسبة الموظفين", "Staff ratio")}</small>` +
      "</div>" +
      '<div class="col-md-3 text-center">' +
      '<div class="h4 mb-0"><span class="badge ' +
      bandClass +
      '">' +
      (metrics.governance_score || 0) +
      "</span></div>" +
      `<small class="text-muted">${analyticsText("الحوكمة", "Governance")}</small>` +
      "</div></div>" +
      `<h6 class="mb-3">${analyticsText("الفصول", "Classes")}</h6>` +
      '<table class="table table-hover">' +
      "<thead>" +
      "<tr>" +
      `<th>${analyticsText("الفصل", "Class")}</th>` +
      `<th>${analyticsText("الفئة العمرية", "Age group")}</th>` +
      `<th>${analyticsText("الأطفال", "Children")}</th>` +
      "</tr>" +
      "</thead>" +
      "<tbody>";

    if (data.children) {
      data.children.forEach(function (cls) {
        html +=
          "<tr class=\"drilldown-btn\" onclick=\"Analytics.drilldown('CLASS', '" +
          cls.id +
          "')\">" +
          "<td>" +
          analyticsLiteral(cls.name) +
          "</td>" +
          "<td>" +
          (cls.age_group || "-") +
          "</td>" +
          "<td>" +
          cls.children_count +
          "/" +
          cls.capacity +
          "</td>" +
          "</tr>";
      });
    }

    html += "</tbody></table>";
    container.innerHTML = html;
  },

  /**
   * Render class drilldown
   */
  renderClassDrilldown: function (container, data) {
    const metrics = data.metrics || {};

    var html =
      '<div class="row g-3 mb-4">' +
      '<div class="col-md-4 text-center">' +
      '<div class="h4 mb-0">' +
      (metrics.children_count || 0) +
      "/" +
      (metrics.capacity || 0) +
      "</div>" +
      `<small class="text-muted">${analyticsText("الأطفال/السعة", "Children/Capacity")}</small>` +
      "</div>" +
      '<div class="col-md-4 text-center">' +
      '<div class="h4 mb-0">' +
      (metrics.age_group || "-") +
      "</div>" +
      `<small class="text-muted">${analyticsText("الفئة العمرية", "Age group")}</small>` +
      "</div></div>" +
      `<h6 class="mb-3">${analyticsText("الأطفال", "Children")}</h6>` +
      '<table class="table">' +
      "<thead>" +
      "<tr>" +
      `<th>${analyticsText("الاسم", "Name")}</th>` +
      `<th>${analyticsText("أيام الحضور", "Attendance days")}</th>` +
      `<th>${analyticsText("نسبة الحضور", "Attendance rate")}</th>` +
      "</tr>" +
      "</thead>" +
      "<tbody>";

    if (data.children) {
      data.children.forEach(function (child) {
        html +=
          "<tr>" +
          "<td>" +
          analyticsLiteral(child.name) +
          "</td>" +
          "<td>" +
          child.attendance_days +
          "</td>" +
          "<td>" +
          child.attendance_rate +
          "%</td>" +
          "</tr>";
      });
    }

    html += "</tbody></table>";
    container.innerHTML = html;
  },

  /**
   * Load enrollment data
   */
  loadEnrollmentData: async function () {
    // Check authentication before loading data
    if (!api.isAuthenticated()) {
      return;
    }

    try {
      const response = await api.get("/api/analytics/enrollments/summary?" + this.getQueryParams());

      this.renderEnrollmentFunnel(response.status_breakdown);
      this.renderEnrollmentSummary(response);
    } catch (error) {
      console.error("Error loading enrollment data:", error);
    }
  },

  /**
   * Render enrollment funnel chart
   */
  renderEnrollmentFunnel: function (statusBreakdown) {
    const ctx = document.getElementById("enrollmentFunnelChart");

    if (this.charts.enrollmentFunnel) {
      this.charts.enrollmentFunnel.destroy();
    }

    const labels = [];
    const values = [];
    const statusLabels = {
      PENDING: analyticsText("قيد الانتظار", "Pending"),
      SUBMITTED: analyticsText("مقدم", "Submitted"),
      UNDER_REVIEW: analyticsText("قيد المراجعة", "Under review"),
      WAITLISTED: analyticsText("قائمة الانتظار", "Waitlisted"),
      APPROVED: analyticsText("موافق", "Approved"),
      ENROLLED: analyticsText("مسجل", "Enrolled"),
      ACTIVE: analyticsText("نشط", "Active"),
      REJECTED: analyticsText("مرفوض", "Rejected"),
      WITHDRAWN: analyticsText("منسحب", "Withdrawn"),
    };

    if (statusBreakdown) {
      Object.keys(statusBreakdown).forEach(function (status) {
        labels.push(statusLabels[status] || status);
        values.push(statusBreakdown[status] || 0);
      });
    }

    this.charts.enrollmentFunnel = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: analyticsText("عدد الطلبات", "Applications"),
            data: values,
            backgroundColor: [
              "#6c757d",
              "#17a2b8",
              "#ffc107",
              "#fd7e14",
              "#28a745",
              "#007bff",
              "#198754",
              "#dc3545",
              "#6c757d",
            ],
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        indexAxis: "y",
        plugins: {
          legend: {
            display: false,
          },
        },
      },
    });
  },

  /**
   * Render enrollment summary
   */
  renderEnrollmentSummary: function (data) {
    const container = document.getElementById("enrollmentSummary");
    container.innerHTML =
      '<div class="mb-3">' +
      '<div class="h4 text-primary">' +
      (data.total_applications || 0) +
      "</div>" +
      `<small class="text-muted">${analyticsText("إجمالي الطلبات", "Total applications")}</small>` +
      "</div>" +
      '<div class="mb-3">' +
      '<div class="h4 text-success">' +
      (data.active_enrollments || 0) +
      "</div>" +
      `<small class="text-muted">${analyticsText("المسجلون النشطون", "Active enrollments")}</small>` +
      "</div>" +
      '<div class="mb-3">' +
      '<div class="h4 text-info">' +
      (data.new_applications || 0) +
      "</div>" +
      `<small class="text-muted">${analyticsText("طلبات جديدة في الفترة", "New applications in period")}</small>` +
      "</div>" +
      "<div>" +
      '<div class="h4">' +
      (data.conversion_rate || 0) +
      "%</div>" +
      `<small class="text-muted">${analyticsText("نسبة التحويل", "Conversion rate")}</small>` +
      "</div>";
  },

  /**
   * Load attendance data
   */
  loadAttendanceData: async function () {
    // Check authentication before loading data
    if (!api.isAuthenticated()) {
      return;
    }

    try {
      const response = await api.get("/api/analytics/attendance/summary?" + this.getQueryParams());

      this.renderAttendanceDayChart(response.day_of_week_distribution);
      this.renderAttendanceSummary(response);
    } catch (error) {
      console.error("Error loading attendance data:", error);
    }
  },

  /**
   * Render attendance by day chart
   */
  renderAttendanceDayChart: function (dayDistribution) {
    const ctx = document.getElementById("attendanceDayChart");

    if (this.charts.attendanceDay) {
      this.charts.attendanceDay.destroy();
    }

    const labels = Object.keys(dayDistribution || {});
    const values = Object.values(dayDistribution || {});

    this.charts.attendanceDay = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: analyticsText("الحضور", "Attendance"),
            data: values,
            backgroundColor: "#0d6efd",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false,
          },
        },
      },
    });
  },

  /**
   * Render attendance summary
   */
  renderAttendanceSummary: function (data) {
    const container = document.getElementById("attendanceSummary");
    container.innerHTML =
      '<div class="mb-3">' +
      '<div class="h4 text-primary">' +
      (data.total_attendance_logs || 0) +
      "</div>" +
      `<small class="text-muted">${analyticsText("إجمالي سجلات الحضور", "Total attendance logs")}</small>` +
      "</div>" +
      '<div class="mb-3">' +
      '<div class="h4 text-success">' +
      (data.average_daily_attendance || 0) +
      "</div>" +
      `<small class="text-muted">${analyticsText("متوسط الحضور اليومي", "Average daily attendance")}</small>` +
      "</div>" +
      "<div>" +
      '<div class="h4">' +
      (data.period_days || 0) +
      "</div>" +
      `<small class="text-muted">${analyticsText("أيام الفترة", "Period days")}</small>` +
      "</div>";
  },

  /**
   * Load daily reports data
   */
  loadReportsData: async function () {
    // Check authentication before loading data
    if (!api.isAuthenticated()) {
      return;
    }

    try {
      const response = await api.get(
        "/api/analytics/daily-reports/summary?" + this.getQueryParams()
      );

      this.renderReportsStatusChart(response.status_breakdown);
      this.renderReportsSummary(response);
    } catch (error) {
      console.error("Error loading reports data:", error);
    }
  },

  /**
   * Render reports status chart
   */
  renderReportsStatusChart: function (statusBreakdown) {
    const ctx = document.getElementById("reportsStatusChart");

    if (this.charts.reportsStatus) {
      this.charts.reportsStatus.destroy();
    }

    const statusLabels = {
      DRAFT: analyticsText("مسودة", "Draft"),
      PENDING: analyticsText("قيد الانتظار", "Pending"),
      SENT: analyticsText("مرسل", "Sent"),
      VIEWED: analyticsText("تم الاطلاع", "Viewed"),
    };

    const labels = [];
    const values = [];

    if (statusBreakdown) {
      Object.keys(statusBreakdown).forEach(function (status) {
        labels.push(statusLabels[status] || status);
        values.push(statusBreakdown[status] || 0);
      });
    }

    this.charts.reportsStatus = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: labels,
        datasets: [
          {
            data: values,
            backgroundColor: ["#6c757d", "#ffc107", "#198754", "#0dcaf0"],
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
      },
    });
  },

  /**
   * Render reports summary
   */
  renderReportsSummary: function (data) {
    const container = document.getElementById("reportsSummary");
    container.innerHTML =
      '<div class="mb-3">' +
      '<div class="h4 text-primary">' +
      (data.total_reports || 0) +
      "</div>" +
      `<small class="text-muted">${analyticsText("إجمالي التقارير", "Total reports")}</small>` +
      "</div>" +
      '<div class="mb-3">' +
      '<div class="h4 text-success">' +
      (data.sent_count || 0) +
      "</div>" +
      `<small class="text-muted">${analyticsText("تقارير مرسلة", "Sent reports")}</small>` +
      "</div>" +
      "<div>" +
      '<div class="h4">' +
      (data.completion_rate || 0) +
      "%</div>" +
      `<small class="text-muted">${analyticsText("نسبة الإكمال", "Completion rate")}</small>` +
      "</div>";
  },

  /**
   * Load safety data
   */
  loadSafetyData: async function () {
    // Check authentication before loading data
    if (!api.isAuthenticated()) {
      return;
    }

    try {
      const response = await api.get("/api/analytics/safety/summary?" + this.getQueryParams());

      this.renderIncidentSeverityChart(response.severity_breakdown);
      this.renderIncidentTypeChart(response.type_breakdown);
      this.renderSafetySummary(response);
    } catch (error) {
      console.error("Error loading safety data:", error);
    }
  },

  /**
   * Render incident severity chart
   */
  renderIncidentSeverityChart: function (severityBreakdown) {
    const ctx = document.getElementById("incidentSeverityChart");

    if (this.charts.incidentSeverity) {
      this.charts.incidentSeverity.destroy();
    }

    const severityLabels = {
      LOW: analyticsText("منخفض", "Low"),
      MEDIUM: analyticsText("متوسط", "Medium"),
      HIGH: analyticsText("مرتفع", "High"),
      CRITICAL: analyticsText("حرج", "Critical"),
    };

    const colors = {
      LOW: "#198754",
      MEDIUM: "#ffc107",
      HIGH: "#fd7e14",
      CRITICAL: "#dc3545",
    };

    const labels = [];
    const values = [];
    const bgColors = [];

    if (severityBreakdown) {
      Object.keys(severityBreakdown).forEach(function (severity) {
        labels.push(severityLabels[severity] || severity);
        values.push(severityBreakdown[severity] || 0);
        bgColors.push(colors[severity] || "#6c757d");
      });
    }

    this.charts.incidentSeverity = new Chart(ctx, {
      type: "pie",
      data: {
        labels: labels,
        datasets: [
          {
            data: values,
            backgroundColor: bgColors,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
      },
    });
  },

  /**
   * Render incident type chart
   */
  renderIncidentTypeChart: function (typeBreakdown) {
    const ctx = document.getElementById("incidentTypeChart");

    if (this.charts.incidentType) {
      this.charts.incidentType.destroy();
    }

    const typeLabels = {
      INJURY: analyticsText("إصابة", "Injury"),
      ILLNESS: analyticsText("مرض", "Illness"),
      BEHAVIORAL: analyticsText("سلوكي", "Behavioral"),
      SAFETY: analyticsText("سلامة", "Safety"),
      OTHER: analyticsText("أخرى", "Other"),
    };

    const labels = [];
    const values = [];

    if (typeBreakdown) {
      Object.keys(typeBreakdown).forEach(function (type) {
        labels.push(typeLabels[type] || type);
        values.push(typeBreakdown[type] || 0);
      });
    }

    this.charts.incidentType = new Chart(ctx, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          {
            label: analyticsText("عدد الحوادث", "Incident count"),
            data: values,
            backgroundColor: "#0d6efd",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false,
          },
        },
      },
    });
  },

  /**
   * Render safety summary
   */
  renderSafetySummary: function (data) {
    const container = document.getElementById("safetySummary");
    container.innerHTML =
      '<div class="row g-3">' +
      '<div class="col-md-3 text-center">' +
      '<div class="h4 text-primary">' +
      (data.total_incidents || 0) +
      "</div>" +
      `<small class="text-muted">${analyticsText("إجمالي الحوادث", "Total incidents")}</small>` +
      "</div>" +
      '<div class="col-md-3 text-center">' +
      '<div class="h4 text-success">' +
      (data.resolved_count || 0) +
      "</div>" +
      `<small class="text-muted">${analyticsText("تم حلها", "Resolved")}</small>` +
      "</div>" +
      '<div class="col-md-3 text-center">' +
      '<div class="h4">' +
      (data.resolution_rate || 0) +
      "%</div>" +
      `<small class="text-muted">${analyticsText("نسبة الحل", "Resolution rate")}</small>` +
      "</div>" +
      '<div class="col-md-3 text-center">' +
      '<div class="h4 text-warning">' +
      ((data.severity_breakdown || {}).HIGH || 0) +
      "</div>" +
      `<small class="text-muted">${analyticsText("حوادث مرتفعة الخطورة", "High-severity incidents")}</small>` +
      "</div>" +
      "</div>";
  },

  /**
   * Load staffing data
   */
  loadStaffingData: async function () {
    // Check authentication before loading data
    if (!api.isAuthenticated()) {
      return;
    }

    try {
      const response = await api.get("/api/analytics/staffing/summary?" + this.getQueryParams());

      this.renderRatioComplianceChart(response);
      this.renderStaffingSummary(response);
    } catch (error) {
      console.error("Error loading staffing data:", error);
    }
  },

  /**
   * Render ratio compliance chart
   */
  renderRatioComplianceChart: function (data) {
    const ctx = document.getElementById("ratioComplianceChart");

    if (this.charts.ratioCompliance) {
      this.charts.ratioCompliance.destroy();
    }

    const compliance = data.compliance_rate || 0;
    const nonCompliance = 100 - compliance;

    this.charts.ratioCompliance = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: [analyticsText("ملتزم", "Compliant"), analyticsText("غير ملتزم", "Non-compliant")],
        datasets: [
          {
            data: [compliance, nonCompliance],
            backgroundColor: ["#198754", "#dc3545"],
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          title: {
            display: true,
            text: analyticsText(
              "نسبة الالتزام: " + compliance.toFixed(1) + "%",
              "Compliance rate: " + compliance.toFixed(1) + "%"
            ),
          },
        },
      },
    });
  },

  /**
   * Render staffing summary
   */
  renderStaffingSummary: function (data) {
    const container = document.getElementById("staffingSummary");
    const staffByRole = data.staff_by_role || {};

    container.innerHTML =
      '<div class="mb-3">' +
      '<div class="h4 text-primary">' +
      (data.compliance_rate || 0) +
      "%</div>" +
      `<small class="text-muted">${analyticsText("نسبة الالتزام", "Compliance rate")}</small>` +
      "</div>" +
      '<div class="mb-3">' +
      '<div class="h4">' +
      (data.average_ratio || 0) +
      "</div>" +
      `<small class="text-muted">${analyticsText("متوسط نسبة الأطفال للموظفين", "Average children-to-staff ratio")}</small>` +
      "</div>" +
      '<div class="mb-3">' +
      '<div class="h4">' +
      (staffByRole.MANAGER || 0) +
      "</div>" +
      `<small class="text-muted">${analyticsText("مديرون", "Managers")}</small>` +
      "</div>" +
      "<div>" +
      '<div class="h4">' +
      (staffByRole.SUPERVISOR || 0) +
      "</div>" +
      `<small class="text-muted">${analyticsText("مشرفون", "Supervisors")}</small>` +
      "</div>";
  },

  /**
   * Export data
   */
  exportData: async function (format) {
    try {
      const activeTab = document.querySelector("#analyticsTabs .nav-link.active");
      const reportType = activeTab ? activeTab.id.replace("-tab", "") : "overview";

      const response = await api.post("/api/analytics/export", {
        report_type: reportType,
        export_format: format,
      });

      showToast(
        analyticsText(
          "تم إنشاء طلب التصدير رقم " + response.job_id,
          "Export request created: " + response.job_id
        ),
        "success"
      );
    } catch (error) {
      console.error("Error requesting export:", error);
      showToast(analyticsText("خطأ في طلب التصدير", "Export request failed"), "error");
    }
  },
};

window.addEventListener("languageChanged", () => {
  if (typeof Analytics?.applyFilters === "function") {
    Analytics.applyFilters();
  }
});
