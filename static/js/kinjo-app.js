/**
 * KinJo Application JavaScript
 * Main application logic and UI interactions
 */

function appCurrentLang() {
  if (window.AppI18n && window.AppI18n.currentLang) {
    return window.AppI18n.currentLang;
  }
  return document.documentElement.lang === "en" ? "en" : "ar";
}

function appCurrentLocale() {
  return appCurrentLang() === "en" ? "en-US" : "ar-JO";
}

function appText(key, arText, enText) {
  const lang = appCurrentLang();
  if (window.AppI18n && typeof window.AppI18n.t === "function") {
    const translated = window.AppI18n.t(key);
    if (translated && translated !== key) {
      return translated;
    }
  }
  return lang === "en" ? enText : arText;
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Show loading overlay
 */
function showLoading() {
  const overlay = document.getElementById("loadingOverlay");
  if (
    window.PageLoadTimer &&
    typeof window.PageLoadTimer.startTask === "function"
  ) {
    if (!window.__kinjoLoadingTaskEnd) {
      window.__kinjoLoadingTaskEnd = window.PageLoadTimer.startTask();
    }
  }
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
  if (typeof window.__kinjoLoadingTaskEnd === "function") {
    window.__kinjoLoadingTaskEnd();
    window.__kinjoLoadingTaskEnd = null;
  }
}

/**
 * Show toast notification
 */
function showToast(message, type = "info") {
  const container =
    document.getElementById("toastContainer") || createToastContainer();
  const closeLabel = appText("common.close", "إغلاق", "Close");

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
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="${closeLabel}"></button>
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
 * Format date for display
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

  return date.toLocaleDateString(appCurrentLocale(), options);
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
    draft: {
      class: "bg-secondary",
      text: appText("status.draft", "مسودة", "Draft"),
    },
    submitted: {
      class: "bg-info",
      text: appText("status.submitted", "مُقدم", "Submitted"),
    },
    pending_review: {
      class: "bg-warning",
      text: appText("status.pending_review", "قيد المراجعة", "Pending review"),
    },
    accepted: {
      class: "bg-success",
      text: appText("status.accepted", "مقبول", "Accepted"),
    },
    rejected: {
      class: "bg-danger",
      text: appText("status.rejected", "مرفوض", "Rejected"),
    },
    active: {
      class: "bg-success",
      text: appText("status.active", "نشط", "Active"),
    },
    inactive: {
      class: "bg-secondary",
      text: appText("status.inactive", "غير نشط", "Inactive"),
    },
    withdrawn: {
      class: "bg-dark",
      text: appText("status.withdrawn", "منسحب", "Withdrawn"),
    },
    waitlisted: {
      class: "bg-warning",
      text: appText("status.waitlisted", "قائمة انتظار", "Waitlisted"),
    },
    approved: {
      class: "bg-success",
      text: appText("status.approved", "معتمد", "Approved"),
    },
    returned: {
      class: "bg-warning",
      text: appText("status.returned", "مُعاد", "Returned"),
    },
  };

  // Status values arrive from the API in UPPERCASE (e.g. "PENDING_REVIEW",
  // "ACTIVE"); the map keys are lowercase, so normalise before lookup.
  const key = String(status ?? "").toLowerCase();
  const info = statusMap[key] || { class: "bg-secondary", text: status };
  return `<span class="badge ${info.class}">${info.text}</span>`;
}

/**
 * Toggle language between Arabic and English
 */
function toggleLanguage() {
  if (window.AppI18n && typeof window.AppI18n.toggleLanguage === "function") {
    window.AppI18n.toggleLanguage();
    return;
  }

  const currentLang = document.documentElement.lang;
  const newLang = currentLang === "ar" ? "en" : "ar";
  document.documentElement.lang = newLang;
  document.documentElement.dir = newLang === "ar" ? "rtl" : "ltr";
  localStorage.setItem("kinjo_lang", newLang);
  localStorage.setItem("admin_language", newLang);
  document.cookie = `kinjo_lang=${newLang}; path=/; max-age=31536000; SameSite=Lax`;
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
  const closeLabel = appText("common.close", "إغلاق", "Close");
  const modalHTML = `
        <div class="modal fade" id="confirmModal" tabindex="-1">
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">${title}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="${closeLabel}"></button>
                    </div>
                    <div class="modal-body">
                        <p>${message}</p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">${appText("common.cancel", "إلغاء", "Cancel")}</button>
                        <button type="button" class="btn btn-primary" id="confirmActionBtn">${appText("common.confirm", "تأكيد", "Confirm")}</button>
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
// Page Guidance & Inline Help
// ============================================================================

function uniqueItems(items) {
  return Array.from(new Set(items.filter(Boolean)));
}

function detectStepLabels() {
  const labels = Array.from(document.querySelectorAll(".step-item .step-label"))
    .map((el) => el.textContent.trim())
    .filter(Boolean);
  return uniqueItems(labels);
}

function buildPageGuide() {
  const steps = [];
  const tips = [];

  const stepLabels = detectStepLabels();
  if (stepLabels.length > 1) {
    steps.push(...stepLabels);
  } else if (document.querySelector("form")) {
    steps.push(
      appText(
        "guide.steps.fill_required",
        "املأ الحقول المطلوبة بعناية",
        "Fill in the required fields carefully",
      ),
    );
    if (document.querySelector('input[type="file"]')) {
      steps.push(
        appText(
          "guide.steps.attach_files",
          "أرفق الملفات المطلوبة إن وجدت",
          "Attach required files if available",
        ),
      );
    }
    steps.push(
      appText(
        "guide.steps.review",
        "راجع البيانات قبل الإرسال",
        "Review the data before submission",
      ),
    );
    steps.push(
      appText(
        "guide.steps.submit",
        "اضغط حفظ أو إرسال لإكمال العملية",
        "Click Save or Submit to complete the process",
      ),
    );
  }

  if (document.querySelector("table")) {
    steps.push(
      appText(
        "guide.steps.use_search",
        "استخدم البحث أو التصفية للوصول بسرعة إلى النتائج",
        "Use search or filters to quickly reach results",
      ),
    );
    steps.push(
      appText(
        "guide.steps.open_details",
        "انقر على الصف أو زر الإجراء لعرض التفاصيل",
        "Click a row or action button to view details",
      ),
    );
  }

  if (steps.length === 0) {
    steps.push(
      appText(
        "guide.steps.browse_info",
        "استعرض المعلومات المعحضانة في الصفحة",
        "Browse the information shown on this page",
      ),
    );
    if (document.querySelector("a.btn, button.btn")) {
      steps.push(
        appText(
          "guide.steps.use_buttons",
          "استخدم الأزرار للانتقال أو تنفيذ الإجراءات",
          "Use the buttons to navigate or perform actions",
        ),
      );
    }
  }

  tips.push(
    appText(
      "guide.tips.required",
      "الحقول التي تحمل علامة * إلزامية.",
      "Fields marked with * are required.",
    ),
  );
  if (
    document.querySelector('input[type="search"], .filter-row, .filter-bar')
  ) {
    tips.push(
      appText(
        "guide.tips.search_filter",
        "استخدم البحث والتصفية لتضييق النتائج.",
        "Use search and filters to narrow the results.",
      ),
    );
  }
  tips.push(
    appText(
      "guide.tips.hover_icons",
      "مرّر المؤشر فوق الأيقونات لعرض التلميحات.",
      "Hover over icons to view hints.",
    ),
  );

  return {
    title: appText(
      "guide.title",
      "كيف تستخدم هذه الصفحة",
      "How to use this page",
    ),
    steps: uniqueItems(steps).slice(0, 6),
    tips: uniqueItems(tips),
  };
}

function renderPageGuide(guide) {
  const panel = document.getElementById("pageGuidePanel");
  const body = document.getElementById("pageGuideBody");
  const titleEl = document.getElementById("pageGuideTitle");
  if (!panel || !body || !guide) return;

  if (titleEl) titleEl.textContent = guide.title;

  const stepsHtml = renderGuideSteps(guide.steps, escapeHtml);
  const tipsHtml = renderGuideTips(guide.tips, escapeHtml, "small text-muted");

  body.innerHTML = `
        ${stepsHtml}
        ${tipsHtml}
    `;

  panel.classList.remove("d-none");
}

function syncHelpModalContent(guide) {
  if (!guide) return;
  let helpContent = document.getElementById("pageHelpContent");
  if (!helpContent) {
    helpContent = document.createElement("div");
    helpContent.id = "pageHelpContent";
    helpContent.className = "d-none";
    document.body.appendChild(helpContent);
  }

  helpContent.setAttribute("data-help-title", guide.title);
  const stepsHtml = renderGuideSteps(guide.steps, escapeHtml);
  const tipsHtml = renderGuideTips(
    guide.tips,
    escapeHtml,
    "alert alert-light border mt-3 mb-0",
  );

  helpContent.innerHTML = `
        ${stepsHtml}
        ${tipsHtml}
    `;
}

function guideStepNumber(index) {
  const arabicIndic = ["١", "٢", "٣", "٤", "٥", "٦", "٧", "٨", "٩"];
  return appCurrentLang() === "ar"
    ? arabicIndic[index] || String(index + 1)
    : String(index + 1);
}

function renderGuideSteps(steps, escapeFn) {
  const dir = appCurrentLang() === "ar" ? "rtl" : "ltr";
  const items = steps
    .map(
      (step, index) => `
        <li class="guide-step d-flex align-items-start gap-2 mb-1">
          <span class="guide-step-number flex-shrink-0">${guideStepNumber(index)}.</span>
          <span>${escapeFn(step)}</span>
        </li>`,
    )
    .join("");
  return `<ol class="guide-steps list-unstyled mb-2" dir="${dir}">${items}</ol>`;
}

function renderGuideTips(tips, escapeFn, className) {
  if (!tips.length) return "";
  const dir = appCurrentLang() === "ar" ? "rtl" : "ltr";
  const items = tips
    .map(
      (tip) => `
        <li class="d-flex align-items-start gap-2 mb-1">
          <span aria-hidden="true" class="flex-shrink-0">•</span>
          <span>${escapeFn(tip)}</span>
        </li>`,
    )
    .join("");
  return `<ul class="guide-tips list-unstyled ${className}" dir="${dir}">${items}</ul>`;
}

function injectRequiredFieldHints() {
  const requiredFields = document.querySelectorAll(
    "form input[required], form select[required], form textarea[required]",
  );
  requiredFields.forEach((field) => {
    if (field.type === "hidden") return;
    // Skip fields inside custom auth input wrappers (they have their own validation UI)
    if (field.closest(".auth-input-wrap")) return;
    const wrapper =
      field.closest(".mb-3, .form-group, .col-12, .col-md-6") ||
      field.parentElement;
    if (!wrapper || wrapper.querySelector(".field-hint")) return;
    if (wrapper.querySelector(".form-text")) return;

    const hint = document.createElement("div");
    hint.className = "form-text text-muted field-hint";
    hint.textContent = appText(
      "forms.required_hint",
      "هذا الحقل مطلوب لإكمال النموذج.",
      "This field is required to complete the form.",
    );
    field.insertAdjacentElement("afterend", hint);

    if (!field.getAttribute("title")) {
      field.setAttribute(
        "title",
        appText(
          "forms.required_title",
          "هذا الحقل مطلوب",
          "This field is required",
        ),
      );
    }
    field.setAttribute("data-bs-toggle", "tooltip");
  });
}

function initTooltips() {
  const elements = Array.from(document.querySelectorAll("[title]"));
  elements.forEach((el) => {
    if (!el.getAttribute("data-bs-toggle")) {
      el.setAttribute("data-bs-toggle", "tooltip");
    }
  });
  const triggers = [].slice.call(
    document.querySelectorAll('[data-bs-toggle="tooltip"]'),
  );
  triggers.forEach((el) => new bootstrap.Tooltip(el));
}

function initSidebarInteractions() {
  const sidebar = document.getElementById("sidebarMenu");
  if (!sidebar || typeof bootstrap === "undefined") {
    return;
  }

  const backdrop = document.getElementById("sidebarBackdrop");
  const toggleButtons = document.querySelectorAll("[data-sidebar-toggle]");
  const sidebarCollapse = bootstrap.Collapse.getOrCreateInstance(sidebar, {
    toggle: false,
  });

  const syncState = () => {
    const isMobile = window.innerWidth < 768;
    const isOpen = isMobile && sidebar.classList.contains("show");
    document.body.classList.toggle("sidebar-open", isOpen);
    toggleButtons.forEach((button) =>
      button.setAttribute("aria-expanded", isOpen ? "true" : "false"),
    );
    if (backdrop) {
      backdrop.classList.toggle("show", isOpen);
    }
  };

  const closeSidebar = () => {
    if (window.innerWidth < 768 && sidebar.classList.contains("show")) {
      sidebarCollapse.hide();
    }
  };

  toggleButtons.forEach((toggleButton) => {
    toggleButton.addEventListener("click", (event) => {
      if (window.innerWidth >= 768) {
        return;
      }
      event.preventDefault();
      sidebarCollapse.toggle();
    });
  });

  sidebar.querySelectorAll("a.nav-link").forEach((link) => {
    link.addEventListener("click", closeSidebar);
  });

  if (backdrop) {
    backdrop.addEventListener("click", closeSidebar);
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeSidebar();
    }
  });

  sidebar.addEventListener("shown.bs.collapse", syncState);
  sidebar.addEventListener("hidden.bs.collapse", syncState);
  window.addEventListener("resize", syncState);
  syncState();
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
      false,
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
function initDataTable(tableId, _options = {}) {
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
          label: appText(
            "charts.attendance_rate",
            "نسبة الحضور %",
            "Attendance rate %",
          ),
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
      // Dashboard loading is handled by the HTML template.
    } else {
      await loadParentDashboard();
    }

    hideLoading();
  } catch (error) {
    hideLoading();
    showToast(
      appText(
        "dashboard.error_load",
        "حدث خطأ في تحميل لوحة التحكم",
        "An error occurred while loading the dashboard",
      ),
      "error",
    );
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
                        <h6 class="mb-1">${escapeHtml(child.first_name)} ${escapeHtml(child.last_name)}</h6>
                        <small class="text-muted">${appText("reports.requires_report", "يتطلب تقرير", "Report required")}</small>
                    </div>
                </a>
            `,
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
    "motherNationalIdGroup",
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

    showToast(
      appText(
        "enrollment.submit_success",
        "تم تقديم طلب التسجيل بنجاح",
        "Enrollment request submitted successfully",
      ),
      "success",
    );

    setTimeout(() => {
      window.location.href = "/enrollments";
    }, 1500);
  } catch (error) {
    hideLoading();
    showToast(
      error.message ||
        appText(
          "enrollment.submit_error",
          "حدث خطأ في تقديم الطلب",
          "An error occurred while submitting the request",
        ),
      "error",
    );
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
    showToast(
      appText(
        "attendance.load_error",
        "حدث خطأ في تحميل بيانات الحضور",
        "An error occurred while loading attendance data",
      ),
      "error",
    );
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
            <div class="mt-2 small">${escapeHtml(child.first_name)}</div>
        </div>
    `,
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

    showToast(
      isPresent
        ? appText(
            "attendance.checkout_success",
            "تم تسجيل الخروج",
            "Check-out recorded",
          )
        : appText(
            "attendance.checkin_success",
            "تم تسجيل الحضور",
            "Check-in recorded",
          ),
      "success",
    );
  } catch (error) {
    showToast(
      error.message ||
        appText(
          "common.unexpected_error",
          "حدث خطأ",
          "An unexpected error occurred",
        ),
      "error",
    );
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

    showToast(
      appText(
        "reports.daily_save_success",
        "تم حفظ التقرير اليومي بنجاح",
        "Daily report saved successfully",
      ),
      "success",
    );

    setTimeout(() => {
      window.location.href = "/daily-reports";
    }, 1500);
  } catch (error) {
    hideLoading();
    showToast(
      error.message ||
        appText(
          "reports.daily_save_error",
          "حدث خطأ في حفظ التقرير",
          "An error occurred while saving the daily report",
        ),
      "error",
    );
  }
}

Object.assign(window, {
  showError,
  formatDate,
  formatDateISO,
  getStatusBadge,
  toggleLanguage,
  logout,
  confirmAction,
  validateJordanPhone,
  validateNationalId,
  createAttendanceChart,
  createEnrollmentPieChart,
  createGaugeChart,
  initDashboard,
  submitEnrollmentForm,
  initAttendancePage,
  toggleAttendance,
  submitDailyReport,
});

// ============================================================================
// Global Event Listeners
// ============================================================================

document.addEventListener("DOMContentLoaded", () => {
  initSidebarInteractions();

  // Initialize form validation
  initFormValidation();

  // Page guide + inline help
  const guide = buildPageGuide();
  renderPageGuide(guide);
  syncHelpModalContent(guide);
  injectRequiredFieldHints();
  initTooltips();

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

  // Load stored language preference — cookie takes priority over localStorage
  const _kjLangCookieMatch = document.cookie.match(
    /(?:^|;\s*)kinjo_lang=(ar|en)(?:;|$)/i,
  );
  const _kjCookieLang = _kjLangCookieMatch
    ? _kjLangCookieMatch[1].toLowerCase()
    : null;
  const storedLang = _kjCookieLang || localStorage.getItem("kinjo_lang");
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
      showToast(
        appText(
          "auth.login.session_expired",
          "انتهت الجلسة، يرجى تسجيل الدخول مرة أخرى",
          "Your session has expired. Please sign in again.",
        ),
        "warning",
      );
      setTimeout(() => api.logout(), 2000);
    });
  }
});
