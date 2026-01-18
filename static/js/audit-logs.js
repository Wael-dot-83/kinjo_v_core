/**
 * Audit Logs Management
 * Handles loading, filtering, and displaying audit logs
 */

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
    document
      .getElementById("actionFilter")
      .addEventListener("change", () => this.onFilterChange());
    document
      .getElementById("entityFilter")
      .addEventListener("change", () => this.onFilterChange());
    document
      .getElementById("userFilter")
      .addEventListener("input", () => this.onFilterChange());
    document
      .getElementById("dateFilter")
      .addEventListener("change", () => this.onFilterChange());
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
        ...this.filters,
      });

      const response = await api.get(`/api/audit-logs?${params}`);

      this.totalRecords = response.total || 0;
      this.renderAuditLogs(response.logs || []);
      this.renderPagination(response.total_pages || 1);
      this.updateResultsCount();
    } catch (error) {
      console.error("Error loading audit logs:", error);
      this.showError("حدث خطأ في تحميل سجلات التدقيق");
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
                        لا توجد سجلات تدقيق
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
                <td>${this.escapeHtml(log.user_name || "غير محدد")}</td>
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
        `,
      )
      .join("");
  }

  renderPagination(totalPages) {
    const pagination = document.getElementById("pagination");
    const maxVisiblePages = 5;

    if (totalPages <= 1) {
      pagination.innerHTML = "";
      return;
    }

    let startPage = Math.max(
      1,
      this.currentPage - Math.floor(maxVisiblePages / 2),
    );
    let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);

    if (endPage - startPage + 1 < maxVisiblePages) {
      startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }

    let html = "";

    // Previous button
    if (this.currentPage > 1) {
      html += `<li class="page-item"><a class="page-link" href="#" onclick="auditLogs.changePage(${this.currentPage - 1})">السابق</a></li>`;
    } else {
      html += `<li class="page-item disabled"><span class="page-link">السابق</span></li>`;
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
      html += `<li class="page-item"><a class="page-link" href="#" onclick="auditLogs.changePage(${this.currentPage + 1})">التالي</a></li>`;
    } else {
      html += `<li class="page-item disabled"><span class="page-link">التالي</span></li>`;
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
      countElement.textContent = "لا توجد نتائج";
    } else {
      countElement.textContent = `عرض ${start} - ${end} من ${this.totalRecords} سجل`;
    }
  }

  showLoading() {
    const tbody = document.getElementById("auditLogsBody");
    tbody.innerHTML = `
            <tr>
                <td colspan="7" class="text-center py-4">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">جاري التحميل...</span>
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
    return date.toLocaleString("ar-JO", {
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
      CREATE: "إنشاء",
      UPDATE: "تحديث",
      DELETE: "حذف",
      LOGIN: "تسجيل دخول",
      LOGOUT: "تسجيل خروج",
      VIEW: "عرض",
    };
    return labels[action] || action;
  }

  getEntityTypeLabel(entityType) {
    const labels = {
      USER: "مستخدم",
      CHILD: "طفل",
      KINDERGARTEN: "روضة",
      ENROLLMENT: "تسجيل",
      ATTENDANCE: "حضور",
      REPORT: "تقرير",
      INCIDENT: "حادثة",
      TASK: "مهمة",
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
  exportBtn.innerHTML =
    '<span class="spinner-border spinner-border-sm me-2"></span>جاري التصدير...';
  exportBtn.disabled = true;

  // Build export URL
  const params = new URLSearchParams({
    format: format,
    period: period,
    ...auditLogs.filters,
  });

  // Create download link
  const link = document.createElement("a");
  link.href = `/api/audit-logs/export?${params}`;
  link.download = `audit-logs.${format}`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  // Reset button
  exportBtn.textContent = originalText;
  exportBtn.disabled = false;

  // Close modal
  const modal = bootstrap.Modal.getInstance(
    document.getElementById("exportModal"),
  );
  modal.hide();

  showToast("تم بدء عملية التصدير", "success");
}

// Initialize when DOM is loaded
let auditLogs;
document.addEventListener("DOMContentLoaded", function () {
  auditLogs = new AuditLogsManager();
});
