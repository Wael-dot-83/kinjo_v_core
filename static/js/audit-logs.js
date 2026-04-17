/**
 * Audit Logs Management
 * Handles loading, filtering, and displaying audit logs
 */

function auditLangCode() {
  return (
    window.AppI18n?.currentLang ||
    window.AdminI18n?.getCurrentLanguage?.().code ||
    localStorage.getItem("kinjo_lang") ||
    localStorage.getItem("admin_language") ||
    document.documentElement.lang ||
    "ar"
  );
}

function auditText(arText, enText) {
  return String(auditLangCode()).toLowerCase().startsWith("en") ? enText : arText;
}

function auditLocale() {
  return auditText("ar-JO", "en-US");
}

function auditLiteral(value) {
  const raw = String(value ?? "");
  if (!raw) return "";
  if (typeof window.AppI18n?.replaceLiteralSegments === "function") {
    return window.AppI18n.replaceLiteralSegments(raw);
  }
  if (typeof window.AdminI18n?.replaceLiteralSegments === "function") {
    return window.AdminI18n.replaceLiteralSegments(raw);
  }
  return raw;
}

class AuditLogsManager {
  constructor() {
    this.currentPage = 1;
    this.pageSize = 25;
    this.filters = {
      action: "",
      entity_type: "",
      user: "",
      date: "",
    };
    this.totalRecords = 0;
    this.isLoading = false;

    this.init();
  }

  init() {
    // Load initial data
    this.loadAuditLogs();

    // Setup filter listeners
    document.getElementById("actionFilter").addEventListener("change", () => this.onFilterChange());
    document.getElementById("entityFilter").addEventListener("change", () => this.onFilterChange());
    document.getElementById("userFilter").addEventListener("input", () => this.onFilterChange());
    document.getElementById("dateFilter").addEventListener("change", () => this.onFilterChange());
  }

  onFilterChange() {
    // Debounce filter changes
    clearTimeout(this.filterTimeout);
    this.filterTimeout = setTimeout(() => {
      this.updateFilters();
      this.currentPage = 1;
      this.loadAuditLogs();
    }, 500);
  }

  updateFilters() {
    this.filters = {
      action: document.getElementById("actionFilter").value,
      entity_type: document.getElementById("entityFilter").value,
      user: document.getElementById("userFilter").value.trim(),
      date: document.getElementById("dateFilter").value,
    };
  }

  applyFilters() {
    this.updateFilters();
    this.currentPage = 1;
    this.loadAuditLogs();
  }

  async loadAuditLogs() {
    if (this.isLoading) return;

    this.isLoading = true;
    this.showLoading();

    try {
      const params = new URLSearchParams({
        page: this.currentPage,
        limit: this.pageSize,
      });
      // Only include non-empty filter values to avoid 422 from FastAPI
      Object.entries(this.filters).forEach(([key, value]) => {
        if (value) params.set(key, value);
      });

      const response = await api.get(`/api/audit-logs?${params}`);

      this.totalRecords = response.total || 0;
      this.renderAuditLogs(response.logs || []);
      this.renderPagination(response.total_pages || 1);
      this.updateResultsCount();
    } catch (error) {
      console.error("Error loading audit logs:", error);
      this.showError(auditText("حدث خطأ في تحميل سجلات التدقيق", "Failed to load audit logs"));
    } finally {
      this.isLoading = false;
    }
  }

  renderAuditLogs(logs) {
    const tbody = document.getElementById("auditLogsBody");

    if (!logs || logs.length === 0) {
      tbody.innerHTML = `
                <tr>
                    <td colspan="7" class="text-center py-4 text-muted">
                        <i class="bi bi-info-circle me-2"></i>
                        ${auditText("لا توجد سجلات تدقيق", "No audit logs found")}
                    </td>
                </tr>
            `;
      return;
    }

    tbody.innerHTML = logs
      .map(
        (log) => `
            <tr>
                <td>${this.formatDateTime(log.created_at)}</td>
                <td>${this.escapeHtml(auditLiteral(log.user_name || auditText("غير محدد", "Not specified")))}</td>
                <td>
                    <span class="badge ${this.getActionBadgeClass(log.action)}">
                        ${this.getActionLabel(log.action)}
                    </span>
                </td>
                <td>${this.getEntityTypeLabel(log.entity_type)}</td>
                <td>${log.entity_id || "-"}</td>
                <td>
                    <div class="text-truncate" style="max-width: 200px;" title="${this.escapeHtml(log.details || "")}">
                        ${this.escapeHtml(log.details || "-")}
                    </div>
                </td>
                <td>${log.ip_address || "-"}</td>
            </tr>
        `
      )
      .join("");
  }

  renderPagination(totalPages) {
    const pagination = document.getElementById("pagination");
    if (!pagination) return;
    const maxVisiblePages = 5;

    if (totalPages <= 1) {
      pagination.innerHTML = "";
      return;
    }

    let startPage = Math.max(1, this.currentPage - Math.floor(maxVisiblePages / 2));
    let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);

    if (endPage - startPage + 1 < maxVisiblePages) {
      startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }

    let html = "";

    // Previous button
    if (this.currentPage > 1) {
      html += `<li class="page-item"><a class="page-link" href="#" onclick="auditLogs.changePage(${this.currentPage - 1})">${auditText("السابق", "Previous")}</a></li>`;
    } else {
      html += `<li class="page-item disabled"><span class="page-link">${auditText("السابق", "Previous")}</span></li>`;
    }

    // Page numbers
    for (let i = startPage; i <= endPage; i++) {
      if (i === this.currentPage) {
        html += `<li class="page-item active"><span class="page-link">${i}</span></li>`;
      } else {
        html += `<li class="page-item"><a class="page-link" href="#" onclick="auditLogs.changePage(${i})">${i}</a></li>`;
      }
    }

    // Next button
    if (this.currentPage < totalPages) {
      html += `<li class="page-item"><a class="page-link" href="#" onclick="auditLogs.changePage(${this.currentPage + 1})">${auditText("التالي", "Next")}</a></li>`;
    } else {
      html += `<li class="page-item disabled"><span class="page-link">${auditText("التالي", "Next")}</span></li>`;
    }

    pagination.innerHTML = html;
  }

  changePage(page) {
    this.currentPage = page;
    this.loadAuditLogs();
  }

  updateResultsCount() {
    const countElement = document.getElementById("resultsCount");
    const start = (this.currentPage - 1) * this.pageSize + 1;
    const end = Math.min(this.currentPage * this.pageSize, this.totalRecords);

    if (this.totalRecords === 0) {
      countElement.textContent = auditText("لا توجد نتائج", "No results");
    } else {
      countElement.textContent = auditText(
        `عرض ${start} - ${end} من ${this.totalRecords} سجل`,
        `Showing ${start} - ${end} of ${this.totalRecords} records`
      );
    }
  }

  showLoading() {
    const tbody = document.getElementById("auditLogsBody");
    tbody.innerHTML = `
            <tr>
                <td colspan="7" class="text-center py-4">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">${auditText("جاري التحميل...", "Loading...")}</span>
                    </div>
                </td>
            </tr>
        `;
  }

  showError(message) {
    const tbody = document.getElementById("auditLogsBody");
    tbody.innerHTML = `
            <tr>
                <td colspan="7" class="text-center py-4 text-danger">
                    <i class="bi bi-exclamation-triangle me-2"></i>
                    ${message}
                </td>
            </tr>
        `;
  }

  formatDateTime(dateString) {
    if (!dateString) return "-";
    const date = new Date(dateString);
    return date.toLocaleString(auditLocale(), {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  getActionBadgeClass(action) {
    const classes = {
      CREATE: "bg-success",
      UPDATE: "bg-warning",
      DELETE: "bg-danger",
      LOGIN: "bg-info",
      LOGOUT: "bg-secondary",
      VIEW: "bg-light text-dark",
    };
    return classes[action] || "bg-secondary";
  }

  getActionLabel(action) {
    const labels = {
      CREATE: auditText("إنشاء", "Create"),
      UPDATE: auditText("تحديث", "Update"),
      DELETE: auditText("حذف", "Delete"),
      LOGIN: auditText("تسجيل دخول", "Sign in"),
      LOGOUT: auditText("تسجيل خروج", "Sign out"),
      VIEW: auditText("عرض", "View"),
    };
    return labels[action] || action;
  }

  getEntityTypeLabel(entityType) {
    const labels = {
      USER: auditText("مستخدم", "User"),
      CHILD: auditText("طفل", "Child"),
      KINDERGARTEN: auditText("روضة", "Kindergarten"),
      ENROLLMENT: auditText("تسجيل", "Enrollment"),
      ATTENDANCE: auditText("حضور", "Attendance"),
      REPORT: auditText("تقرير", "Report"),
      INCIDENT: auditText("حادثة", "Incident"),
      TASK: auditText("مهمة", "Task"),
    };
    return labels[entityType] || entityType;
  }

  escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }
}

// Global functions for HTML onclick handlers
function applyFilters() {
  auditLogs.applyFilters();
}

function refreshAuditLogs() {
  auditLogs.currentPage = 1;
  auditLogs.loadAuditLogs();
}

function exportAuditLogs() {
  const modal = new bootstrap.Modal(document.getElementById("exportModal"));
  modal.show();
}

function doExport() {
  const format = document.getElementById("exportFormat").value;
  const period = document.getElementById("exportPeriod").value;

  // Show loading
  const exportBtn = document.querySelector("#exportModal .btn-primary");
  const originalText = exportBtn.textContent;
  exportBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>${auditText("جاري التصدير...", "Exporting...")}`;
  exportBtn.disabled = true;

  // Build export URL
  const params = new URLSearchParams({
    format: format,
    period: period,
    ...auditLogs.filters,
  });

  // Download with auth header
  const token = AuthStorage.getToken();
  if (!token) {
    window.location.href = "/login";
    return;
  }

  fetch(`/api/audit-logs/export?${params}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
    .then((res) => {
      if (!res.ok) throw new Error(auditText("فشل التصدير", "Export failed"));
      return res.blob();
    })
    .then((blob) => {
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `audit-logs.${format}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      showToast(auditText("تم تصدير السجلات بنجاح", "Audit logs exported successfully"), "success");
    })
    .catch((err) => {
      console.error("Export error:", err);
      showToast(auditText("فشل تصدير السجلات", "Failed to export audit logs"), "error");
    })
    .finally(() => {
      // Reset button
      exportBtn.textContent = originalText;
      exportBtn.disabled = false;

      // Close modal
      const modal = bootstrap.Modal.getInstance(document.getElementById("exportModal"));
      if (modal) modal.hide();
    });
}

window.applyFilters = applyFilters;
window.refreshAuditLogs = refreshAuditLogs;
window.exportAuditLogs = exportAuditLogs;
window.doExport = doExport;

// Initialize when DOM is loaded
let auditLogs;
document.addEventListener("DOMContentLoaded", function () {
  auditLogs = new AuditLogsManager();
});

window.addEventListener("languageChanged", () => {
  if (auditLogs) {
    auditLogs.loadAuditLogs();
  }
});
