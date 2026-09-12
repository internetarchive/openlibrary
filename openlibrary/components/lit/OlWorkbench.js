import { LitElement, html, css, nothing } from 'lit';
import { translate } from './utils/labels.js';
import { DEFAULT_LABELS, labelsFromElement } from './workbench-labels.js';
import { api, olid, normalizeKey, keyType } from '../../plugins/openlibrary/js/librarians/api.js';
import './OLButton.js';
import './OlIcon.js';
import './OlWorkbenchGrid.js';
import './OlRecordPanel.js';
import './OlWorkbenchActionForm.js';
import './OlBatchPreview.js';
import { showToast } from './OlToastRegion.js';

const TYPES = ['edition', 'work', 'author'];
const TYPE_LABEL = { edition: 'editions', work: 'works', author: 'authors' };
const MAX_OPEN = 20;

/**
 * The librarian workbench: worklists on the left, a query bar and a dense
 * grid in the middle, a record panel on the right, and every write routed
 * through the batch preview dialog.
 *
 * Owns all page state (query, selection, focus, staged edits) and mirrors
 * the query into the URL so a worklist view is a link.
 *
 * @element ol-workbench
 *
 * @prop {String} username - The signed-in librarian
 * @prop {Boolean} canApply - Whether the viewer is a super-librarian
 */
export class OlWorkbench extends LitElement {
    static properties = {
        username: { type: String },
        canApply: { type: Boolean, attribute: 'can-apply' },
        _tab: { state: true },
        _type: { state: true },
        _q: { state: true },
        _filters: { state: true },
        _sort: { state: true },
        _page: { state: true },
        _rows: { state: true },
        _result: { state: true },
        _busy: { state: true },
        _error: { state: true },
        _config: { state: true },
        _worklists: { state: true },
        _activeWorklist: { state: true },
        _selected: { state: true },
        _focusKey: { state: true },
        _panelKey: { state: true },
        _pending: { state: true },
        _batches: { state: true },
        _batchesMine: { state: true },
        _pasteOpen: { state: true },
        _touched: { state: true },
    };

    static styles = css`
        :host { display: block; font-family: var(--font-family-body); font-size: var(--font-size-body-medium); color: var(--color-text); background: var(--color-surface); }
        * { box-sizing: border-box; }
        a { color: var(--color-link); }
        .masthead { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--spacing-2xl); padding: 0 var(--spacing-2xl); border-bottom: var(--border-width) solid var(--color-border-muted); }
        .masthead .l { display: flex; align-items: flex-end; gap: var(--spacing-2xl); }
        h1 { margin: 0; padding: var(--spacing-md) 0 var(--spacing-sm); font-family: var(--font-family-title); font-size: var(--font-size-title-large); font-weight: var(--font-weight-semibold); line-height: var(--line-height-tight); color: var(--color-text-heading); }
        .tabs { display: flex; gap: var(--spacing-xl); }
        .tab { height: 40px; display: inline-flex; align-items: center; gap: var(--spacing-xs); padding: 0 2px; background: none; border: 0; border-bottom: 2px solid transparent; font: inherit; font-weight: var(--font-weight-medium); color: var(--color-text-secondary); cursor: pointer; }
        .tab[aria-selected="true"] { color: var(--color-link); border-bottom-color: var(--color-primary); }
        .tab:focus-visible { outline: 2px solid var(--color-border-focused); outline-offset: -2px; }
        .badge { display: inline-flex; align-items: center; height: 18px; padding: 0 6px; border-radius: 9px; background: var(--color-primary); color: var(--color-text-inverse); font-size: var(--font-size-label-small); font-weight: var(--font-weight-semibold); }
        .masthead .r { display: flex; gap: var(--spacing-sm); padding-bottom: var(--spacing-sm); }
        .body { display: grid; grid-template-columns: 248px minmax(0, 1fr); min-height: calc(100vh - 180px); }
        .body[data-panel] { grid-template-columns: 200px minmax(0, 1fr) 400px; }
        @media (max-width: 1100px) { .body, .body[data-panel] { grid-template-columns: minmax(0, 1fr); } .rail { display: none; } }
        .rail { border-right: var(--border-width) solid var(--color-border-muted); background: var(--color-surface-sunken); padding: var(--spacing-md) var(--spacing-sm); display: flex; flex-direction: column; gap: 2px; overflow: hidden; }
        .section { font-size: var(--font-size-label-small); font-weight: var(--font-weight-semibold); letter-spacing: 0.06em; text-transform: uppercase; color: var(--color-text-secondary); padding: 0 var(--spacing-md); margin: var(--spacing-md) 0 var(--spacing-xs); }
        .wl { display: flex; align-items: center; justify-content: space-between; gap: var(--spacing-sm); min-height: 30px; padding: 0 var(--spacing-md); border-radius: var(--border-radius-md); border: 0; background: none; font: inherit; font-size: var(--font-size-body-small); color: var(--color-text); text-align: left; cursor: pointer; width: 100%; }
        .wl:hover { background: var(--color-surface); }
        .wl[aria-current="true"] { background: var(--color-primary-subtle); color: var(--color-link); font-weight: var(--font-weight-semibold); }
        .wl .n { font-size: var(--font-size-label-medium); color: var(--color-text-muted); font-variant-numeric: tabular-nums; font-weight: var(--font-weight-regular); }
        .wl[aria-current="true"] .n { color: var(--color-link); }
        .wl span:first-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .rail .note { margin-top: auto; padding: var(--spacing-md); border-top: var(--border-width) solid var(--color-border-muted); font-size: var(--font-size-label-medium); color: var(--color-text-muted); }
        .main { display: flex; flex-direction: column; min-width: 0; border-right: var(--border-width) solid var(--color-border-muted); }
        .query { padding: var(--spacing-md) var(--spacing-xl) var(--spacing-sm); border-bottom: var(--border-width) solid var(--color-border-muted); display: grid; gap: var(--spacing-sm); }
        .qrow { display: flex; align-items: center; gap: var(--spacing-sm); }
        .types { display: inline-flex; height: var(--control-height-medium); border: var(--border-width) solid var(--color-border); border-radius: var(--border-radius-button); overflow: hidden; }
        .types button { padding: 0 var(--spacing-md); border: 0; border-right: var(--border-width) solid var(--color-border); background: var(--color-surface); font: inherit; font-size: var(--font-size-label-large); font-weight: var(--font-weight-medium); color: var(--color-text-secondary); cursor: pointer; }
        .types button:last-child { border-right: 0; }
        .types button[aria-pressed="true"] { background: var(--color-primary-subtle); color: var(--color-link); }
        .types button:focus-visible { outline: 2px solid var(--color-border-focused); outline-offset: -2px; }
        .qinput { flex: 1; height: var(--control-height-medium); padding: 0 var(--spacing-sm); font-family: var(--font-family-mono); font-size: var(--font-size-label-medium); border: var(--border-width) solid var(--color-border); border-radius: var(--border-radius-input); background: var(--color-surface); color: var(--color-text); }
        .qinput:focus-visible { outline: 2px solid var(--color-border-focused); outline-offset: 1px; }
        .frow { display: flex; align-items: center; gap: var(--spacing-sm); flex-wrap: wrap; }
        .filter { display: inline-flex; align-items: center; gap: var(--spacing-xs); height: 26px; padding: 0 var(--spacing-xs) 0 var(--spacing-md); border-radius: 13px; background: var(--color-surface); border: var(--border-width) solid var(--color-border); font-size: var(--font-size-label-medium); }
        .filter b { font-weight: var(--font-weight-semibold); }
        .filter .page { color: var(--color-text-muted); }
        .filter button { display: inline-flex; border: 0; background: none; padding: 2px; color: var(--color-text-muted); cursor: pointer; border-radius: 50%; }
        .filter button:hover { color: var(--color-text); background: var(--color-surface-sunken); }
        .filter input { width: 90px; height: 20px; border: 0; border-bottom: 1px solid var(--color-border); font: inherit; font-size: var(--font-size-label-medium); background: transparent; color: var(--color-text); }
        .filter input:focus-visible { outline: none; border-bottom-color: var(--color-border-focused); }
        select.add { height: 26px; border-radius: 13px; border: var(--border-width) dashed var(--color-border); background: var(--color-surface); font: inherit; font-size: var(--font-size-label-medium); color: var(--color-text-secondary); padding: 0 var(--spacing-sm); }
        .sp { flex: 1; }
        .count { font-size: var(--font-size-body-small); color: var(--color-text-secondary); white-space: nowrap; }
        .count b { color: var(--color-text); font-weight: var(--font-weight-semibold); font-variant-numeric: tabular-nums; }
        select.sort { height: 26px; border: 0; background: transparent; font: inherit; font-size: var(--font-size-body-small); color: var(--color-text-secondary); }
        .grid { flex: 1; min-height: 240px; }
        .pager { position: sticky; bottom: 0; z-index: 2; background: var(--color-surface); display: flex; align-items: center; gap: var(--spacing-sm); padding: var(--spacing-xs) var(--spacing-xl); border-top: var(--border-width) solid var(--color-border-muted); font-size: var(--font-size-label-medium); color: var(--color-text-secondary); }
        .bar { position: sticky; bottom: 0; z-index: 2; border-top: var(--border-width) solid var(--color-border-muted); background: var(--color-surface-sunken); padding: var(--spacing-sm) var(--spacing-xl); display: flex; align-items: center; gap: var(--spacing-sm); flex-wrap: wrap; }
        .bar.pending { background: var(--color-warning-bg); border-top-color: var(--color-warning-border); }
        .bar b { font-size: var(--font-size-body-small); font-weight: var(--font-weight-semibold); }
        .bar .hint { font-size: var(--font-size-label-medium); color: var(--color-text-secondary); }
        .bar .keys { display: inline-flex; gap: 4px; align-items: center; font-size: var(--font-size-label-small); color: var(--color-text-muted); }
        .panel { position: sticky; top: 0; height: 100vh; min-height: 0; overflow: hidden; }
        @media (max-width: 1100px) { .panel { position: fixed; inset: auto 0 0 0; height: 60vh; z-index: var(--z-index-level-3, 30); box-shadow: 0 -8px 24px rgba(0,0,0,.15); } }
        .error { padding: var(--spacing-sm) var(--spacing-xl); color: var(--color-error-fg); background: var(--color-error-bg); border-bottom: var(--border-width) solid var(--color-error-border); }
        .paste { display: grid; gap: var(--spacing-xs); padding: var(--spacing-sm) var(--spacing-xl); border-bottom: var(--border-width) solid var(--color-border-muted); background: var(--color-surface-sunken); }
        .paste textarea { width: 100%; min-height: 60px; font: inherit; font-size: var(--font-size-label-medium); font-family: var(--font-family-mono); padding: var(--spacing-xs); border: var(--border-width) solid var(--color-border); border-radius: var(--border-radius-input); }
        .paste .acts { display: flex; gap: var(--spacing-xs); }
        table.batches { width: 100%; border-collapse: collapse; font-size: var(--font-size-body-small); }
        table.batches th, table.batches td { text-align: left; padding: var(--spacing-xs) var(--spacing-md); border-bottom: var(--border-width) solid var(--color-border-subtle); vertical-align: top; }
        table.batches th { font-size: var(--font-size-label-small); text-transform: uppercase; letter-spacing: 0.04em; color: var(--color-text-secondary); }
        .status { display: inline-block; padding: 0 var(--spacing-xs); border-radius: var(--border-radius-sm); background: var(--color-surface-sunken); font-size: var(--font-size-label-small); font-weight: var(--font-weight-semibold); text-transform: capitalize; }
        .status[data-s="applied"] { background: var(--color-success-bg); color: var(--color-success-fg); }
        .status[data-s="requested"] { background: var(--color-info-bg); color: var(--color-info-fg); }
        .status[data-s="declined"], .status[data-s="failed"] { background: var(--color-error-bg); color: var(--color-error-fg); }
        .bacts { display: flex; gap: var(--spacing-2xs); }
        .batches-wrap { padding: var(--spacing-md) var(--spacing-xl); }
        .batches-wrap .top { display: flex; gap: var(--spacing-sm); align-items: center; margin-bottom: var(--spacing-sm); }
        .muted { color: var(--color-text-muted); }
    `;

    constructor() {
        super();
        this.username = '';
        this.canApply = false;
        this.labels = {};
        this._tab = 'records';
        this._type = 'edition';
        this._q = '';
        this._filters = [];
        this._sort = 'relevance';
        this._page = 1;
        this._rows = 50;
        this._result = null;
        this._busy = false;
        this._error = null;
        this._config = null;
        this._worklists = [];
        this._activeWorklist = null;
        this._selected = new Set();
        this._focusKey = '';
        this._panelKey = '';
        this._pending = {};
        this._batches = null;
        this._batchesMine = true;
        this._pasteOpen = false;
        this._touched = new Set();
        this._anchorKey = null;
        this._onKey = this.onKey.bind(this);
        this._onPop = () => { this.readUrl(); this.run(); };
    }

    t(key, vars) {
        return translate(this.labels, DEFAULT_LABELS, key, vars);
    }

    connectedCallback() {
        super.connectedCallback();
        this.labels = labelsFromElement(this);
        document.addEventListener('keydown', this._onKey);
        window.addEventListener('popstate', this._onPop);
        this.boot();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('keydown', this._onKey);
        window.removeEventListener('popstate', this._onPop);
    }

    async boot() {
        this.readUrl();
        try {
            const [config, wl] = await Promise.all([api.config(), api.worklists(true)]);
            this._config = config;
            this._worklists = wl.worklists;
            if (this._activeWorklist) {
                const w = this._worklists.find((x) => x.id === this._activeWorklist);
                if (w) this.applyWorklist(w, false);
            }
        } catch (e) {
            this._error = this.t('error', { error: e.message });
        }
        await this.run();
    }

    // ── URL state ────────────────────────────────────────────────

    readUrl() {
        const p = new URLSearchParams(location.search);
        this._type = TYPES.includes(p.get('type')) ? p.get('type') : 'edition';
        this._q = p.get('q') || '';
        this._sort = p.get('sort') || 'relevance';
        this._page = Number(p.get('page') || 1) || 1;
        this._activeWorklist = p.get('wl') || null;
        this._tab = p.get('tab') === 'batches' ? 'batches' : 'records';
        try { this._filters = p.get('filters') ? JSON.parse(p.get('filters')) : []; } catch { this._filters = []; }
    }

    writeUrl() {
        const p = new URLSearchParams();
        if (this._tab === 'batches') p.set('tab', 'batches');
        p.set('type', this._type);
        if (this._q) p.set('q', this._q);
        if (this._filters.length) p.set('filters', JSON.stringify(this._filters));
        if (this._sort !== 'relevance') p.set('sort', this._sort);
        if (this._page > 1) p.set('page', String(this._page));
        if (this._activeWorklist) p.set('wl', this._activeWorklist);
        history.replaceState(null, '', `${location.pathname}?${p}`);
    }

    // ── Query ────────────────────────────────────────────────────

    async run() {
        this.writeUrl();
        if (this._tab !== 'records') return;
        this._busy = true;
        this._error = null;
        try {
            this._result = await api.query({ type: this._type, q: this._q, filters: this._filters, sort: this._sort, page: this._page, rows: this._rows });
            this._focusKey = this._result.records.find((r) => r.key === this._focusKey)?.key || '';
        } catch (e) {
            this._error = this.t('error', { error: e.message });
        } finally {
            this._busy = false;
        }
    }

    setType(t) {
        if (t === this._type) return;
        this._type = t;
        this._filters = this._filters.filter((f) => this.filterSpec(f.id)?.types.includes(t));
        if (!this.sorts.includes(this._sort)) this._sort = 'relevance';
        this._page = 1;
        this._activeWorklist = null;
        this._selected = new Set();
        this._panelKey = '';
        this.run();
    }

    submitQuery(e) {
        e?.preventDefault();
        this._q = this.renderRoot.querySelector('.qinput')?.value || '';
        this._page = 1;
        this._activeWorklist = null;
        this.run();
    }

    filterSpec(id) {
        return this._config?.filters?.find((f) => f.id === id);
    }

    get availableFilters() {
        return (this._config?.filters || []).filter((f) => f.types.includes(this._type) && !this._filters.some((x) => x.id === f.id));
    }

    get sorts() {
        return this._config?.sorts?.[this._type] || ['relevance'];
    }

    addFilter(id) {
        if (!id) return;
        const spec = this.filterSpec(id);
        const f = { id };
        if (spec?.value === 'range') f.value = { from: '', to: '' };
        else if (spec?.value) f.value = spec.options?.[0] || '';
        this._filters = [...this._filters, f];
        this._page = 1;
        this._activeWorklist = null;
        if (!spec?.value) this.run();
    }

    setFilterValue(idx, value) {
        const next = this._filters.map((f, i) => (i === idx ? { ...f, value } : f));
        this._filters = next;
        this._page = 1;
        this._activeWorklist = null;
        this.run();
    }

    removeFilter(idx) {
        this._filters = this._filters.filter((_, i) => i !== idx);
        this._page = 1;
        this._activeWorklist = null;
        this.run();
    }

    setSort(s) {
        this._sort = s;
        this._page = 1;
        this.run();
    }

    setPage(n) {
        this._page = Math.max(1, n);
        this.run();
        this.renderRoot.querySelector('.grid')?.scrollTo(0, 0);
    }

    // ── Worklists ────────────────────────────────────────────────

    applyWorklist(w, andRun = true) {
        this._type = w.type;
        this._q = w.q || '';
        this._filters = [...(w.filters || [])];
        this._sort = w.sort || 'relevance';
        this._page = 1;
        this._activeWorklist = w.id;
        this._selected = new Set();
        this._panelKey = '';
        if (andRun) this.run();
    }

    async saveWorklist() {
        const name = window.prompt(this.t('worklistName'));
        if (!name) return;
        try {
            const w = await api.createWorklist({ name, type: this._type, q: this._q, filters: this._filters, sort: this._sort });
            this._worklists = [...this._worklists, { ...w, count: this._result?.num_found ?? null }];
            this._activeWorklist = w.id;
            this.writeUrl();
        } catch (e) {
            showToast(this.t('error', { error: e.message }), { variant: 'error' });
        }
    }

    async deleteWorklist(w) {
        if (!window.confirm(this.t('deleteWorklistConfirm'))) return;
        try {
            await api.deleteWorklist(w.id);
            this._worklists = this._worklists.filter((x) => x.id !== w.id);
            if (this._activeWorklist === w.id) this._activeWorklist = null;
        } catch (e) {
            showToast(this.t('error', { error: e.message }), { variant: 'error' });
        }
    }

    async loadPasted() {
        const raw = this.renderRoot.querySelector('.paste textarea')?.value || '';
        const keys = raw.split(/[\s,]+/).map((s) => normalizeKey(s)).filter(Boolean);
        if (!keys.length) return;
        const type = keyType(keys[0]);
        this._type = type;
        this._activeWorklist = null;
        this._busy = true;
        try {
            const r = await api.keys(keys.filter((k) => keyType(k) === type));
            this._result = { type, records: r.groups[type] || [], num_found: (r.groups[type] || []).length, page: 1, rows: this._rows, page_filters: [] };
            this._q = '';
            this._filters = [];
            this._pasteOpen = false;
            this.writeUrl();
        } catch (e) {
            this._error = this.t('error', { error: e.message });
        } finally {
            this._busy = false;
        }
    }

    // ── Selection and focus ──────────────────────────────────────

    get records() {
        return this._result?.records || [];
    }

    toggle(key, shift = false) {
        const next = new Set(this._selected);
        const keys = this.records.map((r) => r.key);
        if (shift && this._anchorKey && keys.includes(this._anchorKey) && keys.includes(key)) {
            const [a, b] = [keys.indexOf(this._anchorKey), keys.indexOf(key)].sort((x, y) => x - y);
            const on = !next.has(key);
            for (const k of keys.slice(a, b + 1)) { if (on) next.add(k); else next.delete(k); }
        } else if (next.has(key)) {
            next.delete(key);
        } else {
            next.add(key);
        }
        this._anchorKey = key;
        this._selected = next;
    }

    selectPage() {
        const next = new Set(this._selected);
        for (const r of this.records) next.add(r.key);
        this._selected = next;
    }

    clearSelection() {
        this._selected = new Set();
    }

    get selectedRecords() {
        const byKey = new Map(this.records.map((r) => [r.key, r]));
        return [...this._selected].map((k) => byKey.get(k) || this._selectedCache?.get(k)).filter(Boolean);
    }

    updated(changed) {
        // Keep hydrated rows for keys selected on earlier pages so actions can list them.
        if (changed.has('_result') || changed.has('_selected')) {
            this._selectedCache = this._selectedCache || new Map();
            for (const r of this.records) if (this._selected.has(r.key)) this._selectedCache.set(r.key, r);
            for (const k of [...this._selectedCache.keys()]) if (!this._selected.has(k)) this._selectedCache.delete(k);
        }
    }

    openPanel(key) {
        this._panelKey = key;
        this._focusKey = key;
    }

    navPanel(dir) {
        const keys = this.records.map((r) => r.key);
        const i = keys.indexOf(this._panelKey || this._focusKey);
        const next = keys[Math.min(keys.length - 1, Math.max(0, i + dir))];
        if (next) this.openPanel(next);
    }

    onKey(e) {
        if (this._tab !== 'records') return;
        const path = e.composedPath();
        if (path.some((el) => el.tagName && /^(INPUT|TEXTAREA|SELECT|OL-DIALOG|OL-AUTOCOMPLETE|OL-BATCH-PREVIEW|OL-WORKBENCH-ACTION-FORM)$/.test(el.tagName)) || e.metaKey || e.ctrlKey || e.altKey) return;
        const keys = this.records.map((r) => r.key);
        if (!keys.length) return;
        const i = keys.indexOf(this._focusKey);
        if (e.key === 'j' || e.key === 'k') {
            const n = e.key === 'j' ? Math.min(keys.length - 1, i + 1) : Math.max(0, i - 1);
            this._focusKey = keys[n];
            if (this._panelKey) this._panelKey = keys[n];
            this.renderRoot.querySelector('ol-workbench-grid')?.shadowRoot?.querySelector('tr[data-focus]')?.scrollIntoView({ block: 'nearest' });
            e.preventDefault();
        } else if ((e.key === 'x' || e.key === 'X') && this._focusKey) {
            this.toggle(this._focusKey, e.shiftKey);
            e.preventDefault();
        } else if (e.key === 'a') {
            this.selectPage();
            e.preventDefault();
        } else if (e.key === 'Enter' && this._focusKey) {
            this.openPanel(this._focusKey);
            e.preventDefault();
        } else if (e.key === 'Escape' && this._panelKey) {
            this._panelKey = '';
        }
    }

    // ── Actions ──────────────────────────────────────────────────

    get actions() {
        const sel = this.selectedRecords;
        const types = new Set(sel.map((r) => r.type));
        const n = sel.length;
        const only = (t) => n > 0 && types.size === 1 && types.has(t);
        const max = this._config?.max_batch || 200;
        const tooMany = n > max;
        const gate = (ok, reason) => (tooMany ? this.t('tooMany', { max }) : ok ? '' : reason);
        const list = [
            { id: 'set_author', label: 'setAuthor', reason: gate(n > 0 && !types.has('author'), this.t('needsWorks')) },
            { id: 'move_editions', label: 'moveEditions', reason: gate(only('edition'), this.t('needsEditions')) },
            { id: 'tag', label: 'manageSubjects', reason: gate(n > 0 && !types.has('author'), this.t('needsWorks')) },
            { id: 'set_field', label: 'setField', reason: gate(n > 0 && types.size === 1 && !types.has('author'), this.t('needsEditions')) },
            { id: 'merge_editions', label: 'mergeEditions', reason: gate(only('edition') && n >= 2, this.t('needsTwo')) },
            { id: 'merge_works', label: 'mergeWorks', reason: gate(only('work') && n >= 2, this.t('needsTwo')) },
            { id: 'merge_authors', label: 'mergeAuthors', reason: gate(only('author') && n >= 2, this.t('needsTwo')) },
            { id: 'add_to_list', label: 'addToList', reason: gate(n > 0, '') },
            { id: 'flag', label: 'flag', reason: gate(n > 0, '') },
            { id: 'delete', label: 'deleteRecords', reason: this.canApply ? gate(n > 0, '') : this.t('superOnly') },
        ];
        return list;
    }

    async openAction(id) {
        const records = this.selectedRecords;
        if (id === 'merge_works' || id === 'merge_authors') {
            const page = id === 'merge_works' ? '/works/merge' : '/authors/merge';
            const href = `${page}?records=${records.map((r) => olid(r.key)).join(',')}`;
            this.preview.show({ mode: 'checks', action: id, items: records.map((r) => ({ key: r.key })), records, href, title: this.t(id === 'merge_works' ? 'mergeWorks' : 'mergeAuthors') });
            return;
        }
        this.form.show({ kind: id, records });
    }

    get preview() {
        return this.renderRoot.querySelector('ol-batch-preview');
    }

    get form() {
        return this.renderRoot.querySelector('ol-workbench-action-form');
    }

    onActionSubmit(e) {
        const { action, params, title } = e.detail;
        const records = this._actionRecords || this.selectedRecords;
        this._actionRecords = null;
        this.preview.show({ action, items: records.map((r) => ({ key: r.key, expected_revision: r.revision ?? null })), params, records, title });
    }

    onPanelAction(e) {
        const { action, keys, params, title } = e.detail;
        const records = keys.map((k) => this.records.find((r) => r.key === k)).filter(Boolean);
        if (action === 'move_editions' && params.target !== 'new') {
            this._actionRecords = records;
            this.form.show({ kind: 'move_editions', records });
            return;
        }
        this.preview.show({ action, items: records.map((r) => ({ key: r.key, expected_revision: r.revision ?? null })), params, records, title });
    }

    async onActionList(e) {
        const records = this.selectedRecords;
        const m = String(e.detail.listKey).match(/OL\d+L/);
        if (!m) return;
        try {
            await api.addSeeds(this.username, m[0], records.map((r) => r.key));
            showToast(this.t('added', { count: records.length }), { variant: 'success' });
        } catch (err) {
            showToast(this.t('error', { error: err.message }), { variant: 'error' });
        }
    }

    onBatchApplied(e) {
        const keys = new Set(e.detail.keys || []);
        this._touched = new Set([...this._touched, ...keys]);
        if (this._result) {
            this._result = { ...this._result, records: this._result.records.map((r) => (keys.has(r.key) ? { ...r, touched: true } : r)) };
        }
        for (const k of keys) delete this._pending[k];
        this._pending = { ...this._pending };
        if (e.detail.status === 'applied') {
            this.clearSelection();
            this.renderRoot.querySelector('ol-record-panel')?.refresh();
            // Re-fetch so revisions and chips are current; Solr may lag, the rows keep their tint.
            setTimeout(() => this.run(), 800);
        }
        if (this._tab === 'batches') this.loadBatches();
    }

    // ── Pending field edits ──────────────────────────────────────

    onPanelEdit(e) {
        const { key, field, value } = e.detail;
        const cur = { ...(this._pending[key] || {}) };
        if (value === null) delete cur[field]; else cur[field] = value;
        const next = { ...this._pending };
        if (Object.keys(cur).length) next[key] = cur; else delete next[key];
        this._pending = next;
    }

    get pendingCount() {
        return Object.values(this._pending).reduce((n, f) => n + Object.keys(f).length, 0);
    }

    /** Group staged edits by (field, value) so each becomes one set_field batch. */
    get pendingGroups() {
        const groups = new Map();
        for (const [key, fields] of Object.entries(this._pending)) {
            for (const [field, value] of Object.entries(fields)) {
                const id = `${field} ${JSON.stringify(value)}`;
                if (!groups.has(id)) groups.set(id, { field, value, keys: [] });
                groups.get(id).keys.push(key);
            }
        }
        return [...groups.values()];
    }

    previewPending() {
        const groups = this.pendingGroups;
        if (!groups.length) return;
        const [g, ...rest] = groups;
        const records = g.keys.map((k) => this.records.find((r) => r.key === k) || { key: k, type: this._type, title: olid(k) });
        const kind = this._config?.settable_fields?.[this._type]?.[g.field];
        this.preview.show({
            action: 'set_field',
            items: records.map((r) => ({ key: r.key, expected_revision: r.revision ?? null })),
            params: { field: g.field, value: kind === 'int' ? Number(g.value) : g.value, mode: 'set' },
            records,
            title: `${this.t('setField').replace(/…$/, '')}: ${g.field.replace(/_/g, ' ')}`,
        });
        this._pendingQueue = rest.length;
    }

    discardPending() {
        this._pending = {};
    }

    // ── Batches tab ──────────────────────────────────────────────

    async loadBatches() {
        try {
            const r = await api.batches({ mine: this._batchesMine, limit: 50 });
            this._batches = r.batches;
        } catch (e) {
            this._error = this.t('error', { error: e.message });
        }
    }

    setTab(tab) {
        this._tab = tab;
        this.writeUrl();
        if (tab === 'batches') this.loadBatches();
    }

    async batchDo(b, what, force = false) {
        try {
            if (what === 'apply') await api.batchApply(b.id, null, []);
            else if (what === 'decline') await api.batchDecline(b.id, null);
            else if (what === 'revert') await api.batchRevert(b.id, null, force);
            await this.loadBatches();
        } catch (e) {
            if (what === 'revert' && e.status === 409 && e.detail?.moved && window.confirm(`${this.t('revertMoved')} ${this.t('forceRevert')}?`)) {
                return this.batchDo(b, 'revert', true);
            }
            if (what === 'apply' && e.status === 409 && e.detail?.warnings) {
                const blocks = e.detail.warnings.filter((w) => w.level === 'block');
                if (blocks.length && window.confirm(`${blocks.map((w) => w.text).join('\n')}\n\n${this.t('override')}?`)) {
                    try {
                        await api.batchApply(b.id, null, blocks.map((w) => w.code));
                        await this.loadBatches();
                        return;
                    } catch (err) {
                        showToast(this.t('error', { error: err.message }), { variant: 'error' });
                        return;
                    }
                }
            }
            showToast(this.t('error', { error: e.message }), { variant: 'error' });
        }
    }

    // ── Render ───────────────────────────────────────────────────

    renderRail() {
        const builtin = this._worklists.filter((w) => w.builtin && w.type === this._type);
        const mine = this._worklists.filter((w) => !w.builtin);
        const row = (w) => html`
            <button class="wl" aria-current=${this._activeWorklist === w.id ? 'true' : 'false'} @click=${() => this.applyWorklist(w)} title=${w.q || ''}>
                <span>${w.name}</span>
                <span class="n">${w.count ?? ''}</span>
            </button>`;
        return html`
            <nav class="rail" aria-label=${this.t('worklists')}>
                <div class="section" style="margin-top:0">${this.t('worklists')} · ${this.t(TYPE_LABEL[this._type])}</div>
                ${builtin.map(row)}
                ${mine.length ? html`<div class="section">${this.t('mine')}</div>${mine.map((w) => html`<div style="display:flex;align-items:center;gap:2px">${row(w)}${w.owner === this.username || this.canApply ? html`<ol-button size="x-small" variant="ghost" shape="icon" aria-label=${this.t('delete')} @click=${() => this.deleteWorklist(w)}><ol-icon name="trash" size="sm"></ol-icon></ol-button>` : nothing}</div>`)}` : nothing}
                <button class="wl" style="color: var(--color-link)" @click=${this.saveWorklist}><span><ol-icon name="plus" size="sm"></ol-icon> ${this.t('saveWorklist')}</span></button>
                <div class="note">${this.t('pageFilterNote')}</div>
            </nav>`;
    }

    renderFilter(f, idx) {
        const spec = this.filterSpec(f.id) || { label: f.id };
        let control = nothing;
        if (spec.value === 'range') {
            control = html`<input type="number" placeholder=${this.t('from')} .value=${f.value?.from ?? ''} @change=${(e) => this.setFilterValue(idx, { ...f.value, from: e.target.value })}>–<input type="number" placeholder=${this.t('to')} .value=${f.value?.to ?? ''} @change=${(e) => this.setFilterValue(idx, { ...f.value, to: e.target.value })}>`;
        } else if (spec.value === 'enum') {
            control = html`<select @change=${(e) => this.setFilterValue(idx, e.target.value)}>${spec.options.map((o) => html`<option value=${o} ?selected=${f.value === o}>${o}</option>`)}</select>`;
        } else if (spec.value) {
            control = html`<input type=${spec.value === 'int' ? 'number' : 'text'} placeholder=${this.t('filterValue')} .value=${f.value ?? ''} @change=${(e) => this.setFilterValue(idx, e.target.value)}>`;
        }
        return html`
            <span class="filter">
                <b>${spec.label}</b>${spec.scope === 'page' ? html`<span class="page">(${this.t('onPage')})</span>` : nothing}
                ${control}
                <button type="button" aria-label=${this.t('delete')} @click=${() => this.removeFilter(idx)}><ol-icon name="x" size="sm"></ol-icon></button>
            </span>`;
    }

    renderQuery() {
        const r = this._result;
        const from = r ? (r.page - 1) * r.rows + 1 : 0;
        const to = r ? Math.min(r.num_found, (r.page - 1) * r.rows + r.records.length) : 0;
        return html`
            <form class="query" @submit=${this.submitQuery}>
                <div class="qrow">
                    <div class="types" role="group">
                        ${TYPES.map((t) => html`<button type="button" aria-pressed=${this._type === t ? 'true' : 'false'} @click=${() => this.setType(t)}>${this.t(TYPE_LABEL[t])}</button>`)}
                    </div>
                    <input class="qinput" type="search" .value=${this._q} placeholder=${this.t('searchPlaceholder')} aria-label=${this.t('search')} autocomplete="off" spellcheck="false">
                    <ol-button type="submit" variant="primary" ?loading=${this._busy}>${this.t('run')}</ol-button>
                    <ol-button variant="secondary" @click=${() => { this._pasteOpen = !this._pasteOpen; }}>${this.t('pasteOlids')}</ol-button>
                </div>
                <div class="frow">
                    ${this._filters.map((f, i) => this.renderFilter(f, i))}
                    <select class="add" aria-label=${this.t('addFilter')} .value=${''} @change=${(e) => { this.addFilter(e.target.value); e.target.value = ''; }}>
                        <option value="">+ ${this.t('addFilter')}</option>
                        ${this.availableFilters.map((f) => html`<option value=${f.id}>${f.label}${f.scope === 'page' ? ` (${this.t('onPage')})` : ''}</option>`)}
                    </select>
                    ${this._filters.length ? html`<ol-button size="x-small" variant="ghost" @click=${() => { this._filters = []; this._page = 1; this.run(); }}>${this.t('clearFilters')}</ol-button>` : nothing}
                    <span class="sp"></span>
                    ${r ? html`<span class="count"><b>${r.num_found.toLocaleString()}</b> ${this.t(TYPE_LABEL[this._type]).toLowerCase()}${r.num_found ? html` · ${this.t('showing', { from, to })}` : nothing}</span>` : nothing}
                    <select class="sort" aria-label=${this.t('sort')} @change=${(e) => this.setSort(e.target.value)}>
                        ${this.sorts.map((s) => html`<option value=${s} ?selected=${this._sort === s}>${this.t('sort')}: ${s.replace(/_/g, ' ')}</option>`)}
                    </select>
                </div>
            </form>
            ${this._pasteOpen ? html`<div class="paste">
                <textarea placeholder=${this.t('pasteHint')}></textarea>
                <div class="acts"><ol-button size="small" variant="primary" @click=${this.loadPasted}>${this.t('load')}</ol-button><ol-button size="small" variant="ghost" @click=${() => { this._pasteOpen = false; }}>${this.t('cancel')}</ol-button></div>
            </div>` : nothing}`;
    }

    renderBar() {
        const n = this._selected.size;
        const pending = this.pendingCount;
        if (pending) {
            return html`
                <div class="bar pending">
                    <ol-icon name="pencil" size="sm"></ol-icon>
                    <b>${this.t('pendingChanges', { count: pending })}</b>
                    <span class="hint">${this.t('pendingNote')}</span>
                    <span class="sp"></span>
                    <ol-button size="small" variant="ghost" @click=${this.discardPending}>${this.t('discard')}</ol-button>
                    <ol-button size="small" variant="primary" @click=${this.previewPending}>${this.t('previewChanges')}</ol-button>
                </div>`;
        }
        return html`
            <div class="bar">
                <b>${this.t('selected', { count: n })}</b>
                ${this.actions.map((a) => html`<ol-button size="x-small" variant="secondary" ?disabled=${!!a.reason} title=${a.reason || ''} @click=${() => this.openAction(a.id)}>${this.t(a.label)}</ol-button>`)}
                <span class="sp"></span>
                <span class="keys">${this.t('keysHint')}</span>
                <ol-button size="x-small" variant="ghost" @click=${this.selectPage}>${this.t('selectPage')}</ol-button>
                <ol-button size="x-small" variant="ghost" ?disabled=${!n} @click=${this.clearSelection}>${this.t('clear')}</ol-button>
                <ol-button size="x-small" variant="ghost" ?disabled=${!n} @click=${() => { for (const r of this.selectedRecords.slice(0, MAX_OPEN)) window.open(r.key, '_blank', 'noopener'); }}>${this.t('openAll')}</ol-button>
            </div>`;
    }

    renderRecords() {
        const r = this._result;
        const pages = r ? Math.max(1, Math.ceil(r.num_found / r.rows)) : 1;
        return html`
            ${this.renderQuery()}
            ${this._error ? html`<div class="error" role="alert">${this._error}</div>` : nothing}
            <div class="grid" aria-busy=${this._busy ? 'true' : 'false'}>
                ${r ? html`<ol-workbench-grid .type=${this._type} .records=${r.records} .selected=${this._selected} focus-key=${this._focusKey} .pending=${this._pending} .labels=${this.labels}
                    @ol-grid-toggle=${(e) => this.toggle(e.detail.key, e.detail.shift)}
                    @ol-grid-focus=${(e) => { this._focusKey = e.detail.key; }}
                    @ol-grid-open=${(e) => this.openPanel(e.detail.key)}></ol-workbench-grid>` : html`<div class="muted" style="padding: var(--spacing-3xl)">${this.t('loading')}</div>`}
            </div>
            ${r && pages > 1 ? html`<div class="pager">
                <ol-button size="x-small" variant="ghost" ?disabled=${this._page <= 1} @click=${() => this.setPage(this._page - 1)}>${this.t('prev')}</ol-button>
                <span>${this._page} / ${pages}</span>
                <ol-button size="x-small" variant="ghost" ?disabled=${this._page >= pages} @click=${() => this.setPage(this._page + 1)}>${this.t('next')}</ol-button>
            </div>` : nothing}
            ${this.renderBar()}`;
    }

    renderBatches() {
        const rows = this._batches;
        return html`
            <div class="batches-wrap">
                <div class="top">
                    <ol-button size="small" variant=${this._batchesMine ? 'primary' : 'secondary'} @click=${() => { this._batchesMine = true; this.loadBatches(); }}>${this.t('myBatches')}</ol-button>
                    ${this.canApply ? html`<ol-button size="small" variant=${!this._batchesMine ? 'primary' : 'secondary'} @click=${() => { this._batchesMine = false; this.loadBatches(); }}>${this.t('allBatches')}</ol-button>` : nothing}
                </div>
                ${!rows ? html`<span class="muted">${this.t('loading')}</span>` : !rows.length ? html`<span class="muted">${this.t('noBatches')}</span>` : html`
                <table class="batches">
                    <thead><tr><th>#</th><th>${this.t('status')}</th><th>${this.t('changes')}</th><th></th><th></th></tr></thead>
                    <tbody>${rows.map((b) => html`
                        <tr>
                            <td><a href=${`/librarians/batch/${b.id}`}>#${b.id}</a></td>
                            <td><span class="status" data-s=${b.status}>${b.status.replace(/_/g, ' ')}</span></td>
                            <td>${b.summary || b.action}<div class="muted">${this.t('by', { username: b.username })} · ${(b.created || '').slice(0, 16).replace('T', ' ')}${b.comment ? html` · ${b.comment}` : nothing}</div></td>
                            <td class="muted">${(b.items || []).length}</td>
                            <td><div class="bacts">
                                ${b.status === 'requested' && this.canApply ? html`<ol-button size="x-small" variant="primary" @click=${() => this.batchDo(b, 'apply')}>${this.t('applyBatch')}</ol-button><ol-button size="x-small" variant="ghost" @click=${() => this.batchDo(b, 'decline')}>${this.t('decline')}</ol-button>` : nothing}
                                ${(b.status === 'applied' || b.status === 'partially_reverted') && (this.canApply || b.username === this.username) ? html`<ol-button size="x-small" variant="secondary" @click=${() => this.batchDo(b, 'revert')}>${this.t('revert')}</ol-button>` : nothing}
                            </div></td>
                        </tr>`)}</tbody>
                </table>`}
            </div>`;
    }

    render() {
        const pendingQueue = this._batches?.filter((b) => b.status === 'requested').length || 0;
        return html`
            <div class="masthead">
                <div class="l">
                    <h1>${this.t('workbench')}</h1>
                    <div class="tabs" role="tablist">
                        <button class="tab" role="tab" aria-selected=${this._tab === 'records' ? 'true' : 'false'} @click=${() => this.setTab('records')}>${this.t('records')}</button>
                        <button class="tab" role="tab" aria-selected=${this._tab === 'batches' ? 'true' : 'false'} @click=${() => this.setTab('batches')}>${this.t('batches')}${pendingQueue ? html` <span class="badge">${pendingQueue}</span>` : nothing}</button>
                        <a class="tab" href="/merges">${this.t('queue')}</a>
                    </div>
                </div>
                <div class="r"></div>
            </div>
            <div class="body" ?data-panel=${!!this._panelKey && this._tab === 'records'}>
                ${this._tab === 'records' ? this.renderRail() : html`<div class="rail"></div>`}
                <div class="main">${this._tab === 'records' ? this.renderRecords() : this.renderBatches()}</div>
                ${this._panelKey && this._tab === 'records' ? html`
                    <ol-record-panel class="panel" record-key=${this._panelKey} .pending=${this._pending[this._panelKey] || {}} ?selected=${this._selected.has(this._panelKey)} .labels=${this.labels}
                        @ol-panel-edit=${this.onPanelEdit}
                        @ol-panel-action=${this.onPanelAction}
                        @ol-panel-select=${(e) => this.toggle(e.detail.key)}
                        @ol-panel-nav=${(e) => this.navPanel(e.detail.dir)}
                        @ol-panel-close=${() => { this._panelKey = ''; }}></ol-record-panel>` : nothing}
            </div>
            <ol-workbench-action-form .config=${this._config || {}} username=${this.username} .labels=${this.labels} @ol-action-submit=${this.onActionSubmit} @ol-action-list=${this.onActionList}></ol-workbench-action-form>
            <ol-batch-preview ?can-apply=${this.canApply} .labels=${this.labels} @ol-batch-applied=${this.onBatchApplied}></ol-batch-preview>`;
    }
}

customElements.define('ol-workbench', OlWorkbench);
