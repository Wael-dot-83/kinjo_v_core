/**
 * KinJo Web Vitals Collector
 * Collects LCP, FID, CLS via PerformanceObserver and submits to /api/telemetry/vitals.
 * Privacy-first: no PII, anonymous session hash, route path only.
 */
(function () {
  "use strict";

  if (typeof window === "undefined") return;

  var CONFIG = {
    batchSize: typeof CONFIG_BATCH !== "undefined" ? CONFIG_BATCH : 20,
    flushInterval: typeof CONFIG_INTERVAL !== "undefined" ? CONFIG_INTERVAL : 10000,
    endpoint: "/api/telemetry/vitals",
    enabled: true,
  };

  function getConfig() {
    try {
      var dataConfig = document.querySelector("[data-telemetry-config]");
      if (dataConfig) {
        var parsed = JSON.parse(dataConfig.getAttribute("data-telemetry-config") || "{}");
        for (var k in parsed) {
          if (parsed.hasOwnProperty(k)) CONFIG[k] = parsed[k];
        }
      }
    } catch (e) {}
    return CONFIG;
  }

  var config = getConfig();
  var queue = [];
  var sessionId = generateSessionId();

  function generateSessionId() {
    try {
      var stored = sessionStorage.getItem("kinjo_telemetry_sid");
      if (stored) return stored;
    } catch (e) {}
    var sid =
      "s_" +
      Math.random().toString(36).substring(2, 15) +
      Date.now().toString(36);
    try {
      sessionStorage.setItem("kinjo_telemetry_sid", sid);
    } catch (e) {}
    return sid;
  }

  function getPagePath() {
    try {
      return window.location.pathname || "/";
    } catch (e) {
      return "/";
    }
  }

  function getRole() {
    try {
      return window.__KINJO_USER_ROLE__ || "ANONYMOUS";
    } catch (e) {
      return "ANONYMOUS";
    }
  }

  function getLang() {
    try {
      return document.documentElement.lang || "ar";
    } catch (e) {
      return "ar";
    }
  }

  function getDirection() {
    try {
      return document.documentElement.dir || "rtl";
    } catch (e) {
      return "rtl";
    }
  }

  function rateLCP(ms) {
    if (ms <= 2500) return "good";
    if (ms <= 4000) return "needs-improvement";
    return "poor";
  }

  function rateFID(ms) {
    if (ms <= 100) return "good";
    if (ms <= 300) return "needs-improvement";
    return "poor";
  }

  function rateCLS(value) {
    if (value <= 0.1) return "good";
    if (value <= 0.25) return "needs-improvement";
    return "poor";
  }

  function track(name, payload) {
    if (!config.enabled) return;
    queue.push({
      name: name,
      value: payload.value,
      rating: payload.rating,
      timestamp_ms: payload.timestamp_ms || Date.now(),
    });
    if (queue.length >= config.batchSize) {
      flush();
    }
  }

  function flush() {
    if (queue.length === 0) return;
    var batch = queue.splice(0);
    var body = JSON.stringify({
      session_id: sessionId,
      page: getPagePath(),
      role: getRole(),
      lang: getLang(),
      direction: getDirection(),
      metrics: batch,
    });

    try {
      if (navigator.sendBeacon) {
        var blob = new Blob([body], { type: "application/json" });
        navigator.sendBeacon(config.endpoint, blob);
      } else {
        fetch(config.endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: body,
          keepalive: true,
        });
      }
    } catch (e) {}
  }

  function observeLCP() {
    if (!("PerformanceObserver" in window)) return;
    try {
      var observer = new PerformanceObserver(function (entryList) {
        var entries = entryList.getEntries();
        if (entries.length === 0) return;
        var lastEntry = entries[entries.length - 1];
        track("lcp", {
          value: lastEntry.startTime,
          rating: rateLCP(lastEntry.startTime),
        });
      });
      observer.observe({ type: "largest-contentful-paint", buffered: true });
    } catch (e) {}
  }

  function observeFID() {
    if (!("PerformanceObserver" in window)) return;
    try {
      var observer = new PerformanceObserver(function (entryList) {
        var entries = entryList.getEntries();
        if (entries.length === 0) return;
        var first = entries[0];
        var fid = first.processingStart - first.startTime;
        track("fid", {
          value: fid,
          rating: rateFID(fid),
        });
      });
      observer.observe({ type: "first-input", buffered: true });
    } catch (e) {}
  }

  function observeCLS() {
    if (!("PerformanceObserver" in window)) return;
    var clsValue = 0;
    try {
      var observer = new PerformanceObserver(function (entryList) {
        for (var i = 0; i < entryList.getEntries().length; i++) {
          var entry = entryList.getEntries()[i];
          if (!entry.hadRecentInput) {
            clsValue += entry.value;
            track("cls", {
              value: clsValue,
              rating: rateCLS(clsValue),
            });
          }
        }
      });
      observer.observe({ type: "layout-shift", buffered: true });
    } catch (e) {}
  }

  function setupFlush() {
    setInterval(function () {
      flush();
    }, config.flushInterval);

    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") {
        flush();
      }
    });

    window.addEventListener("beforeunload", function () {
      flush();
    });
  }

  function init() {
    observeLCP();
    observeFID();
    observeCLS();
    setupFlush();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.KinjoWebVitals = {
    flush: flush,
    getSessionId: function () {
      return sessionId;
    },
    setEnabled: function (enabled) {
      config.enabled = enabled;
    },
  };
})();
