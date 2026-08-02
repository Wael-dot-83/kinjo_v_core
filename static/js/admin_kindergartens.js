/* =========================================================================
   Admin Kindergartens — list page controller
   Extracted from list.html and enhanced: KPI summary cards, debounced
   auto-search with URL persistence, SweetAlert2 confirms, toast feedback,
   client-side column sort, occupancy bars, CSV export, pagination.
   Depends on globals from admin_base.html: `api` (kinjo-api.js),
   `Swal` (SweetAlert2), `AdminComponents.showNotification`.
   ========================================================================= */
(function () {
  "use strict";

  var tbody = document.getElementById("kg-tbody");
  if (!tbody) return; // only run on the list page

  var IS_EN = document.documentElement.lang === "en";
  var T = function (ar, en) { return IS_EN ? en : ar; };
  var LIMIT = 20;

  var state = {
    skip: 0,
    total: 0,
    items: [],
    sortKey: null,
    sortDir: 1, // 1 asc, -1 desc
  };

  // ---- small helpers ------------------------------------------------------
  function $(id) { return document.getElementById(id); }
  function show(id) { var el = $(id); if (el) el.classList.remove("d-none"); }
  function hide(id) { var el = $(id); if (el) el.classList.add("d-none"); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function toast(type, message) {
    if (window.AdminComponents && typeof window.AdminComponents.showNotification === "function") {
      window.AdminComponents.showNotification({ type: type, title: "", message: message });
    }
  }

  var STATUS_LABEL = {
    active: T("نشط", "Active"),
    frozen: T("مجمدة", "Frozen"),
    deleted: T("محذوفة", "Deleted"),
    draft: T("مسودة", "Draft"),
    inactive: T("غير نشط", "Inactive"),
  };
  function statusBadge(s) {
    var label = STATUS_LABEL[s] || s || "—";
    return '<span class="kg-badge kg-badge--' + esc(s || "inactive") + '">' + esc(label) + "</span>";
  }
  function occupancyCell(pct) {
    if (pct == null) return '<span class="text-muted">—</span>';
    var cls = pct >= 100 ? "is-full" : (pct >= 85 ? "is-high" : "");
    var w = Math.max(0, Math.min(100, pct));
    return (
      '<div class="kg-occ"><div class="kg-occ-track"><div class="kg-occ-fill ' + cls +
      '" style="width:' + w + '%"></div></div><span class="kg-occ-num">' + pct + "%</span></div>"
    );
  }

  // ---- URL <-> filter state ----------------------------------------------
  var FILTER_IDS = {
    q: "filter-q",
    governorate: "filter-governorate",
    status: "filter-status",
    min_children: "filter-min-children",
    min_occupancy: "filter-min-occupancy",
  };

  function readFiltersFromUrl() {
    var p = new URLSearchParams(window.location.search);
    Object.keys(FILTER_IDS).forEach(function (key) {
      var el = $(FILTER_IDS[key]);
      if (el && p.has(key)) el.value = p.get(key);
    });
    if (p.has("skip")) state.skip = parseInt(p.get("skip"), 10) || 0;
  }

  function currentFilters() {
    var f = {};
    Object.keys(FILTER_IDS).forEach(function (key) {
      var el = $(FILTER_IDS[key]);
      var v = el ? String(el.value).trim() : "";
      if (v) f[key] = v;
    });
    return f;
  }

  function syncUrl() {
    var p = new URLSearchParams();
    var f = currentFilters();
    Object.keys(f).forEach(function (k) { p.set(k, f[k]); });
    if (state.skip) p.set("skip", state.skip);
    var qs = p.toString();
    var url = window.location.pathname + (qs ? "?" + qs : "");
    window.history.replaceState(null, "", url);
  }

  // ---- KPI summary --------------------------------------------------------
  function setKpi(id, value) {
    var el = $(id);
    if (!el) return;
    el.classList.remove("kg-skeleton");
    el.textContent = value;
  }
  function loadStats() {
    api.get("/api/admin/kindergartens/stats").then(function (json) {
      if (!json || !json.success) return;
      var d = json.data || {};
      setKpi("kpi-total", d.total != null ? d.total : "—");
      setKpi("kpi-active", d.active != null ? d.active : "—");
      setKpi("kpi-frozen", d.frozen != null ? d.frozen : "—");
      setKpi("kpi-draft", d.draft != null ? d.draft : "—");
      setKpi("kpi-children", d.total_children != null ? d.total_children : "—");
      setKpi("kpi-occupancy", d.avg_occupancy != null ? d.avg_occupancy + "%" : "—");
    }).catch(function () {
      ["kpi-total", "kpi-active", "kpi-frozen", "kpi-draft", "kpi-children", "kpi-occupancy"].forEach(function (id) {
        setKpi(id, "—");
      });
    });
  }

  // ---- list load + render -------------------------------------------------
  function load() {
    hide("state-error"); hide("state-empty"); hide("table-wrap");
    show("state-loading");
    var params = currentFilters();
    params.limit = LIMIT;
    params.skip = state.skip;
    syncUrl();
    api.get("/api/kindergartens", params).then(function (json) {
      hide("state-loading");
      if (!json || !json.success) throw new Error((json && json.message) || "Error");
      state.items = (json.data && json.data.items) || [];
      state.total = (json.data && json.data.total) || 0;
      applySort();
      render();
    }).catch(function (e) {
      hide("state-loading");
      var el = $("error-text");
      if (el) el.textContent = (e && e.message) || T("تعذر تحميل البيانات", "Failed to load data");
      show("state-error");
    });
  }

  function render() {
    if (!state.items.length) { show("state-empty"); return; }
    show("table-wrap");
    var rows = state.items.map(function (kg) {
      var actions =
        '<div class="dropdown">' +
        '<button class="btn btn-sm btn-outline-secondary" data-bs-toggle="dropdown" aria-label="' + T("إجراءات", "Actions") + '"><i class="bi bi-three-dots"></i></button>' +
        '<ul class="dropdown-menu dropdown-menu-end">' +
        '<li><a class="dropdown-item" href="/admin/kindergartens/' + kg.id + '"><i class="bi bi-eye me-2"></i>' + T("عرض التفاصيل", "Details") + "</a></li>" +
        '<li><a class="dropdown-item" href="/admin/kindergartens/' + kg.id + '/edit"><i class="bi bi-pencil me-2"></i>' + T("تعديل", "Edit") + "</a></li>" +
        (kg.status === "frozen"
          ? '<li><a class="dropdown-item" href="#" data-act="activate" data-id="' + kg.id + '"><i class="bi bi-play-circle me-2"></i>' + T("تفعيل", "Activate") + "</a></li>"
          : (kg.status === "deleted" ? "" : '<li><a class="dropdown-item" href="#" data-act="freeze" data-id="' + kg.id + '"><i class="bi bi-snow me-2"></i>' + T("تجميد", "Freeze") + "</a></li>")) +
        (kg.status === "deleted" ? "" : '<li><hr class="dropdown-divider"></li><li><a class="dropdown-item text-danger" href="#" data-act="delete" data-id="' + kg.id + '"><i class="bi bi-trash me-2"></i>' + T("حذف", "Delete") + "</a></li>") +
        "</ul></div>";
      return (
        "<tr>" +
        '<td data-label="' + T("الاسم", "Name") + '"><div class="kg-kg-name">' + esc(kg.name_ar) + "</div>" +
        (kg.legal_name ? '<div class="kg-kg-sub">' + esc(kg.legal_name) + "</div>" : "") + "</td>" +
        '<td data-label="' + T("المحافظة", "Governorate") + '">' + esc(kg.governorate || "—") +
        (kg.district ? '<div class="kg-kg-sub">' + esc(kg.district) + "</div>" : "") + "</td>" +
        '<td data-label="' + T("الأطفال", "Children") + '">' + (kg.child_count != null ? kg.child_count : 0) + "</td>" +
        '<td data-label="' + T("الحضور %", "Attendance %") + '">' + (kg.attendance_pct != null ? kg.attendance_pct + "%" : "—") + "</td>" +
        '<td data-label="' + T("الإشغال %", "Occupancy %") + '">' + occupancyCell(kg.occupancy_pct) + "</td>" +
        '<td data-label="' + T("الحالة", "Status") + '">' + statusBadge(kg.status) + "</td>" +
        '<td data-label="' + T("آخر تحديث", "Last Update") + '"><span class="kg-kg-sub">' + (kg.updated_at ? esc(KinjoDate.jordanDate(kg.updated_at)) : "—") + "</span></td>" +
        '<td data-label="' + T("الإجراءات", "Actions") + '" class="text-end">' + actions + "</td>" +
        "</tr>"
      );
    }).join("");
    tbody.innerHTML = rows;

    var from = state.total ? state.skip + 1 : 0;
    var to = state.skip + state.items.length;
    var info = $("pager-info");
    if (info) info.textContent = from + "–" + to + " / " + state.total;
    var prev = $("btn-prev"), next = $("btn-next");
    if (prev) prev.disabled = state.skip <= 0;
    if (next) next.disabled = to >= state.total;
  }

  // ---- client-side sort (current page) -----------------------------------
  function applySort() {
    if (!state.sortKey) return;
    var k = state.sortKey, dir = state.sortDir;
    state.items.sort(function (a, b) {
      var va = a[k], vb = b[k];
      if (va == null) va = "";
      if (vb == null) vb = "";
      if (typeof va === "number" && typeof vb === "number") return (va - vb) * dir;
      return String(va).localeCompare(String(vb), IS_EN ? "en" : "ar") * dir;
    });
  }

  function wireSort() {
    document.querySelectorAll("th.kg-sortable").forEach(function (th) {
      th.addEventListener("click", function () {
        var key = th.getAttribute("data-sort");
        if (state.sortKey === key) { state.sortDir *= -1; }
        else { state.sortKey = key; state.sortDir = 1; }
        document.querySelectorAll("th.kg-sortable").forEach(function (t) { t.removeAttribute("aria-sort"); });
        th.setAttribute("aria-sort", state.sortDir === 1 ? "ascending" : "descending");
        applySort();
        render();
      });
    });
  }

  // ---- actions (SweetAlert2) ---------------------------------------------
  function afterAction(promise, okMsg) {
    return promise.then(function (json) {
      if (!json || !json.success) throw new Error((json && json.message) || T("فشل الإجراء", "Action failed"));
      toast("success", okMsg);
      loadStats();
      load();
    }).catch(function (e) {
      toast("error", (e && e.message) || T("تعذر تنفيذ الإجراء", "Could not perform action"));
    });
  }

  function onFreeze(id) {
    Swal.fire({
      title: T("تجميد الحضانة", "Freeze kindergarten"),
      text: T("سيتم تعليق نشاط الحضانة. أدخل سبب التجميد:", "This suspends the kindergarten. Enter a freeze reason:"),
      input: "text",
      inputPlaceholder: T("سبب التجميد", "Freeze reason"),
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: T("تجميد", "Freeze"),
      cancelButtonText: T("إلغاء", "Cancel"),
      confirmButtonColor: "#0284c7",
      inputValidator: function (v) { return !v && T("الرجاء إدخال سبب", "Please enter a reason"); },
    }).then(function (res) {
      if (res.isConfirmed) afterAction(api.freezeKindergarten(id, res.value), T("تم تجميد الحضانة", "Kindergarten frozen"));
    });
  }
  function onActivate(id) {
    Swal.fire({
      title: T("تفعيل الحضانة", "Activate kindergarten"),
      text: T("هل تريد إعادة تفعيل هذه الحضانة؟", "Reactivate this kindergarten?"),
      icon: "question",
      showCancelButton: true,
      confirmButtonText: T("تفعيل", "Activate"),
      cancelButtonText: T("إلغاء", "Cancel"),
      confirmButtonColor: "#15803d",
    }).then(function (res) {
      if (res.isConfirmed) afterAction(api.unfreezeKindergarten(id), T("تم تفعيل الحضانة", "Kindergarten activated"));
    });
  }
  function onDelete(id) {
    Swal.fire({
      title: T("حذف الحضانة", "Delete kindergarten"),
      text: T("هذا الإجراء لا يمكن التراجع عنه. هل أنت متأكد؟", "This action cannot be undone. Are you sure?"),
      icon: "error",
      showCancelButton: true,
      confirmButtonText: T("نعم، حذف", "Yes, delete"),
      cancelButtonText: T("إلغاء", "Cancel"),
      confirmButtonColor: "#b91c1c",
    }).then(function (res) {
      if (res.isConfirmed) afterAction(api.deleteKindergarten(id), T("تم حذف الحضانة", "Kindergarten deleted"));
    });
  }

  tbody.addEventListener("click", function (e) {
    var a = e.target.closest("[data-act]");
    if (!a) return;
    e.preventDefault();
    var id = a.getAttribute("data-id"), act = a.getAttribute("data-act");
    if (act === "freeze") onFreeze(id);
    else if (act === "activate") onActivate(id);
    else if (act === "delete") onDelete(id);
  });

  // ---- CSV export (all matching rows, not just the page) ------------------
  function exportCsv() {
    var params = currentFilters();
    params.limit = 200; params.skip = 0;
    var btn = $("btn-export");
    if (btn) btn.disabled = true;
    api.get("/api/kindergartens", params).then(function (json) {
      var items = (json && json.data && json.data.items) || [];
      var headers = [T("الاسم", "Name"), T("الاسم القانوني", "Legal name"), T("المحافظة", "Governorate"),
        T("المديرية", "District"), T("الأطفال", "Children"), T("الإشغال %", "Occupancy %"),
        T("الحضور %", "Attendance %"), T("الحالة", "Status"), T("آخر تحديث", "Last update")];
      var cell = function (v) {
        var s = String(v == null ? "" : v);
        if (/^[=+\-@]/.test(s)) s = "'" + s; // CSV injection guard
        return '"' + s.replace(/"/g, '""') + '"';
      };
      var lines = [headers.map(cell).join(",")];
      items.forEach(function (k) {
        lines.push([k.name_ar, k.legal_name, k.governorate, k.district, k.child_count,
          k.occupancy_pct, k.attendance_pct, STATUS_LABEL[k.status] || k.status,
          k.updated_at ? KinjoDate.jordanDate(k.updated_at) : ""].map(cell).join(","));
      });
      var blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url; a.download = "kindergartens.csv";
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast("success", T("تم تصدير الملف", "Export ready"));
    }).catch(function () {
      toast("error", T("تعذر التصدير", "Export failed"));
    }).finally(function () { if (btn) btn.disabled = false; });
  }

  // ---- governorate filter options ----------------------------------------
  function loadGovernorates() {
    api.get("/api/reference/governorates").then(function (json) {
      var sel = $("filter-governorate");
      if (!sel) return;
      (json.governorates || []).forEach(function (g) {
        var o = document.createElement("option");
        o.value = g.name_ar; o.textContent = g.name_ar;
        sel.appendChild(o);
      });
      // restore selection if it came from the URL
      var p = new URLSearchParams(window.location.search);
      if (p.has("governorate")) sel.value = p.get("governorate");
    }).catch(function () {});
  }

  // ---- events -------------------------------------------------------------
  var debounceTimer = null;
  function debouncedSearch() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () { state.skip = 0; load(); }, 300);
  }

  function wire() {
    var q = $("filter-q");
    if (q) q.addEventListener("input", debouncedSearch);
    ["filter-governorate", "filter-status", "filter-min-children", "filter-min-occupancy"].forEach(function (id) {
      var el = $(id);
      if (el) el.addEventListener("change", function () { state.skip = 0; load(); });
    });
    var s = $("btn-search"); if (s) s.addEventListener("click", function () { state.skip = 0; load(); });
    var r = $("btn-reset"); if (r) r.addEventListener("click", function () {
      Object.keys(FILTER_IDS).forEach(function (k) { var el = $(FILTER_IDS[k]); if (el) el.value = ""; });
      state.skip = 0; load();
    });
    var retry = $("btn-retry"); if (retry) retry.addEventListener("click", load);
    var prev = $("btn-prev"); if (prev) prev.addEventListener("click", function () { if (state.skip >= LIMIT) { state.skip -= LIMIT; load(); } });
    var next = $("btn-next"); if (next) next.addEventListener("click", function () { state.skip += LIMIT; load(); });
    var exp = $("btn-export"); if (exp) exp.addEventListener("click", exportCsv);
    wireSort();
  }

  // ---- init ---------------------------------------------------------------
  readFiltersFromUrl();
  wire();
  loadGovernorates();
  loadStats();
  load();
})();
