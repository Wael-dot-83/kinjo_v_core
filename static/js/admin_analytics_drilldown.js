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
  const typeLabel =
    type === "GOVERNORATE"
      ? drilldownText("محافظة", "Governorate")
      : drilldownText("حضانة", "Kindergarten");
  const displayName = drilldownLiteral(name);

  document.getElementById("drilldownTitle").innerHTML =
    `<i class="bi bi-graph-up-arrow me-2 text-primary"></i> ${drilldownText("تحليل", "Analysis")} ${typeLabel}: ${displayName}`;
  document.getElementById("breadcrumbDimension").textContent = displayName;
}

function populateSummaryCards(metrics, type) {
  const container = document.getElementById("summaryCardRow");
  if (!container) return;

  let cardsHtml = "";
  if (type.toUpperCase() === "GOVERNORATE") {
    cardsHtml = `
            <div class="col-md-4"><div class="card"><div class="card-body">
                <h6 class="text-muted">${drilldownText("عدد الحضانات", "Number of kindergartens")}</h6><h3 class="fw-bold">${metrics.kindergarten_count}</h3>
            </div></div></div>
            <div class="col-md-4"><div class="card"><div class="card-body">
                <h6 class="text-muted">${drilldownText("إجمالي الأطفال", "Total children")}</h6><h3 class="fw-bold">${metrics.children_count || "N/A"}</h3>
            </div></div></div>
            <div class="col-md-4"><div class="card"><div class="card-body">
                <h6 class="text-muted">${drilldownText("متوسط الحوكمة", "Average governance")}</h6><h3 class="fw-bold">${metrics.governance_score ? metrics.governance_score.toFixed(1) : "N/A"}</h3>
            </div></div></div>
        `;
  } else {
    // KINDERGARTEN
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

function populateTable(children, type) {
  const table = document.getElementById("drilldownTable");
  const thead = document.getElementById("drilldownThead");
  const tbody = document.getElementById("drilldownTbody");
  if (!thead || !tbody) return;

  let headers = "";
  let rows = "";

  if (type.toUpperCase() === "GOVERNORATE") {
    document.getElementById("tableTitle").textContent = drilldownText(
      "أداء الحضانات في المحافظة",
      "Kindergarten performance in the governorate"
    );
    headers = `
            <tr>
                <th role="button">${drilldownText("الحضانة", "Kindergarten")}</th>
                <th class="text-center" role="button" data-sort-method="number">${drilldownText("الأطفال", "Children")}</th>
                <th class="text-center" role="button" data-sort-method="number">${drilldownText("نسبة الحضور", "Attendance rate")}</th>
                <th class="text-center" role="button" data-sort-method="number">${drilldownText("معدل الحوادث /1K", "Incident rate /1K")}</th>
                <th class="text-center" role="button" data-sort-method="number">${drilldownText("الحوكمة", "Governance")}</th>
            </tr>
        `;
    rows = children
      .map(
        (kg) => `
            <tr data-kg-id="${kg.id}" style="cursor:pointer;" onclick="window.location.href='/kindergartens/${kg.id}'">
                <td class="fw-bold">${drilldownLiteral(kg.name)}</td>
                <td class="text-center">${kg.children_count}</td>
                <td class="text-center" data-sort="${kg.attendance_rate}"><span class="badge ${getScoreColor(kg.attendance_rate, true)}">${(kg.attendance_rate ?? 0).toFixed(1)}%</span></td>
                <td class="text-center" data-sort="${kg.incident_rate}">${(kg.incident_rate ?? 0).toFixed(2)}/1K</td>
                <td class="text-center" data-sort="${kg.governance_score}">
                    <span class="fw-bold me-2">${(kg.governance_score ?? 0).toFixed(1)}</span>
                    <span class="badge ${kg.governance_band === "INSUFFICIENT" ? "bg-secondary" : getScoreColor(kg.governance_score)}">${kg.governance_band === "INSUFFICIENT" ? drilldownText("بيانات غير كافية", "Insufficient data") : drilldownLiteral(kg.governance_band)}</span>
                </td>
            </tr>
        `
      )
      .join("");
  }
  // Add logic for KINDERGARTEN -> CLASS drilldown if needed later

  thead.innerHTML = headers;
  tbody.innerHTML = rows;

  if (tableSorter) tableSorter.destroy();
  tableSorter = new Tablesort(table);
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

window.addEventListener("languageChanged", () => {
  if (!document.getElementById("content")?.classList.contains("d-none")) {
    loadDrilldownData();
  }
});
