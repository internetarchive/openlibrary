import { LitElement, html, css, nothing } from 'lit';
import { translate } from './utils/labels.js';
import { DEFAULT_LABELS } from './workbench-labels.js';
import { api, olid } from '../../plugins/openlibrary/js/librarians/api.js';
import './OLButton.js';
import './OLChip.js';
import './OlIcon.js';

const LEVEL_ICON = { block: 'octagon-alert', warn: 'triangle-alert', info: 'info', ok: 'circle-check' };

/**
 * The record panel beside the workbench grid: one record's findings (the
 * full health strip), its editable fields, and what it belongs to.
 *
 * Field edits are staged, not written: every change is reported to the
 * parent, which batches them through set_field with a preview.
 *
 * @element ol-record-panel
 *
 * @prop {String} recordKey - The record to show
 * @prop {Object} pending - Staged edits for this record: { field: value }
 * @prop {Boolean} selected - Whether the record is in the selection
 * @prop {Object} labels - Translated strings
 *
 * @fires ol-panel-edit - detail: { key, field, kind, value } (value null clears the edit)
 * @fires ol-panel-action - detail: { action, keys, params, title }
 * @fires ol-panel-select - detail: { key }
 * @fires ol-panel-nav - detail: { dir: 1 | -1 }
 * @fires ol-panel-close
 */
export class OlRecordPanel extends LitElement {
    static properties = {
        recordKey: { type: String, attribute: 'record-key' },
        pending: { type: Object },
        selected: { type: Boolean },
        labels: { type: Object },
        _data: { state: true },
        _error: { state: true },
        _busy: { state: true },
    };

    static styles = css`
        :host { display: flex; flex-direction: column; min-height: 0; height: 100%; font-family: var(--font-family-body); font-size: var(--font-size-body-small); color: var(--color-text); background: var(--color-surface); }
        .head { padding: var(--spacing-md) var(--spacing-lg) var(--spacing-sm); border-bottom: var(--border-width) solid var(--color-border-muted); display: grid; gap: var(--spacing-2xs); }
        .head .row { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--spacing-sm); }
        h2 { margin: 0; font-family: var(--font-family-title); font-size: var(--font-size-title-medium); font-weight: var(--font-weight-semibold); line-height: var(--line-height-heading); color: var(--color-text-heading); }
        .meta { color: var(--color-text-secondary); font-size: var(--font-size-label-medium); }
        .meta a { color: var(--color-link); }
        .mono { font-family: var(--font-family-mono); }
        .body { flex: 1; overflow: auto; padding: var(--spacing-md) var(--spacing-lg); display: grid; gap: var(--spacing-lg); align-content: start; }
        h3 { margin: 0 0 var(--spacing-sm); font-size: var(--font-size-label-small); font-weight: var(--font-weight-semibold); letter-spacing: 0.06em; text-transform: uppercase; color: var(--color-text-secondary); }
        .finding { border: var(--border-width) solid var(--color-border-muted); border-radius: var(--border-radius-md); padding: var(--spacing-sm) var(--spacing-md); display: grid; gap: var(--spacing-xs); margin-bottom: var(--spacing-sm); }
        .finding .h { display: flex; align-items: center; gap: var(--spacing-xs); font-weight: var(--font-weight-semibold); }
        .finding[data-level="block"] { border-color: var(--color-error-border); background: var(--color-error-bg); }
        .finding[data-level="block"] .h { color: var(--color-error-fg); }
        .finding[data-level="warn"] { border-color: var(--color-warning-border); background: var(--color-warning-bg); }
        .finding[data-level="warn"] .h { color: var(--color-warning-fg); }
        .finding .d { color: var(--color-text-secondary); font-size: var(--font-size-label-medium); }
        .finding .acts { display: flex; flex-wrap: wrap; gap: var(--spacing-xs); }
        .frow { display: grid; grid-template-columns: 104px minmax(0, 1fr); gap: var(--spacing-sm); align-items: center; margin-bottom: var(--spacing-xs); }
        .frow label { font-size: var(--font-size-label-medium); color: var(--color-text-secondary); }
        input, select { width: 100%; box-sizing: border-box; height: var(--control-height-small); padding: 0 var(--spacing-sm); font: inherit; font-size: 16px; border: var(--border-width) solid var(--color-border); border-radius: var(--border-radius-input); background: var(--color-surface); color: var(--color-text); }
        @media (hover: hover) and (pointer: fine) { input, select { font-size: var(--font-size-body-small); } }
        input:focus-visible, select:focus-visible { outline: 2px solid var(--color-border-focused); outline-offset: 1px; }
        input[data-edited] { border-color: var(--color-warning-fg); background: var(--color-warning-bg); }
        .note { color: var(--color-text-muted); font-size: var(--font-size-label-medium); margin-top: var(--spacing-xs); }
        .foot { padding: var(--spacing-sm) var(--spacing-lg); border-top: var(--border-width) solid var(--color-border-muted); display: flex; align-items: center; gap: var(--spacing-sm); }
        .foot .sp { flex: 1; }
        .error { color: var(--color-error-fg); }
        a { color: var(--color-link); }
        .belongs { display: grid; gap: var(--spacing-xs); }
        .belongs .acts { display: flex; flex-wrap: wrap; gap: var(--spacing-xs); }
    `;

    constructor() {
        super();
        this.recordKey = '';
        this.pending = {};
        this.selected = false;
        this.labels = {};
        this._data = null;
        this._error = null;
        this._busy = false;
    }

    t(key, vars) {
        return translate(this.labels, DEFAULT_LABELS, key, vars);
    }

    updated(changed) {
        if (changed.has('recordKey')) this.load();
    }

    async load() {
        const key = this.recordKey;
        this._data = null;
        this._error = null;
        if (!key) return;
        this._busy = true;
        try {
            const data = await api.record(key);
            if (this.recordKey === key) this._data = data;
        } catch (e) {
            this._error = e.status === 404 ? this.t('notFound') : this.t('error', { error: e.message });
        } finally {
            this._busy = false;
        }
    }

    /** Refresh after a batch touched this record. */
    refresh() {
        return this.load();
    }

    emit(name, detail = {}) {
        this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true, composed: true }));
    }

    onField(field, kind, raw) {
        const original = this._data?.fields?.[field]?.value;
        let value;
        if (kind === 'list' || kind === 'keys') value = raw.split(/[,;]/).map((s) => s.trim()).filter(Boolean);
        else if (kind === 'int') value = raw === '' ? null : Number(raw);
        else value = raw.trim();
        const same = JSON.stringify(value ?? '') === JSON.stringify(original ?? '') || (kind === 'int' && value === null && !original);
        this.emit('ol-panel-edit', { key: this._data.record.key, field, kind, value: same ? null : value });
    }

    fieldValue(field) {
        const edit = this.pending?.[field];
        const v = edit !== undefined ? edit : this._data?.fields?.[field]?.value;
        if (v === null || v === undefined) return '';
        return Array.isArray(v) ? v.join(', ') : String(v);
    }

    action(action, params = {}, title = '') {
        this.emit('ol-panel-action', { action, keys: [this._data.record.key], params, title });
    }

    renderFinding(c) {
        const r = this._data.record;
        const level = c.level in LEVEL_ICON ? c.level : 'info';
        let acts = nothing;
        if (c.code === 'author_mismatch' && r.type === 'edition' && r.work?.authors?.length) {
            const workAuthor = r.work.authors[0];
            acts = html`<div class="acts">
                <ol-button size="x-small" variant="secondary" @click=${() => this.action('set_author', { author: workAuthor.key, mode: 'set', include_editions: true }, this.t('useWorkAuthor'))}>${this.t('useWorkAuthor')}</ol-button>
                ${r.authors?.[0]?.key ? html`<ol-button size="x-small" variant="ghost" href=${`/authors/merge?records=${olid(workAuthor.key)},${olid(r.authors[0].key)}`} target="_blank" rel="noopener">${this.t('mergeTheseAuthors')}</ol-button>` : nothing}
            </div>`;
        }
        const detail = c.detail && typeof c.detail === 'object' && !Array.isArray(c.detail)
            ? Object.entries(c.detail).filter(([, v]) => v !== null && v !== undefined && !(Array.isArray(v) && !v.length)).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : typeof v === 'object' ? JSON.stringify(v) : v}`).join(' · ')
            : '';
        return html`
            <div class="finding" data-level=${level}>
                <div class="h"><ol-icon name=${LEVEL_ICON[level]} size="sm"></ol-icon>${c.href ? html`<a href=${c.href} target="_blank" rel="noopener">${c.text}</a>` : c.text}</div>
                ${detail ? html`<div class="d">${detail}</div>` : nothing}
                ${acts}
            </div>`;
    }

    renderFields() {
        const fields = this._data?.fields || {};
        const names = Object.keys(fields);
        if (!names.length) return nothing;
        const label = (f) => f.replace(/_/g, ' ');
        return html`
            <section>
                <h3>${this.t('fields')}</h3>
                ${names.map((f) => {
        const kind = fields[f].kind;
        const edited = this.pending?.[f] !== undefined;
        return html`<div class="frow">
                        <label for=${`f-${f}`}>${label(f)}</label>
                        <input id=${`f-${f}`} type=${kind === 'int' ? 'number' : 'text'} .value=${this.fieldValue(f)} ?data-edited=${edited} placeholder=${kind === 'list' || kind === 'keys' ? this.t('commaSeparated') : ''} @change=${(e) => this.onField(f, kind, e.target.value)}>
                    </div>`;
    })}
                <div class="note">${this.t('fieldsNote')}</div>
            </section>`;
    }

    renderBelongs() {
        const r = this._data.record;
        if (r.type !== 'edition') return nothing;
        return html`
            <section>
                <h3>${this.t('belongsTo')}</h3>
                <div class="belongs">
                    <div class="frow"><label>${this.t('work')}</label>
                        <div>${r.work ? html`<a href=${r.work.key} target="_blank" rel="noopener">${r.work.title || olid(r.work.key)}</a> <span class="meta mono">${olid(r.work.key)}</span>` : html`<span class="meta">—</span>`}</div>
                    </div>
                    <div class="acts">
                        <ol-button size="x-small" variant="secondary" @click=${() => this.action('move_editions', {}, this.t('moveToWork'))}>${this.t('moveToWork')}</ol-button>
                        <ol-button size="x-small" variant="ghost" @click=${() => this.action('move_editions', { target: 'new' }, this.t('moveToNewWork'))}>${this.t('moveToNewWork')}</ol-button>
                    </div>
                </div>
            </section>`;
    }

    render() {
        const d = this._data;
        const r = d?.record;
        return html`
            <div class="head">
                <div class="row">
                    <h2>${r ? r.title || olid(r.key) : this.recordKey ? olid(this.recordKey) : ''}</h2>
                    <ol-button size="x-small" variant="ghost" shape="icon" aria-label=${this.t('close')} @click=${() => this.emit('ol-panel-close')}><ol-icon name="x" size="sm"></ol-icon></ol-button>
                </div>
                ${r ? html`
                    <div class="meta"><span class="mono">${olid(r.key)}</span> · ${this.t('revision', { n: r.revision ?? '?' })} · <a href=${r.key} target="_blank" rel="noopener">${this.t('openRecord')}</a> · <a href=${`${r.key}/edit`} target="_blank" rel="noopener">${this.t('editForm')}</a> · <a href=${`${r.key}?m=history`} target="_blank" rel="noopener">${this.t('history')}</a></div>
                ` : nothing}
            </div>
            <div class="body" aria-busy=${this._busy ? 'true' : 'false'}>
                ${this._error ? html`<div class="error" role="alert">${this._error}</div>` : nothing}
                ${this._busy && !d ? html`<div class="meta">${this.t('loading')}</div>` : nothing}
                ${d ? html`
                    <section>
                        <h3>${this.t('findings')}</h3>
                        ${(d.health?.chips || []).map((c) => this.renderFinding(c))}
                    </section>
                    ${this.renderFields()}
                    ${this.renderBelongs()}
                ` : nothing}
            </div>
            <div class="foot">
                <ol-button size="x-small" variant="ghost" shape="icon" aria-label=${this.t('prevRecord')} @click=${() => this.emit('ol-panel-nav', { dir: -1 })}><ol-icon name="chevron-left" size="sm"></ol-icon></ol-button>
                <ol-button size="x-small" variant="ghost" shape="icon" aria-label=${this.t('nextRecord')} @click=${() => this.emit('ol-panel-nav', { dir: 1 })}><ol-icon name="chevron-right" size="sm"></ol-icon></ol-button>
                <span class="sp"></span>
                ${r ? html`<ol-button size="small" variant="secondary" aria-pressed=${this.selected ? 'true' : 'false'} @click=${() => this.emit('ol-panel-select', { key: r.key })}>${this.selected ? this.t('inSelection') : this.t('addToSelection')}</ol-button>` : nothing}
            </div>`;
    }
}

customElements.define('ol-record-panel', OlRecordPanel);
