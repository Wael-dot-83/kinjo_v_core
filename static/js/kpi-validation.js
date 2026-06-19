/**
 * KPI Dashboard Centralized Validation & Formatting Utilities
 * Handles data quality, Arabic encoding, percentage clamping, and state management.
 */

(function () {
  "use strict";

  // Valid UTF-8 Arabic character range
  const ARABIC_CHAR_PATTERN = /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/;

  window.KpiValidation = {
    /**
     * Check if text contains corrupted Arabic (replacement chars or excessive question marks)
     */
    containsCorruptedArabic: function (value) {
      if (typeof value !== "string") return false;
      if (value.includes("\uFFFD")) return true;
      if (/\?{3,}/.test(value)) return true;
      return false;
    },

    /**
     * Clamp a numeric value to valid range
     */
    clamp: function (value, min, max) {
      if (min === undefined) min = 0;
      if (max === undefined) max = 100;
      const numeric = Number(value);
      if (!Number.isFinite(numeric)) return { valid: false, value: null };
      if (numeric < min) return { valid: false, value: min };
      if (numeric > max) return { valid: false, value: max };
      return { valid: true, value: numeric };
    },

    /**
     * Validate if a string contains valid UTF-8 Arabic text (not corrupted)
     */
    isValidArabicText: function (text) {
      if (text == null) return true;
      if (typeof text !== "string") return true;
      if (text === "") return true;
      if (text.includes("\uFFFD")) return false;
      if ((text.match(/\?/g) || []).length > 2) return false;
      return true;
    },

    /**
     * Detect and sanitize corrupted text
     */
    sanitizeCorruptedText: function (text, fallback) {
      if (fallback === undefined) fallback = "غير متاح";
      if (this.isValidArabicText(text)) return text;
      return fallback;
    },

    /**
     * Validate KPI value - ensures percentages are valid, counts are non-negative
     */
    validateKpiValue: function (value, type) {
      if (type === undefined) type = "percent";
      const numeric = Number(value);

      if (!Number.isFinite(numeric)) {
        return { valid: false, reason: "invalid_number", value: null };
      }

      if (type === "percent") {
        if (numeric < 0) {
          return { valid: false, reason: "negative_percent", value: 0 };
        }
        if (numeric > 100) {
          return { valid: false, reason: "overflow_percent", value: 100 };
        }
        return { valid: true, value: numeric };
      }

      if (type === "count") {
        if (numeric < 0) {
          return { valid: false, reason: "negative_count", value: 0 };
        }
        return { valid: true, value: Math.round(numeric) };
      }

      if (type === "rate") {
        if (numeric < 0) {
          return { valid: false, reason: "negative_rate", value: 0 };
        }
        return { valid: true, value: numeric };
      }

      return { valid: true, value: numeric };
    },

    /**
     * Validate forecast metric - percentage forecasts must be 0-100, counts non-negative
     */
    validateForecastMetric: function (forecastData, metricType) {
      const value = Number(forecastData?.value);
      const lower = Number(forecastData?.confidence?.lower?.slice(-1)?.[0]?.value ?? 0);
      const upper = Number(forecastData?.confidence?.upper?.slice(-1)?.[0]?.value ?? 0);

      if (!Number.isFinite(value)) {
        return { valid: false, message: "التوقع غير متاح", reason: "no_data" };
      }

      if (metricType === "attendance" || metricType === "enrollment") {
        if (value < 0 || value > 100) {
          return {
            valid: false,
            message: "قيمة غير صالحة: التوقع خارج النطاق 0% إلى 100%",
            reason: "out_of_range_percent"
          };
        }
        if (lower < 0 || upper > 100) {
          return {
            valid: false,
            message: "نطاق ثقة غير صالح",
            reason: "confidence_out_of_range"
          };
        }
      }

      if (metricType === "incidents") {
        if (value < 0 || lower < 0 || upper < 0) {
          return {
            valid: false,
            message: "قيمة غير صالحة: التوقع سالب",
            reason: "negative_value"
          };
        }
      }

      return { valid: true, message: null };
    },

    /**
     * Classify governance score into categories
     */
    classifyGovernanceScore: function (score) {
      const value = Number(score);
      if (!Number.isFinite(value)) return "unknown";
      if (value >= 85) return "excellent";
      if (value >= 60) return "medium";
      return "needs_improvement";
    },

    /**
     * Format a percentage value safely
     */
    formatPercent: function (value, decimals) {
      if (decimals === undefined) decimals = 1;
      const result = this.validateKpiValue(value, "percent");
      if (!result.valid) return "--";
      return result.value.toFixed(decimals) + "%";
    },

    /**
     * Format a count value safely
     */
    formatCount: function (value) {
      const result = this.validateKpiValue(value, "count");
      if (!result.valid) return "--";
      return String(result.value);
    },

    /**
     * CSV escape to prevent injection
     */
    escapeCsv: function (value) {
      if (value == null) return "";
      const str = String(value);
      if (/^[=+\-@\t\r\n]/.test(str)) {
        return "'" + str;
      }
      if (/[,"\r\n]/.test(str)) {
        return '"' + str.replace(/"/g, '""') + '"';
      }
      return str;
    },

    /**
     * Generate UTF-8 BOM for Excel compatibility
     */
    csvWithUtf8Bom: function (content) {
      return "\uFEFF" + content;
    },
  };

  window.KpiValidation.validateForecastMetric = function (forecastData, metricType) {
    const lastPoint = forecastData?.forecast_points?.slice(-1)?.[0];
    const value = Number(forecastData?.value ?? lastPoint?.value);
    const lowerPoint = forecastData?.confidence?.lower?.slice(-1)?.[0];
    const upperPoint = forecastData?.confidence?.upper?.slice(-1)?.[0];
    const lower = lowerPoint ? Number(lowerPoint.value) : null;
    const upper = upperPoint ? Number(upperPoint.value) : null;

    if (!Number.isFinite(value)) {
      return { valid: false, message: "غير متاح", reason: "no_data" };
    }

    if (metricType === "attendance") {
      if (value < 0 || value > 100) {
        return { valid: false, message: "خارج النطاق المتوقع", reason: "out_of_range_percent" };
      }
      if (
        (lower !== null && (!Number.isFinite(lower) || lower < 0 || lower > 100)) ||
        (upper !== null && (!Number.isFinite(upper) || upper < 0 || upper > 100))
      ) {
        return { valid: false, message: "نطاق الثقة غير صالح", reason: "confidence_out_of_range" };
      }
    }

    if (metricType === "incidents" || metricType === "enrollment") {
      if (
        value < 0 ||
        (lower !== null && (!Number.isFinite(lower) || lower < 0)) ||
        (upper !== null && (!Number.isFinite(upper) || upper < 0))
      ) {
        return { valid: false, message: "قيمة غير صالحة", reason: "negative_value" };
      }
    }

    return { valid: true, message: null, value: value };
  };

  // Global helper for use in templates
  window.formatValue = function (value, type) {
    if (type === undefined) type = "percent";
    return window.KpiValidation.formatPercent(value);
  };

  window.formatCount = function (value) {
    return window.KpiValidation.formatCount(value);
  };
})();
