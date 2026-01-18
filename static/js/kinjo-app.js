/**
 * KinJo Application JavaScript
 * Main application logic and UI interactions
 */

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Show loading overlay
 */
function showLoading() {
  const overlay = document.getElementById("loadingOverlay");
  if (overlay) {
    overlay.style.display = "flex";
  } else {
    const newOverlay = document.createElement("div");
    newOverlay.id = "loadingOverlay";
    newOverlay.className = "loading-overlay";
    newOverlay.innerHTML = '<div class="loading-spinner"></div>';
    document.body.appendChild(newOverlay);
  }
}

/**
 * Hide loading overlay
 */
function hideLoading() {
  const overlay = document.getElementById("loadingOverlay");
  if (overlay) {
    overlay.style.display = "none";
  }
}

/**
 * Show toast notification
 */
function showToast(message, type = "info") {
  const container =
    document.getElementById("toastContainer") || createToastContainer();

  const toastId = `toast-${Date.now()}`;
  const iconMap = {
    success: "check-circle-fill",
    error: "exclamation-triangle-fill",
    warning: "exclamation-circle-fill",
    info: "info-circle-fill",
  };

  const bgMap = {
    success: "bg-success",
    error: "bg-danger",
    warning: "bg-warning",
    info: "bg-primary",
  };

  const toastHTML = `
        <div id="${toastId}" class="toast align-items-center text-white ${bgMap[type]} border-0" role="alert">
            <div class="d-flex">
                <div class="toast-body">
                    <i class="bi bi-${iconMap[type]} me-2"></i>
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;

  container.insertAdjacentHTML("beforeend", toastHTML);

  const toastElement = document.getElementById(toastId);
  const toast = new bootstrap.Toast(toastElement, { delay: 5000 });
  toast.show();

  toastElement.addEventListener("hidden.bs.toast", () => {
    toastElement.remove();
  });
}

/**
 * Show error message (alias for showToast with error type)
 */
function showError(message) {
  showToast(message, "error");
}

/**
 * Create toast container if not exists
 */
function createToastContainer() {
  const container = document.createElement("div");
  container.id = "toastContainer";
  container.className = "toast-container position-fixed top-0 end-0 p-3";
  container.style.zIndex = "1100";
  document.body.appendChild(container);
  return container;
}

/**
 * Format date for display (Arabic)
 */
function formatDate(dateString, includeTime = false) {
  const date = new Date(dateString);
  const options = {
    year: "numeric",
    month: "long",
    day: "numeric",
  };

  if (includeTime) {
    options.hour = "2-digit";
    options.minute = "2-digit";
  }

  return date.toLocaleDateString("ar-JO", options);
}

/**
 * Format date for API (ISO)
 */
function formatDateISO(date) {
  return date.toISOString().split("T")[0];
}

/**
 * Get status badge HTML
 */
function getStatusBadge(status) {
  const statusMap = {
    draft: { class: "bg-secondary", text: "مسودة" },
    submitted: { class: "bg-info", text: "مُقدم" },
    pending_review: { class: "bg-warning", text: "قيد المراجعة" },
    accepted: { class: "bg-success", text: "مقبول" },
    rejected: { class: "bg-danger", text: "مرفوض" },
    active: { class: "bg-success", text: "نشط" },
    inactive: { class: "bg-secondary", text: "غير نشط" },
    withdrawn: { class: "bg-dark", text: "منسحب" },
    waitlisted: { class: "bg-warning", text: "قائمة انتظار" },
    approved: { class: "bg-success", text: "معتمد" },
    returned: { class: "bg-warning", text: "مُعاد" },
  };

  const info = statusMap[status] || { class: "bg-secondary", text: status };
  return `<span class="badge ${info.class}">${info.text}</span>`;
}

/**
 * Toggle language between Arabic and English
 */
function toggleLanguage() {
  const currentLang = document.documentElement.lang;
  const newLang = currentLang === "ar" ? "en" : "ar";
  const newDir = newLang === "ar" ? "rtl" : "ltr";

  document.documentElement.lang = newLang;
  document.documentElement.dir = newDir;

  localStorage.setItem("kinjo_lang", newLang);

  // Reload to apply language changes
  window.location.reload();
}

/**
 * Logout user
 */
function logout() {
  api.logout();
}

/**
 * Confirm action with modal
 */
function confirmAction(title, message, onConfirm) {
  const modalHTML = `
        <div class="modal fade" id="confirmModal" tabindex="-1">
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">${title}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p>${message}</p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">إلغاء</button>
                        <button type="button" class="btn btn-primary" id="confirmActionBtn">تأكيد</button>
                    </div>
                </div>
            </div>
        </div>
    `;

  // Remove existing modal
  const existingModal = document.getElementById("confirmModal");
  if (existingModal) {
    existingModal.remove();
  }

  document.body.insertAdjacentHTML("beforeend", modalHTML);

  const modal = new bootstrap.Modal(document.getElementById("confirmModal"));
  modal.show();

  document.getElementById("confirmActionBtn").addEventListener("click", () => {
    modal.hide();
    onConfirm();
  });
}

// ============================================================================
// Form Validation
// ============================================================================

/**
 * Initialize Bootstrap form validation
 */
function initFormValidation() {
  const forms = document.querySelectorAll(".needs-validation");

  forms.forEach((form) => {
    form.addEventListener(
      "submit",
      (event) => {
        if (!form.checkValidity()) {
          event.preventDefault();
          event.stopPropagation();
        }
        form.classList.add("was-validated");
      },
      false
    );
  });
}

/**
 * Validate Jordan phone number
 */
function validateJordanPhone(phone) {
  const pattern = /^(\+962|00962|0)[0-9]{9}$/;
  return pattern.test(phone);
}

/**
 * Validate National ID
 */
function validateNationalId(id) {
  return /^\d{10}$/.test(id);
}

// ============================================================================
// Data Tables
// ============================================================================

/**
 * Initialize data table with search and pagination
 */
function initDataTable(tableId, options = {}) {
  const table = document.getElementById(tableId);
  if (!table) return;

  const searchInput = document.getElementById(`${tableId}Search`);
  const tbody = table.querySelector("tbody");
  const rows = Array.from(tbody.querySelectorAll("tr"));

  // Search functionality
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      const searchTerm = searchInput.value.toLowerCase();

      rows.forEach((row) => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(searchTerm) ? "" : "none";
      });
    });
  }
}

// ============================================================================
// Charts
// ============================================================================

/**
 * Create attendance chart
 */
function createAttendanceChart(canvasId, data) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  return new Chart(ctx, {
    type: "line",
    data: {
      labels: data.labels,
      datasets: [
        {
          label: "نسبة الحضور %",
          data: data.values,
          borderColor: "#0d6efd",
          backgroundColor: "rgba(13, 110, 253, 0.1)",
          fill: true,
          tension: 0.4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false,
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          max: 100,
        },
      },
    },
  });
}

/**
 * Create enrollment status pie chart
 */
function createEnrollmentPieChart(canvasId, data) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  return new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: data.labels,
      datasets: [
        {
          data: data.values,
          backgroundColor: [
            "#198754",
            "#ffc107",
            "#0dcaf0",
            "#dc3545",
            "#6c757d",
          ],
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "bottom",
        },
      },
    },
  });
}

/**
 * Create KPI gauge chart
 */
function createGaugeChart(canvasId, value, label, color = "#0d6efd") {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  return new Chart(ctx, {
    type: "doughnut",
    data: {
      datasets: [
        {
          data: [value, 100 - value],
          backgroundColor: [color, "#e9ecef"],
          borderWidth: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      circumference: 180,
      rotation: 270,
      cutout: "80%",
      plugins: {
        legend: {
          display: false,
        },
        tooltip: {
          enabled: false,
        },
      },
    },
  });
}

// ============================================================================
// Page-Specific Initializers
// ============================================================================

/**
 * Initialize dashboard page
 */
async function initDashboard() {
  try {
    showLoading();

    // Load dashboard data based on user role
    const user = await api.getCurrentUser();

    if (user.role === "supervisor") {
      const dashboard = await api.getSupervisorDashboard();
      renderSupervisorDashboard(dashboard);
    } else if (user.role === "admin" || user.role === "manager") {
      // Dashboard loading is handled by the HTML template
      console.log("Manager dashboard handled by HTML template");
    } else {
      await loadParentDashboard();
    }

    hideLoading();
  } catch (error) {
    hideLoading();
    showToast("حدث خطأ في تحميل لوحة التحكم", "error");
    console.error("Dashboard error:", error);
  }
}

/**
 * Render supervisor dashboard
 */
function renderSupervisorDashboard(data) {
  // Update stats cards
  updateStatCard("totalChildren", data.total_children);
  updateStatCard("presentToday", data.attendance?.present || 0);
  updateStatCard("absentToday", data.attendance?.absent || 0);
  updateStatCard("pendingReports", data.pending_reports?.length || 0);

  // Render pending reports list
  if (data.pending_reports && data.pending_reports.length > 0) {
    const container = document.getElementById("pendingReportsList");
    if (container) {
      container.innerHTML = data.pending_reports
        .map(
          (child) => `
                <a href="/daily-reports/create?child_id=${child.child_id}" class="list-group-item list-group-item-action">
                    <div class="d-flex w-100 justify-content-between">
                        <h6 class="mb-1">${child.first_name} ${child.last_name}</h6>
                        <small class="text-muted">يتطلب تقرير</small>
                    </div>
                </a>
            `
        )
        .join("");
    }
  }
}

/**
 * Load parent dashboard
 */
async function loadParentDashboard() {
  // Load parent-specific data
}
async function loadParentDashboard() {
  // Load parent-specific data
}

/**
 * Update stat card value
 */
function updateStatCard(cardId, value) {
  const element = document.getElementById(cardId);
  if (element) {
    element.textContent = value;
  }
}

// ============================================================================
// Enrollment Form Handlers
// ============================================================================

/**
 * Initialize enrollment form
 */
function initEnrollmentForm() {
  const nationalitySelect = document.getElementById("nationality");
  const nationalIdGroup = document.getElementById("nationalIdGroup");
  const passportGroup = document.getElementById("passportGroup");

  if (nationalitySelect) {
    nationalitySelect.addEventListener("change", () => {
      const isJordanian = nationalitySelect.value === "Jordanian";

      if (nationalIdGroup) {
        nationalIdGroup.style.display = isJordanian ? "block" : "none";
        nationalIdGroup.querySelector("input").required = isJordanian;
      }

      if (passportGroup) {
        passportGroup.style.display = isJordanian ? "none" : "block";
        passportGroup.querySelector("input").required = !isJordanian;
      }
    });
  }

  // Mother nationality handler
  const motherNationalitySelect = document.getElementById("motherNationality");
  const motherNationalIdGroup = document.getElementById(
    "motherNationalIdGroup"
  );
  const motherPassportGroup = document.getElementById("motherPassportGroup");

  if (motherNationalitySelect) {
    motherNationalitySelect.addEventListener("change", () => {
      const isJordanian = motherNationalitySelect.value === "Jordanian";

      if (motherNationalIdGroup) {
        motherNationalIdGroup.style.display = isJordanian ? "block" : "none";
      }

      if (motherPassportGroup) {
        motherPassportGroup.style.display = isJordanian ? "none" : "block";
      }
    });
  }
}

/**
 * Submit enrollment form
 */
async function submitEnrollmentForm(form) {
  try {
    showLoading();

    const formData = new FormData(form);
    const data = Object.fromEntries(formData.entries());

    await api.createEnrollment(data);

    showToast("تم تقديم طلب التسجيل بنجاح", "success");

    setTimeout(() => {
      window.location.href = "/enrollments";
    }, 1500);
  } catch (error) {
    hideLoading();
    showToast(error.message || "حدث خطأ في تقديم الطلب", "error");
  }
}

// ============================================================================
// Attendance Handlers
// ============================================================================

/**
 * Initialize attendance page
 */
async function initAttendancePage() {
  try {
    showLoading();

    const status = await api.getAttendanceStatus();
    renderAttendanceGrid(status);

    hideLoading();
  } catch (error) {
    hideLoading();
    showToast("حدث خطأ في تحميل بيانات الحضور", "error");
  }
}

/**
 * Render attendance grid
 */
function renderAttendanceGrid(data) {
  const container = document.getElementById("attendanceGrid");
  if (!container || !data.children) return;

  container.innerHTML = data.children
    .map(
      (child) => `
        <div class="attendance-cell ${child.is_present ? "present" : ""}" 
             data-child-id="${child.child_id}"
             onclick="toggleAttendance(${child.child_id})">
            <i class="bi bi-${
              child.is_present
                ? "check-circle-fill text-success"
                : "circle text-muted"
            } fs-4"></i>
            <div class="mt-2 small">${child.first_name}</div>
        </div>
    `
    )
    .join("");
}

/**
 * Toggle child attendance
 */
async function toggleAttendance(childId) {
  try {
    const cell = document.querySelector(`[data-child-id="${childId}"]`);
    const isPresent = cell.classList.contains("present");

    if (isPresent) {
      await api.checkOut(childId);
      cell.classList.remove("present");
    } else {
      await api.checkIn(childId, "kiosk");
      cell.classList.add("present");
    }

    showToast(isPresent ? "تم تسجيل الخروج" : "تم تسجيل الحضور", "success");
  } catch (error) {
    showToast(error.message || "حدث خطأ", "error");
  }
}

// ============================================================================
// Daily Report Handlers
// ============================================================================

/**
 * Initialize daily report form
 */
function initDailyReportForm() {
  // Meal checkbox toggles
  document.querySelectorAll(".meal-checkbox").forEach((checkbox) => {
    checkbox.addEventListener("click", () => {
      checkbox.classList.toggle("checked");
      const input = checkbox.querySelector("input");
      input.checked = !input.checked;
    });
  });

  // Nap time calculation
  const napStart = document.getElementById("napStart");
  const napEnd = document.getElementById("napEnd");
  const napDuration = document.getElementById("napDuration");

  if (napStart && napEnd && napDuration) {
    const calculateNapDuration = () => {
      if (napStart.value && napEnd.value) {
        const start = new Date(`2000-01-01 ${napStart.value}`);
        const end = new Date(`2000-01-01 ${napEnd.value}`);
        const diff = (end - start) / 60000; // minutes
        napDuration.value = diff > 0 ? diff : 0;
      }
    };

    napStart.addEventListener("change", calculateNapDuration);
    napEnd.addEventListener("change", calculateNapDuration);
  }
}

/**
 * Submit daily report
 */
async function submitDailyReport(form) {
  try {
    showLoading();

    const formData = new FormData(form);
    const data = Object.fromEntries(formData.entries());

    // Convert checkbox values
    data.breakfast = data.breakfast === "on";
    data.snack = data.snack === "on";
    data.milk = data.milk === "on";
    data.lunch = data.lunch === "on";

    await api.createDailyReport(data);

    showToast("تم حفظ التقرير اليومي بنجاح", "success");

    setTimeout(() => {
      window.location.href = "/daily-reports";
    }, 1500);
  } catch (error) {
    hideLoading();
    showToast(error.message || "حدث خطأ في حفظ التقرير", "error");
  }
}

// ============================================================================
// Global Event Listeners
// ============================================================================

document.addEventListener("DOMContentLoaded", () => {
  // Initialize form validation
  initFormValidation();

  // Initialize data tables
  document.querySelectorAll(".data-table").forEach((table) => {
    initDataTable(table.id);
  });

  // Initialize enrollment form if present
  if (document.getElementById("enrollmentForm")) {
    initEnrollmentForm();
  }

  // Initialize daily report form if present
  if (document.getElementById("dailyReportForm")) {
    initDailyReportForm();
  }

  // Load stored language preference
  const storedLang = localStorage.getItem("kinjo_lang");
  if (storedLang && storedLang !== document.documentElement.lang) {
    document.documentElement.lang = storedLang;
    document.documentElement.dir = storedLang === "ar" ? "rtl" : "ltr";
  }

  // Global search handler
  const searchForm = document.getElementById("globalSearchForm");
  if (searchForm) {
    searchForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const query = document.getElementById("globalSearchInput").value;
      if (query) {
        window.location.href = `/search?q=${encodeURIComponent(query)}`;
      }
    });
  }
});

// Handle page visibility for session timeout
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && api.isAuthenticated()) {
    // Check if session is still valid
    api.getCurrentUser().catch(() => {
      showToast("انتهت الجلسة، يرجى تسجيل الدخول مرة أخرى", "warning");
      setTimeout(() => api.logout(), 2000);
    });
  }
});
