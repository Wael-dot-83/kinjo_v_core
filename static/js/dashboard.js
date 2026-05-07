/**
 * dashboard.js — KPI loading, chart refresh, date range selection
 */
(function () {
    'use strict';

    const DEFAULT_RANGE = '30';

    /* ── Skeleton loader helpers ── */
    function showSkeleton(container) {
        container.querySelectorAll('.stat-value, .chart-placeholder').forEach(el => {
            el.classList.add('skeleton-loading');
        });
    }

    function hideSkeleton(container) {
        container.querySelectorAll('.skeleton-loading').forEach(el => {
            el.classList.remove('skeleton-loading');
        });
    }

    /* ── Stat card animation ── */
    function animateCount(el, target) {
        const duration = 900;
        const start = performance.now();
        const from = parseInt(el.textContent.replace(/\D/g, ''), 10) || 0;

        function step(now) {
            const elapsed = Math.min((now - start) / duration, 1);
            const eased = 1 - Math.pow(1 - elapsed, 3);
            el.textContent = Math.round(from + (target - from) * eased).toLocaleString();
            if (elapsed < 1) requestAnimationFrame(step);
        }

        requestAnimationFrame(step);
    }

    /* ── Load KPI data ── */
    async function loadKPIs(days) {
        const board = document.getElementById('kpi-board');
        if (!board) return;

        showSkeleton(board);
        try {
            const token = window.KinjoAuth?.getToken?.();
            const headers = token ? { 'Authorization': 'Bearer ' + token } : {};
            const res = await fetch('/api/kpi/summary?days=' + days, { headers });
            if (!res.ok) return;
            const data = await res.json();

            Object.entries(data).forEach(([key, value]) => {
                const el = board.querySelector('[data-kpi="' + key + '"]');
                if (el && typeof value === 'number') animateCount(el, value);
                else if (el) el.textContent = value;
            });
        } catch (_) {
        } finally {
            hideSkeleton(board);
        }
    }

    /* ── Date range selector ── */
    function initDateRange() {
        const selector = document.getElementById('dateRangeSelector');
        if (!selector) return;

        selector.value = DEFAULT_RANGE;
        selector.addEventListener('change', () => loadKPIs(selector.value));
    }

    /* ── Refresh button ── */
    function initRefresh() {
        const btn = document.getElementById('dashboardRefreshBtn');
        if (!btn) return;

        btn.addEventListener('click', async () => {
            btn.disabled = true;
            btn.querySelector('i')?.classList.add('spin');
            const days = document.getElementById('dateRangeSelector')?.value || DEFAULT_RANGE;
            await loadKPIs(days);
            btn.disabled = false;
            btn.querySelector('i')?.classList.remove('spin');
        });
    }

    /* ── Mini trend sparkline ── */
    window.renderSparkline = function (canvasId, values, color) {
        const canvas = document.getElementById(canvasId);
        if (!canvas || !window.Chart) return;

        new Chart(canvas, {
            type: 'line',
            data: {
                labels: values.map((_, i) => i),
                datasets: [{
                    data: values,
                    borderColor: color || 'var(--kinjo-primary)',
                    borderWidth: 2,
                    fill: true,
                    backgroundColor: (ctx) => {
                        const g = ctx.chart.ctx.createLinearGradient(0, 0, 0, 50);
                        g.addColorStop(0, (color || '#0A5C8E') + '40');
                        g.addColorStop(1, (color || '#0A5C8E') + '00');
                        return g;
                    },
                    tension: 0.4,
                    pointRadius: 0,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: { enabled: false } },
                scales: { x: { display: false }, y: { display: false } },
                animation: { duration: 600 }
            }
        });
    };

    /* ── CSS spin keyframe (injected once) ── */
    if (!document.getElementById('dashboard-spin-style')) {
        const style = document.createElement('style');
        style.id = 'dashboard-spin-style';
        style.textContent = '@keyframes spin{to{transform:rotate(360deg)}} .spin{animation:spin 0.8s linear infinite; display:inline-block;}';
        document.head.appendChild(style);
    }

    document.addEventListener('DOMContentLoaded', () => {
        initDateRange();
        initRefresh();
        loadKPIs(DEFAULT_RANGE);
    });
})();
