(function () {
    "use strict";

    // Read kinjo_csrf_token cookie (JS-visible, set by server)
    function getCsrfToken() {
        const match = document.cookie.match(/(?:^|;\s*)kinjo_csrf_token=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    async function apiRequest(url, options = {}) {
        const method = (options.method || "GET").toUpperCase();
        const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
        if (method !== "GET" && method !== "HEAD") {
            headers["X-CSRF-Token"] = getCsrfToken();
        }
        const resp = await fetch(url, { ...options, headers, credentials: "same-origin" });
        if (!resp.ok) {
            const text = await resp.text().catch(() => "");
            throw new Error(text || `HTTP ${resp.status}`);
        }
        return resp.json();
    }

    function formatNumber(value, digits = 2) {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
        return Number(value).toFixed(digits);
    }

    function formatDate(dateStr) {
        if (!dateStr) return "--";
        const d = new Date(dateStr);
        if (Number.isNaN(d.getTime())) return dateStr;
        return d.toLocaleString("en-US");
    }

    function escapeHtml(str) {
        return String(str ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    const SEVERITY_META = {
        CRITICAL: { cls: "bg-danger", label: "Critical" },
        HIGH: { cls: "bg-warning text-dark", label: "High" },
        MEDIUM: { cls: "bg-warning", label: "Medium" },
        LOW: { cls: "bg-info text-dark", label: "Low" },
    };

    const STATUS_META = {
        ACTIVE: { cls: "bg-danger", label: "Active" },
        ACKNOWLEDGED: { cls: "bg-warning text-dark", label: "Acknowledged" },
        RESOLVED: { cls: "bg-success", label: "Resolved" },
    };

    function severityBadge(severity) {
        const meta = SEVERITY_META[severity];
        if (!meta) return `<span class="badge bg-secondary">${escapeHtml(severity)}</span>`;
        return `<span class="badge ${meta.cls}">${meta.label}</span>`;
    }

    function statusBadge(status) {
        const meta = STATUS_META[status];
        if (!meta) return `<span class="badge bg-secondary">${escapeHtml(status)}</span>`;
        return `<span class="badge ${meta.cls}">${meta.label}</span>`;
    }

    function setLoading(on) {
        document.getElementById("alertsLoading")?.classList.toggle("d-none", !on);
    }

    function setError(msg) {
        const el = document.getElementById("alertsError");
        if (!el) return;
        el.textContent = msg || "";
        el.classList.toggle("d-none", !msg);
    }

    function setEmpty(on) {
        document.getElementById("alertsEmpty")?.classList.toggle("d-none", !on);
    }

    // Convert timeFilter value to a date_from ISO string
    function timeFilterToDateFrom(timeValue) {
        if (!timeValue) return null;
        const now = new Date();
        const hours = { "24h": 24, "7d": 168, "30d": 720 };
        const h = hours[timeValue];
        if (!h) return null;
        return new Date(now.getTime() - h * 3600 * 1000).toISOString();
    }

    // Pagination state
    let currentPage = 1;
    const PAGE_SIZE = 50;

    function filterParams(page = 1) {
        const params = new URLSearchParams();
        const severity   = document.getElementById("severityFilter")?.value;
        const governorate = document.getElementById("governorateFilter")?.value;
        const status     = document.getElementById("statusFilter")?.value;
        const timeVal    = document.getElementById("timeFilter")?.value;
        const dateFrom   = timeFilterToDateFrom(timeVal);

        if (severity)    params.set("severity", severity);
        if (governorate) params.set("governorate", governorate);
        if (status)      params.set("status", status);
        if (dateFrom)    params.set("date_from", dateFrom);
        params.set("skip", String((page - 1) * PAGE_SIZE));
        params.set("limit", String(PAGE_SIZE));
        return params;
    }

    function renderAlerts(alerts) {
        const tbody = document.getElementById("alertsTableBody");
        if (!tbody) return;
        if (!alerts || alerts.length === 0) {
            tbody.innerHTML = "";
            setEmpty(true);
            return;
        }
        setEmpty(false);
        tbody.innerHTML = alerts.map((a) => `
            <tr data-alert-id="${a.id}">
                <td>${severityBadge(a.severity)}</td>
                <td>${escapeHtml(a.governorate || "--")}</td>
                <td>${escapeHtml(a.kindergarten_name || "--")}</td>
                <td>${escapeHtml(a.metric || "--")}</td>
                <td>${formatNumber(a.current_value)}</td>
                <td>${formatNumber(a.threshold)}</td>
                <td>${formatDate(a.triggered_at)}</td>
                <td>${statusBadge(a.status)}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary" data-action="view" data-alert-id="${a.id}"
                            aria-label="View alert: ${escapeHtml(a.metric || "alert")} — ${escapeHtml(a.kindergarten_name || a.governorate || `#${a.id}`)}">
                        View
                    </button>
                </td>
            </tr>
        `).join("");
    }

    function renderPagination(total, page) {
        const wrap = document.getElementById("alertsPagination");
        if (!wrap) return;
        const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
        wrap.innerHTML = `
            <div class="d-flex align-items-center gap-2 mt-3">
                <button class="btn btn-sm btn-outline-secondary" id="prevPageBtn" ${page <= 1 ? "disabled" : ""}>
                    Previous
                </button>
                <span class="text-muted small">${page} / ${totalPages} &nbsp;(${total})</span>
                <button class="btn btn-sm btn-outline-secondary" id="nextPageBtn" ${page >= totalPages ? "disabled" : ""}>
                    Next
                </button>
            </div>
        `;
        document.getElementById("prevPageBtn")?.addEventListener("click", () => goToPage(page - 1));
        document.getElementById("nextPageBtn")?.addEventListener("click", () => goToPage(page + 1));
    }

    function goToPage(page) {
        currentPage = page;
        loadAlerts(page);
    }

    // In-memory cache of the last loaded alert page
    let cachedAlerts = [];

    // Holds the currently-viewed alert object for the acknowledge action
    let currentAlert = null;

    function renderDetailModal(alert) {
        currentAlert = alert;
        const content = document.getElementById("alertDetailContent");
        if (!content) return;

        const ackRow = alert.status !== "ACTIVE" ? `
            <tr>
                <th>Acknowledged At</th>
                <td>${formatDate(alert.acknowledged_at)}</td>
            </tr>` : "";

        content.innerHTML = `
            <table class="table table-sm">
                <tbody>
                    <tr><th>ID</th><td>${escapeHtml(alert.id)}</td></tr>
                    <tr><th>Severity</th><td>${severityBadge(alert.severity)}</td></tr>
                    <tr><th>Status</th><td>${statusBadge(alert.status)}</td></tr>
                    <tr><th>Metric</th><td>${escapeHtml(alert.metric)}</td></tr>
                    <tr><th>Governorate</th><td>${escapeHtml(alert.governorate || "--")}</td></tr>
                    <tr><th>Kindergarten</th><td>${escapeHtml(alert.kindergarten_name || "--")}</td></tr>
                    <tr><th>Current Value</th><td>${formatNumber(alert.current_value)}</td></tr>
                    <tr><th>Threshold</th><td>${formatNumber(alert.threshold)}</td></tr>
                    <tr><th>Triggered At</th><td>${formatDate(alert.triggered_at)}</td></tr>
                    ${ackRow}
                    <tr><th>Message</th><td>${escapeHtml(alert.message || "--")}</td></tr>
                </tbody>
            </table>
        `;

        const ackBtn = document.getElementById("acknowledgeAlertBtn");
        if (ackBtn) {
            ackBtn.disabled = alert.status !== "ACTIVE";
            ackBtn.dataset.alertId = alert.id;
        }

        const modal = document.getElementById("alertDetailModal");
        if (modal && window.bootstrap) {
            bootstrap.Modal.getOrCreateInstance(modal).show();
        }
    }

    async function acknowledgeAlert(alertId) {
        const ackBtn = document.getElementById("acknowledgeAlertBtn");
        if (ackBtn) ackBtn.disabled = true;
        try {
            const updated = await apiRequest(`/api/admin/alerts/${alertId}/acknowledge`, { method: "PATCH" });
            renderDetailModal(updated);
            await loadAlerts(currentPage);
        } catch (err) {
            const msg = "Failed to acknowledge alert.";
            setError(msg);
            if (ackBtn) ackBtn.disabled = false;
        }
    }

    async function loadGovernorates() {
        try {
            const resp = await apiRequest("/api/admin/options/governorates");
            const select = document.getElementById("governorateFilter");
            if (!select || !resp.governorates) return;
            resp.governorates.forEach((gov) => {
                const opt = document.createElement("option");
                opt.value = gov.id || gov;
                opt.textContent = gov.name_ar || gov.name_en || gov.id || gov;
                select.appendChild(opt);
            });
        } catch (e) {
            console.warn("Could not load governorates:", e);
        }
    }

    async function loadAlerts(page = 1) {
        setLoading(true);
        setError("");
        try {
            const params = filterParams(page);
            const data = await apiRequest(`/api/admin/alerts?${params}`);
            cachedAlerts = data.alerts || [];
            renderAlerts(cachedAlerts);
            renderPagination(data.total || 0, data.page || page);
            currentPage = data.page || page;
        } catch (err) {
            const msg = "Failed to load alerts. Please try again.";
            setError(msg);
            setEmpty(false);
        } finally {
            setLoading(false);
        }
    }

    function bindEvents() {
        document.getElementById("refreshAlertsBtn")?.addEventListener("click", () => loadAlerts(1));
        document.getElementById("severityFilter")?.addEventListener("change", () => loadAlerts(1));
        document.getElementById("governorateFilter")?.addEventListener("change", () => loadAlerts(1));
        document.getElementById("statusFilter")?.addEventListener("change", () => loadAlerts(1));
        document.getElementById("timeFilter")?.addEventListener("change", () => loadAlerts(1));

        // Delegated click handles dynamically-rendered View buttons.
        document.getElementById("alertsTableBody")?.addEventListener("click", (e) => {
            const btn = e.target.closest("[data-action='view']");
            if (!btn) return;
            const alertId = parseInt(btn.dataset.alertId, 10);
            if (!alertId) return;
            // Find the alert object in the last loaded results or fetch it
            fetchAndShowAlert(alertId);
        });

        document.getElementById("acknowledgeAlertBtn")?.addEventListener("click", (e) => {
            const alertId = parseInt(e.currentTarget.dataset.alertId, 10);
            if (alertId) acknowledgeAlert(alertId);
        });
    }

    function fetchAndShowAlert(alertId) {
        const alert = cachedAlerts.find((a) => a.id === alertId);
        if (alert) {
            renderDetailModal(alert);
        } else {
            console.warn("Alert not found in cache:", alertId);
        }
    }

    async function init() {
        if (!document.getElementById("alertsRoot")) return;
        bindEvents();
        await loadGovernorates();
        await loadAlerts(1);
    }

    init();
})();
