(function () {
    function tokenValue() {
        return localStorage.getItem("kinjo_token") || sessionStorage.getItem("kinjo_token") || "";
    }

    function authHeaders() {
        const headers = { "Content-Type": "application/json" };
        const token = tokenValue();
        if (token) {
            headers.Authorization = `Bearer ${token}`;
        }
        return headers;
    }

    async function apiRequest(url, options = {}) {
        const headers = authHeaders();
        const response = await fetch(url, { ...options, headers });
        if (!response.ok) {
            const text = await response.text();
            throw new Error(text || "تعذر تنفيذ الطلب");
        }
        return response.json();
    }

    function formatNumber(value, digits = 2) {
        if (value === null || value === undefined || Number.isNaN(Number(value))) {
            return "--";
        }
        return Number(value).toFixed(digits);
    }

    function formatDate(dateStr) {
        if (!dateStr) return "--";
        const date = new Date(dateStr);
        if (Number.isNaN(date.getTime())) return dateStr;
        return date.toLocaleString();
    }

    function escapeHtml(str) {
        return String(str || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function severityBadge(severity) {
        const classes = {
            CRITICAL: "bg-danger",
            HIGH: "bg-warning text-dark",
            MEDIUM: "bg-warning",
            LOW: "bg-info",
        };
        const labels = {
            CRITICAL: "حرج",
            HIGH: "عالي",
            MEDIUM: "متوسط",
            LOW: "منخفض",
        };
        return `<span class="badge ${classes[severity] || "bg-secondary"}">${labels[severity] || severity}</span>`;
    }

    function setLoading(isLoading) {
        const el = document.getElementById("alertsLoading");
        if (el) el.classList.toggle("d-none", !isLoading);
    }

    function setError(message) {
        const el = document.getElementById("alertsError");
        if (el) {
            el.textContent = message || "";
            el.classList.toggle("d-none", !message);
        }
    }

    function setEmpty(isEmpty) {
        const el = document.getElementById("alertsEmpty");
        if (el) el.classList.toggle("d-none", !isEmpty);
    }

    function filterParams() {
        const params = new URLSearchParams();
        const severity = document.getElementById("severityFilter")?.value;
        const governorate = document.getElementById("governorateFilter")?.value;
        const status = document.getElementById("statusFilter")?.value;
        const timeFilter = document.getElementById("timeFilter")?.value;

        if (severity) params.set("severity", severity);
        if (governorate) params.set("governorate", governorate);
        if (status) params.set("status", status);
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
        tbody.innerHTML = alerts
            .map((alert) => `
            <tr>
                <td>${severityBadge(alert.severity)}</td>
                <td>${escapeHtml(alert.governorate || "--")}</td>
                <td>${escapeHtml(alert.kindergarten_name || "--")}</td>
                <td>${escapeHtml(alert.metric || "--")}</td>
                <td>${formatNumber(alert.current_value)}</td>
                <td>${formatNumber(alert.threshold)}</td>
                <td>${formatDate(alert.triggered_at)}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary" data-alert-id="${alert.id}" data-action="view">
                        عرض
                    </button>
                </td>
            </tr>
        `)
            .join("");
    }

    async function loadGovernorates() {
        try {
            const response = await apiRequest("/api/admin/options/governorates");
            const select = document.getElementById("governorateFilter");
            if (select && response.governorates) {
                response.governorates.forEach((gov) => {
                    const option = document.createElement("option");
                    option.value = gov.id || gov;
                    option.textContent = gov.name_ar || gov.name_en || gov.id || gov;
                    select.appendChild(option);
                });
            }
        } catch (error) {
            console.warn("Could not load governorates:", error);
        }
    }

    async function loadAlerts() {
        setLoading(true);
        setError("");
        try {
            const params = filterParams();
            const data = await apiRequest(`/api/admin/alerts?${params.toString()}`);
            renderAlerts(data.alerts || []);
        } catch (error) {
            setError("تعذر تحميل التنبيهات. يرجى إعادة المحاولة.");
            setEmpty(false);
        } finally {
            setLoading(false);
        }
    }

    function bindEvents() {
        document.getElementById("refreshAlertsBtn")?.addEventListener("click", loadAlerts);
        document.getElementById("severityFilter")?.addEventListener("change", loadAlerts);
        document.getElementById("governorateFilter")?.addEventListener("change", loadAlerts);
        document.getElementById("statusFilter")?.addEventListener("change", loadAlerts);
        document.getElementById("timeFilter")?.addEventListener("change", loadAlerts);
    }

    async function init() {
        if (!document.getElementById("alertsRoot")) return;
        bindEvents();
        await loadGovernorates();
        await loadAlerts();
    }

    init();
})();