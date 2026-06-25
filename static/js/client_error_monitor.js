/**
 * KinJo Client Error Monitor
 * Captures uncaught JS exceptions and unhandled promise rejections.
 * Reports sanitized errors (no stack traces, no PII) to /api/telemetry/errors.
 */
(function () {
  "use strict";

  if (typeof window === "undefined") return;

  var CONFIG = {
    endpoint: "/api/telemetry/errors",
    enabled: true,
    maxQueueSize: 50,
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

  function sanitize(message) {
    if (!message) return "Unknown error";
    var sanitized = String(message);
    sanitized = sanitized.replace(/file:\/\/[^\s]+/g, "[path]");
    sanitized = sanitized.replace(/https?:\/\/[^\s]+/g, "[url]");
    sanitized = sanitized.replace(
      /\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b/g,
      "[email]"
    );
    sanitized = sanitized.replace(/\b\d{4}-\d{2}-\d{2}\b/g, "[date]");
    return sanitized.substring(0, 500);
  }

  function hashStack(stack) {
    if (!stack) return null;
    var frames = stack.split("\n").slice(0, 2).join("\n");
    var hash = 0;
    for (var i = 0; i < frames.length; i++) {
      var chr = frames.charCodeAt(i);
      hash = (hash << 5) - hash + chr;
      hash |= 0;
    }
    return Math.abs(hash).toString(16).padStart(8, "0").substring(0, 8);
  }

  function report(type, event) {
    if (!config.enabled) return;

    var message = "";
    var stackHash = null;

    if (type === "uncaught" && event && event.message) {
      message = event.message;
      if (event.error && event.error.stack) {
        stackHash = hashStack(event.error.stack);
      }
    } else if (type === "rejection" && event && event.reason) {
      if (typeof event.reason === "string") {
        message = event.reason;
      } else if (event.reason && event.reason.message) {
        message = event.reason.message;
        if (event.reason.stack) {
          stackHash = hashStack(event.reason.stack);
        }
      } else {
        message = "Unhandled promise rejection";
      }
    }

    var payload = {
      session_id: getSessionId(),
      page: getPagePath(),
      role: getRole(),
      error_type: type,
      message: sanitize(message),
      stack_hash: stackHash,
      timestamp_ms: Date.now(),
    };

    try {
      var body = JSON.stringify(payload);
      if (navigator.sendBeacon) {
        var blob = new Blob([body], { type: "application/json" });
        var sent = navigator.sendBeacon(config.endpoint, blob);
        if (!sent) {
          queueForRetry(payload);
        }
      } else {
        fetch(config.endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: body,
          keepalive: true,
        }).catch(function () {
          queueForRetry(payload);
        });
      }
    } catch (e) {
      queueForRetry(payload);
    }
  }

  function queueForRetry(payload) {
    try {
      var queued = JSON.parse(localStorage.getItem("kinjo_error_queue") || "[]");
      queued.push(payload);
      if (queued.length > config.maxQueueSize) {
        queued = queued.slice(queued.length - config.maxQueueSize);
      }
      localStorage.setItem("kinjo_error_queue", JSON.stringify(queued));
    } catch (e) {}
  }

  function flushQueue() {
    try {
      var queued = JSON.parse(localStorage.getItem("kinjo_error_queue") || "[]");
      if (queued.length === 0) return;

      for (var i = 0; i < queued.length; i++) {
        var body = JSON.stringify(queued[i]);
        navigator.sendBeacon(config.endpoint, body);
      }
      localStorage.removeItem("kinjo_error_queue");
    } catch (e) {}
  }

  function init() {
    window.addEventListener("error", function (event) {
      // Filter out Cesium web-worker importScripts failures and other
      // resource-loading errors that have no JS Error object (e.error === null).
      // These are non-fatal and already logged by the browser console.
      if (!event.error) return;
      if (event.message && /importScripts|blob:/i.test(event.message)) return;
      report("uncaught", event);
    });

    window.addEventListener("unhandledrejection", function (event) {
      report("rejection", event);
    });

    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") {
        flushQueue();
      }
    });

    if (navigator.onLine) {
      setTimeout(flushQueue, 3000);
    }

    window.addEventListener("online", flushQueue);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.KinjoErrorMonitor = {
    setEnabled: function (enabled) {
      config.enabled = enabled;
    },
    flush: flushQueue,
  };
})();
