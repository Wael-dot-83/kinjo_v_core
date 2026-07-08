/**
 * Recent Activity filter bar — KinJo Admin Dashboard.
 * Filters the "Recent Activity" feed via GET /api/admin/dashboard/activity.
 * State is persisted to the URL query string (multi-page app — filters must
 * survive reload and be bookmarkable), unlike dashboard_filters.js's in-memory-only state.
 * Depends on: admin_dashboard.js (window.adminDashboard.renderActivityFeed), admin_i18n.js.
 */

(function () {
  "use strict";

  const ENDPOINT = "/api/admin/dashboard/activity";

  // Options mirror the backend's _ACTIVITY_MAP / _SIDEBAR_MODULE_LABELS exactly.
  const ACTIVITY_TYPE_OPTIONS = [
    { value: "user_login",        ar: "تسجيل الدخول",        en: "Login" },
    { value: "user_logout",       ar: "تسجيل الخروج",        en: "Logout" },
    { value: "user_create",       ar: "إضافة مستخدم",        en: "User Added" },
    { value: "user_update",       ar: "تحديث بيانات مستخدم", en: "User Updated" },
    { value: "permission_change", ar: "تعديل صلاحيات",        en: "Permission Change" },
    { value: "user_delete",       ar: "حذف مستخدم",          en: "User Deleted" },
    { value: "data_create",       ar: "إنشاء سجل",           en: "Record Created" },
    { value: "data_update",       ar: "تحديث بيانات",        en: "Data Updated" },
    { value: "data_delete",       ar: "حذف سجل",             en: "Record Deleted" },
    { value: "data_submit",       ar: "تقديم تقرير",         en: "Report Submitted" },
    { value: "message_sent",      ar: "إرسال رسالة",         en: "Message Sent" },
    { value: "incident_log",      ar: "تسجيل حادث",          en: "Incident Logged" },
    { value: "report_export",     ar: "تصدير تقرير",         en: "Report Exported" },
    { value: "settings_change",   ar: "تغيير إعدادات النظام", en: "Settings Changed" },
  ];

  const ROLE_OPTIONS = [
    { value: "ADMIN",      ar: "مدير النظام", en: "Admin" },
    { value: "MANAGER",    ar: "مدير حضانة",   en: "Manager" },
    { value: "SUPERVISOR", ar: "مراقب",       en: "Supervisor" },
    { value: "PARENT",     ar: "ولي الأمر",   en: "Parent" },
  ];

  const MODULE_OPTIONS = [
    { value: "management",        ar: "إدارة مكونات النظام", en: "System Management" },
    { value: "operations",        ar: "العمليات",          en: "Operations" },
    { value: "reports-analytics", ar: "التقارير والتحليل",  en: "Reports & Analytics" },
    { value: "governance",        ar: "الحوكمة",           en: "Governance" },
    { value: "settings",          ar: "الإعدادات",         en: "Settings" },
  ];

  const STATUS_OPTIONS = [
    { value: "success", ar: "ناجح", en: "Success" },
    { value: "failed",  ar: "فشل",  en: "Failed" },
  ];

  const SEVERITY_OPTIONS = [
    { value: "low",      ar: "منخفض", en: "Low" },
    { value: "medium",   ar: "متوسط", en: "Medium" },
    { value: "high",     ar: "مرتفع", en: "High" },
    { value: "critical", ar: "حرج",   en: "Critical" },
  ];

  const PERIOD_OPTIONS = [
    { value: "today",  ar: "اليوم",             en: "Today" },
    { value: "24h",    ar: "آخر 24 ساعة",       en: "Last 24 Hours" },
    { value: "7d",     ar: "آخر 7 أيام",        en: "Last 7 Days" },
    { value: "30d",    ar: "آخر 30 يوم",        en: "Last 30 Days" },
    { value: "month",  ar: "هذا الشهر",         en: "This Month" },
    { value: "custom", ar: "نطاق تاريخ مخصص",   en: "Custom Range" },
  ];

  const FILTER_FIELDS = [
    { key: "severity",      options: SEVERITY_OPTIONS,     labelAr: "الخطورة",     labelEn: "Severity" },
    { key: "status",        options: STATUS_OPTIONS,       labelAr: "الحالة",      labelEn: "Status" },
    { key: "module",        options: MODULE_OPTIONS,       labelAr: "القسم",       labelEn: "Module" },
    { key: "role",          options: ROLE_OPTIONS,         labelAr: "الدور",       labelEn: "Role" },
  ];

  function lang() {
    return window.KINJO_LANG === "en" ? "en" : "ar";
  }

  function t(key, fallback, params) {
    const i18n = window.AdminI18n;
    if (i18n && typeof i18n.translate === "function") return i18n.translate(key, fallback, params || {});
    return fallback || key;
  }

  function optionLabel(opt) {
    return lang() === "en" ? opt.en : opt.ar;
  }

  class ActivityFilterBar {
    constructor(container) {
      this.container = container;
      this.state = this.readStateFromUrl();
      this.render();
      this.load();
      // The bar renders synchronously at DOMContentLoaded, before the async
      // translation JSON finishes loading, so it initially shows English
      // fallback text even in Arabic mode. Poll for a canary key (cheap,
      // bounded) and refresh labels exactly once when translations land —
      // never re-render after that, so later filter changes never steal
      // focus mid-interaction.
      this._waitForI18nThenRefresh();
    }

    _waitForI18nThenRefresh(attemptsLeft = 20) {
      const canary = window.AdminI18n?.translations?.[lang()]?.dashboard?.activity_search_placeholder;
      if (canary) {
        this.render();
        if (this._lastData) {
          this.renderPagination(this._lastData);
        } else {
          // i18n loaded before the first activity fetch resolved — give load() a
          // moment to finish, then render pagination once with correct labels.
          setTimeout(() => { if (this._lastData) this.renderPagination(this._lastData); }, 200);
        }
        return;
      }
      if (attemptsLeft <= 0) return;
      setTimeout(() => this._waitForI18nThenRefresh(attemptsLeft - 1), 100);
    }

    readStateFromUrl() {
      const params = new URLSearchParams(window.location.search);
      return {
        severity:      params.get("severity") || "",
        status:        params.get("status") || "",
        module:        params.get("module") || "",
        role:          params.get("role") || "",
        user_id:       params.get("user_id") || "",
        activity_type: params.get("activity_type") || "",
        period:        params.get("period") || "",
        start_date:    params.get("start_date") || "",
        end_date:      params.get("end_date") || "",
        search:        params.get("search") || "",
        page:          parseInt(params.get("activity_page") || "1", 10) || 1,
      };
    }

    writeStateToUrl() {
      const params = new URLSearchParams(window.location.search);
      Object.entries(this.state).forEach(([key, value]) => {
        const paramKey = key === "page" ? "activity_page" : key;
        if (value === "" || value === null || value === undefined || (key === "page" && value === 1)) {
          params.delete(paramKey);
        } else {
          params.set(paramKey, value);
        }
      });
      const newUrl = `${window.location.pathname}?${params.toString()}`.replace(/\?$/, "");
      window.history.replaceState(null, "", newUrl);
    }

    render() {
      this.container.innerHTML = "";
      this.container.setAttribute("role", "search");
      this.container.setAttribute("aria-label", t("dashboard.activity_filter_bar", "Filter recent activity"));
      this.container.className = "admin-activity-filter-bar";

      // Selects render in the exact order requested (severity → status → module →
      // role → user → activity_type → period → search); a plain flex row respects
      // the document's dir automatically, so no RTL-specific reordering is needed.
      FILTER_FIELDS.forEach((field) => this.container.appendChild(this.buildSelect(field)));
      this.container.appendChild(this.buildUserIdInput());
      this.container.appendChild(this.buildSelect({ key: "activity_type", options: ACTIVITY_TYPE_OPTIONS, labelAr: "نوع النشاط", labelEn: "Activity Type" }));
      this.container.appendChild(this.buildSelect({ key: "period", options: PERIOD_OPTIONS, labelAr: "الفترة", labelEn: "Period" }));
      this.container.appendChild(this.buildCustomDateRange());
      this.container.appendChild(this.buildSearchInput());

      this.toggleCustomRangeVisibility();
    }

    buildSelect(field) {
      const wrap = document.createElement("div");
      wrap.className = "admin-activity-filter-field";

      const label = document.createElement("label");
      const selectId = `activity-filter-${field.key}`;
      label.setAttribute("for", selectId);
      label.className = "visually-hidden";
      label.textContent = lang() === "en" ? field.labelEn : field.labelAr;
      wrap.appendChild(label);

      const select = document.createElement("select");
      select.id = selectId;
      select.className = "admin-activity-filter-select";
      select.setAttribute("aria-label", lang() === "en" ? field.labelEn : field.labelAr);

      const allOpt = document.createElement("option");
      allOpt.value = "";
      allOpt.textContent = lang() === "en" ? field.labelEn : field.labelAr;
      select.appendChild(allOpt);

      field.options.forEach((opt) => {
        const optionEl = document.createElement("option");
        optionEl.value = opt.value;
        optionEl.textContent = optionLabel(opt);
        if (this.state[field.key] === opt.value) optionEl.selected = true;
        select.appendChild(optionEl);
      });

      select.addEventListener("change", () => {
        this.state[field.key] = select.value;
        this.state.page = 1;
        if (field.key === "period") this.toggleCustomRangeVisibility();
        this.applyAndReload();
      });

      wrap.appendChild(select);
      return wrap;
    }

    buildUserIdInput() {
      const wrap = document.createElement("div");
      wrap.className = "admin-activity-filter-field";

      const label = document.createElement("label");
      label.setAttribute("for", "activity-filter-user");
      label.className = "visually-hidden";
      label.textContent = t("dashboard.activity_user", "User ID");
      wrap.appendChild(label);

      const input = document.createElement("input");
      input.type = "number";
      input.id = "activity-filter-user";
      input.className = "admin-activity-filter-input";
      input.min = "1";
      input.placeholder = t("dashboard.activity_user", "User ID");
      input.setAttribute("aria-label", t("dashboard.activity_user", "User ID"));
      input.value = this.state.user_id;

      let debounceTimer = null;
      input.addEventListener("input", () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          this.state.user_id = input.value.trim();
          this.state.page = 1;
          this.applyAndReload();
        }, 400);
      });

      wrap.appendChild(input);
      return wrap;
    }

    buildCustomDateRange() {
      const wrap = document.createElement("div");
      wrap.className = "admin-activity-filter-field admin-activity-filter-custom-range";
      wrap.id = "activity-filter-custom-range";

      const startInput = document.createElement("input");
      startInput.type = "date";
      startInput.className = "admin-activity-filter-input";
      startInput.setAttribute("aria-label", t("dashboard.activity_start_date", "Start date"));
      startInput.value = this.state.start_date;

      const endInput = document.createElement("input");
      endInput.type = "date";
      endInput.className = "admin-activity-filter-input";
      endInput.setAttribute("aria-label", t("dashboard.activity_end_date", "End date"));
      endInput.value = this.state.end_date;

      const applyRange = () => {
        if (!startInput.value || !endInput.value) return;
        this.state.start_date = startInput.value;
        this.state.end_date = endInput.value;
        this.state.page = 1;
        this.applyAndReload();
      };
      startInput.addEventListener("change", applyRange);
      endInput.addEventListener("change", applyRange);

      wrap.appendChild(startInput);
      wrap.appendChild(endInput);
      return wrap;
    }

    toggleCustomRangeVisibility() {
      const el = this.container.querySelector("#activity-filter-custom-range");
      if (el) el.style.display = this.state.period === "custom" ? "flex" : "none";
    }

    buildSearchInput() {
      const wrap = document.createElement("div");
      wrap.className = "admin-activity-filter-field admin-activity-filter-search";

      const label = document.createElement("label");
      label.setAttribute("for", "activity-filter-search");
      label.className = "visually-hidden";
      label.textContent = t("dashboard.activity_search_placeholder", "Search recent activity…");
      wrap.appendChild(label);

      const input = document.createElement("input");
      input.type = "search";
      input.id = "activity-filter-search";
      input.className = "admin-activity-filter-input";
      input.setAttribute("dir", "auto");
      input.placeholder = t("dashboard.activity_search_placeholder", "Search recent activity…");
      // No aria-label here: the visually-hidden <label for="activity-filter-search">
      // above already provides the accessible name via its for/id association —
      // an aria-label with the same text is redundant (aria-label wins over the
      // <label> in the accessible-name computation, so it wasn't a double
      // announcement, just dead duplication of the same string in two places).
      input.value = this.state.search;

      let debounceTimer = null;
      input.addEventListener("input", () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          this.state.search = input.value.trim();
          this.state.page = 1;
          this.applyAndReload();
        }, 400);
      });

      const icon = document.createElement("i");
      icon.className = "bi bi-search";
      icon.setAttribute("aria-hidden", "true");
      wrap.appendChild(icon);
      wrap.appendChild(input);
      return wrap;
    }

    applyAndReload() {
      this.writeStateToUrl();
      this.load();
    }

    async load() {
      const params = new URLSearchParams();
      if (this.state.severity) params.set("severity", this.state.severity);
      if (this.state.status) params.set("status", this.state.status);
      if (this.state.module) params.set("module", this.state.module);
      if (this.state.role) params.set("role", this.state.role);
      if (this.state.user_id) params.set("user_id", this.state.user_id);
      if (this.state.activity_type) params.set("activity_type", this.state.activity_type);
      if (this.state.period) params.set("period", this.state.period);
      if (this.state.period === "custom" && this.state.start_date && this.state.end_date) {
        params.set("start_date", this.state.start_date);
        params.set("end_date", this.state.end_date);
      }
      if (this.state.search) params.set("search", this.state.search);
      params.set("page", String(this.state.page || 1));
      params.set("page_size", "20");

      const feed = document.getElementById("activity-feed");
      if (feed) {
        window.AdminComponents.renderAsyncState(feed, "loading", {
          loadingText: t("dashboard.activity_loading", lang() === "en" ? "Loading activities..." : "جاري تحميل النشاطات..."),
        });
      }

      try {
        const response = await fetch(`${ENDPOINT}?${params.toString()}`, {
          method: "GET",
          headers: { "X-Requested-With": "XMLHttpRequest" },
          credentials: "same-origin",
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        this._lastData = data;
        if (window.adminDashboard && typeof window.adminDashboard.renderActivityFeed === "function") {
          window.adminDashboard.renderActivityFeed(data.items || []);
        }
        this.renderPagination(data);
      } catch (error) {
        console.error("[ActivityFilterBar] load error:", error);
        if (feed) {
          window.AdminComponents.renderAsyncState(feed, "error", {
            errorText: t(
              "dashboard.activity_load_error",
              lang() === "en" ? "Unable to load activities. Please try again." : "تعذر تحميل النشاطات. يرجى المحاولة مرة أخرى."
            ),
            retryText: t("dashboard.activity_retry", lang() === "en" ? "Retry" : "إعادة المحاولة"),
            onRetry: () => this.load(),
          });
        }
      }
    }

    renderPagination(data) {
      const container = document.getElementById("activity-pagination");
      if (!container) return;
      container.innerHTML = "";
      const total = data.total || 0;
      const pageSize = data.page_size || 20;
      const totalPages = Math.max(1, Math.ceil(total / pageSize));
      const currentPage = data.page || 1;
      if (totalPages <= 1) return;

      const prevBtn = document.createElement("button");
      prevBtn.type = "button";
      prevBtn.className = "admin-btn admin-btn-ghost admin-btn-icon";
      prevBtn.disabled = currentPage <= 1;
      prevBtn.setAttribute("aria-label", t("dashboard.activity_prev_page", "Previous page"));
      const prevIcon = document.createElement("i");
      prevIcon.className = "bi bi-chevron-left icon icon-directional";
      prevIcon.setAttribute("aria-hidden", "true");
      prevBtn.appendChild(prevIcon);
      prevBtn.addEventListener("click", () => {
        this.state.page = Math.max(1, currentPage - 1);
        this.applyAndReload();
      });

      const status = document.createElement("span");
      status.className = "admin-activity-pagination-status";
      status.textContent = t("dashboard.activity_page_status", `Page ${currentPage} of ${totalPages}`, {
        page: String(currentPage),
        total: String(totalPages),
      });

      const nextBtn = document.createElement("button");
      nextBtn.type = "button";
      nextBtn.className = "admin-btn admin-btn-ghost admin-btn-icon";
      nextBtn.disabled = currentPage >= totalPages;
      nextBtn.setAttribute("aria-label", t("dashboard.activity_next_page", "Next page"));
      const nextIcon = document.createElement("i");
      nextIcon.className = "bi bi-chevron-right icon icon-directional";
      nextIcon.setAttribute("aria-hidden", "true");
      nextBtn.appendChild(nextIcon);
      nextBtn.addEventListener("click", () => {
        this.state.page = Math.min(totalPages, currentPage + 1);
        this.applyAndReload();
      });

      container.appendChild(prevBtn);
      container.appendChild(status);
      container.appendChild(nextBtn);
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const container = document.getElementById("activity-filter-bar");
    if (container) new ActivityFilterBar(container);
  });
})();
