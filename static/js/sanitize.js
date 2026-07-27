/**
 * Global HTML sanitization utility for XSS prevention.
 * Include this script before any JS that uses innerHTML with dynamic data.
 */
(function () {
  "use strict";
  if (window.escapeHtml) return; // already defined

  window.escapeHtml = function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  };
})();
