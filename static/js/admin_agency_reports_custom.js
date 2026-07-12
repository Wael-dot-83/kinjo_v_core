/* Custom Reports (التقارير المخصصة) — guided 5-step wizard for /admin/agency-reports.
 * Backend-driven: options from GET /api/admin/agency-reports/custom/schema,
 * results from POST /api/admin/agency-reports/custom. Aggregated data only.
 * The wizard is a UI layer over the same scope contract as before.
 */
(function () {
  "use strict";

  const form = document.getElementById("custom-report-form");
  if (!form) return;

  const controls = document.getElementById("custom-report-controls");
  const staticActionBar = document.getElementById("custom-report-action-bar");
  const resultBox = document.getElementById("custom-report-result");
  const lang = document.documentElement.lang === "en" ? "en" : "ar";
  const t = (ar, en) => (lang === "en" ? en : ar);
  const chartInstances = [];
  const DRAFT_KEY = "kinjo.customReport.draft";

  if (staticActionBar) staticActionBar.hidden = true; // wizard supplies its own nav

  // -------------------------------------------------- helpers
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
      headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest", "X-CSRF-Token": getCookie("kinjo_csrf_token") },
      body: JSON.stringify(body),
    });
  }
  function el(tag, opts) {
    const node = document.createElement(tag);
    if (!opts) return node;
    if (opts.class) node.className = opts.class;
    if (opts.html != null) node.innerHTML = opts.html;
    else if (opts.text != null) node.textContent = opts.text;
    if (opts.attrs) Object.keys(opts.attrs).forEach((k) => node.setAttribute(k, opts.attrs[k]));
    (opts.children || []).forEach((c) => c && node.appendChild(c));
    return node;
  }
  function field(id, labelText, type, opts) {
    opts = opts || {};
    const wrap = el("div", { class: "custom-field" });
    const label = el("label", { text: labelText, attrs: { for: id } });
    const input = el(opts.textarea ? "textarea" : "input", { attrs: Object.assign({ id, name: id, class: "form-control", autocomplete: "off" }, opts.textarea ? { rows: "2" } : { type: type || "text" }) });
    const err = el("p", { class: "wiz-field-error", attrs: { id: id + "-error", role: "alert", hidden: "hidden" } });
    wrap.append(label, input, err);
    if (opts.hint) wrap.insertBefore(el("span", { class: "wiz-hint", text: opts.hint }), err);
    return wrap;
  }
  function labelledSelect(id, labelText, options, valueKey) {
    const wrap = el("div", { class: "custom-field" });
    const label = el("label", { text: labelText, attrs: { for: id } });
    const select = el("select", { attrs: { id, name: id, class: "form-select" } });
    (options || []).forEach((opt) => {
      const o = el("option", { text: lang === "en" ? (opt.name_en || opt.name_ar) : opt.name_ar });
      o.value = opt[valueKey];
      select.appendChild(o);
    });
    wrap.append(label, select);
    return wrap;
  }
  function fieldError(id, msg) {
    const e = document.getElementById(id + "-error");
    const input = document.getElementById(id);
    if (e) { e.textContent = msg || ""; e.hidden = !msg; }
    if (input) { input.setAttribute("aria-invalid", msg ? "true" : "false"); input.classList.toggle("is-invalid", !!msg); }
  }

  // Cascading geo select: placeholder-first select with an inline error slot.
  function geoSelect(id, labelText, hint) {
    const wrap = el("div", { class: "custom-field", attrs: { id: "field-" + id } });
    const label = el("label", { text: labelText, attrs: { for: id, id: "label-" + id } });
    const select = el("select", { attrs: { id, name: id, class: "form-select" } });
    select.appendChild(el("option", { text: t("— اختر —", "— Select —"), attrs: { value: "" } }));
    wrap.append(label, select);
    if (hint) wrap.append(el("span", { class: "wiz-hint", text: hint, attrs: { id: "hint-" + id } }));
    wrap.append(el("p", { class: "wiz-field-error", attrs: { id: id + "-error", role: "alert", hidden: "hidden" } }));
    return wrap;
  }
  function resetSelect(id, placeholder) {
    const s = document.getElementById(id);
    if (!s) return;
    s.innerHTML = "";
    s.appendChild(el("option", { text: placeholder, attrs: { value: "" } }));
  }
  function optionEl(value, text) { const o = el("option", { text }); o.value = value; return o; }
  function selectedText(id) { const s = document.getElementById(id); return s && s.selectedIndex > 0 ? s.options[s.selectedIndex].text : ""; }

  // -------------------------------------------------- state
  let schema = null;
  let schemaAgencies = [];
  let divisions = []; // Jordan governorate -> districts -> areas (from static JSON)

  // Geographic requirement per scope level. Non-geographic levels (class/child/
  // supervisor/manager) allow optional governorate+district refinement.
  const LEVEL_GEO = {
    national: { gov: "hidden", city: "hidden", kg: "hidden", noteAr: "سيشمل التقرير المملكة بالكامل.", noteEn: "The report will cover the whole kingdom." },
    governorate: { gov: "required", city: "optional", kg: "hidden" },
    city: { gov: "required", city: "required", kg: "hidden" },
    kindergarten: { gov: "required", city: "required", kg: "required" },
  };
  function levelGeo(level) { return LEVEL_GEO[level] || { gov: "optional", city: "optional", kg: "hidden" }; }
  function geoBaseLabel(id) { return id === "cr-governorate" ? t("المحافظة", "Governorate") : id === "cr-city" ? t("قصبة / لواء", "District") : t("الحضانة", "Kindergarten"); }
  let currentStep = 0;
  let dirty = false;
  let generated = false;
  const STEPS = [
    { id: "purpose", ar: "الجهة والغرض", en: "Agency & purpose" },
    { id: "scope", ar: "النطاق والفترة", en: "Scope & period" },
    { id: "indicators", ar: "اختيار المؤشرات", en: "Indicators" },
    { id: "review", ar: "المراجعة والمعاينة", en: "Review" },
    { id: "generate", ar: "الإنشاء والنتيجة", en: "Generate" },
  ];

  function markDirty() { dirty = true; generated = false; }

  // -------------------------------------------------- build wizard
  function buildWizard(sc) {
    schema = sc;
    schemaAgencies = sc.agencies || [];
    controls.innerHTML = "";
    controls.removeAttribute("aria-busy");

    controls.appendChild(buildStepper());
    controls.appendChild(buildStepPurpose());
    controls.appendChild(buildStepScope());
    controls.appendChild(buildStepIndicators());
    controls.appendChild(buildStepReview());
    controls.appendChild(buildStepGenerate());
    controls.appendChild(buildNav());

    maybeOfferDraft();
    goToStep(0);
  }

  function buildStepper() {
    const ol = el("ol", { class: "wiz-stepper", attrs: { "aria-label": t("خطوات إنشاء التقرير", "Report steps") } });
    STEPS.forEach((s, i) => {
      const li = el("li", { class: "wiz-step", attrs: { "data-step": i } });
      li.append(
        el("span", { class: "wiz-step__num", text: String(i + 1), attrs: { "aria-hidden": "true" } }),
        el("span", { class: "wiz-step__label", text: t(s.ar, s.en) }),
      );
      ol.appendChild(li);
    });
    return ol;
  }

  function panel(index, titleAr, titleEn) {
    const sec = el("section", { class: "wiz-panel", attrs: { id: "wiz-panel-" + index, "data-step": index, role: "group", "aria-labelledby": "wiz-h-" + index, hidden: "hidden" } });
    sec.appendChild(el("h3", { class: "wiz-panel__title", text: t(titleAr, titleEn), attrs: { id: "wiz-h-" + index, tabindex: "-1" } }));
    sec.appendChild(el("div", { class: "wiz-errors", attrs: { id: "wiz-errors-" + index, role: "alert", hidden: "hidden" } }));
    return sec;
  }

  function buildStepPurpose() {
    const p = panel(0, "الجهة والغرض", "Agency & purpose");
    const row = el("div", { class: "custom-report-row" });
    row.append(labelledSelect("cr-agency", t("الجهة الرسمية المستفيدة", "Beneficiary agency"), schema.agencies, "code"));
    p.appendChild(row);
    const row2 = el("div", { class: "custom-report-row" });
    row2.append(
      field("cr-name", t("اسم التقرير", "Report name"), "text", { hint: t("اسم وصفي يظهر في المراجعة (اختياري)", "A descriptive name shown in review (optional)") }),
    );
    p.appendChild(row2);
    p.appendChild(el("div", { class: "custom-report-row", children: [field("cr-purpose", t("وصف أو غرض التقرير", "Report description or purpose"), "text", { textarea: true, hint: t("لماذا تُنشئ هذا التقرير؟ (اختياري)", "Why are you creating this report? (optional)") })] }));
    p.appendChild(el("div", { class: "custom-agency-preview", attrs: { id: "cr-agency-preview-wiz", "aria-live": "polite" } }));
    return p;
  }

  function buildStepScope() {
    const p = panel(1, "النطاق والفترة", "Scope & period");
    const row1 = el("div", { class: "custom-report-row" });
    row1.append(
      labelledSelect("cr-level", t("النطاق الجغرافي", "Geographic scope"), schema.levels, "code"),
      labelledSelect("cr-period", t("مستوى التجميع", "Aggregation level"), schema.periods, "code"),
    );
    p.appendChild(row1);
    // National-scope note (shown when no geographic narrowing applies).
    p.appendChild(el("p", { class: "wiz-geo-note", attrs: { id: "cr-geo-note", role: "note", hidden: "hidden" } }));
    const dates = el("div", { class: "custom-report-row", attrs: { id: "cr-custom-dates", hidden: "hidden" } });
    dates.append(field("cr-start", t("تاريخ البداية", "Start date"), "date"), field("cr-end", t("تاريخ النهاية", "End date"), "date"));
    p.appendChild(dates);
    const row2 = el("div", { class: "custom-report-row" });
    row2.append(
      geoSelect("cr-governorate", geoBaseLabel("cr-governorate")),
      geoSelect("cr-city", geoBaseLabel("cr-city"), t("اختر المحافظة أولاً", "Select a governorate first")),
      geoSelect("cr-kindergarten", geoBaseLabel("cr-kindergarten"), t("اختر المحافظة والقصبة / اللواء أولاً", "Select governorate and district first")),
    );
    p.appendChild(row2);

    // Wiring
    const level = document.getElementById("cr-level");
    const period = document.getElementById("cr-period");
    const gov = document.getElementById("cr-governorate");
    const city = document.getElementById("cr-city");
    if (level) level.addEventListener("change", () => { onLevelChanged(); markDirty(); });
    if (period) period.addEventListener("change", () => { togglePeriodDates(); markDirty(); });
    if (gov) gov.addEventListener("change", () => { fillDistricts(gov.value); resetSelect("cr-kindergarten", t("اختر القصبة / اللواء أولاً", "Select a district first")); applyLevelVisibility(); maybeFillKindergartens(); markDirty(); });
    if (city) city.addEventListener("change", () => { applyLevelVisibility(); maybeFillKindergartens(); markDirty(); });
    return p;
  }

  // -------------------------------------------------- geo cascade
  function populateGovernorates() {
    const s = document.getElementById("cr-governorate");
    if (!s || !divisions.length) return;
    const cur = s.value;
    resetSelect("cr-governorate", t("— اختر المحافظة —", "— Select governorate —"));
    divisions.forEach((g) => s.appendChild(optionEl(g.gov, g.gov)));
    if (cur) s.value = cur;
  }
  function fillDistricts(govName, keep) {
    resetSelect("cr-city", t("— اختر قصبة / لواء —", "— Select district —"));
    const s = document.getElementById("cr-city");
    const entry = divisions.find((g) => g.gov === govName);
    if (s && entry) entry.districts.forEach((d) => s.appendChild(optionEl(d.name, d.name)));
    if (s && keep) s.value = keep;
  }
  function fillKindergartens(govName, distName, keep) {
    const s = document.getElementById("cr-kindergarten");
    if (!s) return Promise.resolve();
    resetSelect("cr-kindergarten", t("جارٍ التحميل...", "Loading..."));
    s.disabled = true;
    const params = new URLSearchParams({ limit: "200" });
    if (govName) params.set("governorate", govName);
    if (distName) params.set("district", distName);
    return apiGet("/api/kindergartens?" + params.toString())
      .then((res) => {
        const items = (res.data && res.data.items) || [];
        resetSelect("cr-kindergarten", items.length ? t("— اختر الحضانة —", "— Select kindergarten —") : t("لا توجد حضانات في هذا النطاق", "No kindergartens in this scope"));
        items.forEach((kg) => s.appendChild(optionEl(String(kg.id), kg.name_ar || ("#" + kg.id))));
        s.disabled = items.length === 0;
        if (keep) s.value = keep;
      })
      .catch(() => { resetSelect("cr-kindergarten", t("تعذّر تحميل الحضانات", "Could not load kindergartens")); s.disabled = true; });
  }
  function maybeFillKindergartens() {
    const cfg = levelGeo(valueOf("cr-level"));
    if (cfg.kg === "hidden") return;
    const g = valueOf("cr-governorate"), d = valueOf("cr-city");
    if (g && d) fillKindergartens(g, d);
    else resetSelect("cr-kindergarten", t("اختر القصبة / اللواء أولاً", "Select a district first"));
  }
  function onLevelChanged() {
    // Clear geo selections that no longer apply, then re-apply visibility.
    const cfg = levelGeo(valueOf("cr-level"));
    if (cfg.gov === "hidden") { const g = document.getElementById("cr-governorate"); if (g) g.value = ""; }
    if (cfg.city === "hidden") { const c = document.getElementById("cr-city"); if (c) c.value = ""; }
    if (cfg.kg === "hidden") { resetSelect("cr-kindergarten", t("— اختر الحضانة —", "— Select kindergarten —")); }
    applyLevelVisibility();
    maybeFillKindergartens();
  }
  function togglePeriodDates() {
    const period = document.getElementById("cr-period");
    const dates = document.getElementById("cr-custom-dates");
    if (period && dates) dates.hidden = period.value !== "custom";
  }
  function applyLevelVisibility() {
    const cfg = levelGeo(valueOf("cr-level"));
    [["cr-governorate", cfg.gov], ["cr-city", cfg.city], ["cr-kindergarten", cfg.kg]].forEach(([id, state]) => {
      const wrap = document.getElementById("field-" + id);
      const sel = document.getElementById(id);
      const label = document.getElementById("label-" + id);
      if (!wrap || !sel) return;
      if (state === "hidden") { wrap.hidden = true; sel.setAttribute("aria-required", "false"); }
      else {
        wrap.hidden = false;
        const req = state === "required";
        sel.setAttribute("aria-required", req ? "true" : "false");
        if (label) label.innerHTML = geoBaseLabel(id) + (req ? ' <span class="wiz-req" aria-hidden="true">*</span>' : ' <span class="wiz-optional">(' + t("اختياري", "optional") + ")</span>");
      }
    });
    const gov = valueOf("cr-governorate"), dist = valueOf("cr-city");
    const citySel = document.getElementById("cr-city");
    const cityWrap = document.getElementById("field-cr-city");
    if (citySel && cityWrap && !cityWrap.hidden) citySel.disabled = !gov;
    const kgSel = document.getElementById("cr-kindergarten");
    const kgWrap = document.getElementById("field-cr-kindergarten");
    if (kgSel && kgWrap && !kgWrap.hidden && !(gov && dist)) kgSel.disabled = true;
    const note = document.getElementById("cr-geo-note");
    if (note) { const txt = t(cfg.noteAr || "", cfg.noteEn || ""); note.textContent = txt; note.hidden = !txt; }
  }

  function buildStepIndicators() {
    const p = panel(2, "اختيار المؤشرات", "Select indicators");
    p.appendChild(el("p", { class: "wiz-hint", text: t("اختر مؤشرًا واحدًا على الأقل. المؤشرات المعطّلة تتطلب بيانات غير متوفرة حاليًا.", "Select at least one indicator. Disabled indicators require data that is not available yet.") }));
    const totalBar = el("div", { class: "wiz-indicator-total", attrs: { id: "wiz-indicator-total", "aria-live": "polite" } });
    p.appendChild(totalBar);
    const groups = el("div", { class: "wiz-groups" });
    (schema.domains || []).forEach((domain, gi) => {
      const details = el("details", { class: "wiz-group", attrs: { open: "open" } });
      const summary = el("summary", { class: "wiz-group__summary" });
      const gname = lang === "en" ? (domain.name_en || domain.name_ar) : domain.name_ar;
      summary.append(
        el("span", { class: "wiz-group__name", text: gname }),
        el("span", { class: "wiz-group__count", attrs: { "data-group": gi }, text: "0" }),
      );
      const selectableCount = domain.indicators.filter((i) => i.status === "ready").length;
      const actions = el("span", { class: "wiz-group__actions" });
      const allBtn = el("button", { class: "wiz-linkbtn", text: t("تحديد الكل", "Select all"), attrs: { type: "button" } });
      const clrBtn = el("button", { class: "wiz-linkbtn", text: t("مسح", "Clear"), attrs: { type: "button" } });
      if (!selectableCount) { allBtn.disabled = true; clrBtn.disabled = true; }
      actions.append(allBtn, clrBtn);
      summary.appendChild(actions);
      details.appendChild(summary);

      const body = el("div", { class: "wiz-group__body" });
      domain.indicators.forEach((ind) => {
        const wrap = el("label", { class: "custom-indicator" });
        const cb = el("input", { attrs: { type: "checkbox", name: "indicator", value: ind.code, "data-group": gi } });
        if (ind.status !== "ready") { cb.disabled = true; wrap.classList.add("custom-indicator--needs-data"); }
        cb.addEventListener("change", () => { markDirty(); updateCounts(); });
        const span = el("span", { text: (lang === "en" ? (ind.name_en || ind.name_ar) : ind.name_ar) });
        wrap.append(cb, span);
        if (ind.status !== "ready") wrap.append(el("span", { class: "wiz-needs-badge", text: t("يتطلب بيانات", "needs data") }));
        body.appendChild(wrap);
      });
      details.appendChild(body);

      allBtn.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); body.querySelectorAll('input[type="checkbox"]:not(:disabled)').forEach((c) => { c.checked = true; }); markDirty(); updateCounts(); });
      clrBtn.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); body.querySelectorAll('input[type="checkbox"]').forEach((c) => { c.checked = false; }); markDirty(); updateCounts(); });
      groups.appendChild(details);
    });
    p.appendChild(groups);
    return p;
  }

  function buildStepReview() {
    const p = panel(3, "المراجعة والمعاينة", "Review & preview");
    p.appendChild(el("div", { class: "wiz-review", attrs: { id: "wiz-review-body" } }));
    p.appendChild(el("p", { class: "wiz-privacy-note", html: '<i class="bi bi-shield-lock-fill" aria-hidden="true"></i> ' + t("سيُنشأ التقرير ببيانات تجميعية فقط دون أي بيانات شخصية.", "The report will be generated with aggregated data only — no personal data.") }));
    return p;
  }

  function buildStepGenerate() {
    const p = panel(4, "الإنشاء والنتيجة", "Generate & result");
    const actions = el("div", { class: "wiz-generate-actions" });
    const genBtn = el("button", { class: "admin-btn admin-btn-primary", attrs: { type: "button", id: "wiz-generate" } });
    genBtn.innerHTML = '<i class="bi bi-play-circle" aria-hidden="true"></i> ' + t("إنشاء التقرير", "Generate report");
    genBtn.addEventListener("click", run);
    const draftBtn = el("button", { class: "admin-btn admin-btn-secondary", text: t("حفظ كمسودة", "Save as draft"), attrs: { type: "button" } });
    draftBtn.addEventListener("click", saveDraft);
    actions.append(genBtn, draftBtn);
    p.appendChild(actions);
    // result mount point = existing resultBox lives after the form; keep as-is.
    return p;
  }

  function buildNav() {
    const nav = el("div", { class: "wiz-nav" });
    const back = el("button", { class: "admin-btn admin-btn-secondary", text: t("السابق", "Back"), attrs: { type: "button", id: "wiz-back" } });
    const next = el("button", { class: "admin-btn admin-btn-primary", text: t("التالي", "Next"), attrs: { type: "button", id: "wiz-next" } });
    const reset = el("button", { class: "wiz-reset-link", text: t("إعادة تعيين", "Reset"), attrs: { type: "button", id: "wiz-reset" } });
    back.addEventListener("click", () => goToStep(currentStep - 1));
    next.addEventListener("click", () => { if (validateStep(currentStep)) goToStep(currentStep + 1); });
    reset.addEventListener("click", resetWizard);
    nav.append(back, el("div", { class: "wiz-nav__spacer" }), reset, next);
    return nav;
  }

  // -------------------------------------------------- navigation
  function goToStep(index) {
    index = Math.max(0, Math.min(STEPS.length - 1, index));
    currentStep = index;
    controls.querySelectorAll(".wiz-panel").forEach((sec) => { sec.hidden = Number(sec.dataset.step) !== index; });
    controls.querySelectorAll(".wiz-step").forEach((li, i) => {
      li.classList.toggle("is-active", i === index);
      li.classList.toggle("is-done", i < index);
      if (i === index) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
    });
    const back = document.getElementById("wiz-back");
    const next = document.getElementById("wiz-next");
    if (back) back.style.visibility = index === 0 ? "hidden" : "visible";
    if (next) next.hidden = index === STEPS.length - 1; // last step uses Generate button
    if (index === 3) renderReview();
    const h = document.getElementById("wiz-h-" + index);
    if (h) h.focus();
  }

  function showErrors(index, messages) {
    const box = document.getElementById("wiz-errors-" + index);
    if (!box) return;
    box.innerHTML = "";
    if (!messages.length) { box.hidden = true; return; }
    box.hidden = false;
    const ul = el("ul");
    messages.forEach((m) => ul.appendChild(el("li", { text: m })));
    box.append(el("strong", { text: t("يرجى تصحيح ما يلي:", "Please fix the following:") }), ul);
  }

  function validateStep(index) {
    const errors = [];
    ["cr-agency", "cr-start", "cr-end", "cr-governorate", "cr-city", "cr-kindergarten"].forEach((id) => fieldError(id, ""));
    if (index === 0) {
      const agency = valueOf("cr-agency");
      if (!agency) { errors.push(t("يرجى اختيار الجهة الرسمية المستفيدة.", "Please select the beneficiary agency.")); fieldError("cr-agency", t("مطلوب", "Required")); }
    } else if (index === 1) {
      const cfg = levelGeo(valueOf("cr-level"));
      if (cfg.gov === "required" && !valueOf("cr-governorate")) { errors.push(t("يرجى اختيار المحافظة.", "Please select a governorate.")); fieldError("cr-governorate", t("مطلوب", "Required")); }
      if (cfg.city === "required" && !valueOf("cr-city")) { errors.push(t("يرجى اختيار القصبة / اللواء.", "Please select a district.")); fieldError("cr-city", t("مطلوب", "Required")); }
      if (cfg.kg === "required" && !valueOf("cr-kindergarten")) { errors.push(t("يرجى اختيار الحضانة.", "Please select a kindergarten.")); fieldError("cr-kindergarten", t("مطلوب", "Required")); }
      if (valueOf("cr-period") === "custom") {
        const s = valueOf("cr-start"), e = valueOf("cr-end");
        if (!s || !e) { errors.push(t("يرجى تحديد تاريخ البداية وتاريخ النهاية.", "Please set both the start and end dates.")); if (!s) fieldError("cr-start", t("مطلوب", "Required")); if (!e) fieldError("cr-end", t("مطلوب", "Required")); }
        else if (e < s) { errors.push(t("يجب أن يكون تاريخ النهاية مساويًا لتاريخ البداية أو لاحقًا له.", "The end date must be on or after the start date.")); fieldError("cr-end", t("تاريخ غير صالح", "Invalid date")); }
      }
    } else if (index === 2) {
      if (!selectedIndicators().length) errors.push(t("اختر مؤشرًا واحدًا على الأقل لإنشاء التقرير.", "Select at least one indicator to generate the report."));
    }
    showErrors(index, errors);
    if (errors.length) {
      const firstInvalid = controls.querySelector('#wiz-panel-' + index + ' [aria-invalid="true"]');
      if (firstInvalid) firstInvalid.focus();
      else { const box = document.getElementById("wiz-errors-" + index); if (box) box.focus && box.focus(); }
    }
    return !errors.length;
  }

  // -------------------------------------------------- review
  function renderReview() {
    const body = document.getElementById("wiz-review-body");
    if (!body) return;
    body.innerHTML = "";
    const agency = schemaAgencies.find((a) => a.code === valueOf("cr-agency"));
    const level = (schema.levels || []).find((l) => l.code === valueOf("cr-level"));
    const period = (schema.periods || []).find((pp) => pp.code === valueOf("cr-period"));
    const indicators = selectedIndicators();

    function line(labelAr, labelEn, value, ltr) {
      if (value == null || value === "") return;
      const div = el("div", { class: "wiz-review__line" });
      const dd = el("dd", { text: value });
      if (ltr) { dd.setAttribute("dir", "ltr"); dd.style.textAlign = "start"; } // keep dates/IDs readable in RTL
      div.append(el("dt", { text: t(labelAr, labelEn) }), dd);
      return div;
    }
    const dl = el("dl", { class: "wiz-review__list" });
    [
      line("الجهة", "Agency", agency ? agency.name_ar : valueOf("cr-agency")),
      line("اسم التقرير", "Report name", valueOf("cr-name")),
      line("الغرض", "Purpose", valueOf("cr-purpose")),
      line("النطاق الجغرافي", "Geographic scope", level ? level.name_ar : ""),
      line("المحافظة", "Governorate", valueOf("cr-governorate")),
      line("قصبة / لواء", "District", valueOf("cr-city")),
      line("الحضانة", "Kindergarten", selectedText("cr-kindergarten")),
      line("مستوى التجميع", "Aggregation level", period ? period.name_ar : ""),
      valueOf("cr-period") === "custom" ? line("الفترة", "Period", (valueOf("cr-start") || "—") + " → " + (valueOf("cr-end") || "—"), true) : null,
      line("عدد المؤشرات", "Indicators selected", String(indicators.length)),
    ].forEach((n) => n && dl.appendChild(n));
    body.appendChild(dl);

    // Indicators grouped by category
    const groupsWrap = el("div", { class: "wiz-review__indicators" });
    groupsWrap.appendChild(el("h4", { text: t("المؤشرات المختارة", "Selected indicators") }));
    (schema.domains || []).forEach((domain) => {
      const chosen = domain.indicators.filter((i) => indicators.indexOf(i.code) !== -1);
      if (!chosen.length) return;
      const g = el("div", { class: "wiz-review__group" });
      g.appendChild(el("h5", { text: lang === "en" ? (domain.name_en || domain.name_ar) : domain.name_ar }));
      const ul = el("ul");
      chosen.forEach((i) => ul.appendChild(el("li", { text: lang === "en" ? (i.name_en || i.name_ar) : i.name_ar })));
      g.appendChild(ul);
      groupsWrap.appendChild(g);
    });
    if (!indicators.length) groupsWrap.appendChild(el("p", { class: "wiz-warning", text: t("لم تختر أي مؤشر بعد. عد إلى خطوة المؤشرات.", "No indicators selected yet. Go back to the indicators step.") }));
    body.appendChild(groupsWrap);
  }

  // -------------------------------------------------- indicators helpers
  function selectedIndicators() {
    return Array.prototype.slice.call(form.querySelectorAll('input[name="indicator"]:checked')).map((c) => c.value);
  }
  function updateCounts() {
    const total = selectedIndicators().length;
    const totalBar = document.getElementById("wiz-indicator-total");
    if (totalBar) totalBar.textContent = t("المؤشرات المختارة: ", "Indicators selected: ") + total;
    controls.querySelectorAll(".wiz-group__count").forEach((c) => {
      const gi = c.getAttribute("data-group");
      const n = controls.querySelectorAll('input[name="indicator"][data-group="' + gi + '"]:checked').length;
      c.textContent = String(n);
      c.classList.toggle("is-active", n > 0);
    });
  }

  // -------------------------------------------------- scope / value
  function valueOf(id) { const n = document.getElementById(id); return n ? String(n.value || "").trim() : ""; }
  function collectScope() {
    const scope = {
      agency: valueOf("cr-agency"),
      level: valueOf("cr-level"),
      period: valueOf("cr-period"),
      indicators: selectedIndicators(),
      governorate: valueOf("cr-governorate") || null,
      city: valueOf("cr-city") || null,
      kindergarten_id: valueOf("cr-kindergarten") || null,
      report_name: valueOf("cr-name") || null,
      purpose: valueOf("cr-purpose") || null,
    };
    if (scope.period === "custom") { scope.start_date = valueOf("cr-start") || null; scope.end_date = valueOf("cr-end") || null; }
    return scope;
  }

  // -------------------------------------------------- draft (localStorage)
  function saveDraft() {
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify(collectScope()));
      flash(t("تم حفظ المسودة.", "Draft saved."));
    } catch (e) { flash(t("تعذّر حفظ المسودة.", "Could not save draft."), true); }
  }
  function maybeOfferDraft() {
    let draft = null;
    try { draft = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null"); } catch (e) { draft = null; }
    if (!draft) return;
    const banner = el("div", { class: "wiz-draft-banner", attrs: { role: "note" } });
    banner.appendChild(el("span", { text: t("توجد مسودة محفوظة.", "You have a saved draft.") }));
    const restore = el("button", { class: "wiz-linkbtn", text: t("استعادة", "Restore"), attrs: { type: "button" } });
    const discard = el("button", { class: "wiz-linkbtn", text: t("تجاهل", "Discard"), attrs: { type: "button" } });
    restore.addEventListener("click", () => { applyDraft(draft); banner.remove(); });
    discard.addEventListener("click", () => { localStorage.removeItem(DRAFT_KEY); banner.remove(); });
    banner.append(restore, discard);
    controls.insertBefore(banner, controls.firstChild);
  }
  function applyDraft(draft) {
    function set(id, v) { const n = document.getElementById(id); if (n && v != null) n.value = v; }
    set("cr-agency", draft.agency); set("cr-level", draft.level); set("cr-period", draft.period);
    set("cr-name", draft.report_name); set("cr-purpose", draft.purpose);
    set("cr-start", draft.start_date); set("cr-end", draft.end_date);
    // geo cascade (governorate -> district -> kindergarten)
    populateGovernorates();
    set("cr-governorate", draft.governorate);
    if (draft.governorate) fillDistricts(draft.governorate, draft.city);
    togglePeriodDates();
    applyLevelVisibility();
    const cfg = levelGeo(draft.level);
    if (cfg.kg !== "hidden" && draft.governorate && draft.city) {
      fillKindergartens(draft.governorate, draft.city, draft.kindergarten_id).then(applyLevelVisibility);
    }
    (draft.indicators || []).forEach((code) => { const cb = form.querySelector('input[name="indicator"][value="' + code + '"]'); if (cb && !cb.disabled) cb.checked = true; });
    updateCounts();
    onAgencyChanged();
  }

  // -------------------------------------------------- reset
  function resetWizard() {
    if ((dirty || selectedIndicators().length) && !window.confirm(t("سيتم مسح كل اختياراتك في التقرير المخصص. هل تريد المتابعة؟", "This will clear all your custom-report selections. Continue?"))) return;
    form.reset();
    destroyCharts();
    resultBox.innerHTML = "";
    dirty = false; generated = false;
    onScopeControlsChanged();
    onAgencyChanged();
    updateCounts();
    goToStep(0);
  }

  // -------------------------------------------------- progressive disclosure
  function onScopeControlsChanged() {
    togglePeriodDates();
    applyLevelVisibility();
  }
  function onAgencyChanged() {
    const box = document.getElementById("cr-agency-preview-wiz");
    if (!box) return;
    const agency = schemaAgencies.find((a) => a.code === valueOf("cr-agency"));
    box.innerHTML = "";
    if (!agency) return;
    const wrap = el("div", { class: "custom-agency-option", attrs: { "aria-hidden": "true" } });
    if (typeof window.renderAgencyLogo === "function") wrap.appendChild(window.renderAgencyLogo(agency, 48));
    const text = el("div", { class: "custom-agency-preview-text" });
    text.appendChild(el("div", { class: "custom-agency-preview-name", text: agency.name_ar }));
    if (agency.description_ar) text.appendChild(el("div", { class: "custom-agency-preview-desc", text: agency.description_ar }));
    wrap.appendChild(text);
    box.appendChild(wrap);
  }

  // -------------------------------------------------- flash
  let flashTimer = null;
  function flash(msg, isError) {
    let f = document.getElementById("wiz-flash");
    if (!f) { f = el("div", { attrs: { id: "wiz-flash", role: "status", "aria-live": "polite" }, class: "wiz-flash" }); controls.appendChild(f); }
    f.textContent = msg;
    f.classList.toggle("wiz-flash--error", !!isError);
    f.classList.add("is-visible");
    clearTimeout(flashTimer);
    flashTimer = setTimeout(() => f.classList.remove("is-visible"), 2600);
  }

  // -------------------------------------------------- result rendering (reused)
  function setState(kind, message) { resultBox.innerHTML = ""; resultBox.appendChild(el("div", { class: "custom-report-state custom-report-state--" + kind, text: message })); }
  function destroyCharts() { while (chartInstances.length) { try { chartInstances.pop().destroy(); } catch (e) { /* noop */ } } }
  function renderKpis(kpis) {
    const grid = el("div", { class: "custom-kpi-grid" });
    kpis.forEach((k) => grid.appendChild(el("div", { class: "custom-kpi-card", children: [
      el("div", { class: "custom-kpi-value", text: String(k.value) + (k.unit_ar ? " " + k.unit_ar : "") }),
      el("div", { class: "custom-kpi-label", text: k.label_ar }),
    ] })));
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
        card.appendChild(canvas); wrap.appendChild(card);
        chartInstances.push(new window.Chart(canvas.getContext("2d"), {
          type: chart.type === "pie" ? "pie" : "bar",
          data: { labels: series.map((s) => s.label), datasets: [{ label: chart.title_ar, data: series.map((s) => s.value), backgroundColor: ["#1f6f54", "#2f8f6d", "#c0392b", "#e0a90e", "#2b6cb0", "#6b46c1", "#718096"] }] },
          options: { responsive: true, plugins: { legend: { position: chart.type === "pie" ? "bottom" : "top" } } },
        }));
      } else {
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
    if (!rows.length) { card.appendChild(el("p", { text: t("لا توجد صفوف تفصيلية.", "No detailed rows.") })); return card; }
    const headers = [];
    rows.forEach((r) => Object.keys(r).forEach((k) => { if (headers.indexOf(k) === -1) headers.push(k); }));
    const table = el("table", { class: "custom-table admin-table", attrs: { dir: lang === "en" ? "ltr" : "rtl" } });
    const thead = el("thead"); const htr = el("tr");
    headers.forEach((h) => htr.appendChild(el("th", { text: h, attrs: { scope: "col" } })));
    thead.appendChild(htr);
    const tbody = el("tbody");
    rows.forEach((r) => { const tr = el("tr"); headers.forEach((h) => tr.appendChild(el("td", { text: r[h] != null ? String(r[h]) : "—" }))); tbody.appendChild(tr); });
    table.append(thead, tbody);
    const scroll = el("div", { class: "custom-table-scroll", attrs: { tabindex: "0", role: "region", "aria-label": t("جدول تفصيلي", "Detailed table") } });
    scroll.appendChild(table); card.appendChild(scroll);
    return card;
  }
  function dataQualityLabel(status) { return { sufficient: t("كافية", "Sufficient"), limited: t("محدودة", "Limited"), incomplete: t("غير مكتملة", "Incomplete") }[status] || status; }

  function render(data) {
    destroyCharts();
    resultBox.innerHTML = "";
    const header = el("div", { class: "custom-report-result-header" });
    header.appendChild(el("h3", { text: (valueOf("cr-name") || data.title || t("تقرير مخصص", "Custom report")) + " — " + (data.scope.agency_name_ar || data.scope.agency) }));
    header.appendChild(el("span", { class: "custom-dq custom-dq--" + (data.data_quality.status || "incomplete"), text: t("حالة البيانات: ", "Data quality: ") + dataQualityLabel(data.data_quality.status) }));
    resultBox.appendChild(header);
    resultBox.appendChild(el("p", { class: "custom-report-scope", text: t("النطاق: ", "Scope: ") + [data.scope.level_name_ar, data.scope.governorate, data.scope.city].filter(Boolean).join(" / ") + " · " + data.scope.start_date + " → " + data.scope.end_date }));

    // Partial-success note: requested indicators that the backend could not include.
    const requested = selectedIndicators().length;
    const included = (data.kpis || []).length;
    if (requested && included && included < requested) {
      resultBox.appendChild(el("div", { class: "custom-report-state custom-report-state--partial", text: t("تم إنشاء التقرير، لكن بعض المؤشرات لم تُضمّن بسبب عدم توفر البيانات المطلوبة.", "Report created, but some indicators were omitted because the required data is unavailable.") }));
    }

    if ((data.kpis || []).length) resultBox.appendChild(renderKpis(data.kpis));
    if ((data.charts || []).length) resultBox.appendChild(renderCharts(data.charts));
    resultBox.appendChild(renderTable(data.table || []));
    if (data.summary_ar) resultBox.appendChild(el("div", { class: "custom-summary", children: [el("h4", { text: t("ملخص تنفيذي", "Executive summary") }), el("p", { text: data.summary_ar })] }));
    if ((data.decision_notes_ar || []).length) {
      const notes = el("div", { class: "custom-decision-notes", children: [el("h4", { text: t("ملاحظات لدعم القرار", "Decision-support notes") })] });
      const ul = el("ul"); data.decision_notes_ar.forEach((n) => ul.appendChild(el("li", { text: n }))); notes.appendChild(ul); resultBox.appendChild(notes);
    }
    if ((data.data_quality.notes || []).length) {
      const dqn = el("div", { class: "custom-dq-notes", children: [el("h4", { text: t("ملاحظات جودة البيانات", "Data-quality notes") })] });
      const ul = el("ul"); data.data_quality.notes.forEach((n) => ul.appendChild(el("li", { text: n }))); dqn.appendChild(ul); resultBox.appendChild(dqn);
    }
    const exportBar = el("div", { class: "custom-export-bar" });
    const csvBtn = el("button", { class: "admin-btn admin-btn-secondary", attrs: { type: "button" } });
    csvBtn.innerHTML = '<i class="bi bi-file-earmark-spreadsheet" aria-hidden="true"></i> ' + t("تصدير CSV", "Export CSV");
    csvBtn.addEventListener("click", exportCsv);
    exportBar.append(csvBtn);
    resultBox.appendChild(exportBar);
  }

  function exportCsv() {
    apiPost("/api/admin/agency-reports/custom/export.csv", collectScope())
      .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.blob(); })
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = el("a", { attrs: { href: url, download: "custom_agency_report.csv" } });
        document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
      })
      .catch(() => flash(t("تعذّر تصدير الملف.", "Export failed."), true));
  }

  function run() {
    if (!validateStep(2)) { goToStep(2); return; }
    const scope = collectScope();
    setState("loading", t("جارٍ إنشاء التقرير...", "Generating report..."));
    apiPost("/api/admin/agency-reports/custom", scope)
      .then((r) => r.json().then((body) => ({ ok: r.ok, body })))
      .then(({ ok, body }) => {
        if (!ok) { setState("error", (body && body.detail) ? body.detail : t("تعذّر إنشاء التقرير. لم يتم فقدان إعداداتك، ويمكنك المحاولة مرة أخرى.", "Could not generate the report. Your settings are kept; you can try again.")); return; }
        generated = true; dirty = false;
        render(body.data);
        flash(t("تم إنشاء التقرير بنجاح.", "Report created successfully."));
        resultBox.scrollIntoView({ behavior: "smooth", block: "start" });
      })
      .catch(() => setState("error", t("حدث خطأ غير متوقع أثناء إنشاء التقرير. لم يتم فقدان إعداداتك.", "An unexpected error occurred. Your settings are kept.")));
  }

  // -------------------------------------------------- init
  form.addEventListener("submit", (e) => e.preventDefault());
  // cr-level / cr-period / cr-governorate / cr-city have explicit listeners in buildStepScope.
  form.addEventListener("input", (e) => {
    if (e.target && e.target.id === "cr-agency") onAgencyChanged();
    if (e.target && e.target.closest && e.target.closest("#custom-report-controls")) markDirty();
  });
  form.addEventListener("change", (e) => { if (e.target && e.target.id === "cr-agency") onAgencyChanged(); });
  window.addEventListener("beforeunload", (e) => { if (dirty && !generated) { e.preventDefault(); e.returnValue = ""; } });

  // Jordan admin divisions (governorate -> district -> area) for the geo cascade.
  fetch((window.JORDAN_ADMIN_DIVISIONS_URL) || "/static/data/jordan_admin_divisions.json", { credentials: "same-origin" })
    .then((r) => (r.ok ? r.json() : []))
    .then((data) => { divisions = Array.isArray(data) ? data : []; populateGovernorates(); applyLevelVisibility(); })
    .catch(() => {});

  apiGet("/api/admin/agency-reports/custom/schema")
    .then((res) => { buildWizard(res.data); populateGovernorates(); onScopeControlsChanged(); onAgencyChanged(); updateCounts(); })
    .catch(() => { controls.removeAttribute("aria-busy"); controls.textContent = t("تعذّر تحميل خيارات التقرير المخصص.", "Could not load custom report options."); });
})();
