/**
 * chart_utils.js — shared Chart.js data helpers.
 * Loaded before admin_dashboard.js and admin_analytics.js so both reuse one
 * implementation (avoids the previously duplicated safeChartData definition).
 */
(function (global) {
  "use strict";

  /**
   * Normalize an array for safe Chart.js consumption:
   * returns [] for non-arrays and replaces null/undefined entries with 0.
   * @param {Array} arr
   * @returns {Array}
   */
  function safeChartData(arr) {
    if (!Array.isArray(arr)) return [];
    return arr.map((v) => (v == null ? 0 : v));
  }

  global.safeChartData = safeChartData;
})(typeof window !== "undefined" ? window : this);
