/**
 * date-utils.js — KinJo shared date/time presentation utilities.
 *
 * All timestamps from the API are ISO-8601 strings (UTC or +03:00).
 * All presentation uses Asia/Amman (Jordan, UTC+3 year-round — no DST).
 */

const _AMMAN_TZ = "Asia/Amman";

const _FMT = {
  date:     { ar: new Intl.DateTimeFormat("ar-JO", { year: "numeric", month: "short", day: "numeric",                                              timeZone: _AMMAN_TZ }), en: new Intl.DateTimeFormat("en-JO", { year: "numeric", month: "short", day: "numeric",                                              timeZone: _AMMAN_TZ }) },
  datetime: { ar: new Intl.DateTimeFormat("ar-JO", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",           timeZone: _AMMAN_TZ }), en: new Intl.DateTimeFormat("en-JO", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",           timeZone: _AMMAN_TZ }) },
  time:     { ar: new Intl.DateTimeFormat("ar-JO", {                                                   hour: "2-digit", minute: "2-digit",           timeZone: _AMMAN_TZ }), en: new Intl.DateTimeFormat("en-JO", {                                                   hour: "2-digit", minute: "2-digit",           timeZone: _AMMAN_TZ }) },
};

function _getLang() {
  return document.documentElement.getAttribute("lang") === "en" ? "en" : "ar";
}

/**
 * Format an ISO-8601 timestamp for display in Asia/Amman timezone.
 * @param {string|null} val  - ISO-8601 string, or null/""
 * @param {object} opts
 * @param {boolean} [opts.time=false]   - include hours/minutes
 * @param {string}  [opts.lang]         - "ar"|"en" (defaults to page lang)
 * @returns {string} formatted string, "-" for null/empty, error badge for invalid
 */
function formatToAmman(val, { time = false, lang } = {}) {
  if (val == null || val === "") return "-";
  const d = new Date(val);
  if (isNaN(d.getTime())) {
    const raw = String(val).replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return `<span class="badge bg-warning text-dark" title="${raw}">Invalid Date</span>`;
  }
  const l = lang || _getLang();
  const key = time ? "datetime" : "date";
  return _FMT[key][l].format(d);
}

/**
 * Format with time component (shorthand for formatToAmman(val, {time:true})).
 */
function formatToAmmanDatetime(val, opts = {}) {
  return formatToAmman(val, { ...opts, time: true });
}

/**
 * Return a relative "time ago" string (Arabic or English) for recent timestamps.
 * Falls back to formatToAmman for timestamps older than 7 days.
 */
function timeAgoAmman(val, { lang } = {}) {
  if (val == null || val === "") return "-";
  const d = new Date(val);
  if (isNaN(d.getTime())) return formatToAmman(val, { lang });

  const l = lang || _getLang();
  const diffMs = Date.now() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr  = Math.floor(diffMs / 3600000);
  const diffDay = Math.floor(diffMs / 86400000);

  if (diffDay > 7)  return formatToAmman(val, { lang: l });
  if (diffDay >= 1) return l === "ar" ? `منذ ${diffDay} يوم` : `${diffDay}d ago`;
  if (diffHr  >= 1) return l === "ar" ? `منذ ${diffHr} ساعة` : `${diffHr}h ago`;
  if (diffMin >= 1) return l === "ar" ? `منذ ${diffMin} دقيقة` : `${diffMin}m ago`;
  return l === "ar" ? "الآن" : "just now";
}

export { formatToAmman, formatToAmmanDatetime, timeAgoAmman };
