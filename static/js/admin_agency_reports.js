(function () {
  "use strict";
  const page = document.querySelector("[data-agency-reports-page]");
  if (!page) return;
  const lang = document.documentElement.lang === "en" ? "en" : "ar";
  const root = document.getElementById("agency-reports-root") || document.getElementById("agency-report-root");
  const api = (path) => fetch(path, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } }).then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
  const t = (ar, en) => lang === "en" ? en : ar;

  function clear(el) { if (el) el.innerHTML = ""; }
  function pill(text, kind) { const span = document.createElement("span"); span.className = "agency-status agency-status--" + (kind || "default"); span.textContent = text; return span; }

  // Official-agency logo/branding badge: renders the registry icon inside a
  // rounded badge; falls back to the agency's initials when no icon is set.
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

  function renderIndex(data) {
    clear(root);
    const list = document.createElement("ul");
    list.className = "agency-card-grid";
    list.setAttribute("role", "list");
    data.agencies.forEach((agency) => {
      const li = document.createElement("li");
      li.className = "agency-card";
      const header = document.createElement("div");
      header.className = "agency-card__head";
      header.appendChild(logoBadge(agency));
      const h2 = document.createElement("h2");
      h2.textContent = lang === "en" ? agency.name_en : agency.name_ar;
      header.appendChild(h2);
      const p = document.createElement("p");
      p.textContent = agency.description_ar || "";
      const meta = document.createElement("div");
      meta.className = "agency-card-meta";
      meta.append(pill(t("التقارير: ", "Reports: ") + agency.report_count, "info"));
      meta.append(pill(t("جاهزة: ", "Ready: ") + agency.ready_report_count, "success"));
      if (agency.requires_data_count) meta.append(pill(t("تحتاج بيانات: ", "Needs data: ") + agency.requires_data_count, "warning"));
      const link = document.createElement("a");
      link.className = "admin-btn admin-btn-primary";
      link.href = "/admin/agency-reports/" + encodeURIComponent(agency.code);
      link.textContent = t("عرض تقارير " + agency.name_ar, "View " + agency.name_en + " reports");
      li.append(header, p, meta, link);
      list.appendChild(li);
    });
    root.appendChild(list);
  }

  function renderAgency(data) {
    clear(root);
    const title = document.getElementById("agency-current-name");
    if (title) title.textContent = lang === "en" ? data.agency_name_en : data.agency_name_ar;
    const desc = document.getElementById("agency-description");
    if (desc) desc.textContent = data.description_ar || "";
    const list = document.createElement("ul");
    list.className = "agency-card-grid";
    list.setAttribute("role", "list");
    data.reports.forEach((report) => {
      const li = document.createElement("li");
      li.className = "agency-card";
      const h2 = document.createElement("h2");
      h2.textContent = lang === "en" ? report.title_en : report.title_ar;
      const status = pill(report.status === "ready" ? t("جاهز", "Ready") : t("يتطلب بيانات منظمة", "Requires structured data"), report.status === "ready" ? "success" : "warning");
      const link = document.createElement("a");
      link.className = "admin-btn admin-btn-primary";
      link.href = "/admin/agency-reports/" + encodeURIComponent(data.agency_code) + "/" + encodeURIComponent(report.report_code);
      link.textContent = t("فتح التقرير", "Open report");
      li.append(h2, status, link);
      list.appendChild(li);
    });
    root.appendChild(list);
  }

  function renderReport(payload) {
    clear(root);
    const title = document.getElementById("agency-report-title");
    if (title) title.textContent = lang === "en" ? payload.metadata.report_title_en : payload.metadata.report_title_ar;
    const summary = document.createElement("section");
    summary.className = "agency-report-summary";
    summary.setAttribute("aria-labelledby", "agency-summary-title");
    const h2 = document.createElement("h2");
    h2.id = "agency-summary-title";
    h2.textContent = t("الملخص التنفيذي", "Executive summary");
    const dl = document.createElement("dl");
    const summaryLabels = payload.summary_labels || {};
    Object.entries(payload.summary || {}).forEach(([key, value]) => { const dt = document.createElement("dt"); dt.textContent = summaryLabels[key] || key; const dd = document.createElement("dd"); dd.textContent = value == null ? "—" : String(value); dl.append(dt, dd); });
    summary.append(h2, dl);
    root.appendChild(summary);

    if (payload.unavailable_indicators && payload.unavailable_indicators.length) {
      const alert = document.createElement("div");
      alert.className = "agency-alert agency-alert--warning";
      alert.textContent = payload.summary.message_ar || t("هذا التقرير يتطلب بيانات منظمة إضافية.", "This report requires additional structured data.");
      root.appendChild(alert);
      return;
    }

    const rows = payload.breakdowns || [];
    const table = document.createElement("table");
    table.className = "agency-table";
    const caption = document.createElement("caption");
    caption.textContent = payload.metadata.report_title_ar;
    table.appendChild(caption);
    const columnLabels = payload.column_labels || {};
    if (rows.length) {
      const headers = Object.keys(rows[0]);
      const thead = document.createElement("thead");
      const tr = document.createElement("tr");
      headers.forEach((h) => { const th = document.createElement("th"); th.scope = "col"; th.textContent = columnLabels[h] || h; tr.appendChild(th); });
      thead.appendChild(tr); table.appendChild(thead);
      const tbody = document.createElement("tbody");
      rows.forEach((row) => { const r = document.createElement("tr"); headers.forEach((h) => { const td = document.createElement("td"); td.textContent = row[h] == null ? "—" : String(row[h]); r.appendChild(td); }); tbody.appendChild(r); });
      table.appendChild(tbody);
      root.appendChild(table);
    } else {
      const empty = document.createElement("div");
      empty.className = "agency-alert";
      empty.textContent = t("لا توجد بيانات مطابقة لهذا التقرير ضمن النطاق المحدد.", "No matching data for this report in the selected scope.");
      root.appendChild(empty);
    }

    const exports = document.createElement("div");
    exports.className = "agency-export-actions";
    const base = "/api/admin/agency-reports/" + encodeURIComponent(payload.metadata.agency_code) + "/reports/" + encodeURIComponent(payload.metadata.report_code);
    if (payload.exports && payload.exports.csv) { const a = document.createElement("a"); a.href = base + "/export.csv" + window.location.search; a.className = "admin-btn admin-btn-secondary"; a.textContent = t("تصدير CSV", "Export CSV"); exports.appendChild(a); }
    if (payload.exports && payload.exports.json) { const a = document.createElement("a"); a.href = base + "/export.json" + window.location.search; a.className = "admin-btn admin-btn-secondary"; a.textContent = t("تصدير JSON", "Export JSON"); exports.appendChild(a); }
    root.appendChild(exports);
  }

  function loadReport() {
    const agencyCode = page.dataset.agencyCode;
    const reportCode = page.dataset.reportCode;
    const form = document.getElementById("agency-report-filters");
    const query = new URLSearchParams(new FormData(form || undefined)).toString();
    api("/api/admin/agency-reports/" + encodeURIComponent(agencyCode) + "/reports/" + encodeURIComponent(reportCode) + (query ? "?" + query : "")).then(renderReport).catch(() => { root.textContent = t("تعذر تحميل التقرير.", "Unable to load report."); });
  }

  const type = page.dataset.agencyReportsPage;
  if (type === "index") api("/api/admin/agency-reports/catalog").then(renderIndex).catch(() => { root.textContent = t("تعذر تحميل الجهات الرسمية.", "Unable to load agencies."); });
  if (type === "agency") api("/api/admin/agency-reports/" + encodeURIComponent(page.dataset.agencyCode) + "/reports").then(renderAgency).catch(() => { root.textContent = t("تعذر تحميل تقارير الجهة.", "Unable to load agency reports."); });
  if (type === "report") {
    document.getElementById("agency-report-filters")?.addEventListener("submit", (e) => { e.preventDefault(); loadReport(); });
    loadReport();
  }
})();
