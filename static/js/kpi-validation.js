/**
 * KPI Dashboard Centralized Validation & Formatting Utilities
 * Handles data quality, Arabic encoding, percentage clamping, and state management.
 */

(function () {
  "use strict";

  // Valid ASCII range for Arabic characters in UTF-8
  const ARABIC_CHAR_PATTERN = /[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/;
  const CORRUPTED_PATTERNS = [/�/, /(\?){2,}/, /[^\x00-\x7F\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/];

  window.KpiValidation = {
    /**
     * Clamp a numeric value to valid range
     */
    clamp: function (value, min = 0, max = 100) {
      const numeric = Number(value);
      if (!Number.isFinite(numeric)) return min;
      return Math.min(Math.max(numeric, min), max);
    },

    /**
     * Validate if a string contains valid UTF-8 Arabic text (not corrupted)
     */
    isValidArabicText: function (text) {
      if (text == null) return true; // null/undefined is acceptable
      if (typeof text !== "string") return true;
      if (text === "") return true;

      // Check for replacement characters (�) which indicate encoding issues
      if (text.includes("\uFFFD")) return false;

      // Check for excessive question marks (often indicates corrupted text)
      if ((text.match(/\?/g) || []).length > 2) return false;

      return true;
    },

    /**
     * Detect and sanitize corrupted text
     */
    sanitizeCorruptedText: function (text, fallback = "غير محدد") {
      if (this.isValidArabicText(text)) return text;
      
      // Try to find a clean fallback or use default
      return fallback;
    },

    /**
     * Validate KPI value - ensures percentages are valid, counts are non-negative
     */
    validateKpiValue: function (value, type = "percent") {
      const numeric = Number(value);

      if (!Number.isFinite(numeric)) {
        return { valid: false, reason: "invalid_number", value: null };
      }

      if (type === "percent") {
        if (numeric < 0) {
          return { valid: false, reason: "negative_percent", value: this.clamp(numeric, 0, 100) };
        }
        if (numeric > 100) {
          return { valid: false, reason: "overflow_percent", value: this.clamp(numeric, 0, 100) };
        }
        return { valid: true, value: this.clamp(numeric, 0, 100) };
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
     * Format a percentage value safely
     */
    formatPercent: function (value, decimals = 1) {
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
     * Calculate data quality score based on completeness and validity
     */
    calculateDataQualityScore: function (data) {
      if (!data || typeof data !== "object") return 0;

      const fields = [
        "overall_gcei",
        "attendance_rate",
        "ratio_compliance",
        "training_completion_rate",
        "report_submission_rate",
        "incident_rate",
        "serious_incident_rate",
        "incident_followup_sla",
        "chronic_absence_rate",
        "capacity_utilization_rate",
      ];

      let validCount = 0;
      let totalScore = 0;

      fields.forEach((field) => {
        const metric = data[field];
        if (!metric) return;

        // Check has_data flag
        const hasData = metric.has_data !== false;
        const coverage = metric.data_coverage ?? 100;

        // Check for corrupted text
        const nameValid = this.isValidArabicText(metric.name_ar) && this.isValidArabicText(metric.name_en);

        if (hasData && nameValid) {
          validCount++;
          // Add coverage score (0-100% coverage = partial score)
          totalScore += Math.min(coverage, 100) / 100;
        } else if (hasData) {
          validCount++;
          totalScore += 0.5; // Partial score for has_data=true but corrupted text
        }
      });

      const score = (totalScore / fields.length) * 100;
      return Math.round(score);
    },

    /**
     * Validate API payload before rendering
     */
    validatePayload: function (payload) {
      const issues = [];

      if (!payload || typeof payload !== "object") {
        return { valid: false, issues: ["empty_or_invalid_payload"] };
      }

      // Check for corrupted text in key fields
      const arabicFields = ["governorate", "city", "area", "kindergarten_name"];
      arabicFields.forEach((field) => {
        if (payload[field] && !this.isValidArabicText(payload[field])) {
          issues.push(`corrupted_text:${field}`);
        }
      });

      // Validate percentages
      const percentFields = [
        "attendance_rate",
        "ratio_compliance",
        "training_completion_rate",
        "report_submission_rate",
        "incident_followup_sla",
      ];
      percentFields.forEach((field) => {
        const metric = payload[field];
        if (metric && metric.has_data !== false) {
          const value = Number(metric.value);
          if (Number.isFinite(value)) {
            if (value < 0) issues.push(`negative_percent:${field}`);
            if (value > 100) issues.push(`overflow_percent:${field}`);
          }
        }
      });

      // Validate counts
      const countFields = ["active_enrollments", "new_enrollments"];
      countFields.forEach((field) => {
        const metric = payload[field];
        if (metric && metric.has_data !== false) {
          const value = Number(metric.value);
          if (Number.isFinite(value) && value < 0) {
            issues.push(`negative_count:${field}`);
          }
        }
      });

      return {
        valid: issues.length === 0,
        issues,
        quality_score: this.calculateDataQualityScore(payload),
      };
    },

    /**
     * Escape HTML for security
     */
    escapeHtml: function (value) {
      if (value == null) return "";
      return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    },

    /**
     * CSV escape to prevent injection
     */
    escapeCsv: function (value) {
      if (value == null) return "";
      const str = String(value);
      
      // Check for formula injection characters
      if (/^[=+\-@\t\r\n]/.test(str)) {
        return "'" + str;
      }
      
      // Quote if contains comma, quote, or newline
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

  // Global helper for use in templates
  window.formatValue = function (value, type = "percent") {
    return window.KpiValidation.formatPercent(value);
  };

  window.formatCount = function (value) {
    return window.KpiValidation.formatCount(value);
  };
})();