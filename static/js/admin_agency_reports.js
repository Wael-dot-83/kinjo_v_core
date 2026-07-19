(function () {
  "use strict";
  const page = document.querySelector("[data-agency-reports-page]");
  if (!page) return;
  const lang = document.documentElement.lang === "en" ? "en" : "ar";
  const root = document.getElementById("agency-reports-root") || document.getElementById("agency-report-root");
  const api = (path) => fetch(path, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } }).then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
  const t = (ar, en) => lang === "en" ? en : ar;

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
    ready:      { ar: "جاهز",            en: "Ready",           cls: "success", icon: "bi-check-circle-fill" },
    partial:    { ar: "جاهز جزئيًا",     en: "Partially ready", cls: "info",    icon: "bi-clock-history" },
    needs_data: { ar: "يحتاج إلى بيانات", en: "Needs data",      cls: "warning", icon: "bi-exclamation-triangle-fill" },
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

    let bodyElement = null;
    if (agency.code !== "mosd") {
      const desc = document.createElement("p");
      desc.className = "agency-card-desc";
      desc.textContent = (lang === "en" ? (agency.description_en || agency.description_ar) : agency.description_ar) || "";
      bodyElement = desc;
    }

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
    if (bodyElement) li.appendChild(bodyElement);
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
    link.innerHTML = "<span>" + t("عرض التقارير", "View reports") + '</span><i class="bi bi-chevron-left icon-directional" aria-hidden="true"></i>';
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

      li.append(h2, reportDesc, statusRow, link);
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
      if (window.Chart && payload.chart.series && payload.chart.series.length) {
        const canvas = document.createElement("canvas");
        canvas.id = "agency-report-chart";
        canvas.setAttribute("aria-label", payload.chart.title_ar || "");
        canvas.setAttribute("role", "img");
        chartSection.appendChild(canvas);
        canvas.style.minHeight = "350px";
        const isPie = payload.chart.type === "pie";
        const premiumPalette = ["#4f46e5", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6"];
        const ctx = canvas.getContext("2d");
        const bgColors = payload.chart.series.map((_, i) => {
            if (isPie) return premiumPalette[i % premiumPalette.length];
            const g = ctx.createLinearGradient(0, 0, 0, 400);
            const baseColor = premiumPalette[i % premiumPalette.length];
            g.addColorStop(0, baseColor);
            g.addColorStop(1, baseColor + "80");
            return g;
        });

        if (window.Chart) {
          window.Chart.defaults.font.family = "'Inter', 'Segoe UI', system-ui, sans-serif";
          window.Chart.defaults.color = "#64748b";
        }

        const chartInst = new window.Chart(ctx, {
          type: isPie ? "pie" : "bar",
          data: {
            labels: payload.chart.series.map((s) => s.label),
            datasets: [{ 
              label: payload.chart.title_ar || "", 
              data: payload.chart.series.map((s) => s.value), 
              backgroundColor: bgColors,
              borderWidth: isPie ? 2 : 0,
              borderColor: "#ffffff",
              borderRadius: isPie ? 0 : 8,
              borderSkipped: false,
              hoverOffset: isPie ? 8 : 0
            }]
          },
          options: { 
            responsive: true, 
            maintainAspectRatio: false,
            animation: { duration: 1200, easing: 'easeOutQuart' },
            layout: { padding: { top: 20, bottom: 20 } },
            plugins: { 
              legend: { 
                position: isPie ? "bottom" : "top",
                labels: { padding: 20, usePointStyle: true, pointStyle: 'circle' }
              },
              tooltip: {
                backgroundColor: 'rgba(15, 23, 42, 0.95)',
                titleFont: { size: 14, family: "'Inter', sans-serif" },
                bodyFont: { size: 14, family: "'Inter', sans-serif" },
                padding: 14,
                cornerRadius: 12,
                boxPadding: 6,
                usePointStyle: true
              }
            },
            scales: isPie ? {} : {
                x: {
                    grid: { display: false, drawBorder: false },
                    ticks: { font: { weight: '500' } }
                },
                y: {
                    grid: { color: '#e2e8f0', borderDash: [5, 5], drawBorder: false },
                    beginAtZero: true
                }
            }
          }
        });
        // Chart export button
        const chartExportBtn = document.createElement("button");
        chartExportBtn.type = "button";
        chartExportBtn.className = "admin-btn admin-btn-secondary agency-chart-export-btn";
        chartExportBtn.innerHTML = '<i class="bi bi-image" aria-hidden="true"></i> ' + t("تصدير الرسم البياني", "Export Chart");
        chartExportBtn.addEventListener("click", function () {
          const date = new Date().toISOString().slice(0, 10);
          const link = document.createElement("a");
          link.href = canvas.toDataURL("image/png");
          link.download = (payload.metadata.report_code || "report") + "_chart_" + date + ".png";
          link.click();
        });
        chartSection.appendChild(chartExportBtn);
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
          td.style.fontWeight = "700";
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
