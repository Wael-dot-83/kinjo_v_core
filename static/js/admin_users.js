/**
 * Admin Users Page Module
 * Handles user listing, filtering, sorting, bulk actions, and CSV import
 * Production-ready with proper i18n, data validation, and event handling
 */

(function() {
  'use strict';

  // ============================================================================
  // Configuration
  // ============================================================================

  const CONFIG = {
    DEFAULT_PAGE_SIZE: 100,
    MAX_PAGE_SIZE: 1000,
    DEBOUNCE_DELAY: 300,
    TOAST_DURATION: 5000
  };

  // ============================================================================
  // State Management
  // ============================================================================

  const state = {
    users: [],
    pagination: {
      page: 1,
      pageSize: CONFIG.DEFAULT_PAGE_SIZE,
      total: 0,
      totalPages: 0
    },
    currentSort: { field: 'created_at', direction: 'desc' },
    filters: {
      search: '',
      role: '',
      status: ''
    },
    currentUserRole: null,
    csvData: null
  };

  // ============================================================================
  // User Data Normalization
  // ============================================================================

  /**
   * Normalize raw API user data to UI format
   * Handles null/undefined values gracefully
   */
  function normalizeUser(apiUser) {
    if (!apiUser) return null;

    return {
      id: apiUser.id || 0,
      username: apiUser.username || '',
      email: apiUser.email || '',
      role: apiUser.role || 'PARENT',
      status: apiUser.status || 'ACTIVE',
      kindergarten_id: apiUser.kindergarten_id != null ? apiUser.kindergarten_id : null,
      created_at: apiUser.created_at || null
    };
  }

  // ============================================================================
  // Translation Helpers
  // ============================================================================

  /**
   * Get translation using AdminI18n or fallback
   */
  function t(key, fallback = '') {
    if (window.AdminI18n && typeof AdminI18n.translate === 'function') {
      return AdminI18n.translate(key, fallback);
    }
    return fallback || key;
  }

  /**
   * Get current UI language
   */
  function currentLang() {
    return document.documentElement.lang === 'en' ? 'en' : 'ar';
  }

  /**
   * Translate with Arabic/English inline fallback
   */
  function translate(arText, enText) {
    return currentLang() === 'en' ? enText : arText;
  }

  // ============================================================================
  // Utility Functions
  // ============================================================================

  /**
   * Debounce utility for performance
   */
  function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }

  /**
   * Escape HTML to prevent XSS
   */
  function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
  }

  // ============================================================================
  // Date Formatting (Respects UI Language)
  // ============================================================================

  function formatDateForDisplay(dateString) {
    if (!dateString) return '';
    try {
      const date = new Date(dateString);
      if (isNaN(date.getTime())) return '';
      const locale = currentLang() === 'en' ? 'en-US' : 'ar-JO';
      return date.toLocaleDateString(locale);
    } catch (e) {
      return '';
    }
  }

  // ============================================================================
  // Badge Components
  // ============================================================================

function getRoleBadge(role) {
    const badges = {
      ADMIN: '<span class="badge bg-dark">' + translate('مدير النظام', 'System Admin') + '</span>',
      MANAGER: '<span class="badge badge-soft badge-soft-primary">' + translate('مدير روضة', 'Kindergarten Manager') + '</span>',
      SUPERVISOR: '<span class="badge badge-soft badge-soft-info">' + translate('مشرف', 'Supervisor') + '</span>',
      PARENT: '<span class="badge badge-soft badge-soft-success">' + translate('ولي أمر', 'Parent') + '</span>'
    };
    return badges[role] || '<span class="badge badge-soft badge-soft-secondary">' + escapeHtml(role) + '</span>';
  }

  function getStatusBadge(status) {
    const badges = {
      ACTIVE: '<span class="badge badge-soft badge-soft-success"><i class="bi bi-check-circle me-1"></i>' + translate('نشط', 'Active') + '</span>',
      INACTIVE: '<span class="badge badge-soft badge-soft-secondary"><i class="bi bi-dash-circle me-1"></i>' + translate('غير نشط', 'Inactive') + '</span>',
      SUSPENDED: '<span class="badge badge-soft badge-soft-danger"><i class="bi bi-ban me-1"></i>' + translate('موقوف', 'Suspended') + '</span>'
    };
    return badges[status] || '<span class="badge bg-light text-dark">' + escapeHtml(status) + '</span>';
  }

  function getStatusBadge(status) {
    const badges = {
      ACTIVE: '<span class="badge badge-soft badge-soft-success"><i class="bi bi-check-circle me-1"></i>' + translate('نشط', 'Active') + '</span>',
      INACTIVE: '<span class="badge badge-soft badge-soft-secondary"><i class="bi bi-dash-circle me-1"></i>' + translate('غير نشط', 'Inactive') + '</span>',
      SUSPENDED: '<span class="badge badge-soft badge-soft-danger"><i class="bi bi-ban me-1"></i>' + translate('موقوف', 'Suspended') + '</span>'
    };
    return badges[status] || '<span class="badge bg-light text-dark">' + escapeHtml(status) + '</span>';
  }

  // ============================================================================
  // Rendering
  // ============================================================================

  function renderUsers(users) {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;

    if (!users || users.length === 0) {
      renderEmptyState();
      return;
    }

    // Update results count
    const resultCount = document.getElementById('resultCount');
    if (resultCount) {
      resultCount.textContent = translate(
        `عرض ${users.length} مستخدم`,
        `Showing ${users.length} user(s)`
      );
    }

    tbody.innerHTML = users.map(user => {
      const safeUsername = escapeHtml(user.username);
      const safeEmail = escapeHtml(user.email);
      const initial = safeUsername.charAt(0).toUpperCase() || '?';

      return `
        <tr data-user-id="${user.id}">
          <td>
            <div class="form-check">
              <input type="checkbox" class="form-check-input user-checkbox" value="${user.id}" onchange="AdminUsers.updateBulkActions()" aria-label="${translate('تحديد', 'Select')} ${safeUsername}">
            </div>
          </td>
          <td>
            <div class="d-flex align-items-center">
              <div class="avatar-initials bg-soft-primary text-primary rounded-circle me-3" aria-hidden="true">
                ${initial}
              </div>
              <div>
                <div class="fw-semibold">${safeUsername}</div>
                <div class="small text-muted">${safeEmail}</div>
              </div>
            </div>
          </td>
          <td>${getRoleBadge(user.role)}</td>
          <td>
            ${user.kindergarten_id ? `<span class="text-body"><i class="bi bi-building me-1 text-muted" aria-hidden="true"></i>${translate('رقم', 'No.')} ${user.kindergarten_id}</span>` : '<span class="text-muted">-</span>'}
          </td>
          <td>${getStatusBadge(user.status)}</td>
          <td>
            <time class="small text-muted" datetime="${user.created_at || ''}" title="${user.created_at ? formatDateForDisplay(user.created_at) : ''}">
              ${user.created_at ? formatDateForDisplay(user.created_at) : '-'}
            </time>
          </td>
          <td class="text-end">
            <div class="btn-group" role="group" aria-label="${translate('إجراءات المستخدم', 'User actions')}">
              <a href="/admin/users/${user.id}/edit" class="btn btn-sm btn-outline-secondary" title="${translate('تعديل', 'Edit')}" aria-label="${translate('تعديل', 'Edit')} ${safeUsername}">
                <i class="bi bi-pencil" aria-hidden="true"></i>
              </a>
              ${state.currentUserRole === 'ADMIN' ? `
              <button data-action="reset-password" data-user-id="${user.id}" data-username="${safeUsername}" class="btn btn-sm btn-outline-warning js-user-action" title="${translate('إعادة تعيين كلمة المرور', 'Reset password')}" aria-label="${translate('إعادة تعيين كلمة مرور', 'Reset password for')} ${safeUsername}">
                <i class="bi bi-key" aria-hidden="true"></i>
              </button>
              ` : ''}
              ${state.currentUserRole === 'ADMIN' && user.role !== 'ADMIN' ? `
              <button data-action="delete-user" data-user-id="${user.id}" data-username="${safeUsername}" class="btn btn-sm btn-outline-danger js-user-action" title="${translate('حذف', 'Delete')}" aria-label="${translate('حذف', 'Delete')} ${safeUsername}">
                <i class="bi bi-trash" aria-hidden="true"></i>
              </button>
              ` : ''}
            </div>
          </td>
        </tr>
      `;
    }).join('');
  }

  function renderLoadingState() {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;

    let skeletonRows = '';
    for (let i = 0; i < 5; i++) {
      skeletonRows += '<tr class="table-skeleton-row">';
      for (let j = 0; j < 7; j++) {
        skeletonRows += `<td><div class="table-skeleton-cell" style="width: ${35 + ((i * 17 + j * 13) % 45)}%"></div></td>`;
      }
      skeletonRows += '</tr>';
    }

    tbody.innerHTML = skeletonRows;
    tbody.setAttribute('aria-hidden', 'true');
  }

  function renderEmptyState() {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;

    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="text-center py-5">
          <div class="empty-state">
            <i class="bi bi-person-x"></i>
            <h5>${translate('لا توجد نتائج مطابقة', 'No matching results')}</h5>
            <p class="text-muted">${translate('جرب تغيير معايير البحث أو الفلاتر', 'Try changing search criteria or filters')}</p>
            <a href="/admin/users/create" class="btn btn-primary btn-sm mt-2">
              <i class="bi bi-person-plus me-1"></i>
              ${translate('إضافة مستخدم', 'Add User')}
            </a>
          </div>
        </td>
      </tr>
    `;
  }

  function renderErrorState(errorMessage) {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;

    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="text-center py-5">
          <div class="text-danger">
            <i class="bi bi-exclamation-triangle fs-1 d-block mb-3 opacity-50"></i>
            <p class="mb-1">${translate('حدث خطأ أثناء تحميل البيانات', 'Error loading data')}</p>
            <small class="text-muted d-block mb-3">${escapeHtml(errorMessage)}</small>
            <button class="btn btn-outline-primary btn-sm" onclick="AdminUsers.loadUsers()">
              <i class="bi bi-arrow-clockwise me-1"></i>
              ${translate('إعادة المحاولة', 'Retry')}
            </button>
          </div>
        </td>
      </tr>
    `;
  }

  // ============================================================================
  // Sorting
  // ============================================================================

  function sortUsers(users, field) {
    // Toggle direction if same field
    if (state.currentSort.field === field) {
      state.currentSort.direction = state.currentSort.direction === 'asc' ? 'desc' : 'asc';
    } else {
      state.currentSort.field = field;
      state.currentSort.direction = 'asc';
    }

    // Update UI
    document.querySelectorAll('.sortable').forEach(th => {
      th.classList.remove('asc', 'desc');
    });
    const activeHeader = document.querySelector(`[data-sort="${field}"]`);
    if (activeHeader) {
      activeHeader.classList.add(state.currentSort.direction);
    }

    // Sort the array
    return users.sort((a, b) => {
      let valA = a[field] || '';
      let valB = b[field] || '';

      // Handle date sorting
      if (field === 'created_at') {
        valA = valA ? new Date(valA).getTime() : 0;
        valB = valB ? new Date(valB).getTime() : 0;
      } else {
        valA = String(valA).toLowerCase();
        valB = String(valB).toLowerCase();
      }

      if (valA < valB) return state.currentSort.direction === 'asc' ? -1 : 1;
      if (valA > valB) return state.currentSort.direction === 'asc' ? 1 : -1;
      return 0;
    });
  }

  // ============================================================================
  // Data Loading
  // ============================================================================

  async function loadUsers(page = 1) {
    state.pagination.page = page;
    renderLoadingState();

    try {
      const response = await api.get('/api/admin/users', {
        page: page,
        limit: state.pagination.pageSize,
        search: state.filters.search,
        role: state.filters.role || undefined,
        status: state.filters.status || undefined
      });

      // Extract data and pagination from response
      const usersRaw = response.data || [];
      const pagination = response.pagination || {};

      // Update pagination state
      state.pagination = {
        page: pagination.page || 1,
        pageSize: pagination.pageSize || CONFIG.DEFAULT_PAGE_SIZE,
        total: pagination.total || 0,
        totalPages: pagination.total_pages || 0
      };

      // Normalize users
      state.users = usersRaw.map(normalizeUser).filter(Boolean);

      // Apply current sort then render
      sortUsers(state.users, state.currentSort.field);
      renderUsers(state.users);

      // Update pagination controls
      updatePaginationControls();

    } catch (error) {
      console.error('Error loading users:', error);
      renderErrorState(error.message || translate('حدث خطأ غير متوقع', 'An unexpected error occurred'));
    }
  }

  // ============================================================================
  // Bulk Actions
  // ============================================================================

  function toggleSelectAll() {
    const selectAllCheckbox = document.getElementById('selectAll');
    const checkboxes = document.querySelectorAll('.user-checkbox');
    checkboxes.forEach(checkbox => {
      checkbox.checked = selectAllCheckbox.checked;
    });
    updateBulkActions();
  }

  function updateBulkActions() {
    const checkboxes = document.querySelectorAll('.user-checkbox:checked');
    const bulkActions = document.getElementById('bulkActions');
    const selectedCount = checkboxes.length;

    if (selectedCount > 0) {
      bulkActions.style.display = 'block';
      const deleteLbl = document.getElementById('bulkDeleteLabel');
      if (deleteLbl) {
        deleteLbl.textContent = `${translate('حذف المحدد', 'Delete selected')} (${selectedCount})`;
      }
    } else {
      bulkActions.style.display = 'none';
    }
  }

  function clearSelection() {
    document.querySelectorAll('.user-checkbox').forEach(cb => cb.checked = false);
    document.getElementById('selectAll').checked = false;
    updateBulkActions();
  }

  async function bulkDelete() {
    const checkboxes = document.querySelectorAll('.user-checkbox:checked');
    const userIds = Array.from(checkboxes).map(cb => parseInt(cb.value, 10)).filter(Boolean);

    if (userIds.length === 0) return;

    if (!confirm(translate(`هل أنت متأكد من رغبتك في حذف ${userIds.length} مستخدم؟\nهذا الإجراء لا رجعة فيه.`, `Are you sure you want to delete ${userIds.length} user(s)?\nThis action cannot be undone.`))) {
      return;
    }

    try {
      await api.post('/api/admin/users/bulk-delete', { user_ids: userIds });
      showToast(translate(`تم حذف ${userIds.length} مستخدم بنجاح`, `Successfully deleted ${userIds.length} user(s)`), 'success');
      clearSelection();
      loadUsers();
    } catch (error) {
      showToast(error.message || translate('فشل حذف المستخدمين', 'Failed to delete users'), 'error');
    }
  }

  async function bulkStatusUpdate(newStatus) {
    const checkboxes = document.querySelectorAll('.user-checkbox:checked');
    const userIds = Array.from(checkboxes).map(cb => parseInt(cb.value, 10)).filter(Boolean);

    if (userIds.length === 0) return;

    const statusText = newStatus === 'ACTIVE' ? translate('تفعيل', 'activate') :
                       newStatus === 'SUSPENDED' ? translate('تعليق', 'suspend') :
                       translate('إلغاء تفعيل', 'deactivate');

    if (!confirm(translate(`هل أنت متأكد من رغبتك في ${statusText} ${userIds.length} مستخدم؟`, `Are you sure you want to ${statusText} ${userIds.length} user(s)?`))) {
      return;
    }

    try {
      await api.post('/api/admin/users/bulk-status-update', {
        user_ids: userIds,
        new_status: newStatus
      });
      showToast(translate(`تم ${statusText} ${userIds.length} مستخدم بنجاح`, `Successfully ${statusText}d ${userIds.length} user(s)`), 'success');
      clearSelection();
      loadUsers();
    } catch (error) {
      showToast(error.message || translate(`فشل ${statusText} المستخدمين`, `Failed to ${statusText} users`), 'error');
    }
  }

  // ============================================================================
  // User Actions
  // ============================================================================

  async function handleDeleteUser(id, name) {
    if (!confirm(translate(`هل أنت متأكد من رغبتك في حذف المستخدم "${name}"؟\nهذا الإجراء لا رجعة فيه.`, `Are you sure you want to delete user "${name}"?\nThis action cannot be undone.`))) {
      return;
    }

    try {
      await api.delete(`/api/admin/users/${id}`);
      showToast(translate('تم حذف المستخدم بنجاح', 'User deleted successfully'), 'success');
      loadUsers();
    } catch (error) {
      showToast(error.message || translate('فشل حذف المستخدم', 'Failed to delete user'), 'error');
    }
  }

  // ============================================================================
  // CSV Import
  // ============================================================================

  let csvFileChangeListener = null;

  function initCSVImport() {
    const csvFile = document.getElementById('csvFile');
    if (!csvFile) return;

    // Remove old listener if exists
    if (csvFileChangeListener) {
      csvFile.removeEventListener('change', csvFileChangeListener);
    }

    csvFileChangeListener = function(event) {
      const file = event.target.files[0];
      if (!file) return;

      if (file.size > 5 * 1024 * 1024) {
        showCSVError(translate('الملف كبير جدًا (الحد الأقصى 5 ميجابايت)', 'File is too large (max 5 MB)'));
        return;
      }

      const reader = new FileReader();
      reader.onload = function(e) {
        parseCSV(e.target.result);
      };
      reader.readAsText(file);
    };

    csvFile.addEventListener('change', csvFileChangeListener);
  }

  function showImportModal() {
    const modal = new bootstrap.Modal(document.getElementById('importModal'));
    modal.show();

    // Reset modal state
    document.getElementById('csvFile').value = '';
    document.getElementById('csvPreview').innerHTML = `<p class="text-muted mb-0">${translate('اختر ملف CSV لرؤية المعاينة...', 'Choose a CSV file to see the preview...')}</p>`;
    document.getElementById('importResults').classList.add('d-none');
    document.getElementById('importBtn').disabled = true;

    // Initialize CSV import event listener
    initCSVImport();
  }

  function parseCSV(csv) {
    const lines = csv.split('\n').filter(line => line.trim());
    if (lines.length < 2) {
      showCSVError(translate('الملف يجب أن يحتوي على رأس وصف واحد على الأقل', 'File must contain a header and at least one row'));
      return;
    }

    const headers = lines[0].split(',').map(h => h.trim().toLowerCase());
    const requiredHeaders = ['username', 'email', 'password', 'role'];
    const missingHeaders = requiredHeaders.filter(h => !headers.includes(h));

    if (missingHeaders.length > 0) {
      showCSVError(translate(`الأعمدة المطلوبة مفقودة: ${missingHeaders.join(', ')}`, `Missing required columns: ${missingHeaders.join(', ')}`));
      return;
    }

    // Preview first 5 rows
    const previewRows = lines.slice(1, 6);
    let previewHTML = '<table class="table table-sm"><thead><tr>';
    headers.forEach(header => {
      previewHTML += `<th>${escapeHtml(header)}</th>`;
    });
    previewHTML += '</tr></thead><tbody>';

    previewRows.forEach(row => {
      const cells = row.split(',').map(cell => cell.trim());
      previewHTML += '<tr>';
      cells.forEach(cell => {
        previewHTML += `<td>${escapeHtml(cell)}</td>`;
      });
      previewHTML += '</tr>';
    });

    if (lines.length > 6) {
      previewHTML += `<tr><td colspan="${headers.length}" class="text-muted">... ${translate('و', 'and')} ${lines.length - 6} ${translate('صفوف أخرى', 'more rows')}</td></tr>`;
    }

    previewHTML += '</tbody></table>';
    document.getElementById('csvPreview').innerHTML = previewHTML;
    document.getElementById('importBtn').disabled = false;

    // Store parsed data
    state.csvData = lines.slice(1).map((line, index) => {
      const values = line.split(',').map(v => v.trim());
      const user = {};
      headers.forEach((header, idx) => {
        user[header] = values[idx] || '';
      });
      user._rowIndex = index + 1;
      return user;
    });
  }

  function showCSVError(message) {
    document.getElementById('csvPreview').innerHTML = `<div class="alert alert-danger">${escapeHtml(message)}</div>`;
    document.getElementById('importBtn').disabled = true;
  }

  async function performImport() {
    if (!state.csvData || state.csvData.length === 0) return;

    const btn = document.getElementById('importBtn');
    const btnText = btn.querySelector('.btn-text');
    const btnLoading = btn.querySelector('.btn-loading');

    btn.disabled = true;
    btnText.classList.add('d-none');
    btnLoading.classList.remove('d-none');

    try {
      const users = state.csvData.map(row => ({
        username: row.username,
        email: row.email,
        password: row.password,
        role: (row.role || 'PARENT').toUpperCase(),
        kindergarten_id: row.kindergarten_id ? parseInt(row.kindergarten_id, 10) : null
      }));

      const response = await api.post('/api/admin/users/bulk-create', { users: users });

      document.getElementById('importResults').classList.remove('d-none');

      const createdCount = (response.succeeded || []).length;
      if (createdCount > 0) {
        document.getElementById('importSuccess').classList.remove('d-none');
        document.getElementById('importSuccess').textContent = translate(`تم إنشاء ${createdCount} مستخدم بنجاح`, `Successfully created ${createdCount} user(s)`);
      }

      if (response.errors && response.errors.length > 0) {
        const formattedErrors = response.errors.map(error => {
          const row = error.row ? `Row ${error.row}` : translate('صف', 'Row');
          const field = error.field ? ` (${escapeHtml(error.field)})` : '';
          const message = error.message ? escapeHtml(error.message) : translate('خطأ غير معروف', 'Unknown error');
          return `${row}${field}: ${message}`;
        });
        const errEl = document.getElementById('importErrors');
        errEl.classList.remove('d-none');
        errEl.innerHTML = `<i class="bi bi-exclamation-triangle me-2"></i><strong>${translate('أخطاء:', 'Errors:')}</strong><br> - ${formattedErrors.join('<br> - ')}`;
      }

      if (createdCount > 0) loadUsers();

    } catch (error) {
      document.getElementById('importResults').classList.remove('d-none');
      document.getElementById('importErrors').classList.remove('d-none');
      document.getElementById('importErrors').innerHTML = `<i class="bi bi-exclamation-triangle me-2"></i><strong>${translate('خطأ:', 'Error:')}</strong> ${escapeHtml(error.message || translate('حدث خطأ غير متوقع', 'An unexpected error occurred'))}`;
    } finally {
      btn.disabled = false;
      btnText.classList.remove('d-none');
      btnLoading.classList.add('d-none');
    }
  }

  // ============================================================================
  // Pagination
  // ============================================================================

  function updatePaginationControls() {
    const paginationContainer = document.getElementById('pagination');
    if (!paginationContainer) return;

    if (state.pagination.totalPages <= 1) {
      paginationContainer.innerHTML = '';
      return;
    }

    let html = '<nav aria-label="' + translate('تنقل الصفحات', 'Page navigation') + '"><ul class="pagination justify-content-center mb-0">';

    // Previous
    html += `<li class="page-item${state.pagination.page <= 1 ? ' disabled' : ''}">
      <a class="page-link" href="#" onclick="AdminUsers.loadUsers(${state.pagination.page - 1}); return false;" ${state.pagination.page <= 1 ? 'tabindex="-1" aria-disabled="true"' : ''}>
        ${translate('السابق', 'Previous')}
      </a>
    </li>`;

    // Page numbers (show up to 5)
    const startPage = Math.max(1, state.pagination.page - 2);
    const endPage = Math.min(state.pagination.totalPages, startPage + 4);

    for (let i = startPage; i <= endPage; i++) {
      html += `<li class="page-item${i === state.pagination.page ? ' active' : ''}">
        <a class="page-link" href="#" onclick="AdminUsers.loadUsers(${i}); return false;" ${i === state.pagination.page ? 'aria-current="page"' : ''}>${i}</a>
      </li>`;
    }

    // Next
    html += `<li class="page-item${state.pagination.page >= state.pagination.totalPages ? ' disabled' : ''}">
      <a class="page-link" href="#" onclick="AdminUsers.loadUsers(${state.pagination.page + 1}); return false;" ${state.pagination.page >= state.pagination.totalPages ? 'tabindex="-1" aria-disabled="true"' : ''}>
        ${translate('التالي', 'Next')}
      </a>
    </li>`;

    html += '</ul></nav>';
    paginationContainer.innerHTML = html;
  }

  // ============================================================================
  // Initialization
  // ============================================================================

  function init() {
    // Get current user role from template
    const roleMeta = document.querySelector('meta[name="user-role"]');
    state.currentUserRole = roleMeta ? roleMeta.getAttribute('content') : null;

    // Load initial users
    loadUsers();

    // Setup event listeners
    const searchInput = document.getElementById('searchUser');
    const roleFilter = document.getElementById('roleFilter');
    const statusFilter = document.getElementById('statusFilter');
    const resetBtn = document.getElementById('resetFilters');
    const importBtn = document.getElementById('importBtn');

    if (searchInput) {
      searchInput.addEventListener('input', debounce(() => {
        state.filters.search = searchInput.value;
        loadUsers(1);
      }, CONFIG.DEBOUNCE_DELAY));
    }

    if (roleFilter) {
      roleFilter.addEventListener('change', () => {
        state.filters.role = roleFilter.value;
        loadUsers(1);
      });
    }

    if (statusFilter) {
      statusFilter.addEventListener('change', () => {
        state.filters.status = statusFilter.value;
        loadUsers(1);
      });
    }

    if (resetBtn) {
      resetBtn.addEventListener('click', () => {
        state.filters = { search: '', role: '', status: '' };
        if (searchInput) searchInput.value = '';
        if (roleFilter) roleFilter.value = '';
        if (statusFilter) statusFilter.value = '';
        loadUsers(1);
      });
    }

    if (importBtn) {
      importBtn.addEventListener('click', performImport);
    }

    // Table event delegation
    const tbody = document.getElementById('usersTableBody');
    if (tbody) {
      tbody.addEventListener('click', function(event) {
        const actionBtn = event.target.closest('button[data-action]');
        if (!actionBtn) return;

        const userId = parseInt(actionBtn.dataset.userId, 10);
        const username = actionBtn.dataset.username || '';
        const action = actionBtn.dataset.action;

        if (action === 'reset-password') {
          window.location.href = `/admin/users/${userId}/edit?reset_password=1`;
        } else if (action === 'delete-user') {
          handleDeleteUser(userId, username);
        }
      });
    }

    // Keyboard support for sortable headers
    document.querySelectorAll('.sortable').forEach(header => {
      header.setAttribute('tabindex', '0');
      header.setAttribute('role', 'button');
      header.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          const field = this.dataset.sort;
          sortUsers(state.users, field);
          renderUsers(state.users);
        }
      });
    });
  }

  // ============================================================================
  // Toast Helper (uses AdminComponents or fallback)
  // ============================================================================

  function showToast(message, type = 'info') {
    if (window.AdminComponents && AdminComponents.showNotification) {
      AdminComponents.showNotification({
        type: type,
        message: message,
        duration: CONFIG.TOAST_DURATION
      });
    } else if (window.showToast) {
      window.showToast(message, type);
    } else {
      // Fallback: alert
      alert(message);
    }
  }

  // ============================================================================
  // Public API
  // ============================================================================

  window.AdminUsers = {
    init,
    loadUsers,
    sortUsers,
    updateBulkActions,
    toggleSelectAll,
    clearSelection,
    bulkDelete,
    bulkStatusUpdate,
    handleDeleteUser,
    showImportModal,
    performImport,
    t,
    translate
  };

  // Auto-init on DOM ready
  document.addEventListener('DOMContentLoaded', init);

})();