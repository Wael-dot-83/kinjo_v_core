/**
 * Decision Support Dashboard Module
 * Fetches aggregated analytics and renders decision-support widgets:
 *  - Geographic distribution chart
 *  - Classification bands (performance bands)
 *  - Capacity tier breakdown
 *  - Predictive insights
 *  - Risk assessment table
 *  - Enrollment funnel
 *  - Age group distribution
 */

/* global Chart, dashboardFetch, dashboardCurrentLang, dashboardText, formatNumber, escapeHtml, clampPercent */

(function () {
  "use strict";

  const DS_ENDPOINT = "/api/dashboard/decision-support";

  const DS_LABELS = {
    // Section headings
    "ds.geo_distribution": { ar: "التوزيع الجغرافي", en: "Geographic Distribution" },
    "ds.classification": { ar: "تصنيف الأداء", en: "Performance Classification" },
    "ds.capacity_overview": { ar: "نظرة على السعة", en: "Capacity Overview" },
    "ds.predictions": { ar: "التنبؤات والتوقعات", en: "Predictions & Forecasts" },
    "ds.risk_assessment": { ar: "تقييم المخاطر", en: "Risk Assessment" },
    "ds.enrollment_funnel": { ar: "مسار التسجيل", en: "Enrollment Pipeline" },
    "ds.age_distribution": { ar: "توزيع الفئات العمرية", en: "Age Group Distribution" },
    "ds.network_summary": { ar: "ملخص الشبكة", en: "Network Summary" },
    // Bands
    "ds.band.green": { ar: "ممتاز", en: "Excellent" },
    "ds.band.amber": { ar: "يحتاج تحسين", en: "Needs Improvement" },
    "ds.band.red": { ar: "حرج", en: "Critical" },
    // Capacity tiers
    "ds.tier.low": { ar: "استغلال منخفض", en: "Low Utilization" },
    "ds.tier.moderate": { ar: "استغلال متوسط", en: "Moderate Utilization" },
    "ds.tier.high": { ar: "استغلال مرتفع", en: "High Utilization" },
    "ds.tier.over_capacity": { ar: "تجاوز السعة", en: "Over Capacity" },
    // Prediction directions
    "ds.direction.up": { ar: "اتجاه صاعد ↑", en: "Trending Up ↑" },
    "ds.direction.down": { ar: "اتجاه هابط ↓", en: "Trending Down ↓" },
    "ds.direction.stable": { ar: "مستقر →", en: "Stable →" },
    // Metrics
    "ds.metric.attendance": { ar: "الحضور", en: "Attendance" },
    "ds.metric.incidents": { ar: "الحوادث", en: "Incidents" },
    "ds.metric.enrollment": { ar: "التسجيل", en: "Enrollment" },
    // Risk factors
    "ds.risk.low_attendance": { ar: "حضور منخفض", en: "Low Attendance" },
    "ds.risk.below_avg_attendance": { ar: "حضور دون المتوسط", en: "Below Avg Attendance" },
    "ds.risk.over_capacity": { ar: "تجاوز السعة", en: "Over Capacity" },
    "ds.risk.under_utilized": { ar: "استخدام منخفض", en: "Under-utilized" },
    "ds.risk.high_incident_rate": { ar: "معدل حوادث مرتفع", en: "High Incident Rate" },
    "ds.risk.elevated_incident_rate": { ar: "معدل حوادث متصاعد", en: "Elevated Incident Rate" },
    "ds.risk.license_expiring_soon": { ar: "ترخيص يقارب الانتهاء", en: "License Expiring Soon" },
    "ds.risk.license_expired": { ar: "ترخيص منتهي", en: "License Expired" },
    // Enrollment statuses
    "ds.funnel.submitted": { ar: "مقدّمة", en: "Submitted" },
    "ds.funnel.pending_review": { ar: "بانتظار المراجعة", en: "Pending Review" },
    "ds.funnel.accepted": { ar: "مقبولة", en: "Accepted" },
    "ds.funnel.active": { ar: "نشطة", en: "Active" },
    "ds.funnel.rejected": { ar: "مرفوضة", en: "Rejected" },
    "ds.funnel.waitlisted": { ar: "قائمة الانتظار", en: "Waitlisted" },
    "ds.funnel.withdrawn": { ar: "منسحبة", en: "Withdrawn" },
    // Table headers
    "ds.governorate": { ar: "المحافظة", en: "Governorate" },
    "ds.city": { ar: "المدينة", en: "City" },
    "ds.kg_count": { ar: "عدد الروضات", en: "Kindergartens" },
    "ds.capacity": { ar: "السعة", en: "Capacity" },
    "ds.enrolled": { ar: "المسجلون", en: "Enrolled" },
    "ds.utilization": { ar: "الاستغلال", en: "Utilization" },
    "ds.attendance": { ar: "الحضور", en: "Attendance" },
    "ds.incidents": { ar: "الحوادث", en: "Incidents" },
    "ds.kindergarten": { ar: "الروضة", en: "Kindergarten" },
    "ds.risk_score": { ar: "درجة المخاطر", en: "Risk Score" },
    "ds.risk_factors": { ar: "عوامل الخطر", en: "Risk Factors" },
    "ds.current": { ar: "الحالي", en: "Current" },
    "ds.predicted": { ar: "المتوقع", en: "Predicted" },
    "ds.confidence": { ar: "الثقة", en: "Confidence" },
    "ds.direction": { ar: "الاتجاه", en: "Direction" },
    "ds.forecast_period": { ar: "فترة التوقع", en: "Forecast Period" },
    "ds.days": { ar: "أيام", en: "days" },
    "ds.no_data": { ar: "لا توجد بيانات كافية", en: "Insufficient data" },
    "ds.total_kindergartens": { ar: "إجمالي الروضات", en: "Total Kindergartens" },
    "ds.total_children": { ar: "إجمالي الأطفال", en: "Total Children" },
    "ds.total_capacity": { ar: "إجمالي السعة", en: "Total Capacity" },
    "ds.network_util": { ar: "استخدام الشبكة", en: "Network Utilization" },
    "ds.network_att": { ar: "حضور الشبكة", en: "Network Attendance" },
    "ds.avg_attendance": { ar: "متوسط الحضور", en: "Avg Attendance" },
    "ds.avg_utilization": { ar: "متوسط الاستغلال", en: "Avg Utilization" },
    "ds.count": { ar: "العدد", en: "Count" },
  };

  function dsText(key) {
    const lang = typeof dashboardCurrentLang === "function" ? dashboardCurrentLang() : "ar";
    const entry = DS_LABELS[key];
    if (!entry) return key;
    return lang === "en" ? entry.en : entry.ar;
  }

  function fmtNum(v) {
    return typeof formatNumber === "function" ? formatNumber(v) : String(v);
  }

  function esc(v) {
    return typeof escapeHtml === "function" ? escapeHtml(v) : String(v || "");
  }

  // Chart.js instances for cleanup
  const chartInstances = {};

  function destroyChart(key) {
    if (chartInstances[key]) {
      chartInstances[key].destroy();
      chartInstances[key] = null;
    }
  }

  function canRenderChart() {
    return typeof Chart !== "undefined";
  }

  function showCanvasFallback(canvas, message) {
    if (!canvas) return;
    destroyChart(canvas.dataset.dsChartKey || "");
    canvas.style.display = "none";
    const parent = canvas.parentElement;
    if (!parent) return;
    let fallback = parent.querySelector(".ds-chart-fallback");
    if (!fallback) {
      fallback = document.createElement("p");
      fallback.className = "ds-chart-fallback text-muted text-center py-4 mb-0";
      parent.appendChild(fallback);
    }
    fallback.textContent = message || dsText("ds.no_data");
  }

  function prepareCanvas(canvas, chartKey) {
    if (!canvas) return false;
    canvas.dataset.dsChartKey = chartKey;
    const fallback = canvas.parentElement?.querySelector(".ds-chart-fallback");
    if (fallback) fallback.remove();
    canvas.style.display = "";
    if (canRenderChart()) return true;
    showCanvasFallback(canvas, dsText("ds.no_data"));
    return false;
  }

  function renderDecisionSupportFallback() {
    [
      "dsGeoChart",
      "dsClassificationChart",
      "dsCapacityChart",
      "dsFunnelChart",
      "dsAgeChart",
    ].forEach(function (id) {
      showCanvasFallback(document.getElementById(id), dsText("ds.no_data"));
    });

    const tableFallbacks = [
      ["dsGeoTable", 8],
      ["dsRiskTable", 4],
    ];
    tableFallbacks.forEach(function (entry) {
      const el = document.getElementById(entry[0]);
      if (el) {
        el.innerHTML =
          '<tr><td colspan="' +
          entry[1] +
          '" class="text-center text-muted py-3">' +
          esc(dsText("ds.no_data")) +
          "</td></tr>";
      }
    });

    ["dsClassificationDetail", "dsPredictions"].forEach(function (id) {
      const el = document.getElementById(id);
      if (el) {
        el.innerHTML = '<p class="text-muted text-center py-4 mb-0">' + esc(dsText("ds.no_data")) + "</p>";
      }
    });
  }

  // -----------------------------------------------------------------------
  // Render functions
  // -----------------------------------------------------------------------

  function renderNetworkSummary(data) {
    const el = document.getElementById("dsNetworkSummary");
    if (!el) return;
    const items = [
      {
        label: dsText("ds.total_kindergartens"),
        value: fmtNum(data.total_kindergartens),
        icon: "bi-building",
        color: "primary",
      },
      {
        label: dsText("ds.total_children"),
        value: fmtNum(data.total_children),
        icon: "bi-people",
        color: "success",
      },
      {
        label: dsText("ds.total_capacity"),
        value: fmtNum(data.total_capacity),
        icon: "bi-box",
        color: "info",
      },
      {
        label: dsText("ds.network_util"),
        value: data.network_utilization_pct + "%",
        icon: "bi-bar-chart-line",
        color: "warning",
      },
      {
        label: dsText("ds.network_att"),
        value: data.network_attendance_pct + "%",
        icon: "bi-check2-circle",
        color: "success",
      },
    ];
    el.innerHTML = items
      .map(function (it) {
        return (
          '<div class="col">' +
          '<div class="ds-summary-card border-start border-4 border-' +
          it.color +
          " bg-" +
          it.color +
          '-subtle rounded-3 p-3 h-100">' +
          '<div class="d-flex align-items-center gap-2 mb-1">' +
          '<i class="bi ' +
          it.icon +
          " fs-5 text-" +
          it.color +
          '"></i>' +
          '<span class="text-muted small">' +
          esc(it.label) +
          "</span></div>" +
          '<div class="fs-4 fw-bold">' +
          esc(it.value) +
          "</div></div></div>"
        );
      })
      .join("");
  }

  function renderGeoDistribution(items) {
    const chartEl = document.getElementById("dsGeoChart");
    const tableEl = document.getElementById("dsGeoTable");
    if (!items || items.length === 0) {
      showCanvasFallback(chartEl, dsText("ds.no_data"));
      if (tableEl)
        tableEl.innerHTML =
          '<tr><td colspan="8" class="text-center text-muted py-3">' +
          esc(dsText("ds.no_data")) +
          "</td></tr>";
      return;
    }

    // Bar chart: kindergartens by governorate
    if (chartEl && prepareCanvas(chartEl, "geo")) {
      const govMap = {};
      items.forEach(function (g) {
        var gov = g.governorate || "—";
        govMap[gov] = (govMap[gov] || 0) + g.kindergarten_count;
      });
      const labels = Object.keys(govMap);
      const values = Object.values(govMap);
      destroyChart("geo");
      chartInstances["geo"] = new Chart(chartEl, {
        type: "bar",
        data: {
          labels: labels,
          datasets: [
            {
              label: dsText("ds.kg_count"),
              data: values,
              backgroundColor: "rgba(13, 110, 253, 0.75)",
              hoverBackgroundColor: "rgba(13, 110, 253, 1)",
              borderRadius: 6,
              borderWidth: 0,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: { duration: 600, easing: "easeOutQuart" },
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: "rgba(17,24,39,0.92)",
              titleColor: "#f9fafb",
              bodyColor: "#d1d5db",
              padding: 10,
              cornerRadius: 6,
            },
          },
          scales: {
            x: { grid: { display: false } },
            y: {
              beginAtZero: true,
              ticks: { stepSize: 1 },
              grid: { color: "rgba(0,0,0,0.06)" },
            },
          },
        },
      });
    }

    // Table
    if (tableEl) {
      tableEl.innerHTML = items
        .map(function (g) {
          var utilClass =
            g.utilization_pct >= 95
              ? "text-danger"
              : g.utilization_pct >= 75
                ? "text-warning"
                : "text-success";
          var attClass =
            g.attendance_rate >= 85
              ? "text-success"
              : g.attendance_rate >= 70
                ? "text-warning"
                : "text-danger";
          return (
            "<tr>" +
            "<td>" +
            esc(g.governorate) +
            "</td>" +
            "<td>" +
            esc(g.city) +
            "</td>" +
            '<td class="fw-semibold">' +
            fmtNum(g.kindergarten_count) +
            "</td>" +
            "<td>" +
            fmtNum(g.total_capacity) +
            "</td>" +
            "<td>" +
            fmtNum(g.total_enrolled) +
            "</td>" +
            '<td class="' +
            utilClass +
            ' fw-semibold">' +
            g.utilization_pct +
            "%</td>" +
            '<td class="' +
            attClass +
            ' fw-semibold">' +
            g.attendance_rate +
            "%</td>" +
            "<td>" +
            fmtNum(g.incident_count) +
            "</td></tr>"
          );
        })
        .join("");
    }
  }

  function renderClassificationBands(bands) {
    const chartEl = document.getElementById("dsClassificationChart");
    const detailEl = document.getElementById("dsClassificationDetail");
    if (!bands || bands.length === 0) {
      showCanvasFallback(chartEl, dsText("ds.no_data"));
      if (detailEl) detailEl.innerHTML = "";
      return;
    }

    // Doughnut chart
    if (chartEl && prepareCanvas(chartEl, "classification")) {
      const labels = bands.map(function (b) {
        return dsText("ds.band." + b.band);
      });
      const values = bands.map(function (b) {
        return b.count;
      });
      const colors = bands.map(function (b) {
        return b.band === "green" ? "#198754" : b.band === "amber" ? "#ffc107" : "#dc3545";
      });
      const hoverColors = bands.map(function (b) {
        return b.band === "green" ? "#157347" : b.band === "amber" ? "#e0a800" : "#bb2d3b";
      });
      destroyChart("classification");
      chartInstances["classification"] = new Chart(chartEl, {
        type: "doughnut",
        data: {
          labels: labels,
          datasets: [{
            data: values,
            backgroundColor: colors,
            hoverBackgroundColor: hoverColors,
            borderWidth: 0,
            hoverOffset: 6,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: "65%",
          animation: { duration: 600, easing: "easeOutQuart" },
          plugins: {
            legend: { position: "bottom" },
            tooltip: {
              backgroundColor: "rgba(17,24,39,0.92)",
              titleColor: "#f9fafb",
              bodyColor: "#d1d5db",
              padding: 10,
              cornerRadius: 6,
              callbacks: {
                label: function (ctx) {
                  const total = (ctx.dataset.data || []).reduce(function (a, b) { return a + (b || 0); }, 0);
                  const pct = total ? ((ctx.parsed / total) * 100).toFixed(1) : "0.0";
                  return " " + ctx.label + ": " + ctx.parsed + " (" + pct + "%)";
                },
              },
            },
          },
        },
      });
    }

    // Detail cards
    if (detailEl) {
      detailEl.innerHTML = bands
        .map(function (b) {
          var colorClass =
            b.band === "green" ? "success" : b.band === "amber" ? "warning" : "danger";
          return (
            '<div class="col-md-4">' +
            '<div class="card border-' +
            colorClass +
            ' h-100">' +
            '<div class="card-body text-center">' +
            '<h5 class="card-title text-' +
            colorClass +
            '">' +
            esc(dsText("ds.band." + b.band)) +
            "</h5>" +
            '<div class="fs-2 fw-bold text-' +
            colorClass +
            '">' +
            fmtNum(b.count) +
            "</div>" +
            '<div class="small text-muted mt-2">' +
            esc(dsText("ds.avg_attendance")) +
            ": " +
            b.avg_attendance +
            "%</div>" +
            '<div class="small text-muted">' +
            esc(dsText("ds.avg_utilization")) +
            ": " +
            b.avg_capacity_util +
            "%</div>" +
            "</div></div></div>"
          );
        })
        .join("");
    }
  }

  function renderCapacityTiers(tiers) {
    const chartEl = document.getElementById("dsCapacityChart");
    if (!tiers || tiers.length === 0) {
      showCanvasFallback(chartEl, dsText("ds.no_data"));
      return;
    }
    if (!prepareCanvas(chartEl, "capacity")) return;
    const labels = tiers.map(function (t) {
      return dsText("ds.tier." + t.tier);
    });
    const values = tiers.map(function (t) {
      return t.count;
    });
    const colors = ["#0dcaf0", "#198754", "#ffc107", "#dc3545"];
    const hoverColors = ["#0aa6c9", "#157347", "#e0a800", "#bb2d3b"];
    destroyChart("capacity");
    chartInstances["capacity"] = new Chart(chartEl, {
      type: "pie",
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: colors.slice(0, tiers.length),
          hoverBackgroundColor: hoverColors.slice(0, tiers.length),
          borderWidth: 0,
          hoverOffset: 6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 600, easing: "easeOutQuart" },
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            backgroundColor: "rgba(17,24,39,0.92)",
            titleColor: "#f9fafb",
            bodyColor: "#d1d5db",
            padding: 10,
            cornerRadius: 6,
            callbacks: {
              label: function (ctx) {
                const total = (ctx.dataset.data || []).reduce(function (a, b) { return a + (b || 0); }, 0);
                const pct = total ? ((ctx.parsed / total) * 100).toFixed(1) : "0.0";
                return " " + ctx.label + ": " + ctx.parsed + " (" + pct + "%)";
              },
            },
          },
        },
      },
    });
  }

  function renderPredictions(predictions) {
    const el = document.getElementById("dsPredictions");
    if (!el) return;
    if (!predictions || predictions.length === 0) {
      el.innerHTML = '<p class="text-muted text-center py-4">' + esc(dsText("ds.no_data")) + "</p>";
      return;
    }
    el.innerHTML = predictions
      .map(function (p) {
        var dirClass =
          p.direction === "up" ? "success" : p.direction === "down" ? "danger" : "secondary";
        var dirIcon =
          p.direction === "up"
            ? "bi-arrow-up-right"
            : p.direction === "down"
              ? "bi-arrow-down-right"
              : "bi-arrow-right";
        var confPct = Math.round(p.confidence * 100);
        return (
          '<div class="col-md-4">' +
          '<div class="card border-0 shadow-sm h-100">' +
          '<div class="card-body">' +
          '<div class="d-flex justify-content-between align-items-center mb-2">' +
          '<h6 class="mb-0">' +
          esc(dsText("ds.metric." + p.metric)) +
          "</h6>" +
          '<span class="badge bg-' +
          dirClass +
          "-subtle text-" +
          dirClass +
          '"><i class="bi ' +
          dirIcon +
          ' me-1"></i>' +
          esc(dsText("ds.direction." + p.direction)) +
          "</span></div>" +
          '<div class="row text-center mt-3">' +
          '<div class="col-6"><div class="text-muted small">' +
          esc(dsText("ds.current")) +
          '</div><div class="fs-5 fw-bold">' +
          fmtNum(p.current_value) +
          "</div></div>" +
          '<div class="col-6"><div class="text-muted small">' +
          esc(dsText("ds.predicted")) +
          '</div><div class="fs-5 fw-bold text-' +
          dirClass +
          '">' +
          fmtNum(p.predicted_value) +
          "</div></div></div>" +
          '<div class="mt-3">' +
          '<div class="d-flex justify-content-between small text-muted"><span>' +
          esc(dsText("ds.confidence")) +
          "</span><span>" +
          confPct +
          "%</span></div>" +
          '<div class="progress" style="height:6px"><div class="progress-bar bg-' +
          dirClass +
          '" style="width:' +
          confPct +
          '%"></div></div>' +
          '<div class="text-muted small mt-1">' +
          esc(dsText("ds.forecast_period")) +
          ": " +
          p.forecast_days +
          " " +
          esc(dsText("ds.days")) +
          "</div>" +
          "</div></div></div></div>"
        );
      })
      .join("");
  }

  function renderRiskAssessment(items) {
    const el = document.getElementById("dsRiskTable");
    if (!el) return;
    if (!items || items.length === 0) {
      el.innerHTML =
        '<tr><td colspan="5" class="text-center text-muted py-3">' +
        esc(dsText("ds.no_data")) +
        "</td></tr>";
      return;
    }
    el.innerHTML = items
      .slice(0, 10)
      .map(function (r) {
        var scoreClass = r.risk_score >= 60 ? "danger" : r.risk_score >= 30 ? "warning" : "info";
        var factors = r.risk_factors
          .map(function (f) {
            return (
              '<span class="badge bg-' +
              scoreClass +
              "-subtle text-" +
              scoreClass +
              ' me-1 mb-1">' +
              esc(dsText("ds.risk." + f) || f) +
              "</span>"
            );
          })
          .join("");
        return (
          "<tr>" +
          '<td class="fw-semibold">' +
          esc(r.kindergarten_name) +
          "</td>" +
          "<td>" +
          esc(r.city) +
          "</td>" +
          '<td><span class="badge bg-' +
          scoreClass +
          ' fs-6">' +
          Math.round(r.risk_score) +
          "</span></td>" +
          "<td>" +
          factors +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
  }

  function renderEnrollmentFunnel(funnel) {
    const chartEl = document.getElementById("dsFunnelChart");
    if (!funnel || !chartEl) {
      showCanvasFallback(chartEl, dsText("ds.no_data"));
      return;
    }

    const stages = [
      { key: "submitted", value: funnel.submitted, color: "#6c757d" },
      { key: "pending_review", value: funnel.pending_review, color: "#0d6efd" },
      { key: "accepted", value: funnel.accepted, color: "#198754" },
      { key: "active", value: funnel.active, color: "#0dcaf0" },
      { key: "waitlisted", value: funnel.waitlisted, color: "#ffc107" },
      { key: "rejected", value: funnel.rejected, color: "#dc3545" },
      { key: "withdrawn", value: funnel.withdrawn, color: "#6f42c1" },
    ];

    if (!prepareCanvas(chartEl, "funnel")) return;
    destroyChart("funnel");
    chartInstances["funnel"] = new Chart(chartEl, {
      type: "bar",
      data: {
        labels: stages.map(function (s) {
          return dsText("ds.funnel." + s.key);
        }),
        datasets: [
          {
            data: stages.map(function (s) {
              return s.value;
            }),
            backgroundColor: stages.map(function (s) {
              return s.color;
            }),
            hoverBackgroundColor: stages.map(function (s) {
              return s.color;
            }),
            borderRadius: 6,
            borderWidth: 0,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 600, easing: "easeOutQuart" },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "rgba(17,24,39,0.92)",
            titleColor: "#f9fafb",
            bodyColor: "#d1d5db",
            padding: 10,
            cornerRadius: 6,
          },
        },
        scales: {
          x: { beginAtZero: true, grid: { color: "rgba(0,0,0,0.06)" } },
          y: { grid: { display: false } },
        },
      },
    });
  }

  function renderAgeDistribution(items) {
    const chartEl = document.getElementById("dsAgeChart");
    if (!items || items.length === 0 || !chartEl) {
      showCanvasFallback(chartEl, dsText("ds.no_data"));
      return;
    }
    const labels = items.map(function (a) {
      return a.age_group;
    });
    const values = items.map(function (a) {
      return a.count;
    });
    const colors = ["#0d6efd", "#198754", "#ffc107", "#dc3545", "#6f42c1", "#0dcaf0"];
    const hoverColors = ["#0b5ed7", "#157347", "#e0a800", "#bb2d3b", "#59359a", "#0aa6c9"];
    if (!prepareCanvas(chartEl, "age")) return;
    destroyChart("age");
    chartInstances["age"] = new Chart(chartEl, {
      type: "doughnut",
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: colors.slice(0, items.length),
          hoverBackgroundColor: hoverColors.slice(0, items.length),
          borderWidth: 0,
          hoverOffset: 6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "65%",
        animation: { duration: 600, easing: "easeOutQuart" },
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            backgroundColor: "rgba(17,24,39,0.92)",
            titleColor: "#f9fafb",
            bodyColor: "#d1d5db",
            padding: 10,
            cornerRadius: 6,
            callbacks: {
              label: function (ctx) {
                const total = (ctx.dataset.data || []).reduce(function (a, b) { return a + (b || 0); }, 0);
                const pct = total ? ((ctx.parsed / total) * 100).toFixed(1) : "0.0";
                return " " + ctx.label + ": " + ctx.parsed + " (" + pct + "%)";
              },
            },
          },
        },
      },
    });
  }

  // -----------------------------------------------------------------------
  // Main loader
  // -----------------------------------------------------------------------

  async function loadDecisionSupport() {
    const container = document.getElementById("decisionSupportSection");
    if (!container) return;

    // Show loading skeleton
    container.querySelectorAll(".ds-loading").forEach(function (el) {
      el.style.display = "block";
    });

    try {
      var data = await dashboardFetch(DS_ENDPOINT);
      if (!data) return;

      renderNetworkSummary(data);
      renderGeoDistribution(data.geo_distribution);
      renderClassificationBands(data.classification_bands);
      renderCapacityTiers(data.capacity_tiers);
      renderPredictions(data.predictions);
      renderRiskAssessment(data.risk_items);
      renderEnrollmentFunnel(data.enrollment_funnel);
      renderAgeDistribution(data.age_group_distribution);
    } catch (err) {
      console.error("Decision support load error:", err);
      renderDecisionSupportFallback();
    } finally {
      container.querySelectorAll(".ds-loading").forEach(function (el) {
        el.style.display = "none";
      });
    }
  }

  // Export for external use
  window.loadDecisionSupport = loadDecisionSupport;
})();
