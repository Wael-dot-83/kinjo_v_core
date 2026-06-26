(function () {
  "use strict";

  if (window.__kinjoPageLoadTimerInstalled) return;
  window.__kinjoPageLoadTimerInstalled = true;

  // Auth pages are simple forms — no need for a loading timer.
  const _authPages = ["/login", "/register", "/mfa", "/change-password", "/forgot-password", "/reset-password"];
  if (_authPages.some(function (p) { return window.location.pathname.startsWith(p); })) return;

  const QUIET_PERIOD_MS = 350;
  const SHOW_DELAY_MS = 180;
  const REFRESH_MS = 100;

  const state = {
    domReady: document.readyState !== "loading",
    pageReady: document.readyState === "complete",
    pendingNetwork: 0,
    pendingTasks: 0,
    cycleStart: now(),
    activeSince: now(),
    lastActivity: now(),
    finished: false,
    progress: 0.06,
    tickId: null,
  };

  function now() {
    return typeof performance !== "undefined" && performance.now ? performance.now() : Date.now();
  }

  function currentLang() {
    const lang = (document.documentElement.lang || "ar").toLowerCase();
    return lang.startsWith("en") ? "en" : "ar";
  }

  function labels() {
    if (currentLang() === "en") {
      return {
        loading: "Loading data",
        done: "Loaded in",
        idle: "Ready",
      };
    }
    return {
      loading:
        "\u062c\u0627\u0631 \u062a\u062d\u0645\u064a\u0644 \u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a",
      done: "\u0627\u0643\u062a\u0645\u0644 \u062e\u0644\u0627\u0644",
      idle: "\u062c\u0627\u0647\u0632",
    };
  }

  function formatSeconds(milliseconds) {
    const seconds = (milliseconds / 1000).toFixed(2);
    return currentLang() === "en" ? `${seconds}s` : `${seconds} ثانية`;
  }

  function totalPending() {
    return state.pendingNetwork + state.pendingTasks;
  }

  function loadingActive() {
    return !state.domReady || !state.pageReady || totalPending() > 0;
  }

  function loadingVisible() {
    if (!loadingActive()) return false;
    if (!state.finished) return true;
    return now() - state.activeSince >= SHOW_DELAY_MS;
  }

  function setBusyState(isBusy) {
    const targets = document.querySelectorAll("main, #mainContent, .admin-content");
    targets.forEach((element) => {
      element.setAttribute("aria-busy", isBusy ? "true" : "false");
    });
  }

  function ensureStyles() {
    if (document.getElementById("pageLoadTimerStyles")) return;

    const style = document.createElement("style");
    style.id = "pageLoadTimerStyles";
    style.textContent = `
      .page-load-timer {
        --page-load-progress: 0;
        position: fixed;
        top: calc(env(safe-area-inset-top, 0px) + 0.6rem);
        inset-inline-end: 1rem;
        z-index: 13000;
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.45rem 0.75rem;
        border-radius: 999px;
        color: #fff;
        font-size: 0.83rem;
        font-weight: 600;
        line-height: 1;
        box-shadow: 0 10px 24px rgba(15, 23, 42, 0.22);
        backdrop-filter: blur(10px);
        transition: background-color 0.2s ease, box-shadow 0.2s ease, opacity 0.5s ease;
        pointer-events: none;
        opacity: 1;
      }
      .page-load-timer.is-hidden {
        opacity: 0;
        pointer-events: none;
      }
      .page-load-timer__bar {
        position: fixed;
        top: 0;
        inset-inline: 0;
        height: 3px;
        z-index: 12990;
        background: rgba(15, 23, 42, 0.08);
        pointer-events: none;
      }
      .page-load-timer__bar-fill {
        display: block;
        width: 100%;
        height: 100%;
        transform: scaleX(var(--page-load-progress));
        transform-origin: left center;
        transition: transform 0.16s ease, background-color 0.2s ease;
      }
      html[dir="rtl"] .page-load-timer__bar-fill {
        transform-origin: right center;
      }
      .page-load-timer.is-loading {
        background: rgba(31, 94, 71, 0.92);
      }
      .page-load-timer.is-loading .page-load-timer__bar-fill {
        background: linear-gradient(90deg, #4F46E5 0%, #0EA5E9 100%);
      }
      .page-load-timer.is-done {
        background: rgba(22, 163, 74, 0.9);
      }
      .page-load-timer.is-done .page-load-timer__bar-fill {
        background: linear-gradient(90deg, #16a34a 0%, #22c55e 100%);
      }
      .page-load-timer.is-idle {
        background: rgba(51, 65, 85, 0.9);
      }
      .page-load-timer.is-idle .page-load-timer__bar-fill {
        background: linear-gradient(90deg, #64748b 0%, #94a3b8 100%);
      }
      .page-load-timer__dot {
        width: 0.44rem;
        height: 0.44rem;
        border-radius: 999px;
        background: currentColor;
      }
      .page-load-timer.is-loading .page-load-timer__dot {
        animation: page-load-timer-pulse 1s ease-in-out infinite;
      }
      .page-load-timer__value {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        min-width: 3.9rem;
        text-align: end;
      }
      @keyframes page-load-timer-pulse {
        0%, 100% { transform: scale(1); opacity: 1; }
        50% { transform: scale(1.35); opacity: 0.75; }
      }
      @media (max-width: 576px) {
        .page-load-timer {
          top: calc(env(safe-area-inset-top, 0px) + 0.5rem);
          inset-inline-end: 0.7rem;
          font-size: 0.78rem;
          padding: 0.4rem 0.58rem;
          gap: 0.36rem;
        }
        .page-load-timer__value {
          min-width: 3.45rem;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function ensureElement() {
    let root = document.getElementById("pageLoadTimer");
    if (root) return root;
    if (!document.body) return null;

    ensureStyles();
    root = document.createElement("div");
    root.id = "pageLoadTimer";
    root.className = "page-load-timer is-loading";
    root.setAttribute("role", "status");
    root.setAttribute("aria-live", "polite");
    root.innerHTML = `
      <div class="page-load-timer__bar" aria-hidden="true">
        <span class="page-load-timer__bar-fill"></span>
      </div>
      <span class="page-load-timer__dot" aria-hidden="true"></span>
      <span class="page-load-timer__label"></span>
      <span class="page-load-timer__value"></span>
    `;
    document.body.appendChild(root);
    return root;
  }

  function refreshProgress(isActive) {
    if (isActive) {
      const elapsed = now() - state.cycleStart;
      const target = Math.min(0.92, 0.12 + Math.log1p(Math.max(elapsed, 1) / 220) * 0.24);
      state.progress = Math.max(state.progress, target);
      return;
    }
    if (state.finished) {
      state.progress = 1;
      return;
    }
    state.progress = 0.06;
  }

  function updateElement() {
    const root = ensureElement();
    if (!root) return;

    const showLoading = loadingVisible();
    const elapsed = now() - state.cycleStart;
    const text = labels();
    const label = root.querySelector(".page-load-timer__label");
    const value = root.querySelector(".page-load-timer__value");

    refreshProgress(showLoading);

    if (label) {
      if (showLoading) {
        label.textContent = text.loading;
      } else if (state.finished) {
        label.textContent = text.done;
      } else {
        label.textContent = text.idle;
      }
    }
    if (value) {
      value.textContent = formatSeconds(elapsed);
    }

    root.style.setProperty("--page-load-progress", String(state.progress));
    root.classList.toggle("is-loading", showLoading);
    root.classList.toggle("is-done", !showLoading && state.finished);
    root.classList.toggle("is-idle", !showLoading && !state.finished);
    root.setAttribute("aria-busy", showLoading ? "true" : "false");
    setBusyState(showLoading);
  }

  function startCycle() {
    const startAt = now();
    state.cycleStart = startAt;
    state.activeSince = startAt;
    state.lastActivity = startAt;
    state.finished = false;
    state.progress = 0.08;
    // Re-show badge when a new load cycle starts.
    const root = document.getElementById("pageLoadTimer");
    if (root) root.classList.remove("is-hidden");
    updateElement();
  }

  function tryFinishCycle() {
    if (state.finished) return;
    if (!state.domReady || !state.pageReady) return;
    if (totalPending() > 0) return;
    if (now() - state.lastActivity < QUIET_PERIOD_MS) return;

    state.finished = true;
    state.progress = 1;
    updateElement();

    // Auto-hide: show "done" briefly, then fade out entirely.
    window.setTimeout(function () {
      const root = document.getElementById("pageLoadTimer");
      if (root) root.classList.add("is-hidden");
    }, 1400);
  }

  function startPendingWork(setter) {
    const wasIdle = totalPending() === 0;
    setter();
    if (wasIdle) {
      state.activeSince = now();
      if (state.finished) {
        startCycle();
        return;
      }
    }
    state.lastActivity = now();
    updateElement();
  }

  function onNetworkStart() {
    startPendingWork(() => {
      state.pendingNetwork += 1;
    });
  }

  function onNetworkEnd() {
    state.pendingNetwork = Math.max(0, state.pendingNetwork - 1);
    state.lastActivity = now();
    updateElement();
    tryFinishCycle();
  }

  function installFetchTracking() {
    if (typeof window.fetch !== "function" || window.fetch.__kinjoTimerWrapped) return;

    const originalFetch = window.fetch.bind(window);
    const wrappedFetch = function (...args) {
      onNetworkStart();
      return originalFetch(...args).finally(onNetworkEnd);
    };
    wrappedFetch.__kinjoTimerWrapped = true;
    window.fetch = wrappedFetch;
  }

  function installXhrTracking() {
    if (!window.XMLHttpRequest || XMLHttpRequest.prototype.__kinjoTimerWrapped) return;

    const originalSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function (...args) {
      onNetworkStart();
      this.addEventListener("loadend", onNetworkEnd, { once: true });
      return originalSend.apply(this, args);
    };
    XMLHttpRequest.prototype.__kinjoTimerWrapped = true;
  }

  function installLifecycleHooks() {
    document.addEventListener("DOMContentLoaded", () => {
      state.domReady = true;
      ensureElement();
      tryFinishCycle();
      updateElement();
    });

    window.addEventListener("load", () => {
      state.pageReady = true;
      state.lastActivity = now();
      tryFinishCycle();
      updateElement();
    });

    document.addEventListener("visibilitychange", () => {
      updateElement();
    });
  }

  function installManualApi() {
    window.PageLoadTimer = {
      startTask() {
        startPendingWork(() => {
          state.pendingTasks += 1;
        });

        let ended = false;
        return function endTask() {
          if (ended) return;
          ended = true;
          state.pendingTasks = Math.max(0, state.pendingTasks - 1);
          state.lastActivity = now();
          updateElement();
          tryFinishCycle();
        };
      },

      wrapPromise(promiseLike) {
        const endTask = this.startTask();
        return Promise.resolve(promiseLike).finally(endTask);
      },

      markDone() {
        state.pendingTasks = 0;
        state.pendingNetwork = 0;
        state.domReady = true;
        state.pageReady = true;
        state.lastActivity = now() - QUIET_PERIOD_MS;
        tryFinishCycle();
        updateElement();
      },

      reset() {
        startCycle();
      },
    };
  }

  function startTick() {
    if (state.tickId) clearInterval(state.tickId);
    state.tickId = window.setInterval(() => {
      updateElement();
      tryFinishCycle();
    }, REFRESH_MS);
  }

  installFetchTracking();
  installXhrTracking();
  installLifecycleHooks();
  installManualApi();
  startCycle();
  startTick();
})();
