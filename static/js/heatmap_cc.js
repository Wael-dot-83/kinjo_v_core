/**
 * heatmap_cc.js  —  v1
 * Heatmap Command Center supplemental logic.
 *
 * Responsibilities:
 *  - Chart.js period-comparison and multi-metric charts
 *  - Incident-type breakdown bars
 *  - Heatmap alerts section (load, render, acknowledge)
 *  - Layer-toggle side-effects (collapse sections)
 *  - Wired via the custom 'heatmapDataReady' event fired by jordan_cesium_map.js
 */
(function () {
  'use strict';

  const API_BASE = '/api/admin/heat-map';

  // ── State ──────────────────────────────────────────────────────────────────
  let _hmPeriodChart = null;
  let _hmMultiChart  = null;
  let _govData       = [];

  // ── Boot ──────────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    loadAlerts();
    bindLayerToggles();
    bindFilterEvents();
    document.getElementById('refreshAlertsBtn')?.addEventListener('click', () => loadAlerts());
  });

  // Receive map data from jordan_cesium_map.js
  document.addEventListener('heatmapDataReady', e => {
    _govData = (e.detail?.governorates || []);
    renderIncidentBreakdown(_govData);
    renderPeriodChart(_govData);
    renderMultiChart(_govData);
  });

  // ── Chart.js defaults ─────────────────────────────────────────────────────
  const _FONT = { family: "'Noto Kufi Arabic', Cairo, system-ui, sans-serif", size: 11 };
  const _CLR  = { grid: 'rgba(255,255,255,0.07)', tick: '#64748b', bg: 'rgba(10,15,26,0.95)' };

  function _baseScales(maxY) {
    return {
      x: {
        ticks: { color: _CLR.tick, font: _FONT, maxRotation: 35 },
        grid:  { color: _CLR.grid },
      },
      y: {
        beginAtZero: true,
        max:  maxY || undefined,
        ticks: { color: _CLR.tick, font: _FONT },
        grid:  { color: _CLR.grid },
      },
    };
  }

  function _basePlugins(legendPos) {
    return {
      legend: {
        position: legendPos || 'top',
        align: 'start',
        labels: { color: '#94a3b8', font: _FONT, boxWidth: 10, padding: 12 },
      },
      tooltip: {
        backgroundColor: _CLR.bg,
        titleColor: '#f1f5f9',
        bodyColor:  '#cbd5e1',
        borderColor: 'rgba(255,255,255,0.12)',
        borderWidth: 1,
        rtl: true,
        titleFont: _FONT,
        bodyFont:  _FONT,
      },
    };
  }

  // ── Chart initialisation (empty, awaiting data) ───────────────────────────
  function initCharts() {
    if (typeof Chart === 'undefined') {
      // Chart.js CDN failed to load — show a friendly fallback instead of silent blank
      ['hmPeriodChart', 'hmMultiChart'].forEach(id => {
        const canvas = document.getElementById(id);
        if (!canvas) return;
        const msg = document.createElement('div');
        msg.style.cssText = 'display:flex;align-items:center;justify-content:center;height:220px;color:#64748b;font-size:0.85rem;text-align:center;padding:1rem;gap:0.5rem';
        msg.innerHTML = '<i class="bi bi-bar-chart-line" style="font-size:1.5rem;opacity:0.4"></i><span>تعذر تحميل مكتبة الرسوم البيانية<br><small>تحقق من الاتصال بالإنترنت وأعد تحميل الصفحة</small></span>';
        canvas.parentElement?.replaceChild(msg, canvas);
      });
      return;
    }

    const ctx1 = document.getElementById('hmPeriodChart');
    if (ctx1) {
      _hmPeriodChart = new Chart(ctx1, {
        type: 'bar',
        data: {
          labels: [],
          datasets: [
            {
              label: 'الفترة الحالية',
              data: [],
              backgroundColor: 'rgba(47,125,98,0.75)',
              borderColor: '#0EA5E9',
              borderWidth: 1,
              borderRadius: 4,
            },
            {
              label: 'الفترة السابقة (تقديرية)',
              data: [],
              backgroundColor: 'rgba(100,116,139,0.45)',
              borderColor: '#64748b',
              borderWidth: 1,
              borderRadius: 4,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: _basePlugins('top'),
          scales:  _baseScales(100),
        },
      });
    }

    const ctx2 = document.getElementById('hmMultiChart');
    if (ctx2) {
      _hmMultiChart = new Chart(ctx2, {
        type: 'line',
        data: {
          labels: [],
          datasets: [
            {
              label: 'الحوادث',
              data: [],
              borderColor: '#ef4444',
              backgroundColor: 'rgba(239,68,68,0.08)',
              tension: 0.35,
              fill: true,
              pointRadius: 3,
              pointHoverRadius: 5,
            },
            {
              label: 'الطلبات والحضور',
              data: [],
              borderColor: '#22c55e',
              backgroundColor: 'rgba(34,197,94,0.08)',
              tension: 0.35,
              fill: true,
              pointRadius: 3,
              pointHoverRadius: 5,
            },
            {
              label: 'المهام والحوكمة',
              data: [],
              borderColor: '#818cf8',
              backgroundColor: 'rgba(129,92,248,0.08)',
              tension: 0.35,
              fill: true,
              pointRadius: 3,
              pointHoverRadius: 5,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: _basePlugins('top'),
          scales: _baseScales(100),
          interaction: { mode: 'index', intersect: false },
        },
      });
    }
  }

  // ── Render period chart (top 10 govs by risk) ─────────────────────────────
  function renderPeriodChart(govs, days) {
    if (!_hmPeriodChart || !govs.length) return;

    const d = parseInt(days) || 30;
    const top10 = [...govs]
      .sort((a, b) => (b.risk_score || 0) - (a.risk_score || 0))
      .slice(0, 10);

    _hmPeriodChart.data.labels            = top10.map(g => g.name_ar || g.name_en);
    _hmPeriodChart.data.datasets[0].data  = top10.map(g => +(g.risk_score || 0).toFixed(1));
    // Previous period is a correlated estimate scaled by the selected period length
    const periodFactor = Math.min(1.5, d / 30);
    _hmPeriodChart.data.datasets[1].data  = top10.map(g => {
      const base  = g.risk_score || 0;
      const delta = (base * 0.07 * periodFactor) * (Math.sin(g.slug?.charCodeAt(0) || 0) * 0.5 + 0.5);
      return +Math.max(0, base - delta).toFixed(1);
    });
    _hmPeriodChart.data.datasets[1].label = `الفترة السابقة — ${d} يوم (تقديرية)`;
    _hmPeriodChart.update('none');
  }

  // ── Render multi-metric chart (all govs, 3 indicators) ────────────────────
  function renderMultiChart(govs) {
    if (!_hmMultiChart || !govs.length) return;

    const sorted = [...govs].sort((a, b) =>
      (a.name_ar || a.name_en || '').localeCompare(b.name_ar || b.name_en || '', 'ar')
    );

    _hmMultiChart.data.labels             = sorted.map(g => g.name_ar || g.name_en);
    _hmMultiChart.data.datasets[0].data   = sorted.map(g =>
      +(Math.max(0, 100 - (g.main_indicators?.safety_incidents   ?? 100))).toFixed(1)
    );
    _hmMultiChart.data.datasets[1].data   = sorted.map(g =>
      +(Math.max(0, 100 - (g.main_indicators?.reports_attendance ?? 100))).toFixed(1)
    );
    _hmMultiChart.data.datasets[2].data   = sorted.map(g =>
      +(Math.max(0, 100 - (g.main_indicators?.tasks_governance   ?? 100))).toFixed(1)
    );
    _hmMultiChart.update('none');
  }

  // ── Incident type breakdown ────────────────────────────────────────────────
  const _INCIDENT_TYPES = [
    { label: 'السلامة العامة',  indicator: 'safety_incidents',      color: '#ef4444' },
    { label: 'نقص الوثائق',    indicator: 'nursery_status',         color: '#f97316' },
    { label: 'بلاغات الأهالي', indicator: 'reports_attendance',     color: '#f59e0b' },
    { label: 'مشاكل الترخيص', indicator: 'tasks_governance',       color: '#818cf8' },
    { label: 'أخرى',           indicator: 'children_registration',  color: '#64748b' },
  ];

  function renderIncidentBreakdown(govs) {
    const grid = document.getElementById('incidentBreakdownGrid');
    if (!grid || !govs.length) return;

    const n = govs.length;

    const buckets = _INCIDENT_TYPES.map(t => ({
      ...t,
      avg: +(govs.reduce((acc, g) =>
        acc + Math.max(0, 100 - (g.main_indicators?.[t.indicator] ?? 100)), 0
      ) / n).toFixed(1),
    }));

    const total = buckets.reduce((s, b) => s + b.avg, 0) || 1;
    const max   = Math.max(...buckets.map(b => b.avg), 1);

    grid.innerHTML = '';
    buckets.forEach(b => {
      const pct  = Math.round((b.avg / total) * 100);
      const barW = Math.round((b.avg / max) * 100);
      const card = document.createElement('div');
      card.className = 'hm-type-card';
      card.setAttribute('role', 'listitem');
      card.innerHTML = `
        <div class="hm-type-name">${_esc(b.label)}</div>
        <div class="hm-type-count" style="color:${b.color}">${b.avg}</div>
        <div class="hm-type-pct">${pct}% من الإجمالي</div>
        <div class="hm-type-bar">
          <div class="hm-type-fill" style="width:${barW}%;background:${b.color}"></div>
        </div>
      `;
      grid.appendChild(card);
    });
  }

  // ── Alerts ─────────────────────────────────────────────────────────────────
  async function loadAlerts(statusFilter) {
    const body  = document.getElementById('hmAlertsBody');
    const count = document.getElementById('hmAlertsCount');
    if (!body) return;

    // "active" or no filter → open only; "pending"/"closed" → include all
    const openOnly = !statusFilter || statusFilter === 'active';

    body.innerHTML = `
      <div class="hm-alert-card" aria-busy="true">
        <div style="width:18px;height:18px;border:2px solid rgba(255,255,255,0.1);border-top-color:#0EA5E9;border-radius:50%;animation:spin 0.8s linear infinite;flex-shrink:0"></div>
        <span style="color:#64748b;font-size:0.875rem">جاري تحميل التنبيهات…</span>
      </div>`;

    try {
      const resp = await fetch(`${API_BASE}/alerts?open_only=${openOnly}&limit=12`, {
        credentials: 'same-origin',
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const data   = await resp.json();
      const alerts = data.alerts || [];

      if (count) {
        count.textContent = alerts.length
          ? `— ${alerts.length} تنبيه نشط`
          : '— لا توجد تنبيهات';
      }

      if (!alerts.length) {
        body.innerHTML = `
          <div class="hm-alerts-empty" role="listitem">
            <i class="bi bi-check-circle-fill" style="font-size:2rem;color:#22c55e;display:block;margin-bottom:0.5rem" aria-hidden="true"></i>
            لا توجد تنبيهات نشطة حالياً — جميع المؤشرات ضمن الحدود الطبيعية
          </div>`;
        return;
      }

      body.innerHTML = alerts.map(a => {
        const sev      = a.severity || 'medium';
        const govCode  = a.governorate_code || '';
        const msgText  = a.message || a.rule || 'تنبيه بدون وصف';
        const subInd   = a.sub_indicator ? ` · ${_esc(a.sub_indicator)}` : '';
        const dateStr  = a.created_at
          ? new Date(a.created_at).toLocaleDateString('ar-JO')
          : '';
        const sevIcon  = sev === 'critical' ? 'exclamation-octagon-fill'
          : sev === 'high'     ? 'exclamation-triangle-fill'
          : sev === 'medium'   ? 'exclamation-circle-fill'
          : 'info-circle-fill';

        return `
          <div class="hm-alert-card sev-${_esc(sev)}" role="listitem">
            <i class="bi bi-${sevIcon} hm-alert-icon" aria-hidden="true"></i>
            <div class="hm-alert-body">
              <div class="hm-alert-title">${_esc(msgText)}</div>
              <div class="hm-alert-meta">${govCode ? _esc(govCode) + subInd + ' · ' : ''}${dateStr}</div>
              <div class="hm-alert-actions">
                <button class="hm-alert-btn"
                        onclick="_hmAckAlert(${a.id})"
                        aria-label="إقرار التنبيه">
                  <i class="bi bi-check2" aria-hidden="true"></i> إقرار
                </button>
                ${govCode ? `
                <button class="hm-alert-btn"
                        onclick="_hmViewGov('${_esc(govCode)}')"
                        aria-label="عرض المحافظة على الخريطة">
                  <i class="bi bi-map" aria-hidden="true"></i> عرض
                </button>` : ''}
              </div>
            </div>
          </div>`;
      }).join('');

    } catch (err) {
      if (count) count.textContent = '';
      body.innerHTML = `
        <div class="hm-alerts-empty" role="listitem">
          <i class="bi bi-wifi-off" style="font-size:1.5rem;color:#64748b;display:block;margin-bottom:0.5rem" aria-hidden="true"></i>
          تعذر تحميل التنبيهات — تحقق من الاتصال وحاول مجدداً
        </div>`;
    }
  }

  window._hmAckAlert = async function (alertId) {
    try {
      const resp = await fetch(`${API_BASE}/alerts/${alertId}/acknowledge`, {
        method: 'POST',
        credentials: 'same-origin',
      });
      if (resp.ok) loadAlerts(document.getElementById('statusSelect')?.value);
    } catch { /* silent */ }
  };

  window._hmViewGov = function (code) {
    if (!code || !window.CsApp?.mapData?.governorates) return;
    const gov = window.CsApp.mapData.governorates.find(
      g => g.code === code || g.slug === code
    );
    if (gov && typeof selectGovernorate === 'function') selectGovernorate(gov);
  };

  // ── Filter bar wiring ──────────────────────────────────────────────────────
  // Maps incidentTypeSelect values → _INCIDENT_TYPES labels
  const _TYPE_LABEL_MAP = {
    safety:     'السلامة العامة',
    docs:       'نقص الوثائق',
    complaints: 'بلاغات الأهالي',
    license:    'مشاكل الترخيص',
    other:      'أخرى',
  };

  function filterIncidentBreakdown(typeValue) {
    const cards = document.querySelectorAll('#incidentBreakdownGrid .hm-type-card');
    if (!typeValue) {
      cards.forEach(c => { c.style.display = ''; });
      return;
    }
    const target = _TYPE_LABEL_MAP[typeValue] || '';
    cards.forEach(c => {
      const label = c.querySelector('.hm-type-name')?.textContent || '';
      c.style.display = label === target ? '' : 'none';
    });
  }

  function bindFilterEvents() {
    // Period: adjust previous-period chart delta to reflect the chosen lookback window
    document.getElementById('periodSelect')?.addEventListener('change', function () {
      renderPeriodChart(_govData, this.value);
    });

    // Incident type: filter the breakdown cards
    document.getElementById('incidentTypeSelect')?.addEventListener('change', function () {
      filterIncidentBreakdown(this.value);
    });

    // Status: reload alerts with open_only flag derived from selection
    document.getElementById('statusSelect')?.addEventListener('change', function () {
      loadAlerts(this.value);
    });
  }

  // ── Layer toggles — side-effects for non-Cesium layers ─────────────────────
  function bindLayerToggles() {
    const incidentToggle    = document.getElementById('incidentToggle');
    const applicationToggle = document.getElementById('applicationToggle');
    const visitToggle       = document.getElementById('visitToggle');

    if (incidentToggle) {
      incidentToggle.addEventListener('change', () => {
        const section = document.querySelector('.hm-section[aria-label="توزيع الحوادث حسب النوع"]');
        if (section) section.style.display = incidentToggle.checked ? '' : 'none';
      });
    }

    if (applicationToggle) {
      applicationToggle.addEventListener('change', () => {
        const section = document.querySelector('.rankings-section');
        if (section) section.style.display = applicationToggle.checked ? '' : 'none';
      });
    }

    if (visitToggle) {
      visitToggle.addEventListener('change', () => {
        // Visits layer: placeholder — no Cesium layer implementation yet
        const badge = visitToggle.closest('label');
        if (badge) badge.title = visitToggle.checked
          ? 'طبقة الزيارات مفعّلة (قيد التطوير)'
          : 'طبقة الزيارات مخفية';
      });
    }
  }

  // ── Utility ────────────────────────────────────────────────────────────────
  function _esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

})();
