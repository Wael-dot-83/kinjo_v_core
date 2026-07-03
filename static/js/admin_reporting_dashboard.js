(function () {
  'use strict';

  const CSRF_HEADER = 'X-CSRF-Token';
  const CSRF_COOKIE = document.querySelector('meta[name="csrf-token"]')?.content || '';

  async function apiGet(path, params) {
    const url = new URL(path, window.location.origin);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
          url.searchParams.set(key, value);
        }
      });
    }
    const headers = {};
    if (CSRF_HEADER && CSRF_COOKIE) {
      headers[CSRF_HEADER] = CSRF_COOKIE;
    }
    const response = await fetch(url.toString(), {
      method: 'GET',
      headers,
      credentials: 'same-origin',
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`API error ${response.status}: ${text}`);
    }
    return response.json();
  }

  function getLevel() {
    return document.getElementById('reportLevel')?.value || 'jordan';
  }

  function getGovernorate() {
    return document.getElementById('governorateFilter')?.value?.trim() || undefined;
  }

  function getCity() {
    return document.getElementById('cityFilter')?.value?.trim() || undefined;
  }

  function getKindergartenId() {
    const val = document.getElementById('kindergartenIdFilter')?.value?.trim();
    return val ? parseInt(val, 10) : undefined;
  }

  function getClassId() {
    const val = document.getElementById('classIdFilter')?.value?.trim();
    return val ? parseInt(val, 10) : undefined;
  }

  function getPeriod() {
    const start = document.getElementById('periodStart')?.value;
    const end = document.getElementById('periodEnd')?.value;
    if (start && end) {
      return { date_from: start, date_to: end };
    }
    return { period: 'this_month' };
  }

  function getFilters() {
    const period = getPeriod();
    return {
      level: getLevel(),
      governorate: getGovernorate(),
      city: getCity(),
      kindergarten_id: getKindergartenId(),
      class_id: getClassId(),
      ...period,
    };
  }

  const _isAr = () => document.documentElement.lang === 'ar';
  const _t = (ar, en) => _isAr() ? ar : en;

  function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function setHtml(id, html) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  }

  function emptyRow(colspan) {
    return `<tr><td colspan="${colspan}" class="text-center py-4 text-muted">${_t('لا تتوفر بيانات للفترة أو المعايير المحددة. يرجى تعديل عوامل التصفية أو اختيار نطاق زمني مختلف.', 'No data available')}</td></tr>`;
  }

  function errorRow(colspan) {
    return `<tr><td colspan="${colspan}" class="text-center py-4 text-danger">${_t('فشل التحميل', 'Failed to load')}</td></tr>`;
  }

  function formatPct(value) {
    if (value === null || value === undefined || isNaN(value)) return '--%';
    return Math.round(value) + '%';
  }

  function formatNumber(value) {
    if (value === null || value === undefined || isNaN(value)) return '--';
    return value.toLocaleString();
  }

  function statusBadge(status) {
    const map = {
      critical: { cls: 'badge bg-danger',           ar: 'حرج',      en: 'Critical' },
      warning:  { cls: 'badge bg-warning text-dark', ar: 'تحذير',    en: 'Warning' },
      normal:   { cls: 'badge bg-success',           ar: 'طبيعي',    en: 'Normal' },
      green:    { cls: 'badge bg-success',           ar: 'أخضر',     en: 'Green' },
      yellow:   { cls: 'badge bg-warning text-dark', ar: 'أصفر',     en: 'Yellow' },
      orange:   { cls: 'badge bg-orange',            ar: 'برتقالي',  en: 'Orange' },
      red:      { cls: 'badge bg-danger',            ar: 'أحمر',     en: 'Red' },
    };
    const entry = map[status] || { cls: 'badge bg-secondary', ar: escapeHtml(status), en: escapeHtml(status) };
    return `<span class="${entry.cls}">${_t(entry.ar, entry.en)}</span>`;
  }

  function classificationLabel(cls) {
    const map = {
      inactive:                 { ar: 'غير نشط',          en: 'Inactive' },
      resource_underuse:        { ar: 'استخدام منخفض',     en: 'Underuse' },
      critical_risk:            { ar: 'خطورة حرجة',        en: 'Critical risk' },
      normal:                   { ar: 'طبيعي',             en: 'Normal' },
      under_supervised:         { ar: 'إشراف منخفض',       en: 'Under-supervised' },
      capacity_class_pressure:  { ar: 'ضغط على الفصل',    en: 'Class pressure' },
      over_capacity:            { ar: 'تجاوز السعة',       en: 'Over capacity' },
      operational_issue:        { ar: 'مشكلة تشغيلية',     en: 'Operational issue' },
    };
    const entry = map[cls] || { ar: escapeHtml(cls), en: escapeHtml(cls) };
    return _t(entry.ar, entry.en);
  }

  let ageChartInstance = null;
  let genderChartInstance = null;
  let childrenGovChartInstance = null;
  let childrenCityChartInstance = null;
  let childrenVsSupChartInstance = null;
  let riskClassChartInstance = null;
  let supGapChartInstance = null;
  let supErrorChartInstance = null;

  function destroyChart(instance) {
    if (instance) instance.destroy();
    return null;
  }

  async function loadNationalKPIs() {
    try {
      const data = await apiGet('/api/admin/reports/overview', { level: 'jordan', ...getPeriod() });
      setText('kpiTotalChildren', formatNumber(data.kpis?.total_children));
      setText('kpiTotalKindergartens', formatNumber(data.kpis?.total_kindergartens));
      setText('kpiTotalSupervisors', formatNumber(data.kpis?.total_supervisors));
      setText('kpiTotalClasses', formatNumber(data.kpis?.total_classes));
      setText('kpiChildrenPerSupervisor', formatNumber(data.kpis?.children_per_supervisor));
      setText('kpiSupervisorGap', formatNumber(data.kpis?.supervisor_gap));
      setText('kpiCapacityUtil', formatPct(data.kpis?.capacity_utilization_pct));
      setText('kpiDataQuality', formatPct(data.kpis?.data_quality_score));
      setText('kpiCompliance', formatPct(data.kpis?.compliance_score));

      const dqScore = data.kpis?.data_quality_score ?? 0;
      let dqBandAr = 'أحمر', dqBandEn = 'Red';
      if (dqScore >= 95) { dqBandAr = 'أخضر'; dqBandEn = 'Green'; }
      else if (dqScore >= 85) { dqBandAr = 'أصفر'; dqBandEn = 'Yellow'; }
      else if (dqScore >= 70) { dqBandAr = 'برتقالي'; dqBandEn = 'Orange'; }
      const isAr = document.documentElement.lang === 'ar';
      setText('kpiDataQualityBand', isAr ? dqBandAr : dqBandEn);

      const compScore = data.kpis?.compliance_score ?? 0;
      let compBandAr = 'أحمر', compBandEn = 'Red';
      if (compScore >= 95) { compBandAr = 'أخضر'; compBandEn = 'Green'; }
      else if (compScore >= 85) { compBandAr = 'أصفر'; compBandEn = 'Yellow'; }
      else if (compScore >= 70) { compBandAr = 'برتقالي'; compBandEn = 'Orange'; }
      setText('kpiComplianceBand', isAr ? compBandAr : compBandEn);

      if (data.interpretation) {
        const summary = data.interpretation.summary || '';
        const action = data.interpretation.recommended_action || '';
        setHtml('nationalInterpretation', `<strong>${summary}</strong><br>${action}`);
      }
    } catch (err) {
      console.error('Failed to load national KPIs:', err);
    }
  }

  async function loadChildrenAnalytics() {
    try {
      const ageData = await apiGet('/api/admin/reports/children/age-buckets', { ...getFilters(), level: getLevel() });
      const genderData = await apiGet('/api/admin/reports/children/gender', { ...getFilters(), level: getLevel() });
      const geoData = await apiGet('/api/admin/reports/children/geography', { ...getFilters(), level: getLevel() });

      ageChartInstance = destroyChart(ageChartInstance);
      const ageCtx = document.getElementById('ageDistributionChart');
      if (ageCtx) {
        ageChartInstance = new Chart(ageCtx, {
          type: 'bar',
          data: {
            labels: (ageData.age_buckets || []).map(b => b.bucket),
            datasets: [{
              label: document.documentElement.lang === 'ar' ? 'عدد الأطفال' : 'Children',
              data: (ageData.age_buckets || []).map(b => b.count),
              backgroundColor: 'rgba(37, 99, 235, 0.7)',
              borderColor: 'rgba(37, 99, 235, 1)',
              borderWidth: 1,
            }],
          },
          options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
        });
      }

      genderChartInstance = destroyChart(genderChartInstance);
      const genderCtx = document.getElementById('genderDistributionChart');
      if (genderCtx) {
        const counts = genderData.counts || { male: 0, female: 0, unknown: 0 };
        genderChartInstance = new Chart(genderCtx, {
          type: 'doughnut',
          data: {
            labels: [document.documentElement.lang === 'ar' ? 'ذكر' : 'Male', document.documentElement.lang === 'ar' ? 'أنثى' : 'Female', document.documentElement.lang === 'ar' ? 'غير محدد' : 'Unknown'],
            datasets: [{
              data: [counts.male || 0, counts.female || 0, counts.unknown || 0],
              backgroundColor: ['rgba(37, 99, 235, 0.7)', 'rgba(236, 72, 153, 0.7)', 'rgba(156, 163, 175, 0.7)'],
              borderColor: ['rgba(37, 99, 235, 1)', 'rgba(236, 72, 153, 1)', 'rgba(156, 163, 175, 1)'],
              borderWidth: 1,
            }],
          },
          options: { responsive: true, maintainAspectRatio: false },
        });
      }

      childrenGovChartInstance = destroyChart(childrenGovChartInstance);
      const govCtx = document.getElementById('childrenByGovernorateChart');
      if (govCtx) {
        const govs = geoData.governorates || [];
        childrenGovChartInstance = new Chart(govCtx, {
          type: 'bar',
          data: {
            labels: govs.map(g => g.governorate),
            datasets: [{
              label: document.documentElement.lang === 'ar' ? 'الأطفال' : 'Children',
              data: govs.map(g => g.children_count || 0),
              backgroundColor: 'rgba(16, 185, 129, 0.7)',
              borderColor: 'rgba(16, 185, 129, 1)',
              borderWidth: 1,
            }],
          },
          options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y', plugins: { legend: { display: false } } },
        });
      }

      childrenCityChartInstance = destroyChart(childrenCityChartInstance);
      const cityCtx = document.getElementById('childrenByCityChart');
      if (cityCtx) {
        const cities = geoData.cities || [];
        childrenCityChartInstance = new Chart(cityCtx, {
          type: 'bar',
          data: {
            labels: cities.map(c => c.city),
            datasets: [{
              label: document.documentElement.lang === 'ar' ? 'الأطفال' : 'Children',
              data: cities.map(c => c.children_count || 0),
              backgroundColor: 'rgba(245, 158, 11, 0.7)',
              borderColor: 'rgba(245, 158, 11, 1)',
              borderWidth: 1,
            }],
          },
          options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y', plugins: { legend: { display: false } } },
        });
      }
    } catch (err) {
      console.error('Failed to load children analytics:', err);
    }
  }

  async function loadKindergartensAnalytics() {
    try {
      const data = await apiGet('/api/admin/reports/kindergartens/classification', { ...getFilters(), level: getLevel() });
      const kgs = data.kindergartens || [];
      const tbody = document.getElementById('kindergartenRiskTableBody');
      if (kgs.length === 0) {
        tbody.innerHTML = emptyRow(9);
      } else {
        tbody.innerHTML = kgs.map(kg => `
          <tr>
            <td>${escapeHtml(kg.name_ar || kg.name_en) || '--'}</td>
            <td>${escapeHtml(kg.governorate) || '--'}</td>
            <td>${escapeHtml(kg.city) || '--'}</td>
            <td>${formatNumber(kg.children_count)}</td>
            <td>${formatNumber(kg.supervisors_count)}</td>
            <td>${formatNumber(kg.capacity)}</td>
            <td>${formatPct(kg.capacity_utilization_pct)}</td>
            <td>${statusBadge(kg.risk_status)}</td>
            <td>${escapeHtml(kg.recommended_action_ar || kg.recommended_action_en) || '--'}</td>
          </tr>
        `).join('');
      }

      const classificationCounts = data.classification_counts || {};
      const labels = Object.keys(classificationCounts).map(classificationLabel);
      const values = Object.values(classificationCounts);

      childrenVsSupChartInstance = destroyChart(childrenVsSupChartInstance);
      const cvCtx = document.getElementById('childrenVsSupervisorsChart');
      if (cvCtx) {
        childrenVsSupChartInstance = new Chart(cvCtx, {
          type: 'scatter',
          data: {
            datasets: [{
              label: document.documentElement.lang === 'ar' ? 'حضانات' : 'Kindergartens',
              data: kgs.map(kg => ({ x: kg.supervisors_count || 0, y: kg.children_count || 0 })),
              backgroundColor: 'rgba(37, 99, 235, 0.7)',
            }],
          },
          options: { responsive: true, maintainAspectRatio: false, scales: { x: { title: { display: true, text: document.documentElement.lang === 'ar' ? 'مشرفون' : 'Supervisors' } }, y: { title: { display: true, text: document.documentElement.lang === 'ar' ? 'أطفال' : 'Children' } } } },
        });
      }

      riskClassChartInstance = destroyChart(riskClassChartInstance);
      const rcCtx = document.getElementById('riskClassificationChart');
      if (rcCtx) {
        riskClassChartInstance = new Chart(rcCtx, {
          type: 'pie',
          data: {
            labels,
            datasets: [{
              data: values,
              backgroundColor: ['rgba(239, 68, 68, 0.7)', 'rgba(245, 158, 11, 0.7)', 'rgba(16, 185, 129, 0.7)', 'rgba(156, 163, 175, 0.7)', 'rgba(99, 102, 241, 0.7)'],
            }],
          },
          options: { responsive: true, maintainAspectRatio: false },
        });
      }
    } catch (err) {
      console.error('Failed to load kindergartens analytics:', err);
    }
  }

  async function loadSupervisorsAnalytics() {
    try {
      const data = await apiGet('/api/admin/reports/supervisors/analytics', { ...getFilters(), level: getLevel() });
      const errorTable = data.error_table || [];
      const supTbody = document.getElementById('supervisorErrorsTableBody');
      if (errorTable.length === 0) {
        supTbody.innerHTML = emptyRow(6);
      } else {
        supTbody.innerHTML = errorTable.map(s => `
          <tr>
            <td>${escapeHtml(s.full_name || s.username) || '--'}</td>
            <td>${escapeHtml(s.kindergarten_name_ar || s.kindergarten_name_en) || '--'}</td>
            <td>${escapeHtml(s.city || s.governorate) || '--'}</td>
            <td>${formatNumber(s.classes_count)}</td>
            <td>${formatNumber(s.children_count)}</td>
            <td>${escapeHtml((s.error_flags || []).map(f => f.replace(/_/g, ' ')).join(', ')) || '--'}</td>
          </tr>
        `).join('');
      }

      supGapChartInstance = destroyChart(supGapChartInstance);
      const gapCtx = document.getElementById('supervisorGapChart');
      if (gapCtx) {
        const totalRequired = data.kpis?.required_supervisors ?? 0;
        const totalActual = data.kpis?.actual_supervisors ?? 0;
        supGapChartInstance = new Chart(gapCtx, {
          type: 'bar',
          data: {
            labels: [document.documentElement.lang === 'ar' ? 'مطلوب' : 'Required', document.documentElement.lang === 'ar' ? 'فعلي' : 'Actual'],
            datasets: [{
              label: document.documentElement.lang === 'ar' ? 'المشرفون' : 'Supervisors',
              data: [totalRequired, totalActual],
              backgroundColor: ['rgba(245, 158, 11, 0.7)', 'rgba(16, 185, 129, 0.7)'],
              borderColor: ['rgba(245, 158, 11, 1)', 'rgba(16, 185, 129, 1)'],
              borderWidth: 1,
            }],
          },
          options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
        });
      }

      supErrorChartInstance = destroyChart(supErrorChartInstance);
      const errCtx = document.getElementById('supervisorErrorsChart');
      if (errCtx) {
        const errorCounts = {
          [document.documentElement.lang === 'ar' ? 'بلا فصل' : 'No class']: data.supervisors_without_class || 0,
          [document.documentElement.lang === 'ar' ? 'فصول متعددة' : 'Multiple classes']: data.supervisors_multiple_classes || 0,
          [document.documentElement.lang === 'ar' ? 'خارج الحضانة' : 'Outside KG']: data.supervisors_outside_kg || 0,
        };
        supErrorChartInstance = new Chart(errCtx, {
          type: 'bar',
          data: {
            labels: Object.keys(errorCounts),
            datasets: [{
              label: document.documentElement.lang === 'ar' ? 'العدد' : 'Count',
              data: Object.values(errorCounts),
              backgroundColor: ['rgba(239, 68, 68, 0.7)', 'rgba(245, 158, 11, 0.7)', 'rgba(99, 102, 241, 0.7)'],
              borderWidth: 1,
            }],
          },
          options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } },
        });
      }
    } catch (err) {
      console.error('Failed to load supervisors analytics:', err);
    }
  }

  async function loadDataQuality() {
    try {
      const data = await apiGet('/api/admin/reports/data-quality', { ...getFilters(), level: getLevel() });
      setText('dqScore', formatPct(data.data_quality_score));
      const score = data.data_quality_score ?? 0;
      let bandAr = 'أحمر', bandEn = 'Red';
      if (score >= 95) { bandAr = 'أخضر'; bandEn = 'Green'; }
      else if (score >= 85) { bandAr = 'أصفر'; bandEn = 'Yellow'; }
      else if (score >= 70) { bandAr = 'برتقالي'; bandEn = 'Orange'; }
      const isAr = document.documentElement.lang === 'ar';
      setText('dqBand', isAr ? bandAr : bandEn);

      const issues = data.issues || {};
      setText('dqMissingDob', formatNumber(issues.missing_dob));
      setText('dqWithoutKg', formatNumber(issues.children_without_kindergarten));
      setText('dqDuplicate', formatNumber(issues.duplicate_children));

      if (data.interpretation) {
        const summary = data.interpretation.summary || '';
        const action = data.interpretation.recommended_action || '';
        setHtml('dqInterpretation', `<strong>${summary}</strong><br>${action}`);
      }
    } catch (err) {
      console.error('Failed to load data quality:', err);
    }
  }

  async function loadCompliance() {
    try {
      const data = await apiGet('/api/admin/reports/compliance', { ...getFilters(), level: getLevel() });
      setText('compScore', formatPct(data.compliance_score));
      const score = data.compliance_score ?? 0;
      let bandAr = 'أحمر', bandEn = 'Red';
      if (score >= 95) { bandAr = 'أخضر'; bandEn = 'Green'; }
      else if (score >= 85) { bandAr = 'أصفر'; bandEn = 'Yellow'; }
      else if (score >= 70) { bandAr = 'برتقالي'; bandEn = 'Orange'; }
      const isAr = document.documentElement.lang === 'ar';
      setText('compBand', isAr ? bandAr : bandEn);

      const violations = data.violations || {};
      setText('compOverCapacity', formatNumber(violations.kindergartens_over_capacity));
      setText('compNoSupervisor', formatNumber(violations.kindergartens_no_supervisor_with_children));
      setText('compInvalidAge', formatNumber(violations.invalid_age_too_young + violations.invalid_age_too_old));

      if (data.interpretation) {
        const summary = data.interpretation.summary || '';
        const action = data.interpretation.recommended_action || '';
        setHtml('compInterpretation', `<strong>${summary}</strong><br>${action}`);
      }
    } catch (err) {
      console.error('Failed to load compliance:', err);
    }
  }

  async function loadRiskRanking() {
    try {
      const data = await apiGet('/api/admin/reports/risk-ranking', { ...getFilters(), level: getLevel() });
      const ranking = data.ranking || [];
      const tbody = document.getElementById('riskRankingTableBody');
      if (ranking.length === 0) {
        tbody.innerHTML = emptyRow(6);
      } else {
        tbody.innerHTML = ranking.map(r => `
          <tr>
            <td>${escapeHtml(r.governorate) || '--'}</td>
            <td>${escapeHtml(r.city) || '--'}</td>
            <td>${formatNumber(r.risk_score)}</td>
            <td>${statusBadge(r.risk_status)}</td>
            <td>${formatNumber(r.children_per_supervisor)}</td>
            <td>${formatPct(r.capacity_utilization_pct)}</td>
          </tr>
        `).join('');
      }
    } catch (err) {
      console.error('Failed to load risk ranking:', err);
    }
  }

  async function loadKindergartenDetail() {
    const level = getLevel();
    const section = document.getElementById('section-kindergarten-detail');
    if (level === 'jordan' || level === 'governorate' || level === 'city') {
      section.classList.remove('d-none');
      const tbody = document.getElementById('kindergartenDetailTableBody');
      try {
        const data = await apiGet('/api/admin/reports/kindergartens/detail', { ...getFilters(), level });
        const kgs = data.kindergartens || [];
        if (kgs.length === 0) {
          tbody.innerHTML = emptyRow(12);
        } else {
          tbody.innerHTML = kgs.map(kg => `
            <tr>
              <td>${escapeHtml(kg.name_ar || kg.name_en) || '--'}</td>
              <td>${escapeHtml(kg.governorate) || '--'}</td>
              <td>${escapeHtml(kg.city) || '--'}</td>
              <td>${formatNumber(kg.children_count)}</td>
              <td>${formatNumber(kg.supervisors_count)}</td>
              <td>${formatNumber(kg.classes_count)}</td>
              <td>${formatNumber(kg.capacity)}</td>
              <td>${formatPct(kg.capacity_utilization_pct)}</td>
              <td>${formatNumber(kg.supervisor_gap)}</td>
              <td>${statusBadge(kg.risk_status)}</td>
              <td>${classificationLabel(kg.classification)}</td>
              <td>${escapeHtml(kg.recommended_action_ar || kg.recommended_action_en) || '--'}</td>
            </tr>
          `).join('');
        }
      } catch (err) {
        console.error('Failed to load kindergarten detail:', err);
        tbody.innerHTML = errorRow(12);
      }
    } else {
      section.classList.add('d-none');
    }
  }

  async function loadClassDetail() {
    const level = getLevel();
    const section = document.getElementById('section-class-detail');
    if (level === 'kindergarten' || level === 'class') {
      section.classList.remove('d-none');
      const tbody = document.getElementById('classDetailTableBody');
      try {
        const data = await apiGet('/api/admin/reports/classes/detail', { ...getFilters(), level: 'kindergarten', kindergarten_id: getKindergartenId(), class_id: getClassId() });
        const classes = data.classes || [];
        if (classes.length === 0) {
          tbody.innerHTML = emptyRow(10);
        } else {
          tbody.innerHTML = classes.map(c => `
            <tr>
              <td>${escapeHtml(c.class_code) || '--'}</td>
              <td>${escapeHtml(_isAr() ? c.name_ar : c.name_en) || '--'}</td>
              <td>${escapeHtml(c.age_group) || '--'}</td>
              <td>${formatNumber(c.children_count)}</td>
              <td>${formatNumber(c.capacity)}</td>
              <td>${formatNumber(c.supervisors_count)}</td>
              <td>${formatNumber(c.required_supervisors)}</td>
              <td>${formatNumber(c.supervisor_gap)}</td>
              <td>${statusBadge(c.risk_status)}</td>
              <td>${escapeHtml(c.recommended_action_ar || c.recommended_action_en) || '--'}</td>
            </tr>
          `).join('');
        }
      } catch (err) {
        console.error('Failed to load class detail:', err);
        tbody.innerHTML = errorRow(10);
      }
    } else {
      section.classList.add('d-none');
    }
  }

  async function loadAllReports() {
    const indicator = document.getElementById('loadingIndicator');
    const content = document.getElementById('reportContent');
    indicator.classList.remove('d-none');
    content.classList.add('d-none');

    try {
      await Promise.allSettled([
        loadNationalKPIs(),
        loadChildrenAnalytics(),
        loadKindergartensAnalytics(),
        loadSupervisorsAnalytics(),
        loadDataQuality(),
        loadCompliance(),
        loadRiskRanking(),
        loadKindergartenDetail(),
        loadClassDetail(),
      ]);
    } catch (err) {
      console.error('Failed to load reports:', err);
    } finally {
      indicator.classList.add('d-none');
      content.classList.remove('d-none');
      const now = new Date();
      setText('reportsLastUpdated', _t(
        `آخر تحديث: ${now.toLocaleString('ar-JO')}`,
        `Last updated: ${now.toLocaleString('en-US')}`
      ));
    }
  }

  function onLevelChange() {
    const level = getLevel();
    const govContainer = document.getElementById('governorateContainer');
    const cityContainer = document.getElementById('cityContainer');
    const kgContainer = document.getElementById('kgContainer');
    const classContainer = document.getElementById('classContainer');

    if (level === 'jordan') {
      govContainer.style.display = 'none';
      cityContainer.style.display = 'none';
      kgContainer.style.display = 'none';
      classContainer.style.display = 'none';
    } else if (level === 'governorate') {
      govContainer.style.display = '';
      cityContainer.style.display = 'none';
      kgContainer.style.display = 'none';
      classContainer.style.display = 'none';
    } else if (level === 'city') {
      govContainer.style.display = '';
      cityContainer.style.display = '';
      kgContainer.style.display = 'none';
      classContainer.style.display = 'none';
    } else if (level === 'kindergarten') {
      govContainer.style.display = 'none';
      cityContainer.style.display = 'none';
      kgContainer.style.display = '';
      classContainer.style.display = 'none';
    } else if (level === 'class') {
      govContainer.style.display = 'none';
      cityContainer.style.display = 'none';
      kgContainer.style.display = '';
      classContainer.style.display = '';
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    onLevelChange();
    loadAllReports();
  });
})();
