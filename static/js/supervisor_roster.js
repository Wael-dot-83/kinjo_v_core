/**
 * Class roster — file a whole class's daily reports from one screen.
 *
 * Shared values (date, arrival, leave, meals) are entered once at the top of the
 * page and every row inherits them; a row only carries what the supervisor
 * actually changed. Save posts once to /api/daily-reports/batch, which answers
 * 207 with a per-child outcome, so a class where one child is absent and another
 * already has a report still files everyone else.
 */
(function () {
  "use strict";

  var IS_EN = document.documentElement.lang === "en";
  function T(ar, en) { return IS_EN ? en : ar; }

  // sanitize.js publishes escapeHtml; fall back rather than throw, because an
  // undefined escaper inside a template literal fails silently into an empty UI.
  function esc(v) {
    return window.escapeHtml ? window.escapeHtml(v) : String(v == null ? "" : v);
  }

  var MOODS = [
    { value: "happy",  emoji: "😊", ar: "سعيد",  en: "Happy" },
    { value: "normal", emoji: "😐", ar: "عادي",  en: "Normal" },
    { value: "sad",    emoji: "😢", ar: "حزين",  en: "Sad" },
    { value: "tired",  emoji: "😴", ar: "نعسان", en: "Tired" },
    { value: "sick",   emoji: "🤒", ar: "مريض",  en: "Sick" }
  ];

  var els = {};
  var children = [];
  var filedChildIds = new Set();

  function headers() {
    var h = { "Content-Type": "application/json" };
    var m = document.cookie.match(/(?:^|;\s*)kinjo_csrf_token=([^;]+)/);
    if (m) h["X-CSRF-Token"] = decodeURIComponent(m[1]);
    return h;
  }

  function todayISO() {
    // Jordan is UTC+3; using the browser's local date would file a report
    // against the wrong day for anyone working outside that offset.
    var now = new Date();
    var jordan = new Date(now.getTime() + (now.getTimezoneOffset() + 180) * 60000);
    return jordan.toISOString().slice(0, 10);
  }

  function initialOf(name) {
    return (name || "?").trim().charAt(0) || "?";
  }

  function rowTemplate(child) {
    var filed = filedChildIds.has(child.id);
    var moods = MOODS.map(function (m) {
      var id = "mood-" + child.id + "-" + m.value;
      return (
        '<input type="radio" name="mood-' + child.id + '" id="' + id + '" value="' + m.value + '"' +
        (filed ? " disabled" : "") + '>' +
        '<label for="' + id + '" title="' + T(m.ar, m.en) + '">' +
        '<span aria-hidden="true">' + m.emoji + '</span>' +
        '<span class="visually-hidden">' + T(m.ar, m.en) + '</span>' +
        "</label>"
      );
    }).join("");

    return (
      '<div class="roster-row' + (filed ? " is-filed" : "") + '" data-child-id="' + child.id + '">' +
        '<div class="roster-child">' +
          '<span class="roster-avatar" aria-hidden="true">' + esc(initialOf(child.name || child.first_name)) + "</span>" +
          '<span class="roster-name">' + esc(child.name || (child.first_name + " " + child.last_name)) + "</span>" +
        "</div>" +
        '<div class="roster-moods" role="group" aria-label="' + T("مزاج", "Mood") + " " + esc(child.name) + '">' + moods + "</div>" +
        '<div>' +
          '<label class="visually-hidden" for="nap-' + child.id + '">' + T("نوم بالدقائق", "Nap minutes") + "</label>" +
          '<input type="number" min="0" max="300" step="5" class="form-control form-control-sm" ' +
            'id="nap-' + child.id + '" placeholder="' + T("نوم", "Nap") + '"' + (filed ? " disabled" : "") + ">" +
        "</div>" +
        '<div>' +
          '<label class="visually-hidden" for="note-' + child.id + '">' + T("ملاحظة", "Note") + "</label>" +
          '<input type="text" maxlength="300" class="form-control form-control-sm" ' +
            'id="note-' + child.id + '" placeholder="' + T("ملاحظة لولي الأمر", "Note for the parent") + '"' +
            (filed ? " disabled" : "") + ">" +
        "</div>" +
        '<div class="d-flex align-items-center gap-2">' +
          (filed
            ? '<span class="badge bg-success-subtle text-success-emphasis roster-filed-badge">' +
              T("تم التقرير", "Already filed") + "</span>"
            : '<div class="form-check m-0" title="' + T("تخطّي هذا الطفل", "Skip this child") + '">' +
              '<input class="form-check-input roster-skip" type="checkbox" id="skip-' + child.id + '">' +
              '<label class="form-check-label small" for="skip-' + child.id + '">' + T("تخطٍّ", "Skip") + "</label>" +
              "</div>") +
          '<a class="btn btn-sm btn-link text-decoration-none" href="/daily-reports/create?child_id=' + child.id + '" ' +
            'title="' + T("التفاصيل الكاملة", "Full details") + '">' +
            '<i class="bi bi-arrow-left-short" aria-hidden="true"></i>' +
            '<span class="visually-hidden">' + T("التفاصيل الكاملة", "Full details") + "</span></a>" +
        "</div>" +
      "</div>"
    );
  }

  function render() {
    if (!children.length) {
      els.loading.classList.add("d-none");
      els.empty.classList.remove("d-none");
      return;
    }
    els.list.innerHTML = children.map(rowTemplate).join("");
    els.loading.classList.add("d-none");
    els.list.classList.remove("d-none");
    els.bar.classList.remove("d-none");
    els.list.addEventListener("change", onRowChange);
    updateCount();
  }

  function onRowChange(e) {
    if (e.target.classList.contains("roster-skip")) {
      var row = e.target.closest(".roster-row");
      if (row) row.classList.toggle("is-skipped", e.target.checked);
    }
    updateCount();
  }

  function pendingRows() {
    return children.filter(function (c) {
      if (filedChildIds.has(c.id)) return false;
      var skip = document.getElementById("skip-" + c.id);
      return !(skip && skip.checked);
    });
  }

  function updateCount() {
    var pending = pendingRows().length;
    var filed = filedChildIds.size;
    els.count.textContent = filed
      ? T(
          pending + " جاهز للحفظ · " + filed + " تم تقريره سابقاً",
          pending + " ready to save · " + filed + " already filed"
        )
      : T(pending + " من " + children.length + " جاهز للحفظ", pending + " of " + children.length + " ready to save");
    els.save.disabled = pending === 0;
  }

  function buildPayload() {
    var shared = napWindow();

    return {
      date: els.date.value,
      arrival_time: els.arrival.value,
      leave_time: els.leave.value,
      breakfast: els.breakfast.checked,
      lunch: els.lunch.checked,
      snack: els.snack.checked,
      children: children
        .filter(function (c) { return !filedChildIds.has(c.id); })
        .map(function (c) {
          var skip = document.getElementById("skip-" + c.id);
          var mood = document.querySelector('input[name="mood-' + c.id + '"]:checked');
          var nap = document.getElementById("nap-" + c.id);
          var note = document.getElementById("note-" + c.id);
          var override = nap && nap.value ? parseInt(nap.value, 10) : null;

          // Three cases, in order of precedence:
          //   1. the row overrides the duration — keep the shared start and end
          //      that many minutes later, so the child's own window is recorded
          //   2. the shared window is set — every row inherits it
          //   3. neither — no nap is recorded for this child
          //
          // The previous version had no shared window at all: it anchored the
          // nap to the arrival time, so every nap was recorded as beginning the
          // moment the child walked through the door.
          var napStart = null, napEnd = null, napMinutes = null;
          if (override && shared.start) {
            napStart = shared.start;
            napEnd = addMinutes(shared.start, override);
            napMinutes = override;
          } else if (shared.minutes != null) {
            napStart = shared.start;
            napEnd = shared.end;
            napMinutes = shared.minutes;
          }

          return {
            child_id: c.id,
            skip: !!(skip && skip.checked),
            mood: mood ? mood.value : null,
            nap_start: napStart,
            nap_end: napEnd,
            nap_duration_minutes: napMinutes,
            notes: note && note.value ? note.value : null
          };
        })
    };
  }

  function addMinutes(hhmm, minutes) {
    var parts = String(hhmm || "08:00").split(":");
    var total = parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10) + minutes;
    total = Math.min(total, 23 * 60 + 59);
    var h = String(Math.floor(total / 60)).padStart(2, "0");
    var m = String(total % 60).padStart(2, "0");
    return h + ":" + m;
  }

  // ── Shared nap window ──────────────────────────────────────────────────────
  // The supervisor picks an hour and a minute for the start and for the end;
  // the duration is derived from those two, never typed. Returns null when the
  // window is incomplete or invalid so callers can tell "not set" from "zero".

  function toMinutes(hhmm) {
    if (!hhmm) return null;
    var p = String(hhmm).split(":");
    if (p.length !== 2) return null;
    var h = parseInt(p[0], 10);
    var m = parseInt(p[1], 10);
    if (isNaN(h) || isNaN(m)) return null;
    return h * 60 + m;
  }

  // An hour on its own is a complete time — minutes default to :00 — but a
  // minute on its own is not, so it yields nothing rather than a bogus 00:MM.
  function napTimeOf(hourSelect, minuteSelect) {
    if (!hourSelect || !hourSelect.value) return null;
    return hourSelect.value + ":" + (minuteSelect && minuteSelect.value ? minuteSelect.value : "00");
  }

  function napWindow() {
    var start = napTimeOf(els.napStartHour, els.napStartMinute);
    var end = napTimeOf(els.napEndHour, els.napEndMinute);
    if (!start || !end) return { start: start, end: end, minutes: null, error: null };

    var diff = toMinutes(end) - toMinutes(start);
    if (diff <= 0) {
      return {
        start: start,
        end: end,
        minutes: null,
        error: T("وقت الانتهاء يجب أن يكون بعد وقت البدء.",
                 "The end time must be after the start time.")
      };
    }
    return { start: start, end: end, minutes: diff, error: null };
  }

  function refreshNapDuration() {
    var w = napWindow();
    if (els.napDuration) {
      els.napDuration.value = w.minutes == null ? "" : String(w.minutes);
    }
    if (els.napWarning) {
      if (w.error) {
        els.napWarning.textContent = w.error;
        els.napWarning.classList.remove("d-none");
      } else {
        els.napWarning.textContent = "";
        els.napWarning.classList.add("d-none");
      }
    }
    return w;
  }

  function showResult(data) {
    var lines = [];
    if (data.created) lines.push(T(data.created + " تقرير تم حفظه كمسودة", data.created + " report(s) saved as draft"));
    if (data.skipped) lines.push(T(data.skipped + " تم تخطّيه", data.skipped + " skipped"));

    var failures = (data.results || []).filter(function (r) { return r.status === "failed"; });
    var cls = failures.length ? "alert-warning" : "alert-success";
    var body = "<p class='mb-" + (failures.length ? "2" : "0") + " fw-semibold'>" + esc(lines.join(" · ")) + "</p>";
    if (failures.length) {
      body += "<ul class='mb-0 ps-3 small'>" + failures.map(function (f) {
        var child = children.filter(function (c) { return c.id === f.child_id; })[0];
        var name = child ? (child.name || child.first_name) : "#" + f.child_id;
        return "<li>" + esc(name) + " — " + esc(f.detail) + "</li>";
      }).join("") + "</ul>";
    }
    els.result.className = "mt-3 alert " + cls;
    els.result.innerHTML = body;
    els.result.classList.remove("d-none");
  }

  async function loadFiledReports(dateStr) {
    filedChildIds = new Set();
    try {
      var res = await fetch("/api/supervisor/daily-reports?date=" + encodeURIComponent(dateStr), { headers: headers() });
      if (!res.ok) return;
      var data = await res.json();
      var list = data.reports || data.items || data.daily_reports || (Array.isArray(data) ? data : []);
      list.forEach(function (r) { if (r && r.child_id) filedChildIds.add(r.child_id); });
    } catch (err) {
      // A failure here only costs the "already filed" hint; the server still
      // rejects a duplicate with 409 and the roster reports it per child.
      console.warn("[roster] could not load existing reports:", err);
    }
  }

  async function load() {
    els.loading.classList.remove("d-none");
    els.list.classList.add("d-none");
    els.empty.classList.add("d-none");
    els.bar.classList.add("d-none");
    els.result.classList.add("d-none");
    try {
      var res = await fetch("/api/supervisor/children", { headers: headers() });
      if (!res.ok) throw new Error("HTTP " + res.status);
      var data = await res.json();
      children = data.children || [];
      await loadFiledReports(els.date.value);
      render();
    } catch (err) {
      els.loading.classList.add("d-none");
      els.error.textContent = T("تعذّر تحميل قائمة الأطفال. حدّث الصفحة وحاول مجدداً.",
                                "Could not load your class. Refresh and try again.");
      els.error.classList.remove("d-none");
      console.error("[roster] load failed:", err);
    }
  }

  async function save() {
    els.save.disabled = true;
    var original = els.save.innerHTML;
    els.save.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>' +
      T("جارٍ الحفظ…", "Saving…");
    try {
      var res = await fetch("/api/daily-reports/batch", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify(buildPayload())
      });
      var data = await res.json();
      if (!res.ok && res.status !== 207) {
        throw new Error(data.detail || "HTTP " + res.status);
      }
      showResult(data);
      await load();  // refresh so saved rows show as filed
    } catch (err) {
      els.result.className = "mt-3 alert alert-danger";
      els.result.textContent = T("تعذّر حفظ التقارير: ", "Could not save reports: ") + err.message;
      els.result.classList.remove("d-none");
      console.error("[roster] save failed:", err);
    } finally {
      els.save.innerHTML = original;
      updateCount();
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    els = {
      date: document.getElementById("rosterDate"),
      arrival: document.getElementById("sharedArrival"),
      leave: document.getElementById("sharedLeave"),
      breakfast: document.getElementById("sharedBreakfast"),
      lunch: document.getElementById("sharedLunch"),
      snack: document.getElementById("sharedSnack"),
      loading: document.getElementById("rosterLoading"),
      empty: document.getElementById("rosterEmpty"),
      error: document.getElementById("rosterError"),
      list: document.getElementById("rosterList"),
      bar: document.getElementById("rosterBar"),
      count: document.getElementById("rosterCount"),
      save: document.getElementById("rosterSave"),
      result: document.getElementById("rosterResult"),
      napStartHour: document.getElementById("sharedNapStartHour"),
      napStartMinute: document.getElementById("sharedNapStartMinute"),
      napEndHour: document.getElementById("sharedNapEndHour"),
      napEndMinute: document.getElementById("sharedNapEndMinute"),
      napDuration: document.getElementById("sharedNapDuration"),
      napWarning: document.getElementById("sharedNapWarning")
    };
    if (!els.list) return;

    els.date.value = todayISO();
    els.date.max = todayISO();  // the API refuses future dates; do not offer them
    els.date.addEventListener("change", load);
    els.save.addEventListener("click", save);

    // The duration is recomputed on every one of the four selects, so it stays
    // right whichever the supervisor changes last.
    [els.napStartHour, els.napStartMinute, els.napEndHour, els.napEndMinute]
      .forEach(function (sel) {
        if (sel) sel.addEventListener("change", refreshNapDuration);
      });
    refreshNapDuration();

    load();
  });
})();
