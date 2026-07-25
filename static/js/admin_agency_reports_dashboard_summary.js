(function () {
  "use strict";
  const root = document.getElementById("agency-reports-summary");
  if (!root) return;
  const lang = window.KINJO_LANG === "en" ? "en" : "ar";
  const text = {
    ar: { agencies: "جهات رسمية", reports: "تقارير", ready: "جاهزة", data: "تحتاج بيانات منظمة", updated: "آخر تحديث" },
    en: { agencies: "Agencies", reports: "Reports", ready: "Ready", data: "Need structured data", updated: "Last updated" },
  }[lang];
  fetch("/api/admin/agency-reports/summary", { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
    .then((response) => {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then((data) => {
      root.innerHTML = "";
      [
        [text.agencies, data.agency_count],
        [text.reports, data.report_count],
        [text.ready, data.ready_report_count],
        [text.data, data.requires_data_count],
        // Not a count — pass the formatted date string through verbatim so it
        // is not coerced to NaN by the numeric formatter below.
        [text.updated, data.generated_at ? new Date(data.generated_at).toLocaleString(lang === "ar" ? "ar-JO" : "en-US", { dateStyle: "medium", timeStyle: "short" }) : "—", false],
      ].forEach(([label, value, isNumeric = true]) => {
        const item = document.createElement("div");
        item.className = "agency-summary-pill";
        const number = document.createElement("strong");
        number.textContent = isNumeric
          ? new Intl.NumberFormat(lang === "ar" ? "ar-JO" : "en-US").format(Number(value || 0))
          : value;
        const span = document.createElement("span");
        span.textContent = label;
        item.append(number, span);
        root.appendChild(item);
      });
    })
    .catch(() => {
      root.textContent = lang === "en" ? "Unable to load official agency reports summary." : "تعذر تحميل ملخص تقارير الجهات الرسمية.";
    });
})();
