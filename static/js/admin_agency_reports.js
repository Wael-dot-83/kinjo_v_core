(function () {
  "use strict";
  const page = document.querySelector("[data-agency-reports-page]");
  if (!page) return;
  const lang = document.documentElement.lang === "en" ? "en" : "ar";
  const root = document.getElementById("agency-reports-root") || document.getElementById("agency-report-root");
  const api = (path) => fetch(path, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } }).then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
  const t = (ar, en) => lang === "en" ? en : ar;

  async function populateLocationFilters() {
    const govSelect = document.getElementById("filter-governorate");
    const citySelect = document.getElementById("filter-city");
    if (!govSelect) return;

    try {
      const govJson = await api("/api/locations/jordan/governorates");
      (govJson.data && govJson.data.governorates || []).forEach(g => {
        const o = document.createElement("option");
        o.value = g.key;
        o.textContent = g.name_ar;
        govSelect.appendChild(o);
      });
    } catch (e) { console.warn("Failed to load governorates:", e); }

    govSelect.addEventListener("change", async function() {
      if (!citySelect) return;
      const val = this.value;
      if (!val) {
        citySelect.innerHTML = '<option value="">' + t("اختر المحافظة أولاً", "Select governorate first") + '</option>';
        citySelect.disabled = true;
        return;
      }
      citySelect.innerHTML = '<option value="">' + t("جارٍ التحميل...", "Loading...") + '</option>';
      citySelect.disabled = true;
      try {
        const cityJson = await api("/api/locations/jordan/governorates/" + encodeURIComponent(val) + "/areas");
        citySelect.innerHTML = '<option value="">' + t("جميع المناطق", "All areas") + '</option>';
        (cityJson.data && cityJson.data.areas || []).forEach(a => {
          const o = document.createElement("option");
          o.value = a.key;
          o.textContent = a.name_ar;
          citySelect.appendChild(o);
        });
        citySelect.disabled = false;
      } catch (e) {
        citySelect.innerHTML = '<option value="">' + t("جميع المناطق", "All areas") + '</option>';
        citySelect.disabled = false;
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", populateLocationFilters);
  } else {
    populateLocationFilters();
  }

  function clear(el) { if (el) el.innerHTML = ""; }
  function pill(text, kind) { const span = document.createElement("span"); span.className = "agency-status agency-status--" + (kind || "default"); span.textContent = text; return span; }

  function renderIndex(data) {
    clear(root);
    const list = document.createElement("ul");
    list.className = "agency-card-grid";
    list.setAttribute("role", "list");
    data.agencies.forEach((agency) => {
      const li = document.createElement("li");
      li.className = "agency-card";
      li.setAttribute("role", "listitem");

      const header = document.createElement("div");
      header.className = "agency-card__header";
      if (typeof window.renderAgencyLogo === "function") {
        header.appendChild(window.renderAgencyLogo(agency, 56));
      }
      const titles = document.createElement("div");
      titles.className = "agency-card__titles";
      const nameAr = document.createElement("h2");
      nameAr.className = "agency-card__title-ar";
      nameAr.textContent = agency.name_ar;
      titles.appendChild(nameAr);
      if (agency.name_en) {
        const nameEn = document.createElement("p");
        nameEn.className = "agency-card__title-en";
        nameEn.textContent = agency.name_en;
        titles.appendChild(nameEn);
      }
      header.appendChild(titles);
      li.appendChild(header);

      if (agency.description_ar) {
        const purpose = document.createElement("p");
        purpose.className = "agency-card__purpose";
        purpose.textContent = agency.description_ar;
        li.appendChild(purpose);
      }

      const domains = (agency.reports || []).map((r) => r.title_ar).filter(Boolean);
      if (domains.length) {
        const d = document.createElement("p");
        d.className = "agency-domains";
        const strong = document.createElement("strong");
        strong.textContent = t("المجالات: ", "Domains: ");
        d.appendChild(strong);
        d.appendChild(document.createTextNode(domains.join("، ")));
        li.appendChild(d);
      }

      const meta = document.createElement("div");
      meta.className = "agency-card-meta";
      meta.append(pill(t("التقارير: ", "Reports: ") + agency.report_count, "info"));
      meta.append(pill(t("جاهزة: ", "Ready: ") + agency.ready_report_count, "success"));
      if (agency.requires_data_count) meta.append(pill(t("تحتاج بيانات: ", "Needs data: ") + agency.requires_data_count, "warning"));
      li.appendChild(meta);

      const dq = document.createElement("div");
      const good = agency.requires_data_count === 0;
      const dqSpan = document.createElement("span");
      dqSpan.className = "agency-dq " + (good ? "agency-dq--good" : "agency-dq--partial");
      dqSpan.textContent = good ? t("جودة البيانات: جيدة", "Data quality: good")
                                : t("جودة البيانات: جزئية", "Data quality: partial");
      dq.appendChild(dqSpan);
      li.appendChild(dq);

      const link = document.createElement("a");
      link.className = "admin-btn admin-btn-primary";
      link.href = "/admin/agency-reports/" + encodeURIComponent(agency.code);
      link.textContent = t("عرض التقرير", "View report");
      li.appendChild(link);

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
    const header = document.querySelector(".agency-page-header");
    const existing = header ? header.querySelector(".agency-page-header-logo") : null;
    if (header && !existing && typeof window.renderAgencyLogo === "function") {
      const logo = window.renderAgencyLogo({
        code: data.agency_code,
        name_ar: data.agency_name_ar,
        name_en: data.agency_name_en,
        logo: data.logo,
      }, 64);
      logo.classList.add("agency-page-header-logo");
      header.insertBefore(logo, header.firstChild);
    }
    const list = document.createElement("ul");
    list.className = "agency-card-grid";
    list.setAttribute("role", "list");
    data.reports.forEach((report) => {
      const li = document.createElement("li");
      li.className = "agency-card";
      li.setAttribute("role", "listitem");
      const h2 = document.createElement("h2");
      h2.className = "agency-card__title-ar";
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
    Object.entries(payload.summary || {}).forEach(([key, value]) => { const dt = document.createElement("dt"); dt.textContent = key; const dd = document.createElement("dd"); dd.textContent = String(value); dl.append(dt, dd); });
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
    if (rows.length) {
      const headers = Object.keys(rows[0]);
      const thead = document.createElement("thead");
      const tr = document.createElement("tr");
      headers.forEach((h) => { const th = document.createElement("th"); th.scope = "col"; th.textContent = h; tr.appendChild(th); });
      thead.appendChild(tr); table.appendChild(thead);
      const tbody = document.createElement("tbody");
      rows.forEach((row) => { const r = document.createElement("tr"); headers.forEach((h) => { const td = document.createElement("td"); td.textContent = row[h] == null ? "—" : String(row[h]); r.appendChild(td); }); tbody.appendChild(r); });
      table.appendChild(tbody);
    }
    root.appendChild(table);

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
