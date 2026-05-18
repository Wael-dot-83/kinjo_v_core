/**
 * attendance.js — Check-in/out logic and attendance table helpers
 */
(function () {
    'use strict';

    /* ── Mark attendance via API ── */
    async function markAttendance(childId, status, btn) {
        if (!childId || !status) return;

        btn.disabled = true;
        const original = btn.innerHTML;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span>';

        try {
            const token = window.KinjoAuth?.getToken?.();
            const res = await fetch('/api/attendance', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + (token || '')
                },
                body: JSON.stringify({ child_id: childId, status: status })
            });

            if (res.ok) {
                const row = btn.closest('tr');
                if (row) updateRowStatus(row, status);
                window.showToast?.('تم تسجيل الحضور بنجاح', 'success');
            } else {
                const err = await res.json().catch(() => ({}));
                window.showToast?.(err.detail || 'حدث خطأ أثناء التسجيل', 'error');
                btn.innerHTML = original;
            }
        } catch (_) {
            window.showToast?.('تعذّر الاتصال بالخادم', 'error');
            btn.innerHTML = original;
        } finally {
            btn.disabled = false;
        }
    }

    function updateRowStatus(row, status) {
        const badge = row.querySelector('.attendance-status-badge');
        if (!badge) return;

        const map = {
            PRESENT: { label: 'حاضر', cls: 'bg-success' },
            ABSENT:  { label: 'غائب',  cls: 'bg-danger'  },
            LATE:    { label: 'متأخر', cls: 'bg-warning'  },
            EXCUSED: { label: 'معذور', cls: 'bg-info'     },
        };
        const info = map[status] || { label: status, cls: 'bg-secondary' };
        badge.className = 'badge attendance-status-badge ' + info.cls;
        badge.textContent = info.label;
    }

    /* ── Live filter ── */
    function initFilter() {
        const input = document.getElementById('attendanceFilter');
        const table = document.getElementById('attendanceTable');
        if (!input || !table) return;

        input.addEventListener('input', () => {
            const q = input.value.trim().toLowerCase();
            table.querySelectorAll('tbody tr').forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = q && !text.includes(q) ? 'none' : '';
            });
        });
    }

    /* ── Bulk check-in button ── */
    function initBulkCheckIn() {
        const btn = document.getElementById('bulkCheckInBtn');
        if (!btn) return;

        btn.addEventListener('click', async () => {
            const unchecked = document.querySelectorAll('.attendance-check:not(:checked)');
            if (!unchecked.length) {
                window.showToast?.('لا توجد سجلات لتحديثها', 'info');
                return;
            }

            btn.disabled = true;
            const ids = Array.from(unchecked).map(cb => parseInt(cb.value, 10)).filter(Boolean);

            try {
                const token = window.KinjoAuth?.getToken?.();
                const res = await fetch('/api/attendance/bulk', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + (token || '')
                    },
                    body: JSON.stringify({ child_ids: ids, status: 'PRESENT' })
                });
                if (res.ok) {
                    window.showToast?.('تم تسجيل الحضور الجماعي بنجاح', 'success');
                    setTimeout(() => location.reload(), 800);
                } else {
                    window.showToast?.('حدث خطأ', 'error');
                }
            } catch (_) {
                window.showToast?.('تعذّر الاتصال بالخادم', 'error');
            } finally {
                btn.disabled = false;
            }
        });
    }

    /* ── Expose for inline onclick handlers in templates ── */
    window.AttendanceModule = { markAttendance };

    document.addEventListener('DOMContentLoaded', () => {
        initFilter();
        initBulkCheckIn();

        /* Wire up inline action buttons */
        document.querySelectorAll('[data-attendance-action]').forEach(btn => {
            btn.addEventListener('click', () => {
                const childId = parseInt(btn.dataset.childId, 10);
                const status  = btn.dataset.attendanceAction;
                markAttendance(childId, status, btn);
            });
        });
    });
})();
