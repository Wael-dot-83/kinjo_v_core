/**
 * Shared helpers for the parent portal pages (children, attendance,
 * enrollments, profile, dashboard). Loaded before each page's inline script.
 *
 * Consolidates the previously-duplicated inline definitions of getHeaders(),
 * escHtml(), T() and IS_EN so there is one implementation to maintain.
 */
(function () {
  "use strict";

  if (window.__parentCommonLoaded) return;
  window.__parentCommonLoaded = true;

  window.IS_EN = document.documentElement.lang === "en";

  window.T = function (ar, en) {
    return window.IS_EN ? en : ar;
  };

  window.escHtml =
    window.escapeHtml ||
    function (s) {
      return String(s ?? "").replace(/[&<>"']/g, function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
      });
    };

  function readCookie(name) {
    var m = document.cookie.match(new RegExp("(?:^|;\\s*)" + name + "=([^;]*)"));
    return m ? decodeURIComponent(m[1]) : null;
  }

  function resolveCsrfToken() {
    if (typeof getCsrfToken === "function") {
      var fromFn = getCsrfToken();
      if (fromFn) return fromFn;
    }
    if (typeof CSRF_TOKEN !== "undefined" && CSRF_TOKEN) return CSRF_TOKEN;
    var meta = document.querySelector('meta[name="csrf-token"]');
    var fromMeta = meta ? meta.getAttribute("content") : null;
    if (fromMeta) return fromMeta;
    return readCookie("kinjo_csrf_token");
  }

  window.getHeaders = function (extra) {
    var headers = { "Content-Type": "application/json" };
    var csrf = resolveCsrfToken();
    if (csrf) headers["X-CSRF-Token"] = csrf;
    if (extra) {
      for (var k in extra) {
        if (Object.prototype.hasOwnProperty.call(extra, k)) headers[k] = extra[k];
      }
    }
    return headers;
  };
})();
