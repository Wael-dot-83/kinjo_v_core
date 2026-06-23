/**
 * KinJo API Timing Wrapper
 * Wraps global fetch() to collect API call timing metrics.
 * Reports (endpoint, method, status_code, duration_ms, cache_hit) to /api/telemetry/api.
 * Privacy-first: no query params in endpoint, no request/response bodies.
 */
(function () {
  "use strict";

  if (typeof window === "undefined") return;
  if (typeof window.fetch === "undefined") return;

  var CONFIG = {
    batchSize: 30,
    flushInterval: 15000,
    endpoint: "/api/telemetry/api",
    enabled: true,
    ignorePaths: ["/api/telemetry/", "/static/", "/ws/"],
  };

  function getConfig() {
    try {
      var dataConfig = document.querySelector("[data-telemetry-config]");
      if (dataConfig) {
        var parsed = JSON.parse(dataConfig.getAttribute("data-telemetry-config") || "{}");
        for (var k in parsed) {
          if (parsed.hasOwnProperty(k) && CONFIG.hasOwnProperty(k)) CONFIG[k] = parsed[k];
        }
      }
    } catch (e) {}
    return CONFIG;
  }

  var config = getConfig();
  var queue = [];
  var originalFetch = window.fetch;

  function getSessionId() {
    try {
      return (
        (window.KinjoWebVitals && window.KinjoWebVitals.getSessionId()) ||
        sessionStorage.getItem("kinjo_telemetry_sid") ||
        "unknown"
      );
    } catch (e) {
      return "unknown";
    }
  }

  function getRole() {
    try {
      return window.__KINJO_USER_ROLE__ || "ANONYMOUS";
    } catch (e) {
      return "ANONYMOUS";
    }
  }

  function extractEndpoint(input) {
    var url = "";
    if (typeof input === "string") {
      url = input;
    } else if (input && typeof input.url === "string") {
      url = input.url;
    }
    if (url.indexOf("?") !== -1) {
      url = url.split("?")[0];
    }
    if (url.indexOf("#") !== -1) {
      url = url.split("#")[0];
    }
    return url.substring(0, 255);
  }

  function shouldIgnore(endpoint) {
    for (var i = 0; i < config.ignorePaths.length; i++) {
      if (endpoint.indexOf(config.ignorePaths[i]) === 0) return true;
    }
    return false;
  }

  function recordApiCall(endpoint, method, statusCode, duration, cacheHit) {
    if (!config.enabled) return;
    if (shouldIgnore(endpoint)) return;

    queue.push({
      endpoint: endpoint,
      method: (method || "GET").toUpperCase(),
      status_code: statusCode,
      duration_ms: Math.round(duration * 10) / 10,
      cache_hit: cacheHit,
    });

    if (queue.length >= config.batchSize) {
      flush();
    }
  }

  function recordApiError(endpoint, method, duration) {
    if (!config.enabled) return;
    if (shouldIgnore(endpoint)) return;

    queue.push({
      endpoint: endpoint,
      method: (method || "GET").toUpperCase(),
      status_code: 0,
      duration_ms: Math.round(duration * 10) / 10,
      cache_hit: null,
    });
  }

  function flush() {
    if (queue.length === 0) return;
    var batch = queue.splice(0);
    var payload = {
      session_id: getSessionId(),
      role: getRole(),
      calls: batch,
    };

    try {
      if (navigator.sendBeacon) {
        var blob = new Blob([JSON.stringify(payload)], { type: "application/json" });
        navigator.sendBeacon(config.endpoint, blob);
      } else {
        originalFetch(config.endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          keepalive: true,
        });
      }
    } catch (e) {}
  }

  window.fetch = function () {
    var input = arguments[0];
    var init = arguments[1] || {};
    var endpoint = extractEndpoint(input);
    var method = ((init.method || (input && input.method) || "GET") + "").toUpperCase();
    var startTime = performance.now();

    return originalFetch.apply(this, arguments).then(
      function (response) {
        var duration = performance.now() - startTime;
        var cacheHit = null;
        try {
          var cacheStatus = response.headers.get("X-Cache");
          if (cacheStatus) {
            cacheHit = cacheStatus.toLowerCase().indexOf("hit") !== -1;
          }
        } catch (e) {}
        recordApiCall(endpoint, method, response.status, duration, cacheHit);
        return response;
      },
      function (error) {
        var duration = performance.now() - startTime;
        recordApiError(endpoint, method, duration);
        throw error;
      }
    );
  };

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

  setupFlush();

  window.KinjoApiTiming = {
    flush: flush,
    setEnabled: function (enabled) {
      config.enabled = enabled;
    },
  };
})();
