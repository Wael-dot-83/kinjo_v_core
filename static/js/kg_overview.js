/**
 * KinJo — Interactive Kindergarten Overview  v1.0
 * Architecture: Reactive State → Render Pipeline → Chart Engine
 * No framework dependency — pure modern JS (ES2020+)
 */

/* ════════════════════════════════════════════════════════════
   1. REACTIVE STATE STORE
   ════════════════════════════════════════════════════════════ */
class KoStore {
  #state = {};
  #listeners = new Map();

  constructor(initial) {
    this.#state = structuredClone(initial);
  }

  get(key) { return this.#state[key]; }
  getAll() { return structuredClone(this.#state); }

  set(updates) {
    const prev = structuredClone(this.#state);
    Object.assign(this.#state, updates);
    this.#notify(prev);
  }

  on(key, fn) {
    if (!this.#listeners.has(key)) this.#listeners.set(key, new Set());
    this.#listeners.get(key).add(fn);
    return () => this.#listeners.get(key).delete(fn);
  }

  #notify(prev) {
    for (const [key, fns] of this.#listeners) {
      if (JSON.stringify(this.#state[key]) !== JSON.stringify(prev[key])) {
        fns.forEach(fn => fn(this.#state[key], prev[key]));
      }
    }
    const anyFns = this.#listeners.get('*');
    if (anyFns) anyFns.forEach(fn => fn(this.#state, prev));
  }
}

function computeKPIs(kgs) {
  const totalChildren = kgs.reduce((s, k) => s + k.children, 0);
  const totalTeachers = kgs.reduce((s, k) => s + k.teachers, 0);
  const avgAttendance = kgs.length ? Math.round(kgs.reduce((s, k) => s + k.attendance, 0) / kgs.length) : 0;
  const totalAlerts   = kgs.reduce((s, k) => s + k.alerts, 0);
  return { totalChildren, totalTeachers, avgAttendance, totalAlerts };
}

function koEscape(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function koCssEscape(value) {
  const text = String(value ?? '');
  if (window.CSS?.escape) return window.CSS.escape(text);
  return text.replace(/["\\]/g, '\\$&');
}

function normalizeSeverity(severity) {
  const value = String(severity || '').toUpperCase();
  if (value === 'CRITICAL' || value === 'HIGH') return 'high';
  if (value === 'MEDIUM') return 'medium';
  return 'low';
}

function mapOverviewPayload(payload) {
  const kindergartens = Array.isArray(payload?.kindergartens) ? payload.kindergartens : [];
  const kgs = kindergartens.map((kg) => {
    const children = Number(kg.children_count ?? kg.active_children ?? kg.children ?? 0);
    // GET /api/admin/kg-overview has never sent occupancy_rate/capacity/total_capacity —
    // only capacity_utilization (a real, already-computed percentage; see
    // admin_endpoints.py's cap_util = enrolled/total_capacity*100). Reading the
    // wrong field names meant `occupancy` was always 0, so `capacity` always
    // fell through to `children` itself, and every kindergarten's downstream
    // occupancy display computed as children/children = 100%, regardless of
    // its real enrollment vs. real capacity.
    const occupancy = Number(kg.capacity_utilization ?? kg.occupancy_rate ?? 0);
    const capacity = Number(kg.capacity ?? kg.total_capacity ?? (occupancy > 0 ? Math.ceil(children / (occupancy / 100)) : children));
    const name = window.KINJO_LANG === 'en'
      ? (kg.name_en || kg.name_ar || kg.name || `KG ${kg.id}`)
      : (kg.name_ar || kg.name_en || kg.name || `KG ${kg.id}`);
    return {
      id: kg.id,
      name,
      gov: kg.governorate || kg.governorate_name_ar || kg.governorate_name_en || '',
      children,
      teachers: Number(kg.teachers_count ?? kg.teachers ?? 0),
      attendance: Number(kg.attendance_rate ?? kg.attendance ?? 0),
      alerts: Number(kg.open_alerts ?? kg.alerts ?? 0),
      capacity: Math.max(capacity || children || 1, 1),
    };
  });

  const alerts = (Array.isArray(payload?.alerts) ? payload.alerts : []).map((alert, index) => {
    const ageHours = Number(alert.age_hours ?? 0);
    const title = alert.title || alert.message || alert.metric || '';
    return {
      id: String(alert.id ?? `alert-${index}`),
      sev: normalizeSeverity(alert.severity),
      icon: normalizeSeverity(alert.severity) === 'high' ? 'bi-exclamation-triangle-fill' : 'bi-info-circle-fill',
      title,
      desc: alert.message || title,
      kg: alert.kindergarten_name_ar || alert.kindergarten_name_en || alert.kindergarten_name || '',
      ts: Date.now() - Math.max(ageHours, 0) * 3600000,
    };
  });

  return {
    kgs,
    alerts,
    trend: {
      labels: kgs.map((kg) => kg.name),
      attendance: kgs.map((kg) => kg.attendance),
      enrollment: kgs.map((kg) => kg.children),
    },
  };
}

/* ════════════════════════════════════════════════════════════
   3. CHART ENGINE
   ════════════════════════════════════════════════════════════ */
class KoCharts {
  #instances = {};

  get isDark() { return document.documentElement.getAttribute('data-theme') === 'dark'; }
  get textColor() { return this.isDark ? '#8892ab' : '#6b7a99'; }
  get gridColor()  { return this.isDark ? '#2a2f3e' : '#e5e9f0'; }

  baseOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 600, easing: 'easeOutQuart' },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: this.isDark ? '#1a1d27' : '#fff',
          titleColor: this.isDark ? '#e8eaf2' : '#1a2233',
          bodyColor: this.isDark ? '#8892ab' : '#6b7a99',
          borderColor: this.isDark ? '#2a2f3e' : '#e5e9f0',
          borderWidth: 1,
          padding: 10,
          cornerRadius: 8,
          callbacks: {
            title: items => items[0]?.label || '',
          }
        },
      },
      scales: {
        x: {
          grid: { color: this.gridColor, drawBorder: false },
          ticks: { color: this.textColor, font: { size: 11 }, maxRotation: 0 },
        },
        y: {
          grid: { color: this.gridColor, drawBorder: false },
          ticks: { color: this.textColor, font: { size: 11 } },
          beginAtZero: false,
        }
      },
    };
  }

  renderTrend(canvasId, data, chartType = 'line') {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    this.destroy(canvasId);
    const opts = this.baseOptions();
    const blue = '#2563eb', teal = '#0891b2';
    const isLine = chartType === 'line';

    this.#instances[canvasId] = new Chart(ctx, {
      type: isLine ? 'line' : 'bar',
      data: {
        labels: data.labels,
        datasets: [
          {
            label: 'نسبة الحضور %',
            data: data.attendance,
            borderColor: blue,
            backgroundColor: isLine
              ? ctx => { const g = ctx.chart.ctx.createLinearGradient(0,0,0,200); g.addColorStop(0,'rgba(37,99,235,.18)'); g.addColorStop(1,'rgba(37,99,235,0)'); return g; }
              : 'rgba(37,99,235,.75)',
            borderWidth: 2.5,
            tension: .4,
            fill: isLine,
            pointRadius: 3,
            pointHoverRadius: 6,
            pointBackgroundColor: blue,
          },
        ]
      },
      options: {
        ...opts,
        onClick: (e, elems) => {
          if (!elems.length) return;
          const idx = elems[0].index;
          this.#triggerDrilldown(data.labels[idx]);
        },
      }
    });
  }

  renderDonut(canvasId, kgs) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    this.destroy(canvasId);
    const colors = ['#2563eb','#16a34a','#0891b2','#d97706','#7c3aed','#dc2626','#059669','#ea580c'];
    this.#instances[canvasId] = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: kgs.map(k => k.name),
        datasets: [{
          data: kgs.map(k => k.children),
          backgroundColor: kgs.map((_, i) => colors[i % colors.length]),
          borderWidth: 2,
          borderColor: this.isDark ? '#1a1d27' : '#fff',
          hoverOffset: 8,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 700, easing: 'easeOutQuart' },
        cutout: '68%',
        plugins: {
          legend: {
            display: true,
            position: 'right',
            labels: { color: this.textColor, font: { size: 11 }, padding: 10, boxWidth: 12, boxHeight: 12 },
          },
          tooltip: this.baseOptions().plugins.tooltip,
        }
      }
    });
  }

  renderSparkline(canvasId, values, color) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    this.destroy(canvasId);
    this.#instances[canvasId] = new Chart(ctx, {
      type: 'line',
      data: {
        labels: values.map(() => ''),
        datasets: [{ data: values, borderColor: color, borderWidth: 2, tension: .4, fill: false, pointRadius: 0, }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: { x: { display: false }, y: { display: false } },
      }
    });
  }

  destroy(id) {
    if (this.#instances[id]) { this.#instances[id].destroy(); delete this.#instances[id]; }
  }
  destroyAll() { Object.keys(this.#instances).forEach(id => this.destroy(id)); }

  updateTheme() {
    Object.values(this.#instances).forEach(c => {
      if (c.options.scales?.x) c.options.scales.x.ticks.color = this.textColor;
      if (c.options.scales?.y) c.options.scales.y.ticks.color = this.textColor;
      if (c.options.scales?.x) c.options.scales.x.grid.color = this.gridColor;
      if (c.options.scales?.y) c.options.scales.y.grid.color = this.gridColor;
      c.update('none');
    });
  }

  #triggerDrilldown(label) {
    document.dispatchEvent(new CustomEvent('ko:drilldown', { detail: { label } }));
  }
}

/* ════════════════════════════════════════════════════════════
   4. DRAG & DROP (native HTML5)
   ════════════════════════════════════════════════════════════ */
class KoDnD {
  #dragSrc = null;

  enable(containerSel) {
    const container = document.querySelector(containerSel);
    if (!container) return;

    container.addEventListener('dragstart', e => {
      const card = e.target.closest('[draggable="true"]');
      if (!card) return;
      this.#dragSrc = card;
      card.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
    });

    container.addEventListener('dragend', e => {
      document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
      e.target.closest('[draggable="true"]')?.classList.remove('dragging');
    });

    container.addEventListener('dragover', e => {
      e.preventDefault();
      const over = e.target.closest('[draggable="true"]');
      if (!over || over === this.#dragSrc) return;
      document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
      over.classList.add('drag-over');
    });

    container.addEventListener('drop', e => {
      e.preventDefault();
      const over = e.target.closest('[draggable="true"]');
      if (!over || over === this.#dragSrc) return;
      over.classList.remove('drag-over');

      const srcIdx = [...container.children].indexOf(this.#dragSrc);
      const tgtIdx = [...container.children].indexOf(over);
      if (srcIdx < 0 || tgtIdx < 0) return;

      if (srcIdx < tgtIdx) container.insertBefore(this.#dragSrc, over.nextSibling);
      else                 container.insertBefore(this.#dragSrc, over);

      document.dispatchEvent(new CustomEvent('ko:reorder', {
        detail: { order: [...container.children].map(c => c.dataset.kpiKey) }
      }));
    });
  }
}

/* ════════════════════════════════════════════════════════════
   5. PERSISTENCE LAYER
   ════════════════════════════════════════════════════════════ */
const KoPersist = {
  KEY: 'ko_layout_v1',
  save(data) {
    try { localStorage.setItem(this.KEY, JSON.stringify(data)); } catch {}
  },
  load() {
    try { return JSON.parse(localStorage.getItem(this.KEY) || 'null'); } catch { return null; }
  },
  reset() { localStorage.removeItem(this.KEY); }
};

/* ════════════════════════════════════════════════════════════
   6. MAIN CONTROLLER
   ════════════════════════════════════════════════════════════ */
class KgOverview {
  #store;
  #charts;
  #dnd;
  #rtTimer = null;
  #alertFilterSev = 'all';
  #dismissedAlerts = new Set();
  #chartType = 'line';
  #currentView = 'cards';
  #panelOpen = false;
  #panelKey = null;
  #customiseOpen = false;

  constructor() {
    const saved = KoPersist.load() || {};

    this.#store = new KoStore({
      period:     saved.period     || 'month',
      govFilter:  saved.govFilter  || 'all',
      kgFilter:   saved.kgFilter   || 'all',
      kgs:        [],
      kpis:       computeKPIs([]),
      alerts:     [],
      trend:      { labels: [], attendance: [], enrollment: [] },
      theme:      saved.theme      || 'light',
      hiddenKPIs: saved.hiddenKPIs || [],
      kpiOrder:   saved.kpiOrder   || ['children','attendance','teachers','alerts'],
    });

    this.#charts = new KoCharts();
    this.#dnd    = new KoDnD();
  }

  /* ── Init ─────────────────────────────────────────────── */
  async init() {
    this.#applyTheme(this.#store.get('theme'));
    await this.#loadOverviewData().catch(error => {
      console.error('[KgOverview] initial data load failed', error);
    });
    this.#buildControlBar();
    this.#renderKPIs();
    this.#renderDataSection();
    this.#renderQuickActions();
    this.#renderAlerts();
    this.#buildCustomisePanel();
    this.#bindGlobalEvents();
    this.#dnd.enable('.ko-kpi-grid');
    this.#startRealtime();
    this.#renderLastUpdated();
    this.#openDeepLinkedKG();
  }

  /* ── Deep link (e.g. /admin/kg-overview?id=42 from the KPI dashboard) ── */
  #openDeepLinkedKG() {
    const id = new URLSearchParams(window.location.search).get('id');
    if (!id) return;
    const kg = this.#store.get('kgs').find(k => String(k.id) === String(id));
    if (kg) this.#openKGPanel(kg);
  }

  async #loadOverviewData() {
    const params = new URLSearchParams();
    const period = this.#store.get('period');
    if (period && period !== 'all') params.set('period', period);
    const response = await fetchWithAuth(`/api/admin/kg-overview?${params.toString()}`);
    if (!response) return;
    const payload = await response.json();
    const mapped = mapOverviewPayload(payload);
    this.#store.set({
      kgs: mapped.kgs,
      kpis: computeKPIs(mapped.kgs),
      alerts: mapped.alerts,
      trend: mapped.trend,
    });
  }

  /* ── Control Bar ──────────────────────────────────────── */
  #buildControlBar() {
    const bar = document.getElementById('ko-control-bar');
    if (!bar) return;

    const periods = [
      { key:'today', ar:'اليوم',    en:'Today' },
      { key:'week',  ar:'الأسبوع', en:'Week'  },
      { key:'month', ar:'الشهر',   en:'Month' },
    ];

    const currentKgs = this.#store.get('kgs');
    const govs = ['all', ...new Set(currentKgs.map(k => k.gov).filter(Boolean))];
    const kgNames = ['all', ...currentKgs.map(k => k.name)];
    const lang = window.KINJO_LANG || 'ar';
    const isAr = lang !== 'en';
    const cur  = this.#store.get('period');

    bar.innerHTML = `
      <div class="ko-period-btns" role="group" aria-label="${isAr ? 'فترة زمنية' : 'Time period'}">
        ${periods.map(p => `
          <button class="ko-period-btn ${cur === p.key ? 'active' : ''}"
                  data-period="${p.key}" aria-pressed="${cur === p.key}">
            ${isAr ? p.ar : p.en}
          </button>`).join('')}
        <button class="ko-period-btn ${cur === 'custom' ? 'active' : ''}" data-period="custom">
          ${isAr ? 'مخصص' : 'Custom'} <i class="bi bi-calendar3 ms-1"></i>
        </button>
      </div>

      <div class="ko-date-range" id="ko-date-range-wrap" style="${cur !== 'custom' ? 'display:none' : ''}">
        <input type="date" class="ko-date-input" id="ko-date-from"
               value="${this.#today(-30)}" aria-label="${isAr ? 'من' : 'From'}">
        <span class="text-muted" style="font-size:.8rem">→</span>
        <input type="date" class="ko-date-input" id="ko-date-to"
               value="${this.#today(0)}" aria-label="${isAr ? 'إلى' : 'To'}">
      </div>

      <select class="ko-filter-select" id="ko-gov-filter" aria-label="${isAr ? 'المحافظة' : 'Governorate'}">
        ${govs.map(g => `<option value="${g}">${g === 'all' ? (isAr ? 'كل المحافظات' : 'All Governorates') : g}</option>`).join('')}
      </select>

      <select class="ko-filter-select" id="ko-kg-filter" aria-label="${isAr ? 'الحضانة' : 'Kindergarten'}">
        ${kgNames.map(n => `<option value="${n}">${n === 'all' ? (isAr ? 'كل الحضانات' : 'All Kindergartens') : n}</option>`).join('')}
      </select>

      <div class="ko-bar-end">
        <span class="ko-live-badge" id="ko-live-badge">
          <span class="ko-rt-dot"></span>${isAr ? 'مباشر' : 'Live'}
        </span>
        <button class="ko-icon-btn" id="ko-refresh-btn" title="${isAr ? 'تحديث' : 'Refresh'}" aria-label="${isAr ? 'تحديث' : 'Refresh'}">
          <i class="bi bi-arrow-clockwise" aria-hidden="true"></i>
        </button>
        <button class="ko-icon-btn" id="ko-customise-btn" title="${isAr ? 'تخصيص' : 'Customize'}" aria-label="${isAr ? 'تخصيص العناصر' : 'Customize components'}">
          <i class="bi bi-sliders" aria-hidden="true"></i>
        </button>
        <button class="ko-icon-btn" id="ko-theme-btn" title="${isAr ? 'الوضع الليلي' : 'Dark mode'}" aria-label="${isAr ? 'تبديل الوضع الليلي' : 'Toggle dark mode'}">
          <i class="bi ${this.#store.get('theme') === 'dark' ? 'bi-sun-fill' : 'bi-moon-fill'}" aria-hidden="true"></i>
        </button>
        <button class="ko-icon-btn" id="ko-export-btn" title="${isAr ? 'تصدير' : 'Export'}" aria-label="${isAr ? 'تصدير البيانات كملف CSV' : 'Export data as CSV'}">
          <i class="bi bi-download" aria-hidden="true"></i>
        </button>
      </div>`;

    /* Period buttons — unlike governorate/kg (client-side-only filters over
       an already-fetched full dataset), `period` genuinely changes the
       server-side attendance date window (admin_endpoints.py), so choosing
       "Today"/"Week"/"Month" used to have no visible effect until the next
       manual refresh or the 60s auto-poll: #onFilterChange() only re-rendered
       already-fetched data, it never called #loadOverviewData() again. */
    bar.querySelectorAll('.ko-period-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const p = btn.dataset.period;
        bar.querySelectorAll('.ko-period-btn').forEach(b => { b.classList.remove('active'); b.setAttribute('aria-pressed','false'); });
        btn.classList.add('active'); btn.setAttribute('aria-pressed','true');
        const dateWrap = document.getElementById('ko-date-range-wrap');
        dateWrap.style.display = p === 'custom' ? '' : 'none';
        this.#store.set({ period: p });
        this.#onPeriodChange();
      });
    });

    /* Date range */
    ['ko-date-from','ko-date-to'].forEach(id => {
      document.getElementById(id)?.addEventListener('change', () => this.#onFilterChange());
    });

    /* Governorate filter */
    document.getElementById('ko-gov-filter').addEventListener('change', e => {
      this.#store.set({ govFilter: e.target.value });
      this.#onFilterChange();
    });

    /* KG filter */
    document.getElementById('ko-kg-filter').addEventListener('change', e => {
      this.#store.set({ kgFilter: e.target.value });
      this.#onFilterChange();
    });

    /* Refresh */
    document.getElementById('ko-refresh-btn').addEventListener('click', () => this.#refresh());

    /* Theme toggle */
    document.getElementById('ko-theme-btn').addEventListener('click', () => {
      const next = this.#store.get('theme') === 'dark' ? 'light' : 'dark';
      this.#store.set({ theme: next });
      this.#applyTheme(next);
      document.getElementById('ko-theme-btn').querySelector('i').className =
        `bi ${next === 'dark' ? 'bi-sun-fill' : 'bi-moon-fill'}`;
      this.#charts.updateTheme();
      this.#savePrefs();
    });

    /* Customise */
    document.getElementById('ko-customise-btn').addEventListener('click', () => this.#toggleCustomise());

    /* Export */
    document.getElementById('ko-export-btn').addEventListener('click', () => this.#exportCSV());
  }

  /* ── KPI Cards ────────────────────────────────────────── */
  #KPI_META = {
    children:   { label_ar:'إجمالي الأطفال', label_en:'Children',   icon:'bi-people-fill',           accent:'#2563eb', unit:'' },
    attendance: { label_ar:'نسبة الحضور',    label_en:'Attendance', icon:'bi-calendar-check-fill',   accent:'#16a34a', unit:'%' },
    teachers:   { label_ar:'المعلمات',        label_en:'Teachers',   icon:'bi-person-badge-fill',     accent:'#7c3aed', unit:'' },
    alerts:     { label_ar:'التنبيهات',       label_en:'Alerts',     icon:'bi-bell-fill',             accent:'#dc2626', unit:'' },
  };

  #kpiValue(key) {
    const kpis = this.#store.get('kpis');
    switch(key) {
      case 'children':   return kpis.totalChildren;
      case 'attendance': return kpis.avgAttendance;
      case 'teachers':   return kpis.totalTeachers;
      case 'alerts':     return kpis.totalAlerts;
    }
  }

  #kpiDelta(key) {
    const base = { children:230, attendance:78, teachers:25, alerts:8 };
    const cur  = this.#kpiValue(key);
    const diff = cur - base[key];
    if (Math.abs(diff) < 1) return { dir:'flat', text:'—' };
    const pct  = ((diff / base[key]) * 100).toFixed(1);
    return diff > 0
      ? { dir:'up',   text:`+${pct}%` }
      : { dir:'down', text:`${pct}%` };
  }

  #renderKPIs() {
    const grid = document.getElementById('ko-kpi-grid');
    if (!grid) return;
    const lang  = window.KINJO_LANG || 'ar';
    const isAr  = lang !== 'en';
    const hidden = this.#store.get('hiddenKPIs');
    const order  = this.#store.get('kpiOrder');
    const sparkData = {
      children:   [220,225,230,228,235,240,238,245,242,248,250,252,255,this.#kpiValue('children')],
      attendance: [72,75,73,78,76,80,79,82,80,83,81,84,82,this.#kpiValue('attendance')],
      teachers:   [22,22,23,23,24,24,25,25,25,26,26,26,27,this.#kpiValue('teachers')],
      alerts:     [5,6,8,7,9,8,6,7,8,9,7,8,9,this.#kpiValue('alerts')],
    };

    grid.innerHTML = order.map(key => {
      const meta  = this.#KPI_META[key];
      const val   = this.#kpiValue(key);
      const delta = this.#kpiDelta(key);
      const isHidden = hidden.includes(key);
      return `
        <div class="ko-kpi-card ${isHidden ? 'ko-hidden' : ''}"
             draggable="true"
             data-kpi-key="${key}"
             style="--accent:${meta.accent}"
             role="button" tabindex="0"
             aria-label="${isAr ? meta.label_ar : meta.label_en}: ${val}${meta.unit}"
             data-action="open-panel" data-panel-key="${key}">
          <div class="ko-kpi-icon"><i class="bi ${meta.icon}"></i></div>
          <div class="ko-kpi-label">${isAr ? meta.label_ar : meta.label_en}</div>
          <div class="ko-kpi-value" id="ko-val-${key}">${val}${meta.unit}</div>
          <div class="ko-kpi-delta ${delta.dir}" id="ko-delta-${key}">
            ${delta.dir === 'up' ? '<i class="bi bi-arrow-up-short"></i>' : delta.dir === 'down' ? '<i class="bi bi-arrow-down-short"></i>' : '<i class="bi bi-dash"></i>'}
            ${delta.text} ${isAr ? 'مقارنة بالشهر السابق' : 'vs last period'}
          </div>
          <div style="height:44px;overflow:hidden;position:relative;margin-top:.875rem;">
            <canvas id="ko-spark-${key}" aria-hidden="true" style="display:block;width:100%;height:44px;"></canvas>
          </div>
        </div>`;
    }).join('');

    order.forEach(key => this.#charts.renderSparkline(`ko-spark-${key}`, sparkData[key], this.#KPI_META[key].accent));

    grid.querySelectorAll('[data-action="open-panel"]').forEach(el => {
      el.addEventListener('click', () => this.#openPanel(el.dataset.panelKey));
      el.addEventListener('keydown', e => { if (e.key === 'Enter') this.#openPanel(el.dataset.panelKey); });
    });
  }

  #updateKPIValues() {
    const hidden = this.#store.get('hiddenKPIs');
    this.#store.get('kpiOrder').forEach(key => {
      const el = document.getElementById(`ko-val-${key}`);
      if (!el) return;
      const newVal = this.#kpiValue(key) + this.#KPI_META[key].unit;
      if (el.textContent !== newVal) {
        el.textContent = newVal;
        el.classList.remove('pulse');
        void el.offsetWidth;
        el.classList.add('pulse');
      }
    });
  }

  /* ── Data Section ─────────────────────────────────────── */
  #renderDataSection() {
    const sec = document.getElementById('ko-data-section');
    if (!sec) return;
    const lang = window.KINJO_LANG || 'ar';
    const isAr = lang !== 'en';

    sec.innerHTML = `
      <div class="ko-section-header">
        <h2 class="ko-section-title">
          <i class="bi bi-bar-chart-line-fill"></i>
          ${isAr ? 'نظرة عامة على الحضانات' : 'Kindergartens Overview'}
        </h2>
        <div style="display:flex;gap:.5rem;align-items:center;flex-wrap:wrap;">
          <div class="ko-chart-type-btns" id="ko-chart-type-btns">
            ${['line','bar'].map(t => `
              <button class="ko-chart-type-btn ${this.#chartType === t ? 'active' : ''}"
                      data-chart-type="${t}" title="${t}">
                <i class="bi bi-graph-${t === 'line' ? 'up' : 'bar-chart-fill'}"></i>
              </button>`).join('')}
          </div>
          <div class="ko-view-switcher">
            ${[
              { k:'cards', i:'bi-grid',      ar:'بطاقات',  en:'Cards' },
              { k:'chart', i:'bi-bar-chart', ar:'مخطط',    en:'Chart' },
              { k:'table', i:'bi-table',     ar:'جدول',    en:'Table' },
            ].map(v => `
              <button class="ko-view-btn ${this.#currentView === v.k ? 'active' : ''}"
                      data-view="${v.k}" aria-pressed="${this.#currentView === v.k}">
                <i class="bi ${v.i}"></i> ${isAr ? v.ar : v.en}
              </button>`).join('')}
          </div>
        </div>
      </div>

      <!-- Cards View -->
      <div class="ko-data-panel ${this.#currentView !== 'cards' ? 'ko-hidden' : ''}" id="ko-view-cards">
        <div class="ko-kg-grid" id="ko-kg-cards"></div>
        <div id="ko-cards-pagination" class="d-flex align-items-center justify-content-center gap-1 py-2 flex-wrap" style="border-top:1px solid var(--ko-border)"></div>
      </div>

      <!-- Chart View -->
      <div class="ko-data-panel ${this.#currentView !== 'chart' ? 'ko-hidden' : ''}" id="ko-view-chart">
        <div class="ko-chart-wrap" style="height:340px;">
          <canvas id="ko-trend-chart"></canvas>
        </div>
        <div class="ko-chart-wrap" style="height:280px; border-top:1px solid var(--ko-border);">
          <canvas id="ko-donut-chart"></canvas>
        </div>
      </div>

      <!-- Table View -->
      <div class="ko-data-panel ${this.#currentView !== 'table' ? 'ko-hidden' : ''}" id="ko-view-table">
        <div style="overflow-x:auto;">
          <table class="ko-table" id="ko-kg-table">
            <caption class="visually-hidden">${isAr ? 'قائمة الحضانات مع مؤشرات الأداء' : 'Kindergarten list with performance indicators'}</caption>
            <thead>
              <tr>
                ${[
                  { k:'name', ar:'اسم الحضانة',     en:'Kindergarten'  },
                  { k:'gov',  ar:'المحافظة',        en:'Governorate'   },
                  { k:'children', ar:'الأطفال',     en:'Children'      },
                  { k:'teachers', ar:'المعلمات',    en:'Teachers'      },
                  { k:'attendance', ar:'الحضور %',  en:'Attendance %'  },
                  { k:'alerts', ar:'التنبيهات',     en:'Alerts'        },
                  { k:'status', ar:'الحالة',        en:'Status'        },
                ].map(c => `<th scope="col" data-sort="${c.k}" tabindex="0" role="button" aria-sort="none">${isAr ? c.ar : c.en} <i class="bi bi-arrow-down-up" style="opacity:.4;font-size:.7em" aria-hidden="true"></i></th>`).join('')}
              </tr>
            </thead>
            <tbody id="ko-table-body"></tbody>
          </table>
        </div>
        <div id="ko-table-pagination" class="d-flex align-items-center justify-content-center gap-1 py-2 flex-wrap" style="border-top:1px solid var(--ko-border)"></div>
      </div>`;

    /* View switcher */
    sec.querySelectorAll('.ko-view-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        this.#currentView = btn.dataset.view;
        sec.querySelectorAll('.ko-view-btn').forEach(b => { b.classList.remove('active'); b.setAttribute('aria-pressed','false'); });
        btn.classList.add('active'); btn.setAttribute('aria-pressed','true');
        ['cards','chart','table'].forEach(v => {
          const p = document.getElementById(`ko-view-${v}`);
          p?.classList.toggle('ko-hidden', v !== this.#currentView);
        });
        this.#renderActiveView();
      });
    });

    /* Chart type */
    sec.querySelectorAll('.ko-chart-type-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        this.#chartType = btn.dataset.chartType;
        sec.querySelectorAll('.ko-chart-type-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        if (this.#currentView === 'chart') {
          this.#charts.destroy('ko-trend-chart');
          this.#charts.renderTrend('ko-trend-chart', this.#store.get('trend'), this.#chartType);
        }
      });
    });

    /* Table sort — was mouse-only (no tabindex/keydown), and the `th`
       argument was never used inside #sortTable, so there was no aria-sort
       or icon-direction feedback for any sort state either. */
    sec.querySelectorAll('[data-sort]').forEach(th => {
      th.addEventListener('click', () => this.#sortTable(th.dataset.sort, th));
      th.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          this.#sortTable(th.dataset.sort, th);
        }
      });
    });

    this.#renderActiveView();
  }

  #renderActiveView() {
    const kgs = this.#filteredKGs();
    if (this.#currentView === 'cards') this.#renderKGCards(kgs);
    if (this.#currentView === 'chart') {
      this.#charts.renderTrend('ko-trend-chart', this.#store.get('trend'), this.#chartType);
      this.#charts.renderDonut('ko-donut-chart', kgs);
    }
    if (this.#currentView === 'table') this.#renderTable(kgs);
  }

  #renderKGCards(kgs) {
    this.#cardsAllKgs = kgs;
    this.#cardsPage = 1;
    this.#renderCardsPage();
  }

  #renderCardsPage() {
    const wrap = document.getElementById('ko-kg-cards');
    if (!wrap) return;
    const kgs  = this.#cardsAllKgs;
    const lang = window.KINJO_LANG || 'ar';
    const isAr = lang !== 'en';

    if (!kgs.length) {
      wrap.innerHTML = `<div class="ko-empty"><i class="bi bi-search"></i><p>${isAr ? 'لا توجد نتائج' : 'No results'}</p></div>`;
      const pg = document.getElementById('ko-cards-pagination');
      if (pg) pg.innerHTML = '';
      return;
    }

    const start = (this.#cardsPage - 1) * this.#cardsPageSize;
    const page  = kgs.slice(start, start + this.#cardsPageSize);

    wrap.innerHTML = page.map(kg => {
      const pct     = Math.max(0, Math.min(100, Number(kg.attendance) || 0));
      const cls     = pct >= 80 ? '' : pct >= 65 ? 'warn' : 'alert';
      const badge   = pct >= 80 ? 'green' : pct >= 65 ? 'amber' : 'red';
      const cap     = Math.max(0, Math.min(100, Math.round((kg.children / kg.capacity) * 100)));
      const safeId  = koEscape(kg.id);
      return `
        <div class="ko-kg-card" data-kg-id="${safeId}" role="button" tabindex="0"
             aria-label="${koEscape(kg.name)} — ${isAr ? 'عرض التفاصيل' : 'View details'}">
          <div class="ko-kg-card-name">${koEscape(kg.name)}</div>
          <div class="ko-kg-card-meta">${koEscape(kg.gov)} · ${kg.children} ${isAr ? 'طفل' : 'children'}</div>
          <div class="ko-kg-bar-wrap">
            <div style="display:flex;justify-content:space-between;font-size:.72rem;color:var(--ko-text-muted);margin-bottom:.25rem;">
              <span>${isAr ? 'الحضور' : 'Attendance'}</span>
              <span class="${cls ? `ko-badge ko-badge-${badge}` : ''}">${pct}%</span>
            </div>
            <div class="ko-kg-bar"><div class="ko-kg-bar-fill ${cls}" style="width:${pct}%"></div></div>
          </div>
          <div style="margin-top:.625rem;">
            <div style="display:flex;justify-content:space-between;font-size:.72rem;color:var(--ko-text-muted);margin-bottom:.25rem;">
              <span>${isAr ? 'الإشغال' : 'Occupancy'}</span><span>${cap}%</span>
            </div>
            <div class="ko-kg-bar"><div class="ko-kg-bar-fill" style="width:${cap}%;background:var(--ko-teal)"></div></div>
          </div>
          <div style="display:flex;justify-content:space-between;margin-top:.875rem;font-size:.75rem;">
            <span style="color:var(--ko-text-muted)"><i class="bi bi-person-badge me-1"></i>${kg.teachers}</span>
            ${kg.alerts > 0 ? `<span class="ko-badge ko-badge-red"><i class="bi bi-bell me-1"></i>${kg.alerts}</span>` : '<span class="ko-badge ko-badge-green"><i class="bi bi-check-circle me-1"></i>OK</span>'}
          </div>
        </div>`;
    }).join('');

    wrap.querySelectorAll('.ko-kg-card').forEach(card => {
      const open = () => {
        const kg = kgs.find(k => String(k.id) === card.dataset.kgId);
        if (kg) this.#openKGPanel(kg);
      };
      card.addEventListener('click', open);
      card.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
      });
    });

    this.#renderKgCardsPagination(kgs.length);
  }

  #renderKgCardsPagination(total) {
    const el = document.getElementById('ko-cards-pagination');
    if (!el) return;
    const totalPages = Math.ceil(total / this.#cardsPageSize);
    if (totalPages <= 1) { el.innerHTML = ''; return; }

    const lang  = window.KINJO_LANG || 'ar';
    const isAr  = lang !== 'en';
    const cur   = this.#cardsPage;

    const show = new Set([1, totalPages, cur, cur - 1, cur + 1]
      .filter(p => p >= 1 && p <= totalPages));
    const pages = [...show].sort((a, b) => a - b);

    let prev = 0;
    const parts = [];
    for (const p of pages) {
      if (p - prev > 1) parts.push('<span style="padding:0 .3rem;color:var(--ko-text-muted)">…</span>');
      parts.push(`<button class="ko-pg-btn ${p === cur ? 'active' : ''}" data-pg="${p}">${p}</button>`);
      prev = p;
    }

    el.innerHTML = `
      <button class="ko-pg-btn" data-pg="${cur - 1}" ${cur === 1 ? 'disabled' : ''} aria-label="${isAr ? 'السابق' : 'Previous'}">
        <i class="bi bi-chevron-${isAr ? 'right' : 'left'}"></i>
      </button>
      ${parts.join('')}
      <button class="ko-pg-btn" data-pg="${cur + 1}" ${cur === totalPages ? 'disabled' : ''} aria-label="${isAr ? 'التالي' : 'Next'}">
        <i class="bi bi-chevron-${isAr ? 'left' : 'right'}"></i>
      </button>`;

    el.querySelectorAll('.ko-pg-btn:not([disabled])').forEach(btn => {
      btn.addEventListener('click', () => {
        this.#cardsPage = Number(btn.dataset.pg);
        this.#renderCardsPage();
        document.getElementById('ko-view-cards')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });
  }

  #tablePage = 1;
  #tablePageSize = 25;
  #tableAllKgs = [];
  #cardsPage = 1;
  #cardsPageSize = 24;
  #cardsAllKgs = [];

  #sortDir = {};
  #sortTable(key, th) {
    const dir = this.#sortDir[key] === 'asc' ? 'desc' : 'asc';
    this.#sortDir[key] = dir;
    const kgs = [...this.#filteredKGs()].sort((a, b) => {
      const va = a[key] ?? ''; const vb = b[key] ?? '';
      if (dir === 'asc') return va > vb ? 1 : -1;
      return va < vb ? 1 : -1;
    });
    if (th) {
      const row = th.closest('tr');
      row?.querySelectorAll('[data-sort]').forEach(otherTh => {
        if (otherTh === th) return;
        otherTh.setAttribute('aria-sort', 'none');
        const icon = otherTh.querySelector('i');
        if (icon) icon.className = 'bi bi-arrow-down-up';
      });
      th.setAttribute('aria-sort', dir === 'asc' ? 'ascending' : 'descending');
      const icon = th.querySelector('i');
      if (icon) icon.className = dir === 'asc' ? 'bi bi-arrow-up' : 'bi bi-arrow-down';
    }
    this.#renderTable(kgs);
  }

  #renderTable(kgs) {
    this.#tableAllKgs = kgs;
    this.#tablePage = 1;
    this.#renderTablePage();
  }

  #renderTablePage() {
    const tbody = document.getElementById('ko-table-body');
    if (!tbody) return;
    const kgs  = this.#tableAllKgs;
    const lang = window.KINJO_LANG || 'ar';
    const isAr = lang !== 'en';

    if (!kgs.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="ko-empty"><i class="bi bi-search"></i><br>${isAr ? 'لا توجد نتائج' : 'No results'}</td></tr>`;
      const pg = document.getElementById('ko-table-pagination');
      if (pg) pg.innerHTML = '';
      return;
    }

    const start = (this.#tablePage - 1) * this.#tablePageSize;
    const page  = kgs.slice(start, start + this.#tablePageSize);

    tbody.innerHTML = page.map(kg => {
      const attCls = kg.attendance >= 80 ? 'green' : kg.attendance >= 65 ? 'amber' : 'red';
      const alCls  = kg.alerts === 0 ? 'green' : kg.alerts <= 2 ? 'amber' : 'red';
      const safeId = koEscape(kg.id);
      return `
        <tr style="cursor:pointer" data-kg-id="${safeId}" tabindex="0" role="button"
            aria-label="${koEscape(kg.name)} — ${isAr ? 'عرض التفاصيل' : 'View details'}">
          <td><strong>${koEscape(kg.name)}</strong></td>
          <td>${koEscape(kg.gov)}</td>
          <td>${kg.children}</td>
          <td>${kg.teachers}</td>
          <td><span class="ko-badge ko-badge-${attCls}">${kg.attendance}%</span></td>
          <td>${kg.alerts > 0 ? `<span class="ko-badge ko-badge-${alCls}">${kg.alerts}</span>` : '<span class="ko-badge ko-badge-green">0</span>'}</td>
          <td><span class="ko-badge ko-badge-${attCls}">${kg.attendance >= 80 ? (isAr ? 'جيد' : 'Good') : kg.attendance >= 65 ? (isAr ? 'مقبول' : 'Fair') : (isAr ? 'ضعيف' : 'Poor')}</span></td>
        </tr>`;
    }).join('');

    tbody.querySelectorAll('tr[data-kg-id]').forEach(row => {
      const open = () => {
        const kg = kgs.find(k => String(k.id) === row.dataset.kgId);
        if (kg) this.#openKGPanel(kg);
      };
      row.addEventListener('click', open);
      row.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
      });
    });

    this.#renderKgTablePagination(kgs.length);
  }

  #renderKgTablePagination(total) {
    const el = document.getElementById('ko-table-pagination');
    if (!el) return;
    const totalPages = Math.ceil(total / this.#tablePageSize);
    if (totalPages <= 1) { el.innerHTML = ''; return; }

    const lang  = window.KINJO_LANG || 'ar';
    const isAr  = lang !== 'en';
    const cur   = this.#tablePage;

    const show = new Set([1, totalPages, cur, cur - 1, cur + 1]
      .filter(p => p >= 1 && p <= totalPages));
    const pages = [...show].sort((a, b) => a - b);

    let prev = 0;
    const parts = [];
    for (const p of pages) {
      if (p - prev > 1) parts.push('<span style="padding:0 .3rem;color:var(--ko-text-muted)">…</span>');
      parts.push(`<button class="ko-pg-btn ${p === cur ? 'active' : ''}" data-pg="${p}">${p}</button>`);
      prev = p;
    }

    el.innerHTML = `
      <button class="ko-pg-btn" data-pg="${cur - 1}" ${cur === 1 ? 'disabled' : ''} aria-label="${isAr ? 'السابق' : 'Previous'}">
        <i class="bi bi-chevron-${isAr ? 'right' : 'left'}"></i>
      </button>
      ${parts.join('')}
      <button class="ko-pg-btn" data-pg="${cur + 1}" ${cur === totalPages ? 'disabled' : ''} aria-label="${isAr ? 'التالي' : 'Next'}">
        <i class="bi bi-chevron-${isAr ? 'left' : 'right'}"></i>
      </button>`;

    el.querySelectorAll('.ko-pg-btn:not([disabled])').forEach(btn => {
      btn.addEventListener('click', () => {
        this.#tablePage = Number(btn.dataset.pg);
        this.#renderTablePage();
        document.getElementById('ko-kg-table')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });
  }

  /* ── Quick Actions ────────────────────────────────────── */
  #renderQuickActions() {
    const wrap = document.getElementById('ko-quick-actions');
    if (!wrap) return;
    const lang = window.KINJO_LANG || 'ar';
    const isAr = lang !== 'en';

    const actions = [
      { icon:'bi-map-fill',          ar:'خريطة الحضانات',  en:'KG Heatmap',    accent:'#7c3aed', href:'/admin/heatmap',         cls:'' },
      { icon:'bi-building-fill',     ar:'إدارة الحضانات',  en:'Manage KGs',    accent:'#2563eb', href:'/admin/kindergartens',   cls:'primary' },
      { icon:'bi-bar-chart-fill',    ar:'عرض تقرير',      en:'View Report',   accent:'#16a34a', href:'/admin/analytics',       cls:'' },
      { icon:'bi-bell-fill',         ar:'مراجعة التنبيهات',en:'Review Alerts', accent:'#dc2626', href:'/admin/alerts',           cls:'' },
    ];

    wrap.innerHTML = actions.map(a => `
      <a href="${a.href}" class="ko-action-btn ${a.cls}" style="--accent:${a.accent}"
         aria-label="${isAr ? a.ar : a.en}">
        <i class="bi ${a.icon}"></i>
        ${isAr ? a.ar : a.en}
      </a>`).join('');
  }

  /* ── Alerts ───────────────────────────────────────────── */
  #renderAlerts() {
    const wrap = document.getElementById('ko-alerts-section');
    if (!wrap) return;
    const lang = window.KINJO_LANG || 'ar';
    const isAr = lang !== 'en';
    const sevColors = { high:'#dc2626', medium:'#d97706', low:'#16a34a' };
    const sevText   = { high: isAr ? 'عالي' : 'High', medium: isAr ? 'متوسط' : 'Medium', low: isAr ? 'منخفض' : 'Low' };

    const filterBtns = [
      { sev:'all',    ar:'الكل',    en:'All'    },
      { sev:'high',   ar:'عالي',   en:'High'   },
      { sev:'medium', ar:'متوسط',  en:'Medium' },
      { sev:'low',    ar:'منخفض',  en:'Low'    },
    ];

    wrap.innerHTML = `
      <div class="ko-alert-filter-row">
        ${filterBtns.map(b => `
          <button class="ko-alert-filter-btn ${this.#alertFilterSev === b.sev ? 'active' : ''}"
                  data-sev="${b.sev}">${isAr ? b.ar : b.en}</button>`).join('')}
      </div>
      <div class="ko-alert-list" id="ko-alert-list"></div>`;

    wrap.querySelectorAll('.ko-alert-filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        this.#alertFilterSev = btn.dataset.sev;
        wrap.querySelectorAll('.ko-alert-filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.#renderAlertItems();
      });
    });

    this.#renderAlertItems();
  }

  #renderAlertItems() {
    const list = document.getElementById('ko-alert-list');
    if (!list) return;
    const lang = window.KINJO_LANG || 'ar';
    const isAr = lang !== 'en';
    const sevColors = { high:'#dc2626', medium:'#d97706', low:'#16a34a' };

    const filtered = this.#store.get('alerts').filter(a =>
      !this.#dismissedAlerts.has(a.id) &&
      (this.#alertFilterSev === 'all' || a.sev === this.#alertFilterSev)
    );

    if (!filtered.length) {
      list.innerHTML = `<div class="ko-empty"><i class="bi bi-check-circle-fill" style="color:var(--ko-green)"></i><p>${isAr ? 'لا توجد تنبيهات' : 'No alerts'}</p></div>`;
      return;
    }

    list.innerHTML = filtered.map(a => `
      <div class="ko-alert-item" data-alert-id="${koEscape(a.id)}" style="--sev-color:${sevColors[a.sev]}">
        <div class="ko-alert-icon"><i class="bi ${a.icon}"></i></div>
        <div class="ko-alert-body">
          <div class="ko-alert-title">${koEscape(a.title)}</div>
          <div class="ko-alert-desc">${koEscape(a.desc)}</div>
          <div class="ko-alert-meta">
            <i class="bi bi-building me-1"></i>${koEscape(a.kg)}
            · ${this.#timeAgo(a.ts, isAr)}
          </div>
        </div>
        <div class="ko-alert-actions">
          <button class="ko-alert-btn view" data-action="view-alert" data-id="${koEscape(a.id)}"
                  aria-label="${isAr ? 'عرض' : 'View'} — ${koEscape(a.title)} (${koEscape(a.kg)})">
            <i class="bi bi-eye me-1" aria-hidden="true"></i>${isAr ? 'عرض' : 'View'}
          </button>
          <button class="ko-alert-btn dismiss" data-action="dismiss-alert" data-id="${koEscape(a.id)}"
                  aria-label="${isAr ? 'تجاهل' : 'Dismiss'} — ${koEscape(a.title)} (${koEscape(a.kg)})">
            <i class="bi bi-x me-1" aria-hidden="true"></i>${isAr ? 'تجاهل' : 'Dismiss'}
          </button>
        </div>
      </div>`).join('');

    list.querySelectorAll('[data-action="dismiss-alert"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = btn.dataset.id;
        const el = list.querySelector(`[data-alert-id="${koCssEscape(id)}"]`);
        el?.classList.add('dismissed');
        setTimeout(() => { this.#dismissedAlerts.add(id); this.#renderAlertItems(); }, 400);
      });
    });

    list.querySelectorAll('[data-action="view-alert"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const a = this.#store.get('alerts').find(x => String(x.id) === btn.dataset.id);
        if (a) alert(`${a.title}\n\n${a.desc}`);
      });
    });
  }

  /* ── Side Panel ───────────────────────────────────────── */
  #openPanel(key) {
    this.#panelKey = key;
    const meta  = this.#KPI_META[key];
    const val   = this.#kpiValue(key);
    const lang  = window.KINJO_LANG || 'ar';
    const isAr  = lang !== 'en';
    const kgs   = this.#filteredKGs();

    const panelBody = document.getElementById('ko-panel-body');
    const panelTitle = document.getElementById('ko-panel-title');
    if (!panelBody || !panelTitle) return;

    panelTitle.textContent = isAr ? meta.label_ar : meta.label_en;

    panelBody.innerHTML = `
      <div class="ko-panel-stat">
        <div class="ko-panel-stat-label">${isAr ? 'الإجمالي الحالي' : 'Current Total'}</div>
        <div class="ko-panel-stat-val" style="color:${meta.accent}">${val}${meta.unit}</div>
        <div class="ko-panel-stat-sub">${isAr ? 'عبر' : 'across'} ${kgs.length} ${isAr ? 'حضانة' : 'kindergartens'}</div>
      </div>
      <div style="height:180px;margin-bottom:1.5rem;">
        <canvas id="ko-panel-chart"></canvas>
      </div>
      <h3 style="font-size:.85rem;font-weight:700;color:var(--ko-text-muted);margin-bottom:.75rem;text-transform:uppercase;letter-spacing:.06em;">
        ${isAr ? 'توزيع حسب الحضانة' : 'Breakdown by Kindergarten'}
      </h3>
      ${kgs.map(kg => {
        const v = key === 'children' ? kg.children : key === 'attendance' ? kg.attendance : key === 'teachers' ? kg.teachers : kg.alerts;
        const pct = key === 'attendance' ? v : Math.round((v / (val || 1)) * 100);
        return `
          <div style="margin-bottom:.875rem;">
            <div style="display:flex;justify-content:space-between;font-size:.8rem;margin-bottom:.25rem;">
              <span style="color:var(--ko-text)">${koEscape(kg.name)}</span>
              <strong style="color:${meta.accent}">${v}${meta.unit}</strong>
            </div>
            <div class="ko-kg-bar"><div class="ko-kg-bar-fill" style="width:${pct}%;background:${meta.accent}"></div></div>
          </div>`;
      }).join('')}`;

    const panelData = kgs.map(kg => {
      const v = key === 'children' ? kg.children : key === 'attendance' ? kg.attendance : key === 'teachers' ? kg.teachers : kg.alerts;
      return v;
    });
    setTimeout(() => {
      const ctx = document.getElementById('ko-panel-chart');
      if (ctx && window.Chart) {
        new Chart(ctx, {
          type: 'bar',
          data: {
            labels: kgs.map(k => k.name.replace('حضانة ','').substring(0,6)),
            datasets: [{ data: panelData, backgroundColor: meta.accent + 'bb', borderRadius: 6 }]
          },
          options: { responsive:true, maintainAspectRatio:false, plugins:{ legend:{display:false} }, scales:{ x:{display:true,ticks:{font:{size:9}}}, y:{display:true} } }
        });
      }
    }, 50);

    this.#togglePanel(true);
  }

  #openKGPanel(kg) {
    const panelBody  = document.getElementById('ko-panel-body');
    const panelTitle = document.getElementById('ko-panel-title');
    if (!panelBody || !panelTitle) return;
    const lang = window.KINJO_LANG || 'ar';
    const isAr = lang !== 'en';

    panelTitle.textContent = kg.name;
    const attColor = kg.attendance >= 80 ? 'var(--ko-green)' : kg.attendance >= 65 ? 'var(--ko-amber)' : 'var(--ko-red)';

    panelBody.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1.5rem;">
        ${[
          { l: isAr ? 'الأطفال' : 'Children',   v: kg.children,       c: 'var(--ko-blue)'  },
          { l: isAr ? 'الحضور'  : 'Attendance', v: kg.attendance+'%',  c: attColor          },
          { l: isAr ? 'المعلمات': 'Teachers',    v: kg.teachers,       c: 'var(--ko-purple)'},
          { l: isAr ? 'التنبيهات':'Alerts',      v: kg.alerts,         c: 'var(--ko-red)'   },
        ].map(s => `
          <div class="ko-panel-stat" style="background:var(--ko-surface2);padding:.875rem;border-radius:8px;border:1px solid var(--ko-border);">
            <div class="ko-panel-stat-label">${s.l}</div>
            <div class="ko-panel-stat-val" style="font-size:1.5rem;color:${s.c}">${s.v}</div>
          </div>`).join('')}
      </div>
      <div class="ko-panel-stat">
        <div class="ko-panel-stat-label">${isAr ? 'المحافظة' : 'Governorate'}</div>
        <div style="font-size:1rem;font-weight:600;color:var(--ko-text)">${koEscape(kg.gov)}</div>
      </div>
      <div class="ko-panel-stat">
        <div class="ko-panel-stat-label">${isAr ? 'الطاقة الاستيعابية' : 'Capacity'}</div>
        <div style="margin-top:.5rem;">
          <div style="display:flex;justify-content:space-between;font-size:.8rem;margin-bottom:.375rem;">
            <span>${kg.children} / ${kg.capacity}</span>
            <span>${Math.round((kg.children/kg.capacity)*100)}%</span>
          </div>
          <div class="ko-kg-bar" style="height:10px;">
            <div class="ko-kg-bar-fill" style="width:${Math.round((kg.children/kg.capacity)*100)}%;background:var(--ko-teal)"></div>
          </div>
        </div>
      </div>
      <div style="margin-top:1.5rem;display:flex;flex-direction:column;gap:.625rem;">
        <a href="/kindergartens/${encodeURIComponent(kg.id)}" class="ko-action-btn" style="justify-content:center">
          <i class="bi bi-building-fill"></i> ${isAr ? 'عرض الحضانة' : 'View Kindergarten'}
        </a>
        <a href="/attendance/daily?kg=${encodeURIComponent(kg.id)}" class="ko-action-btn" style="justify-content:center">
          <i class="bi bi-calendar-check-fill"></i> ${isAr ? 'سجل الحضور' : 'Attendance Log'}
        </a>
      </div>`;

    this.#togglePanel(true);
  }

  #togglePanel(open) {
    const overlay = document.getElementById('ko-overlay');
    const panel   = document.getElementById('ko-side-panel');
    overlay?.classList.toggle('open', open);
    panel?.classList.toggle('open', open);
    this.#panelOpen = open;
    if (open) document.body.style.overflow = 'hidden';
    else      document.body.style.overflow = '';
  }

  /* ── Customise Panel ──────────────────────────────────── */
  #buildCustomisePanel() {
    const wrap = document.getElementById('ko-customise-wrap');
    if (!wrap) return;
    const lang   = window.KINJO_LANG || 'ar';
    const isAr   = lang !== 'en';
    const hidden = this.#store.get('hiddenKPIs');

    wrap.innerHTML = `
      <div class="ko-customise-panel" id="ko-customise-panel">
        <h3 style="font-size:.875rem;font-weight:700;margin-bottom:1rem;color:var(--ko-text)">
          <i class="bi bi-sliders me-2"></i>${isAr ? 'تخصيص المكونات' : 'Customize Components'}
        </h3>
        ${Object.entries(this.#KPI_META).map(([key, meta]) => `
          <div class="ko-toggle-row">
            <label class="ko-toggle-label" for="ko-toggle-${key}">
              <i class="bi ${meta.icon}" style="color:${meta.accent}"></i>
              ${isAr ? meta.label_ar : meta.label_en}
            </label>
            <label class="ko-toggle">
              <input type="checkbox" id="ko-toggle-${key}" ${hidden.includes(key) ? '' : 'checked'}>
              <span class="ko-toggle-track"></span>
              <span class="ko-toggle-thumb"></span>
            </label>
          </div>`).join('')}
        <div style="margin-top:1rem;display:flex;gap:.5rem;">
          <button class="ko-action-btn" id="ko-reset-layout" style="flex:1;justify-content:center">
            <i class="bi bi-arrow-counterclockwise"></i> ${isAr ? 'إعادة ضبط' : 'Reset'}
          </button>
        </div>
      </div>`;

    Object.keys(this.#KPI_META).forEach(key => {
      document.getElementById(`ko-toggle-${key}`)?.addEventListener('change', e => {
        let hidden = [...this.#store.get('hiddenKPIs')];
        if (e.target.checked) hidden = hidden.filter(h => h !== key);
        else                  hidden.push(key);
        this.#store.set({ hiddenKPIs: hidden });
        document.querySelector(`[data-kpi-key="${key}"]`)?.classList.toggle('ko-hidden', !e.target.checked);
        this.#savePrefs();
      });
    });

    document.getElementById('ko-reset-layout')?.addEventListener('click', () => {
      KoPersist.reset();
      location.reload();
    });
  }

  #toggleCustomise() {
    this.#customiseOpen = !this.#customiseOpen;
    document.getElementById('ko-customise-panel')?.classList.toggle('open', this.#customiseOpen);
    document.getElementById('ko-customise-btn')?.classList.toggle('active', this.#customiseOpen);
  }

  /* ── Global Events ────────────────────────────────────── */
  #bindGlobalEvents() {
    /* Close panel */
    document.getElementById('ko-overlay')?.addEventListener('click', () => this.#togglePanel(false));
    document.getElementById('ko-panel-close')?.addEventListener('click', () => this.#togglePanel(false));
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && this.#panelOpen) this.#togglePanel(false); });

    /* DnD reorder saved */
    document.addEventListener('ko:reorder', e => {
      this.#store.set({ kpiOrder: e.detail.order.filter(Boolean) });
      this.#savePrefs();
    });

  }

  /* ── Realtime Simulation ──────────────────────────────── */
  #startRealtime() {
    this.#rtTimer = setInterval(() => {
      this.#refresh({ silent: true }).catch(error => {
        console.error('[KgOverview] refresh failed', error);
      });
    }, 60000);
  }

  #renderLastUpdated() {
    const el = document.getElementById('ko-last-updated');
    if (!el) return;
    const lang = window.KINJO_LANG || 'ar';
    const isAr = lang !== 'en';
    el.textContent = (isAr ? 'آخر تحديث: ' : 'Updated: ') + new Date().toLocaleTimeString(isAr ? 'ar-JO' : 'en-US');
  }

  /* ── Helpers ──────────────────────────────────────────── */
  #filteredKGs() {
    let kgs = this.#store.get('kgs');
    const gov = this.#store.get('govFilter');
    const kg  = this.#store.get('kgFilter');
    if (gov !== 'all') kgs = kgs.filter(k => k.gov === gov);
    if (kg  !== 'all') kgs = kgs.filter(k => k.name === kg);
    return kgs;
  }

  #onFilterChange() {
    this.#renderActiveView();
    this.#savePrefs();
  }

  async #onPeriodChange() {
    this.#savePrefs();
    try {
      await this.#loadOverviewData();
      this.#updateKPIValues();
      this.#renderActiveView();
      this.#renderAlertItems();
      this.#renderLastUpdated();
    } catch (error) {
      console.error('[KgOverview] period change refetch failed', error);
    }
  }

  async #refresh({ silent = false } = {}) {
    const btn = document.getElementById('ko-refresh-btn');
    const icon = btn?.querySelector('i');
    if (icon) icon.style.animation = 'koShimmer .6s linear infinite';
    try {
      await this.#loadOverviewData();
      this.#updateKPIValues();
      this.#renderActiveView();
      this.#renderAlertItems();
      this.#renderLastUpdated();
    } catch (error) {
      console.error('[KgOverview] refresh failed', error);
      if (!silent) {
        alert(window.KINJO_LANG === 'en' ? 'Failed to refresh kindergarten overview.' : 'تعذر تحديث نظرة الحضانات.');
      }
    } finally {
      setTimeout(() => { if (icon) icon.style.animation = ''; }, 700);
    }
  }

  #today(offsetDays = 0) {
    const d = new Date(); d.setDate(d.getDate() + offsetDays);
    return d.toISOString().split('T')[0];
  }

  #timeAgo(ts, isAr) {
    const secs = Math.round((Date.now() - ts) / 1000);
    if (secs < 60)   return isAr ? 'منذ لحظات' : 'just now';
    if (secs < 3600) return isAr ? `منذ ${Math.round(secs/60)} دقيقة` : `${Math.round(secs/60)}m ago`;
    if (secs < 86400)return isAr ? `منذ ${Math.round(secs/3600)} ساعة` : `${Math.round(secs/3600)}h ago`;
    return isAr ? `منذ ${Math.round(secs/86400)} يوم` : `${Math.round(secs/86400)}d ago`;
  }

  #applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
  }

  #savePrefs() {
    KoPersist.save({
      period:     this.#store.get('period'),
      govFilter:  this.#store.get('govFilter'),
      theme:      this.#store.get('theme'),
      hiddenKPIs: this.#store.get('hiddenKPIs'),
      kpiOrder:   this.#store.get('kpiOrder'),
    });
  }

  #exportCSV() {
    const kgs  = this.#filteredKGs();
    const rows = [['الحضانة','المحافظة','الأطفال','المعلمات','الحضور %','التنبيهات']];
    kgs.forEach(k => rows.push([k.name, k.gov, k.children, k.teachers, k.attendance, k.alerts]));
    const csv  = rows.map(r => r.join(',')).join('\n');
    const blob = new Blob(['﻿' + csv], { type:'text/csv;charset=utf-8;' });
    const url  = URL.createObjectURL(blob);
    const a    = Object.assign(document.createElement('a'), { href:url, download:'kg_overview.csv' });
    a.click(); URL.revokeObjectURL(url);
  }

  destroy() {
    clearInterval(this.#rtTimer);
    this.#charts.destroyAll();
  }
}

/* ════════════════════════════════════════════════════════════
   7. BOOT
   ════════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  if (!window.Chart) {
    console.error('[KgOverview] Chart.js not loaded');
    return;
  }
  window._kgOverview = new KgOverview();
  window._kgOverview.init().catch(error => {
    console.error('[KgOverview] initialisation failed', error);
  });
});
