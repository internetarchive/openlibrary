import { LitElement, html, css, nothing } from 'lit';
import { translate } from './utils/labels.js';
import { DEFAULT_LABELS } from './workbench-labels.js';
import { olid } from '../../plugins/openlibrary/js/librarians/api.js';
import './OLChip.js';
import './OlIcon.js';

/**
 * The workbench grid: one row per record, columns per record type, a
 * checkbox column for selection and a focused row for the panel.
 *
 * Stateless: the parent owns selection, focus and pending edits and passes
 * them in; the grid reports intent through events.
 *
 * @element ol-workbench-grid
 *
 * @prop {String} type - edition | work | author
 * @prop {Array} records - Hydrated rows from /librarians/workbench/query.json
 * @prop {Set} selected - Keys currently selected
 * @prop {String} focusKey - Key of the focused row (the panel's record)
 * @prop {Object} pending - { key: { field: value } } of staged edits, for the cell tint
 * @prop {Object} labels - Translated strings
 *
 * @fires ol-grid-toggle - detail: { key, shift }
 * @fires ol-grid-focus - detail: { key }
 * @fires ol-grid-open - detail: { key }
 */
export class OlWorkbenchGrid extends LitElement {
    static properties = {
        type: { type: String },
        records: { type: Array },
        selected: { type: Object },
        focusKey: { type: String, attribute: 'focus-key' },
        pending: { type: Object },
        labels: { type: Object },
    };

    static styles = css`
        :host { display: block; font-family: var(--font-family-body); font-size: var(--font-size-body-small); color: var(--color-text); }
        table { border-collapse: separate; border-spacing: 0; width: 100%; table-layout: fixed; }
        th {
            position: sticky; top: 0; z-index: 1;
            background: var(--color-surface-sunken);
            text-align: left; padding: var(--spacing-sm) var(--spacing-md);
            font-size: var(--font-size-label-small); font-weight: var(--font-weight-semibold);
            letter-spacing: 0.04em; text-transform: uppercase; color: var(--color-text-secondary);
            border-bottom: var(--border-width) solid var(--color-border-muted); white-space: nowrap;
        }
        td {
            padding: var(--spacing-xs) var(--spacing-md); vertical-align: middle;
            border-bottom: var(--border-width) solid var(--color-border-subtle);
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        tr { cursor: default; }
        tr:hover td { background: var(--color-surface-sunken); }
        tr[data-selected] td { background: var(--color-primary-subtle); }
        tr[data-focus] td:first-child { box-shadow: inset 3px 0 0 var(--color-primary); }
        tr[data-touched] td:first-child { box-shadow: inset 3px 0 0 var(--color-success-object); }
        td.cb, th.cb { width: 34px; padding-right: 0; }
        td.cover, th.cover { width: 34px; padding: 2px var(--spacing-xs); }
        td.cover img { display: block; width: 24px; height: 34px; object-fit: cover; border-radius: 2px; background: var(--color-surface-sunken); }
        td.cover .blank { display: block; width: 24px; height: 34px; border-radius: 2px; background: var(--color-surface-sunken); }
        td.num { font-variant-numeric: tabular-nums; }
        td.mono { font-family: var(--font-family-mono); font-size: var(--font-size-label-medium); }
        td.edited { background: var(--color-warning-bg) !important; position: relative; }
        td.edited::before { content: ""; position: absolute; top: 0; right: 0; border-style: solid; border-width: 0 8px 8px 0; border-color: transparent var(--color-warning-fg) transparent transparent; }
        a { color: var(--color-link); text-decoration: none; }
        a:hover { text-decoration: underline; }
        .sub { color: var(--color-text-muted); font-size: var(--font-size-label-medium); }
        .id { color: var(--color-text-muted); font-family: var(--font-family-mono); font-size: var(--font-size-label-small); margin-left: var(--spacing-2xs); }
        .chips { display: flex; gap: var(--spacing-2xs); overflow: hidden; }
        ol-chip { --chip-padding-block: 1px; }
        input[type="checkbox"] { width: 14px; height: 14px; margin: 0; accent-color: var(--color-primary); cursor: pointer; }
        .empty { padding: var(--spacing-3xl); text-align: center; color: var(--color-text-muted); }
        .via { color: var(--color-text-muted); }
    `;

    constructor() {
        super();
        this.type = 'edition';
        this.records = [];
        this.selected = new Set();
        this.focusKey = '';
        this.pending = {};
        this.labels = {};
    }

    t(key, vars) {
        return translate(this.labels, DEFAULT_LABELS, key, vars);
    }

    /** Column definitions per record type: [header key, class, renderer]. */
    get columns() {
        const t = (k) => this.t(k);
        const names = (list) => (list || []).map((a, i) => html`${i ? ', ' : ''}<a href=${a.key} target="_blank" rel="noopener" title=${olid(a.key)}>${a.name}</a>${a.via ? html` <span class="via">(${t('work').toLowerCase()})</span>` : nothing}`);
        const title = (r) => html`<a href=${r.key} target="_blank" rel="noopener">${r.title || olid(r.key)}</a>${r.subtitle ? html` <span class="sub">${r.subtitle}</span>` : nothing}<span class="id">${olid(r.key)}</span>`;
        const chips = (r) => html`<div class="chips">${(r.chips || []).map((c) => html`<ol-chip size="small" variant=${c.level === 'block' ? 'danger' : c.level === 'warn' ? 'warning' : 'info'} title=${c.text}>${c.text}</ol-chip>`)}</div>`;
        if (this.type === 'edition') {
            return [
                { key: 'title', w: '24%', cell: title },
                { key: 'author', w: '14%', cell: (r) => names(r.authors) },
                { key: 'work', w: '16%', cell: (r) => (r.work ? html`<a href=${r.work.key} target="_blank" rel="noopener">${r.work.title || olid(r.work.key)}</a><span class="id">${olid(r.work.key)}</span>${r.work.authors?.length ? html`<div class="sub">${r.work.authors.map((a) => a.name).join(', ')}</div>` : nothing}` : html`<span class="sub">—</span>`) },
                { key: 'publisher', w: '11%', field: 'publishers', cell: (r) => (r.publishers || []).join('; ') },
                { key: 'year', w: '56px', cls: 'num', field: 'publish_date', cell: (r) => r.publish_date || '' },
                { key: 'isbn', w: '118px', cls: 'mono', cell: (r) => r.isbn || '' },
                { key: 'lang', w: '54px', field: 'languages', cell: (r) => (r.languages || []).join(' ') },
                { key: 'scan', w: '52px', cell: (r) => (r.ocaid ? html`<a href=${`https://archive.org/details/${r.ocaid}`} target="_blank" rel="noopener" title=${r.ocaid}>IA</a>` : '') },
                { key: 'health', w: '', cell: chips },
                { key: 'source', w: '84px', cell: (r) => (r.sources || []).join(', ') },
            ];
        }
        if (this.type === 'work') {
            return [
                { key: 'title', w: '28%', cell: title },
                { key: 'author', w: '18%', cell: (r) => names(r.authors) },
                { key: 'year', w: '56px', cls: 'num', cell: (r) => r.year ?? '' },
                { key: 'editions', w: '70px', cls: 'num', cell: (r) => r.edition_count ?? '' },
                { key: 'lang', w: '70px', cell: (r) => (r.languages || []).slice(0, 3).join(' ') },
                { key: 'subjects', w: '18%', cell: (r) => html`${(r.subjects || []).join(', ')}${r.subject_count > (r.subjects || []).length ? html` <span class="sub">+${r.subject_count - r.subjects.length}</span>` : nothing}` },
                { key: 'readers', w: '66px', cls: 'num', cell: (r) => r.readinglog_count ?? '' },
                { key: 'modified', w: '92px', cls: 'num', cell: (r) => r.modified || '' },
                { key: 'health', w: '', cell: chips },
            ];
        }
        return [
            { key: 'name', w: '30%', cell: title },
            { key: 'dates', w: '120px', cls: 'num', cell: (r) => [r.birth_date, r.death_date].filter(Boolean).join(' – ') },
            { key: 'works', w: '64px', cls: 'num', cell: (r) => r.work_count ?? '' },
            { key: 'topWork', w: '22%', cell: (r) => r.top_work || '' },
            { key: 'ids', w: '14%', cell: (r) => Object.keys(r.ids || {}).join(', ') },
            { key: 'health', w: '', cell: chips },
        ];
    }

    header(key) {
        const map = { title: 'title', author: 'author', work: 'work', publisher: 'publisher', year: 'year', isbn: 'isbn', lang: 'language', scan: 'scan', health: 'health', source: 'source', editions: 'editions', subjects: 'subjects', readers: 'readers', modified: 'modified', name: 'name', dates: 'dates', works: 'works', topWork: 'topWork', ids: 'ids' };
        return this.t(`col_${map[key] || key}`);
    }

    onRowClick(e, r) {
        if (e.target.closest('a, input, ol-chip')) return;
        this.dispatchEvent(new CustomEvent('ol-grid-focus', { detail: { key: r.key }, bubbles: true, composed: true }));
        this.dispatchEvent(new CustomEvent('ol-grid-open', { detail: { key: r.key }, bubbles: true, composed: true }));
    }

    onToggle(e, r) {
        e.stopPropagation();
        this.dispatchEvent(new CustomEvent('ol-grid-toggle', { detail: { key: r.key, shift: !!e.shiftKey }, bubbles: true, composed: true }));
    }

    render() {
        if (!this.records?.length) return html`<div class="empty">${this.t('noResults')}</div>`;
        const cols = this.columns;
        return html`
            <table>
                <colgroup>
                    <col style="width: 34px"><col style="width: 34px">
                    ${cols.map((c) => html`<col style=${c.w ? `width: ${c.w}` : ''}>`)}
                </colgroup>
                <thead>
                    <tr>
                        <th class="cb"></th>
                        <th class="cover"></th>
                        ${cols.map((c) => html`<th>${this.header(c.key)}</th>`)}
                    </tr>
                </thead>
                <tbody>
                    ${this.records.map((r) => {
        const edits = this.pending?.[r.key] || {};
        return html`
                        <tr ?data-selected=${this.selected?.has(r.key)} ?data-focus=${this.focusKey === r.key} ?data-touched=${!!r.touched} @click=${(e) => this.onRowClick(e, r)}>
                            <td class="cb"><input type="checkbox" .checked=${!!this.selected?.has(r.key)} aria-label=${r.title || r.key} @click=${(e) => this.onToggle(e, r)}></td>
                            <td class="cover">${r.cover ? html`<img src=${r.cover} alt="" loading="lazy">` : html`<span class="blank"></span>`}</td>
                            ${cols.map((c) => html`<td class="${c.cls || ''} ${c.field && c.field in edits ? 'edited' : ''}" title=${c.field && c.field in edits ? String(edits[c.field]) : ''}>${c.cell(r)}</td>`)}
                        </tr>`;
    })}
                </tbody>
            </table>`;
    }
}

customElements.define('ol-workbench-grid', OlWorkbenchGrid);
