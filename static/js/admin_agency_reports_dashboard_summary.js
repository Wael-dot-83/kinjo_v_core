/* Official Agency Reports — dashboard summary cards.
 * Renders one card per official agency (from /api/admin/agency-reports/summary)
 * with logo/fallback, Arabic name, report counts, and a CTA. Backend-driven:
 * all branding metadata arrives in the payload; no hardcoded mapping here.
 */
(function () {
  "use strict";
  const root = document.getElementById("agency-reports-summary");
  if (!root) return;
  const lang = window.KINJO_LANG === "en" ? "en" : "ar";
  const t = (ar, en) => (lang === "en" ? en : ar);

  function pill(text, kind) {
    const span = document.createElement("span");
    span.className = "agency-status agency-status--" + (kind || "default");
    span.textContent = text;
    return span;
  }

  function dqBadge(agency) {
    const span = document.createElement("span");
    const good = agency.requires_data_count === 0;
    span.className = "agency-dq " + (good ? "agency-dq--good" : "agency-dq--partial");
    span.textContent = good ? t("جودة البيانات: جيدة", "Data quality: good")
                            : t("جودة البيانات: جزئية", "Data quality: partial");
    return span;
  }

  fetch("/api/admin/agency-reports/summary", {
    credentials: "same-origin",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  })
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((data) => {
      root.innerHTML = "";
      const grid = document.createElement("div");
      grid.className = "official-agency-grid";
      grid.setAttribute("role", "list");
      grid.setAttribute("aria-label", t("الجهات الرسمية", "Official agencies"));

      (data.agencies || []).forEach((agency) => {
        const card = document.createElement("div");
        card.className = "official-agency-card";
        card.setAttribute("role", "listitem");

        const header = document.createElement("div");
        header.className = "agency-card__header";
        if (typeof window.renderAgencyLogo === "function") {
          header.appendChild(window.renderAgencyLogo(agency, 56));
        }
        const titles = document.createElement("div");
        titles.className = "agency-card__titles";
        const h = document.createElement("h3");
        h.className = "agency-card__title-ar";
        h.textContent = agency.name_ar;
        titles.appendChild(h);
        if (agency.name_en) {
          const e = document.createElement("p");
          e.className = "agency-card__title-en";
          e.textContent = agency.name_en;
          titles.appendChild(e);
        }
        header.appendChild(titles);
        card.appendChild(header);

        const meta = document.createElement("div");
        meta.className = "agency-card__meta";
        meta.appendChild(pill(t("تقارير: ", "Reports: ") + agency.report_count, "info"));
        meta.appendChild(pill(t("جاهزة: ", "Ready: ") + agency.ready_report_count, "success"));
        if (agency.requires_data_count) {
          meta.appendChild(pill(t("تحتاج بيانات: ", "Needs data: ") + agency.requires_data_count, "warning"));
        }
        card.appendChild(meta);
        card.appendChild(dqBadge(agency));

        const link = document.createElement("a");
        link.className = "admin-btn admin-btn-primary";
        link.href = "/admin/agency-reports/" + encodeURIComponent(agency.code);
        link.setAttribute("aria-label", t("عرض تقرير " + agency.name_ar, "View " + agency.name_en + " report"));
        link.textContent = t("عرض التقرير", "View report");
        card.appendChild(link);

        grid.appendChild(card);
      });

      root.appendChild(grid);
    })
    .catch(() => {
      root.textContent = lang === "en"
        ? "Unable to load official agency reports."
        : "تعذر تحميل تقارير الجهات الرسمية.";
    });
})();