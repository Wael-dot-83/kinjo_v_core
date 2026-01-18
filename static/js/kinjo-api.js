/**
 * KinJo API Client
 * Handles all communication with the backend API
 */

class KinJoAPI {
  constructor() {
    this.baseURL = "";
    this.token = localStorage.getItem("kinjo_token");
  }

  /**
   * Set authentication token
   */
  setToken(token) {
    this.token = token;
    if (token) {
      localStorage.setItem("kinjo_token", token);
    } else {
      localStorage.removeItem("kinjo_token");
    }
  }

  /**
   * Get current token
   */
  getToken() {
    return this.token;
  }

  /**
   * Check if user is authenticated
   */
  isAuthenticated() {
    return !!this.token;
  }

  /**
   * Generic request method
   */
  async request(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`;

    const defaultHeaders = {
      "Content-Type": "application/json",
    };

    if (this.token) {
      defaultHeaders["Authorization"] = `Bearer ${this.token}`;
    }

    const config = {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
    };

    try {
      const response = await fetch(url, config);

      // Handle authentication errors
      if (response.status === 401) {
        this.setToken(null);
        window.location.href = "/login?expired=true";
        throw new Error("Session expired");
      }

      // Handle other errors
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const detail = errorData.detail;
        let message = `HTTP ${response.status}`;
        let code = null;
        if (typeof detail === "string") {
          message = detail;
        } else if (detail && typeof detail === "object") {
          message = detail.message || message;
          code = detail.code || null;
        }
        const err = new Error(message);
        if (code) err.code = code;
        throw err;
      }

      // Handle empty responses
      const contentType = response.headers.get("content-type");
      if (contentType && contentType.includes("application/json")) {
        return await response.json();
      }

      return null;
    } catch (error) {
      console.error("API Error:", error);
      throw error;
    }
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

  // User Management
  async getUsers(params = {}) {
    return this.get("/api/users", params);
  }

  async getUser(id) {
    return this.get(`/api/users/${id}`);
  }

  async createUser(data) {
    return this.post("/api/users", data);
  }

  async updateUser(id, data) {
    return this.put(`/api/users/${id}`, data);
  }

  async deleteUser(id) {
    return this.delete(`/api/users/${id}`);
  }

  async bulkCreateUsers(users) {
    return this.post("/api/users/bulk-create", { users });
  }

  async bulkUpdateUserStatus(userIds, newStatus) {
    return this.post("/api/users/bulk-status-update", {
      user_ids: userIds,
      new_status: newStatus,
    });
  }

  async bulkDeleteUsers(userIds) {
    return this.post("/api/users/bulk-delete", { user_ids: userIds });
  }

  async adminResetPassword(userId, newPassword) {
    return this.post(`/api/users/${userId}/admin-reset-password`, {
      new_password: newPassword,
    });
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

// Export for module usage
if (typeof module !== "undefined" && module.exports) {
  module.exports = KinJoAPI;
}
