/* KinJo admin appearance control.
 *
 * Three states, and the third one is the point: "system" stores nothing and
 * removes the attribute, so dark-mode.css falls back to prefers-color-scheme.
 * "light" and "dark" set data-theme explicitly and beat the OS in both
 * directions -- which is why dark-mode.css guards its media query with
 * :root:not([data-theme="light"]).
 *
 * No user-facing string appears in this file. The labels are already rendered
 * bilingually by admin_base.html, and the trigger copies whichever one the user
 * picked, so Arabic stays the default without a second copy of the wording
 * living in JavaScript where it would drift.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "kinjo_theme";
  var ICONS = {
    system: "bi-circle-half",
    light: "bi-sun",
    dark: "bi-moon-stars",
  };

  function read() {
    try {
      var v = localStorage.getItem(STORAGE_KEY);
      return v === "light" || v === "dark" ? v : "system";
    } catch (e) {
      return "system";
    }
  }

  function apply(theme) {
    var root = document.documentElement;
    if (theme === "system") {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", theme);
    }
    try {
      if (theme === "system") {
        localStorage.removeItem(STORAGE_KEY);
      } else {
        localStorage.setItem(STORAGE_KEY, theme);
      }
    } catch (e) {
      /* storage unavailable: the choice still applies for this page view */
    }
  }

  function sync(theme) {
    var icon = document.getElementById("themeIcon");
    var label = document.getElementById("themeLabel");

    document.querySelectorAll("[data-kinjo-theme]").forEach(function (btn) {
      var mine = btn.getAttribute("data-kinjo-theme") === theme;
      btn.classList.toggle("active", mine);
      btn.setAttribute("aria-current", mine ? "true" : "false");
      var tick = btn.querySelector(".bi-check2");
      if (tick) tick.classList.toggle("d-none", !mine);
      // Copy the already-translated label onto the trigger.
      if (mine && label) {
        label.textContent = (btn.textContent || "").trim();
      }
    });

    if (icon) {
      Object.keys(ICONS).forEach(function (k) {
        icon.classList.remove(ICONS[k]);
      });
      icon.classList.add(ICONS[theme] || ICONS.system);
    }
  }

  function init() {
    var current = read();
    apply(current);
    sync(current);

    document.querySelectorAll("[data-kinjo-theme]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var next = btn.getAttribute("data-kinjo-theme");
        apply(next);
        sync(next);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
