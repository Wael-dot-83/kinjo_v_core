(function () {
  'use strict';

  const DEBOUNCE_MS = 300;
  const API_BASE = '/api/public/kindergartens/search';
  const LOCATIONS_API = '/api/kindergartens/reference/governorates';
  const RESULTS_LIMIT = 6;

  let debounceTimer = null;

  const inputEl = document.getElementById('kg-search-input');
  const govEl = document.getElementById('kg-filter-governorate');
  const distEl = document.getElementById('kg-filter-district');
  const statusEl = document.getElementById('kg-filter-status');
  const searchBtn = document.getElementById('kg-search-btn');
  const resultsPanel = document.getElementById('kg-search-results');
  const resultsGrid = document.getElementById('kg-results-grid');
  const emptyState = document.getElementById('kg-results-empty');
  const errorState = document.getElementById('kg-results-error');

  function setStatus(key, text) {
    const el = document.getElementById(key);
    if (el) el.textContent = text;
  }

  function showPanel() {
    if (resultsPanel) resultsPanel.classList.remove('hidden');
  }

  function hideStates() {
    if (resultsGrid) resultsGrid.innerHTML = '';
    if (emptyState) emptyState.classList.add('hidden');
    if (errorState) errorState.classList.add('hidden');
  }

  function badgeClass(status) {
    const s = (status || '').toLowerCase();
    if (s === 'active') return 'card-badge-active';
    if (s === 'frozen') return 'card-badge-frozen';
    return 'card-badge-draft';
  }

  function statusLabel(status, uiLang) {
    const map = {
      active: uiLang === 'en' ? 'Active' : 'نشطة',
      frozen: uiLang === 'en' ? 'Frozen' : 'مجمدة',
      draft: uiLang === 'en' ? 'Draft' : 'مسودة',
      inactive: uiLang === 'en' ? 'Inactive' : 'غير نشطة',
    };
    return map[(status || '').toLowerCase()] || status;
  }

  function renderCards(items) {
    hideStates();
    if (!items || items.length === 0) {
      if (emptyState) emptyState.classList.remove('hidden');
      return;
    }
    if (!resultsGrid) return;
    const uiLang = document.documentElement.lang === 'en' ? 'en' : 'ar';
    resultsGrid.innerHTML = items.slice(0, RESULTS_LIMIT).map(function (kg) {
      const name = uiLang === 'en' && kg.name_en ? kg.name_en : kg.name_ar;
      const location = [kg.area, kg.district, kg.governorate].filter(Boolean).join(', ');
      return '<div class="kinjo-home-search-card p-4">' +
        '<div class="flex items-start justify-between gap-3">' +
          '<div class="flex-1 min-w-0">' +
            '<p class="card-title truncate">' + escapeHtml(name) + '</p>' +
            '<p class="card-meta">' + escapeHtml(location) + '</p>' +
          '</div>' +
          '<span class="card-badge ' + badgeClass(kg.status) + '">' + escapeHtml(statusLabel(kg.status, uiLang)) + '</span>' +
        '</div>' +
        '<div class="mt-3 flex items-center gap-4 text-sm text-on-surface-variant">' +
          '<span class="flex items-center gap-1">' +
            '<span class="material-symbols-outlined text-base" aria-hidden="true">groups</span>' +
            '<span>' + (kg.current_child_count || 0) + ' / ' + (kg.total_capacity || 0) + '</span>' +
          '</span>' +
          '<a href="/kindergartens" class="font-label-bold text-label-bold text-primary hover:text-tertiary transition-colors">' +
            (uiLang === 'en' ? 'Details' : 'التفاصيل') +
          '</a>' +
        '</div>' +
      '</div>';
    }).join('');
  }

  function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function buildQuery() {
    const params = new URLSearchParams();
    const q = inputEl ? inputEl.value.trim() : '';
    if (q) params.set('q', q);
    const gov = govEl ? govEl.value.trim() : '';
    if (gov) params.set('governorate', gov);
    const dist = distEl ? distEl.value.trim() : '';
    if (dist) params.set('district', dist);
    const status = statusEl ? statusEl.value.trim() : '';
    if (status) params.set('status', status);
    params.set('limit', String(RESULTS_LIMIT));
    params.set('skip', '0');
    return params;
  }

  async function search() {
    const params = buildQuery();
    const url = API_BASE + '?' + params.toString();
    try {
      const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      const items = (data && data.data && data.data.items) || [];
      showPanel();
      renderCards(items);
    } catch (err) {
      showPanel();
      hideStates();
      if (errorState) errorState.classList.remove('hidden');
      console.error('Home search failed:', err);
    }
  }

  function onSearchTrigger() {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(search, DEBOUNCE_MS);
  }

  async function loadGovernorates() {
    try {
      const res = await fetch(LOCATIONS_API);
      if (!res.ok) return;
      const data = await res.json();
      const governorates = (data && data.governorates) || [];
      if (!govEl || governorates.length === 0) return;
      const uiLang = document.documentElement.lang === 'en' ? 'en' : 'ar';
      governorates.forEach(function (gov) {
        const opt = document.createElement('option');
        opt.value = gov.id || gov.key || gov.name_ar;
        opt.textContent = uiLang === 'en' && gov.name_en ? gov.name_en : gov.name_ar;
        govEl.appendChild(opt);
      });
      govEl.addEventListener('change', function () {
        const selected = govEl.value;
        if (distEl) {
          distEl.innerHTML = '<option value="">' + (uiLang === 'en' ? 'All Districts' : 'جميع المناطق') + '</option>';
          if (selected) {
            const govObj = governorates.find(function (g) { return (g.id || g.key || g.name_ar) === selected; });
            if (govObj && govObj.cities) {
              govObj.cities.forEach(function (city) {
                const opt = document.createElement('option');
                opt.value = city;
                opt.textContent = city;
                distEl.appendChild(opt);
              });
            }
          }
        }
        onSearchTrigger();
      });
    } catch (err) {
      console.error('Failed to load governorates:', err);
    }
  }

  function init() {
    if (searchBtn) searchBtn.addEventListener('click', search);
    if (inputEl) inputEl.addEventListener('input', onSearchTrigger);
    if (statusEl) statusEl.addEventListener('change', onSearchTrigger);
    if (distEl) distEl.addEventListener('change', onSearchTrigger);
    loadGovernorates();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
