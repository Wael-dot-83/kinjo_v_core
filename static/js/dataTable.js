/**
 * dataTable.js — Sortable, searchable, paginated table enhancement
 *
 * Usage: add data-datatable to a <table> element.
 * Options via data attributes on the table:
 *   data-page-size="10"   — rows per page (default 10)
 *   data-searchable="true" — whether to render a search box
 */
(function () {
    'use strict';

    const DEFAULT_PAGE_SIZE = 10;

    class DataTable {
        constructor(table) {
            this.table   = table;
            this.tbody   = table.querySelector('tbody');
            this.headers = Array.from(table.querySelectorAll('thead th'));
            this.pageSize = parseInt(table.dataset.pageSize, 10) || DEFAULT_PAGE_SIZE;
            this.searchable = table.dataset.searchable !== 'false';
            this.currentPage = 1;
            this.sortCol  = -1;
            this.sortAsc  = true;
            this.filter   = '';

            this._allRows = Array.from(this.tbody.querySelectorAll('tr'));
            this._wrap();
        }

        _wrap() {
            const wrapper = document.createElement('div');
            wrapper.className = 'datatable-wrapper';
            this.table.parentNode.insertBefore(wrapper, this.table);
            wrapper.appendChild(this.table);

            if (this.searchable) {
                const bar = document.createElement('div');
                bar.className = 'datatable-toolbar d-flex justify-content-end mb-2';
                bar.innerHTML = `<div class="input-group input-group-sm" style="max-width:240px;">
                    <span class="input-group-text"><i class="bi bi-search"></i></span>
                    <input type="search" class="form-control datatable-search" placeholder="بحث...">
                </div>`;
                wrapper.insertBefore(bar, this.table);
                bar.querySelector('.datatable-search').addEventListener('input', (e) => {
                    this.filter = e.target.value.trim().toLowerCase();
                    this.currentPage = 1;
                    this._render();
                });
            }

            const pager = document.createElement('div');
            pager.className = 'datatable-pager d-flex justify-content-between align-items-center mt-2 flex-wrap gap-2';
            wrapper.appendChild(pager);
            this._pager = pager;

            this.headers.forEach((th, i) => {
                th.style.cursor = 'pointer';
                th.style.userSelect = 'none';
                th.addEventListener('click', () => this._sort(i));
            });

            this._render();
        }

        _sort(col) {
            if (this.sortCol === col) {
                this.sortAsc = !this.sortAsc;
            } else {
                this.sortCol = col;
                this.sortAsc = true;
            }

            this.headers.forEach((th, i) => {
                th.querySelector('.sort-icon')?.remove();
                if (i === this.sortCol) {
                    const icon = document.createElement('i');
                    icon.className = 'bi ms-1 sort-icon ' + (this.sortAsc ? 'bi-caret-up-fill' : 'bi-caret-down-fill');
                    icon.style.fontSize = '0.7em';
                    th.appendChild(icon);
                }
            });

            this._allRows.sort((a, b) => {
                const va = a.cells[col]?.textContent.trim() ?? '';
                const vb = b.cells[col]?.textContent.trim() ?? '';
                const na = parseFloat(va.replace(/,/g, ''));
                const nb = parseFloat(vb.replace(/,/g, ''));
                const cmp = !isNaN(na) && !isNaN(nb) ? na - nb : va.localeCompare(vb, 'ar');
                return this.sortAsc ? cmp : -cmp;
            });

            this.currentPage = 1;
            this._render();
        }

        _filtered() {
            if (!this.filter) return this._allRows;
            return this._allRows.filter(row =>
                row.textContent.toLowerCase().includes(this.filter)
            );
        }

        _render() {
            const rows = this._filtered();
            const total = rows.length;
            const pages = Math.max(1, Math.ceil(total / this.pageSize));
            this.currentPage = Math.min(this.currentPage, pages);

            const start = (this.currentPage - 1) * this.pageSize;
            const visible = rows.slice(start, start + this.pageSize);

            this._allRows.forEach(r => { r.style.display = 'none'; });
            visible.forEach(r => { r.style.display = ''; });

            this._renderPager(pages, total, start, visible.length);
        }

        _renderPager(pages, total, start, count) {
            const p = this._pager;
            p.innerHTML = '';

            const info = document.createElement('span');
            info.style.cssText = 'font-size:0.8rem; color:var(--kinjo-text-muted);';
            info.textContent = `${start + 1}–${start + count} من ${total}`;
            p.appendChild(info);

            if (pages <= 1) return;

            const nav = document.createElement('div');
            nav.className = 'd-flex gap-1';

            const mkBtn = (label, page, disabled) => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'btn btn-sm ' + (page === this.currentPage ? 'btn-primary' : 'btn-outline-secondary');
                btn.textContent = label;
                btn.disabled = disabled;
                btn.addEventListener('click', () => { this.currentPage = page; this._render(); });
                return btn;
            };

            nav.appendChild(mkBtn('‹', this.currentPage - 1, this.currentPage === 1));

            const range = this._pageRange(pages);
            range.forEach(n => {
                if (n === '…') {
                    const el = document.createElement('span');
                    el.className = 'btn btn-sm btn-outline-secondary disabled';
                    el.textContent = '…';
                    nav.appendChild(el);
                } else {
                    nav.appendChild(mkBtn(n, n, false));
                }
            });

            nav.appendChild(mkBtn('›', this.currentPage + 1, this.currentPage === pages));
            p.appendChild(nav);
        }

        _pageRange(pages) {
            if (pages <= 7) return Array.from({ length: pages }, (_, i) => i + 1);
            const c = this.currentPage;
            const result = [1];
            if (c > 3) result.push('…');
            for (let i = Math.max(2, c - 1); i <= Math.min(pages - 1, c + 1); i++) result.push(i);
            if (c < pages - 2) result.push('…');
            result.push(pages);
            return result;
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('table[data-datatable]').forEach(t => new DataTable(t));
    });

    window.DataTable = DataTable;
})();
