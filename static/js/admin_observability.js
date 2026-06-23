(function () {
  "use strict";

  var REFRESH_INTERVAL = 30000;
  var API_BASE = "/api/observability";
  var TELEMETRY_BASE = "/api/telemetry";

  function isArabic() {
    return document.documentElement.lang === "ar" ||
           document.documentElement.lang === "ar-JO";
  }

  function t(ar, en) {
    return isArabic() ? ar : en;
  }

  function el(id) {
    return document.getElementById(id);
  }

  function setStatus(elementId, text, level) {
    var node = el(elementId);
    if (!node) return;
    node.textContent = text;
    node.className = "text-muted small";
    if (level === "good") node.className = "text-success small";
    else if (level === "warn") node.className = "text-warning small";
    else if (level === "bad") node.className = "text-danger small";
  }

  function fetchJSON(url) {
    return fetch(url, {
      headers: {
        "Accept": "application/json",
        "X-Language": isArabic() ? "ar" : "en",
      },
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      });
  }

  function loadSummary() {
    fetchJSON(API_BASE + "/summary")
      .then(function (data) {
        var backend = data.backend || {};
        var cache = data.cache || {};
        var alerts = data.alerts || {};
        var dq = data.data_quality || {};

        var p95 = backend.p95_ms || 0;
        el("latency-p95").textContent = p95.toFixed(0) + "ms";
        setStatus("latency-status",
          p95 < 300 ? t("ضمن الهدف", "Within target") :
          p95 < 1000 ? t("مرتفع", "Elevated") : t("حرج", "Critical"),
          p95 < 300 ? "good" : p95 < 1000 ? "warn" : "bad"
        );

        var errRate = backend.error_rate || 0;
        el("error-rate").textContent = errRate.toFixed(1) + "%";
        setStatus("error-rate-status",
          errRate < 1 ? t("طبيعي", "Normal") :
          errRate < 5 ? t("مرتفع", "Elevated") : t("حرج", "Critical"),
          errRate < 1 ? "good" : errRate < 5 ? "warn" : "bad"
        );

        var hitRate = cache.hit_rate || 0;
        el("cache-hit-rate").textContent = hitRate.toFixed(1) + "%";
        setStatus("cache-status",
          hitRate >= 90 ? t("ممتاز", "Excellent") :
          hitRate >= 75 ? t("مقبول", "Acceptable") : t("ضعيف", "Poor"),
          hitRate >= 90 ? "good" : hitRate >= 75 ? "warn" : "bad"
        );

        var alertHealth = alerts.health || "unknown";
        var alertHealthLabels = {
          healthy: t("صحي", "Healthy"),
          watch: t("مراقبة", "Watch"),
          degraded: t("متدهور", "Degraded"),
          unknown: t("غير محدد", "Unknown"),
        };
        el("alert-health").textContent = alertHealthLabels[alertHealth] || alertHealth;
        var snrVal = alerts.signal_to_noise;
        if (snrVal !== null && snrVal !== undefined) {
          setStatus("alert-snr",
            t("نسبة الإشارة: ", "Signal-to-noise: ") + (snrVal * 100).toFixed(0) + "%",
            snrVal >= 0.6 ? "good" : snrVal >= 0.4 ? "warn" : "bad"
          );
        }

        var dqScore = dq.overall_score;
        if (dqScore !== null && dqScore !== undefined) {
          el("data-quality-score").textContent = dqScore.toFixed(1) + "%";
          setStatus("data-quality-status",
            dqScore >= 90 ? t("ممتاز", "Excellent") :
            dqScore >= 75 ? t("جيد", "Good") :
            dqScore >= 60 ? t("مقبول", "Fair") : t("ضعيف", "Poor"),
            dqScore >= 90 ? "good" : dqScore >= 75 ? "warn" : "bad"
          );
        }

        el("total-requests").textContent = (backend.total_requests || 0).toLocaleString();
        setStatus("requests-status", t("منذ بداية التشغيل", "Since startup"), null);
      })
      .catch(function (err) {
        el("latency-p95").textContent = "--";
        el("error-rate").textContent = "--";
        el("cache-hit-rate").textContent = "--";
        el("alert-health").textContent = "--";
        el("data-quality-score").textContent = "--";
        el("total-requests").textContent = "--";
      });
  }

  function loadFreshness() {
    fetchJSON(API_BASE + "/data-quality/freshness")
      .then(function (data) {
        var hours = data.hours_since_last_report;
        if (hours === null) {
          el("data-freshness").textContent = "--";
          setStatus("freshness-status", t("لا توجد بيانات", "No data"), "warn");
          return;
        }
        el("data-freshness").textContent = hours.toFixed(1) + "h";
        setStatus("freshness-status",
          hours <= 2 ? t("حديث", "Fresh") :
          hours <= 6 ? t("قديم قليلاً", "Stale") : t("قديم", "Old"),
          hours <= 2 ? "good" : hours <= 6 ? "warn" : "bad"
        );
      })
      .catch(function () {
        el("data-freshness").textContent = "--";
      });
  }

  function loadTelemetry() {
    fetchJSON(TELEMETRY_BASE + "/stats?period_hours=24")
      .then(function (data) {
        var lcpP95 = (data.web_vitals || {}).lcp || {};
        if (lcpP95.p95) {
          var val = lcpP95.p95;
          el("web-vitals-lcp").textContent = (val / 1000).toFixed(1) + "s";
          setStatus("vitals-status",
            val <= 2500 ? t("سريع", "Fast") :
            val <= 4000 ? t("متوسط", "Medium") : t("بطيء", "Slow"),
            val <= 2500 ? "good" : val <= 4000 ? "warn" : "bad"
          );
        } else {
          el("web-vitals-lcp").textContent = "--";
          setStatus("vitals-status", t("لم يتم جمع البيانات بعد", "No data collected yet"), null);
        }
      })
      .catch(function () {
        el("web-vitals-lcp").textContent = "--";
      });
  }

  function loadEndpointLatency() {
    fetchJSON(API_BASE + "/latency")
      .then(function (data) {
        var perEndpoint = data.per_endpoint_p95 || {};
        var endpoints = Object.keys(perEndpoint).slice(0, 20);
        if (endpoints.length === 0) {
          el("endpoint-latency-chart").innerHTML =
            '<p class="text-center text-muted my-4">' +
            t("لا توجد بيانات زمن استجابة متاحة بعد", "No latency data available yet") +
            "</p>";
          return;
        }
        if (typeof Plotly !== "undefined") {
          renderPlotlyChart(endpoints, perEndpoint);
        } else {
          renderTableChart(endpoints, perEndpoint);
        }
      })
      .catch(function () {
        el("endpoint-latency-chart").innerHTML =
          '<p class="text-center text-muted my-4">' +
          t("فشل تحميل البيانات", "Failed to load data") +
          "</p>";
      });
  }

  function renderPlotlyChart(endpoints, latencies) {
    var sortedEndpoints = endpoints.sort(function (a, b) {
      return (latencies[b] || 0) - (latencies[a] || 0);
    });

    var values = sortedEndpoints.map(function (ep) { return latencies[ep] || 0; });
    var colors = values.map(function (v) {
      if (v <= 300) return "#059669";
      if (v <= 1000) return "#d97706";
      return "#dc2626";
    });

    var trace = {
      x: values,
      y: sortedEndpoints,
      type: "bar",
      orientation: "h",
      marker: { color: colors },
    };

    var layout = {
      margin: { l: 200, r: 20, t: 10, b: 40 },
      xaxis: { title: t("زمن الاستجابة p95 (ميلي ثانية)", "p95 Latency (ms)") },
      height: Math.max(300, sortedEndpoints.length * 25),
    };

    Plotly.newPlot("endpoint-latency-chart", [trace], layout, {
      responsive: true,
      displaylogo: false,
    });
  }

  function renderTableChart(endpoints, latencies) {
    var html = "<table class='table table-sm table-hover'>";
    html += "<thead><tr><th>" + t("المسار", "Endpoint") + "</th><th>p95 (ms)</th></tr></thead><tbody>";
    endpoints.forEach(function (ep) {
      var val = latencies[ep] || 0;
      var badge = val <= 300 ? "badge bg-success" :
                  val <= 1000 ? "badge bg-warning" : "badge bg-danger";
      html += "<tr><td><code>" + ep + "</code></td>";
      html += "<td><span class='" + badge + "'>" + val.toFixed(0) + "</span></td></tr>";
    });
    html += "</tbody></table>";
    el("endpoint-latency-chart").innerHTML = html;
  }

  function loadDataQuality() {
    fetchJSON(API_BASE + "/data-quality")
      .then(function (data) {
        var rows = [
          { label: t("الحداثة", "Freshness"), value: data.freshness ? data.freshness.status : "--", },
          { label: t("الاكتمال", "Completeness"), value: data.completeness ? data.completeness.score + "%" : "--", },
          { label: t("الاتساق", "Consistency"), value: data.consistency ? data.consistency.consistency_score + "% (" + data.consistency.status + ")" : "--", },
          { label: t("التفرد", "Uniqueness"), value: data.uniqueness ? data.uniqueness.uniqueness_score + "% (" + data.uniqueness.status + ")" : "--", },
          { label: t("الصلاحية", "Validity"), value: data.validity ? data.validity.validity_score + "% (" + data.validity.status + ")" : "--", },
        ];

        var html = "";
        rows.forEach(function (row) {
          html += "<tr><td>" + row.label + "</td>";
          html += "<td>" + row.value + "</td>";
          var statusLevel = row.value;
          if (typeof statusLevel === "string") {
            if (statusLevel.indexOf("good") >= 0 || statusLevel.indexOf("excellent") >= 0 ||
                statusLevel.indexOf("unique") >= 0 || statusLevel.indexOf("valid") >= 0 ||
                statusLevel.indexOf("consistent") >= 0) {
              html += "<td><span class='badge bg-success'>" + t("نعم", "OK") + "</span></td>";
            } else if (row.value.indexOf("--") >= 0) {
              html += "<td><span class='badge bg-secondary'>--</span></td>";
            } else {
              html += "<td><span class='badge bg-warning'>" + t("تنبيه", "Warning") + "</span></td>";
            }
          } else {
            html += "<td>--</td>";
          }
          html += "</tr>";
        });

        el("quality-table-body").innerHTML = html;
      })
      .catch(function () {
        el("quality-table-body").innerHTML =
          "<tr><td colspan='3' class='text-center text-danger'>" +
          t("فشل تحميل البيانات", "Failed to load data") +
          "</td></tr>";
      });
  }

  function refreshAll() {
    loadSummary();
    loadFreshness();
    loadTelemetry();
    loadEndpointLatency();
    loadDataQuality();
    el("last-updated").textContent =
      t("آخر تحديث: ", "Last updated: ") + new Date().toLocaleTimeString();
  }

  function init() {
    refreshAll();
    setInterval(refreshAll, REFRESH_INTERVAL);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
