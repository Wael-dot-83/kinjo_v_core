(function () {
  "use strict";
  const govSel = document.getElementById("filter-governorate");
  const distSel = document.getElementById("filter-district");
  const areaSel = document.getElementById("filter-area");
  const resetBtn = document.getElementById("filter-reset-btn");
  if (!govSel || !distSel || !areaSel) return;

  const lang = document.documentElement.lang === "en" ? "en" : "ar";
  const t = (ar, en) => lang === "en" ? en : ar;

  let divisions = [];

  function clearSelect(sel, placeholder) {
    sel.innerHTML = "";
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = placeholder;
    sel.appendChild(opt);
    sel.disabled = true;
  }

  function fillDistricts(govName) {
    const entry = divisions.find((g) => g.gov === govName);
    clearSelect(distSel, t("Select district", "اختر قصبة / لواء"));
    clearSelect(areaSel, t("Select district first", "اختر قصبة / لواء أولاً"));
    if (!entry) return;
    entry.districts.forEach((d) => {
      const opt = document.createElement("option");
      opt.value = d.name;
      opt.textContent = d.name;
      distSel.appendChild(opt);
    });
    distSel.disabled = false;
  }

  function fillAreas(govName, distName) {
    const entry = divisions.find((g) => g.gov === govName);
    clearSelect(areaSel, t("Select area", "اختر المنطقة"));
    if (!entry) return;
    const dist = entry.districts.find((d) => d.name === distName);
    if (!dist) return;
    dist.areas.forEach((a) => {
      const opt = document.createElement("option");
      opt.value = a;
      opt.textContent = a;
      areaSel.appendChild(opt);
    });
    areaSel.disabled = false;
  }

  govSel.addEventListener("change", function () {
    clearSelect(distSel, t("Select district", "اختر قصبة / لواء"));
    clearSelect(areaSel, t("Select district first", "اختر قصبة / لواء أولاً"));
    if (this.value) fillDistricts(this.value);
  });

  distSel.addEventListener("change", function () {
    clearSelect(areaSel, t("Select area", "اختر المنطقة"));
    if (this.value) fillAreas(govSel.value, this.value);
  });

  if (resetBtn) {
    resetBtn.addEventListener("click", function () {
      govSel.value = "";
      clearSelect(distSel, t("Select governorate first", "اختر المحافظة أولاً"));
      clearSelect(areaSel, t("Select district first", "اختر قصبة / لواء أولاً"));
    });
  }

  const url = (window.JORDAN_ADMIN_DIVISIONS_URL) || "/static/data/jordan_admin_divisions.json";
  fetch(url, { credentials: "same-origin" })
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((data) => {
      divisions = data;
    })
    .catch(() => {
      // Silently fail — dropdowns remain static from HTML options
    });
})();
