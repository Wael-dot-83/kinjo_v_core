/* static/js/core/i18n.js */
(function(window) {
  'use strict';

  class I18nManager {
    constructor() {
      this.translations = {};
      this.currentLang = document.documentElement.lang || 'en';
      this.isLoaded = false;
    }

    async init() {
      try {
        // Fetch translations for the current language
        const data = await window.dataFetcher.fetch(`/api/i18n/${this.currentLang}`);
        this.translations = data || {};
        this.isLoaded = true;
      } catch (e) {
        console.error("Failed to load translations, falling back to keys.", e);
        this.translations = {};
        this.isLoaded = true;
      }
    }

    _t(key, variables = {}) {
      let text = this.translations[key] || key;
      for (const [v, val] of Object.entries(variables)) {
        text = text.replace(new RegExp(`{${v}}`, 'g'), val);
      }
      return text;
    }
  }

  window.i18nManager = new I18nManager();
  
  // Global helper function to match Jinja's _t()
  window._t = function(key, fallback = null, variables = {}) {
    if (!window.i18nManager.isLoaded && fallback) return fallback;
    return window.i18nManager._t(key, variables) || fallback || key;
  };

  // Initialize on load
  document.addEventListener('DOMContentLoaded', () => {
    window.i18nManager.init();
  });
})(window);
