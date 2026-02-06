/**
 * KinJo API Client
 * Handles all communication with the backend API
 * Uses centralized AuthService for authentication
 */

class KinJoAPI {
  constructor() {
    this.baseURL = "";
  }

  /**
   * Check if user is authenticated
   */
  isAuthenticated() {
    return AuthService && AuthService.isAuthenticated();
  }

  /**
   * Generic request method using centralized auth
   */
  async request(endpoint, options = {}) {
    const response = await fetchWithAuth(`${this.baseURL}${endpoint}`, options);

    // fetchWithAuth already throws on non-OK responses and redirects on 401,
    // so at this point we should have a valid response object (or null when redirected).
    if (!response) {
      throw new Error("Authentication required");
    }

    // Some endpoints may return no content (204)
    if (response.status === 204) {
      return null;
    }

    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      return await response.json();
    }

    // Fallback: return text for non-JSON responses
    return await response.text();
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
      throw new Error(error.detail || "Login failed");
    }

    const data = await response.json();
    this.setToken(data.access_token);
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
    return this.post("/api/kindergartens", data);
  }

  async updateKindergarten(id, data) {
    return this.put(`/api/kindergartens/${id}`, data);
  }

  async deleteKindergarten(id) {
    return this.delete(`/api/kindergartens/${id}`);
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
    return this.post("/enrollment/apply", data);
  }

  async submitEnrollment(id) {
    return this.post(`/enrollment/${id}/submit`);
  }

  async reviewEnrollment(id, decision, reason = null) {
    const params = { decision };
    if (reason) params.reason = reason;
    return this.post(`/enrollment/${id}/review`, params);
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
    return this.get("/api/attendance/today", {
      kindergarten_id: kindergartenId,
    });
  }

  async searchKindergartens(params = {}) {
    const queryParams = {};
    if (params.search) queryParams.name = params.search;
    if (params.governorate) queryParams.governorate = params.governorate;
    if (params.phone) queryParams.phone = params.phone;
    return this.get("/api/kindergartens", queryParams);
  }

  async getKindergartenClasses(kindergartenId) {
    return this.get("/api/classes", { kindergarten_id: kindergartenId });
  }

  async getKindergartenChildren(kindergartenId, classIds = null) {
    const params = { kindergarten_id: kindergartenId };
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

  // =========================================================================
  // KPI Endpoints
  // =========================================================================

  async getAttendanceRate(kindergartenId, periodStart, periodEnd) {
    return this.get("/api/kpi/attendance-rate", {
      kindergarten_id: kindergartenId,
      period_start: periodStart,
      period_end: periodEnd,
    });
  }

  async getIncidentRate(kindergartenId, periodStart, periodEnd) {
    return this.get("/api/kpi/incident-rate", {
      kindergarten_id: kindergartenId,
      period_start: periodStart,
      period_end: periodEnd,
    });
  }

  async getRatioCompliance(kindergartenId, periodStart, periodEnd) {
    return this.get("/api/kpi/ratio-compliance", {
      kindergarten_id: kindergartenId,
      period_start: periodStart,
      period_end: periodEnd,
    });
  }

  async getGovernanceScore(kindergartenId, periodStart, periodEnd) {
    return this.get("/api/kpi/governance-score", {
      kindergarten_id: kindergartenId,
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
    return this.get("/api/supervisor/my-children");
  }

  async getAttendanceStatus(targetDate = null) {
    const params = {};
    if (targetDate) params.target_date = targetDate;
    return this.get("/api/supervisor/attendance-status", params);
  }

  async getPendingReports(reportDate = null) {
    const params = {};
    if (reportDate) params.report_date = reportDate;
    return this.get("/api/supervisor/pending-reports", params);
  }

  // =========================================================================
  // Manager Endpoints
  // =========================================================================

  async getManagerDashboard() {
    return this.get("/api/manager/dashboard");
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
  async bulkUpdateUserStatus(
    userIds,
    newStatus,
    confirmationToken = null,
    dryRun = false,
  ) {
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

    const response = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${this.token}`,
      },
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const message =
        errorData.error?.message || errorData.detail || "Import failed";
      const err = new Error(message);
      err.status = response.status;
      throw err;
    }

    return response.json();
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

    const response = await fetch(url, {
      headers: {
        Authorization: `Bearer ${this.token}`,
      },
    });

    if (!response.ok) {
      throw new Error("Export failed");
    }

    return response.blob();
  }

  // =========================================================================
  // Incident Endpoints
  // =========================================================================

  async createIncident(data) {
    return this.post("/api/incidents/create", data);
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
    return this.get("/api/staff", params);
  }
}

// Global API instance
const api = new KinJoAPI();

// Make API instance globally available
window.api = api;

// Export for module usage
if (typeof module !== "undefined" && module.exports) {
  module.exports = KinJoAPI;
}
