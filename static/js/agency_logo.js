/* Shared agency logo renderer — single source of truth on the client.
 * Logo metadata (path/available/fallback_label/alt_*) comes from the backend
 * (catalog/summary/custom schema), so JS never hardcodes the mapping.
 *
 * Accessibility: the agency name is ALWAYS rendered as real text beside the
 * logo, so the logo image is treated as decorative (alt="" + aria-hidden) to
 * avoid double-announcement. The fallback badge is also decorative.
 */
(function () {
  "use strict";
  window.renderAgencyLogo = function renderAgencyLogo(agency, size) {
    size = size || 56;
    var logo = agency && agency.logo;
    if (logo && logo.available && logo.path) {
      var img = document.createElement("img");
      img.className = "agency-logo";
      img.src = logo.path;
      img.width = size;
      img.height = size;
      img.alt = "";
      img.setAttribute("aria-hidden", "true");
      img.loading = "lazy";
      img.onerror = function () {
        var fb = renderAgencyFallback(agency, size);
        if (img.parentNode) img.parentNode.replaceChild(fb, img);
      };
      return img;
    }
    return renderAgencyFallback(agency, size);
  };

  function renderAgencyFallback(agency, size) {
    var span = document.createElement("span");
    span.className = "agency-logo-fallback";
    span.style.width = size + "px";
    span.style.height = size + "px";
    span.setAttribute("aria-hidden", "true");
    var name = (agency && agency.name_ar) || (agency && agency.name_en) || "";
    if (name) span.title = name;
    var label = (agency && agency.logo && agency.logo.fallback_label) ||
      (agency && agency.code ? String(agency.code).toUpperCase() : "?");
    span.textContent = label;
    return span;
  }
})();