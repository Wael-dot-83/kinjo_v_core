(function () {
  const state = {
    allKindergartens: [],
    selectedResponse: null,
    governorateMap: new Map(),
    page: 1,
  };

  const STATUS_ORDER = {
    received: 1,
    pending: 2,
    incomplete: 3,
    absent: 4,
    not_submitted: 5,
  };

  const STATUS_UI_CONFIG = {
    received: {
      labelAr: "تم استلامه من قبل الوالدين",
      labelEn: "Received by parents",
      icon: "bi bi-check-circle-fill",
      colorClass: "text-success",
      bgClass: "bg-success-subtle",
    },
    pending: {
      labelAr: "بانتظار مراجعة المدير",
      labelEn: "Pending manager review",
      icon: "bi bi-clock-fill",
      colorClass: "text-warning",
      bgClass: "bg-warning-subtle",
    },
    incomplete: {
      labelAr: "غير مكتمل",
      labelEn: "Incomplete",
      icon: "bi bi-exclamation-triangle-fill",
      colorClass: "text-info",
      bgClass: "bg-info-subtle",
    },
    absent: {
      labelAr: "غير مملوء - غياب الطفل",
      labelEn: "Not filled - child absent",
      icon: "bi bi-person-x-fill",
      colorClass: "text-danger",
      bgClass: "bg-danger-subtle",
    },
    not_submitted: {
      labelAr: "غير مملوء - لم يقدم المشرف/المعلم",
      labelEn: "Not filled - supervisor or teacher did not submit",
      icon: "bi bi-file-earmark-x-fill",
      colorClass: "text-secondary",
      bgClass: "bg-secondary-subtle",
    },
  };

  function isEnglishUi() {
    if (typeof t === "function") {
      return !t("ar", "en");
    }
    return String(document.documentElement.lang || "").toLowerCase() === "en";
  }

  function t(arText, enText) {
    if (typeof window.t === "function") {
      return window.t(arText, enText);
    }
    return isEnglishUi() ? enText : arText;
  }

  function uiLocale() {
    return isEnglishUi() ? "en-GB" : "ar-EG";
  }

  function formatNumber(value) {
    const numericValue = Number(value || 0);
    return numericValue.toLocaleString(uiLocale());
  }

  function localizeServerMessage(message) {
    const normalized = String(message || "").trim();
    if (!normalized) {
      return "";
    }
    if (normalized === "غير متاح") {
      return t("غير متاح", "Not available");
    }
    if (normalized === "لا توجد تقارير متاحة بناءً على الاختيارات") {
      return t(
        "لا توجد تقارير متاحة بناءً على الاختيارات",
        "No reports are available for the selected filters"
      );
    }
    if (normalized === "لا توجد تقارير يومية مقدمة لهذا اليوم") {
      return t(
        "لا توجد تقارير يومية مقدمة لهذا اليوم",
        "No daily reports were submitted for this date"
      );
    }
    return normalized;
  }

  function getStatusDisplay(status) {
    const cfg = STATUS_UI_CONFIG[status] || {
      labelAr: status || "غير معروف",
      labelEn: status || "Unknown",
      icon: "fas fa-question-circle",
      colorClass: "text-muted",
      bgClass: "bg-light",
    };
    return {
      ...cfg,
      label: t(cfg.labelAr, cfg.labelEn),
    };
  }


  async function apiGet(path, params = {}) {
    const search = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null || value === "") {
        return;
      }
      search.set(key, String(value));
    });

    const query = search.toString();
    const url = query ? `${path}?${query}` : path;

    const response = await fetch(url, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
      },
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(
        localizeServerMessage(text) || t("تعذر تحميل البيانات", "Unable to load data")
      );
    }

    return response.json();
  }

  function toYmd(dateObj) {
    const year = dateObj.getFullYear();
    const month = String(dateObj.getMonth() + 1).padStart(2, "0");
    const day = String(dateObj.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function formatDateLocalized(isoDate) {
    if (!isoDate) {
      return "";
    }
    const dateValue = new Date(`${isoDate}T00:00:00`);
    if (Number.isNaN(dateValue.getTime())) {
      return isoDate;
    }
    const locale = isEnglishUi() ? "en-GB" : "ar-EG-u-ca-gregory-nu-arab";
    return new Intl.DateTimeFormat(locale, {
      day: "numeric",
      month: "long",
      year: "numeric",
    }).format(dateValue);
  }

  function resolveKindergartenName(kg) {
    if (isEnglishUi()) {
      return (
        kg?.name_en || kg?.name_ar || kg?.name || t("حضانة غير محددة", "Unspecified kindergarten")
      );
    }
    return (
      kg?.name_ar || kg?.name_en || kg?.name || t("حضانة غير محددة", "Unspecified kindergarten")
    );
  }

  function resolveGovernorateLabel(rawGovernorate) {
    const value = String(rawGovernorate || "").trim();
    if (!value) {
      return t("غير محدد", "Unspecified");
    }
    if (!isEnglishUi()) {
      return value;
    }
    return state.governorateMap.get(value) || value;
  }

  function resolveChildName(row) {
    if (isEnglishUi()) {
      return row?.child_name_en || row?.child_name_ar || "";
    }
    return row?.child_name_ar || row?.child_name_en || "";
  }

  function resolveTeacherName(row) {
    if (isEnglishUi()) {
      return row?.filled_by_name_en || row?.filled_by_name_ar || "";
    }
    return row?.filled_by_name_ar || row?.filled_by_name_en || "";
  }

  function buildChildLabel(row) {
    const childName = resolveChildName(row) || t("غير متاح", "Unavailable");
    if (isEnglishUi()) {
      return `${childName} (<bdi>ID: ${row.child_id}</bdi>)`;
    }
    return row?.child_label_ar || `اسم الطفل: ${childName} (<bdi>المعرف: ${row.child_id}</bdi>)`;
  }

  function setLoading(isLoading) {
    const loadingBox = document.getElementById("dailyReportsLoading");
    if (!loadingBox) {
      return;
    }
    loadingBox.classList.toggle("d-none", !isLoading);
  }

  function setError(message) {
    const errorBox = document.getElementById("dailyReportsError");
    if (!errorBox) {
      return;
    }

    if (message) {
      errorBox.textContent = message;
      errorBox.classList.remove("d-none");
    } else {
      errorBox.textContent = "";
      errorBox.classList.add("d-none");
    }
  }

  function setEmptyMessage(message) {
    const emptyBox = document.getElementById("dailyReportsEmpty");
    if (!emptyBox) {
      return;
    }

    if (message) {
      const msg = localizeServerMessage(message) || message;
      emptyBox.innerHTML = `
        <div class="empty-state p-4 text-center border rounded-3 bg-light text-dark" role="status">
          <h3 class="h5 mb-2">${escapeHtml(msg)}</h3>
          <p class="text-muted mb-0 small">
            ${t("يرجى مراجعة المعلم أو التحقق من سجل الحضور لمعرفة حالة الحضور والتقارير.", "Please consult the teacher or check the attendance register to verify reporting and attendance status.")}
          </p>
        </div>
      `;
      emptyBox.classList.remove("d-none");
    } else {
      emptyBox.innerHTML = "";
      emptyBox.classList.add("d-none");
    }
  }

  function setMeta(response, shownCount) {
    const meta = document.getElementById("dailyReportsMeta");
    const selectedDateChip = document.getElementById("selectedDateChip");
    const selectedCountChip = document.getElementById("selectedCountChip");
    if (!meta || !selectedDateChip || !selectedCountChip) {
      return;
    }

    if (!response) {
      meta.classList.add("d-none");
      return;
    }

    const dateLabel = isEnglishUi()
      ? formatDateLocalized(response.date)
      : response.date_ar || formatDateLocalized(response.date);
    selectedDateChip.textContent = `${t("التاريخ", "Date")}: ${dateLabel}`;
    selectedCountChip.textContent = `${t("عدد الحضانات المعروضة", "Displayed kindergartens")}: ${formatNumber(shownCount)}`;
    meta.classList.remove("d-none");
  }

  function getSelectedKindergartenIds() {
    const container = document.getElementById("kindergartenCheckboxGroup");
    if (!container) {
      return [];
    }
    return Array.from(container.querySelectorAll(".kg-checkbox:checked"))
      .map((input) => Number(input.value))
      .filter((value) => Number.isInteger(value) && value > 0);
  }

  function renderGovernorates(governorates) {
    const governorateSelect = document.getElementById("governorateSelect");
    if (!governorateSelect) {
      return;
    }

    state.governorateMap = new Map();
    const options = [`<option value="">${t("اختر المحافظة", "Select governorate")}</option>`];

    governorates.forEach((item) => {
      const canonical = item.name_ar || item.name || item.name_en || "";
      if (!canonical) {
        return;
      }
      const labelEn = item.name_en || item.name || canonical;
      state.governorateMap.set(String(canonical), labelEn);
      const label = isEnglishUi() ? labelEn : item.name_ar || canonical;
      options.push(`<option value="${escapeHtml(canonical)}">${escapeHtml(label)}</option>`);
    });
    governorateSelect.innerHTML = options.join("");
  }

  function renderKindergartensByGovernorate(governorateValue) {
    const container = document.getElementById("kindergartenCheckboxGroup");
    if (!container) {
      return;
    }

    const items = state.allKindergartens.filter((kg) => {
      if (!governorateValue) {
        return true;
      }
      return String(kg.governorate || "") === String(governorateValue);
    });

    items.sort((a, b) =>
      String(resolveKindergartenName(a)).localeCompare(
        String(resolveKindergartenName(b)),
        uiLocale()
      )
    );

    const checkboxes = items.map((kg) => {
      const name = resolveKindergartenName(kg);
      const governorate = resolveGovernorateLabel(kg.governorate);
      return `
        <div class="form-check mb-1">
          <input class="form-check-input kg-checkbox" type="checkbox" value="${kg.id}" id="kg_chk_${kg.id}">
          <label class="form-check-label small" for="kg_chk_${kg.id}">
            ${escapeHtml(name)} - <span class="text-muted"><bdi>${escapeHtml(governorate)}</bdi></span>
          </label>
        </div>
      `;
    });
    container.innerHTML = checkboxes.join("");

    const allChecked = Boolean(document.getElementById("allKindergartens")?.checked);
    if (!allChecked && governorateValue) {
      container.querySelectorAll(".kg-checkbox").forEach((input) => {
        input.checked = true;
      });
    }

    // Bind checkbox change events
    container.querySelectorAll(".kg-checkbox").forEach((input) => {
      input.addEventListener("change", () => {
        if (state.selectedResponse) {
          state.page = 1;
          renderGroups(state.selectedResponse);
        }
      });
    });

    toggleScopeControls();
  }

  function toggleScopeControls() {
    const allCheckbox = document.getElementById("allKindergartens");
    const governorateSelect = document.getElementById("governorateSelect");
    const container = document.getElementById("kindergartenCheckboxGroup");
    if (!allCheckbox || !governorateSelect || !container) {
      return;
    }

    const disabled = allCheckbox.checked;
    governorateSelect.disabled = disabled;
    container.querySelectorAll(".kg-checkbox").forEach((input) => {
      input.disabled = disabled;
    });
  }

  function buildQueryParams() {
    const dateInput = document.getElementById("dailyReportDate");
    const governorateSelect = document.getElementById("governorateSelect");
    const allCheckbox = document.getElementById("allKindergartens");

    const dateValue = dateInput?.value || toYmd(new Date());
    const allChecked = Boolean(allCheckbox?.checked);
    const governorateValue = governorateSelect?.value || "";
    const kindergartenIds = getSelectedKindergartenIds();

    const params = {
      date: dateValue,
      all_kindergartens: allChecked ? "true" : "false",
    };

    if (!allChecked && kindergartenIds.length > 0) {
      params.kindergarten_ids = kindergartenIds.join(",");
    } else if (!allChecked && governorateValue) {
      params.governorate_id = governorateValue;
    }

    return params;
  }

  function applyClientFilters(groups) {
    const statusFilter = document.getElementById("statusFilter")?.value || "";
    const childSearch = (document.getElementById("childSearch")?.value || "").trim().toLowerCase();
    const teacherSearch = (document.getElementById("teacherSearch")?.value || "")
      .trim()
      .toLowerCase();
    const sortField = document.getElementById("sortField")?.value || "child";
    const sortDir = document.getElementById("sortDir")?.value || "asc";

    return (groups || [])
      .map((kg) => {
        let rows = Array.isArray(kg.reports) ? [...kg.reports] : [];

        rows = rows.filter((row) => {
          if (statusFilter && row.status !== statusFilter) {
            return false;
          }

          if (childSearch && !String(resolveChildName(row)).toLowerCase().includes(childSearch)) {
            return false;
          }

          if (
            teacherSearch &&
            !String(resolveTeacherName(row)).toLowerCase().includes(teacherSearch)
          ) {
            return false;
          }

          return true;
        });

        rows.sort((a, b) => {
          let left = "";
          let right = "";

          if (sortField === "status") {
            left = STATUS_ORDER[a.status] || 99;
            right = STATUS_ORDER[b.status] || 99;
          } else if (sortField === "teacher") {
            left = String(resolveTeacherName(a));
            right = String(resolveTeacherName(b));
          } else {
            left = String(resolveChildName(a));
            right = String(resolveChildName(b));
          }

          if (left < right) {
            return sortDir === "asc" ? -1 : 1;
          }
          if (left > right) {
            return sortDir === "asc" ? 1 : -1;
          }
          return 0;
        });

        return { ...kg, reports: rows };
      })
      .filter((kg) => kg.has_reports || kg.reports.length > 0);
  }

  function statusSummaryHtml(statusCounts) {
    if (!statusCounts || typeof statusCounts !== "object") {
      return "";
    }
    return Object.keys(STATUS_UI_CONFIG)
      .map((key) => {
        const value = Number(statusCounts[key] || 0);
        const cfg = getStatusDisplay(key);
        return `
          <li class="summary-chip badge ${cfg.bgClass} text-dark p-2 border">
            <span class="fw-semibold">${escapeHtml(cfg.label)}:</span>
            <strong class="mx-1"><bdi>${formatNumber(value)}</bdi></strong>
          </li>
        `;
      })
      .join("");
  }

  function renderTableRows(rows) {
    if (!rows || rows.length === 0) {
      return `
        <tr>
          <td colspan="4" class="text-center text-muted py-4">${t("لا توجد نتائج مطابقة للفلاتر الحالية", "No matching rows for the current filters")}</td>
        </tr>
      `;
    }

    return rows
      .map((row) => {
        const cfg = getStatusDisplay(row.status);
        const teacherName = resolveTeacherName(row);
        const displayTeacher = teacherName ? escapeHtml(teacherName) : `<span aria-label="${t("غير متاح", "Unavailable")}">—</span>`;
        const displayNotes = row.notes ? escapeHtml(row.notes) : `<span aria-label="${t("لا توجد ملاحظات", "No notes")}">—</span>`;
        return `
        <tr>
          <td>
            <div class="fw-semibold">${escapeHtml(buildChildLabel(row))}</div>
          </td>
          <td>${displayTeacher}</td>
          <td>
            <span class="status-pill ${cfg.bgClass}">
              <i class="${cfg.icon} ${cfg.colorClass}"></i>
              ${escapeHtml(cfg.label)}
            </span>
          </td>
          <td>${displayNotes}</td>
        </tr>
      `;
      })
      .join("");
  }


  // Page-level totals across the kindergartens currently shown. Each group
  // already carries status_counts, so this aggregates what is on screen rather
  // than issuing another query -- and it reuses STATUS_UI_CONFIG so a status
  // keeps the same colour here as in the per-kindergarten chips.
  function renderKpiBar(groups) {
    const bar = document.getElementById("dailyReportsKpiBar");
    if (!bar) {
      return;
    }
    if (!Array.isArray(groups) || groups.length === 0) {
      bar.hidden = true;
      bar.innerHTML = "";
      return;
    }

    const totals = {};
    let grand = 0;
    Object.keys(STATUS_UI_CONFIG).forEach((key) => {
      totals[key] = 0;
    });
    groups.forEach((group) => {
      const counts = group.status_counts || {};
      Object.keys(totals).forEach((key) => {
        const value = Number(counts[key] || 0);
        totals[key] += value;
        grand += value;
      });
    });

    const cards = Object.keys(totals).map((key) => {
      const cfg = getStatusDisplay(key);
      const value = totals[key];
      const share = grand > 0 ? Math.round((value / grand) * 100) : 0;
      return `
        <div class="col-6 col-lg-3">
          <div class="card h-100 border-0 shadow-sm ${cfg.bgClass}">
            <div class="card-body py-3">
              <div class="small fw-semibold text-dark">${escapeHtml(cfg.label)}</div>
              <div class="h4 mb-0 fw-bold text-dark"><bdi>${formatNumber(value)}</bdi></div>
              <div class="small text-dark opacity-75"><bdi>${share}%</bdi></div>
            </div>
          </div>
        </div>
      `;
    });

    bar.innerHTML = cards.join("");
    bar.hidden = false;
  }


  // ── Pagination ───────────────────────────────────────────────────────────
  // Client-side on purpose: status, child/teacher search and sorting are all
  // applied after the fetch, so paginating on the server would let those
  // filters see only one page of data.
  function currentPerPage() {
    const el = document.getElementById("dailyReportsPerPage");
    return Number(el?.value) || 20;
  }

  function paginate(groups) {
    const perPage = currentPerPage();
    const pages = Math.max(1, Math.ceil(groups.length / perPage));
    // A filter can shrink the list under the current page; clamp instead of
    // rendering an empty page.
    if (state.page > pages) {
      state.page = pages;
    }
    if (state.page < 1) {
      state.page = 1;
    }
    const start = (state.page - 1) * perPage;
    return groups.slice(start, start + perPage);
  }

  function goToPage(page) {
    state.page = page;
    if (state.selectedResponse) {
      renderGroups(state.selectedResponse);
    }
    document.getElementById("dailyReportsAccordion")?.scrollIntoView({
      block: "start",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    });
  }

  function renderPagination(total) {
    const nav = document.getElementById("dailyReportsPagination");
    const pager = document.getElementById("dailyReportsPager");
    const range = document.getElementById("dailyReportsRange");
    if (!nav || !pager || !range) {
      return;
    }

    const perPage = currentPerPage();
    const pages = Math.ceil(total / perPage);
    if (total === 0) {
      nav.hidden = true;
      pager.innerHTML = "";
      range.textContent = "";
      return;
    }
    nav.hidden = false;

    const first = (state.page - 1) * perPage + 1;
    const last = Math.min(total, first + perPage - 1);
    range.textContent = isEnglishUi()
      ? `Showing ${first}–${last} of ${total} kindergartens`
      : `عرض ${formatNumber(first)}–${formatNumber(last)} من ${formatNumber(total)} حضانة`;

    pager.innerHTML = "";
    if (pages <= 1) {
      return;   // range still reads usefully with a single page
    }

    const add = (label, page, opts) => {
      const settings = opts || {};
      const li = document.createElement("li");
      li.className = "page-item" +
        (settings.disabled ? " disabled" : "") +
        (settings.active ? " active" : "");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "page-link";
      btn.textContent = label;
      if (settings.active) {
        btn.setAttribute("aria-current", "page");
      }
      if (settings.label) {
        btn.setAttribute("aria-label", settings.label);
      }
      btn.disabled = !!settings.disabled;
      btn.addEventListener("click", () => goToPage(page));
      li.appendChild(btn);
      pager.appendChild(li);
    };

    // Chevrons are written as words so RTL never flips their meaning.
    add(t("السابق", "Previous"), state.page - 1, {
      disabled: state.page <= 1,
      label: t("الصفحة السابقة", "Previous page"),
    });

    // A window around the current page keeps the control usable at 400 pages.
    const from = Math.max(1, state.page - 2);
    const to = Math.min(pages, state.page + 2);
    if (from > 1) {
      add(formatNumber(1), 1, {});
      if (from > 2) {
        add("…", state.page, { disabled: true });
      }
    }
    for (let p = from; p <= to; p += 1) {
      add(formatNumber(p), p, {
        active: p === state.page,
        label: t(`الصفحة ${p}`, `Page ${p}`),
      });
    }
    if (to < pages) {
      if (to < pages - 1) {
        add("…", state.page, { disabled: true });
      }
      add(formatNumber(pages), pages, {});
    }

    add(t("التالي", "Next"), state.page + 1, {
      disabled: state.page >= pages,
      label: t("الصفحة التالية", "Next page"),
    });
  }


  // ── Status pills ─────────────────────────────────────────────────────────
  // Counts come from the same status_counts the totals bar uses, so a pill and
  // the bar can never disagree.
  function statusTotals(groups) {
    const totals = { "": 0 };
    Object.keys(STATUS_UI_CONFIG).forEach((key) => {
      totals[key] = 0;
    });
    (groups || []).forEach((group) => {
      const counts = group.status_counts || {};
      Object.keys(STATUS_UI_CONFIG).forEach((key) => {
        const value = Number(counts[key] || 0);
        totals[key] += value;
        totals[""] += value;
      });
    });
    return totals;
  }

  function renderStatusPills(groups) {
    const host = document.getElementById("statusPills");
    const hidden = document.getElementById("statusFilter");
    if (!host || !hidden) {
      return;
    }
    const totals = statusTotals(groups);
    const active = hidden.value || "";
    const options = [{ key: "", label: t("كل الحالات", "All statuses"), icon: "bi bi-list-ul" }]
      .concat(Object.keys(STATUS_UI_CONFIG).map((key) => {
        const cfg = getStatusDisplay(key);
        return { key: key, label: cfg.label, icon: cfg.icon };
      }));

    host.innerHTML = "";
    options.forEach((opt) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-sm rounded-pill pill-filter " +
        (opt.key === active ? "btn-primary" : "btn-outline-secondary");
      btn.dataset.status = opt.key;
      // aria-pressed carries the state; colour alone would not reach a screen
      // reader.
      btn.setAttribute("aria-pressed", opt.key === active ? "true" : "false");
      btn.innerHTML =
        '<i class="' + opt.icon + '" aria-hidden="true"></i> ' +
        "<span>" + escapeHtml(opt.label) + "</span> " +
        '<span class="badge bg-light text-dark ms-1 pill-count"><bdi>' +
        formatNumber(totals[opt.key] || 0) + "</bdi></span>";
      btn.addEventListener("click", () => {
        // Clicking the active pill clears it, so a filter can be undone without
        // hunting for an "all" option.
        hidden.value = hidden.value === opt.key ? "" : opt.key;
        state.page = 1;
        if (state.selectedResponse) {
          renderGroups(state.selectedResponse);
        }
      });
      host.appendChild(btn);
    });
  }

  // ── Fuzzy suggestions ────────────────────────────────────────────────────
  // Written here rather than pulling in Fuse.js: this project has no bundler,
  // serves /static directly and blocks external CDNs, so the dependency would
  // have to be vendored. Subsequence matching with a proximity score covers the
  // typo and partial-name cases this search actually sees.
  function fuzzyScore(needle, haystack) {
    const n = needle.toLowerCase();
    const h = String(haystack || "").toLowerCase();
    if (!n) {
      return 0;
    }
    const direct = h.indexOf(n);
    if (direct !== -1) {
      return 1000 - direct; // an exact substring always outranks a fuzzy hit
    }
    let i = 0;
    let score = 0;
    let last = -1;
    for (let c = 0; c < h.length && i < n.length; c += 1) {
      if (h[c] === n[i]) {
        // Characters found close together score better than scattered ones.
        score += last === -1 || c - last === 1 ? 6 : 2;
        last = c;
        i += 1;
      }
    }
    return i === n.length ? score : -1; // every character must appear, in order
  }

  function suggestionPool(field) {
    const names = [];
    (state.selectedResponse?.kindergartens || []).forEach((group) => {
      (group.reports || group.rows || []).forEach((row) => {
        const name = field === "child" ? resolveChildName(row) : resolveTeacherName(row);
        if (name) {
          names.push(String(name));
        }
      });
    });
    return Array.from(new Set(names));
  }

  function closeSuggestions(field) {
    const list = document.getElementById(field + "Suggestions");
    const input = document.getElementById(field + "Search");
    if (list) {
      list.classList.add("d-none");
      list.innerHTML = "";
    }
    if (input) {
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
    }
  }

  function renderSuggestions(field) {
    const input = document.getElementById(field + "Search");
    const list = document.getElementById(field + "Suggestions");
    if (!input || !list) {
      return;
    }
    const term = input.value.trim();
    // Below two characters nearly every name matches, which is noise not help.
    if (term.length < 2) {
      closeSuggestions(field);
      return;
    }
    const matches = suggestionPool(field)
      .map((name) => ({ name: name, score: fuzzyScore(term, name) }))
      .filter((entry) => entry.score >= 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 8);

    if (matches.length === 0) {
      closeSuggestions(field);
      return;
    }

    list.innerHTML = matches
      .map((entry, index) =>
        '<li class="list-group-item list-group-item-action py-1 small" role="option" id="' +
        field + "Option" + index + '" aria-selected="false" tabindex="-1"><bdi>' +
        escapeHtml(entry.name) + "</bdi></li>")
      .join("");
    list.classList.remove("d-none");
    input.setAttribute("aria-expanded", "true");
    list.dataset.activeIndex = "-1";
  }

  function moveSuggestion(field, delta) {
    const list = document.getElementById(field + "Suggestions");
    const input = document.getElementById(field + "Search");
    if (!list || list.classList.contains("d-none")) {
      return;
    }
    const items = Array.from(list.querySelectorAll("[role='option']"));
    if (items.length === 0) {
      return;
    }
    let index = Number(list.dataset.activeIndex || -1) + delta;
    if (index < 0) {
      index = items.length - 1;
    }
    if (index >= items.length) {
      index = 0;
    }
    items.forEach((li, i) => {
      const on = i === index;
      li.classList.toggle("active", on);
      li.setAttribute("aria-selected", on ? "true" : "false");
    });
    list.dataset.activeIndex = String(index);
    items[index].scrollIntoView({ block: "nearest" });
    input.setAttribute("aria-activedescendant", items[index].id);
  }

  function chooseSuggestion(field, li) {
    const input = document.getElementById(field + "Search");
    if (!input || !li) {
      return;
    }
    input.value = li.textContent.trim();
    closeSuggestions(field);
    state.page = 1;
    if (state.selectedResponse) {
      renderGroups(state.selectedResponse);
    }
  }

  function wireAutocomplete(field) {
    const input = document.getElementById(field + "Search");
    const list = document.getElementById(field + "Suggestions");
    if (!input || !list) {
      return;
    }
    input.addEventListener("input", () => renderSuggestions(field));
    input.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        moveSuggestion(field, 1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        moveSuggestion(field, -1);
      } else if (event.key === "Enter") {
        const active = list.querySelector("[aria-selected='true']");
        if (active) {
          event.preventDefault();
          chooseSuggestion(field, active);
        }
      } else if (event.key === "Escape") {
        closeSuggestions(field);
      }
    });
    list.addEventListener("mousedown", (event) => {
      // mousedown, not click: blur would tear the list down first.
      const li = event.target.closest("[role='option']");
      if (li) {
        event.preventDefault();
        chooseSuggestion(field, li);
      }
    });
    input.addEventListener("blur", () => window.setTimeout(() => closeSuggestions(field), 120));
  }


  // ── Submission trend chart ───────────────────────────────────────────────
  // Chart.js is vendored and loaded by a plain <script> tag; this project has
  // no bundler, so there is no import to make.
  let trendChart = null;
  let trendPeriod = "month";

  // Lifecycle buckets, not the per-child status vocabulary: "received" there
  // means a parent opened the report, which the trend query cannot know. Colours
  // still line up with STATUS_UI_CONFIG's success/warning/danger reading.
  const TREND_BUCKETS = {
    sent: { color: "#198754", labelAr: "أُرسل لولي الأمر", labelEn: "Sent to parent" },
    pending: { color: "#ffc107", labelAr: "بانتظار الاعتماد", labelEn: "Awaiting approval" },
    incomplete: { color: "#dc3545", labelAr: "غير مكتمل", labelEn: "Incomplete" },
  };

  function trendBucketLabel(key) {
    const cfg = TREND_BUCKETS[key];
    if (!cfg) {
      return key;
    }
    return isEnglishUi() ? cfg.labelEn : cfg.labelAr;
  }

  function showTrendError(message) {
    const box = document.getElementById("trendError");
    if (!box) {
      return;
    }
    box.textContent = t("تعذر تحميل بيانات الاتجاه.", "Could not load trend data.") + " " + message;
    box.classList.remove("d-none");
  }

  function hideTrendError() {
    document.getElementById("trendError")?.classList.add("d-none");
  }

  function currentTrendFilters() {
    const params = new URLSearchParams({ period: trendPeriod });
    const governorate = document.getElementById("governorateSelect")?.value;
    if (governorate) {
      params.set("governorate", governorate);
    }
    // Honour an explicit kindergarten selection so the chart matches the list.
    const allChecked = document.getElementById("allKindergartens")?.checked;
    if (!allChecked) {
      const ids = Array.from(
        document.querySelectorAll("#kindergartenCheckboxGroup input[type='checkbox']:checked")
      ).map((cb) => cb.value);
      if (ids.length > 0) {
        params.set("kindergarten_ids", ids.join(","));
      }
    }
    return params;
  }

  function renderTrendSummary(data) {
    const host = document.getElementById("trendSummary");
    if (!host) {
      return;
    }
    const totals = data.totals || {};
    const parts = [
      `<span><strong><bdi>${formatNumber(totals.total || 0)}</bdi></strong> ${escapeHtml(t("إجمالي التقديمات", "total submissions"))}</span>`,
      `<span><strong><bdi>${formatNumber(totals.average || 0)}</bdi></strong> ${escapeHtml(t("متوسط يومي", "daily average"))}</span>`,
    ];
    if (totals.best_day) {
      parts.push(
        `<span>${escapeHtml(t("أفضل يوم", "Best day"))}: <bdi>${escapeHtml(formatDateLocalized(totals.best_day))}</bdi> (<bdi>${formatNumber(totals.best_day_count || 0)}</bdi>)</span>`
      );
    }
    host.innerHTML = parts.join("");
  }

  function renderTrendChart(data) {
    const canvas = document.getElementById("submissionTrendChart");
    const ChartLib = window.Chart;
    if (!canvas || !ChartLib) {
      return;   // the summary text still carries the numbers
    }
    if (trendChart) {
      trendChart.destroy();
    }

    const datasets = Object.keys(data.series || {}).map((key) => ({
      label: trendBucketLabel(key),
      data: data.series[key],
      backgroundColor: (TREND_BUCKETS[key] || {}).color || "#6c757d",
      borderRadius: 3,
    }));

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    trendChart = new ChartLib(canvas, {
      type: "bar",
      data: {
        labels: (data.labels || []).map((iso) => formatDateLocalized(iso)),
        datasets: datasets,
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: reduceMotion ? false : { duration: 300 },
        plugins: {
          legend: {
            position: "top",
            rtl: document.documentElement.dir === "rtl",
            labels: { usePointStyle: true, pointStyle: "circle" },
          },
          tooltip: {
            rtl: document.documentElement.dir === "rtl",
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${formatNumber(ctx.parsed.y)}`,
            },
          },
        },
        // Stacked: the useful reading is the day's total split by state, not
        // three separate series to eyeball against each other.
        scales: {
          x: { stacked: true, grid: { display: false } },
          y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } },
        },
      },
    });
  }

  async function refreshTrendChart() {
    try {
      const response = await fetch(`/api/daily-reports/trends?${currentTrendFilters().toString()}`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const data = await response.json();
      hideTrendError();
      renderTrendSummary(data);
      renderTrendChart(data);
    } catch (error) {
      // The chart is supplementary; a failure here must not disturb the list.
      showTrendError(error?.message || "");
    }
  }

  function wireTrendControls() {
    const buttons = document.querySelectorAll(".trend-controls [data-period]");
    if (buttons.length === 0) {
      return;
    }
    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        buttons.forEach((other) => {
          const on = other === btn;
          other.classList.toggle("active", on);
          other.setAttribute("aria-pressed", on ? "true" : "false");
        });
        trendPeriod = btn.dataset.period;
        refreshTrendChart();
      });
    });
    refreshTrendChart();
  }

  function renderGroups(response) {
    const container = document.getElementById("dailyReportsAccordion");
    if (!container) {
      return;
    }

    renderStatusPills(response.kindergartens || []);
    const groups = applyClientFilters(response.kindergartens || []);
    // Totals stay across the whole filtered set, not just the visible page:
    // "12 missing" is only meaningful for everything the filters match.
    renderKpiBar(groups);
    const pageGroups = paginate(groups);
    renderPagination(groups.length);

    if (groups.length === 0) {
      container.innerHTML = "";
      if (response.is_future_date) {
        setEmptyMessage(t("غير متاح", "Not available"));
      } else {
        setEmptyMessage(
          localizeServerMessage(response.message) ||
            t(
              "لا توجد تقارير متاحة بناءً على الاختيارات",
              "No reports are available for the selected filters"
            )
        );
      }
      setMeta(response, 0);
      renderPagination(0);
      return;
    }

    setEmptyMessage("");
    setMeta(response, groups.length);

    container.innerHTML = pageGroups
      .map((kg, index) => {
        const collapseId = `kgCollapse${kg.id}`;
        const headingId = `kgHeading${kg.id}`;
        const expanded = index === 0 ? "true" : "false";
        const showClass = index === 0 ? "show" : "";
        const noReportsNote =
          kg.has_reports === false
            ? `<div class="no-report-note">${escapeHtml(localizeServerMessage(kg.message) || t("لا توجد تقارير يومية مقدمة لهذا اليوم", "No daily reports were submitted for this date"))}</div>`
            : "";
        const managerName = isEnglishUi()
          ? kg.manager_name_en || kg.manager_name_ar || t("غير محدد", "Unspecified")
          : kg.manager_name_ar || kg.manager_name_en || t("غير محدد", "Unspecified");
        const reportDate = isEnglishUi()
          ? formatDateLocalized(kg.report_date)
          : kg.report_date_ar || formatDateLocalized(kg.report_date);

        return `
          <section class="accordion-item mb-3 border rounded-3 overflow-hidden" aria-labelledby="${headingId}">
            <h2 class="accordion-header" id="${headingId}">
              <button class="accordion-button ${index === 0 ? "" : "collapsed"}" type="button"
                data-bs-toggle="collapse" data-bs-target="#${collapseId}" aria-expanded="${expanded}" aria-controls="${collapseId}">
                <div class="w-100">
                  <div class="fw-bold">${escapeHtml(resolveKindergartenName(kg))}</div>
                  <div class="kg-meta mt-1">
                    ${t("المدير", "Manager")}: <bdi>${escapeHtml(managerName)}</bdi> |
                    ${t("التاريخ", "Date")}: <bdi>${escapeHtml(reportDate)}</bdi>
                  </div>
                </div>
              </button>
            </h2>
            <div id="${collapseId}" class="accordion-collapse collapse ${showClass}" aria-labelledby="${headingId}" data-bs-parent="#dailyReportsAccordion">
              <div class="accordion-body">
                <ul class="status-summary d-flex flex-wrap gap-2 mb-3 list-unstyled" aria-label="${t(`ملخص حالة التقارير في ${resolveKindergartenName(kg)}`, `Report status summary in ${resolveKindergartenName(kg)}`)}">
                  ${statusSummaryHtml(kg.status_counts)}
                </ul>
                ${noReportsNote}
                <div class="table-responsive">
                  <table class="table table-hover report-table align-middle">
                    <caption class="visually-hidden">${t(`جدول التقارير اليومية لـ ${resolveKindergartenName(kg)}`, `Daily reports table for ${resolveKindergartenName(kg)}`)}</caption>
                    <thead class="table-light">
                      <tr>
                        <th scope="col">${t("الطفل", "Child")}</th>
                        <th scope="col">${t("تمت التعبئة بواسطة", "Filled by")}</th>
                        <th scope="col">${t("الحالة", "Status")}</th>
                        <th scope="col">${t("ملاحظات", "Notes")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      ${renderTableRows(kg.reports)}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </section>
        `;
      })
      .join("");
  }

  async function loadInitialFilters() {
    const [governoratesResponse, kindergartensResponse] = await Promise.all([
      apiGet("/api/reference/governorates"),
      // Full network list (635+) for client-side governorate grouping; the
      // endpoint envelope nests rows under data.items.
      apiGet("/api/kindergartens", { limit: 1000, include_inactive: true }),
    ]);

    const governorates = governoratesResponse?.governorates || [];
    const kindergartens = kindergartensResponse?.data?.items || kindergartensResponse?.items || [];

    state.allKindergartens = kindergartens;
    renderGovernorates(governorates);
    renderKindergartensByGovernorate("");
  }

  async function fetchAndRenderReports() {
    setError("");
    setEmptyMessage("");
    setLoading(true);
    try {
      const params = buildQueryParams();
      const response = await apiGet("/api/daily-reports", params);
      state.selectedResponse = response;
      renderGroups(response);
    } catch (error) {
      console.error(error);
      setError(
         error?.message ||
          t("خطأ في التحميل. يرجى إعادة المحاولة.", "Loading failed. Please try again.")
      );
      document.getElementById("dailyReportsAccordion").innerHTML = "";
      setMeta(null, 0);
    } finally {
      setLoading(false);
    }
  }

  function attachEvents() {
    const filterForm = document.getElementById("dailyReportsFilterForm");
    filterForm?.addEventListener("submit", (e) => {
      e.preventDefault();
      fetchAndRenderReports();
    });

    const searchBtn = document.getElementById("searchDailyReportsBtn");
    const allCheckbox = document.getElementById("allKindergartens");
    const governorateSelect = document.getElementById("governorateSelect");
    const dateInput = document.getElementById("dailyReportDate");
    const statusFilter = document.getElementById("statusFilter");
    const childSearch = document.getElementById("childSearch");
    const teacherSearch = document.getElementById("teacherSearch");
    const sortField = document.getElementById("sortField");
    const sortDir = document.getElementById("sortDir");

    searchBtn?.addEventListener("click", (e) => {
      e.preventDefault();
      fetchAndRenderReports();
    });

    allCheckbox?.addEventListener("change", () => {
      toggleScopeControls();
      if (allCheckbox.checked && state.selectedResponse) {
        fetchAndRenderReports();
      }
    });

    governorateSelect?.addEventListener("change", () => {
      renderKindergartensByGovernorate(governorateSelect.value || "");
    });

    dateInput?.addEventListener("change", fetchAndRenderReports);
    document.getElementById("governorateSelect")?.addEventListener("change", refreshTrendChart);
    wireTrendControls();
    wireAutocomplete("child");
    wireAutocomplete("teacher");
    // Changing the page size invalidates the current page number.
    document.getElementById("dailyReportsPerPage")?.addEventListener("change", () => {
      state.page = 1;
      if (state.selectedResponse) {
        renderGroups(state.selectedResponse);
      }
    });

    [statusFilter, childSearch, teacherSearch, sortField, sortDir].forEach((control) => {
      control?.addEventListener("input", () => {
        if (state.selectedResponse) {
          state.page = 1;
          renderGroups(state.selectedResponse);
        }
      });
    });
  }

  async function init() {
    const dateInput = document.getElementById("dailyReportDate");
    if (dateInput && !dateInput.value) {
      dateInput.value = toYmd(new Date());
    }

    toggleScopeControls();
    attachEvents();
    setLoading(true);
    try {
      await loadInitialFilters();
      await fetchAndRenderReports();
    } catch (error) {
      console.error(error);
      setLoading(false);
      setError(error?.message || t("تعذر تحميل بيانات الصفحة.", "Unable to load page data."));
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
