/**
 * chart_utils.js — shared Chart.js data helpers and lifecycle management.
 * Loaded before admin_dashboard.js and admin_analytics.js so both reuse one
 * implementation (avoids the previously duplicated safeChartData definition).
 * 
 * Batch 4 enhancements:
 * - CHART-021: Empty state handling
 * - CHART-023: Chart instance cleanup (memory leak prevention)
 * - CHART-024: RTL layout support
 */
(function (global) {
  "use strict";

  /**
   * Normalize an array for safe Chart.js consumption:
   * returns [] for non-arrays and replaces null/undefined entries with 0.
   * @param {Array} arr
   * @returns {Array}
   */
  function safeChartData(arr) {
    if (!Array.isArray(arr)) return [];
    return arr.map((v) => (v == null ? 0 : v));
  }

  /**
   * Check if data is empty (CHART-021: Empty state handling)
   * @param {Object} chartData - Chart.js data object with labels and datasets
   * @returns {boolean} True if data is empty or invalid
   */
  function isChartDataEmpty(chartData) {
    if (!chartData) return true;
    if (!chartData.labels || !Array.isArray(chartData.labels) || chartData.labels.length === 0) {
      return true;
    }
    if (!chartData.datasets || !Array.isArray(chartData.datasets) || chartData.datasets.length === 0) {
      return true;
    }
    // Check if all data values are zero or null
    const allZero = chartData.datasets.every(dataset => {
      if (!dataset.data || !Array.isArray(dataset.data)) return true;
      return dataset.data.every(v => v == null || v === 0);
    });
    return allZero;
  }

  /**
   * Display empty state message on chart canvas (CHART-021)
   * @param {HTMLCanvasElement} canvas - Chart canvas element
   * @param {string} message - Empty state message (default: bilingual)
   */
  function showEmptyState(canvas, message) {
    if (!canvas || !canvas.getContext) return;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    
    // Clear canvas
    ctx.clearRect(0, 0, width, height);
    
    // Draw empty state message
    ctx.fillStyle = '#6b7280';
    ctx.font = '14px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    
    const msg = message || (document.documentElement.lang === 'ar' 
      ? 'لا توجد بيانات متاحة' 
      : 'No data available');
    
    ctx.fillText(msg, width / 2, height / 2);
  }

  /**
   * Safely destroy a Chart.js instance to prevent memory leaks (CHART-023)
   * @param {Chart} chartInstance - Chart.js instance to destroy
   */
  function destroyChart(chartInstance) {
    if (chartInstance && typeof chartInstance.destroy === 'function') {
      try {
        chartInstance.destroy();
      } catch (e) {
        console.warn('Failed to destroy chart instance:', e);
      }
    }
  }

  /**
   * Get RTL-aware chart options (CHART-024)
   * @param {Object} baseOptions - Base chart options
   * @returns {Object} RTL-aware chart options
   */
  function getRTLAwareOptions(baseOptions) {
    const isRTL = document.documentElement.dir === 'rtl' || document.documentElement.lang === 'ar';
    
    const options = Object.assign({}, baseOptions);
    
    if (isRTL) {
      // Reverse legend position for RTL
      if (options.plugins && options.plugins.legend) {
        options.plugins.legend.position = options.plugins.legend.position === 'left' ? 'right' : 'left';
      }
      // Reverse x-axis for RTL
      if (options.scales && options.scales.x) {
        options.scales.x.reverse = true;
      }
    }
    
    return options;
  }

  /**
   * Create a chart with proper lifecycle management (CHART-021, CHART-023, CHART-024)
   * @param {HTMLCanvasElement} canvas - Chart canvas element
   * @param {Object} config - Chart.js configuration
   * @param {string} emptyMessage - Custom empty state message
   * @returns {Chart|null} Chart instance or null if data is empty
   */
  function createChartWithLifecycle(canvas, config, emptyMessage) {
    if (!canvas || typeof Chart === 'undefined') return null;
    
    // Check for empty data (CHART-021)
    if (isChartDataEmpty(config.data)) {
      showEmptyState(canvas, emptyMessage);
      return null;
    }
    
    // Destroy existing chart instance to prevent memory leaks (CHART-023)
    const existingChart = Chart.getChart(canvas);
    if (existingChart) {
      destroyChart(existingChart);
    }
    
    // Apply RTL-aware options (CHART-024)
    config.options = getRTLAwareOptions(config.options || {});
    
    // Create new chart
    return new Chart(canvas, config);
  }

  // Export functions
  global.safeChartData = safeChartData;
  global.isChartDataEmpty = isChartDataEmpty;
  global.showEmptyState = showEmptyState;
  global.destroyChart = destroyChart;
  global.getRTLAwareOptions = getRTLAwareOptions;
  global.createChartWithLifecycle = createChartWithLifecycle;
})(typeof window !== "undefined" ? window : this);
