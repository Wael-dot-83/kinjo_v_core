(function () {
  'use strict';

  const DEBOUNCE_MS = 400;
  const RESULTS_LIMIT = 12;
  const API_BASE = '/api/public/kindergartens/search';
  const SINGLE_KG_API = '/api/public/kindergartens';
  const LOCATIONS_API = '/api/reference/governorates';
  const EARTH_RADIUS_KM = 6371;

  const inputEl = document.getElementById('kg-search-input');
  const clearBtn = document.getElementById('kg-search-clear');
  const govEl = document.getElementById('kg-filter-governorate');
  const distEl = document.getElementById('kg-filter-district');
  const geoBtn = document.getElementById('kg-geo-btn');
  const geoBtnText = document.getElementById('kg-geo-btn-text');
  const geoSpinner = document.getElementById('kg-geo-spinner');
  const geoStatus = document.getElementById('kg-geo-status');
  const searchBtn = document.getElementById('kg-search-btn');
  const resultsPanel = document.getElementById('kg-search-results');
  const resultsGrid = document.getElementById('kg-results-grid');
  const resultsCountEl = document.getElementById('kg-results-count');
  const resultsContextEl = document.getElementById('kg-results-context');
  const resultsResetBtn = document.getElementById('kg-results-reset');
  const resultsEmptyResetBtn = document.getElementById('kg-results-empty-reset');
  const resultsRetryBtn = document.getElementById('kg-results-retry');
  const emptyState = document.getElementById('kg-results-empty');
  const errorState = document.getElementById('kg-results-error');
  const loadingState = document.getElementById('kg-results-loading');
  const quickPills = document.querySelectorAll('.kg-quick-gov-pill');

  const modalEl = document.getElementById('kg-details-modal');
  const modalPanel = modalEl ? modalEl.querySelector('[data-modal-panel]') : null;
  const modalCloseBtn = document.getElementById('modal-close-btn');
  const modalCloseFooterBtn = document.getElementById('modal-close-footer-btn');
  const modalKgName = document.getElementById('modal-kg-name');
  const modalKgNameEn = document.getElementById('modal-kg-name-en');
  const modalKgLocation = document.getElementById('modal-kg-location');
  const modalKgGovDist = document.getElementById('modal-kg-gov-dist');
  const modalKgArea = document.getElementById('modal-kg-area');
  const modalKgPhone = document.getElementById('modal-kg-phone');
  const modalKgPhoneText = document.getElementById('modal-kg-phone-text');
  const modalKgEmail = document.getElementById('modal-kg-email');
  const modalKgEmailLink = document.getElementById('modal-kg-email-link');
  const modalKgAddress = document.getElementById('modal-kg-address');
  const modalKgHours = document.getElementById('modal-kg-hours');
  const modalKgDays = document.getElementById('modal-kg-days');
  const modalKgDistance = document.getElementById('modal-kg-distance');
  const modalKgCapacityText = document.getElementById('modal-kg-capacity-text');
  const modalKgCapacityBar = document.getElementById('modal-kg-capacity-bar');
  const modalKgMapsWrap = document.getElementById('modal-kg-maps-wrap');
  const modalKgMapsBtn = document.getElementById('modal-kg-maps-btn');
  const modalKgCallBtn = document.getElementById('modal-kg-call-btn');
  const modalStatus = document.getElementById('modal-kg-status');

  let debounceTimer = null;
  let requestController = null;
  let lastQuerySignature = '';
  let cachedGovernorates = [];
  let userPosition = null;
  let lastFocusedTrigger = null;

  function isEnglish() { return document.documentElement.lang === 'en'; }
  function t(en, ar) { return isEnglish() ? en : ar; }
  function setHidden(element, hidden) { if (element) element.classList.toggle('hidden', hidden); }
  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function formatDistance(km) { return Number(km).toFixed(1) + ' ' + t('km', 'ÙƒÙ…'); }
  function haversineDistanceKm(lat1, lon1, lat2, lon2) {
    const radians = function (value) { return value * Math.PI / 180; };
    const dLat = radians(lat2 - lat1);
    const dLon = radians(lon2 - lon1);
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(radians(lat1)) * Math.cos(radians(lat2)) * Math.sin(dLon / 2) ** 2;
    return EARTH_RADIUS_KM * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(Math.max(0, 1 - a)));
  }
  function showPanel() { setHidden(resultsPanel, false); }
  function setResultsBusy(busy) { if (resultsPanel) resultsPanel.setAttribute('aria-busy', busy ? 'true' : 'false'); }
  function hideStates() {
    if (resultsGrid) resultsGrid.innerHTML = '';
    setHidden(emptyState, true); setHidden(errorState, true); setHidden(loadingState, true);
  }
  function showLoading() {
    if (resultsGrid) resultsGrid.innerHTML = '';
    setHidden(emptyState, true); setHidden(errorState, true); setHidden(loadingState, false);
    setResultsBusy(true);
    setHidden(searchBtn && searchBtn.querySelector('.kg-btn-spinner'), false);
    if (searchBtn) searchBtn.setAttribute('aria-busy', 'true');
  }
  function hideLoading() {
    setHidden(loadingState, true); setHidden(searchBtn && searchBtn.querySelector('.kg-btn-spinner'), true);
    setResultsBusy(false);
    if (searchBtn) searchBtn.removeAttribute('aria-busy');
  }
  function buildQuery() {
    const params = new URLSearchParams();
    const q = inputEl ? inputEl.value.trim() : '';
    const governorate = govEl ? govEl.value.trim() : '';
    const district = distEl ? distEl.value.trim() : '';
    if (q) params.set('q', q);
    if (governorate) params.set('governorate', governorate);
    if (district) params.set('district', district);
    if (userPosition) { params.set('lat', String(userPosition.lat)); params.set('lng', String(userPosition.lng)); }
    params.set('limit', String(RESULTS_LIMIT)); params.set('skip', '0');
    return params;
  }
  function syncUrl() {
    const params = buildQuery(); params.delete('lat'); params.delete('lng');
    const query = params.toString();
    window.history.replaceState(null, '', window.location.pathname + (query ? '?' + query : '') + window.location.hash);
  }
  function updateClearButton() { if (clearBtn && inputEl) setHidden(clearBtn, !inputEl.value.trim()); }
  function resetSearch() {
    if (inputEl) inputEl.value = '';
    if (govEl) govEl.value = '';
    if (distEl) distEl.value = '';
    userPosition = null;
    if (geoBtn) geoBtn.classList.remove('kg-geo-active');
    if (geoBtnText) geoBtnText.textContent = t('Find nurseries near me (GPS)', 'Ø£Ù‚Ø±Ø¨ Ø­Ø¶Ø§Ù†Ø© Ù„Ù…ÙˆÙ‚Ø¹ÙŠ (GPS)');
    setGeoStatus('');
    setDistrictOptions('');
    updateClearButton();
    search(true);
    if (inputEl) inputEl.focus();
  }
  function setModalStatus(message, isError) {
    if (!modalStatus) return;
    modalStatus.textContent = message || '';
    modalStatus.classList.toggle('is-error', Boolean(isError));
    setHidden(modalStatus, !message);
  }

    function renderCards(items, total) {
    hideStates(); hideLoading();
    if (resultsCountEl) resultsCountEl.textContent = typeof total === 'number' ? total + ' ' + t('available', 'متاحة') : '';
    if (resultsContextEl) resultsContextEl.textContent = items && items.length
      ? t('Select a kindergarten to view its public details without signing in.', 'اختر حضانة لعرض تفاصيلها العامة دون تسجيل الدخول.')
      : t('Try a wider search or clear the filters to see more kindergartens.', 'جرّب بحثاً أوسع أو امسح التصفية لرؤية حضانات أكثر.');
    if (!items || !items.length) { setHidden(emptyState, false); return; }
    if (!resultsGrid) return;
    resultsGrid.innerHTML = items.slice(0, RESULTS_LIMIT).map(function (kg) {
      const name = isEnglish() && kg.name_en ? kg.name_en : (kg.name_ar || kg.name_en || t('Nursery', 'حضانة'));
      const location = [kg.area, kg.district, kg.governorate].filter(Boolean).join('، ');
      const address = kg.address_line || location || t('Jordan', 'الأردن');
      const distance = typeof kg.distance_km === 'number' ? '<span class="kg-distance-badge"><span class="material-symbols-outlined" aria-hidden="true">near_me</span>' + escapeHtml(formatDistance(kg.distance_km)) + '</span>' : '';
      // Pin button for direct Google Maps link
      const hasCoords = Number.isFinite(Number(kg.latitude)) && Number.isFinite(Number(kg.longitude));
      const pinBtn = hasCoords
        ? '<button type="button" class="kg-card-pin-btn" data-lat="' + escapeHtml(String(kg.latitude)) + '" data-lng="' + escapeHtml(String(kg.longitude)) + '" data-name="' + escapeHtml(name) + '" aria-label="' + escapeHtml(t('Open ' + name + ' in Google Maps', 'فتح ' + name + ' في خرائط Google')) + '"><span class="material-symbols-outlined" aria-hidden="true">location_on</span></button>'
        : '';
      return '<article class="kinjo-home-search-card" tabindex="0" role="button" data-kg-id="' + escapeHtml(kg.id) + '" aria-label="' + escapeHtml(t('View details for ' + name, 'عرض تفاصيل ' + name)) + '">' +
        '<div class="kg-card-heading"><div class="kg-card-title-wrap"><h3 class="card-title">' + escapeHtml(name) + '</h3><p class="card-meta"><span class="material-symbols-outlined" aria-hidden="true">location_on</span><span>' + escapeHtml(location || address) + '</span></p></div><div class="kg-card-badges"><span class="kg-license-badge"><span class="material-symbols-outlined" aria-hidden="true">location_city</span>' + escapeHtml(t('Active listing', 'سجل نشط')) + '</span>' + distance + '</div></div>' +
        '<p class="kg-card-address">' + escapeHtml(address) + '</p><div class="kg-card-footer"><span class="kg-card-source"><span class="material-symbols-outlined" aria-hidden="true">account_balance</span>' + escapeHtml(t('Public registry', 'السجل العام')) + '</span><span class="kg-card-details"><span>' + escapeHtml(t('View public details', 'عرض التفاصيل العامة')) + '</span><span class="material-symbols-outlined" aria-hidden="true">arrow_forward</span></span>' + pinBtn + '</div></article>';
    }).join('');
  }


async function search(force) {
    const params = buildQuery(); const signature = params.toString();
    if (!force && signature === lastQuerySignature) return;
    lastQuerySignature = signature; syncUrl(); showPanel(); showLoading();
    if (requestController) requestController.abort();
    requestController = new AbortController();
    try {
      const response = await fetch(API_BASE + '?' + signature, { headers: { Accept: 'application/json' }, signal: requestController.signal });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const payload = await response.json(); const data = payload && payload.data ? payload.data : {};
      renderCards(data.items || [], typeof data.total === 'number' ? data.total : 0);
    } catch (error) {
      if (error.name === 'AbortError') return;
      hideLoading(); hideStates(); setHidden(errorState, false);
      if (resultsContextEl) resultsContextEl.textContent = t('Your filters are saved. Try the search again when the connection is back.', 'ØªÙ… Ø­ÙØ¸ Ø®ÙŠØ§Ø±Ø§Øª Ø§Ù„Ø¨Ø­Ø«. Ø­Ø§ÙˆÙ„ Ù…Ø±Ø© Ø£Ø®Ø±Ù‰ Ø¹Ù†Ø¯ Ø¹ÙˆØ¯Ø© Ø§Ù„Ø§ØªØµØ§Ù„.');
      console.error('Home search failed:', error);
    }
  }
  function debouncedSearch() {
    updateClearButton(); if (debounceTimer) window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(function () { search(false); }, DEBOUNCE_MS);
  }
  function setGeoStatus(message, isError) {
    if (!geoStatus) return;
    geoStatus.textContent = message; geoStatus.classList.toggle('kg-search-status-error', Boolean(isError)); setHidden(geoStatus, !message);
  }
  function handleGeolocation() {
    if (!navigator.geolocation) { setGeoStatus(t('Location is not supported by this browser. You can search by neighborhood or area instead.', 'Ø§Ù„Ù…ØªØµÙØ­ Ù„Ø§ ÙŠØ¯Ø¹Ù… ØªØ­Ø¯ÙŠØ¯ Ø§Ù„Ù…ÙˆÙ‚Ø¹. ÙŠÙ…ÙƒÙ†Ùƒ Ø§Ù„Ø¨Ø­Ø« Ø¨Ø§Ø³Ù… Ø§Ù„Ø­ÙŠ Ø£Ùˆ Ø§Ù„Ù…Ù†Ø·Ù‚Ø©.'), true); return; }
    if (geoBtn) { geoBtn.disabled = true; geoBtn.setAttribute('aria-busy', 'true'); }
    setHidden(geoSpinner, false); setGeoStatus(t('Requesting your locationâ€¦', 'Ø¬Ø§Ø±Ù Ø·Ù„Ø¨ Ù…ÙˆÙ‚Ø¹Ùƒâ€¦')); if (geoBtnText) geoBtnText.textContent = t('Locatingâ€¦', 'Ø¬Ø§Ø±Ù ØªØ­Ø¯ÙŠØ¯ Ø§Ù„Ù…ÙˆÙ‚Ø¹â€¦');
    navigator.geolocation.getCurrentPosition(function (position) {
      userPosition = { lat: position.coords.latitude, lng: position.coords.longitude }; setHidden(geoSpinner, true);
      if (geoBtn) { geoBtn.disabled = false; geoBtn.removeAttribute('aria-busy'); geoBtn.classList.add('kg-geo-active'); }
      if (geoBtnText) geoBtnText.textContent = t('Near me (GPS active)', 'Ø§Ù„Ø£Ù‚Ø±Ø¨ Ø¥Ù„Ù‰ Ù…ÙˆÙ‚Ø¹ÙŠ (GPS Ù…ÙØ¹Ù‘Ù„)');
      setGeoStatus(t('Results are sorted from nearest to farthest.', 'ØªÙ… ØªØ±ØªÙŠØ¨ Ø§Ù„Ù†ØªØ§Ø¦Ø¬ Ù…Ù† Ø§Ù„Ø£Ù‚Ø±Ø¨ Ø¥Ù„Ù‰ Ø§Ù„Ø£Ø¨Ø¹Ø¯.')); search(true);
    }, function (error) {
      userPosition = null; setHidden(geoSpinner, true);
      if (geoBtn) { geoBtn.disabled = false; geoBtn.removeAttribute('aria-busy'); geoBtn.classList.remove('kg-geo-active'); }
      if (geoBtnText) geoBtnText.textContent = t('Find nurseries near me (GPS)', 'Ø£Ù‚Ø±Ø¨ Ø­Ø¶Ø§Ù†Ø© Ù„Ù…ÙˆÙ‚Ø¹ÙŠ (GPS)');
      const message = error.code === 1 ? t('Location permission was denied. You can search by neighborhood or area instead.', 'ØªÙ… Ø±ÙØ¶ Ø¥Ø°Ù† Ø§Ù„ÙˆØµÙˆÙ„ Ø¥Ù„Ù‰ Ø§Ù„Ù…ÙˆÙ‚Ø¹. ÙŠÙ…ÙƒÙ†Ùƒ Ø§Ù„Ø¨Ø­Ø« Ø¨Ø§Ø³Ù… Ø§Ù„Ø­ÙŠ Ø£Ùˆ Ø§Ù„Ù…Ù†Ø·Ù‚Ø©.') : error.code === 2 ? t('Your location is unavailable. Try a manual neighborhood or area search.', 'ØªØ¹Ø°Ø± ØªØ­Ø¯ÙŠØ¯ Ù…ÙˆÙ‚Ø¹Ùƒ. Ø¬Ø±Ù‘Ø¨ Ø§Ù„Ø¨Ø­Ø« Ø§Ù„ÙŠØ¯ÙˆÙŠ Ø¨Ø§Ø³Ù… Ø§Ù„Ø­ÙŠ Ø£Ùˆ Ø§Ù„Ù…Ù†Ø·Ù‚Ø©.') : error.code === 3 ? t('Location request timed out. Try again or search manually by area.', 'Ø§Ù†ØªÙ‡Øª Ù…Ù‡Ù„Ø© ØªØ­Ø¯ÙŠØ¯ Ø§Ù„Ù…ÙˆÙ‚Ø¹. Ø­Ø§ÙˆÙ„ Ù…Ø±Ø© Ø£Ø®Ø±Ù‰ Ø£Ùˆ Ø§Ø¨Ø­Ø« ÙŠØ¯ÙˆÙŠØ§Ù‹ Ø¨Ø§Ø³Ù… Ø§Ù„Ù…Ù†Ø·Ù‚Ø©.') : t('We could not retrieve your location. You can search manually by neighborhood or area.', 'ØªØ¹Ø°Ø± Ø§Ù„Ø­ØµÙˆÙ„ Ø¹Ù„Ù‰ Ù…ÙˆÙ‚Ø¹Ùƒ. ÙŠÙ…ÙƒÙ†Ùƒ Ø§Ù„Ø¨Ø­Ø« ÙŠØ¯ÙˆÙŠØ§Ù‹ Ø¨Ø§Ø³Ù… Ø§Ù„Ø­ÙŠ Ø£Ùˆ Ø§Ù„Ù…Ù†Ø·Ù‚Ø©.');
      setGeoStatus(message, true);
    }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 });
  }

  function setDistrictOptions(governorate) {
    if (!distEl) return;
    distEl.innerHTML = '<option value="">' + escapeHtml(governorate ? t('All districts / areas', 'ÙƒÙ„ Ø§Ù„Ø£Ù„ÙˆÙŠØ© / Ø§Ù„Ù…Ù†Ø§Ø·Ù‚') : t('Select a governorate first to view districts', 'Ø§Ø®ØªØ± Ø§Ù„Ù…Ø­Ø§ÙØ¸Ø© Ø£ÙˆÙ„Ø§Ù‹ Ù„Ø¹Ø±Ø¶ Ø§Ù„Ø£Ù„ÙˆÙŠØ©')) + '</option>';
    distEl.disabled = !governorate; if (!governorate) return;
    const selected = cachedGovernorates.find(function (item) { return item.name_ar === governorate || item.name_en === governorate || item.id === governorate || item.key === governorate; });
    (selected && selected.cities ? selected.cities : []).forEach(function (city) { const option = document.createElement('option'); option.value = city; option.textContent = city; distEl.appendChild(option); });
  }
  function selectGovernorate(governorate) {
    if (!govEl) return;
    const matching = cachedGovernorates.find(function (item) {
      return item.name_ar === governorate || item.name_en === governorate || item.id === governorate || (item.cities || []).indexOf(governorate) !== -1;
    });
    const resolvedGovernorate = matching ? (matching.name_ar || matching.name_en || governorate) : governorate;
    govEl.value = resolvedGovernorate; setDistrictOptions(resolvedGovernorate); if (distEl) distEl.value = '';
    quickPills.forEach(function (pill) { pill.classList.toggle('kg-pill-active', pill.getAttribute('data-gov') === governorate); });
    const section = document.getElementById('kg-search-section'); if (section) section.scrollIntoView({ behavior: 'smooth', block: 'center' }); search(true);
  }
  window.selectGovernorate = selectGovernorate;

  function fillModal(kg) {
    const name = isEnglish() && kg.name_en ? kg.name_en : (kg.name_ar || kg.name_en || t('Nursery', 'Ø­Ø¶Ø§Ù†Ø©'));
    const location = [kg.area, kg.district, kg.governorate].filter(Boolean).join('ØŒ '); const phone = kg.contact_phone || ''; const email = kg.contact_email || '';
    const address = kg.address_line || location || t('Address not available', 'Ø§Ù„Ø¹Ù†ÙˆØ§Ù† ØºÙŠØ± Ù…ØªÙˆÙØ±'); const capacity = Number(kg.total_capacity || 0); const current = Number(kg.current_child_count || 0);
    const occupancy = typeof kg.occupancy_pct === 'number' ? kg.occupancy_pct : (capacity ? Math.round(current / capacity * 100) : 0);
    if (modalKgName) modalKgName.textContent = name; if (modalKgNameEn) modalKgNameEn.textContent = kg.name_en && !isEnglish() ? kg.name_en : '';
    if (modalKgLocation) modalKgLocation.textContent = location; if (modalKgGovDist) modalKgGovDist.textContent = [kg.governorate, kg.district].filter(Boolean).join(' â€” ') || t('Not specified', 'ØºÙŠØ± Ù…Ø­Ø¯Ø¯');
    if (modalKgArea) modalKgArea.textContent = kg.area || t('Not specified', 'ØºÙŠØ± Ù…Ø­Ø¯Ø¯'); if (modalKgAddress) modalKgAddress.textContent = address;
    if (modalKgPhoneText) modalKgPhoneText.textContent = phone || t('Not available', 'ØºÙŠØ± Ù…ØªÙˆÙØ±'); if (modalKgPhone) { modalKgPhone.href = phone ? 'tel:' + phone.replace(/\s+/g, '') : '#'; modalKgPhone.classList.toggle('is-disabled', !phone); }
    if (modalKgCallBtn) { modalKgCallBtn.href = phone ? 'tel:' + phone.replace(/\s+/g, '') : '#'; modalKgCallBtn.classList.toggle('is-disabled', !phone); }
    if (modalKgEmail) modalKgEmail.textContent = email || t('Not available', 'ØºÙŠØ± Ù…ØªÙˆÙØ±'); if (modalKgEmailLink) { modalKgEmailLink.href = email ? 'mailto:' + email : '#'; modalKgEmailLink.classList.toggle('is-disabled', !email); }
    if (modalKgHours) modalKgHours.textContent = [kg.working_hours_start, kg.working_hours_end].filter(Boolean).join(' â€” ') || t('Not specified', 'ØºÙŠØ± Ù…Ø­Ø¯Ø¯Ø©'); if (modalKgDays) modalKgDays.textContent = kg.working_days || t('Not specified', 'ØºÙŠØ± Ù…Ø­Ø¯Ø¯Ø©');
    if (modalKgCapacityText) modalKgCapacityText.textContent = capacity ? current + ' / ' + capacity + ' (' + occupancy + '%)' : t('Registered capacity available', 'Ø§Ù„Ø·Ø§Ù‚Ø© Ø§Ù„Ø§Ø³ØªÙŠØ¹Ø§Ø¨ÙŠØ© Ø§Ù„Ù…Ø³Ø¬Ù„Ø© Ù…ØªØ§Ø­Ø©'); if (modalKgCapacityBar) modalKgCapacityBar.style.width = Math.min(100, Math.max(0, occupancy)) + '%';
    const hasCoordinates = Number.isFinite(Number(kg.latitude)) && Number.isFinite(Number(kg.longitude));
    if (modalKgDistance) { const distance = userPosition && hasCoordinates ? haversineDistanceKm(userPosition.lat, userPosition.lng, Number(kg.latitude), Number(kg.longitude)) : null; modalKgDistance.textContent = distance === null ? t('Available after GPS search', 'ØªØ¸Ù‡Ø± Ø¨Ø¹Ø¯ ØªÙØ¹ÙŠÙ„ Ø¨Ø­Ø« GPS') : formatDistance(distance); setHidden(modalKgDistance.closest('[data-distance-row]'), distance === null); }
    if (modalKgMapsWrap && modalKgMapsBtn) {
      if (hasCoordinates) {
        const mapsUrl = new URL('https://www.google.com/maps/search/');
        mapsUrl.searchParams.set('api', '1');
        mapsUrl.searchParams.set('query', String(kg.latitude) + ',' + String(kg.longitude));
        modalKgMapsBtn.href = mapsUrl.toString();
        modalKgMapsBtn.setAttribute('aria-label', t('Open ' + name + ' location in Google Maps', 'ÙØªØ­ Ù…ÙˆÙ‚Ø¹ ' + name + ' ÙÙŠ Ø®Ø±Ø§Ø¦Ø· Google'));
        setHidden(modalKgMapsWrap, false);
      } else {
        setHidden(modalKgMapsWrap, true);
      }
    }
  }
  function getFocusableModalElements() { return modalPanel ? Array.from(modalPanel.querySelectorAll('a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])')).filter(function (element) { return !element.classList.contains('is-disabled'); }) : []; }
  async function openKgDetailsModal(id, trigger) {
    if (!modalEl) return;
    lastFocusedTrigger = trigger || document.querySelector('[data-kg-id="' + String(id).replace(/"/g, '') + '"]');
    modalEl.classList.remove('hidden');
    document.body.classList.add('overflow-hidden');
    if (modalPanel) { modalPanel.setAttribute('aria-busy', 'true'); modalPanel.focus(); }
    if (modalKgName) modalKgName.textContent = t('Loading kindergarten detailsâ€¦', 'Ø¬Ø§Ø±Ù ØªØ­Ù…ÙŠÙ„ ØªÙØ§ØµÙŠÙ„ Ø§Ù„Ø­Ø¶Ø§Ù†Ø©â€¦');
    if (modalKgNameEn) modalKgNameEn.textContent = '';
    setModalStatus(t('Loading public detailsâ€¦', 'Ø¬Ø§Ø±Ù ØªØ­Ù…ÙŠÙ„ Ø§Ù„ØªÙØ§ØµÙŠÙ„ Ø§Ù„Ø¹Ø§Ù…Ø©â€¦'));
    try {
      const response = await fetch(SINGLE_KG_API + '/' + encodeURIComponent(id), { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const payload = await response.json(); const kg = payload && payload.data;
      if (!kg) throw new Error('Empty kindergarten details');
      fillModal(kg); setModalStatus('');
    } catch (error) {
      console.error('Failed fetching public nursery details:', error);
      setModalStatus(t('We could not load this kindergarten. Close the dialog and try again.', 'ØªØ¹Ø°Ø± ØªØ­Ù…ÙŠÙ„ Ø¨ÙŠØ§Ù†Ø§Øª Ù‡Ø°Ù‡ Ø§Ù„Ø­Ø¶Ø§Ù†Ø©. Ø£ØºÙ„Ù‚ Ø§Ù„Ù†Ø§ÙØ°Ø© ÙˆØ­Ø§ÙˆÙ„ Ù…Ø±Ø© Ø£Ø®Ø±Ù‰.'), true);
    } finally {
      if (modalPanel) modalPanel.setAttribute('aria-busy', 'false');
    }
  }
  function closeKgDetailsModal() { if (!modalEl) return; modalEl.classList.add('hidden'); document.body.classList.remove('overflow-hidden'); setModalStatus(''); if (modalPanel) modalPanel.setAttribute('aria-busy', 'false'); if (lastFocusedTrigger && document.contains(lastFocusedTrigger)) lastFocusedTrigger.focus(); }
  window.openKgDetailsModal = openKgDetailsModal; window.closeKgDetailsModal = closeKgDetailsModal;

  async function loadGovernorates() {
    try { const response = await fetch(LOCATIONS_API, { headers: { Accept: 'application/json' } }); if (!response.ok) return; const payload = await response.json(); cachedGovernorates = payload && payload.governorates ? payload.governorates : []; if (!govEl || !cachedGovernorates.length) return;
      const params = new URLSearchParams(window.location.search); const current = params.get('governorate') || '';
      govEl.innerHTML = '<option value="">' + escapeHtml(t('All governorates (12)', 'ÙƒÙ„ Ø§Ù„Ù…Ø­Ø§ÙØ¸Ø§Øª (12)')) + '</option>';
      cachedGovernorates.forEach(function (item) { const option = document.createElement('option'); option.value = item.name_ar || item.name_en || item.id; option.textContent = isEnglish() && item.name_en ? item.name_en : (item.name_ar || item.name_en); govEl.appendChild(option); });
      if (current) govEl.value = current; setDistrictOptions(govEl.value); if (distEl && params.get('district')) distEl.value = params.get('district');
    } catch (error) { console.warn('Failed to load governorates:', error); }
  }

  function init() {
    const params = new URLSearchParams(window.location.search); if (inputEl && params.get('q')) inputEl.value = params.get('q'); updateClearButton();
    if (searchBtn) searchBtn.addEventListener('click', function () { search(true); }); if (geoBtn) geoBtn.addEventListener('click', handleGeolocation);
    if (inputEl) { inputEl.addEventListener('input', debouncedSearch); inputEl.addEventListener('keydown', function (event) { if (event.key === 'Enter') { event.preventDefault(); if (debounceTimer) window.clearTimeout(debounceTimer); search(true); } }); }
    if (clearBtn && inputEl) clearBtn.addEventListener('click', resetSearch);
    if (govEl) govEl.addEventListener('change', function () { setDistrictOptions(govEl.value); if (distEl) distEl.value = ''; search(true); }); if (distEl) distEl.addEventListener('change', function () { search(true); });
    quickPills.forEach(function (pill) { pill.addEventListener('click', function () { selectGovernorate(pill.getAttribute('data-gov') || ''); }); });
    if (resultsResetBtn) resultsResetBtn.addEventListener('click', resetSearch);
    if (resultsEmptyResetBtn) resultsEmptyResetBtn.addEventListener('click', resetSearch);
    if (resultsRetryBtn) resultsRetryBtn.addEventListener('click', function () { search(true); });
    if (resultsGrid) {
      // Pin button click - open Google Maps directly
      resultsGrid.addEventListener('click', function (event) {
        const pinBtn = event.target.closest('.kg-card-pin-btn');
        if (pinBtn) {
          event.stopPropagation();
          const lat = pinBtn.getAttribute('data-lat');
          const lng = pinBtn.getAttribute('data-lng');
          const name = pinBtn.getAttribute('data-name');
          if (lat && lng) {
            const mapsUrl = new URL('https://www.google.com/maps/search/');
            mapsUrl.searchParams.set('api', '1');
            mapsUrl.searchParams.set('query', lat + ',' + lng);
            window.open(mapsUrl.toString(), '_blank', 'noopener,noreferrer');
          }
          return;
        }
        const trigger = event.target.closest('[data-kg-id]');
        if (trigger) openKgDetailsModal(trigger.getAttribute('data-kg-id'), trigger);
      });
      resultsGrid.addEventListener('keydown', function (event) {
        const card = event.target.closest('article[data-kg-id]');
        if (card && (event.key === 'Enter' || event.key === ' ')) {
          event.preventDefault();
          openKgDetailsModal(card.getAttribute('data-kg-id'), card);
        }
      });
    }
    if (modalCloseBtn) modalCloseBtn.addEventListener('click', closeKgDetailsModal); if (modalCloseFooterBtn) modalCloseFooterBtn.addEventListener('click', closeKgDetailsModal); if (modalEl) modalEl.addEventListener('click', function (event) { if (event.target === modalEl) closeKgDetailsModal(); });
    document.addEventListener('keydown', function (event) { if (!modalEl || modalEl.classList.contains('hidden')) return; if (event.key === 'Escape') { event.preventDefault(); closeKgDetailsModal(); return; } if (event.key !== 'Tab') return; const focusable = getFocusableModalElements(); if (!focusable.length) return; const first = focusable[0]; const last = focusable[focusable.length - 1]; if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); } });
    loadGovernorates();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();


