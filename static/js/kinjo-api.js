/**
 * KinJo API Client
 * Handles all communication with the backend API
 * Uses centralized AuthService for authentication
 */

function kinjoApiCurrentLang() {
  if (window.AppI18n?.currentLang) {
    return window.AppI18n.currentLang;
  }
  const stored = localStorage.getItem("kinjo_lang");
  if (stored === "en" || stored === "ar") {
    return stored;
  }
  return document.documentElement.lang === "en" ? "en" : "ar";
}

function kinjoApiText(key, arText, enText) {
  if (window.AppI18n && typeof window.AppI18n.t === "function") {
    const resolved = window.AppI18n.t(key);
    if (resolved && resolved !== key) {
      return resolved;
    }
  }
  return kinjoApiCurrentLang() === "en" ? enText : arText;
}

class KinJoAPI {
  constructor() {
    this.baseURL = "";
    this.token = null;
  }

  /**
   * Manually set token (kept for backwards compatibility)
   */
  setToken(token) {
    this.token = token;
  }

  /**
   * Check if user is authenticated
   */
  isAuthenticated() {
    if (window.AuthService && typeof AuthService.isAuthenticated === "function") {
      return AuthService.isAuthenticated();
    }
    if (window.AuthStorage && typeof AuthStorage.isAuthenticated === "function") {
      return AuthStorage.isAuthenticated();
    }
    return false;
  }

  /**
   * Get current user's kindergarten ID (for manager role enforcement)
   */
  getCurrentUserKindergartenId() {
    if (window.AuthService && typeof AuthService.getCurrentUser === "function") {
      const user = AuthService.getCurrentUser();
      return user && user.role === "MANAGER" ? user.kindergarten_id : null;
    }
    if (window.AuthStorage && typeof AuthStorage.getCurrentUser === "function") {
      const user = AuthStorage.getCurrentUser();
      return user && user.role === "MANAGER" ? user.kindergarten_id : null;
    }
    return null;
  }

  /**
   * Force kindergarten ID for manager role (single-kindergarten isolation)
   */
  forceManagerKindergartenId(providedKindergartenId) {
    const userKgId = this.getCurrentUserKindergartenId();
    // If user is a manager, always use their assigned kindergarten ID
    return userKgId || providedKindergartenId;
  }

  /**
   * Generic request method using centralized auth
   */
  async request(endpoint, options = {}) {
    options.headers = { ...(options.headers || {}) };
    const hasContentType = Object.keys(options.headers).some(
      (key) => key.toLowerCase() === "content-type"
    );
    if (typeof options.body === "string" && !hasContentType) {
      options.headers["Content-Type"] = "application/json";
    }

    const response = await fetchWithAuth(`${this.baseURL}${endpoint}`, options);

    // fetchWithAuth already throws on non-OK responses and redirects on 401,
    // so at this point we should have a valid response object (or null when redirected).
    if (!response) {
      throw new Error(
        kinjoApiText("auth.login.required", "يتطلب تسجيل الدخول", "Sign-in is required")
      );
    }

    const text = await response.text();
    const contentType = response.headers.get("content-type") || "";

    // Some endpoints may return no content
    if (response.status === 204) {
      return null;
    }

    if (contentType.includes("application/json")) {
      try {
        return JSON.parse(text);
      } catch (e) {
        console.warn("Failed to parse JSON response:", text.substring(0, 100));
        // If it looks like an error response, throw it with the text
        if (response.status >= 400) {
          const messagePrefix = kinjoApiText(
            "common.server_error",
            "خطأ في الخادم",
            "Server error"
          );
          throw new Error(`${messagePrefix} (${response.status}): ${text.substring(0, 200)}...`);
        }
        // Otherwise rethrow syntax error
        throw e;
      }
    }

    // For non-JSON responses
    return text;
  }

  /**
   * GET request
   */
  async get(endpoint, params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const url = queryString ? `${endpoint}?${queryString}` : endpoint;
    return this.request(url, { method: "GET" });
  }

  /**
   * POST request
   */
  async post(endpoint, data = {}) {
    return this.request(endpoint, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  /**
   * PUT request
   */
  async put(endpoint, data = {}) {
    return this.request(endpoint, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  /**
   * PATCH request
   */
  async patch(endpoint, data = {}) {
    return this.request(endpoint, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  }

  /**
   * DELETE request
   */
  async delete(endpoint) {
    return this.request(endpoint, { method: "DELETE" });
  }

  // =========================================================================
  // Authentication Endpoints
  // =========================================================================

  /**
   * Login user
   */
  async login(username, password) {
    const formData = new URLSearchParams();
    formData.append("username", username);
    formData.append("password", password);

    const response = await fetch(`${this.baseURL}/token`, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(
        error.detail || kinjoApiText("auth.login.failed", "فشل تسجيل الدخول", "Sign-in failed")
      );
    }

    const data = await response.json();
    this.setToken(data.access_token);
    if (window.AuthService && typeof AuthService.setToken === "function") {
      AuthService.setToken(data.access_token);
    }
    return data;
  }

  /**
   * Register parent
   */
  async registerParent(data) {
    return this.post("/api/register/parent", data);
  }

  /**
   * Get current user
   */
  async getCurrentUser() {
    return this.get("/api/users/me");
  }

  /**
   * Logout
   */
  logout() {
    this.setToken(null);
    window.location.href = "/login";
  }

  // =========================================================================
  // Kindergarten Endpoints
  // =========================================================================

  async getKindergartens(params = {}) {
    return this.get("/api/kindergartens", params);
  }

  async getKindergarten(id) {
    return this.get(`/api/kindergartens/${id}`);
  }

  async createKindergarten(data) {
    return this.post("/api/admin/kindergartens", data);
  }

  // Atomic kindergarten + primary manager creation (FRD §2.4).
  async createKindergartenWithManager(data) {
    return this.post("/api/admin/kindergartens/with-manager", data);
  }

  // Freeze / Unfreeze (FRD §1.4).
  async freezeKindergarten(id, reason) {
    return this.patch(`/api/admin/kindergartens/${id}/freeze`, reason ? { reason } : {});
  }

  async unfreezeKindergarten(id) {
    return this.patch(`/api/admin/kindergartens/${id}/activate`, {});
  }

  // Assign / replace a kindergarten's manager (FRD §3.3).
  async assignKindergartenManager(id, userId, replace = false) {
    return this.post(`/api/admin/kindergartens/${id}/assign-manager`, { user_id: userId, replace });
  }

  async updateKindergarten(id, data) {
    return this.put(`/api/admin/kindergartens/${id}`, data);
  }

  async deleteKindergarten(id) {
    return this.delete(`/api/admin/kindergartens/${id}`);
  }

  // =========================================================================
  // Class Endpoints
  // =========================================================================

  async getClasses(params = {}) {
    return this.get("/api/classes", params);
  }

  async getClass(id) {
    return this.get(`/api/classes/${id}`);
  }

  async createClass(data) {
    return this.post("/api/classes", data);
  }

  async updateClass(id, data) {
    return this.put(`/api/classes/${id}`, data);
  }

  async getClassRequiredSupervisors(ageGroup, childrenCount) {
    return this.get("/api/classes/required-supervisors", {
      age_group: ageGroup,
      children_count: childrenCount,
    });
  }

  async getEligibleSupervisors(kindergartenId, classId = null) {
    const params = { kindergarten_id: kindergartenId };
    if (classId !== null && classId !== undefined) {
      params.class_id = classId;
    }
    return this.get("/api/classes/eligible-supervisors", params);
  }

  async deleteClass(id) {
    return this.delete(`/api/classes/${id}`);
  }

  async deactivateClass(id) {
    return this.put(`/api/classes/${id}/deactivate`);
  }

  // =========================================================================
  // Child Endpoints
  // =========================================================================

  async getChildren(params = {}) {
    return this.get("/api/children", params);
  }

  async getChild(id) {
    return this.get(`/api/children/${id}`);
  }

  // =========================================================================
  // Enrollment Endpoints
  // =========================================================================

  async getEnrollments(params = {}) {
    return this.get("/api/enrollments", params);
  }

  async createEnrollment(data) {
    return this.post("/api/enrollment/apply", data);
  }

  async submitEnrollment(id) {
    return this.post(`/api/enrollment/${id}/submit`);
  }

  async reviewEnrollment(id, decision, reason = null) {
    const params = { decision };
    if (reason) params.reason = reason;
    return this.post(`/api/enrollment/${id}/review`, params);
  }

  // =========================================================================
  // Attendance Endpoints
  // =========================================================================

  async checkIn(childId, method, droppedByName = null) {
    const params = { child_id: childId, method };
    if (droppedByName) params.dropped_by_name = droppedByName;
    return this.post("/api/attendance/check-in", params);
  }

  async checkOut(childId, pickedByName = null) {
    const params = { child_id: childId };
    if (pickedByName) params.picked_by_name = pickedByName;
    return this.post("/api/attendance/check-out", params);
  }

  async getTodayAttendance(kindergartenId) {
    const enforcedKgId = this.forceManagerKindergartenId(kindergartenId);
    return this.get("/api/attendance/today", {
      kindergarten_id: enforcedKgId,
    });
  }

  async searchKindergartens(params = {}) {
    const queryParams = {};
    if (params.search) queryParams.name = params.search;
    if (params.governorate) queryParams.governorate = params.governorate;
    if (params.city) queryParams.city = params.city;
    if (params.phone) queryParams.phone = params.phone;
    if (params.status) queryParams.status = params.status;
    return this.get("/api/kindergartens", queryParams);
  }

  // The backend exposes districts, not cities — `/cities` was never registered and
  // returned 404 (a leftover of the city→district migration).
  async getDistrictsByGovernorate(governorate) {
    return this.get(`/api/governorates/${encodeURIComponent(governorate)}/districts`);
  }

  async getKindergartenClasses(kindergartenId) {
    const enforcedKgId = this.forceManagerKindergartenId(kindergartenId);
    return this.get("/api/classes", { kindergarten_id: enforcedKgId });
  }

  async getKindergartenChildren(kindergartenId, classIds = null) {
    const enforcedKgId = this.forceManagerKindergartenId(kindergartenId);
    const params = { kindergarten_id: enforcedKgId };
    if (classIds && classIds.length > 0) {
      params.class_id = classIds.join(",");
    }
    return this.get("/api/children", params);
  }

  async getAttendanceReport(params) {
    return this.get("/api/attendance/report", params);
  }

  // =========================================================================
  // Daily Report Endpoints
  // =========================================================================

  async createDailyReport(data) {
    return this.post("/api/daily-reports/create", data);
  }

  async submitDailyReport(id) {
    return this.post(`/api/daily-reports/${id}/submit`);
  }

  async approveDailyReport(id) {
    return this.post(`/api/daily-reports/${id}/approve`);
  }

  async getChildDailyReports(childId) {
    return this.get(`/api/daily-reports/child/${childId}`);
  }

  async getOrganizationDailyReports(params = {}) {
    return this.get("/api/daily-reports", params);
  }

  // =========================================================================
  // KPI Endpoints
  // =========================================================================

  async getAttendanceRate(kindergartenId, periodStart, periodEnd) {
    const enforcedKgId = this.forceManagerKindergartenId(kindergartenId);
    return this.get("/api/kpi/attendance-rate", {
      kindergarten_id: enforcedKgId,
      period_start: periodStart,
      period_end: periodEnd,
    });
  }

  async getIncidentRate(kindergartenId, periodStart, periodEnd) {
    const enforcedKgId = this.forceManagerKindergartenId(kindergartenId);
    // incident-rate is part of KPI summary; use summary endpoint
    const summary = await this.get("/api/kpi/summary", {
      kindergarten_id: enforcedKgId,
      period_start: periodStart,
      period_end: periodEnd,
    });
    return { incident_rate: summary?.incident_rate ?? 0, ...summary };
  }

  async getRatioCompliance(kindergartenId, periodStart, periodEnd) {
    const enforcedKgId = this.forceManagerKindergartenId(kindergartenId);
    // ratio-compliance data is part of KPI summary
    const summary = await this.get("/api/kpi/summary", {
      kindergarten_id: enforcedKgId,
      period_start: periodStart,
      period_end: periodEnd,
    });
    return { ratio_compliance: summary?.ratio_compliance ?? 0, ...summary };
  }

  async getGovernanceScore(kindergartenId, periodStart, periodEnd) {
    const enforcedKgId = this.forceManagerKindergartenId(kindergartenId);
    return this.get("/api/kpi/governance-score", {
      kindergarten_id: enforcedKgId,
      period_start: periodStart,
      period_end: periodEnd,
    });
  }

  // =========================================================================
  // Supervisor Endpoints
  // =========================================================================

  async getSupervisorDashboard(targetDate = null) {
    const params = {};
    if (targetDate) params.target_date = targetDate;
    return this.get("/api/supervisor/dashboard", params);
  }

  async getMyClasses() {
    return this.get("/api/supervisor/my-classes");
  }

  async getMyChildren() {
    return this.get("/api/supervisor/children");
  }

  async getAttendanceStatus(targetDate = null) {
    const params = {};
    if (targetDate) params.target_date = targetDate;
    return this.get("/api/supervisor/present-children", params);
  }

  async getPendingReports(reportDate = null) {
    const params = {};
    if (reportDate) params.report_date = reportDate;
    return this.get("/api/supervisor/daily-reports", params);
  }

  // =========================================================================
  // Manager Endpoints
  // =========================================================================

  async getManagerDashboard() {
    return this.get("/api/manager/dashboard");
  }

  // Manager Dashboard Sections
  async getSubmittedReports() {
    return this.get("/api/manager/reports/submitted");
  }

  async getSupervisorStats() {
    return this.get("/api/manager/supervisors/stats");
  }

  async getManagerClasses() {
    return this.get("/api/manager/classes");
  }

  async getAccounts() {
    return this.get("/api/manager/accounts");
  }

  // Manager KPI and Analytics
  async getManagerKPIs() {
    return this.get("/api/kpi/manager/dashboard");
  }

  async getAlerts() {
    return this.get("/api/manager/alerts");
  }

  // Manager Actions
  async approveReport(reportId) {
    return this.post(`/api/manager/reports/${reportId}/approve`);
  }

  async rejectReport(reportId, reason) {
    return this.post(`/api/manager/reports/${reportId}/reject`, { reason });
  }

  // =========================================================================
  // Admin Endpoints
  // =========================================================================

  async getAdminDashboard() {
    return this.get("/api/admin/dashboard");
  }

  // User Management (Hardened Admin Endpoints)
  async getUsers(params = {}) {
    // Use new paginated admin endpoint
    return this.get("/api/admin/users", params);
  }

  async getUser(id) {
    return this.get(`/api/admin/users/${id}`);
  }

  async createUser(data) {
    return this.post("/api/admin/users", data);
  }

  async updateUser(id, data) {
    return this.put(`/api/admin/users/${id}`, data);
  }

  async deleteUser(id) {
    return this.delete(`/api/admin/users/${id}`);
  }

  /**
   * Bulk create users with optional dry-run
   * @param {Array} users - Array of user objects
   * @param {boolean} dryRun - If true, validate without creating
   */
  async bulkCreateUsers(users, dryRun = false) {
    return this.post("/api/admin/users/bulk-create", {
      users,
      dry_run: dryRun,
    });
  }

  /**
   * Bulk update user status with confirmation support
   * @param {Array} userIds - Array of user IDs
   * @param {string} newStatus - New status (ACTIVE, SUSPENDED, INACTIVE)
   * @param {string} confirmationToken - Token for confirming large operations
   * @param {boolean} dryRun - If true, preview without applying
   */
  async bulkUpdateUserStatus(userIds, newStatus, confirmationToken = null, dryRun = false) {
    const payload = {
      user_ids: userIds,
      new_status: newStatus,
      dry_run: dryRun,
    };
    if (confirmationToken) {
      payload.confirmation_token = confirmationToken;
    }
    return this.post("/api/admin/users/bulk-status-update", payload);
  }

  /**
   * Bulk delete users with confirmation support
   * @param {Array} userIds - Array of user IDs
   * @param {string} confirmationToken - Required confirmation token
   * @param {boolean} dryRun - If true, preview without applying
   */
  async bulkDeleteUsers(userIds, confirmationToken = null, dryRun = false) {
    const payload = {
      user_ids: userIds,
      dry_run: dryRun,
    };
    if (confirmationToken) {
      payload.confirmation_token = confirmationToken;
    }
    return this.post("/api/admin/users/bulk-delete", payload);
  }

  /**
   * Admin password reset with verification
   * @param {number} userId - Target user ID
   * @param {string} newPassword - New password for user
   * @param {string} adminPassword - Admin's own password for verification
   */
  async adminResetPassword(userId, newPassword, adminPassword) {
    return this.post(`/api/admin/users/${userId}/admin-reset-password`, {
      new_password: newPassword,
      admin_password: adminPassword,
    });
  }

  /**
   * Import users from CSV
   * @param {File} file - CSV file
   * @param {boolean} dryRun - If true, validate without importing
   */
async importUsersCSV(file, dryRun = false) {
     const formData = new FormData();
     formData.append("file", file);

     const url = `/api/admin/users/import-csv?dry_run=${dryRun}`;
     if (!this.isAuthenticated()) {
       window.location.href = "/login";
       throw new Error(
         kinjoApiText("auth.login.required", "يتطلب تسجيل الدخول", "Sign-in is required")
       );
     }

     const response = await fetchWithAuth(url, {
       method: "POST",
       body: formData,
     });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const message =
        errorData.error?.message ||
        errorData.detail ||
        kinjoApiText("common.import_failed", "فشل الاستيراد", "Import failed");
      const err = new Error(message);
      err.status = response.status;
      throw err;
    }

    return response.json();
  }

  /**
   * Download CSV import error report.
   * @param {Array} errors - Error list returned by importUsersCSV
   */
async downloadCSVErrorReport(errors) {
     if (!this.isAuthenticated()) {
       window.location.href = "/login";
       throw new Error("Sign-in is required");
     }
     const response = await fetchWithAuth("/api/admin/users/import-csv/error-report", {
       method: "POST",
       headers: {
         "Content-Type": "application/json",
       },
       body: JSON.stringify({ errors }),
     });
    if (!response.ok) {
      throw new Error("Failed to download error report");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `import_errors_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  /**
   * Export users to CSV/JSON
   * @param {string} format - 'csv' or 'json'
   * @param {Object} filters - Optional filters (role, status, kindergarten_id)
   */
  async exportUsers(format = "csv", filters = {}) {
    const params = { format, ...filters };
    // This returns a file, handle differently
    const queryString = new URLSearchParams(params).toString();
    const url = `/api/admin/users/export?${queryString}`;
    if (!this.isAuthenticated()) {
      window.location.href = "/login";
      throw new Error(
        kinjoApiText("auth.login.required", "يتطلب تسجيل الدخول", "Sign-in is required")
      );
    }

const response = await fetchWithAuth(url);

    if (!response) {
      throw new Error(
        kinjoApiText("auth.login.required", "يتطلب تسجيل الدخول", "Sign-in is required")
      );
    }

    if (!response.ok) {
      throw new Error(kinjoApiText("common.export_failed", "فشل التصدير", "Export failed"));
    }

    return response.blob();
  }

  // =========================================================================
  // Incident Endpoints
  // =========================================================================

  async createIncident(data) {
    // Incidents are created by POSTing the collection; /api/incidents/create
    // was never registered.
    return this.post("/api/incidents", data);
  }

  async getIncidents(params = {}) {
    return this.get("/api/incidents", params);
  }

  // =========================================================================
  // Staff Endpoints
  // =========================================================================

  async createStaffAccount(data) {
    const params = new URLSearchParams(data).toString();
    return this.post(`/api/staff/create?${params}`);
  }

  async getStaff(params = {}) {
    // Staff listing available via admin users endpoint filtered by role
    return this.get("/api/admin/users", {
      ...params,
      role: params.role || "SUPERVISOR",
    });
  }
}

// Global API instance
const api = new KinJoAPI();

// Make API instance globally available
window.api = api;

/**
 * Child Age Validation Utility
 * Age constraints: 1 day minimum to 56 months (4 years 8 months) maximum
 */
const ChildAgeValidator = {
  MIN_AGE_DAYS: 1,
  MAX_AGE_MONTHS: 56,

  _toDateOnly(dateObj) {
    return new Date(dateObj.getFullYear(), dateObj.getMonth(), dateObj.getDate());
  },

  _parseISODate(value) {
    if (!value) return null;
    const parts = String(value).split("-").map(Number);
    if (parts.length !== 3 || parts.some((p) => Number.isNaN(p))) {
      return null;
    }
    return new Date(parts[0], parts[1] - 1, parts[2]);
  },

  _diffInMonths(today, dob) {
    let months =
      (today.getFullYear() - dob.getFullYear()) * 12 + (today.getMonth() - dob.getMonth());
    if (today.getDate() < dob.getDate()) {
      months -= 1;
    }
    return months;
  },

  _subtractMonths(base, months) {
    const year = base.getFullYear();
    const monthIndex = base.getMonth() - months;
    let targetYear = year + Math.floor(monthIndex / 12);
    let targetMonth = monthIndex % 12;
    if (targetMonth < 0) {
      targetMonth += 12;
      targetYear -= 1;
    }
    const day = base.getDate();
    const lastDay = new Date(targetYear, targetMonth + 1, 0).getDate();
    return new Date(targetYear, targetMonth, Math.min(day, lastDay));
  },

  _getBounds(today) {
    const todayDate = this._toDateOnly(today);
    const maxDate = new Date(todayDate);
    maxDate.setDate(maxDate.getDate() - this.MIN_AGE_DAYS);
    const minDate = this._subtractMonths(todayDate, this.MAX_AGE_MONTHS);
    return { minDate, maxDate };
  },

  /**
   * Calculate child age and check eligibility
   * @param {string|Date} dateOfBirth - Date of birth (string or Date object)
   * @returns {object} Age information including eligibility
   */
  calculate(dateOfBirth) {
    if (!dateOfBirth) {
      return {
        isEligible: false,
        ageDays: 0,
        ageMonths: 0,
        message: "",
        messageAr: "",
      };
    }

    const dob = typeof dateOfBirth === "string" ? this._parseISODate(dateOfBirth) : dateOfBirth;
    if (!dob) {
      return {
        isEligible: false,
        ageDays: 0,
        ageMonths: 0,
        message: "",
        messageAr: "",
      };
    }

    const today = this._toDateOnly(new Date());
    const dobDate = this._toDateOnly(dob);
    const bounds = this._getBounds(today);

    const ageDays = Math.floor((today - dobDate) / (1000 * 60 * 60 * 24));
    const ageMonths = this._diffInMonths(today, dobDate);
    const ageYears = (ageMonths / 12).toFixed(1);
    const maxYears = Math.floor(this.MAX_AGE_MONTHS / 12);
    const maxRemainingMonths = this.MAX_AGE_MONTHS % 12;
    const maxAgeLabel = maxRemainingMonths
      ? `${maxYears} سنوات و${maxRemainingMonths} أشهر`
      : `${maxYears} سنوات`;
    const maxAgeLabelEn = maxRemainingMonths
      ? `${maxYears} years ${maxRemainingMonths} months`
      : `${maxYears} years`;

    let isEligible = true;
    let message = "";
    let messageAr = "";

    if (dobDate > bounds.maxDate) {
      isEligible = false;
      messageAr = `العمر: ${ageDays} يوم - غير مؤهل (الحد الأدنى ${this.MIN_AGE_DAYS} يوم)`;
      message = `Age: ${ageDays} days - Not eligible (minimum ${this.MIN_AGE_DAYS} days)`;
    } else if (dobDate < bounds.minDate) {
      isEligible = false;
      messageAr = `العمر: ${ageMonths} شهر - غير مؤهل (الحد الأقصى ${this.MAX_AGE_MONTHS} شهر / ${maxAgeLabel})`;
      message = `Age: ${ageMonths} months - Not eligible (maximum ${this.MAX_AGE_MONTHS} months / ${maxAgeLabelEn})`;
    } else {
      messageAr = `العمر: ${ageMonths} شهر (${ageYears} سنة) - مؤهل للتسجيل`;
      message = `Age: ${ageMonths} months (${ageYears} years) - Eligible for enrollment`;
    }

    return {
      isEligible,
      ageDays,
      ageMonths,
      ageYears: parseFloat(ageYears),
      message,
      messageAr,
      minAgeDays: this.MIN_AGE_DAYS,
      maxAgeMonths: this.MAX_AGE_MONTHS,
    };
  },

  /**
   * Check if a date of birth is valid for enrollment
   * @param {string|Date} dateOfBirth
   * @returns {boolean}
   */
  isEligible(dateOfBirth) {
    return this.calculate(dateOfBirth).isEligible;
  },

  /**
   * Get valid birth date range
   * @returns {object} { minDate, maxDate } - Date strings in ISO format
   */
  getValidDateRange() {
    const bounds = this._getBounds(new Date());
    const toIso = (d) => d.toISOString().split("T")[0];
    return {
      minDate: toIso(bounds.minDate),
      maxDate: toIso(bounds.maxDate),
    };
  },
};

// Make validator globally available
window.ChildAgeValidator = ChildAgeValidator;

// Export for module usage
if (typeof module !== "undefined" && module.exports) {
  module.exports = KinJoAPI;
}
