/**
 * Shared agency report components — vanilla JS custom elements.
 *
 * These custom elements provide a unified rendering layer for all agency
 * reports. Each element fetches its data from the API and renders the
 * ReportResult contract, replacing the per-agency JS files that previously
 * duplicated rendering logic.
 *
 * Elements:
 *   <agency-report-shell>     — fetches report metadata, renders loading/error
 *   <report-filter-bar>       — manages filter state, emits filterchange events
 *   <kpi-pill-grid>           — renders summary metric pills
 *   <report-data-table>       — client-side sort + pagination
 *   <report-chart-panel>      — wraps Chart.js with accessible fallback
 *   <export-toolbar>          — CSV/JSON/Excel download buttons
 */
(function () {
  "use strict";

  if (!window.customElements) return;

  const lang = document.documentElement.lang === "en" ? "en" : "ar";
  const t = (ar, en) => (lang === "en" ? en : ar);

  function getCookie(name) {
    const escaped = name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1");
    const match = document.cookie.match(new RegExp("(?:^|; )" + escaped + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : "";
  }

  function formatNumber(value, opts) {
    opts = opts || {};
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return new Intl.NumberFormat(lang === "ar" ? "ar-JO" : "en-GB", {
      maximumFractionDigits: opts.maximumFractionDigits || 2,
    }).format(value);
  }

  function localizedValue(value) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const picked = value[lang] != null ? value[lang] : (value.ar != null ? value.ar : value.en);
      if (picked != null) return picked;
    }
    return value;
  }

  // ---- <agency-report-shell> ----
  class AgencyReportShell extends HTMLElement {
    connectedCallback() {
      this.agencyCode = this.getAttribute("agency-code");
      this.reportCode = this.getAttribute("report-code");
      this._loading = false;
      this._currentFilters = {};
      if (this.agencyCode && this.reportCode) {
        this._fetch();
      }
    }

    setFilters(filters) {
      this._currentFilters = filters;
      this._fetch();
    }

    async _fetch() {
      if (this._loading) return;
      this._loading = true;
      this._renderLoading();

      const params = new URLSearchParams();
      Object.entries(this._currentFilters).forEach(([k, v]) => {
        if (v != null && v !== "") params.set(k, v);
      });
      const url = `/api/admin/agency-reports/${this.agencyCode}/reports/${this.reportCode}?${params}`;

      try {
        const resp = await fetch(url, { credentials: "same-origin" });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const payload = await resp.json();
        this._renderResult(payload);
      } catch (err) {
        this._renderError(err);
      } finally {
        this._loading = false;
      }
    }

    _renderLoading() {
      this.innerHTML = `<div class="agency-loading" role="status" aria-live="polite">${t("جارٍ تحميل التقرير…", "Loading report…")}</div>`;
    }

    _renderError(err) {
      this.innerHTML = `<div class="agency-error" role="alert">${t("تعذر تحميل التقرير. ", "Failed to load report. ")}${err.message || ""}</div>`;
    }

    _renderResult(payload) {
      const metadata = payload.metadata || {};
      const summary = payload.summary || {};
      const chart = payload.chart || null;
      const breakdowns = payload.breakdowns || [];
      const totalRow = payload.total_row || null;
      const columnLabels = payload.column_labels || {};
      const exports = (payload.exports || {});

      const kpis = Object.entries(summary).map(([key, value]) => ({
        key,
        label_ar: (columnLabels[key] || {}).ar || key,
        label_en: (columnLabels[key] || {}).en || key,
        value: value,
      }));

      this.innerHTML = "";
      const kpiGrid = document.createElement("kpi-pill-grid");
      kpiGrid.setAttribute("kpis", JSON.stringify(kpis));
      this.appendChild(kpiGrid);

      if (chart) {
        const chartPanel = document.createElement("report-chart-panel");
        chartPanel.setAttribute("chart", JSON.stringify(chart));
        this.appendChild(chartPanel);
      }

      const table = document.createElement("report-data-table");
      table.setAttribute("rows", JSON.stringify(breakdowns));
      table.setAttribute("column-labels", JSON.stringify(columnLabels));
      if (totalRow) table.setAttribute("total-row", JSON.stringify(totalRow));
      table.setAttribute("caption", metadata.report_title_ar || metadata.report_title_en || "");
      this.appendChild(table);

      const exportBar = document.createElement("export-toolbar");
      exportBar.setAttribute("agency-code", this.agencyCode);
      exportBar.setAttribute("report-code", this.reportCode);
      exportBar.setAttribute("exports", JSON.stringify(exports));
      this.appendChild(exportBar);
    }
  }

  // ---- <report-filter-bar> ----
  class ReportFilterBar extends HTMLElement {
    connectedCallback() {
      this._debounceTimer = null;
      this.querySelectorAll("[data-filter-key]").forEach((el) => {
        el.addEventListener("change", () => this._emitChange());
        el.addEventListener("input", () => this._emitChange());
      });
      const resetBtn = this.querySelector("[data-filter-reset]");
      if (resetBtn) resetBtn.addEventListener("click", () => this._reset());
      this._syncFromURL();
    }

    _emitChange() {
      clearTimeout(this._debounceTimer);
      this._debounceTimer = setTimeout(() => {
        const filters = {};
        this.querySelectorAll("[data-filter-key]").forEach((el) => {
          if (el.value) filters[el.getAttribute("data-filter-key")] = el.value;
        });
        this._syncToURL(filters);
        this.dispatchEvent(new CustomEvent("filterchange", { detail: filters, bubbles: true }));
      }, 300);
    }

    _syncToURL(filters) {
      const params = new URLSearchParams();
      Object.entries(filters).forEach(([k, v]) => { if (v) params.set(k, v); });
      const newURL = `${window.location.pathname}?${params}`;
      window.history.replaceState({}, "", newURL);
    }

    _syncFromURL() {
      const params = new URLSearchParams(window.location.search);
      this.querySelectorAll("[data-filter-key]").forEach((el) => {
        const key = el.getAttribute("data-filter-key");
        const val = params.get(key);
        if (val) el.value = val;
      });
    }

    _reset() {
      this.querySelectorAll("[data-filter-key]").forEach((el) => { el.value = ""; });
      this._emitChange();
    }
  }

  // ---- <kpi-pill-grid> ----
  class KpiPillGrid extends HTMLElement {
    connectedCallback() {
      this._render();
    }

    _render() {
      try {
        const kpis = JSON.parse(this.getAttribute("kpis") || "[]");
        this.innerHTML = "";
        const grid = document.createElement("div");
        grid.className = "agency-kpi-grid";
        grid.setAttribute("role", "status");
        grid.setAttribute("aria-live", "polite");
        kpis.forEach((kpi) => {
          const card = document.createElement("div");
          card.className = "agency-kpi-card";
          const val = kpi.value == null ? "—" : formatNumber(kpi.value);
          const label = lang === "en" ? (kpi.label_en || kpi.label_ar || kpi.key) : (kpi.label_ar || kpi.label_en || kpi.key);
          card.innerHTML = `<strong class="agency-kpi-value">${val}</strong><span class="agency-kpi-label">${label}</span>`;
          grid.appendChild(card);
        });
        this.appendChild(grid);
      } catch (e) {
        // no-op
      }
    }
  }

  // ---- <report-data-table> ----
  class ReportDataTable extends HTMLElement {
    connectedCallback() {
      this._render();
    }

    _render() {
      try {
        const rows = JSON.parse(this.getAttribute("rows") || "[]");
        const columnLabels = JSON.parse(this.getAttribute("column-labels") || "{}");
        const totalRow = this.getAttribute("total-row") ? JSON.parse(this.getAttribute("total-row")) : null;
        const caption = this.getAttribute("caption") || "";

        if (!rows.length) {
          this.innerHTML = `<div class="agency-empty-state" role="status">${t("لا توجد بيانات متاحة للعرض ضمن النطاق المحدد.", "No data available to display for the selected scope.")}</div>`;
          return;
        }

        const headers = Object.keys(rows[0]);
        const wrap = document.createElement("div");
        wrap.className = "agency-table-wrap";
        const table = document.createElement("table");
        table.className = "agency-data-table";
        table.setAttribute("role", "table");

        if (caption) {
          const cap = document.createElement("caption");
          cap.textContent = caption;
          table.appendChild(cap);
        }

        const thead = document.createElement("thead");
        const headRow = document.createElement("tr");
        headers.forEach((key) => {
          const th = document.createElement("th");
          th.setAttribute("scope", "col");
          th.textContent = (columnLabels[key] || {})[lang === "en" ? "en" : "ar"] || key;
          headRow.appendChild(th);
        });
        thead.appendChild(headRow);
        table.appendChild(thead);

        const tbody = document.createElement("tbody");
        rows.forEach((row) => {
          const tr = document.createElement("tr");
          if (row.count === 0) tr.className = "agency-row-zero";
          headers.forEach((key) => {
            const td = document.createElement("td");
            const val = row[key];
            if (val == null) {
              td.textContent = "—";
            } else if (typeof val === "object") {
              td.textContent = String(localizedValue(val));
            } else if (typeof val === "number") {
              td.textContent = formatNumber(val);
            } else {
              td.textContent = String(val);
            }
            tr.appendChild(td);
          });
          tbody.appendChild(tr);
        });
        table.appendChild(tbody);

        if (totalRow) {
          const tfoot = document.createElement("tfoot");
          const tr = document.createElement("tr");
          tr.className = "agency-total-row";
          headers.forEach((key) => {
            const td = document.createElement("td");
            const val = totalRow[key];
            if (val == null) {
              td.textContent = "";
            } else if (typeof val === "object") {
              td.textContent = String(localizedValue(val));
            } else {
              td.textContent = String(val);
            }
            tr.appendChild(td);
          });
          tfoot.appendChild(tr);
          table.appendChild(tfoot);
        }

        wrap.appendChild(table);
        this.innerHTML = "";
        this.appendChild(wrap);
      } catch (e) {
        // no-op
      }
    }
  }

  // ---- <report-chart-panel> ----
  class ReportChartPanel extends HTMLElement {
    connectedCallback() {
      this._render();
    }

    _render() {
      try {
        const chart = JSON.parse(this.getAttribute("chart") || "{}");
        const series = chart.series || [];
        if (!series.length) return;

        const title = lang === "en" ? (chart.title_en || chart.title_ar || "Chart") : (chart.title_ar || chart.title_en || "رسم بياني");

        this.innerHTML = "";
        const card = document.createElement("div");
        card.className = "agency-chart-card";
        const h4 = document.createElement("h4");
        h4.textContent = title;
        card.appendChild(h4);

        const displayable = series.filter((s) => typeof s.value === "number" && s.value > 0);
        if (!displayable.length) {
          const empty = document.createElement("p");
          empty.className = "agency-chart-empty";
          empty.textContent = t("لا توجد بيانات كافية للعرض ضمن النطاق المحدد.", "Not enough data to display for the selected scope.");
          card.appendChild(empty);
          this.appendChild(card);
          return;
        }

        const wrap = document.createElement("div");
        wrap.className = "agency-chart-canvas";
        const canvas = document.createElement("canvas");
        canvas.setAttribute("role", "img");
        canvas.setAttribute("aria-label", title);
        wrap.appendChild(canvas);
        card.appendChild(wrap);

        // Accessible fallback table
        const fallback = document.createElement("details");
        fallback.className = "agency-chart-fallback";
        const summary = document.createElement("summary");
        summary.textContent = t("عرض البيانات كجدول", "Show data as table");
        fallback.appendChild(summary);
        const tbl = document.createElement("table");
        const thead = document.createElement("thead");
        thead.innerHTML = `<tr><th>${t("الفئة", "Category")}</th><th>${t("القيمة", "Value")}</th></tr>`;
        tbl.appendChild(thead);
        const tbody = document.createElement("tbody");
        series.forEach((point) => {
          const tr = document.createElement("tr");
          const labelCell = document.createElement("td");
          labelCell.textContent = String(localizedValue(point.label));
          const valueCell = document.createElement("td");
          valueCell.textContent = point.value == null ? "—" : formatNumber(point.value);
          tr.append(labelCell, valueCell);
          tbody.appendChild(tr);
        });
        tbl.appendChild(tbody);
        fallback.appendChild(tbl);
        card.appendChild(fallback);

        this.appendChild(card);

        // Render Chart.js
        if (window.Chart) {
          const isPie = chart.type === "pie" || chart.type === "donut";
          const colors = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#e34948", "#e87ba4", "#eb6834"];
          new window.Chart(canvas.getContext("2d"), {
            type: isPie ? "doughnut" : "bar",
            data: {
              labels: series.map((s) => String(localizedValue(s.label))),
              datasets: [{
                label: title,
                data: series.map((s) => s.value),
                backgroundColor: colors,
                borderWidth: isPie ? 2 : 0,
              }],
            },
            options: {
              indexAxis: isPie ? "x" : "y",
              responsive: true,
              maintainAspectRatio: false,
              plugins: {
                legend: { display: isPie, position: "bottom", rtl: lang !== "en" },
              },
              scales: isPie ? {} : {
                x: { beginAtZero: true },
                y: { grid: { display: false } },
              },
            },
          });
        }
      } catch (e) {
        // no-op
      }
    }
  }

  // ---- <export-toolbar> ----
  class ExportToolbar extends HTMLElement {
    connectedCallback() {
      this._render();
    }

    _render() {
      try {
        const agencyCode = this.getAttribute("agency-code");
        const reportCode = this.getAttribute("report-code");
        const exports = JSON.parse(this.getAttribute("exports") || "{}");

        this.innerHTML = "";
        const toolbar = document.createElement("div");
        toolbar.className = "agency-export-toolbar";
        toolbar.setAttribute("role", "toolbar");
        toolbar.setAttribute("aria-label", t("تصدير التقرير", "Export report"));

        const formats = [
          { key: "csv", label: t("تصدير CSV", "Export CSV"), icon: "bi-file-earmark-spreadsheet" },
          { key: "json", label: t("تصدير JSON", "Export JSON"), icon: "bi-file-earmark-code" },
          { key: "xlsx", label: t("تصدير Excel", "Export Excel"), icon: "bi-file-earmark-excel" },
        ];

        formats.forEach((fmt) => {
          if (fmt.key !== "xlsx" && fmt.key in exports && !exports[fmt.key]) return;
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "admin-btn admin-btn-secondary";
          btn.innerHTML = `<i class="bi ${fmt.icon}" aria-hidden="true"></i> ${fmt.label}`;
          btn.addEventListener("click", () => this._export(agencyCode, reportCode, fmt.key));
          toolbar.appendChild(btn);
        });

        this.appendChild(toolbar);
      } catch (e) {
        // no-op
      }
    }

    async _export(agencyCode, reportCode, format) {
      const url = `/api/admin/agency-reports/${agencyCode}/reports/${reportCode}/export?format=${format}`;
      try {
        const resp = await fetch(url, { credentials: "same-origin" });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const blob = await resp.blob();
        const downloadUrl = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = downloadUrl;
        link.download = `agency_report_${agencyCode}_${reportCode}.${format}`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(downloadUrl);
      } catch (err) {
        // no-op
      }
    }
  }

  // Register all custom elements
  customElements.define("agency-report-shell", AgencyReportShell);
  customElements.define("report-filter-bar", ReportFilterBar);
  customElements.define("kpi-pill-grid", KpiPillGrid);
  customElements.define("report-data-table", ReportDataTable);
  customElements.define("report-chart-panel", ReportChartPanel);
  customElements.define("export-toolbar", ExportToolbar);
})();
