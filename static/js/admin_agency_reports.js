(function () {
  "use strict";
  const page = document.querySelector("[data-agency-reports-page]");
  if (!page) return;
  const lang = document.documentElement.lang === "en" ? "en" : "ar";
  const root =
    document.getElementById("agency-reports-root") ||
    document.getElementById("agency-report-root");
  const api = (path) =>
    fetch(path, {
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
    }).then((r) => {
      if (r.status === 401) {
        window.location.href = "/login?next=" + encodeURIComponent(window.location.pathname + window.location.search);
        throw new Error("HTTP 401 Unauthorized");
      }
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  const t = (ar, en) => (lang === "en" ? en : ar);
  const LOCALE = lang === "ar" ? "ar-JO" : "en-US";
  const bi = (ar, en) => (lang === "en" ? (en || ar) : (ar || en));
  const pick = (v) => (v && typeof v === "object" && (v.ar !== undefined || v.en !== undefined) ? bi(v.ar, v.en) : v);

  function formatDateForFilename(value) {
    if (!value) return new Date().toISOString().slice(0, 10);
    try {
      if (typeof value === "string" && value.length >= 10) {
        return value.slice(0, 10);
      }
      const parsed = new Date(value);
      if (!Number.isNaN(parsed.valueOf())) {
        return parsed.toISOString().slice(0, 10);
      }
    } catch (err) {
      /* ignore and fall through */
    }
    return new Date().toISOString().slice(0, 10);
  }

  // Index-view filter state. Declared at module scope because agencyCard() (a
  // top-level function) reads state.dateFrom/dateTo to propagate the selected
  // date range onto agency links; a block-scoped const would throw ReferenceError
  // there and the catalog .then() would fall into .catch ("تعذر تحميل البيانات").
  const state = {
    search: "",
    status: "all",
    sort: "name",
    dateFrom: "",
    dateTo: "",
  };

  const agencyLogoFiles = {
    moe: "moe.jpg",
    moh: "moh.jpg",
    dos: "gsd.jpg",
    ncfa: "ncfa.png",
    mol: "mol.png",
    mosd: "mosd.jpg",
    mopic: "mopic.png",
  };

  function clear(el) {
    if (el) el.innerHTML = "";
  }

  function pill(text, kind, icon) {
    const span = document.createElement("span");
    span.className = "agency-status agency-status--" + (kind || "default");
    if (icon) {
      const i = document.createElement("i");
      i.className = "bi " + icon;
      i.setAttribute("aria-hidden", "true");
      span.appendChild(i);
      span.appendChild(document.createTextNode(" " + text));
    } else {
      span.textContent = text;
    }
    return span;
  }

  function statusBadge(status) {
    if (status === "ready")
      return pill(t("جاهزة", "Ready"), "success", "bi-check-circle-fill");
    if (status === "requires_structured_data")
      return pill(
        t("تحتاج بيانات", "Needs data"),
        "warning",
        "bi-exclamation-triangle-fill",
      );
    return pill(t("غير متاح", "Unavailable"), "default", "bi-dash-circle");
  }

  function logoBadge(agency) {
    const badge = document.createElement("span");
    badge.className = "agency-logo-badge";
    badge.setAttribute("aria-hidden", "true");
    if (agency.icon) {
      const i = document.createElement("i");
      i.className = "bi " + agency.icon;
      badge.appendChild(i);
    } else {
      const name =
        (lang === "en" ? agency.name_en : agency.name_ar) || agency.code || "";
      badge.textContent = name.trim().slice(0, 2);
      badge.classList.add("agency-logo-badge--text");
    }
    return badge;
  }

  window.renderAgencyLogo = function renderAgencyLogo(agency, size) {
    const logoFile = agencyLogoFiles[agency.code];
    if (logoFile) {
      const img = document.createElement("img");
      img.className = "agency-card-logo";
      img.src = "/static/img/agencies/" + logoFile;
      img.alt = "";
      img.setAttribute("aria-hidden", "true");
      if (size) {
        img.width = size;
        img.height = size;
      }
      return img;
    }
    return logoBadge(agency);
  };

  // -------- Index page: readiness, KPI grid, agency cards, skeletons --------
  const READINESS = {
    ready: {
      ar: "جاهزة",
      en: "Ready",
      cls: "success",
      icon: "bi-check-circle-fill",
    },
    partial: {
      ar: "جاهزة جزئيًا",
      en: "Partially ready",
      cls: "info",
      icon: "bi-clock-history",
    },
    needs_data: {
      ar: "تحتاج بيانات",
      en: "Needs data",
      cls: "warning",
      icon: "bi-exclamation-triangle-fill",
    },
  };
  const READINESS_RANK = { ready: 0, partial: 1, needs_data: 2 };

  function agencyReadiness(agency) {
    const total = agency.report_count || 0;
    const ready = agency.ready_report_count || 0;
    if (total > 0 && ready >= total) return "ready";
    if (ready > 0) return "partial";
    return "needs_data";
  }

  function readinessBadge(key) {
    const r = READINESS[key] || READINESS.needs_data;
    const span = document.createElement("span");
    span.className = "agency-readiness agency-readiness--" + r.cls;
    const i = document.createElement("i");
    i.className = "bi " + r.icon;
    i.setAttribute("aria-hidden", "true");
    span.appendChild(i);
    span.appendChild(document.createTextNode(" " + t(r.ar, r.en)));
    return span;
  }

  function renderKpiGrid(agencies) {
    const grid = document.getElementById("agency-kpi-grid");
    if (!grid) return;
    const totalReports = agencies.reduce(
      (s, a) => s + (a.report_count || 0),
      0,
    );
    const readyReports = agencies.reduce(
      (s, a) => s + (a.ready_report_count || 0),
      0,
    );
    const needsData = agencies.reduce(
      (s, a) => s + (a.requires_data_count || 0),
      0,
    );
    const generatedAt = agencies.length ? agencies[0].generated_at : null;
    const items = [
      {
        value: agencies.length,
        label: t("الجهات الرسمية", "Official agencies"),
        icon: "bi-buildings",
        cls: "primary",
        hint: t("جهات حكومية متكاملة", "Connected agencies"),
      },
      {
        value: totalReports,
        label: t("إجمالي التقارير", "Total reports"),
        icon: "bi-file-earmark-bar-graph",
        cls: "primary",
        hint: t("تقارير تجميعية متاحة", "Aggregated reports"),
      },
      {
        value: readyReports,
        label: t("التقارير الجاهزة", "Ready reports"),
        icon: "bi-check-circle-fill",
        cls: "success",
        hint: t("جاهزة للعرض والتصدير", "Ready to view & export"),
      },
      {
        value: needsData,
        label: t("تحتاج إلى بيانات", "Need data"),
        icon: "bi-exclamation-triangle-fill",
        cls: "warning",
        hint: t("بانتظار بيانات منظمة", "Awaiting structured data"),
      },
    ];
    grid.innerHTML = "";
    items.forEach((item) => {
      const li = document.createElement("li");
      li.className = "agency-kpi agency-kpi--" + item.cls;
      li.setAttribute("aria-label", item.value + " — " + item.label);
      const icon = document.createElement("span");
      icon.className = "agency-kpi__icon";
      icon.innerHTML =
        '<i class="bi ' + item.icon + '" aria-hidden="true"></i>';
      const body = document.createElement("div");
      body.className = "agency-kpi__body";
      const val = document.createElement("span");
      val.className = "agency-kpi__value";
      val.textContent = item.value;
      const lbl = document.createElement("span");
      lbl.className = "agency-kpi__label";
      lbl.textContent = item.label;
      const hint = document.createElement("span");
      hint.className = "agency-kpi__hint";
      hint.textContent = item.hint;
      body.append(val, lbl, hint);
      li.append(icon, body);
      grid.appendChild(li);
    });
    const updatedAtEl = document.getElementById("agency-index-updated");
    if (updatedAtEl) {
      updatedAtEl.innerHTML =
        '<i class="bi bi-clock" aria-hidden="true"></i> ' +
        t("آخر تحديث", "Last updated") +
        ": " +
        (generatedAt
          ? new Date(generatedAt).toLocaleString(LOCALE, {
              dateStyle: "medium",
              timeStyle: "short",
            })
          : "—");
    }
  }

  function agencyCard(agency) {
    const li = document.createElement("li");
    li.className = "agency-card agency-card--interactive";
    const readiness = agencyReadiness(agency);
    const dateParams =
      state.dateFrom || state.dateTo
        ? "?" +
          new URLSearchParams({
            date_from: state.dateFrom || "",
            date_to: state.dateTo || "",
          }).toString()
        : "";
    const href =
      "/admin/agency-reports/" + encodeURIComponent(agency.code) + dateParams;

    const head = document.createElement("div");
    head.className = "agency-card__head";
    head.appendChild(window.renderAgencyLogo(agency, 80));
    const titleWrap = document.createElement("div");
    titleWrap.className = "agency-card__title-wrap";
    const h3 = document.createElement("h3");
    h3.className = "agency-card__title";
    h3.textContent =
      lang === "en" ? agency.name_en || agency.name_ar : agency.name_ar;
    titleWrap.append(h3, readinessBadge(readiness));
    head.appendChild(titleWrap);

    const purpose = document.createElement("p");
    purpose.className = "agency-card-desc";
    purpose.textContent =
      (lang === "en"
        ? agency.description_en || agency.description_ar
        : agency.description_ar) || "";

    const usage = document.createElement("p");
    usage.className = "agency-card-usage";
    usage.innerHTML =
      "<strong>" +
      t("كيفية الاستخدام", "How to use") +
      ":</strong> " +
      t(
        "اختر فترة تجميع البيانات. استخدم الفلاتر لتحديد النطاق الجغرافي. راجع النتائج وصدّرها عند الحاجة.",
        "Select a data aggregation period. Use filters to define the geographic scope. Review results and export when needed.",
      );

    const updated = document.createElement("p");
    updated.className = "agency-card-updated";
    updated.innerHTML =
      '<i class="bi bi-clock" aria-hidden="true"></i> ' +
      t("آخر تحديث", "Last updated") +
      ": " +
      (agency.generated_at
        ? new Date(agency.generated_at).toLocaleString(LOCALE, {
            dateStyle: "medium",
            timeStyle: "short",
          })
        : "—");

    const stats = document.createElement("dl");
    stats.className = "agency-card__stats";
    function stat(labelAr, labelEn, value, cls) {
      const wrap = document.createElement("div");
      wrap.className =
        "agency-card__stat" + (cls ? " agency-card__stat--" + cls : "");
      const dd = document.createElement("dd");
      dd.textContent = value;
      const dt = document.createElement("dt");
      dt.textContent = t(labelAr, labelEn);
      wrap.append(dd, dt);
      return wrap;
    }
    stats.append(
      stat("التقارير", "Reports", agency.report_count || 0),
      stat("جاهزة", "Ready", agency.ready_report_count || 0, "success"),
      stat(
        "تحتاج بيانات",
        "Needs data",
        agency.requires_data_count || 0,
        "warning",
      ),
    );

    li.appendChild(head);
    li.appendChild(purpose);
    li.appendChild(usage);
    li.appendChild(updated);
    li.appendChild(stats);

    if (readiness !== "ready" && (agency.requires_data_count || 0) > 0) {
      const note = document.createElement("p");
      note.className = "agency-card__note";
      note.innerHTML = '<i class="bi bi-info-circle" aria-hidden="true"></i> ';
      note.appendChild(
        document.createTextNode(
          agency.code === "moh"
            ? t(
                "تحتاج التقارير إلى بيانات صحية منظمة.",
                "These reports need structured health data.",
              )
            : t(
                "بعض التقارير تحتاج إلى بيانات منظمة إضافية.",
                "Some reports need additional structured data.",
              ),
        ),
      );
      li.appendChild(note);
    }

    const link = document.createElement("a");
    link.className = "admin-btn admin-btn-primary agency-card-btn";
    link.href = href;
    link.innerHTML =
      "<span>" +
      t("فتح تقارير الجهة", "Open agency reports") +
      '</span><i class="bi bi-chevron-left icon-directional" aria-hidden="true"></i>';
    link.setAttribute(
      "aria-label",
      t(
        "عرض تقارير " + (agency.name_ar || agency.code),
        "View reports for " + (agency.name_en || agency.code),
      ),
    );
    li.appendChild(link);

    // Whole-card affordance without nesting interactive controls: clicking the
    // card background navigates; keyboard users use the real link/inner controls.
    li.addEventListener("click", function (e) {
      if (e.target.closest("a,button")) return;
      window.location.href = href;
    });
    return li;
  }

  function skeletonGrid(n) {
    const ul = document.createElement("ul");
    ul.className = "agency-card-grid";
    ul.setAttribute("aria-hidden", "true");
    for (let i = 0; i < n; i++) {
      const li = document.createElement("li");
      li.className = "agency-card agency-card--skeleton";
      li.innerHTML =
        '<div class="agency-card__head"><span class="sk sk-logo"></span><span class="sk sk-line sk-title"></span></div>' +
        '<span class="sk sk-line"></span><span class="sk sk-line sk-short"></span>' +
        '<div class="agency-card__stats"><span class="sk sk-stat"></span><span class="sk sk-stat"></span><span class="sk sk-stat"></span></div>' +
        '<span class="sk sk-btn"></span>';
      ul.appendChild(li);
    }
    return ul;
  }

  function renderAgency(data) {
    clear(root);

    // Update breadcrumb and page title
    const breadcrumbName = document.getElementById("agency-current-name");
    if (breadcrumbName)
      breadcrumbName.textContent =
        lang === "en" ? data.agency_name_en : data.agency_name_ar;
    const titleEl = document.getElementById("agency-reports-title");
    if (titleEl)
      titleEl.textContent =
        lang === "en" ? data.agency_name_en : data.agency_name_ar;
    const desc = document.getElementById("agency-description");
    if (desc) desc.textContent = bi(data.description_ar, data.description_en) || "";
    const headerUpdated = document.getElementById("agency-header-updated");
    if (headerUpdated) {
      headerUpdated.innerHTML =
        '<i class="bi bi-clock" aria-hidden="true"></i> ' +
        t("آخر تحديث", "Last updated") +
        ": " +
        (data.generated_at
          ? new Date(data.generated_at).toLocaleString(LOCALE, {
              dateStyle: "medium",
              timeStyle: "short",
            })
          : "—");
    }

    // Render agency logo in header
    const logoContainer = document.getElementById("agency-logo-container");
    if (logoContainer && window.renderAgencyLogo) {
      const agencyObj = {
        code: data.agency_code,
        name_ar: data.agency_name_ar,
        name_en: data.agency_name_en,
        icon: data.icon,
      };
      logoContainer.appendChild(window.renderAgencyLogo(agencyObj, 72));
    }

    // Agency explanation
    if (data.description_ar || data.description_en) {
      const expl = document.createElement("div");
      expl.className = "agency-alert agency-alert--info";
      expl.textContent = bi(data.description_ar, data.description_en);
      root.appendChild(expl);
    }

    // Report cards
    const list = document.createElement("ul");
    list.className = "agency-card-grid";
    list.setAttribute("role", "list");

    data.reports.forEach((report) => {
      const li = document.createElement("li");
      li.className = "agency-card agency-report-card";

      const h2 = document.createElement("h2");
      h2.textContent = lang === "en" ? report.title_en : report.title_ar;

      const reportDesc = document.createElement("p");
      reportDesc.className = "agency-card-desc";
      reportDesc.textContent = bi(report.description_ar, report.description_en) || "";

      const indicators = document.createElement("p");
      indicators.className = "agency-card-meta";
      const _srcAr =
        report.data_sources_ar && report.data_sources_ar.length
          ? report.data_sources_ar.join("، ")
          : null;
      const _srcEn =
        report.data_sources && report.data_sources.length
          ? report.data_sources.join(", ")
          : null;
      const _sourcesText =
        lang === "ar" ? _srcAr || _srcEn || "—" : _srcEn || _srcAr || "—";
      indicators.innerHTML =
        "<strong>" +
        t("المؤشرات المتاحة", "Available indicators") +
        ":</strong> " +
        _sourcesText;

      const updated = document.createElement("p");
      updated.className = "agency-card-updated";
      const reportUpdated = report.generated_at || data.generated_at;
      updated.innerHTML =
        '<i class="bi bi-clock" aria-hidden="true"></i> ' +
        t("آخر تحديث", "Last updated") +
        ": " +
        (reportUpdated
          ? new Date(reportUpdated).toLocaleString(LOCALE, {
              dateStyle: "medium",
              timeStyle: "short",
            })
          : "—");

      const usage = document.createElement("p");
      usage.className = "agency-card-usage";
      usage.innerHTML =
        "<strong>" +
        t("كيفية الاستخدام", "How to use") +
        ":</strong> " +
        t(
          "اختر فترة تجميع البيانات. استخدم الفلاتر لتحديد النطاق الجغرافي. راجع النتائج وصدّرها عند الحاجة.",
          "Select a data aggregation period. Use filters to define the geographic scope. Review results and export when needed.",
        );

      const statusRow = document.createElement("div");
      statusRow.className = "agency-card-meta";
      statusRow.appendChild(statusBadge(report.status));
      if (report.status !== "ready" && report.reason_ar) {
        const reason = document.createElement("span");
        reason.className = "agency-card-reason";
        reason.textContent = bi(report.reason_ar, report.reason_en);
        statusRow.appendChild(reason);
      }

      const link = document.createElement("a");
      link.className =
        "admin-btn admin-btn-primary agency-card-btn" +
        (report.status !== "ready" ? " disabled" : "");
      link.href =
        "/admin/agency-reports/" +
        encodeURIComponent(data.agency_code) +
        "/" +
        encodeURIComponent(report.report_code) +
        (report._dateSuffix || "");
      link.textContent = t("فتح التقرير", "Open Report");
      if (report.status !== "ready") {
        link.setAttribute("aria-disabled", "true");
        link.setAttribute("tabindex", "-1");
      }

      li.append(h2, reportDesc, indicators, updated, usage, statusRow, link);
      list.appendChild(li);
    });

    if (!data.reports.length) {
      const empty = document.createElement("div");
      empty.className = "agency-alert";
      empty.textContent = t(
        "لا توجد تقارير جاهزة حالياً. يرجى استكمال البيانات المطلوبة أو مراجعة إعدادات التكامل.",
        "No reports available currently. Please complete required data or review integration settings.",
      );
      root.appendChild(empty);
    } else {
      root.appendChild(list);
    }
  }

  function renderSortablePaginatedTable(container, payload) {
    const rawRows = payload.breakdowns || [];
    if (!rawRows.length) return;

    let rows = [...rawRows];
    let sortKey = "";
    let sortOrder = "asc";
    let currentPage = 1;
    const rowsPerPage = 10;

    const tableTitle = document.createElement("h2");
    tableTitle.id = "agency-table-title";
    tableTitle.textContent = t("جدول البيانات التجميعية", "Aggregated Data Table");
    container.appendChild(tableTitle);

    const tableWrapper = document.createElement("div");
    tableWrapper.style.overflowX = "auto";
    tableWrapper.style.maxHeight = "450px";
    tableWrapper.style.position = "relative";
    tableWrapper.style.border = "1px solid var(--admin-border, #e2e8f0)";
    tableWrapper.style.borderRadius = "12px";

    const table = document.createElement("table");
    table.className = "agency-table";
    table.style.width = "100%";
    table.style.border = "none";

    const caption = document.createElement("caption");
    caption.textContent = bi(payload.metadata.report_title_ar, payload.metadata.report_title_en) || "";
    table.appendChild(caption);

    const columnLabels = payload.column_labels || {};
    const headers = Object.keys(rows[0]);

    const thead = document.createElement("thead");
    const tr = document.createElement("tr");
    headers.forEach((h) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.style.position = "sticky";
      th.style.top = "0";
      th.style.backgroundColor = "#f8fafc";
      th.style.zIndex = "2";
      th.style.cursor = "pointer";
      th.style.userSelect = "none";
      th.style.borderBottom = "2px solid var(--admin-border, #e2e8f0)";
      
      const textSpan = document.createElement("span");
      textSpan.textContent = pick(columnLabels[h]) || h;
      th.appendChild(textSpan);

      const iconSpan = document.createElement("span");
      iconSpan.style.marginInlineStart = "6px";
      iconSpan.style.fontSize = "0.75rem";
      iconSpan.innerHTML = '<i class="bi bi-arrow-down-up text-muted"></i>';
      th.appendChild(iconSpan);

      th.addEventListener("click", () => {
        if (sortKey === h) {
          sortOrder = sortOrder === "asc" ? "desc" : "asc";
        } else {
          sortKey = h;
          sortOrder = "asc";
        }
        Array.from(tr.children).forEach((child, idx) => {
          const key = headers[idx];
          const icon = child.querySelector("span:last-child");
          if (key === sortKey) {
            icon.innerHTML = sortOrder === "asc" 
              ? '<i class="bi bi-sort-up text-primary"></i>' 
              : '<i class="bi bi-sort-down text-primary"></i>';
          } else {
            icon.innerHTML = '<i class="bi bi-arrow-down-up text-muted"></i>';
          }
        });
        sortAndRender();
      });

      tr.appendChild(th);
    });
    thead.appendChild(tr);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    table.appendChild(tbody);

    const totalRow = payload.total_row;
    let tfoot;
    if (totalRow) {
      tfoot = document.createElement("tfoot");
      const ftr = document.createElement("tr");
      ftr.className = "agency-table-total";
      ftr.style.position = "sticky";
      ftr.style.bottom = "0";
      ftr.style.backgroundColor = "#f8fafc";
      ftr.style.zIndex = "2";
      ftr.style.borderTop = "2px solid var(--admin-border, #e2e8f0)";
      headers.forEach((h) => {
        const td = document.createElement("td");
        const v = totalRow[h];
        const dispTotal = pick(v);
        td.textContent = dispTotal == null || dispTotal === "" ? "" : String(dispTotal);
        const isNumeric = typeof v === "number" || (!isNaN(v) && v !== "");
        if (isNumeric) {
          td.style.textAlign = "right";
          td.style.fontVariantNumeric = "tabular-nums";
        }
        ftr.appendChild(td);
      });
      tfoot.appendChild(ftr);
      table.appendChild(tfoot);
    }

    tableWrapper.appendChild(table);
    container.appendChild(tableWrapper);

    const paginationContainer = document.createElement("div");
    paginationContainer.style.display = "flex";
    paginationContainer.style.alignItems = "center";
    paginationContainer.style.justifyContent = "space-between";
    paginationContainer.style.marginTop = "14px";
    paginationContainer.style.gap = "10px";
    container.appendChild(paginationContainer);

    function sortAndRender() {
      if (sortKey) {
        rows.sort((a, b) => {
          const valA = a[sortKey];
          const valB = b[sortKey];
          if (typeof valA === "number" && typeof valB === "number") {
            return sortOrder === "asc" ? valA - valB : valB - valA;
          }
          const strA = String(valA || "");
          const strB = String(valB || "");
          return sortOrder === "asc" 
            ? strA.localeCompare(strB, "ar") 
            : strB.localeCompare(strA, "ar");
        });
      }
      renderBody();
    }

    function renderBody() {
      tbody.innerHTML = "";
      const startIdx = (currentPage - 1) * rowsPerPage;
      const endIdx = startIdx + rowsPerPage;
      const pageRows = rows.slice(startIdx, endIdx);

      pageRows.forEach((row, index) => {
        const r = document.createElement("tr");
        if (index % 2 === 1) {
          r.style.backgroundColor = "#f8fafc";
        }
        headers.forEach((h) => {
          const td = document.createElement("td");
          const v = row[h];
          const disp = pick(v);
          td.textContent = disp == null ? "—" : String(disp);
          const isNumeric = typeof v === "number" || (!isNaN(v) && v !== "");
          if (isNumeric) {
            td.style.textAlign = "right";
            td.style.fontVariantNumeric = "tabular-nums";
          }
          r.appendChild(td);
        });
        tbody.appendChild(r);
      });

      renderPagination();
    }

    function renderPagination() {
      paginationContainer.innerHTML = "";
      const totalPages = Math.ceil(rows.length / rowsPerPage);
      if (totalPages <= 1) return;

      const infoSpan = document.createElement("span");
      infoSpan.className = "small text-muted";
      infoSpan.textContent = t(
        `الصفحة ${currentPage} من ${totalPages} (إجمالي ${rows.length} سجل)`,
        `Page ${currentPage} of ${totalPages} (Total ${rows.length} records)`
      );
      paginationContainer.appendChild(infoSpan);

      const btnGroup = document.createElement("div");
      btnGroup.style.display = "flex";
      btnGroup.style.gap = "6px";

      const prevBtn = document.createElement("button");
      prevBtn.type = "button";
      prevBtn.className = "admin-btn admin-btn-secondary admin-btn-sm";
      prevBtn.textContent = t("السابق", "Previous");
      prevBtn.disabled = currentPage === 1;
      prevBtn.addEventListener("click", () => {
        if (currentPage > 1) {
          currentPage--;
          renderBody();
        }
      });

      const nextBtn = document.createElement("button");
      nextBtn.type = "button";
      nextBtn.className = "admin-btn admin-btn-secondary admin-btn-sm";
      nextBtn.textContent = t("التالي", "Next");
      nextBtn.disabled = currentPage === totalPages;
      nextBtn.addEventListener("click", () => {
        if (currentPage < totalPages) {
          currentPage++;
          renderBody();
        }
      });

      btnGroup.appendChild(prevBtn);
      btnGroup.appendChild(nextBtn);
      paginationContainer.appendChild(btnGroup);
    }

    renderBody();
  }

  function renderReport(payload) {
    clear(root);

    // Populate breadcrumbs and header
    const titleEl = document.getElementById("agency-report-title");
    if (titleEl)
      titleEl.textContent =
        lang === "en"
          ? payload.metadata.report_title_en
          : payload.metadata.report_title_ar;
    const descEl = document.getElementById("agency-report-description");
    if (descEl) descEl.textContent = bi(payload.metadata.description_ar, payload.metadata.description_en) || "";
    const breadcrumbAgency = document.getElementById("breadcrumb-agency-name");
    if (breadcrumbAgency) {
      breadcrumbAgency.textContent =
        bi(payload.metadata.agency_name_ar, payload.metadata.agency_name_en) || payload.metadata.agency_code;
      breadcrumbAgency.href =
        "/admin/agency-reports/" +
        encodeURIComponent(payload.metadata.agency_code);
    }
    const breadcrumbReport = document.getElementById("breadcrumb-report-name");
    if (breadcrumbReport)
      breadcrumbReport.textContent =
        bi(payload.metadata.report_title_ar, payload.metadata.report_title_en) || payload.metadata.report_code;

    // Drill-down breadcrumb
    const drill = window.__agencyDrillDown || {};
    const drillBc = document.getElementById("agency-drill-breadcrumb");
    if (drillBc) {
      if (
        drill.governorate ||
        drill.city ||
        drill.district ||
        drill.kindergarten_id ||
        drill.period ||
        drill.year ||
        drill.quarter
      ) {
        drillBc.classList.remove("d-none");
        const label = document.getElementById("agency-drill-label");
        if (label) {
          const parts = [];
          if (drill.governorate)
            parts.push(
              t("المحافظة:", "Governorate:") + " " + drill.governorate,
            );
          if (drill.city) parts.push(t("المدينة:", "City:") + " " + drill.city);
          if (drill.district)
            parts.push(t("اللواء:", "District:") + " " + drill.district);
          if (drill.kindergarten_id)
            parts.push(
              t("الحضانة:", "Kindergarten:") + " #" + drill.kindergarten_id,
            );
          if (drill.period)
            parts.push(t("الفترة:", "Period:") + " " + drill.period);
          if (drill.year) parts.push(t("السنة:", "Year:") + " " + drill.year);
          if (drill.quarter)
            parts.push(t("الربع:", "Quarter:") + " " + drill.quarter);
          label.textContent = parts.join(" › ");
        }
      } else {
        drillBc.classList.add("d-none");
      }
    }

    // Agency logo in report header
    const logoEl = document.getElementById("report-agency-logo");
    if (logoEl && window.renderAgencyLogo) {
      const agencyObj = {
        code: payload.metadata.agency_code,
        name_ar: payload.metadata.agency_name_ar,
        name_en: payload.metadata.agency_name_en,
      };
      logoEl.appendChild(window.renderAgencyLogo(agencyObj, 72));
    }

    // Data quality badge
    const dqEl = document.getElementById("agency-data-quality-badge");
    if (dqEl && payload.metadata.data_quality_status) {
      const dqMap = {
        sufficient: {
          ar: "مؤشر جودة البيانات: كافٍ",
          en: "Data quality: sufficient",
          cls: "success",
        },
        partial: {
          ar: "مؤشر جودة البيانات: جزئي",
          en: "Data quality: partial",
          cls: "warning",
        },
        limited: {
          ar: "مؤشر جودة البيانات: محدود",
          en: "Data quality: limited",
          cls: "warning",
        },
        incomplete: {
          ar: "مؤشر جودة البيانات: غير مكتمل",
          en: "Data quality: incomplete",
          cls: "danger",
        },
      };
      const dq = dqMap[payload.metadata.data_quality_status] || {
        ar: "مؤشر جودة البيانات: " + payload.metadata.data_quality_status,
        en: "Data quality: " + payload.metadata.data_quality_status,
        cls: "default",
      };
      dqEl.className = "agency-dq-badge agency-dq-badge--" + dq.cls;
      dqEl.innerHTML =
        '<i class="bi bi-activity" aria-hidden="true"></i> ' + t(dq.ar, dq.en);
    }

    // Executive summary
    const summary = document.createElement("section");
    summary.className = "agency-report-summary";
    summary.setAttribute("aria-labelledby", "agency-summary-title");
    const sumH2 = document.createElement("h2");
    sumH2.id = "agency-summary-title";
    sumH2.textContent = t("ملخص النتائج", "Results Summary");
    const dl = document.createElement("dl");
    const summaryLabels = payload.summary_labels || {};
    Object.entries(payload.summary || {}).forEach(([key, value]) => {
      if (key === "message_ar" || key === "data_quality_note_ar" || key === "interpretation_ar" || key === "decision_implications" || key === "required_age" || key === "last_eligible_birth_date" || key === "cutoff_date" || key === "admission_year") return;
      const dt = document.createElement("dt");
      dt.textContent = pick(summaryLabels[key]) || key;
      const dd = document.createElement("dd");
      dd.textContent = value == null ? "—" : String(value);
      dl.append(dt, dd);
    });
    summary.append(sumH2, dl);
    root.appendChild(summary);

    if (
      payload.unavailable_indicators &&
      payload.unavailable_indicators.length
    ) {
      const alert = document.createElement("div");
      alert.className = "agency-alert agency-alert--warning";
      alert.textContent =
        (lang === "en" ? (payload.summary.message_en || payload.summary.message_ar) : payload.summary.message_ar) ||
        t(
          "هذا التقرير يتطلب بيانات منظمة إضافية.",
          "This report requires additional structured data.",
        );
      root.appendChild(alert);
      return;
    }

    // Chart placeholder (if chart data provided)
    if (payload.chart) {
      const chartSection = document.createElement("div");
      chartSection.className = "agency-chart-section";
      const chartTitle = document.createElement("h2");
      chartTitle.className = "agency-chart-title";
      chartTitle.textContent =
        bi(payload.chart.title_ar, payload.chart.title_en) || t("الرسم البياني", "Chart");
      chartSection.appendChild(chartTitle);
      const chartContainer = document.createElement("div");
      chartContainer.id = "agency-plotly-chart";
      chartContainer.setAttribute("role", "img");
      chartContainer.setAttribute("aria-label", bi(payload.chart.title_ar, payload.chart.title_en) || "");
      chartSection.appendChild(chartContainer);
      if (
        window.Plotly &&
        typeof window.Plotly.newPlot === "function" &&
        payload.chart.series &&
        payload.chart.series.length
      ) {
        const labels = payload.chart.series.map((s) => s.label);
        const values = payload.chart.series.map((s) => s.value);
        const colors = payload.chart.series.map((s) => s.color || null);
        const hasSeriesColors = colors.some((c) => typeof c === "string" && c);
        const sharePcts = payload.chart.series.map((s) =>
          typeof s.share_pct === "number" ? s.share_pct : null,
        );
        const total = values.reduce(
          (a, b) => a + (typeof b === "number" ? b : 0),
          0,
        );
        const exportBtn = document.createElement("button");
        exportBtn.type = "button";
        exportBtn.className =
          "admin-btn admin-btn-secondary agency-chart-export-btn";
        exportBtn.innerHTML =
          '<i class="bi bi-image" aria-hidden="true"></i> ' +
          t("تصدير الرسم البياني", "Export Chart");
        exportBtn.disabled = true;
        exportBtn.setAttribute("aria-disabled", "true");
        exportBtn.setAttribute("aria-live", "polite");
        exportBtn.setAttribute(
          "aria-label",
          t(
            "تصدير الرسم البياني كصورة",
            "Export the current chart as an image",
          ),
        );
        const chartStatus = document.createElement("div");
        chartStatus.className = "visually-hidden";
        chartStatus.setAttribute("aria-live", "polite");
        chartStatus.id = "agency-chart-export-status";
        exportBtn.addEventListener("click", function () {
          if (
            !window.Plotly ||
            !chartContainer.__chartReady ||
            exportBtn.classList.contains("is-loading")
          )
            return;
          exportBtn.disabled = true;
          exportBtn.classList.add("is-loading");
          chartStatus.textContent = t(
            "جارٍ تجهيز ملف الصورة...",
            "Preparing chart image...",
          );
          window.Plotly.toImage(chartContainer, {
            format: "png",
            height: 600,
            width: 900,
            scale: 2,
          })
            .then((dataUrl) => {
              const link = document.createElement("a");
              const generatedAt =
                payload.metadata.generated_at || payload.metadata.created_at;
              const dateStr = formatDateForFilename(generatedAt);
              link.href = dataUrl;
              link.download =
                (payload.metadata.report_code || "report") +
                "_chart_" +
                dateStr +
                ".png";
              link.click();
              exportBtn.disabled = false;
              exportBtn.classList.remove("is-loading");
              chartStatus.textContent = t(
                "تم تنزيل الرسم البياني.",
                "Chart downloaded.",
              );
              chartStatus.focus();
            })
            .catch(() => {
              exportBtn.disabled = false;
              exportBtn.classList.remove("is-loading");
              chartStatus.textContent = t(
                "تعذر تصدير الرسم البياني.",
                "Unable to export chart.",
              );
              alert(
                t(
                  "تعذر تصدير الرسم البياني. يرجى المحاولة مرة أخرى.",
                  "Unable to export chart. Please try again.",
                ),
              );
            });
        });
        chartSection.appendChild(chartStatus);
        chartSection.appendChild(exportBtn);
        root.appendChild(chartSection);

        const isPie = payload.chart.type === "pie";
        const isVerticalBar =
          !isPie && payload.chart.orientation === "vertical";
        const showSharePct =
          !isPie &&
          payload.chart.show_share_pct === true &&
          sharePcts.some((v) => typeof v === "number");
        const rawSuffix = payload.chart.value_suffix;
        const valueSuffix = isPie
          ? ""
          : rawSuffix == null
            ? (isVerticalBar ? "" : "")
            : typeof rawSuffix === "object"
              ? bi(rawSuffix.ar, rawSuffix.en)
              : rawSuffix;
        const barText = values.map((v, idx) => {
          if (typeof v !== "number") return "";
          if (showSharePct && typeof sharePcts[idx] === "number") {
            return `${v}${valueSuffix} (${sharePcts[idx]}%)`;
          }
          return `${v}${valueSuffix}`;
        });

        const plotData = [
          {
            type: isPie ? "pie" : "bar",
            name: bi(payload.chart.title_ar, payload.chart.title_en) || "",
            ...(isPie
              ? { labels, values }
              : isVerticalBar
                ? { x: labels, y: values }
                : { x: values, y: labels, orientation: "h" }),
            ...(isPie
              ? {}
              : {
                  customdata: sharePcts,
                  text: barText,
                  textposition: "outside",
                  cliponaxis: false,
                  marker: {
                    color: hasSeriesColors ? colors : undefined,
                    line: { color: "rgba(15, 23, 42, 0.15)", width: 1 },
                  },
                }),
            textinfo: isPie ? "label+percent" : "value",
            hovertemplate: isPie
              ? "%{label}: %{value} (%{percent:.1%})<extra></extra>"
              : isVerticalBar
                ? showSharePct
                  ? "%{x}: %{y}" +
                    valueSuffix +
                    " (%{customdata:.1f}%)<extra></extra>"
                  : "%{x}: %{y}" + valueSuffix + "<extra></extra>"
                : showSharePct
                  ? "%{y}: %{x}" +
                    valueSuffix +
                    " (%{customdata:.1f}%)<extra></extra>"
                  : "%{y}: %{x}" + valueSuffix + "<extra></extra>",
          },
        ];
        const layout = {
          margin: { l: 80, r: 30, t: 40, b: 80 },
          height: !isPie ? Math.max(360, labels.length * 36) : 460,
          paper_bgcolor: "transparent",
          plot_bgcolor: "transparent",
          font: { family: "'Inter', 'Segoe UI', system-ui, sans-serif" },
          title: {
            text: bi(payload.chart.title_ar, payload.chart.title_en) || "",
          },
          uniformtext: !isPie ? { mode: "hide", minsize: 11 } : undefined,
          bargap: !isPie ? 0.3 : undefined,
          xaxis: !isPie
            ? isVerticalBar
              ? {
                  tickfont: { size: 13 },
                  automargin: true,
                  title: bi(payload.chart.x_axis_title_ar, payload.chart.x_axis_title_en) || undefined,
                }
              : {
                  tickfont: { size: 13 },
                  zeroline: false,
                  gridcolor: "rgba(148, 163, 184, 0.25)",
                  title: bi(payload.chart.x_axis_title_ar, payload.chart.x_axis_title_en) || undefined,
                }
            : undefined,
          yaxis: !isPie
            ? isVerticalBar
              ? {
                  tickfont: { size: 13 },
                  zeroline: false,
                  gridcolor: "rgba(148, 163, 184, 0.25)",
                  rangemode: "tozero",
                  ticksuffix: valueSuffix,
                  title: bi(payload.chart.y_axis_title_ar, payload.chart.y_axis_title_en) || undefined,
                }
              : {
                  tickfont: { size: 13 },
                  automargin: true,
                  title: bi(payload.chart.y_axis_title_ar, payload.chart.y_axis_title_en) || undefined,
                }
            : undefined,
        };
        const config = {
          displaylogo: false,
          responsive: true,
          displayModeBar: true,
          modeBarButtonsToRemove: ["lasso2d", "select2d"],
          locale: lang === "ar" ? "ar" : "en",
        };
        window.Plotly.newPlot(chartContainer, plotData, layout, config)
          .then(() => {
            chartContainer.__chartReady = true;
            exportBtn.disabled = false;
            exportBtn.removeAttribute("aria-disabled");
            attachChartDrillDown(chartContainer, payload);
          })
          .catch(() => {
            chartContainer.remove();
            chartSection.appendChild(
              document.createTextNode(
                t("تعذر عرض الرسم البياني.", "Unable to render chart."),
              ),
            );
          });
      } else {
        chartSection.appendChild(
          document.createTextNode(
            t("لا تتوفر بيانات للرسم البياني.", "No chart data available."),
          ),
        );
      }
      root.appendChild(chartSection);
    }

    // Render any extra charts (e.g., license status breakdown).
    if (payload.license_chart) {
      const extraSection = document.createElement("div");
      extraSection.className = "agency-chart-section";
      const extraTitle = document.createElement("h2");
      extraTitle.className = "agency-chart-title";
      extraTitle.textContent =
        bi(payload.license_chart.title_ar, payload.license_chart.title_en) || t("الرسم البياني", "Chart");
      extraSection.appendChild(extraTitle);
      const extraContainer = document.createElement("div");
      extraContainer.id = "agency-plotly-chart-license";
      extraContainer.setAttribute("role", "img");
      extraContainer.setAttribute(
        "aria-label",
        bi(payload.license_chart.title_ar, payload.license_chart.title_en) || "",
      );
      extraSection.appendChild(extraContainer);
      if (
        window.Plotly &&
        typeof window.Plotly.newPlot === "function" &&
        payload.license_chart.series &&
        payload.license_chart.series.length
      ) {
        const labels = payload.license_chart.series.map((s) => s.label);
        const values = payload.license_chart.series.map((s) => s.value);
        const plotData = [
          {
            type: "pie",
            name: bi(payload.license_chart.title_ar, payload.license_chart.title_en) || "",
            labels: labels,
            values: values,
            textinfo: "label+percent",
            hovertemplate: "%{label}: %{value} (%{percent:.1%})<extra></extra>",
          },
        ];
        const layout = {
          margin: { l: 80, r: 30, t: 40, b: 80 },
          height: 420,
          paper_bgcolor: "transparent",
          plot_bgcolor: "transparent",
          font: { family: "'Inter', 'Segoe UI', system-ui, sans-serif" },
          title: { text: bi(payload.license_chart.title_ar, payload.license_chart.title_en) || "" },
        };
        const config = {
          displaylogo: false,
          responsive: true,
          displayModeBar: true,
          modeBarButtonsToRemove: ["lasso2d", "select2d"],
          locale: lang === "ar" ? "ar" : "en",
        };
        window.Plotly.newPlot(extraContainer, plotData, layout, config).catch(
          () => {
            extraContainer.remove();
            extraSection.appendChild(
              document.createTextNode(
                t("تعذر عرض الرسم البياني.", "Unable to render chart."),
              ),
            );
          },
        );
      } else {
        extraSection.appendChild(
          document.createTextNode(
            t("لا تتوفر بيانات للرسم البياني.", "No chart data available."),
          ),
        );
      }

      // If both the main chart and the license chart exist, place them in a
      // responsive side-by-side grid so the page doesn't grow unnecessarily
      // tall on desktop.
      if (chartSection && chartSection.parentNode === root) {
        const grid = document.createElement("div");
        grid.className = "agency-charts-grid";
        root.insertBefore(grid, chartSection);
        root.removeChild(chartSection);
        grid.appendChild(chartSection);
        grid.appendChild(extraSection);
      } else {
        root.appendChild(extraSection);
      }
    }
    // Data table
    const rows = payload.breakdowns || [];
    if (rows.length) {
      const tableSection = document.createElement("section");
      tableSection.className = "agency-table-section";
      tableSection.setAttribute("aria-labelledby", "agency-table-title");
      
      renderSortablePaginatedTable(tableSection, payload);

      root.appendChild(tableSection);
      const groupBy = (payload.chart && payload.chart.group_by) || "";
      attachTableDrillDown(tableSection, groupBy);
    } else {
      const empty = document.createElement("div");
      empty.className = "agency-alert";
      empty.textContent = t(
        "لا توجد بيانات مطابقة للفلاتر المحددة. يرجى تعديل المحافظة أو اللواء أو المنطقة أو الفترة الزمنية.",
        "No matching data for the selected filters. Please adjust the governorate, district, area or time period.",
      );
      root.appendChild(empty);
    }

    // Render Interpretation and Decision support sections for kg2_eligibility
    if (payload.summary && payload.summary.interpretation_ar) {
      const interpretSec = document.createElement("section");
      interpretSec.className = "agency-report-interpretation";
      interpretSec.style.marginTop = "2rem";
      interpretSec.style.padding = "1.25rem";
      interpretSec.style.background = "var(--admin-surface, #fff)";
      interpretSec.style.border = "1px solid var(--admin-border, #d9dee6)";
      interpretSec.style.borderRadius = "12px";

      const ih = document.createElement("h2");
      ih.style.fontSize = "1.15rem";
      ih.style.marginBottom = "0.75rem";
      ih.textContent = t("ماذا تعني النتائج؟", "What do the results mean?");
      interpretSec.appendChild(ih);

      const ip = document.createElement("p");
      ip.style.fontSize = "0.95rem";
      ip.style.lineHeight = "1.6";
      ip.style.color = "var(--admin-text-muted, #5a6472)";
      ip.textContent = payload.summary.interpretation_ar;
      interpretSec.appendChild(ip);

      root.appendChild(interpretSec);
    }

    if (payload.summary && payload.summary.decision_implications) {
      const decisionSec = document.createElement("section");
      decisionSec.className = "agency-report-decisions";
      decisionSec.style.marginTop = "1.5rem";
      decisionSec.style.padding = "1.25rem";
      decisionSec.style.background = "var(--admin-surface, #fff)";
      decisionSec.style.border = "1px solid var(--admin-border, #d9dee6)";
      decisionSec.style.borderRadius = "12px";

      const dh = document.createElement("h2");
      dh.style.fontSize = "1.15rem";
      dh.style.marginBottom = "0.75rem";
      dh.textContent = t("دلالات النتائج لصانع القرار", "Decision Implications");
      decisionSec.appendChild(dh);

      const tableWrapper = document.createElement("div");
      tableWrapper.style.overflowX = "auto";

      const table = document.createElement("table");
      table.className = "admin-table";
      table.style.width = "100%";
      table.style.fontSize = "0.9rem";

      const thead = document.createElement("thead");
      thead.innerHTML = `<tr>
        <th style="text-align: right; padding: 8px;">${t("الملاحظة", "Observation")}</th>
        <th style="text-align: right; padding: 8px;">${t("الدليل", "Evidence")}</th>
        <th style="text-align: right; padding: 8px;">${t("الدلالة", "Implication")}</th>
        <th style="text-align: right; padding: 8px;">${t("الإجراء المقترح", "Suggested Action")}</th>
      </tr>`;
      table.appendChild(thead);

      const tbody = document.createElement("tbody");
      payload.summary.decision_implications.forEach(row => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td style="padding: 8px; border-bottom: 1px solid var(--admin-border, #d9dee6);">${row.observation || ""}</td>
          <td style="padding: 8px; border-bottom: 1px solid var(--admin-border, #d9dee6);">${row.evidence || ""}</td>
          <td style="padding: 8px; border-bottom: 1px solid var(--admin-border, #d9dee6);">${row.implication || ""}</td>
          <td style="padding: 8px; border-bottom: 1px solid var(--admin-border, #d9dee6);">${row.action || ""}</td>
        `;
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      tableWrapper.appendChild(table);
      decisionSec.appendChild(tableWrapper);

      root.appendChild(decisionSec);
    }

    // Methodology & provenance — standardized official-statistics practice: state
    // the definition, source, geographic basis, units, symbols and generation time
    // so figures can be trusted and interpreted without assumptions.
    const meta = payload.metadata || {};
    const provItems = [
      [t("تعريف التقرير", "Definition"), lang === "en" ? meta.definition_en : meta.definition_ar],
      [t("مصدر البيانات", "Data source"), lang === "en" ? meta.data_source_en : meta.data_source_ar],
      [t("الأساس الجغرافي", "Geographic basis"), lang === "en" ? meta.geography_basis_en : meta.geography_basis_ar],
      [t("ملاحظات جودة البيانات", "Data Quality Note"), payload.summary ? (lang === "en" ? (payload.summary.data_quality_note_en || payload.summary.data_quality_note_ar) : payload.summary.data_quality_note_ar) : null],
      [t("وحدات القياس", "Units"), lang === "en" ? meta.units_note_en : meta.units_note_en],
      [t("الرموز", "Symbols"), lang === "en" ? meta.symbols_note_en : meta.symbols_note_ar],
      [
        t("تاريخ الإصدار", "Generated"),
        meta.generated_at
          ? new Date(meta.generated_at).toLocaleString(LOCALE, {
              dateStyle: "medium",
              timeStyle: "short",
            })
          : null,
      ],
    ].filter(function (p) {
      return p[1];
    });
    if (provItems.length) {
      const prov = document.createElement("section");
      prov.className = "agency-provenance";
      prov.setAttribute("aria-labelledby", "agency-prov-title");
      const ph = document.createElement("h2");
      ph.id = "agency-prov-title";
      ph.textContent = t(
        "معلومات ومنهجية التقرير",
        "Report information & methodology",
      );
      prov.appendChild(ph);
      const pdl = document.createElement("dl");
      pdl.className = "agency-provenance-list";
      provItems.forEach(function (p) {
        const dt = document.createElement("dt");
        dt.textContent = p[0];
        const dd = document.createElement("dd");
        dd.textContent = p[1];
        pdl.appendChild(dt);
        pdl.appendChild(dd);
      });
      prov.appendChild(pdl);
      root.appendChild(prov);
    }

    // Export & Actions toolbar — CSV, JSON, Print/PDF, and Copy Summary
    const exports = document.createElement("div");
    exports.className = "agency-export-actions d-flex flex-wrap gap-2 align-items-center mt-4";
    const base =
      "/api/admin/agency-reports/" +
      encodeURIComponent(payload.metadata.agency_code) +
      "/reports/" +
      encodeURIComponent(payload.metadata.report_code);
    const dateStr = new Date().toISOString().slice(0, 10);

    if (payload.exports && payload.exports.csv) {
      const a = document.createElement("a");
      a.href = base + "/export.csv" + window.location.search;
      a.className = "admin-btn admin-btn-secondary";
      a.download = (payload.metadata.report_code || "report") + "_" + dateStr + ".csv";
      a.innerHTML =
        '<i class="bi bi-file-earmark-spreadsheet me-1" aria-hidden="true"></i> ' +
        t("تصدير CSV", "Export CSV");
      exports.appendChild(a);
    }

    if (payload.exports && payload.exports.json) {
      const aJson = document.createElement("a");
      aJson.href = base + "/export.json" + window.location.search;
      aJson.className = "admin-btn admin-btn-secondary";
      aJson.download = (payload.metadata.report_code || "report") + "_" + dateStr + ".json";
      aJson.innerHTML =
        '<i class="bi bi-file-earmark-code me-1" aria-hidden="true"></i> ' +
        t("تصدير JSON", "Export JSON");
      exports.appendChild(aJson);
    }

    const printBtn = document.createElement("button");
    printBtn.type = "button";
    printBtn.className = "admin-btn admin-btn-secondary";
    printBtn.innerHTML =
      '<i class="bi bi-printer me-1" aria-hidden="true"></i> ' +
      t("طباعة / PDF", "Print / PDF");
    printBtn.onclick = function () {
      window.print();
    };
    exports.appendChild(printBtn);

    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "admin-btn admin-btn-secondary";
    copyBtn.innerHTML =
      '<i class="bi bi-clipboard me-1" aria-hidden="true"></i> ' +
      t("نسخ الملخص", "Copy Summary");
    copyBtn.onclick = function () {
      let text = (payload.metadata ? (lang === "en" ? payload.metadata.title_en : payload.metadata.title_ar) || "" : "") + "\n";
      if (payload.kpis && payload.kpis.length) {
        text += payload.kpis.map(function (k) { return (k.title || k.label || "") + ": " + (k.value !== undefined ? k.value : ""); }).join(" | ");
      }
      navigator.clipboard.writeText(text).then(function () {
        if (window.AdminComponents && typeof window.AdminComponents.showNotification === "function") {
          window.AdminComponents.showNotification({ type: "success", title: "", message: t("تم نسخ الملخص بنجاح", "Summary copied to clipboard") });
        }
      });
    };
    exports.appendChild(copyBtn);

    root.appendChild(exports);
  }

  function loadReport() {
    const agencyCode = page.dataset.agencyCode;
    const reportCode = page.dataset.reportCode;
    const form = document.getElementById("agency-report-filters");
    const formData = form ? new FormData(form) : new FormData();
    const params = new URLSearchParams();
    formData.forEach((v, k) => {
      if (v && v.trim()) params.set(k, v.trim());
    });

    const drill = window.__agencyDrillDown || {};
    [
      "governorate",
      "city",
      "district",
      "kindergarten_id",
      "status",
      "severity",
      "role",
      "gender",
      "period",
      "year",
      "quarter",
    ].forEach((k) => {
      const v = drill[k];
      if (v !== undefined && v !== null && String(v).trim() !== "") {
        params.set(k, String(v));
      }
    });

    const query = params.toString();
    const url =
      "/api/admin/agency-reports/" +
      encodeURIComponent(agencyCode) +
      "/reports/" +
      encodeURIComponent(reportCode) +
      (query ? "?" + query : "");

    if (root) {
      root.innerHTML = `
        <div class="agency-loading-skeleton" role="status" aria-label="${t("جاري تحميل البيانات...", "Loading data...")}">
          <div class="agency-kpi-grid agency-card--skeleton" style="margin-bottom: 24px;">
            <div class="agency-kpi"><div class="sk sk-logo" style="width: 48px; height: 48px; border-radius: 12px;"></div><div class="agency-kpi__body" style="flex: 1; margin-inline-start: 14px;"><div class="sk sk-title" style="height: 18px; width: 60%; margin-bottom: 8px;"></div><div class="sk sk-line" style="height: 14px; width: 40%;"></div></div></div>
            <div class="agency-kpi"><div class="sk sk-logo" style="width: 48px; height: 48px; border-radius: 12px;"></div><div class="agency-kpi__body" style="flex: 1; margin-inline-start: 14px;"><div class="sk sk-title" style="height: 18px; width: 60%; margin-bottom: 8px;"></div><div class="sk sk-line" style="height: 14px; width: 40%;"></div></div></div>
          </div>
          <div class="agency-charts-grid" style="margin-bottom: 24px;">
            <div class="agency-chart-section agency-card--skeleton" style="flex: 1; padding: 24px;">
              <div class="sk sk-title" style="height: 20px; width: 40%; margin-bottom: 16px;"></div>
              <div class="sk" style="height: 300px; width: 100%; border-radius: 12px;"></div>
            </div>
            <div class="agency-chart-section agency-card--skeleton" style="flex: 1; padding: 24px;">
              <div class="sk sk-title" style="height: 20px; width: 40%; margin-bottom: 16px;"></div>
              <div class="sk" style="height: 300px; width: 100%; border-radius: 12px;"></div>
            </div>
          </div>
        </div>
      `;
    }

    api(url)
      .then(renderReport)
      .catch((err) => {
        console.error("Agency report load error:", err);
        if (root) {
          const is403 = err && err.message && err.message.includes("403");
          const msg = is403
            ? t("خطأ في الصلاحيات: يتطلب عرض هذا التقرير حساب مدير النظام (Admin).", "Permission error: This report requires Admin account privileges.")
            : t("تعذر تحميل التقرير. يرجى المحاولة مرة أخرى أو التواصل مع مسؤول النظام.", "Unable to load the report. Please try again or contact the system administrator.");
          root.innerHTML =
            '<div class="agency-alert agency-alert--error"><i class="bi bi-exclamation-circle" aria-hidden="true"></i> ' +
            msg +
            '</div>';
        }
      });
  }

  // -------- Tabs (ARIA tablist) --------
  function activateTab(tabId) {
    const tabs = Array.prototype.slice.call(
      document.querySelectorAll('.agency-tab[role="tab"]'),
    );
    tabs.forEach((tab) => {
      const selected = tab.id === tabId;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      const panel = document.getElementById(tab.getAttribute("aria-controls"));
      if (panel) panel.hidden = !selected;
    });
  }

  function initTabs() {
    const tabs = Array.prototype.slice.call(
      document.querySelectorAll('.agency-tab[role="tab"]'),
    );
    if (!tabs.length) return;
    tabs.forEach((tab, idx) => {
      tab.addEventListener("click", () => {
        activateTab(tab.id);
        tab.focus();
      });
      tab.addEventListener("keydown", (e) => {
        let target = null;
        if (e.key === "ArrowLeft")
          target = tabs[(idx + 1) % tabs.length]; // RTL: left = next
        else if (e.key === "ArrowRight")
          target = tabs[(idx - 1 + tabs.length) % tabs.length];
        else if (e.key === "Home") target = tabs[0];
        else if (e.key === "End") target = tabs[tabs.length - 1];
        if (target) {
          e.preventDefault();
          activateTab(target.id);
          target.focus();
        }
      });
    });
  }

  // -------- Drill-down ---------------------------------------------------
  function initDrillDown() {
    const resetBtn = document.getElementById("agency-drill-reset");
    if (resetBtn) {
      resetBtn.addEventListener("click", () => {
        window.__agencyDrillDown = {};
        const url = new URL(window.location.href);
        url.search = "";
        window.history.replaceState({}, "", url.toString());
        loadReport();
      });
    }
  }

  function attachChartDrillDown(chartContainer, payload) {
    if (!chartContainer || !window.Plotly) return;
    const groupBy = payload.chart.group_by || "";
    const supportedGroupBy = new Set([
      "governorate",
      "city",
      "status",
      "severity",
      "role",
      "gender",
      "period",
      "year",
      "quarter",
    ]);
    if (!supportedGroupBy.has(groupBy)) return; // No drill-down for unmapped dimensions.
    chartContainer.on("plotly_click", (eventData) => {
      if (!eventData || !eventData.points || !eventData.points.length) return;
      const pt = eventData.points[0];
      const series = Array.isArray(payload.chart?.series)
        ? payload.chart.series
        : [];
      const pointIndex = Number.isInteger(pt.pointNumber) ? pt.pointNumber : -1;
      const seriesItem = pointIndex >= 0 ? series[pointIndex] : null;
      const clickedCategory =
        seriesItem?.drill_value ??
        pt.label ??
        (typeof pt.y === "string" ? pt.y : null) ??
        (typeof pt.x === "string" ? pt.x : null) ??
        "";
      const drill = Object.assign({}, window.__agencyDrillDown);
      if (groupBy === "governorate") drill.governorate = clickedCategory;
      else if (groupBy === "city") drill.city = clickedCategory;
      else if (groupBy === "status") drill.status = clickedCategory;
      else if (groupBy === "severity") drill.severity = clickedCategory;
      else if (groupBy === "role") drill.role = clickedCategory;
      else if (groupBy === "gender") drill.gender = clickedCategory;
      else if (groupBy === "period") drill.period = clickedCategory;
      else if (groupBy === "year") drill.year = clickedCategory;
      else if (groupBy === "quarter") drill.quarter = clickedCategory;
      if (Object.keys(drill).length) {
        window.__agencyDrillDown = drill;
        const url = new URL(window.location.href);
        Object.entries(drill).forEach(([k, v]) => url.searchParams.set(k, v));
        window.history.replaceState({}, "", url.toString());
        loadReport();
      }
    });
  }

  function attachTableDrillDown(tableSection, groupBy) {
    if (!tableSection) return;
    const supportedGroupBy = new Set([
      "governorate",
      "city",
      "status",
      "severity",
      "role",
      "gender",
      "period",
      "year",
      "quarter",
    ]);
    if (!supportedGroupBy.has(groupBy)) return; // No drill-down for unmapped dimensions.
    const rows = tableSection.querySelectorAll(".agency-table tbody tr");
    rows.forEach((row) => {
      row.style.cursor = "pointer";
      row.setAttribute("tabindex", "0");
      row.setAttribute("role", "button");
      const cells = row.querySelectorAll("td");
      if (!cells.length) return;
      const drill = Object.assign({}, window.__agencyDrillDown);
      const colIdxByGroup = {
        governorate: 0,
        city: 0,
        status: 0,
        severity: 0,
        role: 0,
        gender: 0,
        period: 0,
        year: 1,
        quarter: 2,
      };
      const cellVal = cells[colIdxByGroup[groupBy]]?.textContent?.trim() || "";
      if (groupBy === "governorate") drill.governorate = cellVal;
      else if (groupBy === "city") drill.city = cellVal;
      else if (groupBy === "status") drill.status = cellVal;
      else if (groupBy === "severity") drill.severity = cellVal;
      else if (groupBy === "role") drill.role = cellVal;
      else if (groupBy === "gender") drill.gender = cellVal;
      else if (groupBy === "period") drill.period = cellVal;
      else if (groupBy === "year") drill.year = cellVal;
      else if (groupBy === "quarter") drill.quarter = cellVal;
      const activate = () => {
        if (!Object.keys(drill).length) return;
        window.__agencyDrillDown = drill;
        const url = new URL(window.location.href);
        Object.entries(drill).forEach(([k, v]) => url.searchParams.set(k, v));
        window.history.replaceState({}, "", url.toString());
        loadReport();
      };
      row.addEventListener("click", activate);
      row.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          activate();
        }
      });
    });
  }
  function initDrawer() {
    const dlg = document.getElementById("usage-guide-dialog");
    const openBtn = document.getElementById("open-usage-guide");
    const closeBtn = document.getElementById("close-usage-guide");
    if (!dlg || !openBtn) return;
    openBtn.addEventListener("click", () => {
      if (typeof dlg.showModal === "function") dlg.showModal();
      else dlg.setAttribute("open", "");
    });
    if (closeBtn) closeBtn.addEventListener("click", () => dlg.close());
    dlg.addEventListener("click", (e) => {
      if (e.target === dlg) dlg.close();
    });
  }

  const type = page.dataset.agencyReportsPage;

  if (type === "index") {
    initTabs();
    initDrawer();
    const ctaCustom = document.getElementById("cta-create-custom");
    if (ctaCustom)
      ctaCustom.addEventListener("click", () => {
        activateTab("tab-custom");
        const c = document.getElementById("tab-custom");
        if (c) c.focus();
      });

    if (root) {
      clear(root);
      root.appendChild(skeletonGrid(6));
    }

    let allAgencies = [];

    function matches(agency) {
      if (state.status !== "all" && agencyReadiness(agency) !== state.status)
        return false;
      if (state.search) {
        const q = state.search.toLowerCase();
        const hay = [
          agency.name_ar,
          agency.name_en,
          agency.description_ar,
          agency.code,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    }
    function sortAgencies(list) {
      const arr = list.slice();
      if (state.sort === "reports")
        arr.sort((a, b) => (b.report_count || 0) - (a.report_count || 0));
      else if (state.sort === "readiness")
        arr.sort(
          (a, b) =>
            READINESS_RANK[agencyReadiness(a)] -
            READINESS_RANK[agencyReadiness(b)],
        );
      else
        arr.sort((a, b) =>
          String(a.name_ar || "").localeCompare(String(b.name_ar || ""), "ar"),
        );
      return arr;
    }
    function resetFilters() {
      state.search = "";
      state.status = "all";
      state.sort = "name";
      state.dateFrom = "";
      state.dateTo = "";
      const s = document.getElementById("agency-search");
      if (s) s.value = "";
      const st = document.getElementById("agency-status-filter");
      if (st) st.value = "all";
      const so = document.getElementById("agency-sort");
      if (so) so.value = "name";
      const df = document.getElementById("agency-date-from");
      if (df) df.value = "";
      const dt = document.getElementById("agency-date-to");
      if (dt) dt.value = "";
      render();
    }
    function emptyState(hasFilters) {
      const box = document.createElement("div");
      box.className = "agency-empty-state";
      box.innerHTML = '<i class="bi bi-search" aria-hidden="true"></i>';
      const h = document.createElement("p");
      h.className = "agency-empty-state__title";
      h.textContent = hasFilters
        ? t(
            "لم يتم العثور على جهات أو تقارير مطابقة.",
            "No matching agencies or reports found.",
          )
        : t(
            "لا توجد جهات متاحة حاليًا.",
            "No agencies are available right now.",
          );
      box.appendChild(h);
      if (hasFilters) {
        const p = document.createElement("p");
        p.textContent = t(
          "جرّب تعديل كلمات البحث أو إزالة بعض عوامل التصفية.",
          "Try changing your search terms or removing some filters.",
        );
        box.appendChild(p);
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "admin-btn admin-btn-secondary";
        btn.textContent = t("مسح عوامل التصفية", "Clear filters");
        btn.addEventListener("click", resetFilters);
        box.appendChild(btn);
      }
      return box;
    }
    function render() {
      if (!root) return;
      const filtered = sortAgencies(allAgencies.filter(matches));
      const countEl = document.getElementById("agency-result-count");
      if (countEl)
        countEl.textContent = t(
          filtered.length + " من " + allAgencies.length + " جهة",
          filtered.length + " of " + allAgencies.length + " agencies",
        );
      const active = !!(
        state.search ||
        state.status !== "all" ||
        state.sort !== "name" ||
        state.dateFrom ||
        state.dateTo
      );
      const clearBtn = document.getElementById("agency-clear-filters");
      if (clearBtn) clearBtn.hidden = !active;
      clear(root);
      if (!filtered.length) {
        root.appendChild(emptyState(active));
        return;
      }
      const ul = document.createElement("ul");
      ul.className = "agency-card-grid";
      ul.setAttribute("role", "list");
      filtered.forEach((a) => ul.appendChild(agencyCard(a)));
      root.appendChild(ul);
    }
    function wireToolbar() {
      const toolbar = document.getElementById("agency-toolbar");
      if (toolbar) toolbar.hidden = false;
      const s = document.getElementById("agency-search");
      if (s) {
        let deb;
        s.addEventListener("input", function () {
          clearTimeout(deb);
          deb = setTimeout(() => {
            state.search = s.value.trim();
            render();
          }, 250);
        });
      }
      const st = document.getElementById("agency-status-filter");
      if (st)
        st.addEventListener("change", () => {
          state.status = st.value;
          render();
        });
      const so = document.getElementById("agency-sort");
      if (so)
        so.addEventListener("change", () => {
          state.sort = so.value;
          render();
        });
      const df = document.getElementById("agency-date-from");
      if (df)
        df.addEventListener("change", () => {
          state.dateFrom = df.value;
          render();
        });
      const dt = document.getElementById("agency-date-to");
      if (dt)
        dt.addEventListener("change", () => {
          state.dateTo = dt.value;
          render();
        });
      const clearBtn = document.getElementById("agency-clear-filters");
      if (clearBtn) clearBtn.addEventListener("click", resetFilters);
    }

    api("/api/admin/agency-reports/catalog")
      .then((data) => {
        allAgencies = data.agencies || [];
        renderKpiGrid(allAgencies);
        wireToolbar();
        render();
      })
      .catch(() => {
        if (!root) return;
        clear(root);
        const err = document.createElement("div");
        err.className = "agency-alert agency-alert--error agency-error-state";
        err.setAttribute("role", "alert");
        err.innerHTML =
          '<i class="bi bi-exclamation-octagon" aria-hidden="true"></i>';
        const p = document.createElement("p");
        p.textContent = t(
          "تعذر تحميل البيانات. تحقق من الاتصال ثم حاول مرة أخرى.",
          "Could not load data. Check your connection and try again.",
        );
        err.appendChild(p);
        const retry = document.createElement("button");
        retry.type = "button";
        retry.className = "admin-btn admin-btn-secondary";
        retry.textContent = t("إعادة المحاولة", "Retry");
        retry.addEventListener("click", () => window.location.reload());
        err.appendChild(retry);
        root.appendChild(err);
      });
  }

  if (type === "agency") {
    // Read date_from/date_to from the URL query string and pass to report links
    const urlParams = new URLSearchParams(window.location.search);
    const dateFrom = urlParams.get("date_from") || "";
    const dateTo = urlParams.get("date_to") || "";
    const dateSuffix =
      dateFrom || dateTo
        ? "?" +
          new URLSearchParams({
            date_from: dateFrom,
            date_to: dateTo,
          }).toString()
        : "";

    api(
      "/api/admin/agency-reports/" +
        encodeURIComponent(page.dataset.agencyCode) +
        "/reports",
    )
      .then(function (data) {
        // If date params exist, append them to each report's "Open Report" link
        if (dateSuffix && data.reports) {
          data.reports.forEach(function (r) {
            // Store date params so renderAgency can use them
            r._dateSuffix = dateSuffix;
          });
        }
        renderAgency(data);
      })
      .catch(() => {
        if (root)
          root.textContent = t(
            "تعذر تحميل تقارير الجهة.",
            "Unable to load agency reports.",
          );
      });
  }

  if (type === "report") {
    const filtersForm = document.getElementById("agency-report-filters");
    const drillKeys = [
      "governorate",
      "city",
      "district",
      "kindergarten_id",
      "status",
      "severity",
      "role",
      "gender",
      "period",
      "year",
      "quarter",
    ];
    if (filtersForm) {
      const urlParams = new URLSearchParams(window.location.search);
      const initialDrill = {};

      ["date_from", "date_to", ...drillKeys].forEach((key) => {
        const value = urlParams.get(key);
        if (!value || !value.trim()) return;

        const el = filtersForm.querySelector(`[name="${key}"]`);
        if (el) el.value = value;
        if (drillKeys.includes(key)) {
          initialDrill[key] = value;
        }
      });

      if (Object.keys(initialDrill).length) {
        window.__agencyDrillDown = initialDrill;
      }

      filtersForm.addEventListener("submit", (e) => {
        e.preventDefault();
        loadReport();
      });
    }
    initDrillDown();
    loadReport();
  }
})();
