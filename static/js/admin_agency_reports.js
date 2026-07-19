(function () {
  "use strict";
  const page = document.querySelector("[data-agency-reports-page]");
  if (!page) return;
  const lang = document.documentElement.lang === "en" ? "en" : "ar";
  const root = document.getElementById("agency-reports-root") || document.getElementById("agency-report-root");
  const api = (path) => fetch(path, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } }).then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
  const t = (ar, en) => lang === "en" ? en : ar;
  const LOCALE = lang === "ar" ? "ar-JO" : "en-US";

  function formatDateForFilename(value) {
    if (!value) return new Date().toISOString().slice(0, 10);
    try {
      if (typeof value === "string" && value.length >= 10) {
        return value.slice(0, 10);
      }
      const parsed = new Date(value);
      if (!Number.isNaN(parsed.valueOf())) {
        return parsed.toISOString().slice(0, 10);
      }
    } catch (err) {
      /* ignore and fall through */
    }
    return new Date().toISOString().slice(0, 10);
  }

  // Index-view filter state. Declared at module scope because agencyCard() (a
  // top-level function) reads state.dateFrom/dateTo to propagate the selected
  // date range onto agency links; a block-scoped const would throw ReferenceError
  // there and the catalog .then() would fall into .catch ("تعذر تحميل البيانات").
  const state = { search: "", status: "all", sort: "name", dateFrom: "", dateTo: "" };

  const agencyLogoFiles = {
    moe: "moe.jpg",
    moh: "moh.jpg",
    dos: "gsd.jpg",
    ncfa: "ncfa.png",
    mol: "mol.png",
    mosd: "mosd.jpg"
  };

  function clear(el) { if (el) el.innerHTML = ""; }

  function pill(text, kind, icon) {
    const span = document.createElement("span");
    span.className = "agency-status agency-status--" + (kind || "default");
    if (icon) {
      const i = document.createElement("i");
      i.className = "bi " + icon;
      i.setAttribute("aria-hidden", "true");
      span.appendChild(i);
      span.appendChild(document.createTextNode(" " + text));
    } else {
      span.textContent = text;
    }
    return span;
  }

  function statusBadge(status) {
    if (status === "ready") return pill(t("جاهزة", "Ready"), "success", "bi-check-circle-fill");
    if (status === "requires_structured_data") return pill(t("تحتاج بيانات", "Needs data"), "warning", "bi-exclamation-triangle-fill");
    return pill(t("غير متاح", "Unavailable"), "default", "bi-dash-circle");
  }

  function logoBadge(agency) {
    const badge = document.createElement("span");
    badge.className = "agency-logo-badge";
    badge.setAttribute("aria-hidden", "true");
    if (agency.icon) {
      const i = document.createElement("i");
      i.className = "bi " + agency.icon;
      badge.appendChild(i);
    } else {
      const name = (lang === "en" ? agency.name_en : agency.name_ar) || agency.code || "";
      badge.textContent = name.trim().slice(0, 2);
      badge.classList.add("agency-logo-badge--text");
    }
    return badge;
  }

  window.renderAgencyLogo = function renderAgencyLogo(agency, size) {
    const logoFile = agencyLogoFiles[agency.code];
    if (logoFile) {
      const img = document.createElement("img");
      img.className = "agency-card-logo";
      img.src = "/static/img/agencies/" + logoFile;
      img.alt = "";
      img.setAttribute("aria-hidden", "true");
      if (size) { img.width = size; img.height = size; }
      return img;
    }
    return logoBadge(agency);
  };

  // -------- Index page: readiness, KPI grid, agency cards, skeletons --------
  const READINESS = {
    ready:      { ar: "جاهزة",           en: "Ready",           cls: "success", icon: "bi-check-circle-fill" },
    partial:    { ar: "جاهزة جزئيًا",    en: "Partially ready", cls: "info",    icon: "bi-clock-history" },
    needs_data: { ar: "تحتاج بيانات",    en: "Needs data",      cls: "warning", icon: "bi-exclamation-triangle-fill" },
  };
  const READINESS_RANK = { ready: 0, partial: 1, needs_data: 2 };

  function agencyReadiness(agency) {
    const total = agency.report_count || 0;
    const ready = agency.ready_report_count || 0;
    if (total > 0 && ready >= total) return "ready";
    if (ready > 0) return "partial";
    return "needs_data";
  }

  function readinessBadge(key) {
    const r = READINESS[key] || READINESS.needs_data;
    const span = document.createElement("span");
    span.className = "agency-readiness agency-readiness--" + r.cls;
    const i = document.createElement("i");
    i.className = "bi " + r.icon;
    i.setAttribute("aria-hidden", "true");
    span.appendChild(i);
    span.appendChild(document.createTextNode(" " + t(r.ar, r.en)));
    return span;
  }

  function renderKpiGrid(agencies) {
    const grid = document.getElementById("agency-kpi-grid");
    if (!grid) return;
    const totalReports = agencies.reduce((s, a) => s + (a.report_count || 0), 0);
    const readyReports = agencies.reduce((s, a) => s + (a.ready_report_count || 0), 0);
    const needsData = agencies.reduce((s, a) => s + (a.requires_data_count || 0), 0);
    const generatedAt = agencies.length ? agencies[0].generated_at : null;
    const items = [
      { value: agencies.length, label: t("الجهات الرسمية", "Official agencies"), icon: "bi-buildings", cls: "primary", hint: t("جهات حكومية متكاملة", "Connected agencies") },
      { value: totalReports, label: t("إجمالي التقارير", "Total reports"), icon: "bi-file-earmark-bar-graph", cls: "primary", hint: t("تقارير تجميعية متاحة", "Aggregated reports") },
      { value: readyReports, label: t("التقارير الجاهزة", "Ready reports"), icon: "bi-check-circle-fill", cls: "success", hint: t("جاهزة للعرض والتصدير", "Ready to view & export") },
      { value: needsData, label: t("تحتاج إلى بيانات", "Need data"), icon: "bi-exclamation-triangle-fill", cls: "warning", hint: t("بانتظار بيانات منظمة", "Awaiting structured data") },
    ];
    grid.innerHTML = "";
    items.forEach((item) => {
      const li = document.createElement("li");
      li.className = "agency-kpi agency-kpi--" + item.cls;
      li.setAttribute("aria-label", item.value + " — " + item.label);
      const icon = document.createElement("span");
      icon.className = "agency-kpi__icon";
      icon.innerHTML = '<i class="bi ' + item.icon + '" aria-hidden="true"></i>';
      const body = document.createElement("div");
      body.className = "agency-kpi__body";
      const val = document.createElement("span"); val.className = "agency-kpi__value"; val.textContent = item.value;
      const lbl = document.createElement("span"); lbl.className = "agency-kpi__label"; lbl.textContent = item.label;
      const hint = document.createElement("span"); hint.className = "agency-kpi__hint"; hint.textContent = item.hint;
      body.append(val, lbl, hint);
      li.append(icon, body);
      grid.appendChild(li);
    });
    const updatedAtEl = document.getElementById("agency-index-updated");
    if (updatedAtEl) {
      updatedAtEl.innerHTML = '<i class="bi bi-clock" aria-hidden="true"></i> ' + t("آخر تحديث", "Last updated") + ': ' + (generatedAt ? new Date(generatedAt).toLocaleString(LOCALE, { dateStyle: "medium", timeStyle: "short" }) : "—");
    }
  }

  function agencyCard(agency) {
    const li = document.createElement("li");
    li.className = "agency-card agency-card--interactive";
    const readiness = agencyReadiness(agency);
    const dateParams = (state.dateFrom || state.dateTo)
      ? "?" + new URLSearchParams({ date_from: state.dateFrom || "", date_to: state.dateTo || "" }).toString()
      : "";
    const href = "/admin/agency-reports/" + encodeURIComponent(agency.code) + dateParams;

    const head = document.createElement("div");
    head.className = "agency-card__head";
    head.appendChild(window.renderAgencyLogo(agency, 80));
    const titleWrap = document.createElement("div");
    titleWrap.className = "agency-card__title-wrap";
    const h3 = document.createElement("h3");
    h3.className = "agency-card__title";
    h3.textContent = lang === "en" ? (agency.name_en || agency.name_ar) : agency.name_ar;
    titleWrap.append(h3, readinessBadge(readiness));
    head.appendChild(titleWrap);

    const purpose = document.createElement("p");
    purpose.className = "agency-card-desc";
    purpose.textContent = (lang === "en" ? (agency.description_en || agency.description_ar) : agency.description_ar) || "";

    const usage = document.createElement("p");
    usage.className = "agency-card-usage";
    usage.innerHTML = '<strong>' + t("كيفية الاستخدام", "How to use") + ':</strong> ' + t("اختر فترة تجميع البيانات. استخدم الفلاتر لتحديد النطاق الجغرافي. راجع النتائج وصدّرها عند الحاجة.", "Select a data aggregation period. Use filters to define the geographic scope. Review results and export when needed.");

    const updated = document.createElement("p");
    updated.className = "agency-card-updated";
    updated.innerHTML = '<i class="bi bi-clock" aria-hidden="true"></i> ' + t("آخر تحديث", "Last updated") + ': ' + (agency.generated_at ? new Date(agency.generated_at).toLocaleString(LOCALE, { dateStyle: "medium", timeStyle: "short" }) : "—");

    const stats = document.createElement("dl");
    stats.className = "agency-card__stats";
    function stat(labelAr, labelEn, value, cls) {
      const wrap = document.createElement("div");
      wrap.className = "agency-card__stat" + (cls ? " agency-card__stat--" + cls : "");
      const dd = document.createElement("dd"); dd.textContent = value;
      const dt = document.createElement("dt"); dt.textContent = t(labelAr, labelEn);
      wrap.append(dd, dt);
      return wrap;
    }
    stats.append(
      stat("التقارير", "Reports", agency.report_count || 0),
      stat("جاهزة", "Ready", agency.ready_report_count || 0, "success"),
      stat("تحتاج بيانات", "Needs data", agency.requires_data_count || 0, "warning"),
    );

    li.appendChild(head);
    li.appendChild(purpose);
    li.appendChild(usage);
    li.appendChild(updated);
    li.appendChild(stats);

    if (readiness !== "ready" && (agency.requires_data_count || 0) > 0) {
      const note = document.createElement("p");
      note.className = "agency-card__note";
      note.innerHTML = '<i class="bi bi-info-circle" aria-hidden="true"></i> ';
      note.appendChild(document.createTextNode(
        agency.code === "moh"
          ? t("تحتاج التقارير إلى بيانات صحية منظمة.", "These reports need structured health data.")
          : t("بعض التقارير تحتاج إلى بيانات منظمة إضافية.", "Some reports need additional structured data.")
      ));
      li.appendChild(note);
    }

    const link = document.createElement("a");
    link.className = "admin-btn admin-btn-primary agency-card-btn";
    link.href = href;
    link.innerHTML = "<span>" + t("فتح تقارير الجهة", "Open agency reports") + '</span><i class="bi bi-chevron-left icon-directional" aria-hidden="true"></i>';
    link.setAttribute("aria-label", t("عرض تقارير " + (agency.name_ar || agency.code), "View reports for " + (agency.name_en || agency.code)));
    li.appendChild(link);

    // Whole-card affordance without nesting interactive controls: clicking the
    // card background navigates; keyboard users use the real link/inner controls.
    li.addEventListener("click", function (e) {
      if (e.target.closest("a,button")) return;
      window.location.href = href;
    });
    return li;
  }

  function skeletonGrid(n) {
    const ul = document.createElement("ul");
    ul.className = "agency-card-grid";
    ul.setAttribute("aria-hidden", "true");
    for (let i = 0; i < n; i++) {
      const li = document.createElement("li");
      li.className = "agency-card agency-card--skeleton";
      li.innerHTML =
        '<div class="agency-card__head"><span class="sk sk-logo"></span><span class="sk sk-line sk-title"></span></div>' +
        '<span class="sk sk-line"></span><span class="sk sk-line sk-short"></span>' +
        '<div class="agency-card__stats"><span class="sk sk-stat"></span><span class="sk sk-stat"></span><span class="sk sk-stat"></span></div>' +
        '<span class="sk sk-btn"></span>';
      ul.appendChild(li);
    }
    return ul;
  }

  function renderAgency(data) {
    clear(root);

    // Update breadcrumb and page title
    const breadcrumbName = document.getElementById("agency-current-name");
    if (breadcrumbName) breadcrumbName.textContent = lang === "en" ? data.agency_name_en : data.agency_name_ar;
    const titleEl = document.getElementById("agency-reports-title");
    if (titleEl) titleEl.textContent = lang === "en" ? data.agency_name_en : data.agency_name_ar;
    const desc = document.getElementById("agency-description");
    if (desc) desc.textContent = data.description_ar || "";
    const headerUpdated = document.getElementById("agency-header-updated");
    if (headerUpdated) {
      headerUpdated.innerHTML = '<i class="bi bi-clock" aria-hidden="true"></i> ' + t("آخر تحديث", "Last updated") + ': ' + (data.generated_at ? new Date(data.generated_at).toLocaleString(LOCALE, { dateStyle: "medium", timeStyle: "short" }) : "—");
    }

    // Render agency logo in header
    const logoContainer = document.getElementById("agency-logo-container");
    if (logoContainer && window.renderAgencyLogo) {
      const agencyObj = { code: data.agency_code, name_ar: data.agency_name_ar, name_en: data.agency_name_en, icon: data.icon };
      logoContainer.appendChild(window.renderAgencyLogo(agencyObj, 72));
    }

    // Agency explanation
    if (data.description_ar) {
      const expl = document.createElement("div");
      expl.className = "agency-alert agency-alert--info";
      expl.textContent = data.description_ar;
      root.appendChild(expl);
    }

    // Report cards
    const list = document.createElement("ul");
    list.className = "agency-card-grid";
    list.setAttribute("role", "list");

    data.reports.forEach((report) => {
      const li = document.createElement("li");
      li.className = "agency-card agency-report-card";

      const h2 = document.createElement("h2");
      h2.textContent = lang === "en" ? report.title_en : report.title_ar;

      const reportDesc = document.createElement("p");
      reportDesc.className = "agency-card-desc";
      reportDesc.textContent = report.description_ar || "";

      const indicators = document.createElement("p");
      indicators.className = "agency-card-meta";
      indicators.innerHTML = '<strong>' + t("المؤشرات المتاحة", "Available indicators") + ':</strong> ' + (report.data_sources && report.data_sources.length ? report.data_sources.join(", ") : "—");

      const updated = document.createElement("p");
      updated.className = "agency-card-updated";
      const reportUpdated = report.generated_at || data.generated_at;
      updated.innerHTML = '<i class="bi bi-clock" aria-hidden="true"></i> ' + t("آخر تحديث", "Last updated") + ': ' + (reportUpdated ? new Date(reportUpdated).toLocaleString(LOCALE, { dateStyle: "medium", timeStyle: "short" }) : "—");

      const usage = document.createElement("p");
      usage.className = "agency-card-usage";
      usage.innerHTML = '<strong>' + t("كيفية الاستخدام", "How to use") + ':</strong> ' + t("اختر فترة تجميع البيانات. استخدم الفلاتر لتحديد النطاق الجغرافي. راجع النتائج وصدّرها عند الحاجة.", "Select a data aggregation period. Use filters to define the geographic scope. Review results and export when needed.");

      const statusRow = document.createElement("div");
      statusRow.className = "agency-card-meta";
      statusRow.appendChild(statusBadge(report.status));
      if (report.status !== "ready" && report.reason_ar) {
        const reason = document.createElement("span");
        reason.className = "agency-card-reason";
        reason.textContent = report.reason_ar;
        statusRow.appendChild(reason);
      }

      const link = document.createElement("a");
      link.className = "admin-btn admin-btn-primary agency-card-btn" + (report.status !== "ready" ? " disabled" : "");
      link.href = "/admin/agency-reports/" + encodeURIComponent(data.agency_code) + "/" + encodeURIComponent(report.report_code) + (report._dateSuffix || "");
      link.textContent = t("فتح التقرير", "Open Report");
      if (report.status !== "ready") {
        link.setAttribute("aria-disabled", "true");
        link.setAttribute("tabindex", "-1");
      }

      li.append(h2, reportDesc, indicators, updated, usage, statusRow, link);
      list.appendChild(li);
    });

    if (!data.reports.length) {
      const empty = document.createElement("div");
      empty.className = "agency-alert";
      empty.textContent = t("لا توجد تقارير جاهزة حالياً. يرجى استكمال البيانات المطلوبة أو مراجعة إعدادات التكامل.", "No reports available currently. Please complete required data or review integration settings.");
      root.appendChild(empty);
    } else {
      root.appendChild(list);
    }
  }

  function renderReport(payload) {
    clear(root);

    // Populate breadcrumbs and header
    const titleEl = document.getElementById("agency-report-title");
    if (titleEl) titleEl.textContent = lang === "en" ? payload.metadata.report_title_en : payload.metadata.report_title_ar;
    const descEl = document.getElementById("agency-report-description");
    if (descEl) descEl.textContent = payload.metadata.description_ar || "";
    const breadcrumbAgency = document.getElementById("breadcrumb-agency-name");
    if (breadcrumbAgency) {
      breadcrumbAgency.textContent = payload.metadata.agency_name_ar || payload.metadata.agency_code;
      breadcrumbAgency.href = "/admin/agency-reports/" + encodeURIComponent(payload.metadata.agency_code);
    }
    const breadcrumbReport = document.getElementById("breadcrumb-report-name");
    if (breadcrumbReport) breadcrumbReport.textContent = payload.metadata.report_title_ar || payload.metadata.report_code;

    // Agency logo in report header
    const logoEl = document.getElementById("report-agency-logo");
    if (logoEl && window.renderAgencyLogo) {
      const agencyObj = { code: payload.metadata.agency_code, name_ar: payload.metadata.agency_name_ar };
      logoEl.appendChild(window.renderAgencyLogo(agencyObj, 72));
    }

    // Data quality badge
    const dqEl = document.getElementById("agency-data-quality-badge");
    if (dqEl && payload.metadata.data_quality_status) {
      const dqMap = {
        sufficient: { ar: "مؤشر جودة البيانات: كافٍ", en: "Data quality: sufficient", cls: "success" },
        partial: { ar: "مؤشر جودة البيانات: جزئي", en: "Data quality: partial", cls: "warning" },
        limited: { ar: "مؤشر جودة البيانات: محدود", en: "Data quality: limited", cls: "warning" },
        incomplete: { ar: "مؤشر جودة البيانات: غير مكتمل", en: "Data quality: incomplete", cls: "danger" },
      };
      const dq = dqMap[payload.metadata.data_quality_status] || { ar: "مؤشر جودة البيانات: " + payload.metadata.data_quality_status, en: "Data quality: " + payload.metadata.data_quality_status, cls: "default" };
      dqEl.className = "agency-dq-badge agency-dq-badge--" + dq.cls;
      dqEl.innerHTML = '<i class="bi bi-activity" aria-hidden="true"></i> ' + t(dq.ar, dq.en);
    }

    // Executive summary
    const summary = document.createElement("section");
    summary.className = "agency-report-summary";
    summary.setAttribute("aria-labelledby", "agency-summary-title");
    const sumH2 = document.createElement("h2");
    sumH2.id = "agency-summary-title";
    sumH2.textContent = t("ملخص النتائج", "Results Summary");
    const dl = document.createElement("dl");
    const summaryLabels = payload.summary_labels || {};
    Object.entries(payload.summary || {}).forEach(([key, value]) => {
      if (key === "message_ar") return;
      const dt = document.createElement("dt"); dt.textContent = summaryLabels[key] || key;
      const dd = document.createElement("dd"); dd.textContent = value == null ? "—" : String(value);
      dl.append(dt, dd);
    });
    summary.append(sumH2, dl);
    root.appendChild(summary);

    if (payload.unavailable_indicators && payload.unavailable_indicators.length) {
      const alert = document.createElement("div");
      alert.className = "agency-alert agency-alert--warning";
      alert.textContent = payload.summary.message_ar || t("هذا التقرير يتطلب بيانات منظمة إضافية.", "This report requires additional structured data.");
      root.appendChild(alert);
      return;
    }

    // Chart placeholder (if chart data provided)
    if (payload.chart) {
        const chartSection = document.createElement("div");
        chartSection.className = "agency-chart-section";
      const chartTitle = document.createElement("h2");
      chartTitle.className = "agency-chart-title";
      chartTitle.textContent = payload.chart.title_ar || t("الرسم البياني", "Chart");
      chartSection.appendChild(chartTitle);
      const chartContainer = document.createElement("div");
      chartContainer.id = "agency-plotly-chart";
      chartContainer.setAttribute("role", "img");
      chartContainer.setAttribute("aria-label", payload.chart.title_ar || "");
      chartSection.appendChild(chartContainer);
      if (window.Plotly && payload.chart.series && payload.chart.series.length) {
        const labels = payload.chart.series.map((s) => s.label);
        const values = payload.chart.series.map((s) => s.value);
        const total = values.reduce((a, b) => a + (typeof b === "number" ? b : 0), 0);
        const exportBtn = document.createElement("button");
        exportBtn.type = "button";
        exportBtn.className = "admin-btn admin-btn-secondary agency-chart-export-btn";
        exportBtn.innerHTML = '<i class="bi bi-image" aria-hidden="true"></i> ' + t("تصدير الرسم البياني", "Export Chart");
        exportBtn.disabled = true;
        exportBtn.setAttribute("aria-disabled", "true");
        exportBtn.setAttribute("aria-live", "polite");
        exportBtn.setAttribute("aria-label", t("تصدير الرسم البياني كصورة", "Export the current chart as an image"));
        const chartStatus = document.createElement("div");
        chartStatus.className = "visually-hidden";
        chartStatus.setAttribute("aria-live", "polite");
        chartStatus.id = "agency-chart-export-status";
        exportBtn.addEventListener("click", function () {
          if (!window.Plotly || !chartContainer.__chartReady || exportBtn.classList.contains("is-loading")) return;
          exportBtn.disabled = true;
          exportBtn.classList.add("is-loading");
          chartStatus.textContent = t("جارٍ تجهيز ملف الصورة...", "Preparing chart image...");
          window.Plotly.toImage(chartContainer, { format: "png", height: 600, width: 900, scale: 2 })
            .then((dataUrl) => {
              const link = document.createElement("a");
              const generatedAt = payload.metadata.generated_at || payload.metadata.created_at;
              const dateStr = formatDateForFilename(generatedAt);
              link.href = dataUrl;
              link.download = (payload.metadata.report_code || "report") + "_chart_" + dateStr + ".png";
              link.click();
              exportBtn.disabled = false;
              exportBtn.classList.remove("is-loading");
              chartStatus.textContent = t("تم تنزيل الرسم البياني.", "Chart downloaded.");
              chartStatus.focus();
            })
            .catch(() => {
              exportBtn.disabled = false;
              exportBtn.classList.remove("is-loading");
              chartStatus.textContent = t("تعذر تصدير الرسم البياني.", "Unable to export chart.");
              alert(t("تعذر تصدير الرسم البياني. يرجى المحاولة مرة أخرى.", "Unable to export chart. Please try again."));
            });
        });
        chartSection.appendChild(chartStatus);
        chartSection.appendChild(exportBtn);
        root.appendChild(chartSection);

        const isPie = payload.chart.type === "pie";
        const plotData = [{
          type: isPie ? "pie" : "bar",
          name: payload.chart.title_ar || payload.chart.title_en || "",
          labels: labels,
          values: values,
          orientation: !isPie ? "h" : undefined,
          textinfo: isPie ? "label+percent" : "value",
          hovertemplate: "%{label}: %{value} (" + (total ? "%{percent:.1%}" : "0%") + ")<extra></extra>",
        }];
        const layout = {
          margin: { l: 80, r: 30, t: 40, b: 80 },
          height: !isPie ? Math.max(360, labels.length * 36) : 460,
          paper_bgcolor: "transparent",
          plot_bgcolor: "transparent",
          font: { family: "'Inter', 'Segoe UI', system-ui, sans-serif" },
          title: { text: payload.chart.title_ar || payload.chart.title_en || "" },
          xaxis: !isPie ? { tickfont: { size: 13 }, zeroline: false, gridcolor: "rgba(148, 163, 184, 0.25)" } : undefined,
          yaxis: !isPie ? { tickfont: { size: 13 }, automargin: true } : undefined,
        };
        const config = { displaylogo: false, responsive: true, locale: lang === "ar" ? "ar" : "en" };
        window.Plotly.newPlot(chartContainer, plotData, layout, config).then(() => {
          chartContainer.__chartReady = true;
          exportBtn.disabled = false;
          exportBtn.removeAttribute("aria-disabled");
        }).catch(() => {
          exportBtn.remove();
          chartSection.appendChild(document.createTextNode(t("تعذر عرض الرسم البياني.", "Unable to render chart.")));
        });
      } else {
        chartSection.appendChild(document.createTextNode(t("لا تتوفر بيانات للرسم البياني.", "No chart data available.")));
        root.appendChild(chartSection);
      }
    }

    // Data table
    const rows = payload.breakdowns || [];
    if (rows.length) {
      const tableSection = document.createElement("section");
      tableSection.className = "agency-table-section";
      tableSection.setAttribute("aria-labelledby", "agency-table-title");
      const tableTitle = document.createElement("h2");
      tableTitle.id = "agency-table-title";
      tableTitle.textContent = t("جدول البيانات التجميعية", "Aggregated Data Table");
      tableSection.appendChild(tableTitle);

      const table = document.createElement("table");
      table.className = "agency-table";
      const caption = document.createElement("caption");
      caption.textContent = payload.metadata.report_title_ar;
      table.appendChild(caption);
      const columnLabels = payload.column_labels || {};
      const headers = Object.keys(rows[0]);
      const thead = document.createElement("thead");
      const tr = document.createElement("tr");
      headers.forEach((h) => { const th = document.createElement("th"); th.scope = "col"; th.textContent = columnLabels[h] || h; tr.appendChild(th); });
      thead.appendChild(tr);
      table.appendChild(thead);
      const tbody = document.createElement("tbody");
      rows.forEach((row) => { const r = document.createElement("tr"); headers.forEach((h) => { const td = document.createElement("td"); td.textContent = row[h] == null ? "—" : String(row[h]); r.appendChild(td); }); tbody.appendChild(r); });
      table.appendChild(tbody);
      // Totals footer — a standard statistical table always closes with a total.
      // Counts are summed; rate/ratio columns show "—" (never summed).
      const totalRow = payload.total_row;
      if (totalRow) {
        const tfoot = document.createElement("tfoot");
        const ftr = document.createElement("tr");
        ftr.className = "agency-table-total";
        headers.forEach((h) => {
          const td = document.createElement("td");
          const v = totalRow[h];
          td.textContent = (v == null || v === "") ? "" : String(v);
          ftr.appendChild(td);
        });
        tfoot.appendChild(ftr);
        table.appendChild(tfoot);
      }
      tableSection.appendChild(table);
      root.appendChild(tableSection);
    } else {
      const empty = document.createElement("div");
      empty.className = "agency-alert";
      empty.textContent = t("لا توجد بيانات مطابقة للفلاتر المحددة. يرجى تعديل المحافظة أو اللواء أو المنطقة أو الفترة الزمنية.", "No matching data for the selected filters. Please adjust the governorate, district, area or time period.");
      root.appendChild(empty);
    }

    // Methodology & provenance — standardized official-statistics practice: state
    // the definition, source, geographic basis, units, symbols and generation time
    // so figures can be trusted and interpreted without assumptions.
    const meta = payload.metadata || {};
    const provItems = [
      [t("تعريف التقرير", "Definition"), meta.definition_ar],
      [t("مصدر البيانات", "Data source"), meta.data_source_ar],
      [t("الأساس الجغرافي", "Geographic basis"), meta.geography_basis_ar],
      [t("وحدات القياس", "Units"), meta.units_note_ar],
      [t("الرموز", "Symbols"), meta.symbols_note_ar],
      [t("تاريخ الإصدار", "Generated"), meta.generated_at ? new Date(meta.generated_at).toLocaleString(LOCALE, { dateStyle: "medium", timeStyle: "short" }) : null]
    ].filter(function (p) { return p[1]; });
    if (provItems.length) {
      const prov = document.createElement("section");
      prov.className = "agency-provenance";
      prov.setAttribute("aria-labelledby", "agency-prov-title");
      const ph = document.createElement("h2");
      ph.id = "agency-prov-title";
      ph.textContent = t("معلومات ومنهجية التقرير", "Report information & methodology");
      prov.appendChild(ph);
      const pdl = document.createElement("dl");
      pdl.className = "agency-provenance-list";
      provItems.forEach(function (p) {
        const dt = document.createElement("dt"); dt.textContent = p[0];
        const dd = document.createElement("dd"); dd.textContent = p[1];
        pdl.appendChild(dt); pdl.appendChild(dd);
      });
      prov.appendChild(pdl);
      root.appendChild(prov);
    }

    // Export controls — CSV only (no JSON, PDF, Excel, Print)
    const exports = document.createElement("div");
    exports.className = "agency-export-actions";
    const base = "/api/admin/agency-reports/" + encodeURIComponent(payload.metadata.agency_code) + "/reports/" + encodeURIComponent(payload.metadata.report_code);
    if (payload.exports && payload.exports.csv) {
      const date = new Date().toISOString().slice(0, 10);
      const a = document.createElement("a");
      a.href = base + "/export.csv" + window.location.search;
      a.className = "admin-btn admin-btn-secondary";
      a.download = (payload.metadata.report_code || "report") + "_" + date + ".csv";
      a.innerHTML = '<i class="bi bi-file-earmark-spreadsheet" aria-hidden="true"></i> ' + t("تصدير CSV", "Export CSV");
      exports.appendChild(a);
    }
    root.appendChild(exports);
  }

  function loadReport() {
    const agencyCode = page.dataset.agencyCode;
    const reportCode = page.dataset.reportCode;
    const form = document.getElementById("agency-report-filters");
    const formData = form ? new FormData(form) : new FormData();
    // Remove empty values
    const params = new URLSearchParams();
    formData.forEach((v, k) => { if (v && v.trim()) params.set(k, v.trim()); });
    const query = params.toString();

    if (root) root.innerHTML = '<div class="agency-loading" role="status"><i class="bi bi-hourglass-split" aria-hidden="true"></i> ' + t("جاري تحميل البيانات...", "Loading data...") + "</div>";

    api("/api/admin/agency-reports/" + encodeURIComponent(agencyCode) + "/reports/" + encodeURIComponent(reportCode) + (query ? "?" + query : ""))
      .then(renderReport)
      .catch(() => {
        if (root) root.innerHTML = '<div class="agency-alert agency-alert--error"><i class="bi bi-exclamation-circle" aria-hidden="true"></i> ' + t("تعذر تحميل التقرير. يرجى المحاولة مرة أخرى أو التواصل مع مسؤول النظام.", "Unable to load the report. Please try again or contact the system administrator.") + "</div>";
      });
  }

  // -------- Tabs (ARIA tablist) --------
  function activateTab(tabId) {
    const tabs = Array.prototype.slice.call(document.querySelectorAll('.agency-tab[role="tab"]'));
    tabs.forEach((tab) => {
      const selected = tab.id === tabId;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      const panel = document.getElementById(tab.getAttribute("aria-controls"));
      if (panel) panel.hidden = !selected;
    });
  }

  function initTabs() {
    const tabs = Array.prototype.slice.call(document.querySelectorAll('.agency-tab[role="tab"]'));
    if (!tabs.length) return;
    tabs.forEach((tab, idx) => {
      tab.addEventListener("click", () => { activateTab(tab.id); tab.focus(); });
      tab.addEventListener("keydown", (e) => {
        let target = null;
        if (e.key === "ArrowLeft") target = tabs[(idx + 1) % tabs.length];        // RTL: left = next
        else if (e.key === "ArrowRight") target = tabs[(idx - 1 + tabs.length) % tabs.length];
        else if (e.key === "Home") target = tabs[0];
        else if (e.key === "End") target = tabs[tabs.length - 1];
        if (target) { e.preventDefault(); activateTab(target.id); target.focus(); }
      });
    });
  }

  // -------- Usage-guide drawer (native <dialog>: focus trap + Esc) --------
  function initDrawer() {
    const dlg = document.getElementById("usage-guide-dialog");
    const openBtn = document.getElementById("open-usage-guide");
    const closeBtn = document.getElementById("close-usage-guide");
    if (!dlg || !openBtn) return;
    openBtn.addEventListener("click", () => {
      if (typeof dlg.showModal === "function") dlg.showModal(); else dlg.setAttribute("open", "");
    });
    if (closeBtn) closeBtn.addEventListener("click", () => dlg.close());
    dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  }

  const type = page.dataset.agencyReportsPage;

  if (type === "index") {
    initTabs();
    initDrawer();
    const ctaCustom = document.getElementById("cta-create-custom");
    if (ctaCustom) ctaCustom.addEventListener("click", () => { activateTab("tab-custom"); const c = document.getElementById("tab-custom"); if (c) c.focus(); });

    if (root) { clear(root); root.appendChild(skeletonGrid(6)); }

    let allAgencies = [];

    function matches(agency) {
      if (state.status !== "all" && agencyReadiness(agency) !== state.status) return false;
      if (state.search) {
        const q = state.search.toLowerCase();
        const hay = [agency.name_ar, agency.name_en, agency.description_ar, agency.code].filter(Boolean).join(" ").toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    }
    function sortAgencies(list) {
      const arr = list.slice();
      if (state.sort === "reports") arr.sort((a, b) => (b.report_count || 0) - (a.report_count || 0));
      else if (state.sort === "readiness") arr.sort((a, b) => READINESS_RANK[agencyReadiness(a)] - READINESS_RANK[agencyReadiness(b)]);
      else arr.sort((a, b) => String(a.name_ar || "").localeCompare(String(b.name_ar || ""), "ar"));
      return arr;
    }
    function resetFilters() {
      state.search = ""; state.status = "all"; state.sort = "name"; state.dateFrom = ""; state.dateTo = "";
      const s = document.getElementById("agency-search"); if (s) s.value = "";
      const st = document.getElementById("agency-status-filter"); if (st) st.value = "all";
      const so = document.getElementById("agency-sort"); if (so) so.value = "name";
      const df = document.getElementById("agency-date-from"); if (df) df.value = "";
      const dt = document.getElementById("agency-date-to"); if (dt) dt.value = "";
      render();
    }
    function emptyState(hasFilters) {
      const box = document.createElement("div");
      box.className = "agency-empty-state";
      box.innerHTML = '<i class="bi bi-search" aria-hidden="true"></i>';
      const h = document.createElement("p");
      h.className = "agency-empty-state__title";
      h.textContent = hasFilters
        ? t("لم يتم العثور على جهات أو تقارير مطابقة.", "No matching agencies or reports found.")
        : t("لا توجد جهات متاحة حاليًا.", "No agencies are available right now.");
      box.appendChild(h);
      if (hasFilters) {
        const p = document.createElement("p");
        p.textContent = t("جرّب تعديل كلمات البحث أو إزالة بعض عوامل التصفية.", "Try changing your search terms or removing some filters.");
        box.appendChild(p);
        const btn = document.createElement("button");
        btn.type = "button"; btn.className = "admin-btn admin-btn-secondary";
        btn.textContent = t("مسح عوامل التصفية", "Clear filters");
        btn.addEventListener("click", resetFilters);
        box.appendChild(btn);
      }
      return box;
    }
    function render() {
      if (!root) return;
      const filtered = sortAgencies(allAgencies.filter(matches));
      const countEl = document.getElementById("agency-result-count");
      if (countEl) countEl.textContent = t(filtered.length + " من " + allAgencies.length + " جهة", filtered.length + " of " + allAgencies.length + " agencies");
      const active = !!(state.search || state.status !== "all" || state.sort !== "name" || state.dateFrom || state.dateTo);
      const clearBtn = document.getElementById("agency-clear-filters");
      if (clearBtn) clearBtn.hidden = !active;
      clear(root);
      if (!filtered.length) { root.appendChild(emptyState(active)); return; }
      const ul = document.createElement("ul");
      ul.className = "agency-card-grid";
      ul.setAttribute("role", "list");
      filtered.forEach((a) => ul.appendChild(agencyCard(a)));
      root.appendChild(ul);
    }
    function wireToolbar() {
      const toolbar = document.getElementById("agency-toolbar");
      if (toolbar) toolbar.hidden = false;
      const s = document.getElementById("agency-search");
      if (s) {
        let deb;
        s.addEventListener("input", function () {
          clearTimeout(deb);
          deb = setTimeout(() => { state.search = s.value.trim(); render(); }, 250);
        });
      }
      const st = document.getElementById("agency-status-filter");
      if (st) st.addEventListener("change", () => { state.status = st.value; render(); });
      const so = document.getElementById("agency-sort");
      if (so) so.addEventListener("change", () => { state.sort = so.value; render(); });
      const df = document.getElementById("agency-date-from");
      if (df) df.addEventListener("change", () => { state.dateFrom = df.value; render(); });
      const dt = document.getElementById("agency-date-to");
      if (dt) dt.addEventListener("change", () => { state.dateTo = dt.value; render(); });
      const clearBtn = document.getElementById("agency-clear-filters");
      if (clearBtn) clearBtn.addEventListener("click", resetFilters);
    }

    api("/api/admin/agency-reports/catalog")
      .then((data) => {
        allAgencies = data.agencies || [];
        renderKpiGrid(allAgencies);
        wireToolbar();
        render();
      })
      .catch(() => {
        if (!root) return;
        clear(root);
        const err = document.createElement("div");
        err.className = "agency-alert agency-alert--error agency-error-state";
        err.setAttribute("role", "alert");
        err.innerHTML = '<i class="bi bi-exclamation-octagon" aria-hidden="true"></i>';
        const p = document.createElement("p");
        p.textContent = t("تعذر تحميل البيانات. تحقق من الاتصال ثم حاول مرة أخرى.", "Could not load data. Check your connection and try again.");
        err.appendChild(p);
        const retry = document.createElement("button");
        retry.type = "button"; retry.className = "admin-btn admin-btn-secondary";
        retry.textContent = t("إعادة المحاولة", "Retry");
        retry.addEventListener("click", () => window.location.reload());
        err.appendChild(retry);
        root.appendChild(err);
      });
  }

  if (type === "agency") {
    // Read date_from/date_to from the URL query string and pass to report links
    const urlParams = new URLSearchParams(window.location.search);
    const dateFrom = urlParams.get("date_from") || "";
    const dateTo = urlParams.get("date_to") || "";
    const dateSuffix = (dateFrom || dateTo)
      ? "?" + new URLSearchParams({ date_from: dateFrom, date_to: dateTo }).toString()
      : "";

    api("/api/admin/agency-reports/" + encodeURIComponent(page.dataset.agencyCode) + "/reports")
      .then(function(data) {
        // If date params exist, append them to each report's "Open Report" link
        if (dateSuffix && data.reports) {
          data.reports.forEach(function(r) {
            // Store date params so renderAgency can use them
            r._dateSuffix = dateSuffix;
          });
        }
        renderAgency(data);
      })
      .catch(() => {
        if (root) root.textContent = t("تعذر تحميل تقارير الجهة.", "Unable to load agency reports.");
      });
  }

  if (type === "report") {
    const filtersForm = document.getElementById("agency-report-filters");
    if (filtersForm) {
      // Pre-fill date_from/date_to from URL query string if present
      const urlParams = new URLSearchParams(window.location.search);
      const df = urlParams.get("date_from");
      const dt = urlParams.get("date_to");
      if (df) { const el = filtersForm.querySelector("[name=date_from]"); if (el) el.value = df; }
      if (dt) { const el = filtersForm.querySelector("[name=date_to]"); if (el) el.value = dt; }
      filtersForm.addEventListener("submit", (e) => { e.preventDefault(); loadReport(); });
    }
    loadReport();
  }
})();
