/**
 * notifications.js — Real-time notification badge polling (30s interval)
 */
(function () {
    'use strict';

    const POLL_INTERVAL = 30_000;
    let _timer = null;

    function updateBadge(count) {
        const badge = document.getElementById('notificationCount');
        if (!badge) return;
        if (count > 0) {
            badge.textContent = count > 99 ? '99+' : count;
            badge.style.display = '';
        } else {
            badge.style.display = 'none';
        }
    }

    function renderItems(items) {
        const list = document.getElementById('notificationList');
        const empty = document.getElementById('notificationEmpty');
        if (!list) return;

        if (!items || items.length === 0) {
            if (empty) empty.style.display = '';
            return;
        }

        if (empty) empty.style.display = 'none';

        const frag = document.createDocumentFragment();
        items.slice(0, 10).forEach(n => {
            const el = document.createElement('div');
            el.className = 'px-3 py-2 border-bottom' + (n.is_read ? '' : ' fw-semibold');
            el.style.cssText = 'font-size:0.825rem; cursor:pointer; transition:background 0.15s;';
            el.innerHTML = `<div style="color:var(--kinjo-text-primary);">${escapeHtml(n.title || n.message || '')}</div>
                <div style="font-size:0.75rem; color:var(--kinjo-text-muted); margin-top:2px;">${escapeHtml(n.created_at_display || '')}</div>`;
            frag.appendChild(el);
        });

        // Remove old dynamic items, keep empty placeholder
        list.querySelectorAll('.notif-item').forEach(el => el.remove());
        list.insertBefore(frag, list.firstChild);
    }

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    async function poll() {
        try {
            const token = window.KinjoAuth?.getToken?.();
            if (!token) return;
            const res = await fetch('/api/notifications/unread-count', {
                headers: { 'Authorization': 'Bearer ' + token }
            });
            if (!res.ok) return;
            const data = await res.json();
            updateBadge(data.count ?? 0);
        } catch (_) {
            // silently ignore network errors
        }
    }

    window.markAllNotificationsRead = async function () {
        try {
            const token = window.KinjoAuth?.getToken?.();
            if (!token) return;
            await fetch('/api/notifications/read-all', {
                method: 'POST',
                headers: { 'Authorization': 'Bearer ' + token }
            });
            updateBadge(0);
        } catch (_) {}
    };

    function start() {
        if (!document.getElementById('notificationCount')) return;
        poll();
        _timer = setInterval(poll, POLL_INTERVAL);
    }

    document.addEventListener('DOMContentLoaded', start);
})();
