(function () {
  "use strict";

  const root = document.getElementById("agency-reports-summary");
  if (!root) return;

  const lang = window.KINJO_LANG === "en" ? "en" : "ar";
  const copy = {
    ar: {
      agencies: "جهات رسمية",
      reports: "تقارير",
      ready: "جاهزة",
      data: "تحتاج بيانات منظمة",
      dataReady: "البيانات مكتملة",
      updated: "آخر تحديث",
      reviewData: "مراجعة البيانات",
      loadError: "تعذّر تحميل ملخص تقارير الجهات الرسمية.",
    },
    en: {
      agencies: "Agencies",
      reports: "Reports",
      ready: "Ready",
      data: "Need structured data",
      dataReady: "All data ready",
      updated: "Last updated",
      reviewData: "Review data",
      loadError: "Unable to load official agency reports summary.",
    },
  }[lang];

  function formatNumber(value) {
    return new Intl.NumberFormat(lang === "ar" ? "ar-JO" : "en-US").format(
      Number.isFinite(Number(value)) ? Number(value) : 0,
    );
  }

  function appendSummaryItem(item) {
    const wrapper = document.createElement("div");
    wrapper.className = `agency-summary-pill agency-summary-pill--${item.status}`;
    wrapper.dataset.status = item.status;

    const number = document.createElement("strong");
    number.textContent = item.isNumeric ? formatNumber(item.value) : item.value;

    const label = document.createElement("span");
    label.className = "agency-summary-pill__status";
    const icon = document.createElement("i");
    icon.className = `bi ${item.icon}`;
    icon.setAttribute("aria-hidden", "true");
    label.append(icon, item.label);

    wrapper.append(number, label);

    if (item.action) {
      const action = document.createElement("a");
      action.className = "agency-summary-pill__action";
      action.href = "/admin/agency-reports?status=requires_structured_data";
      const actionIcon = document.createElement("i");
      actionIcon.className = `bi bi-arrow-${lang === "ar" ? "left" : "right"}`;
      actionIcon.setAttribute("aria-hidden", "true");
      action.append(actionIcon, item.action);
      wrapper.appendChild(action);
    }

    root.appendChild(wrapper);
  }

  fetch("/api/admin/agency-reports/summary", {
    credentials: "same-origin",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then((data) => {
      root.innerHTML = "";
      const requiresData = Number(data.requires_data_count || 0);
      const generatedAt = data.generated_at
        ? new Date(data.generated_at).toLocaleString(
            lang === "ar" ? "ar-JO" : "en-US",
            { dateStyle: "medium", timeStyle: "short" },
          )
        : "—";

      [
        { label: copy.agencies, value: data.agency_count, status: "neutral", icon: "bi-bank" },
        { label: copy.reports, value: data.report_count, status: "neutral", icon: "bi-file-earmark-text" },
        { label: copy.ready, value: data.ready_report_count, status: "good", icon: "bi-check-circle-fill" },
        {
          label: requiresData > 0 ? copy.data : copy.dataReady,
          value: requiresData,
          status: requiresData > 0 ? "warning" : "good",
          icon: requiresData > 0 ? "bi-database-exclamation" : "bi-database-check",
          action: requiresData > 0 ? copy.reviewData : "",
        },
        { label: copy.updated, value: generatedAt, status: "neutral", icon: "bi-clock-history", isNumeric: false },
      ].forEach(appendSummaryItem);
    })
    .catch(() => {
      root.textContent = copy.loadError;
    });
})();
