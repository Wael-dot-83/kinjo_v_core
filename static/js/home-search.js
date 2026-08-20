(function () {
  'use strict';

  const DEBOUNCE_MS = 300;
  const API_BASE = '/api/public/kindergartens/search';
  const LOCATIONS_API = '/api/kindergartens/reference/governorates';
  const RESULTS_LIMIT = 9;

  let debounceTimer = null;

  const inputEl = document.getElementById('kg-search-input');
  const clearBtn = document.getElementById('kg-search-clear');
  const govEl = document.getElementById('kg-filter-governorate');
  const distEl = document.getElementById('kg-filter-district');
  const statusEl = document.getElementById('kg-filter-status');
  const searchBtn = document.getElementById('kg-search-btn');
  const resultsPanel = document.getElementById('kg-search-results');
  const resultsGrid = document.getElementById('kg-results-grid');
  const resultsCountEl = document.getElementById('kg-results-count');
  const emptyState = document.getElementById('kg-results-empty');
  const errorState = document.getElementById('kg-results-error');
  const loadingState = document.getElementById('kg-results-loading');
  const quickPills = document.querySelectorAll('.kg-quick-gov-pill');

  let cachedGovernorates = [];

  function showPanel() {
    if (resultsPanel) {
      resultsPanel.classList.remove('hidden');
    }
  }

  function hideStates() {
    if (resultsGrid) resultsGrid.innerHTML = '';
    if (emptyState) emptyState.classList.add('hidden');
    if (errorState) errorState.classList.add('hidden');
    if (loadingState) loadingState.classList.add('hidden');
  }

  function showLoading() {
    if (resultsGrid) resultsGrid.innerHTML = '';
    if (emptyState) emptyState.classList.add('hidden');
    if (errorState) errorState.classList.add('hidden');
    if (loadingState) loadingState.classList.remove('hidden');
    if (searchBtn) {
      const spinner = searchBtn.querySelector('.kg-btn-spinner');
      if (spinner) spinner.classList.remove('hidden');
    }
  }

  function hideLoading() {
    if (loadingState) loadingState.classList.add('hidden');
    if (searchBtn) {
      const spinner = searchBtn.querySelector('.kg-btn-spinner');
      if (spinner) spinner.classList.add('hidden');
    }
  }

  function badgeClass(status) {
    const s = (status || '').toLowerCase();
    if (s === 'active') return 'card-badge-active';
    if (s === 'frozen') return 'card-badge-frozen';
    return 'card-badge-draft';
  }

  function statusLabel(status, uiLang) {
    const map = {
      active: uiLang === 'en' ? 'Active' : 'نشطة ومعتمدة',
      frozen: uiLang === 'en' ? 'Frozen' : 'مجمدة',
      draft: uiLang === 'en' ? 'Draft' : 'مسودة',
      inactive: uiLang === 'en' ? 'Inactive' : 'غير نشطة',
    };
    return map[(status || '').toLowerCase()] || status;
  }

  function renderCards(items, total) {
    hideStates();
    hideLoading();

    const uiLang = document.documentElement.lang === 'en' ? 'en' : 'ar';

    if (resultsCountEl) {
      if (typeof total === 'number') {
        resultsCountEl.textContent = uiLang === 'en'
          ? `(${total} available)`
          : `(${total} متوفرة)`;
      } else {
        resultsCountEl.textContent = '';
      }
    }

    if (!items || items.length === 0) {
      if (emptyState) emptyState.classList.remove('hidden');
      return;
    }
    if (!resultsGrid) return;

    resultsGrid.innerHTML = items.slice(0, RESULTS_LIMIT).map(function (kg) {
      const name = uiLang === 'en' && kg.name_en ? kg.name_en : kg.name_ar;
      const location = [kg.area, kg.district, kg.governorate].filter(Boolean).join(', ') || (uiLang === 'en' ? 'Jordan' : 'الأردن');
      const current = kg.current_child_count || 0;
      const capacity = kg.total_capacity || 0;
      const percent = capacity > 0 ? Math.min(100, Math.round((current / capacity) * 100)) : 0;

      return '<div class="kinjo-home-search-card p-4 sm:p-5 flex flex-col justify-between border border-outline-variant/30 rounded-xl bg-white shadow-sm hover:shadow-md transition-all">' +
        '<div>' +
          '<div class="flex items-start justify-between gap-3 mb-2">' +
            '<div class="flex-1 min-w-0">' +
              '<h4 class="card-title text-base sm:text-lg font-bold text-primary truncate" title="' + escapeHtml(name) + '">' + escapeHtml(name) + '</h4>' +
              '<p class="card-meta text-xs sm:text-sm text-on-surface-variant flex items-center gap-1 mt-0.5">' +
                '<span class="material-symbols-outlined text-xs text-tertiary" aria-hidden="true">location_on</span>' +
                '<span class="truncate">' + escapeHtml(location) + '</span>' +
              '</p>' +
            '</div>' +
            '<span class="card-badge text-xs px-2.5 py-1 rounded-full font-semibold whitespace-nowrap ' + badgeClass(kg.status) + '">' + escapeHtml(statusLabel(kg.status, uiLang)) + '</span>' +
          '</div>' +
          '<div class="my-3 bg-surface-container-low p-2.5 rounded-lg border border-outline-variant/20">' +
            '<div class="flex justify-between text-xs text-on-surface-variant mb-1 font-medium">' +
              '<span>' + (uiLang === 'en' ? 'Capacity Enrolled' : 'نسبة الاستيعاب') + '</span>' +
              '<span class="font-bold text-primary">' + current + ' / ' + capacity + '</span>' +
            '</div>' +
            '<div class="w-full bg-outline-variant/30 h-1.5 rounded-full overflow-hidden">' +
              '<div class="bg-primary h-full rounded-full transition-all" style="width: ' + percent + '%;"></div>' +
            '</div>' +
          '</div>' +
        '</div>' +
        '<div class="mt-2 pt-2 border-t border-outline-variant/10 flex items-center justify-between">' +
          '<span class="text-xs text-on-surface-variant flex items-center gap-1">' +
            '<span class="material-symbols-outlined text-xs text-tertiary" aria-hidden="true">verified</span>' +
            (uiLang === 'en' ? 'Accredited' : 'مرخصة') +
          '</span>' +
          '<a href="/kindergartens" class="inline-flex items-center gap-1 text-xs sm:text-sm font-bold text-primary hover:text-tertiary transition-colors">' +
            (uiLang === 'en' ? 'View Details' : 'عرض التفاصيل') +
            '<span class="material-symbols-outlined text-xs rtl:rotate-180" aria-hidden="true">arrow_forward</span>' +
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

  function updateClearButton() {
    if (!clearBtn || !inputEl) return;
    if (inputEl.value.trim().length > 0) {
      clearBtn.classList.remove('hidden');
    } else {
      clearBtn.classList.add('hidden');
    }
  }

  async function search() {
    const params = buildQuery();
    const url = API_BASE + '?' + params.toString();
    showPanel();
    showLoading();
    try {
      const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      const items = (data && data.data && data.data.items) || [];
      const total = (data && data.data && typeof data.data.total === 'number') ? data.data.total : items.length;
      renderCards(items, total);
    } catch (err) {
      hideLoading();
      hideStates();
      if (errorState) errorState.classList.remove('hidden');
      console.error('Home search failed:', err);
    }
  }

  function onSearchTrigger() {
    updateClearButton();
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(search, DEBOUNCE_MS);
  }

  function selectGovernorate(govName) {
    if (!govEl) return;
    govEl.value = govName;
    govEl.dispatchEvent(new Event('change'));

    // Highlight active quick pill
    quickPills.forEach(function (pill) {
      const val = pill.getAttribute('data-gov') || '';
      if (val === govName) {
        pill.classList.add('bg-primary', 'text-white', 'border-primary');
        pill.classList.remove('bg-surface', 'text-on-surface', 'border-outline-variant/40');
      } else {
        pill.classList.remove('bg-primary', 'text-white', 'border-primary');
        pill.classList.add('bg-surface', 'text-on-surface', 'border-outline-variant/40');
      }
    });

    search();
  }

  async function loadGovernorates() {
    try {
      const res = await fetch(LOCATIONS_API);
      if (!res.ok) return;
      const data = await res.json();
      cachedGovernorates = (data && data.governorates) || [];
      if (!govEl || cachedGovernorates.length === 0) return;
      const uiLang = document.documentElement.lang === 'en' ? 'en' : 'ar';
      
      // Preserve first option
      govEl.innerHTML = '<option value="">' + (uiLang === 'en' ? 'All Governorates' : 'جميع المحافظات') + '</option>';
      
      cachedGovernorates.forEach(function (gov) {
        const opt = document.createElement('option');
        opt.value = gov.name_ar || gov.name_en || gov.id || gov.key;
        opt.textContent = uiLang === 'en' && gov.name_en ? gov.name_en : (gov.name_ar || gov.name_en);
        govEl.appendChild(opt);
      });

      govEl.addEventListener('change', function () {
        const selected = govEl.value;
        if (distEl) {
          distEl.innerHTML = '<option value="">' + (uiLang === 'en' ? 'All Districts' : 'جميع المناطق / الألوية') + '</option>';
          if (selected) {
            const govObj = cachedGovernorates.find(function (g) {
              return (g.name_ar === selected || g.name_en === selected || g.id === selected || g.key === selected);
            });
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
    if (inputEl) {
      inputEl.addEventListener('input', onSearchTrigger);
      inputEl.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          search();
        }
      });
    }
    if (clearBtn && inputEl) {
      clearBtn.addEventListener('click', function () {
        inputEl.value = '';
        updateClearButton();
        search();
        inputEl.focus();
      });
    }
    if (statusEl) statusEl.addEventListener('change', onSearchTrigger);
    if (distEl) distEl.addEventListener('change', onSearchTrigger);

    quickPills.forEach(function (pill) {
      pill.addEventListener('click', function () {
        const gov = pill.getAttribute('data-gov') || '';
        selectGovernorate(gov);
      });
    });

    loadGovernorates();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
