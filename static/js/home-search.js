(function () {
  'use strict';

  const DEBOUNCE_MS = 300;
  const API_BASE = '/api/public/kindergartens/search';
  const SINGLE_KG_API = '/api/public/kindergartens';
  const LOCATIONS_API = '/api/reference/governorates';
  const RESULTS_LIMIT = 12;

  let debounceTimer = null;
  let userLat = null;
  let userLng = null;
  let lastSearchResults = [];

  const inputEl = document.getElementById('kg-search-input');
  const clearBtn = document.getElementById('kg-search-clear');
  const govEl = document.getElementById('kg-filter-governorate');
  const distEl = document.getElementById('kg-filter-district');
  const geoBtn = document.getElementById('kg-geo-btn');
  const geoBtnText = document.getElementById('kg-geo-btn-text');
  const geoSpinner = document.getElementById('kg-geo-spinner');
  const searchBtn = document.getElementById('kg-search-btn');
  const resultsPanel = document.getElementById('kg-search-results');
  const resultsGrid = document.getElementById('kg-results-grid');
  const resultsCountEl = document.getElementById('kg-results-count');
  const emptyState = document.getElementById('kg-results-empty');
  const errorState = document.getElementById('kg-results-error');
  const loadingState = document.getElementById('kg-results-loading');
  const quickPills = document.querySelectorAll('.kg-quick-gov-pill');

  // Modal elements
  const modalEl = document.getElementById('kg-details-modal');
  const modalCloseBtn = document.getElementById('modal-close-btn');
  const modalCloseFooterBtn = document.getElementById('modal-close-footer-btn');
  const modalKgName = document.getElementById('modal-kg-name');
  const modalKgLocation = document.getElementById('modal-kg-location');
  const modalKgGovDist = document.getElementById('modal-kg-gov-dist');
  const modalKgPhone = document.getElementById('modal-kg-phone');
  const modalKgPhoneText = document.getElementById('modal-kg-phone-text');
  const modalKgEmail = document.getElementById('modal-kg-email');
  const modalKgAddress = document.getElementById('modal-kg-address');
  const modalKgCapacityText = document.getElementById('modal-kg-capacity-text');
  const modalKgCapacityBar = document.getElementById('modal-kg-capacity-bar');
  const modalKgMapsWrap = document.getElementById('modal-kg-maps-wrap');
  const modalKgMapsBtn = document.getElementById('modal-kg-maps-btn');
  const modalKgCallBtn = document.getElementById('modal-kg-call-btn');

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

  function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function renderCards(items, total) {
    hideStates();
    hideLoading();

    lastSearchResults = items || [];
    const uiLang = document.documentElement.lang === 'en' ? 'en' : 'ar';

    if (resultsCountEl) {
      if (typeof total === 'number') {
        resultsCountEl.textContent = uiLang === 'en'
          ? `(${total} available)`
          : `(${total} متوفرة ومطابقة)`;
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
      const location = [kg.area, kg.district, kg.governorate].filter(Boolean).join('، ') || (uiLang === 'en' ? 'Jordan' : 'المملكة الأردنية الهاشمية');
      const current = kg.current_child_count || 0;
      const capacity = kg.total_capacity || 0;
      const percent = capacity > 0 ? Math.min(100, Math.round((current / capacity) * 100)) : 0;
      const distanceBadge = (typeof kg.distance_km === 'number')
        ? '<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-tertiary/15 text-primary border border-tertiary/30">' +
            '<span class="material-symbols-outlined text-xs text-tertiary">near_me</span>' +
            kg.distance_km + ' ' + (uiLang === 'en' ? 'km away' : 'كم') +
          '</span>'
        : '';

      return '<div class="kinjo-home-search-card p-4 sm:p-5 flex flex-col justify-between border border-outline-variant/30 rounded-2xl bg-white shadow-sm hover:shadow-lg hover:border-primary/40 transition-all cursor-pointer group" onclick="window.openKgDetailsModal(' + kg.id + ')">' +
        '<div>' +
          '<div class="flex items-start justify-between gap-3 mb-2">' +
            '<div class="flex-1 min-w-0">' +
              '<h4 class="card-title text-base sm:text-lg font-bold text-primary truncate group-hover:text-primary-container transition-colors" title="' + escapeHtml(name) + '">' + escapeHtml(name) + '</h4>' +
              '<p class="card-meta text-xs sm:text-sm text-on-surface-variant flex items-center gap-1 mt-0.5">' +
                '<span class="material-symbols-outlined text-xs text-tertiary" aria-hidden="true">location_on</span>' +
                '<span class="truncate">' + escapeHtml(location) + '</span>' +
              '</p>' +
            '</div>' +
            '<div class="flex flex-col items-end gap-1 flex-shrink-0">' +
              '<span class="card-badge text-[11px] px-2.5 py-1 rounded-full font-bold whitespace-nowrap bg-primary/10 text-primary border border-primary/20">' +
                (uiLang === 'en' ? 'Active &amp; Licensed' : 'نشطة ومعتمدة') +
              '</span>' +
              distanceBadge +
            '</div>' +
          '</div>' +
          '<div class="my-3 bg-surface-container-low p-3 rounded-xl border border-outline-variant/20">' +
            '<div class="flex justify-between text-xs text-on-surface-variant mb-1.5 font-medium">' +
              '<span>' + (uiLang === 'en' ? 'Capacity / Enrolled' : 'نسبة الاستيعاب المعتمدة') + '</span>' +
              '<span class="font-bold text-primary">' + (capacity > 0 ? (current + ' / ' + capacity) : (uiLang === 'en' ? 'Available' : 'متوفرة')) + '</span>' +
            '</div>' +
            '<div class="w-full bg-outline-variant/30 h-1.5 rounded-full overflow-hidden">' +
              '<div class="bg-primary h-full rounded-full transition-all" style="width: ' + percent + '%;"></div>' +
            '</div>' +
          '</div>' +
        '</div>' +
        '<div class="mt-2 pt-3 border-t border-outline-variant/15 flex items-center justify-between">' +
          '<span class="text-xs text-on-surface-variant flex items-center gap-1 font-medium">' +
            '<span class="material-symbols-outlined text-sm text-tertiary" aria-hidden="true">verified</span>' +
            (uiLang === 'en' ? 'Verified Registry' : 'سجل رسمي معتمد') +
          '</span>' +
          '<button type="button" onclick="event.stopPropagation(); window.openKgDetailsModal(' + kg.id + ')" class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary/5 hover:bg-primary text-primary hover:text-white text-xs font-bold transition-all shadow-sm">' +
            (uiLang === 'en' ? 'View Details' : 'عرض التفاصيل') +
            '<span class="material-symbols-outlined text-xs rtl:rotate-180" aria-hidden="true">arrow_forward</span>' +
          '</button>' +
        '</div>' +
      '</div>';
    }).join('');
  }

  function buildQuery() {
    const params = new URLSearchParams();
    const q = inputEl ? inputEl.value.trim() : '';
    if (q) params.set('q', q);
    const gov = govEl ? govEl.value.trim() : '';
    if (gov) params.set('governorate', gov);
    const dist = distEl ? distEl.value.trim() : '';
    if (dist) params.set('district', dist);
    if (userLat !== null && userLng !== null) {
      params.set('lat', String(userLat));
      params.set('lng', String(userLng));
    }
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
    const allPills = document.querySelectorAll('.kg-quick-gov-pill');
    allPills.forEach(function (pill) {
      const val = pill.getAttribute('data-gov') || '';
      if (val === govName) {
        pill.classList.add('bg-primary', 'text-white', 'border-primary');
        pill.classList.remove('bg-surface', 'text-on-surface', 'border-outline-variant/40');
      } else {
        pill.classList.remove('bg-primary', 'text-white', 'border-primary');
        pill.classList.add('bg-surface', 'text-on-surface', 'border-outline-variant/40');
      }
    });

    const searchSection = document.getElementById('kg-search-section') || inputEl;
    if (searchSection) {
      searchSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    search();
  }

  window.selectGovernorate = selectGovernorate;

  // Geolocation handler (Find nearest using Phone/Browser GPS)
  function handleGeolocation() {
    const uiLang = document.documentElement.lang === 'en' ? 'en' : 'ar';
    if (!navigator.geolocation) {
      alert(uiLang === 'en' ? 'Geolocation is not supported by your browser.' : 'خدمة تحديد الموقع الجغرافي غير مدعومة في متصفحك.');
      return;
    }

    if (geoSpinner) geoSpinner.classList.remove('hidden');
    if (geoBtnText) geoBtnText.textContent = uiLang === 'en' ? 'Locating...' : 'جارٍ تحديد موقعك...';

    navigator.geolocation.getCurrentPosition(
      function (pos) {
        userLat = pos.coords.latitude;
        userLng = pos.coords.longitude;
        if (geoSpinner) geoSpinner.classList.add('hidden');
        if (geoBtnText) geoBtnText.textContent = uiLang === 'en' ? 'Nearest to Me (Active)' : 'أقرب حضانة لموقعي (مفعل)';
        if (geoBtn) {
          geoBtn.classList.add('bg-primary', 'text-white', 'border-primary');
          geoBtn.classList.remove('bg-white', 'text-primary');
        }
        search();
      },
      function (err) {
        if (geoSpinner) geoSpinner.classList.add('hidden');
        if (geoBtnText) geoBtnText.textContent = uiLang === 'en' ? 'Nearest to Me (GPS)' : 'أقرب حضانة لموقعي (GPS)';
        console.warn('Geolocation error:', err);
        alert(uiLang === 'en' ? 'Unable to retrieve your location. Please check browser permissions.' : 'تعذر تحديد موقعك. يرجى تفعيل إذن الوصول للموقع في المتصفح أو الهاتف.');
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
    );
  }

  // Public Kindergarten Details Modal Logic
  async function openKgDetailsModal(kgId) {
    if (!modalEl) return;
    const uiLang = document.documentElement.lang === 'en' ? 'en' : 'ar';

    // Check cached item first
    let kg = lastSearchResults.find(function (k) { return k.id === kgId; });

    if (!kg) {
      try {
        const res = await fetch(SINGLE_KG_API + '/' + kgId);
        if (res.ok) {
          const resData = await res.json();
          kg = resData && resData.data;
        }
      } catch (e) {
        console.warn('Failed fetching kg details:', e);
      }
    }

    if (!kg) return;

    const name = (uiLang === 'en' && kg.name_en) ? kg.name_en : (kg.name_ar || kg.name_en || 'Kindergarten');
    const location = [kg.area, kg.district, kg.governorate].filter(Boolean).join('، ') || (uiLang === 'en' ? 'Jordan' : 'المملكة الأردنية الهاشمية');
    const govDist = [kg.governorate, kg.district].filter(Boolean).join(' - ') || (uiLang === 'en' ? 'Jordan' : 'الأردن');
    const phone = kg.contact_phone || 'غير متوفر';
    const email = kg.contact_email || (uiLang === 'en' ? 'Not specified' : 'غير محدد');
    const address = kg.address_line || location;
    const current = kg.current_child_count || 0;
    const capacity = kg.total_capacity || 0;
    const percent = capacity > 0 ? Math.min(100, Math.round((current / capacity) * 100)) : 0;

    if (modalKgName) modalKgName.textContent = name;
    if (modalKgLocation) modalKgLocation.innerHTML = '<span class="material-symbols-outlined text-xs text-tertiary">location_on</span> ' + escapeHtml(location);
    if (modalKgGovDist) modalKgGovDist.textContent = govDist;
    if (modalKgPhoneText) modalKgPhoneText.textContent = phone;
    if (modalKgPhone) modalKgPhone.href = phone !== 'غير متوفر' ? ('tel:' + phone.replace(/\s+/g, '')) : '#';
    if (modalKgCallBtn) {
      modalKgCallBtn.href = phone !== 'غير متوفر' ? ('tel:' + phone.replace(/\s+/g, '')) : '#';
      if (phone === 'غير متوفر') modalKgCallBtn.classList.add('opacity-50', 'pointer-events-none');
      else modalKgCallBtn.classList.remove('opacity-50', 'pointer-events-none');
    }
    if (modalKgEmail) modalKgEmail.textContent = email;
    if (modalKgAddress) modalKgAddress.textContent = address;
    if (modalKgCapacityText) {
      modalKgCapacityText.textContent = capacity > 0
        ? (current + ' / ' + capacity + ' ' + (uiLang === 'en' ? 'Enrolled' : 'طفل مسجل'))
        : (uiLang === 'en' ? 'Standard Accreditation Capacity' : 'طاقة استيعابية معتمدة رسمياً');
    }
    if (modalKgCapacityBar) modalKgCapacityBar.style.width = percent + '%';

    // Google Maps integration
    if (modalKgMapsWrap && modalKgMapsBtn) {
      if (kg.latitude && kg.longitude) {
        modalKgMapsBtn.href = 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(kg.latitude + ',' + kg.longitude);
        modalKgMapsWrap.classList.remove('hidden');
      } else if (address && !address.includes('لا يوجد')) {
        modalKgMapsBtn.href = 'https://www.google.com/maps/search/?api=1&query=' + encodeURIComponent(name + ' ' + address);
        modalKgMapsWrap.classList.remove('hidden');
      } else {
        modalKgMapsWrap.classList.add('hidden');
      }
    }

    modalEl.classList.remove('hidden');
    document.body.classList.add('overflow-hidden');
  }

  function closeKgDetailsModal() {
    if (!modalEl) return;
    modalEl.classList.add('hidden');
    document.body.classList.remove('overflow-hidden');
  }

  window.openKgDetailsModal = openKgDetailsModal;
  window.closeKgDetailsModal = closeKgDetailsModal;

  async function loadGovernorates() {
    try {
      const res = await fetch(LOCATIONS_API);
      if (!res.ok) return;
      const data = await res.json();
      cachedGovernorates = (data && data.governorates) || [];
      if (!govEl || cachedGovernorates.length === 0) return;
      const uiLang = document.documentElement.lang === 'en' ? 'en' : 'ar';
      
      // Preserve first option
      govEl.innerHTML = '<option value="">' + (uiLang === 'en' ? 'All Governorates (12)' : 'جميع المحافظات (12)') + '</option>';
      
      cachedGovernorates.forEach(function (gov) {
        const opt = document.createElement('option');
        opt.value = gov.name_ar || gov.name_en || gov.id || gov.key;
        opt.textContent = uiLang === 'en' && gov.name_en ? gov.name_en : (gov.name_ar || gov.name_en);
        govEl.appendChild(opt);
      });

      // Governorate change cascades to District dropdown
      govEl.addEventListener('change', function () {
        const selected = govEl.value;
        if (distEl) {
          if (!selected) {
            distEl.innerHTML = '<option value="">' + (uiLang === 'en' ? 'Select Governorate First' : 'اختر المحافظة أولاً لعرض الألوية') + '</option>';
          } else {
            distEl.innerHTML = '<option value="">' + (uiLang === 'en' ? 'All Districts / Regions' : 'جميع المناطق / الألوية') + '</option>';
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
    if (geoBtn) geoBtn.addEventListener('click', handleGeolocation);
    if (inputEl) {
      inputEl.addEventListener('input', onSearchTrigger);
      inputEl.addEventListener('keydown', function (e) {
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
    if (distEl) distEl.addEventListener('change', onSearchTrigger);

    quickPills.forEach(function (pill) {
      pill.addEventListener('click', function () {
        const gov = pill.getAttribute('data-gov') || '';
        selectGovernorate(gov);
      });
    });

    if (modalCloseBtn) modalCloseBtn.addEventListener('click', closeKgDetailsModal);
    if (modalCloseFooterBtn) modalCloseFooterBtn.addEventListener('click', closeKgDetailsModal);
    if (modalEl) {
      modalEl.addEventListener('click', function (e) {
        if (e.target === modalEl) closeKgDetailsModal();
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !modalEl.classList.contains('hidden')) {
          closeKgDetailsModal();
        }
      });
    }

    loadGovernorates();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

