/* Extracted verbatim from templates/kpi/dashboard.html.
 *
 * It was 63 KB of inline <script>, which the ?v= cache strategy cannot reach:
 * inline script is re-downloaded on every page view no matter how long the
 * static max-age is. The block contained no Jinja, so this is a byte-for-byte
 * move rather than a rewrite.
 */
(function () {
    const root = document.getElementById("kpiDashboardRoot");
    const userRole = root ? (root.dataset.userRole || "").toUpperCase() : "";
    const userKindergartenId = root
      ? Number(root.dataset.userKindergarten || 0)
      : 0;
    const isManagerView = userRole === "MANAGER";
    const kpiLang = () =>
      document.documentElement.lang === "en" ? "en" : "ar";
    const kpiLocale = () =>
      typeof appCurrentLocale === "function"
        ? appCurrentLocale()
        : kpiLang() === "en"
          ? "en-US"
          : "ar-JO";
    const kpiText = (key, arText, enText) =>
      typeof appText === "function"
        ? appText(key, arText, enText)
        : kpiLang() === "en"
          ? enText
          : arText;
    const kpiLiteral = (text) => {
      if (text == null) return "";
      if (kpiLang() !== "en") return String(text);
      if (
        window.AppI18n &&
        typeof window.AppI18n.replaceLiteralSegments === "function"
      ) {
        return window.AppI18n.replaceLiteralSegments(String(text));
      }
      return String(text);
    };

    const state = {
      startDate: "",
      endDate: "",
      granularity: "weekly",
      governorate: "",
      district: "",
      area: "",
      kindergartenIds: [],
      isLoading: false,
    };

    const KPI_CARD_CONFIG = {
      attendance_rate: {
        value: null,
        skeleton: null,
        progress: null,
        band: null,
      },
      ratio_compliance: {
        value: null,
        skeleton: null,
        progress: null,
        band: null,
      },
      training_completion_rate: {
        value: null,
        skeleton: null,
        progress: null,
        band: null,
      },
      report_submission_rate: {
        value: null,
        skeleton: null,
        progress: null,
        band: null,
      },
      incident_rate: { value: null, skeleton: null, band: null },
      serious_incident_rate: { value: null, skeleton: null, band: null },
      incident_followup_sla: { value: null, skeleton: null, band: null },
      chronic_absence_rate: { value: null, skeleton: null, band: null },
      capacity_utilization_rate: { value: null, skeleton: null },
      active_enrollments: { value: null, skeleton: null },
      new_enrollments: { value: null, skeleton: null },
    };

    let gceiGaugeChart = null;
    let attendanceTrendChart = null;
    let incidentsTrendChart = null;
    let enrollmentTrendChart = null;
    let gceiTrendChart = null;
    let distributionChart = null;
    let latestDashboardRequestId = 0;
    let dashboardReconnectTimer = null;
    let wsReconnectAttempts = 0;
    const WS_MAX_ATTEMPTS = 10; // give up after ~10 retries (≈5 min total)
    const WS_BASE_DELAY_MS = 1000; // 1 s initial delay
    const WS_MAX_DELAY_MS = 30000; // 30 s cap

    function clamp(value, min = 0, max = 100) {
      const numeric = Number(value);
      if (!Number.isFinite(numeric)) return min;
      return Math.min(Math.max(numeric, min), max);
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }

    function sanitizeWidgetId(value) {
      const cleaned = String(value ?? "").replace(/[^a-zA-Z0-9_-]/g, "");
      return cleaned || "widget";
    }

    function getToken() {
      if (
        window.AuthStorage &&
        typeof window.AuthStorage.getToken === "function"
      ) {
        return window.AuthStorage.getToken();
      }
      return (
        localStorage.getItem("kinjo_token") ||
        sessionStorage.getItem("kinjo_token") ||
        null
      );
    }

    async function requestWithAuth(url, options = {}) {
      if (typeof window.fetchWithAuth === "function") {
        return window.fetchWithAuth(url, options);
      }
      const token = getToken();
      const headers = new Headers(options.headers || {});
      if (token && !headers.has("Authorization")) {
        headers.set("Authorization", `Bearer ${token}`);
      }
      return fetch(url, { ...options, headers });
    }

    function extractErrorMessage(error, fallbackMessage) {
      if (!error) return fallbackMessage;
      if (typeof error === "string") return error;
      if (error.message) return error.message;
      if (error.detail) {
        if (typeof error.detail === "string") return error.detail;
        if (error.detail.message) return error.detail.message;
      }
      return fallbackMessage;
    }

    document.addEventListener("DOMContentLoaded", () => {
      initState();
      bindUI();
      initCharts();
      loadKindergartenOptions();
      loadDashboardData();
    });
    function initState() {
      const today = new Date();
      const start = new Date(today.getFullYear(), today.getMonth(), 1);
      const end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
      state.startDate = toInputDate(start);
      state.endDate = toInputDate(end);

      // Safely set date input values with null checks
      const periodStartEl = document.getElementById("periodStart");
      const periodEndEl = document.getElementById("periodEnd");
      if (periodStartEl) periodStartEl.value = state.startDate;
      if (periodEndEl) periodEndEl.value = state.endDate;

      state.granularity = "weekly";
      const granularityEl = document.getElementById("granularitySelect");
      if (granularityEl) granularityEl.value = state.granularity;

      state.governorate = "";
      state.district = "";
      state.area = "";
      state.kindergartenIds = [];
      state.isLoading = true;
      setFilterStatus(
        kpiText(
          "common.loading_data",
          "جارٍ جلب البيانات...",
          "Fetching data...",
        ),
      );
    }

    function bindUI() {
      const applyBtn = document.getElementById("applyFiltersBtn");
      const resetBtn = document.getElementById("resetFiltersBtn");

      if (applyBtn) {
        applyBtn.addEventListener("click", () => {
          if (!updateStateFromFilters(true)) return;
          loadDashboardData();
        });
      }
      if (resetBtn) {
        resetBtn.addEventListener("click", () => {
          resetFilters();
        });
      }
      if (isManagerView) {
        // Hide irrelevant filters for managers
        [
          "kgFilterCol",
          "govFilterCol",
          "cityFilterCol",
          "areaFilterCol",
          "granularitySelect",
        ].forEach((id) => {
          const el = document.getElementById(id);
          if (el) {
            const target =
              el.closest(".col-lg-1, .col-lg-2, .col-lg-3, .col-sm-6") || el;
            target.style.display = "none";
          }
        });
        // Force kindergarten filter to manager's KG
        if (userKindergartenId) {
          state.kindergartenIds = [String(userKindergartenId)];
          const kgSelect = document.getElementById("kindergartenSelect");
          if (kgSelect) {
            kgSelect.innerHTML = "";
            const opt = document.createElement("option");
            opt.value = userKindergartenId;
            opt.textContent = kpiText(
              "kpi.my_kindergarten",
              "روضتي",
              "My kindergarten",
            );
            kgSelect.appendChild(opt);
            kgSelect.value = String(userKindergartenId);
            kgSelect.disabled = true;
            kgSelect.multiple = false;
            const kgHint = document.getElementById("kindergartenHint");
            if (kgHint)
              kgHint.innerText = kpiText(
                "kpi.manager.scope_hint",
                "البيانات مقصورة على الحضانة المرتبطة بك.",
                "Data is limited to your linked kindergarten.",
              );
          }
        }
        setFilterStatus(
          kpiText(
            "kpi.manager.scope_status",
            "عرض مؤشرات الحضانة المرتبطة بالمدير فقط",
            "Showing indicators for manager linked kindergarten only",
          ),
        );
      }
    }

    function updateStateFromFilters(validate = false) {
      const periodStartEl = document.getElementById("periodStart");
      const periodEndEl = document.getElementById("periodEnd");
      const granularityEl = document.getElementById("granularitySelect");
      const governorateEl = document.getElementById("governorateSelect");
      const cityEl = document.getElementById("citySelect");
      const areaEl = document.getElementById("areaSelect");
      const select = document.getElementById("kindergartenSelect");

      state.startDate =
        (periodStartEl && periodStartEl.value) || state.startDate;
      state.endDate = (periodEndEl && periodEndEl.value) || state.endDate;
      state.granularity =
        (granularityEl && granularityEl.value) || state.granularity;
      state.governorate = (governorateEl && governorateEl.value) || "";
      state.district = (cityEl && cityEl.value) || "";
      state.area = (areaEl && areaEl.value) || "";
      const selected = select
        ? Array.from(select.selectedOptions)
            .map((opt) => parseInt(opt.value, 10))
            .filter(Number.isFinite)
        : [];
      if (isManagerView && userKindergartenId) {
        state.kindergartenIds = [userKindergartenId];
        if (select) select.value = String(userKindergartenId);
      } else {
        state.kindergartenIds = selected;
      }
      if (validate) {
        const validation = validateDateRange(state.startDate, state.endDate);
        if (!validation.valid) {
          showFilterError(validation.message);
          return false;
        }
      }
      hideFilterError();
      setFilterStatus(
        buildFilterSummary(
          kpiText(
            "filters.applying",
            "جارٍ تطبيق المرشحات...",
            "Applying filters...",
          ),
        ),
      );
      return true;
    }

    function resetFilters() {
      initState();
      const governorateEl = document.getElementById("governorateSelect");
      const cityEl = document.getElementById("citySelect");
      const areaEl = document.getElementById("areaSelect");
      const select = document.getElementById("kindergartenSelect");
      if (governorateEl) governorateEl.value = "";
      if (cityEl) cityEl.value = "";
      if (areaEl) areaEl.value = "";
      if (select) {
        select.selectedIndex = -1;
        if (isManagerView && userKindergartenId) {
          select.value = String(userKindergartenId);
        }
      }
      loadDashboardData();
    }

    function setFilterStatus(text) {
      const statusEl = document.getElementById("filterStatus");
      if (statusEl) statusEl.textContent = kpiLiteral(text);
    }

    function toInputDate(date) {
      const tzOffset = date.getTimezoneOffset() * 60000;
      return new Date(date - tzOffset).toISOString().slice(0, 10);
    }

    function governorateLabel(value) {
      if (!value)
        return kpiText(
          "filters.all_governorates",
          "جميع المحافظات",
          "All governorates",
        );
      return value;
    }

    function cityLabel(value) {
      if (!value)
        return kpiText("filters.all_cities", "جميع المدن", "All cities");
      return value;
    }

    function areaLabel(value) {
      if (!value)
        return kpiText("filters.all_areas", "جميع المناطق", "All areas");
      return value;
    }

    function validateDateRange(start, end) {
      if (!start || !end) {
        return {
          valid: false,
          message: kpiText(
            "filters.select_start_end",
            "يرجى اختيار تاريخ بداية ونهاية.",
            "Please select start and end date.",
          ),
        };
      }
      if (new Date(start) > new Date(end)) {
        return {
          valid: false,
          message: kpiText(
            "filters.start_before_end",
            "تاريخ البداية يجب أن يكون قبل أو يساوي تاريخ النهاية.",
            "Start date must be before or equal to end date.",
          ),
        };
      }
      return { valid: true };
    }

    function showFilterError(msg) {
      const el = document.getElementById("filterError");
      if (el) {
        el.textContent = kpiLiteral(msg);
        el.classList.remove("d-none");
      }
    }

    function hideFilterError() {
      const el = document.getElementById("filterError");
      if (el) {
        el.classList.add("d-none");
        el.textContent = "";
      }
    }

    function buildFilterSummary(
      prefix = kpiText(
        "filters.applied",
        "تم تطبيق المرشحات",
        "Filters applied",
      ),
    ) {
      if (isManagerView) {
        return `${prefix}: ${kpiText("filters.your_kindergarten", "الحضانة الخاصة بك", "Your kindergarten")} | ${formatArabicDate(state.startDate, state.endDate)}`;
      }
      const parts = [`${formatArabicDate(state.startDate, state.endDate)}`];
      parts.push(
        `${kpiText("common.governorate", "المحافظة", "Governorate")}: ${governorateLabel(state.governorate)}`,
      );
      parts.push(
        `${kpiText("common.district", "اللواء", "District")}: ${cityLabel(state.district)}`,
      );
      parts.push(
        `${kpiText("common.area", "المنطقة", "Area")}: ${areaLabel(state.area)}`,
      );
      parts.push(
        `${kpiText("common.kindergartens", "الحضانات", "Kindergartens")}: ${state.kindergartenIds.length || kpiText("common.all", "الكل", "All")}`,
      );
      return `${prefix}: ${parts.join(" | ")}`;
    }

    async function loadKindergartenOptions() {
      try {
        const response = await window.api.get(
          `/api/kpi/filters?locale=${encodeURIComponent(kpiLang())}`,
        );
        if (!response) return;
        const data = response.data || response;

        // Load kindergartens
        const kgList = data.kindergartens || [];
        const kgSelect = document.getElementById("kindergartenSelect");
        if (kgSelect) {
          if (!isManagerView) {
            const defaultOption = kgSelect.querySelector('option[value=""]');
            kgSelect.innerHTML = "";
            if (defaultOption) kgSelect.appendChild(defaultOption);
          }
          const seen = new Set();
          if (!isManagerView) {
            kgList
              .filter((kg) => {
                if (seen.has(kg.id)) return false;
                seen.add(kg.id);
                return true;
              })
              .sort((a, b) =>
                String(a.name || "").localeCompare(
                  String(b.name || ""),
                  kpiLang(),
                ),
              )
              .forEach((kg) => {
                const option = document.createElement("option");
                option.value = kg.id;
                option.textContent = kg.name;
                kgSelect.appendChild(option);
              });
          }
        }

        // Load governorates
        const govList = data.governorates || [];
        const govSelect = document.getElementById("governorateSelect");
        if (govSelect) {
          const defaultOption = govSelect.querySelector('option[value=""]');
          govSelect.innerHTML = "";
          if (defaultOption) govSelect.appendChild(defaultOption);
          const seenGov = new Set();
          govList.forEach((gov) => {
            if (!gov || !gov.name || seenGov.has(gov.name)) return;
            seenGov.add(gov.name);
            const option = document.createElement("option");
            option.value = gov.name;
            option.dataset.governorateId = gov.id;
            option.textContent = gov.name;
            govSelect.appendChild(option);
          });
        }

        const cityList = data.cities || [];
        const citySelect = document.getElementById("citySelect");
        if (citySelect) {
          const defaultOption = citySelect.querySelector('option[value=""]');
          citySelect.innerHTML = "";
          if (defaultOption) citySelect.appendChild(defaultOption);
          const seenCity = new Set();
          cityList.forEach((district) => {
            if (!district || !district.name || seenCity.has(district.name)) return;
            seenCity.add(district.name);
            const option = document.createElement("option");
            option.value = district.name;
            option.textContent = district.name;
            citySelect.appendChild(option);
          });
        }

        const areaList = data.areas || [];
        const areaSelect = document.getElementById("areaSelect");
        if (areaSelect) {
          const defaultOption = areaSelect.querySelector('option[value=""]');
          areaSelect.innerHTML = "";
          if (defaultOption) areaSelect.appendChild(defaultOption);
          const seenArea = new Set();
          areaList.forEach((area) => {
            if (!area || !area.name || seenArea.has(area.name)) return;
            seenArea.add(area.name);
            const option = document.createElement("option");
            option.value = area.name;
            option.textContent = area.name;
            areaSelect.appendChild(option);
          });
        }

        if (userRole === "MANAGER" && userKindergartenId) {
          if (kgSelect) {
            kgSelect.value = String(userKindergartenId);
            kgSelect.multiple = false;
            kgSelect.disabled = true;
          }
          const kgHint = document.getElementById("kindergartenHint");
          if (kgHint) {
            kgHint.innerText = kpiText(
              "kpi.manager.fixed_kg_hint",
              "الحضانة المرتبطة بالمدير لا يمكن تغييرها.",
              "Manager linked kindergarten cannot be changed.",
            );
          }
        }
      } catch (error) {
        console.warn(
          kpiText(
            "filters.load_failed",
            "تعذر تحميل عوامل التصفية",
            "Unable to load filters",
          ),
          error,
        );
      }
    }

    const chartNumberFormatter = new Intl.NumberFormat(kpiLocale(), {
      minimumFractionDigits: 0,
      maximumFractionDigits: 1,
    });
    const chartIntegerFormatter = new Intl.NumberFormat(kpiLocale(), {
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    });
    const chartDateFormatter = new Intl.DateTimeFormat(kpiLocale(), {
      month: "short",
      day: "numeric",
    });
    const chartPalette = [
      "#1F5E47",
      "#B49B3B",
      "#2F7D62",
      "#D97706",
      "#7C3AED",
      "#163d2e",
    ];

    function formatArabicDate(start, end) {
      if (!start || !end) return "--";
      const monthNames = kpiLang() === "en"
        ? ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        : ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"];
      const format = (iso) => {
        const d = new Date(iso);
        if (Number.isNaN(d.getTime())) return iso;
        return `${d.getDate()} ${monthNames[d.getMonth()]} ${d.getFullYear()}`;
      };
      return `${format(start)} ${kpiText("", " إلى ", " to ")} ${format(end)}`;
    }

    const noDataOverlayPlugin = {
      id: "noDataOverlay",
      afterDraw(chart, _args, options) {
        const dataset = chart?.data?.datasets?.[0]?.data || [];
        const labels = chart?.data?.labels || [];
        const hasData =
          labels.length > 0 &&
          dataset.some((value) => Number.isFinite(Number(value)));
        if (hasData) return;

        const area = chart.chartArea;
        if (!area) return;

        const ctx = chart.ctx;
        ctx.save();
        ctx.fillStyle = "#9aa0a6";
        ctx.font = '12px "Segoe UI", Tahoma, sans-serif';
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(
          kpiLiteral(
            options?.message ||
              kpiText("common.no_data", "لا تتوفر بيانات للفترة أو المعايير المحددة. يرجى تعديل عوامل التصفية أو اختيار نطاق زمني مختلف.", "No data"),
          ),
          (area.left + area.right) / 2,
          (area.top + area.bottom) / 2,
        );
        ctx.restore();
      },
    };

    function formatChartDate(rawValue) {
      if (!rawValue) return "--";
      const parsed = new Date(rawValue);
      if (Number.isNaN(parsed.getTime())) return String(rawValue);
      return chartDateFormatter.format(parsed);
    }

    function formatChartValue(value, decimals = 1, suffix = "") {
      const numeric = Number(value);
      if (!Number.isFinite(numeric)) return "--";
      const formatter =
        decimals === 0 ? chartIntegerFormatter : chartNumberFormatter;
      const rendered = formatter.format(
        decimals === 0
          ? Math.round(numeric)
          : Number(numeric.toFixed(decimals)),
      );
      return suffix ? `${rendered}${suffix}` : rendered;
    }

    function hexToRgba(hexColor, alpha) {
      if (
        !hexColor ||
        typeof hexColor !== "string" ||
        !hexColor.startsWith("#")
      ) {
        return `rgba(31, 94, 71, ${alpha})`;
      }
      const value = hexColor.replace("#", "");
      const full =
        value.length === 3
          ? value
              .split("")
              .map((ch) => ch + ch)
              .join("")
          : value;
      const r = parseInt(full.slice(0, 2), 16);
      const g = parseInt(full.slice(2, 4), 16);
      const b = parseInt(full.slice(4, 6), 16);
      return `rgba(${r}, ${g}, ${b}, ${alpha})`;
    }

    function buildAreaGradient(ctx, color) {
      const gradient = ctx.createLinearGradient(0, 0, 0, 220);
      gradient.addColorStop(0, hexToRgba(color, 0.32));
      gradient.addColorStop(1, hexToRgba(color, 0.02));
      return gradient;
    }

    function createTrendChart(canvasId, config) {
      const canvas = document.getElementById(canvasId);
      if (!canvas) return null;
      const ctx = canvas.getContext("2d");
      const gradient = buildAreaGradient(ctx, config.color);
      const chart = new Chart(ctx, {
        type: "line",
        plugins: [noDataOverlayPlugin],
        data: {
          labels: [],
          datasets: [
            {
              data: [],
              borderColor: config.color,
              backgroundColor: gradient,
              fill: true,
              tension: 0.35,
              borderWidth: 2.5,
              pointRadius: 2,
              pointHoverRadius: 5,
              pointHitRadius: 14,
              pointBackgroundColor: "#ffffff",
              pointBorderColor: config.color,
              pointBorderWidth: 2,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: {
            duration: 650,
            easing: "easeOutQuart",
          },
          interaction: {
            mode: "index",
            intersect: false,
          },
          layout: {
            padding: { top: 8, right: 8, left: 8, bottom: 2 },
          },
          scales: {
            x: {
              display: true,
              grid: { display: false },
              ticks: {
                color: "#7a7f85",
                autoSkip: true,
                maxTicksLimit: 6,
                maxRotation: 0,
                font: { size: 10 },
              },
            },
            y: {
              display: true,
              beginAtZero: true,
              suggestedMin: config.percent ? 0 : undefined,
              suggestedMax: config.percent ? 100 : undefined,
              grid: {
                color: "rgba(15, 23, 42, 0.08)",
                drawBorder: false,
              },
              ticks: {
                color: "#7a7f85",
                maxTicksLimit: 5,
                callback: (value) =>
                  formatChartValue(value, config.decimals, config.suffix),
                font: { size: 10 },
              },
            },
          },
          plugins: {
            legend: { display: false },
            noDataOverlay: {
              message: kpiText(
                "charts.no_data_period",
                "لا توجد بيانات ضمن الفترة المحددة",
                "No data for selected period",
              ),
            },
            tooltip: {
              backgroundColor: "rgba(15, 23, 42, 0.92)",
              titleColor: "#ffffff",
              bodyColor: "#ffffff",
              cornerRadius: 8,
              displayColors: false,
              callbacks: {
                title: (items) => {
                  const rawLabel = items?.[0]?.label;
                  return rawLabel || "--";
                },
                label: (context) =>
                  `${kpiText("charts.value", "القيمة", "Value")}: ${formatChartValue(context.parsed.y, config.decimals, config.suffix)}`,
              },
            },
          },
        },
      });

      chart.$meta = {
        percent: Boolean(config.percent),
        decimals: Number.isFinite(config.decimals) ? config.decimals : 1,
        suffix: config.suffix || "",
      };
      return chart;
    }

    function createDistributionChart(canvasId) {
      const canvas = document.getElementById(canvasId);
      if (!canvas) return null;
      const ctx = canvas.getContext("2d");
      return new Chart(ctx, {
        type: "bar",
        plugins: [noDataOverlayPlugin],
        data: {
          labels: [],
          datasets: [
            {
              data: [],
              borderRadius: 8,
              borderSkipped: false,
              maxBarThickness: 42,
              backgroundColor: [],
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: {
            duration: 650,
            easing: "easeOutQuart",
          },
          plugins: {
            legend: { display: false },
            noDataOverlay: {
              message: kpiText(
                "charts.no_distribution",
                "لا يوجد توزيع متاح حالياً",
                "No distribution available right now",
              ),
            },
            tooltip: {
              callbacks: {
                title: (items) => items?.[0]?.label || "--",
                label: (context) => {
                  const value = Number(context.parsed.y) || 0;
                  const values = context.dataset.data || [];
                  const total = values.reduce(
                    (sum, item) => sum + (Number(item) || 0),
                    0,
                  );
                  const percent = total > 0 ? (value / total) * 100 : 0;
                  return `${kpiText("charts.count", "العدد", "Count")}: ${formatChartValue(value, 0)} (${formatChartValue(percent, 1, "%")})`;
                },
              },
            },
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: {
                color: "#7a7f85",
                autoSkip: false,
                maxRotation: 35,
                minRotation: 0,
                font: { size: 10 },
              },
            },
            y: {
              beginAtZero: true,
              grid: {
                color: "rgba(15, 23, 42, 0.08)",
                drawBorder: false,
              },
              ticks: {
                precision: 0,
                color: "#7a7f85",
                callback: (value) => formatChartValue(value, 0),
                font: { size: 10 },
              },
            },
          },
        },
      });
    }

    function initCharts() {
      // Main GCEI Gauge
      const gaugeCanvas = document.getElementById("gceiGauge");
      if (!gaugeCanvas) {
        showAlert(
          kpiText(
            "charts.init_failed",
            "تعذر تهيئة الرسوم البيانية: عناصر الرسم غير متوفرة.",
            "Unable to initialize charts: chart elements are unavailable.",
          ),
        );
        return;
      }
      if (typeof Chart === "undefined") {
        showAlert(
          kpiText(
            "charts.library_missing",
            "تعذر تحميل مكتبة الرسوم البيانية. تحقق من اتصال الإنترنت أو موارد المكتبة.",
            "Unable to load the chart library. Check network access to chart resources.",
          ),
        );
        return;
      }
      const ctxGauge = gaugeCanvas.getContext("2d");
      gceiGaugeChart = new Chart(ctxGauge, {
        type: "doughnut",
        plugins: [noDataOverlayPlugin],
        data: {
          labels: [
            kpiText("charts.performance", "الأداء", "Performance"),
            kpiText(
              "charts.remaining_to_target",
              "المتبقي للوصول للهدف",
              "Remaining to target",
            ),
          ],
          datasets: [
            {
              data: [0, 100],
              backgroundColor: ["#28a745", "#f1f3f4"],
              borderWidth: 0,
              circumference: 180,
              rotation: 270,
              cutout: "78%",
              borderRadius: 7,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: {
            duration: 700,
            easing: "easeOutQuart",
          },
          plugins: {
            legend: { display: false },
            tooltip: {
              callbacks: {
                label: (context) =>
                  `${kpiText("charts.value", "القيمة", "Value")}: ${formatChartValue(context.parsed, 1, "%")}`,
              },
            },
            noDataOverlay: {
              message: kpiText(
                "common.waiting_data",
                "انتظار البيانات...",
                "Waiting for data...",
              ),
            },
          },
        },
      });

      attendanceTrendChart = createTrendChart("attendanceTrendChart", {
        color: "#34a853",
        percent: true,
        decimals: 1,
        suffix: "%",
      });
      incidentsTrendChart = createTrendChart("incidentsTrendChart", {
        color: "#ea4335",
        percent: false,
        decimals: 2,
        suffix: "",
      });
      enrollmentTrendChart = createTrendChart("enrollmentTrendChart", {
        color: "#2F7D62",
        percent: false,
        decimals: 0,
        suffix: "",
      });
      gceiTrendChart = createTrendChart("gceiTrendChart", {
        color: "#8e24aa",
        percent: true,
        decimals: 1,
        suffix: "%",
      });

      distributionChart = createDistributionChart("distributionChart");
    }
    async function loadDashboardData() {
      state.isLoading = true;
      const btn = document.getElementById("applyFiltersBtn");
      const requestId = ++latestDashboardRequestId;
      hideFilterError();
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status"></span>${kpiText("common.loading_short", "جاري", "Loading")}`;
      }

      const params = new URLSearchParams();
      params.append("period_start", state.startDate);
      params.append("period_end", state.endDate);
      params.append("locale", kpiLang());

      let endpoint = "/api/kpi/dashboard-data";
      if (userRole === "MANAGER") {
        // Managers use the dedicated manager endpoint
        endpoint = "/api/kpi/manager/dashboard";
      } else {
        // Admins can use filters
        params.append("granularity", state.granularity);
        if (state.governorate) {
          params.append("governorate", state.governorate);
        }
        if (state.district) {
          params.append("district", state.district);
        }
        if (state.area) {
          params.append("area", state.area);
        }
        if (state.kindergartenIds.length) {
          state.kindergartenIds.forEach((id) =>
            params.append("kindergarten_ids", id),
          );
        }
      }

      try {
        if (!window.api || typeof window.api.get !== "function") {
          throw new Error(
            kpiText(
              "charts.api_unavailable",
              "تعذر تحميل واجهة البيانات.",
              "Data API client is unavailable.",
            ),
          );
        }
        const response = await window.api.get(endpoint, Object.fromEntries(params));
        if (!response) {
          throw new Error(
            kpiText(
              "common.server_unreachable",
              "تعذر التواصل مع الخادم.",
              "Unable to reach server.",
            ),
          );
        }
        if (requestId !== latestDashboardRequestId) return;
        const payload = response.data || response;
        renderDashboard(payload);
        setFilterStatus(buildFilterSummary());
        if (typeof showToast === "function") {
          showToast(
            kpiText("common.data_updated", "تم تحديث البيانات", "Data updated"),
            "success",
          );
        }
      } catch (error) {
        if (requestId !== latestDashboardRequestId) return;
        showAlert(
          extractErrorMessage(
            error,
            kpiText(
              "common.load_failed",
              "تعذر تحميل البيانات",
              "Unable to load data",
            ),
          ),
        );
        setFilterStatus(
          kpiText(
            "filters.apply_failed",
            "تعذر تطبيق المرشحات",
            "Failed to apply filters",
          ),
        );
      } finally {
        state.isLoading = false;
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = `<i class="bi bi-funnel me-1"></i>${kpiText("common.apply", "تطبيق", "Apply")}`;
        }
      }
    }
function renderDashboard(data) {
       // Centralized validation
       if (window.KpiValidation && window.KpiValidation.validatePayload) {
         const validation = window.KpiValidation.validatePayload(data);
         if (!validation.valid) {
           console.warn("Data validation issues:", validation.issues);
         }
         // Display data quality score
         const qualityScore = validation.quality_score || 0;
         const qualityEl = document.getElementById("dataQualityScore");
         if (qualityEl) {
           qualityEl.textContent = qualityScore + "%";
           qualityEl.className = "badge rounded-pill ms-2";
           if (qualityScore >= 80) {
             qualityEl.classList.add("bg-success-subtle", "text-success");
           } else if (qualityScore >= 50) {
             qualityEl.classList.add("bg-warning-subtle", "text-warning");
           } else {
             qualityEl.classList.add("bg-danger-subtle", "text-danger");
           }
         }
       }

       if (!data || typeof data !== "object") {
         showAlert(
           kpiText(
             "common.invalid_payload",
             "البيانات المستلمة غير صالحة للعرض.",
             "Received data is invalid for display.",
           ),
         );
         return;
       }
      // 1. Overall Governance Hero
      const gv = data.overall_gcei || {};
      const gcei = clamp(gv.value, 0, 100);
      const gceiHasData = gv.has_data !== false;
      const gceiValue = document.getElementById("gceiValue");
      const gceiValuePlaceholder = document.getElementById(
        "gceiValuePlaceholder",
      );

      if (gceiValue) {
        gceiValue.textContent = gceiHasData
          ? gcei.toFixed(1)
          : kpiText("common.no_data", "لا تتوفر بيانات للفترة أو المعايير المحددة. يرجى تعديل عوامل التصفية أو اختيار نطاق زمني مختلف.", "No data");
        gceiValue.classList.remove("d-none");
      }
      if (gceiValuePlaceholder) gceiValuePlaceholder.classList.add("d-none");

      const badge = document.getElementById("gceiStatusBadge");
      const desc = document.getElementById("gceiDescription");

      let color = "#34a853",
        bg = "#e6f4ea",
        status = kpiText("kpi.status.excellent", "ممتاز", "Excellent"),
        suggestions = [];
      if (gcei < 50) {
        status = kpiText("kpi.status.weak", "ضعيف", "Weak");
        color = "#ea4335";
        bg = "#fce8e6";
        suggestions = [
          kpiText(
            "kpi.suggestion.report_compliance",
            "تحسين معدل الالتزام بالتقارير",
            "Improve report compliance rate",
          ),
          kpiText(
            "kpi.suggestion.safety_review",
            "مراجعة إجراءات السلامة المتبعة",
            "Review safety procedures",
          ),
        ];
      } else if (gcei < 75) {
        status = kpiText("kpi.status.good", "جيد", "Good");
        color = "#f9ab00";
        bg = "#fef7e0";
        suggestions = [
          kpiText(
            "kpi.suggestion.training_rate",
            "زيادة معدل الدورات التدريبية",
            "Increase training completion rate",
          ),
          kpiText(
            "kpi.suggestion.parent_communication",
            "تحسين التواصل مع أولياء الأمور",
            "Improve communication with parents",
          ),
        ];
      }

      if (badge) {
        badge.textContent = gceiHasData
          ? status
          : kpiText(
              "common.incomplete_data",
              "بيانات ناقصة",
              "Incomplete data",
            );
        badge.style.backgroundColor = bg;
        badge.style.color = color;
      }
      if (desc) {
        let explanation = "";
        if (gv.components && gv.components.length) {
          explanation = gv.components.map(c => `${c.name}: ${c.weight * 100}%`).join(" | ");
        }
        explanation = explanation ||
          (gv.explanation && (gv.explanation.ar || gv.explanation.en)) ||
          gv.description ||
          kpiText(
            "kpi.overall.explanation_default",
            "يعبر هذا المؤشر عن الكفاءة الشاملة للحضانة.",
            "This indicator reflects the overall kindergarten operational quality.",
          );
        const coverageText =
          gv.data_coverage !== undefined && gv.data_coverage !== null
            ? ` | ${kpiText("kpi.data_coverage", "تغطية البيانات", "Data coverage")}: ${Number(gv.data_coverage).toFixed(1)}%`
            : "";
        const reasonText = gv.no_data_reason ? ` | ${gv.no_data_reason}` : "";
        desc.textContent = kpiLiteral(
          `${explanation}${coverageText}${reasonText}`,
        );
      }

      const actionsList = document.getElementById("suggestedActionsList");
      const actionsContainer = document.getElementById("suggestedActions");
      if (actionsList && actionsContainer) {
        if (suggestions.length) {
          actionsContainer.classList.remove("d-none");
          actionsList.innerHTML = "";
          suggestions.forEach((suggestion) => {
            const li = document.createElement("li");
            li.className = "mb-1";
            li.textContent = suggestion;
            actionsList.appendChild(li);
          });
        } else {
          actionsContainer.classList.add("d-none");
        }
      }

      if (gceiGaugeChart) {
        gceiGaugeChart.data.datasets[0].data = [gcei, 100 - gcei];
        gceiGaugeChart.data.datasets[0].backgroundColor = [color, "#f1f3f4"];
        gceiGaugeChart.update();
      }

      // 2. Secondary Metrics (Standard KPIs)
      const kpiKeys = [
        "attendance_rate",
        "ratio_compliance",
        "training_completion_rate",
        "report_submission_rate",
        "incident_rate",
        "serious_incident_rate",
        "incident_followup_sla",
        "chronic_absence_rate",
        "capacity_utilization_rate",
        "revenue_collection_efficiency",
        "operating_cost_per_child",
        "development_milestone_rate",
        "ilp_completion_rate",
        "accessibility_compliance_rate",
        "language_support_rate",
        "parent_portal_adoption",
        "avg_message_response_time",
        "active_enrollments",
        "new_enrollments",
      ];

      kpiKeys.forEach((key) => {
        const metric = data[key];
        if (!metric) return;

        const valEl = document.querySelector(`[data-value="${key}"]`);
        const progEl = document.querySelector(`[data-progress="${key}"]`);
        const skelEl = document.querySelector(`[data-skeleton="${key}"]`);

        if (valEl) {
          const hasData = metric.has_data !== false;
          valEl.dataset.hasData = hasData;
          const numericValue = Number(metric.value);
          let displayValue = "--";
          if (!hasData) {
            displayValue = kpiText(
              "kpi.not_available",
              "غير متاح",
              "Not available",
            );
          } else if (Number.isFinite(numericValue)) {
            if (key === "active_enrollments" || key === "new_enrollments") {
              displayValue = String(Math.round(numericValue));
            } else if (
              key === "incident_rate" ||
              key === "serious_incident_rate"
            ) {
              displayValue = numericValue.toFixed(2);
            } else if (
              key === "operating_cost_per_child" ||
              key === "avg_message_response_time"
            ) {
              displayValue = numericValue.toFixed(1);
            } else {
              displayValue = `${numericValue.toFixed(1)}%`;
            }
          }
          valEl.textContent = displayValue;
          const badgeContainer = valEl.parentElement?.parentElement?.querySelector('.status-badge-container');
          if (badgeContainer) {
            badgeContainer.classList.toggle('d-none', !hasData);
          }
          if (
            metric.data_coverage !== undefined &&
            metric.data_coverage !== null
          ) {
            const coverage = Number(metric.data_coverage).toFixed(1);
            const reason = metric.no_data_reason
              ? ` | ${metric.no_data_reason}`
              : "";
            valEl.title = kpiLiteral(
              `${kpiText("common.coverage_ratio", "نسبة التغطية", "Coverage ratio")}: ${coverage}%${reason}`,
            );
          }
          valEl.classList.remove("d-none");
        }
        if (progEl) progEl.style.width = clamp(metric.value, 0, 100) + "%";
        if (skelEl) skelEl.classList.add("d-none");
      });

      // 3. Trends
      if (attendanceTrendChart)
        updateTrendChart(attendanceTrendChart, data.attendance_trend || []);
      if (incidentsTrendChart)
        updateTrendChart(incidentsTrendChart, data.incidents_trend || []);
      if (enrollmentTrendChart)
        updateTrendChart(enrollmentTrendChart, data.enrollment_trend || []);
      if (gceiTrendChart)
        updateTrendChart(gceiTrendChart, data.gcei_trend || []);

      // 4. Distribution & Rankings
      renderStudentDistribution(data.student_distribution || []);

      if (!isManagerView) {
        renderRankingList(
          "topPerformersList",
          data.top_performers_by_gcei || [],
          "success",
        );
        renderRankingList(
          "lowPerformersList",
          data.low_performers_by_gcei || [],
          "warning",
        );
      }
      renderAlerts(data.alerts || []);
    }

function renderRankingList(listId, items, color) {
       const list = document.getElementById(listId);
       if (!list) return;
       if (!items || !items.length) {
         list.innerHTML = `<li class="list-group-item border-0 text-muted small bg-transparent">${kpiText("common.no_data", "لا تتوفر بيانات للفترة أو المعايير المحددة. يرجى تعديل عوامل التصفية أو اختيار نطاق زمني مختلف.", "No data")}</li>`;
         return;
       }

       const seenIds = new Set();
       list.innerHTML = items
         .filter((entry) => {
           if (!entry || !entry.id) return true;
           if (seenIds.has(entry.id)) return false;
           seenIds.add(entry.id);
           return true;
         })
         .map(
           (entry, index) => `
                 <li class="list-group-item d-flex justify-content-between align-items-center border-0 px-0 bg-transparent py-2">
                     <div class="d-flex align-items-center gap-2" style="max-width: 72%;">
                         <span class="badge bg-light text-secondary">${index + 1}</span>
                         <span class="small fw-semibold text-truncate" title="${escapeHtml(entry.governorate || '')}">${escapeHtml((entry && entry.name) || kpiText("kpi.kindergarten_fallback", "حضانة", "Kindergarten") + ` #${index + 1}`)}</span>
                     </div>
                     <span class="badge bg-${color}-subtle text-${color} rounded-pill">${formatValue(Number(entry.value) || 0)}</span>
                 </li>
             `,
         )
         .join("");
     }

    function updateTrendChart(chart, points) {
      if (!chart) return;
      const series = Array.isArray(points) ? points.slice(-12) : [];
      const labels = [];
      const values = [];

      series.forEach((point) => {
        const numeric = Number(point?.value);
        if (!Number.isFinite(numeric)) return;
        labels.push(formatChartDate(point?.date));
        values.push(
          chart.$meta?.percent ? clamp(numeric, 0, 100) : Math.max(numeric, 0),
        );
      });

      chart.data.labels = labels;
      chart.data.datasets[0].data = values;
      chart.update();
    }

    function renderStudentDistribution(items) {
      if (!distributionChart) return;
      const list = Array.isArray(items) ? items : [];
      const hasData = list.length > 0;
      const noDataOverlay = document.querySelector("#distributionChart").parentElement?.querySelector(".no-data-overlay");

      if (noDataOverlay) {
        noDataOverlay.classList.toggle("d-none", hasData);
      }

      const labels = list.map((item) =>
        kpiLiteral(
          String(
            item?.label ||
              kpiText("common.unspecified", "غير محدد", "Unspecified"),
          ),
        ),
      );
      const values = list.map((item) => {
        const numeric = Number(item?.value);
        return Number.isFinite(numeric) ? Math.max(numeric, 0) : 0;
      });
      const colors = labels.map(
        (_item, index) => chartPalette[index % chartPalette.length],
      );
      const hoverColors = colors.map((color) => hexToRgba(color, 0.85));

      distributionChart.data.labels = labels;
      distributionChart.data.datasets[0].data = values;
      distributionChart.data.datasets[0].backgroundColor = colors;
      distributionChart.data.datasets[0].hoverBackgroundColor = hoverColors;
      distributionChart.update();
    }

    function renderAlerts(alerts) {
      const container = document.getElementById("dashboardAlerts");
      const list = document.getElementById("dashboardAlertsList");
      if (!container || !list) return;
      list.innerHTML = "";
      container.classList.remove("alert-danger");
      container.classList.add("alert-warning");
      if (!alerts || !alerts.length) {
        container.classList.add("d-none");
        return;
      }
      alerts.forEach((alert) => {
        const li = document.createElement("li");
        li.textContent = kpiLiteral(alert.message);
        list.appendChild(li);
      });
      const retryBtn = document.createElement("button");
      retryBtn.type = "button";
      retryBtn.className = "btn btn-sm btn-outline-secondary ms-2";
      retryBtn.innerHTML = `<i class="bi bi-arrow-clockwise me-1"></i>${kpiText("common.retry", "إعادة المحاولة", "Retry")}`;
      retryBtn.onclick = () => loadDashboardData();
      const retryLi = document.createElement("li");
      retryLi.appendChild(retryBtn);
      list.appendChild(retryLi);
      container.classList.remove("d-none");
    }

    function showAlert(message) {
      const container = document.getElementById("dashboardAlerts");
      const list = document.getElementById("dashboardAlertsList");
      if (!container || !list) {
        console.error(message);
        return;
      }
      list.innerHTML = "";
      const li = document.createElement("li");
      li.textContent = kpiLiteral(message);
      list.appendChild(li);
      container.classList.remove("d-none");
      container.classList.remove("alert-warning");
      container.classList.add("alert-danger");
      const retryBtn = document.createElement("button");
      retryBtn.type = "button";
      retryBtn.className = "btn btn-sm btn-light ms-2";
      retryBtn.innerHTML = `<i class="bi bi-arrow-clockwise me-1"></i>${kpiText("common.retry", "إعادة المحاولة", "Retry")}`;
      retryBtn.onclick = () => loadDashboardData();
      const retryLi = document.createElement("li");
      retryLi.appendChild(retryBtn);
      list.appendChild(retryLi);
    }

    function formatValue(value) {
      if (!Number.isFinite(value)) return "--";
      if (Number.isInteger(value)) return value;
      return value.toFixed(1);
    }

    function hideSkeleton(key) {
      const skeleton = document.querySelector(`[data-skeleton="${key}"]`);
      if (skeleton) {
        skeleton.classList.add("d-none");
      }
    }

    // WebSocket for real-time updates
    let dashboardWebSocket = null;

    /** Show / hide the WS connection-status pill in the page header. */
    function setWsStatus(state) {
      const pill = document.getElementById("wsStatusIndicator");
      const text = document.getElementById("wsStatusText");
      if (!pill || !text) return;
      if (state === "connected") {
        pill.className =
          "badge rounded-pill ms-2 bg-success-subtle text-success border border-success-subtle";
        pill.querySelector("i").className = "bi bi-wifi me-1";
        text.textContent = kpiText("ws.status.connected", "مباشر", "Live");
        pill.classList.remove("d-none");
        // auto-hide after 3 s — no need to clutter UI when all is well
        setTimeout(() => pill.classList.add("d-none"), 3000);
      } else if (state === "reconnecting") {
        pill.className =
          "badge rounded-pill ms-2 bg-warning-subtle text-warning border border-warning-subtle";
        pill.querySelector("i").className = "bi bi-wifi-off me-1";
        text.textContent = kpiText(
          "ws.status.reconnecting",
          "إعادة الاتصال…",
          "Reconnecting…",
        );
        pill.classList.remove("d-none");
      } else if (state === "failed") {
        pill.className =
          "badge rounded-pill ms-2 bg-danger-subtle text-danger border border-danger-subtle";
        pill.querySelector("i").className = "bi bi-wifi-off me-1";
        text.textContent = kpiText(
          "ws.status.failed",
          "البث المباشر معطّل",
          "Live updates unavailable",
        );
        pill.classList.remove("d-none");
      }
    }

    function initWebSocket() {
      const token = getToken();
      if (!token || !window.WebSocket) {
        return;
      }

      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const wsUrl = `${protocol}//${window.location.host}/ws/dashboard?token=${encodeURIComponent(token)}`;

      dashboardWebSocket = new WebSocket(wsUrl);

      dashboardWebSocket.onopen = function (event) {
        console.log("Dashboard WebSocket connected");
        wsReconnectAttempts = 0; // reset back-off counter on successful connect
        setWsStatus("connected");
        // Send subscription request for KPI updates
        dashboardWebSocket.send(
          JSON.stringify({
            type: "subscribe",
            subscriptions: ["kpi_updates", "alerts"],
          }),
        );
      };

      dashboardWebSocket.onmessage = function (event) {
        let data = null;
        try {
          data = JSON.parse(event.data);
        } catch (parseError) {
          console.warn(
            kpiText(
              "ws.invalid_message_ignored",
              "تم تجاهل رسالة فورية غير صالحة.",
              "Ignored invalid realtime message.",
            ),
            parseError,
          );
          return;
        }

        if (data.type === "kpi_update") {
          // Update dashboard with real-time data
          updateDashboardWithRealtimeData(data.data);
        } else if (data.type === "alert") {
          // Show real-time alert
          showRealtimeAlert(data.alert);
        }
      };

      dashboardWebSocket.onclose = function (event) {
        // Code 1000 = normal closure (e.g. user navigates away) — do not retry
        if (event.code === 1000) {
          console.log("Dashboard WebSocket closed normally.");
          return;
        }

        if (wsReconnectAttempts >= WS_MAX_ATTEMPTS) {
          console.warn(
            "Dashboard WebSocket: max reconnect attempts reached. Giving up.",
          );
          setWsStatus("failed");
          return;
        }

        // Exponential back-off with ±10 % jitter
        const base = WS_BASE_DELAY_MS * Math.pow(2, wsReconnectAttempts);
        const jitter = base * 0.1 * (Math.random() * 2 - 1); // ±10 %
        const delay = Math.min(Math.round(base + jitter), WS_MAX_DELAY_MS);
        wsReconnectAttempts++;

        console.log(
          `Dashboard WebSocket disconnected. Retry ${wsReconnectAttempts}/${WS_MAX_ATTEMPTS} in ${delay} ms.`,
        );
        setWsStatus("reconnecting");
        dashboardReconnectTimer = setTimeout(initWebSocket, delay);
      };

      dashboardWebSocket.onerror = function (error) {
        // onerror is always followed by onclose — let onclose handle retry logic
        console.error("Dashboard WebSocket error:", error);
      };

      window.addEventListener(
        "beforeunload",
        () => {
          if (dashboardReconnectTimer) {
            clearTimeout(dashboardReconnectTimer);
            dashboardReconnectTimer = null;
          }
          if (dashboardWebSocket) {
            // Close cleanly (code 1000) so onclose does not trigger a reconnect
            dashboardWebSocket.close(1000, "page unloading");
          }
        },
        { once: true },
      );
    }

    function updateDashboardWithRealtimeData(data) {
      // Update operational metrics
      if (data && data.operational_metrics) {
        Object.keys(data.operational_metrics).forEach((key) => {
          const metric = data.operational_metrics[key];
          const element = document.querySelector(`[data-value="${key}"]`);
          if (element) {
            const numeric = Number(metric.value);
            if (key === "active_enrollments" || key === "new_enrollments") {
              element.textContent = Number.isFinite(numeric)
                ? String(Math.round(numeric))
                : "--";
            } else if (Number.isFinite(numeric)) {
              element.textContent = `${numeric.toFixed(1)}%`;
            } else {
              element.textContent = "--";
            }
          }
        });
      }

      // Show subtle update indicator
      showUpdateIndicator();
    }

    function showRealtimeAlert(alert) {
      // Create and show real-time alert notification
      const alertDiv = document.createElement("div");
      const allowedPriorities = new Set([
        "primary",
        "secondary",
        "success",
        "danger",
        "warning",
        "info",
        "light",
        "dark",
      ]);
      const priority = allowedPriorities.has(alert?.priority)
        ? alert.priority
        : "info";
      alertDiv.className = `alert alert-${priority} alert-dismissible fade show position-fixed`;
      alertDiv.style.cssText =
        "top: 20px; right: 20px; z-index: 9999; min-width: 300px;";
      const strong = document.createElement("strong");
      strong.textContent = kpiLiteral(
        String(alert?.title || kpiText("common.alert", "تنبيه", "Alert")),
      );
      const br = document.createElement("br");
      const small = document.createElement("small");
      small.textContent = kpiLiteral(String(alert?.message || ""));
      const closeButton = document.createElement("button");
      closeButton.type = "button";
      closeButton.className = "btn-close";
      closeButton.setAttribute("data-bs-dismiss", "alert");

      alertDiv.appendChild(strong);
      alertDiv.appendChild(br);
      alertDiv.appendChild(small);
      alertDiv.appendChild(closeButton);

      document.body.appendChild(alertDiv);

      // Auto-remove after 10 seconds
      setTimeout(() => {
        if (alertDiv.parentNode) {
          alertDiv.remove();
        }
      }, 10000);
    }

    function showUpdateIndicator() {
      const existing = document.getElementById("updateIndicator");
      if (existing) existing.remove();
      const indicator = document.createElement("div");
      indicator.className =
        "position-fixed bg-success text-white px-3 py-2 rounded-pill";
      indicator.style.cssText =
        "bottom: 20px; left: 20px; z-index: 9999; font-size: 0.875rem;";
      indicator.innerHTML = `<i class="bi bi-check-circle-fill me-1"></i>${kpiText("common.data_updated", "تم تحديث البيانات", "Data updated")}`;
      indicator.id = "updateIndicator";

      document.body.appendChild(indicator);

      setTimeout(() => {
        const el = document.getElementById("updateIndicator");
        if (el) el.remove();
      }, 3000);
    }

    // Widget customization
    let userWidgets = [];

    async function loadUserWidgets() {
      const container = document.getElementById("dashboardContainer");
      if (!container) {
        return;
      }
      try {
        const response = await requestWithAuth("/api/dashboard/widgets");
        if (!response || !response.ok) {
          throw new Error(
            kpiText(
              "kpi.widgets.load_failed",
              "تعذر جلب إعدادات عناصر اللوحة",
              "Unable to load dashboard widget settings",
            ),
          );
        }
        const data = await response.json();
        userWidgets = data.widgets || [];
        renderDashboardWidgets();
      } catch (error) {
        console.error("Failed to load user widgets:", error);
      }
    }

    function renderDashboardWidgets() {
      const container = document.getElementById("dashboardContainer");
      if (!container) return;

      // Clear existing content
      container.innerHTML = "";

      // Sort widgets by order
      const sortedWidgets = [...userWidgets].sort((a, b) => a.order - b.order);

      sortedWidgets.forEach((widget) => {
        if (!widget.enabled) return;

        const widgetElement = createWidgetElement(widget);
        if (widgetElement) {
          container.appendChild(widgetElement);
        }
      });
    }

    function createWidgetElement(widget) {
      const div = document.createElement("div");
      div.className = "widget-container mb-4";
      div.setAttribute("data-widget-id", widget.id);

      switch (widget.type) {
        case "kpi_cards":
          return createKpiCardsWidget(widget);
        case "chart":
          return createChartWidget(widget);
        case "alerts":
          return createAlertsWidget(widget);
        default:
          return null;
      }
    }

    function createKpiCardsWidget(widget) {
      const div = document.createElement("div");
      div.innerHTML = `
                <div class="row" id="operationalMetrics">
                    <!-- KPI cards will be populated by loadDashboardData() -->
                </div>
            `;
      return div;
    }

    function createChartWidget(widget) {
      const div = document.createElement("div");
      const widgetId = sanitizeWidgetId(widget.id);
      const safeTitle = escapeHtml(widget.title);
      div.innerHTML = `
                <div class="card">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5 class="mb-0">${safeTitle}</h5>
                        <div class="dropdown">
                            <button class="btn btn-sm btn-outline-secondary dropdown-toggle" type="button" data-bs-toggle="dropdown">
                                <i class="bi bi-three-dots"></i>
                            </button>
                            <ul class="dropdown-menu">
                                <li><a class="dropdown-item" href="#" onclick="exportChart('${widgetId}')">${kpiText("common.export", "تصدير", "Export")}</a></li>
                                <li><a class="dropdown-item" href="#" onclick="fullscreenChart('${widgetId}')">${kpiText("common.fullscreen", "ملء الشاشة", "Fullscreen")}</a></li>
                            </ul>
                        </div>
                    </div>
                    <div class="card-body">
                        <canvas id="${widgetId}Chart" width="400" height="200"></canvas>
                    </div>
                </div>
            `;
      return div;
    }

    function createAlertsWidget(widget) {
      const div = document.createElement("div");
      div.innerHTML = `
                <div class="alert alert-warning d-none js-widget-alerts">
                    <h6 class="alert-heading mb-2">
                        <i class="bi bi-exclamation-triangle me-2"></i>
                        ${kpiText("kpi.system_alerts", "تنبيهات النظام", "System alerts")}
                    </h6>
                    <ul class="mb-0 js-widget-alerts-list"></ul>
                </div>
            `;
      return div;
    }

// Export functionality
     async function exportDashboard(format = "csv") {
       try {
         const response = await requestWithAuth(
           `/api/export/kpi-dashboard?format=${encodeURIComponent(format)}`,
         );
         if (!response || !response.ok) {
           const errorText = response ? await response.text() : "";
           throw new Error(
             errorText ||
               kpiText(
                 "export.failed",
                 "تعذر تصدير البيانات",
                 "Unable to export data",
               ),
           );
         }

         const blob = await response.blob();
         const url = window.URL.createObjectURL(blob);
         const a = document.createElement("a");
         a.href = url;
         // Include current filter context in filename for traceability
         const filenameDate = new Date().toISOString().slice(0, 10);
         const filenameContext = state.kindergartenIds.length ? `_kg${state.kindergartenIds.join("-")}` : "";
         a.download = `kpi_dashboard${filenameContext}_${filenameDate}.${format}`;
         document.body.appendChild(a);
         a.click();
         document.body.removeChild(a);
         window.URL.revokeObjectURL(url);
       } catch (error) {
        showAlert(
          extractErrorMessage(
            error,
            kpiText(
              "export.failed_generic",
              "فشل في تصدير البيانات",
              "Data export failed",
            ),
          ),
        );
      }
    }

    function exportChart(widgetId) {
      // Export individual chart (simplified)
      const safeWidgetId = sanitizeWidgetId(widgetId);
      const canvas = document.getElementById(`${safeWidgetId}Chart`);
      if (canvas) {
        const link = document.createElement("a");
        link.download = `${safeWidgetId}_chart.png`;
        link.href = canvas.toDataURL();
        link.click();
      }
    }

    function fullscreenChart(widgetId) {
      const safeWidgetId = sanitizeWidgetId(widgetId);
      const canvas = document.getElementById(`${safeWidgetId}Chart`);
      if (canvas) {
        if (canvas.requestFullscreen) {
          canvas.requestFullscreen();
        }
      }
    }

    // Initialize enhanced features
    document.addEventListener("DOMContentLoaded", function () {
      // Initialize WebSocket
      initWebSocket();

      // Load user widget preferences
      loadUserWidgets();

      // Add export button to header
      const headerActions = document.querySelector(".col-md-4.text-md-end");
      if (headerActions && !document.getElementById("exportKpiDashboardBtn")) {
        const exportBtn = document.createElement("button");
        exportBtn.type = "button";
        exportBtn.className = "btn btn-outline-primary me-2";
        exportBtn.id = "exportKpiDashboardBtn";
        exportBtn.innerHTML = `<i class="bi bi-download me-1"></i>${kpiText("common.export", "تصدير", "Export")}`;
        exportBtn.onclick = () => exportDashboard("csv");
        headerActions.insertBefore(exportBtn, headerActions.firstChild);
      }
    });
  })();
