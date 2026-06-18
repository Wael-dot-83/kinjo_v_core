/**
 * AnalyticsFilterState — Global shared filter state for admin analytics views.
 * Shared across dashboard, heatmap, and analytics pages.
 * Persists to localStorage; notifies subscribers on change.
 *
 * Properties:
 *   governorate  — string (governorate ID or "all"), default "all"
 *   indicator    — string (indicator key), default "risk_score"
 *   periodStart  — string (ISO date YYYY-MM-DD), default: first day of current month
 *   periodEnd    — string (ISO date YYYY-MM-DD), default: today
 *   source       — string ("dashboard" | "heatmap" | "analytics"), last changer
 *
 * DOM elements read/written by syncFromDOM / syncToDOM:
 *   #governorateFilter, #periodStart, #periodEnd, #heatmapIndicator
 */
(function () {
  'use strict';

  var STORAGE_KEY = 'kinjo_analytics_filter_state';

  function today() {
    return new Date().toISOString().slice(0, 10);
  }

  function firstOfMonth() {
    var d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-01';
  }

  var DEFAULTS = {
    governorate: 'all',
    indicator: 'risk_score',
    periodStart: firstOfMonth(),
    periodEnd: today(),
    source: ''
  };

  var state = Object.assign({}, DEFAULTS);
  var subscribers = [];

  try {
    var saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      var parsed = JSON.parse(saved);
      Object.keys(DEFAULTS).forEach(function (k) {
        if (parsed[k] !== undefined && parsed[k] !== null) {
          state[k] = parsed[k];
        }
      });
      if (isNaN(Date.parse(state.periodStart))) state.periodStart = DEFAULTS.periodStart;
      if (isNaN(Date.parse(state.periodEnd))) state.periodEnd = DEFAULTS.periodEnd;
    }
  } catch (e) {
    /* ignore corrupt storage */
  }

  function persist() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) {
      console.error('AnalyticsFilterState: Failed to persist state', e);
    }
  }

  function notify() {
    var snapshot = Object.assign({}, state);
    for (var i = 0; i < subscribers.length; i++) {
      try {
        subscribers[i](snapshot);
      } catch (e) {
        console.error('AnalyticsFilterState: Subscriber error', e);
      }
    }
  }

  /**
   * Read the current page language from the <html> lang attribute.
   * Returns 'ar' for Arabic, otherwise 'en'.
   */
  function getLang() {
    return (document.documentElement.lang || '').toLowerCase().startsWith('ar') ? 'ar' : 'en';
  }

  var api = {
    /** Returns a shallow copy of the current state. */
    getState: function () {
      return Object.assign({}, state);
    },

    /**
     * Merge updates into state, set the source tag, persist, and notify subscribers.
     * @param {Object} updates — partial state to merge
     * @param {string} source  — which view initiated the change
     * @returns {Object} new state snapshot
     */
    setState: function (updates, source) {
      if (updates && typeof updates === 'object') {
        Object.keys(updates).forEach(function (k) {
          if (k in DEFAULTS) {
            state[k] = updates[k];
          }
        });
      }
      if (source && typeof source === 'string') {
        state.source = source;
      }
      persist();
      notify();
      return api.getState();
    },

    /**
     * Register a callback invoked on every state change.
     * @param {Function} callback — receives a state snapshot
     * @returns {Function} unsubscribe function
     */
    subscribe: function (callback) {
      if (typeof callback === 'function') {
        subscribers.push(callback);
      }
      return function () {
        var idx = subscribers.indexOf(callback);
        if (idx > -1) subscribers.splice(idx, 1);
      };
    },

    /** Manually notify all subscribers with the current state. */
    notify: notify,

    /**
     * Read filter values from DOM elements and update internal state.
     * DOM IDs: governorateFilter, periodStart, periodEnd, heatmapIndicator
     * @returns {Object} new state snapshot
     */
    syncFromDOM: function () {
      var gov = document.getElementById('governorateFilter');
      var heatGov = document.getElementById('heatmapGovFilter');
      var pStart = document.getElementById('periodStart');
      var pEnd = document.getElementById('periodEnd');
      var indicator = document.getElementById('heatmapIndicator');

      var updates = {};
      if (gov && gov.value) updates.governorate = gov.value;
      if (heatGov && heatGov.value) updates.governorate = heatGov.value;
      if (pStart && pStart.value) updates.periodStart = pStart.value;
      if (pEnd && pEnd.value) updates.periodEnd = pEnd.value;
      if (indicator && indicator.value) updates.indicator = indicator.value;

      if (Object.keys(updates).length > 0) {
        state = Object.assign(state, updates);
        persist();
      }
      return api.getState();
    },

    /**
     * Write internal state back to DOM elements and dispatch change events
     * so other listeners react.
     */
    syncToDOM: function () {
      var gov = document.getElementById('governorateFilter');
      var heatGov = document.getElementById('heatmapGovFilter');
      var pStart = document.getElementById('periodStart');
      var pEnd = document.getElementById('periodEnd');
      var indicator = document.getElementById('heatmapIndicator');

      if (gov) gov.value = state.governorate;
      if (heatGov) heatGov.value = state.governorate;
      if (pStart) pStart.value = state.periodStart;
      if (pEnd) pEnd.value = state.periodEnd;
      if (indicator) indicator.value = state.indicator;

      [gov, heatGov, pStart, pEnd, indicator].forEach(function (el) {
        if (el) {
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }
      });
    },

    /**
     * Build a URL query string from the current state.
     * Omits governorate when it is "all".
     * @returns {string} e.g. "governorate=2&period_start=2026-01-01&period_end=2026-06-16&indicator=risk_score"
     */
    toQueryParams: function () {
      var params = [];
      if (state.governorate && state.governorate !== 'all') {
        params.push('governorate=' + encodeURIComponent(state.governorate));
      }
      params.push('period_start=' + encodeURIComponent(state.periodStart));
      params.push('period_end=' + encodeURIComponent(state.periodEnd));
      if (state.indicator) {
        params.push('indicator=' + encodeURIComponent(state.indicator));
      }
      return params.join('&');
    },

    /**
     * Reset state to defaults (recalculates today / first-of-month),
     * persist, and notify subscribers.
     * @returns {Object} new state snapshot
     */
    reset: function () {
      state = Object.assign({}, DEFAULTS, {
        periodStart: firstOfMonth(),
        periodEnd: today(),
        source: ''
      });
      persist();
      notify();
      return api.getState();
    },

    /** Returns 'ar' or 'en' based on <html> lang attribute. */
    getLang: getLang
  };

  window.AnalyticsFilterState = api;
})();
