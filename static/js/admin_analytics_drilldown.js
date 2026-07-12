document.addEventListener("DOMContentLoaded", function () {
  const today = new Date();
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
  const formatDate = (d) => d.toISOString().split("T")[0];

  const startInput = document.getElementById("periodStart");
  const endInput = document.getElementById("periodEnd");

  if (startInput && endInput) {
    startInput.value = formatDate(firstDay);
    endInput.value = formatDate(today);
    loadDrilldownData();
  }
});

let tableSorter = null;

function drilldownText(arText, enText) {
  const lang =
    window.AdminI18n?.getCurrentLanguage?.().code ||
    localStorage.getItem("admin_language") ||
    localStorage.getItem("kinjo_lang") ||
    document.documentElement.lang ||
    "ar";
  return String(lang).toLowerCase().startsWith("en") ? enText : arText;
}

function drilldownLiteral(value) {
  const raw = String(value ?? "");
  if (!raw) {
    return "";
  }
  let result = raw;
  if (typeof window.AdminI18n?.replaceLiteralSegments === "function") {
    result = window.AdminI18n.replaceLiteralSegments(raw);
  } else if (typeof window.AppI18n?.replaceLiteralSegments === "function") {
    result = window.AppI18n.replaceLiteralSegments(raw);
  }
  return typeof window.escapeHtml === "function" ? window.escapeHtml(result) : result;
}

// Build the drill-down URL for the next level. `id` may be an Arabic geographic
// name (governorate/city) so it must be URL-encoded.
function drillHref(nextType, id) {
  return `/admin/analytics/drilldown/${nextType}/${encodeURIComponent(id)}`;
}

async function loadDrilldownData() {
  const pathParts = window.location.pathname.split("/");
  const dimensionType = pathParts[pathParts.length - 2];
  const dimensionId = pathParts[pathParts.length - 1];

  const start = document.getElementById("periodStart").value;
  const end = document.getElementById("periodEnd").value;

  document.getElementById("loading").classList.remove("d-none");
  document.getElementById("content").classList.add("d-none");

  try {
    const response = await fetchWithAuth(
      `/api/analytics/drilldown/${dimensionType}/${dimensionId}?start_date=${start}&end_date=${end}`
    );
    if (!response) return;

    const data = await response.json();

    updateBreadcrumbsAndTitle(data.dimension_name, dimensionType);
    populateSummaryCards(data.metrics, dimensionType);
    populateTable(data.children, dimensionType);

    document.getElementById("loading").classList.add("d-none");
    document.getElementById("content").classList.remove("d-none");
  } catch (error) {
    console.error("Drilldown load error:", error);
    document.getElementById("loading").innerHTML =
      `<div class="alert alert-danger">${drilldownText("تعذر تحميل البيانات.", "Unable to load data.")}</div>`;
  }
}

function updateBreadcrumbsAndTitle(name, type) {
  // Country -> Governorate -> City -> Nursery -> Class -> Child
  const typeLabelMap = {
    NETWORK: drilldownText("الشبكة", "Network"),
    GOVERNORATE: drilldownText("محافظة", "Governorate"),
    DISTRICT: drilldownText("لواء", "District"),
    AREA: drilldownText("مدينة", "City"),
    KINDERGARTEN: drilldownText("حضانة", "Nursery"),
    CLASS: drilldownText("صف", "Class"),
    CHILD: drilldownText("طفل", "Child"),
  };
  const typeLabel = typeLabelMap[type.toUpperCase()] || typeLabelMap.KINDERGARTEN;
  const displayName = drilldownLiteral(name);

  document.getElementById("drilldownTitle").innerHTML =
    `<i class="bi bi-graph-up-arrow me-2 text-primary"></i> ${drilldownText("تحليل", "Analysis")} ${typeLabel}: ${displayName}`;
  const breadcrumbEl = document.getElementById("breadcrumbDimension");
  if (breadcrumbEl) breadcrumbEl.textContent = displayName;
}

function summaryCard(labelAr, labelEn, value) {
  return `
            <div class="col-md-4"><div class="card"><div class="card-body">
                <h6 class="text-muted">${drilldownText(labelAr, labelEn)}</h6><h3 class="fw-bold">${value}</h3>
            </div></div></div>`;
}

function populateSummaryCards(metrics, type) {
  const container = document.getElementById("summaryCardRow");
  if (!container) return;
  const t = type.toUpperCase();
  let cardsHtml = "";

  if (t === "NETWORK") {
    cardsHtml =
      summaryCard("عدد المحافظات", "Governorates", metrics.governorate_count) +
      summaryCard("عدد الحضانات", "Nurseries", metrics.nursery_count) +
      summaryCard("إجمالي الأطفال", "Total children", metrics.children_count ?? "N/A");
  } else if (t === "GOVERNORATE" || t === "DISTRICT") {
    cardsHtml =
      summaryCard("عدد المدن", "Cities", metrics.city_count) +
      summaryCard("عدد الحضانات", "Nurseries", metrics.nursery_count) +
      summaryCard("إجمالي الأطفال", "Total children", metrics.children_count ?? "N/A");
  } else if (t === "AREA") {
    cardsHtml =
      summaryCard("عدد الحضانات", "Nurseries", metrics.nursery_count) +
      summaryCard("إجمالي الأطفال", "Total children", metrics.children_count ?? "N/A") +
      summaryCard(
        "متوسط الحوكمة", "Average governance",
        metrics.governance_score ? metrics.governance_score.toFixed(1) : "N/A"
      );
  } else if (t === "CLASS") {
    cardsHtml =
      summaryCard("الأطفال", "Children", metrics.children_count) +
      summaryCard("السعة", "Capacity", metrics.capacity) +
      summaryCard("الفئة العمرية", "Age group", drilldownLiteral(metrics.age_group));
  } else if (t === "CHILD") {
    cardsHtml =
      summaryCard(
        "نسبة الحضور", "Attendance rate",
        metrics.attendance_rate == null ? drilldownText("بيانات غير كافية", "Insufficient data")
                                        : metrics.attendance_rate.toFixed(1) + "%"
      ) +
      summaryCard("أيام الحضور", "Attendance days", metrics.attendance_days) +
      summaryCard("الأيام المسجّلة", "Logged days", metrics.logged_days);
  } else {
    // KINDERGARTEN (Nursery)
    cardsHtml = `
            <div class="col-xl-3 col-md-6"><div class="card"><div class="card-body">
                <h6 class="text-muted">${drilldownText("الأطفال", "Children")}</h6><h3 class="fw-bold">${metrics.children_count}</h3>
            </div></div></div>
            <div class="col-xl-3 col-md-6"><div class="card"><div class="card-body">
                <h6 class="text-muted">${drilldownText("نسبة الحضور", "Attendance rate")}</h6><h3 class="fw-bold">${(metrics.attendance_rate ?? 0).toFixed(1)}%</h3>
            </div></div></div>
            <div class="col-xl-3 col-md-6"><div class="card"><div class="card-body">
                <h6 class="text-muted">${drilldownText("معدل الحوادث /1K", "Incident rate /1K")}</h6><h3 class="fw-bold">${(metrics.incident_rate ?? 0).toFixed(2)}</h3>
            </div></div></div>
            <div class="col-xl-3 col-md-6"><div class="card"><div class="card-body">
                <h6 class="text-muted">${drilldownText("الحوكمة", "Governance")}</h6><h3 class="fw-bold">${(metrics.governance_score ?? 0).toFixed(1)}</h3>
            </div></div></div>
        `;
  }
  container.innerHTML = cardsHtml;
}

// Geographic list (Network->Governorates, Governorate/District->Cities): a name +
// nursery count + children count, each row drilling to `row.dimension_type`.
function geoListTable(children, firstColAr, firstColEn, titleAr, titleEn) {
  document.getElementById("tableTitle").textContent = drilldownText(titleAr, titleEn);
  const headers = `
            <tr>
                <th scope="col" role="button">${drilldownText(firstColAr, firstColEn)}</th>
                <th scope="col" class="text-center" role="button" data-sort-method="number">${drilldownText("عدد الحضانات", "Nurseries")}</th>
                <th scope="col" class="text-center" role="button" data-sort-method="number">${drilldownText("الأطفال", "Children")}</th>
            </tr>`;
  const rows = children
    .map(
      (r) => `
            <tr style="cursor:pointer;" onclick="window.location.href=drillHref('${r.dimension_type}', ${JSON.stringify(String(r.id))})">
                <td class="fw-bold">${drilldownLiteral(r.name)}</td>
                <td class="text-center" data-sort="${r.nursery_count}">${r.nursery_count}</td>
                <td class="text-center" data-sort="${r.children_count}">${r.children_count}</td>
            </tr>`
    )
    .join("");
  return { headers, rows };
}

function populateTable(children, type) {
  const table = document.getElementById("drilldownTable");
  const thead = document.getElementById("drilldownThead");
  const tbody = document.getElementById("drilldownTbody");
  if (!thead || !tbody) return;

  const t = type.toUpperCase();
  let headers = "";
  let rows = "";

  if (t === "NETWORK") {
    ({ headers, rows } = geoListTable(
      children, "المحافظة", "Governorate",
      "المحافظات في الشبكة", "Governorates in the network"
    ));
  } else if (t === "GOVERNORATE" || t === "DISTRICT") {
    ({ headers, rows } = geoListTable(
      children, "المدينة", "City",
      "المدن في المحافظة", "Cities in the governorate"
    ));
  } else if (t === "AREA") {
    // City -> Nurseries (with per-nursery performance), drilling to Nursery.
    document.getElementById("tableTitle").textContent = drilldownText(
      "أداء الحضانات في المدينة", "Nursery performance in the city"
    );
    headers = `
            <tr>
                <th scope="col" role="button">${drilldownText("الحضانة", "Nursery")}</th>
                <th scope="col" class="text-center" role="button" data-sort-method="number">${drilldownText("الأطفال", "Children")}</th>
                <th scope="col" class="text-center" role="button" data-sort-method="number">${drilldownText("نسبة الحضور", "Attendance rate")}</th>
                <th scope="col" class="text-center" role="button" data-sort-method="number">${drilldownText("معدل الحوادث /1K", "Incident rate /1K")}</th>
                <th scope="col" class="text-center" role="button" data-sort-method="number">${drilldownText("الحوكمة", "Governance")}</th>
            </tr>`;
    rows = children
      .map(
        (kg) => `
            <tr data-kg-id="${kg.id}" style="cursor:pointer;" onclick="window.location.href=drillHref('KINDERGARTEN', ${kg.id})">
                <td class="fw-bold">${drilldownLiteral(kg.name)}</td>
                <td class="text-center">${kg.children_count}</td>
                <td class="text-center" data-sort="${kg.attendance_rate}"><span class="badge ${getScoreColor(kg.attendance_rate, true)}">${(kg.attendance_rate ?? 0).toFixed(1)}%</span></td>
                <td class="text-center" data-sort="${kg.incident_rate}">${(kg.incident_rate ?? 0).toFixed(2)}/1K</td>
                <td class="text-center" data-sort="${kg.governance_score}">
                    <span class="fw-bold me-2">${(kg.governance_score ?? 0).toFixed(1)}</span>
                    <span class="badge ${kg.governance_band === "INSUFFICIENT" ? "bg-secondary" : getScoreColor(kg.governance_score)}">${kg.governance_band === "INSUFFICIENT" ? drilldownText("بيانات غير كافية", "Insufficient data") : drilldownLiteral(kg.governance_band)}</span>
                </td>
            </tr>`
      )
      .join("");
  } else if (t === "KINDERGARTEN") {
    document.getElementById("tableTitle").textContent = drilldownText(
      "الصفوف في الحضانة", "Classes in the nursery"
    );
    headers = `
            <tr>
                <th scope="col" role="button">${drilldownText("الصف", "Class")}</th>
                <th scope="col" class="text-center" role="button" data-sort-method="number">${drilldownText("الأطفال", "Children")}</th>
                <th scope="col" class="text-center" role="button" data-sort-method="number">${drilldownText("السعة", "Capacity")}</th>
                <th scope="col" role="button">${drilldownText("الفئة العمرية", "Age group")}</th>
            </tr>`;
    rows = children
      .map(
        (cls) => `
            <tr data-class-id="${cls.id}" style="cursor:pointer;" onclick="window.location.href=drillHref('CLASS', ${cls.id})">
                <td class="fw-bold">${drilldownLiteral(cls.name)}</td>
                <td class="text-center" data-sort="${cls.children_count}">${cls.children_count}</td>
                <td class="text-center" data-sort="${cls.capacity}">${cls.capacity}</td>
                <td>${drilldownLiteral(cls.age_group)}</td>
            </tr>`
      )
      .join("");
  } else if (t === "CLASS") {
    document.getElementById("tableTitle").textContent = drilldownText(
      "الأطفال في الصف", "Children in the class"
    );
    headers = `
            <tr>
                <th scope="col" role="button">${drilldownText("الطفل", "Child")}</th>
                <th scope="col" class="text-center" role="button" data-sort-method="number">${drilldownText("نسبة الحضور", "Attendance rate")}</th>
                <th scope="col" class="text-center" role="button" data-sort-method="number">${drilldownText("أيام الحضور", "Attendance days")}</th>
            </tr>`;
    rows = children
      .map(
        (child) => `
            <tr style="cursor:pointer;" onclick="window.location.href=drillHref('CHILD', ${child.id})">
                <td class="fw-bold">${drilldownLiteral(child.name)}</td>
                <td class="text-center" data-sort="${child.attendance_rate}"><span class="badge ${getScoreColor(child.attendance_rate, true)}">${(child.attendance_rate ?? 0).toFixed(1)}%</span></td>
                <td class="text-center">${child.attendance_days}</td>
            </tr>`
      )
      .join("");
  } else if (t === "CHILD") {
    // Leaf level: no further drill-down. Detail is shown in the summary cards.
    document.getElementById("tableTitle").textContent = drilldownText(
      "تفاصيل الطفل", "Child details"
    );
    headers = "";
    rows = "";
  }

  thead.innerHTML = headers;
  tbody.innerHTML = rows;

  if (tableSorter) tableSorter.destroy();
  if (table && headers) tableSorter = new Tablesort(table);
}

function getScoreColor(score, isAttendance = false) {
  if (isAttendance) {
    if (score >= 90) return "bg-success-subtle text-success-emphasis";
    if (score >= 80) return "bg-warning-subtle text-warning-emphasis";
    return "bg-danger-subtle text-danger-emphasis";
  }
  if (score >= 80) return "bg-success";
  if (score >= 60) return "bg-warning";
  return "bg-danger";
}

// fetchWithAuth is now defined in auth.js

// The shared date-range-filter macro's "Last Month"/"Clear Filters"
// buttons look for a global applyDateFilter() to trigger a reload after
// updating the date inputs -- without this alias they silently updated
// the date pickers with no visible effect (only the explicit Refresh
// button, wired via on_refresh="loadDrilldownData", actually reloaded).
window.applyDateFilter = loadDrilldownData;

window.addEventListener("languageChanged", () => {
  if (!document.getElementById("content")?.classList.contains("d-none")) {
    loadDrilldownData();
  }
});
