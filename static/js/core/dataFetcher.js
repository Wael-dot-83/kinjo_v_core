/* static/js/core/dataFetcher.js */
(function(window) {
  'use strict';

  class DataFetcher {
    constructor() {
      this.cache = new Map();
      this.defaultTTL = 5 * 60 * 1000; // 5 minutes cache for read-only
      this.csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    }

    async fetch(url, options = {}, retries = 3, backoff = 300) {
      const isReadOnly = !options.method || options.method.toUpperCase() === 'GET';
      const cacheKey = url;

      if (isReadOnly && this.cache.has(cacheKey)) {
        const cached = this.cache.get(cacheKey);
        if (Date.now() - cached.timestamp < this.defaultTTL) {
          return cached.data;
        }
      }

      const fetchOptions = {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': this.csrfToken,
          ...(options.headers || {})
        }
      };

      try {
        const response = await window.fetch(url, fetchOptions);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const contentType = response.headers.get("content-type");
        if (contentType && contentType.indexOf("application/json") !== -1) {
          const data = await response.json();
          if (isReadOnly) {
            this.cache.set(cacheKey, { data, timestamp: Date.now() });
          }
          return data;
        } else {
          return await response.text();
        }
      } catch (error) {
        if (retries > 0 && isReadOnly) {
          await new Promise(res => setTimeout(res, backoff));
          return this.fetch(url, options, retries - 1, backoff * 2);
        }
        throw error;
      }
    }

    clearCache(url = null) {
      if (url) {
        this.cache.delete(url);
      } else {
        this.cache.clear();
      }
    }
  }

  window.dataFetcher = new DataFetcher();
})(window);
