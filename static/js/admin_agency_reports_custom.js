/* Custom Reports (التقارير المخصصة) builder for /admin/agency-reports.
 * Backend-driven: options come from /api/admin/agency-reports/custom/schema,
 * results from POST /api/admin/agency-reports/custom. Aggregated data only.
 */
(function () {
  "use strict";

  const form = document.getElementById("custom-report-form");
  if (!form) return;

  const controls = document.getElementById("custom-report-controls");
  const actionBar = document.getElementById("custom-report-action-bar");
  const resultBox = document.getElementById("custom-report-result");
  const lang = document.documentElement.lang === "en" ? "en" : "ar";
  const t = (ar, en) => (lang === "en" ? en : ar);
  const chartInstances = [];

  function getCookie(name) {
    const match = document.cookie.match(new RegExp("(?:^|; )" + name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1") + "=([^;]*)"));
    return match ? decodeURIComponent(match[1]) : "";
  }

  function apiGet(path) {
    return fetch(path, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
  }

  function apiPost(path, body) {
    return fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRF-Token": getCookie("kinjo_csrf_token"),
      },
      body: JSON.stringify(body),
    });
  }

  function el(tag, opts) {
    const node = document.createElement(tag);
    if (!opts) return node;
    if (opts.class) node.className = opts.class;
    if (opts.text != null) node.textContent = opts.text;
    if (opts.attrs) Object.keys(opts.attrs).forEach((k) => node.setAttribute(k, opts.attrs[k]));
    (opts.children || []).forEach((c) => c && node.appendChild(c));
    return node;
  }

  function labelledSelect(id, labelText, options, valueKey, labelKey) {
    const wrap = el("div", { class: "custom-field" });
    const label = el("label", { text: labelText, attrs: { for: id } });
    const select = el("select", { attrs: { id, name: id, class: "form-select" } });
    options.forEach((opt) => {
      const o = el("option", { text: lang === "en" ? (opt.name_en || opt.name_ar) : opt.name_ar });
      o.value = opt[valueKey];
      select.appendChild(o);
    });
    wrap.append(label, select);
    return wrap;
  }

  function textField(id, labelText, type) {
    const wrap = el("div", { class: "custom-field" });
    const label = el("label", { text: labelText, attrs: { for: id } });
    const input = el("input", { attrs: { id, name: id, type: type || "text", class: "form-control", autocomplete: "off" } });
    wrap.append(label, input);
    return wrap;
  }

  let schemaAgencies = [];
  function renderAgencyPreview(code) {
    const box = document.getElementById("cr-agency-preview");
    if (!box) return;
    const agency = schemaAgencies.find((a) => a.code === code);
    if (!agency) { box.hidden = true; box.innerHTML = ""; return; }
    box.hidden = false;
    box.innerHTML = "";
    const wrap = el("div", { class: "custom-agency-option", attrs: { "aria-hidden": "true" } });
    if (typeof window.renderAgencyLogo === "function") wrap.appendChild(window.renderAgencyLogo(agency, 48));
    const text = el("div", { class: "custom-agency-preview-text" });
    const name = el("div", { class: "custom-agency-preview-name", text: agency.name_ar });
    text.appendChild(name);
    if (agency.description_ar) text.appendChild(el("div", { class: "custom-agency-preview-desc", text: agency.description_ar }));
    wrap.appendChild(text);
    box.appendChild(wrap);
  }

  function buildControls(schema) {
    schemaAgencies = schema.agencies || [];
    controls.innerHTML = "";
    controls.removeAttribute("aria-busy");

    const row1 = el("div", { class: "custom-report-row" });
    row1.append(
      labelledSelect("cr-agency", t("الجهة المستفيدة", "Agency"), schema.agencies, "code"),
      labelledSelect("cr-level", t("مستوى التقرير", "Level"), schema.levels, "code"),
      labelledSelect("cr-period", t("الفترة الزمنية", "Period"), schema.periods, "code"),
    );
    controls.appendChild(row1);

    const customDates = el("div", { class: "custom-report-row", attrs: { id: "cr-custom-dates", hidden: "hidden" } });
    customDates.append(
      textField("cr-start", t("من تاريخ", "Start date"), "date"),
      textField("cr-end", t("إلى تاريخ", "End date"), "date"),
    );
    controls.appendChild(customDates);

    const row2 = el("div", { class: "custom-report-row" });
    const govSelect = el("select", { attrs: { id: "cr-governorate", name: "cr-governorate", class: "form-select" } });
    govSelect.appendChild(el("option", { attrs: { value: "" }, text: t("كل المحافظات", "All Governorates") }));
    const citySelect = el("select", { attrs: { id: "cr-city", name: "cr-city", class: "form-select", disabled: "disabled" } });
    citySelect.appendChild(el("option", { attrs: { value: "" }, text: t("اختر المحافظة أولاً", "Select governorate first") }));
    row2.append(
      el("label", { text: t("المحافظة (اختياري)", "Governorate (optional)"), attrs: { for: "cr-governorate", class: "form-label small" } }),
      govSelect,
      el("label", { text: t("المدينة أو اللواء (اختياري)", "City/District (optional)"), attrs: { for: "cr-city", class: "form-label small" } }),
      citySelect,
      textField("cr-kindergarten", t("معرف الحضانة (اختياري)", "Kindergarten ID (optional)"), "number"),
    );
    controls.appendChild(row2);

    const domainsWrap = el("div", { class: "custom-report-domains" });
    domainsWrap.appendChild(el("h3", { class: "custom-report-domains-title", text: t("مجالات ومؤشرات التقرير", "Report domains & indicators") }));
    schema.domains.forEach((domain) => {
      const fs = el("fieldset", { class: "custom-domain" });
      fs.appendChild(el("legend", { text: lang === "en" ? (domain.name_en || domain.name_ar) : domain.name_ar }));
      domain.indicators.forEach((ind) => {
        const wrap = el("label", { class: "custom-indicator" });
        const cb = el("input", { attrs: { type: "checkbox", name: "indicator", value: ind.code } });
        if (ind.status !== "ready") {
          cb.setAttribute("data-requires-data", "1");
          wrap.classList.add("custom-indicator--needs-data");
        }
        const span = el("span", { text: ind.name_ar + (ind.status !== "ready" ? t(" (يتطلب بيانات)", " (needs data)") : "") });
        wrap.append(cb, span);
        fs.appendChild(wrap);
      });
      domainsWrap.appendChild(fs);
    });
    controls.appendChild(domainsWrap);

    const periodSel = document.getElementById("cr-period");
    periodSel.addEventListener("change", () => {
      customDates.hidden = periodSel.value !== "custom";
    });

    const agencySel = document.getElementById("cr-agency");
    if (agencySel) {
      agencySel.addEventListener("change", () => renderAgencyPreview(agencySel.value));
      renderAgencyPreview(agencySel.value);
    }

    actionBar.hidden = false;
  }

  function collectScope() {
    const indicators = Array.prototype.slice
      .call(form.querySelectorAll('input[name="indicator"]:checked'))
      .map((c) => c.value);
    const govSelect = document.getElementById("cr-governorate");
    const citySelect = document.getElementById("cr-city");
    const scope = {
      agency: document.getElementById("cr-agency").value,
      level: document.getElementById("cr-level").value,
      period: document.getElementById("cr-period").value,
      indicators,
      governorate: govSelect && govSelect.value || null,
      city: citySelect && citySelect.value || null,
      kindergarten_id: document.getElementById("cr-kindergarten").value.trim() || null,
    };
    if (scope.period === "custom") {
      scope.start_date = document.getElementById("cr-start").value || null;
      scope.end_date = document.getElementById("cr-end").value || null;
    }
    return scope;
  }

  function setState(kind, message) {
    resultBox.innerHTML = "";
    const box = el("div", { class: "custom-report-state custom-report-state--" + kind, text: message });
    resultBox.appendChild(box);
  }

  function destroyCharts() {
    while (chartInstances.length) {
      try { chartInstances.pop().destroy(); } catch (e) { /* noop */ }
    }
  }

  function renderKpis(kpis) {
    const grid = el("div", { class: "custom-kpi-grid" });
    kpis.forEach((k) => {
      const card = el("div", { class: "custom-kpi-card" });
      card.append(
        el("div", { class: "custom-kpi-value", text: String(k.value) + (k.unit_ar ? " " + k.unit_ar : "") }),
        el("div", { class: "custom-kpi-label", text: k.label_ar }),
      );
      grid.appendChild(card);
    });
    return grid;
  }

  function renderCharts(charts) {
    const wrap = el("div", { class: "custom-charts" });
    charts.forEach((chart, i) => {
      const card = el("div", { class: "custom-chart-card" });
      card.appendChild(el("h4", { text: chart.title_ar }));
      const series = chart.series || [];
      if (window.Chart && series.length) {
        const canvas = el("canvas", { attrs: { id: "cr-chart-" + i, "aria-label": chart.title_ar, role: "img" } });
        card.appendChild(canvas);
        wrap.appendChild(card);
        const inst = new window.Chart(canvas.getContext("2d"), {
          type: chart.type === "pie" ? "pie" : "bar",
          data: {
            labels: series.map((s) => s.label),
            datasets: [{ label: chart.title_ar, data: series.map((s) => s.value), backgroundColor: ["#1f6f54", "#2f8f6d", "#c0392b", "#e0a90e", "#2b6cb0", "#6b46c1", "#718096"] }],
          },
          options: { responsive: true, plugins: { legend: { position: chart.type === "pie" ? "bottom" : "top" } } },
        });
        chartInstances.push(inst);
      } else {
        // Accessible textual fallback when Chart.js is unavailable / no data.
        const ul = el("ul", { class: "custom-chart-fallback" });
        series.forEach((s) => ul.appendChild(el("li", { text: s.label + ": " + s.value })));
        card.appendChild(series.length ? ul : el("p", { text: t("لا توجد بيانات لعرضها.", "No data to display.") }));
        wrap.appendChild(card);
      }
    });
    return wrap;
  }

  function renderTable(rows) {
    const card = el("div", { class: "custom-table-card" });
    card.appendChild(el("h4", { text: t("جدول تفصيلي", "Detailed table") }));
    if (!rows.length) {
      card.appendChild(el("p", { text: t("لا توجد صفوف تفصيلية.", "No detailed rows.") }));
      return card;
    }
    const headers = [];
    rows.forEach((r) => Object.keys(r).forEach((k) => { if (headers.indexOf(k) === -1) headers.push(k); }));
    const table = el("table", { class: "custom-table admin-table", attrs: { dir: lang === "en" ? "ltr" : "rtl" } });
    const thead = el("thead");
    const htr = el("tr");
    headers.forEach((h) => htr.appendChild(el("th", { text: h, attrs: { scope: "col" } })));
    thead.appendChild(htr);
    const tbody = el("tbody");
    rows.forEach((r) => {
      const tr = el("tr");
      headers.forEach((h) => tr.appendChild(el("td", { text: r[h] != null ? String(r[h]) : "—" })));
      tbody.appendChild(tr);
    });
    table.append(thead, tbody);
    const scroll = el("div", { class: "custom-table-scroll", attrs: { tabindex: "0", role: "region", "aria-label": t("جدول تفصيلي", "Detailed table") } });
    scroll.appendChild(table);
    card.appendChild(scroll);
    return card;
  }

  function dataQualityLabel(status) {
    return {
      sufficient: t("كافية", "Sufficient"),
      limited: t("محدودة", "Limited"),
      incomplete: t("غير مكتملة", "Incomplete"),
    }[status] || status;
  }

  function render(data) {
    destroyCharts();
    resultBox.innerHTML = "";

    const header = el("div", { class: "custom-report-result-header" });
    header.appendChild(el("h3", { text: (data.title || t("تقرير مخصص", "Custom report")) + " — " + (data.scope.agency_name_ar || data.scope.agency) }));
    const dq = el("span", { class: "custom-dq custom-dq--" + (data.data_quality.status || "incomplete"), text: t("حالة البيانات: ", "Data quality: ") + dataQualityLabel(data.data_quality.status) });
    header.appendChild(dq);
    resultBox.appendChild(header);

    resultBox.appendChild(el("p", { class: "custom-report-scope", text: t("النطاق: ", "Scope: ") + [data.scope.level_name_ar, data.scope.governorate, data.scope.city].filter(Boolean).join(" / ") + " · " + data.scope.start_date + " → " + data.scope.end_date }));

    if ((data.kpis || []).length) resultBox.appendChild(renderKpis(data.kpis));
    if ((data.charts || []).length) resultBox.appendChild(renderCharts(data.charts));
    resultBox.appendChild(renderTable(data.table || []));

    if (data.summary_ar) {
      const sum = el("div", { class: "custom-summary" });
      sum.append(el("h4", { text: t("ملخص تنفيذي", "Executive summary") }), el("p", { text: data.summary_ar }));
      resultBox.appendChild(sum);
    }
    if ((data.decision_notes_ar || []).length) {
      const notes = el("div", { class: "custom-decision-notes" });
      notes.appendChild(el("h4", { text: t("ملاحظات لدعم القرار", "Decision-support notes") }));
      const ul = el("ul");
      data.decision_notes_ar.forEach((n) => ul.appendChild(el("li", { text: n })));
      notes.appendChild(ul);
      resultBox.appendChild(notes);
    }
    if ((data.data_quality.notes || []).length) {
      const dqn = el("div", { class: "custom-dq-notes" });
      dqn.appendChild(el("h4", { text: t("ملاحظات جودة البيانات", "Data-quality notes") }));
      const ul = el("ul");
      data.data_quality.notes.forEach((n) => ul.appendChild(el("li", { text: n })));
      dqn.appendChild(ul);
      resultBox.appendChild(dqn);
    }

    // Export controls — only those supported by the backend, plus browser print.
    const exportBar = el("div", { class: "custom-export-bar" });
    const csvBtn = el("button", { class: "admin-btn admin-btn-secondary", text: t("تصدير CSV", "Export CSV"), attrs: { type: "button" } });
    csvBtn.addEventListener("click", () => exportCsv());
    const printBtn = el("button", { class: "admin-btn admin-btn-secondary", text: t("طباعة", "Print"), attrs: { type: "button" } });
    printBtn.addEventListener("click", () => window.print());
    exportBar.append(csvBtn, printBtn);
    resultBox.appendChild(exportBar);
  }

  function exportCsv() {
    apiPost("/api/admin/agency-reports/custom/export.csv", collectScope())
      .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.blob(); })
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = el("a", { attrs: { href: url, download: "custom_agency_report.csv" } });
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      })
      .catch(() => setState("error", t("تعذّر تصدير الملف.", "Export failed.")));
  }

  function run() {
    const scope = collectScope();
    if (!scope.indicators.length) {
      setState("empty", t("اختر مؤشرًا واحدًا على الأقل ثم أنشئ التقرير.", "Select at least one indicator, then generate the report."));
      return;
    }
    setState("loading", t("جارٍ إنشاء التقرير...", "Generating report..."));
    apiPost("/api/admin/agency-reports/custom", scope)
      .then((r) => r.json().then((body) => ({ ok: r.ok, body })))
      .then(({ ok, body }) => {
        if (!ok) {
          const msg = (body && body.detail) ? body.detail : t("تعذّر إنشاء التقرير.", "Could not generate the report.");
          setState("error", msg);
          return;
        }
        render(body.data);
      })
      .catch(() => setState("error", t("حدث خطأ غير متوقع أثناء إنشاء التقرير.", "An unexpected error occurred.")));
  }

  form.addEventListener("submit", (e) => { e.preventDefault(); run(); });
  const resetBtn = document.getElementById("custom-report-reset");
  if (resetBtn) resetBtn.addEventListener("click", () => { form.reset(); destroyCharts(); resultBox.innerHTML = ""; const cd = document.getElementById("cr-custom-dates"); if (cd) cd.hidden = true; });

  apiGet("/api/admin/agency-reports/custom/schema")
    .then((res) => buildControls(res.data))
    .catch(() => {
      controls.removeAttribute("aria-busy");
      controls.textContent = t("تعذّر تحميل خيارات التقرير المخصص.", "Could not load custom report options.");
    });

  async function populateLocationFilters() {
    const govSelect = document.getElementById("cr-governorate");
    const citySelect = document.getElementById("cr-city");
    if (!govSelect) return;
    try {
      const resp = await fetch("/api/locations/jordan/governorates", { credentials: "same-origin" });
      if (!resp.ok) return;
      const json = await resp.json();
      const governorates = (json.data && json.data.governorates) || [];
      governorates.forEach(g => {
        const opt = document.createElement("option");
        opt.value = g.key;
        opt.textContent = g.name_ar;
        govSelect.appendChild(opt);
      });
    } catch (e) { console.warn("Failed to load governorates:", e); }

    govSelect.addEventListener("change", async function() {
      const val = this.value;
      if (!val || !citySelect) {
        if (citySelect) {
          citySelect.innerHTML = '<option value="">' + t("اختر المحافظة أولاً", "Select governorate first") + '</option>';
          citySelect.disabled = true;
        }
        return;
      }
      citySelect.innerHTML = '<option value="">' + t("جارٍ التحميل...", "Loading...") + '</option>';
      citySelect.disabled = true;
      try {
        const resp = await fetch("/api/locations/jordan/governorates/" + encodeURIComponent(val) + "/areas", { credentials: "same-origin" });
        if (!resp.ok) {
          citySelect.innerHTML = '<option value="">' + t("كل المناطق", "All areas") + '</option>';
          citySelect.disabled = false;
          return;
        }
        const json = await resp.json();
        const areas = (json.data && json.data.areas) || [];
        citySelect.innerHTML = '<option value="">' + t("كل المناطق", "All areas") + '</option>';
        areas.forEach(a => {
          const opt = document.createElement("option");
          opt.value = a.key;
          opt.textContent = a.name_ar;
          citySelect.appendChild(opt);
        });
        citySelect.disabled = false;
      } catch (e) {
        citySelect.innerHTML = '<option value="">' + t("كل المناطق", "All areas") + '</option>';
        citySelect.disabled = false;
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", populateLocationFilters);
  } else {
    populateLocationFilters();
  }
})();
