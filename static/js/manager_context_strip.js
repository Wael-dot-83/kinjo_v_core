/**
 * Manager Kindergarten Context Strip — hydration.
 *
 * The kindergarten name is already server-rendered. This script only supplies
 * the two things the server cannot state truthfully at render time:
 *
 *   1. the enrolled-child count (kindergartens.current_child_count is NULL in
 *      this dataset, so the authoritative number comes from
 *      /api/manager/dashboard -> summary.active_enrollments)
 *   2. the sync state, which reports whether that data actually arrived
 *
 * The response is cached in sessionStorage so navigating between manager pages
 * costs one request per session rather than one per page. On any failure the
 * count stays hidden and the dot goes to "stale" — the strip never displays a
 * number it did not receive.
 */
(function () {
  "use strict";

  var CACHE_KEY = "kinjo_manager_context";
  var MAX_AGE_MS = 5 * 60 * 1000; // beyond this, the cached count reads as stale

  function el(root, attr) {
    return root.querySelector("[" + attr + "]");
  }

  function isEnglish() {
    return (document.documentElement.lang || "ar").toLowerCase().indexOf("en") === 0;
  }

  function t(ar, en) {
    return isEnglish() ? en : ar;
  }

  function setSync(strip, state) {
    var dot = el(strip, "data-strip-sync-dot");
    var text = el(strip, "data-strip-sync-text");
    if (!dot || !text) return;
    dot.className = "strip-sync-dot " + state;
    if (state === "synced") {
      text.textContent = t("محدّث", "Current");
    } else if (state === "pending") {
      text.textContent = t("جارٍ التحقق من البيانات…", "Checking data…");
    } else {
      text.textContent = t("بيانات قديمة", "Data may be stale");
    }
  }

  function setCount(strip, count) {
    if (typeof count !== "number" || !isFinite(count) || count < 0) return false;
    var wrap = el(strip, "data-strip-children");
    var value = el(strip, "data-strip-children-count");
    if (!wrap || !value) return false;
    // toLocaleString so Arabic renders Arabic-Indic digits like the rest of the UI.
    value.textContent = count.toLocaleString(isEnglish() ? "en" : "ar-JO");
    wrap.classList.remove("d-none");
    return true;
  }

  function readCache() {
    try {
      var raw = sessionStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (!parsed || typeof parsed.count !== "number" || !parsed.at) return null;
      return parsed;
    } catch (e) {
      return null;
    }
  }

  function writeCache(count) {
    try {
      sessionStorage.setItem(CACHE_KEY, JSON.stringify({ count: count, at: Date.now() }));
    } catch (e) {
      /* sessionStorage unavailable (private mode / quota) — not fatal */
    }
  }

  function hydrate(strip) {
    var cached = readCache();
    if (cached && setCount(strip, cached.count)) {
      // Show cached data immediately, but be honest about its age.
      setSync(strip, Date.now() - cached.at < MAX_AGE_MS ? "synced" : "stale");
      if (Date.now() - cached.at < MAX_AGE_MS) return;
    }

    fetch("/api/manager/dashboard", {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        var summary = (data && data.summary) || {};
        var count = summary.active_enrollments;
        if (setCount(strip, count)) {
          writeCache(count);
          setSync(strip, "synced");
        } else {
          // Endpoint answered but without a usable count — don't invent one.
          setSync(strip, "stale");
        }
      })
      .catch(function () {
        setSync(strip, "stale");
      });
  }

  function init() {
    var strip = document.querySelector("[data-manager-context-strip]");
    if (strip) hydrate(strip);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
