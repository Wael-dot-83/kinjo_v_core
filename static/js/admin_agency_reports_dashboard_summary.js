(function () {
  "use strict";
  const root = document.getElementById("agency-reports-summary");
  if (!root) return;
  const lang = window.KINJO_LANG === "en" ? "en" : "ar";
  const text = {
    ar: { agencies: "جهات رسمية", reports: "تقارير", ready: "جاهزة", data: "تحتاج بيانات منظمة" },
    en: { agencies: "Agencies", reports: "Reports", ready: "Ready", data: "Need structured data" },
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
      ].forEach(([label, value]) => {
        const item = document.createElement("div");
        item.className = "agency-summary-pill";
        const number = document.createElement("strong");
        number.textContent = new Intl.NumberFormat(lang === "ar" ? "ar-JO" : "en-US").format(Number(value || 0));
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
