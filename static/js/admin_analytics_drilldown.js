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
      `/api/analytics/drilldown/${dimensionType}/${dimensionId}?start_date=${start}&end_date=${end}`,
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
      '<div class="alert alert-danger">Failed to load data.</div>';
  }
}

function updateBreadcrumbsAndTitle(name, type) {
  document.getElementById("drilldownTitle").innerHTML =
    `<i class="bi bi-graph-up-arrow me-2 text-primary"></i> تحليل ${type === "GOVERNORATE" ? "محافظة" : "روضة"}: ${name}`;
  document.getElementById("breadcrumbDimension").textContent = name;
}

function populateSummaryCards(metrics, type) {
  const container = document.getElementById("summaryCardRow");
  if (!container) return;

  let cardsHtml = "";
  if (type.toUpperCase() === "GOVERNORATE") {
    cardsHtml = `
            <div class="col-md-4"><div class="card"><div class="card-body">
                <h6 class="text-muted">عدد الروضات</h6><h3 class="fw-bold">${metrics.kindergarten_count}</h3>
            </div></div></div>
            <div class="col-md-4"><div class="card"><div class="card-body">
                <h6 class="text-muted">إجمالي الأطفال</h6><h3 class="fw-bold">${metrics.children_count || "N/A"}</h3>
            </div></div></div>
            <div class="col-md-4"><div class="card"><div class="card-body">
                <h6 class="text-muted">متوسط الحوكمة</h6><h3 class="fw-bold">${metrics.governance_score ? metrics.governance_score.toFixed(1) : "N/A"}</h3>
            </div></div></div>
        `;
  } else {
    // KINDERGARTEN
    cardsHtml = `
            <div class="col-xl-3 col-md-6"><div class="card"><div class="card-body">
                <h6 class="text-muted">الأطفال</h6><h3 class="fw-bold">${metrics.children_count}</h3>
            </div></div></div>
            <div class="col-xl-3 col-md-6"><div class="card"><div class="card-body">
                <h6 class="text-muted">نسبة الحضور</h6><h3 class="fw-bold">${metrics.attendance_rate.toFixed(1)}%</h3>
            </div></div></div>
            <div class="col-xl-3 col-md-6"><div class="card"><div class="card-body">
                <h6 class="text-muted">معدل الحوادث</h6><h3 class="fw-bold">${metrics.incident_rate.toFixed(2)}</h3>
            </div></div></div>
            <div class="col-xl-3 col-md-6"><div class="card"><div class="card-body">
                <h6 class="text-muted">الحوكمة</h6><h3 class="fw-bold">${metrics.governance_score.toFixed(1)}</h3>
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
    document.getElementById("tableTitle").textContent =
      "أداء الروضات في المحافظة";
    headers = `
            <tr>
                <th role="button">الروضة</th>
                <th class="text-center" role="button" data-sort-method="number">الأطفال</th>
                <th class="text-center" role="button" data-sort-method="number">نسبة الحضور</th>
                <th class="text-center" role="button" data-sort-method="number">معدل الحوادث</th>
                <th class="text-center" role="button" data-sort-method="number">الحوكمة</th>
            </tr>
        `;
    rows = children
      .map(
        (kg) => `
            <tr data-kg-id="${kg.id}" style="cursor:pointer;" onclick="window.location.href='/kindergartens/${kg.id}'">
                <td class="fw-bold">${kg.name}</td>
                <td class="text-center">${kg.children_count}</td>
                <td class="text-center" data-sort="${kg.attendance_rate}"><span class="badge ${getScoreColor(kg.attendance_rate, true)}">${kg.attendance_rate.toFixed(1)}%</span></td>
                <td class="text-center" data-sort="${kg.incident_rate}">${kg.incident_rate.toFixed(2)}</td>
                <td class="text-center" data-sort="${kg.governance_score}">
                    <span class="fw-bold me-2">${kg.governance_score.toFixed(1)}</span>
                    <span class="badge ${getScoreColor(kg.governance_score)}">${kg.governance_band}</span>
                </td>
            </tr>
        `,
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
