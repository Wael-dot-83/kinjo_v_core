/**
 * date_display.js — Jordan-facing date/time formatting for server timestamps (N16).
 *
 * The server sends timestamps as UTC with an explicit offset (`…+00:00`), because
 * most of the UI passes them to `new Date()` and lets the browser localise. That is
 * correct and must not change.
 *
 * The bug this file exists to prevent is *string-slicing* a server timestamp:
 *
 *     kg.updated_at.slice(0, 10)      // "2026-08-01" — the UTC date
 *
 * Jordan is UTC+3, so 21:00Z onwards is already tomorrow in Amman. Slicing shows
 * anything updated after 21:00 Jordan on the previous calendar day. Parse the value
 * and format it in Asia/Amman instead.
 *
 * `Intl` with `timeZone: "Asia/Amman"` is used rather than a hardcoded +3 offset, so
 * the conversion comes from the browser's tz database and stays correct for
 * historical instants (Jordan observed DST until 2022). Locale `en-CA` is used
 * because it renders as YYYY-MM-DD.
 */
(function (global) {
  "use strict";

  var JORDAN_TZ = "Asia/Amman";

  function parse(value) {
    if (!value) return null;
    var d = value instanceof Date ? value : new Date(value);
    return Number.isNaN(d.valueOf()) ? null : d;
  }

  /** Jordan calendar date as "YYYY-MM-DD". Empty string when absent/unparseable. */
  function jordanDate(value) {
    var d = parse(value);
    if (!d) return "";
    return d.toLocaleDateString("en-CA", { timeZone: JORDAN_TZ });
  }

  /** Jordan date and time as "YYYY-MM-DD HH:MM" (24h). */
  function jordanDateTime(value) {
    var d = parse(value);
    if (!d) return "";
    var datePart = d.toLocaleDateString("en-CA", { timeZone: JORDAN_TZ });
    var timePart = d.toLocaleTimeString("en-GB", {
      timeZone: JORDAN_TZ,
      hour: "2-digit",
      minute: "2-digit",
      hour12: false
    });
    return datePart + " " + timePart;
  }

  /** Today's Jordan date as "YYYY-MM-DD", from the browser clock. */
  function jordanToday() {
    return new Date().toLocaleDateString("en-CA", { timeZone: JORDAN_TZ });
  }

  global.KinjoDate = {
    jordanDate: jordanDate,
    jordanDateTime: jordanDateTime,
    jordanToday: jordanToday
  };
})(typeof window !== "undefined" ? window : this);
