import { LitElement, html, css, nothing } from 'lit';
import { translate } from './utils/labels.js';
import { DEFAULT_LABELS } from './workbench-labels.js';
import { api, olid } from '../../plugins/openlibrary/js/librarians/api.js';
import './OlDialog.js';
import './OLButton.js';
import './OlAutocomplete.js';

const SUBJECT_TYPES = [['subjects', 'subjects'], ['subject_people', 'subjectPeople'], ['subject_places', 'subjectPlaces'], ['subject_times', 'subjectTimes']];
const REASONS = [['review', 'review'], ['duplicate', 'duplicate'], ['spam', 'spam'], ['non_book', 'nonBook'], ['delete', 'toDelete']];

/**
 * The parameter form for one batch action, in a dialog. Submitting does not
 * write anything: it reports the parameters, and the parent hands them to the
 * preview dialog.
 *
 * @element ol-workbench-action-form
 *
 * @prop {String} kind - set_author | move_editions | tag | set_field | merge_editions | flag | delete | add_to_list
 * @prop {Array} records - The records the action applies to (hydrated rows)
 * @prop {Object} preset - Parameters to start from (e.g. { target: 'new' })
 * @prop {Object} config - /librarians/workbench/config.json (settable fields)
 * @prop {String} username - For the list picker
 * @prop {Object} labels - Translated strings
 *
 * @fires ol-action-submit - detail: { action, params, title }
 * @fires ol-action-list - detail: { listKey }
 */
export class OlWorkbenchActionForm extends LitElement {
    static properties = {
        kind: { type: String },
        records: { type: Array },
        preset: { type: Object },
        config: { type: Object },
        username: { type: String },
        labels: { type: Object },
        _open: { state: true },
        _params: { state: true },
        _lists: { state: true },
        _error: { state: true },
    };

    static styles = css`
        :host { display: contents; font-family: var(--font-family-body); }
        .body { display: grid; gap: var(--spacing-md); font-size: var(--font-size-body-small); color: var(--color-text); }
        .row { display: grid; gap: var(--spacing-2xs); }
        .row > span, label.lbl { font-size: var(--font-size-label-medium); color: var(--color-text-secondary); }
        .inline { display: flex; flex-wrap: wrap; gap: var(--spacing-md); align-items: center; }
        label.opt { display: inline-flex; align-items: center; gap: var(--spacing-xs); cursor: pointer; }
        input[type="text"], input[type="number"], select, textarea { width: 100%; box-sizing: border-box; font: inherit; font-size: 16px; padding: var(--spacing-xs) var(--spacing-sm); border: var(--border-width) solid var(--color-border); border-radius: var(--border-radius-input); background: var(--color-surface); color: var(--color-text); }
        @media (hover: hover) and (pointer: fine) { input[type="text"], input[type="number"], select, textarea { font-size: var(--font-size-body-small); } }
        input:focus-visible, select:focus-visible, textarea:focus-visible { outline: 2px solid var(--color-border-focused); outline-offset: 1px; }
        input[type="radio"], input[type="checkbox"] { accent-color: var(--color-primary); margin: 0; }
        .authors { border: var(--border-width) solid var(--color-border-muted); border-radius: var(--border-radius-md); padding: var(--spacing-xs) var(--spacing-md); display: grid; gap: var(--spacing-2xs); }
        .authors div { display: flex; justify-content: space-between; gap: var(--spacing-sm); }
        .muted { color: var(--color-text-muted); }
        .footer { display: flex; gap: var(--spacing-xs); justify-content: flex-end; }
        .error { color: var(--color-error-fg); }
        .count { font-size: var(--font-size-label-medium); color: var(--color-text-secondary); }
    `;

    constructor() {
        super();
        this.kind = '';
        this.records = [];
        this.preset = {};
        this.config = {};
        this.username = '';
        this.labels = {};
        this._open = false;
        this._params = {};
        this._lists = null;
        this._error = null;
    }

    t(key, vars) {
        return translate(this.labels, DEFAULT_LABELS, key, vars);
    }

    async show({ kind, records, preset = {} }) {
        this.kind = kind;
        this.records = records;
        this.preset = preset;
        this._error = null;
        this._params = { ...this.defaults(kind), ...preset };
        this._open = true;
        await this.updateComplete;
        this.renderRoot.querySelector('ol-dialog').open = true;
        if (kind === 'add_to_list' && !this._lists) {
            try {
                const r = await api.myLists(this.username);
                this._lists = r.entries || r.lists || [];
            } catch (e) {
                this._error = e.message;
            }
        }
    }

    close() {
        this._open = false;
        const d = this.renderRoot.querySelector('ol-dialog');
        if (d) d.open = false;
    }

    defaults(kind) {
        if (kind === 'set_author') return { mode: 'add', include_editions: true, author: '', replace: '' };
        if (kind === 'move_editions') return { target: '', new_title: '' };
        if (kind === 'tag') return { add: {}, remove: {} };
        if (kind === 'set_field') return { field: this.fieldNames[0] || '', value: '', mode: 'set' };
        if (kind === 'merge_editions') return { master: this.lowestKey };
        if (kind === 'flag') return { reason: 'review' };
        if (kind === 'delete') return { include_editions: false };
        return {};
    }

    set(k, v) {
        this._params = { ...this._params, [k]: v };
    }

    get recordType() {
        return this.records[0]?.type || 'edition';
    }

    get fieldNames() {
        return Object.keys(this.config?.settable_fields?.[this.recordType] || {});
    }

    get lowestKey() {
        return [...this.records].sort((a, b) => Number(olid(a.key).slice(2, -1)) - Number(olid(b.key).slice(2, -1)))[0]?.key;
    }

    /** Authors across the selected records, with how many records carry each. */
    get currentAuthors() {
        const counts = new Map();
        for (const r of this.records) {
            for (const a of r.authors || []) {
                if (a.via) continue;
                const cur = counts.get(a.key) || { key: a.key, name: a.name, count: 0 };
                cur.count += 1;
                counts.set(a.key, cur);
            }
        }
        return [...counts.values()].sort((a, b) => b.count - a.count);
    }

    get valid() {
        const p = this._params;
        if (this.kind === 'set_author') return !!p.author && (p.mode !== 'replace' || !!p.replace);
        if (this.kind === 'move_editions') return p.target === 'new' || !!p.target;
        if (this.kind === 'tag') return Object.values(p.add).some((l) => l.length) || Object.values(p.remove).some((l) => l.length);
        if (this.kind === 'set_field') return !!p.field && p.value !== '' && p.value !== null;
        if (this.kind === 'merge_editions') return this.records.length >= 2;
        if (this.kind === 'add_to_list') return !!p.list;
        return true;
    }

    submit() {
        if (!this.valid) return;
        if (this.kind === 'add_to_list') {
            this.dispatchEvent(new CustomEvent('ol-action-list', { detail: { listKey: this._params.list }, bubbles: true, composed: true }));
            this.close();
            return;
        }
        const params = { ...this._params };
        if (this.kind === 'set_field') {
            const kind = this.config?.settable_fields?.[this.recordType]?.[params.field];
            if (kind === 'list' || kind === 'keys') params.value = String(params.value).split(/[,;]/).map((s) => s.trim()).filter(Boolean);
            if (kind === 'int') params.value = Number(params.value);
        }
        if (this.kind === 'move_editions' && params.target !== 'new') delete params.new_title;
        this.dispatchEvent(new CustomEvent('ol-action-submit', { detail: { action: this.kind, params, title: this.title }, bubbles: true, composed: true }));
        this.close();
    }

    get title() {
        const map = { set_author: 'setAuthor', move_editions: 'moveEditions', tag: 'manageSubjects', set_field: 'setField', merge_editions: 'mergeEditions', flag: 'flag', delete: 'deleteRecords', add_to_list: 'addToList' };
        return this.t(map[this.kind] || this.kind).replace(/…$/, '');
    }

    subjectList(bucket, type) {
        return (this._params[bucket]?.[type] || []).join(', ');
    }

    setSubjects(bucket, type, raw) {
        const list = raw.split(/[,;]/).map((s) => s.trim()).filter(Boolean);
        this.set(bucket, { ...this._params[bucket], [type]: list });
    }

    renderForm() {
        const p = this._params;
        switch (this.kind) {
        case 'set_author': {
            const authors = this.currentAuthors;
            return html`
                ${authors.length ? html`<div class="row"><span>${this.t('currentAuthors')}</span>
                    <div class="authors">${authors.map((a) => html`<div><span>${a.name} <span class="muted">${olid(a.key)}</span></span><span class="muted">${a.count}</span></div>`)}</div></div>` : nothing}
                <div class="inline" role="radiogroup">
                    ${[['add', 'modeAdd'], ['replace', 'modeReplace'], ['set', 'modeSet']].map(([v, l]) => html`<label class="opt"><input type="radio" name="mode" value=${v} .checked=${p.mode === v} @change=${() => this.set('mode', v)}>${this.t(l)}</label>`)}
                </div>
                ${p.mode === 'replace' ? html`<div class="row"><span>${this.t('modeReplace')}</span>
                    <select @change=${(e) => this.set('replace', e.target.value)}>
                        <option value="" ?selected=${!p.replace}>—</option>
                        ${authors.map((a) => html`<option value=${a.key} ?selected=${p.replace === a.key}>${a.name} (${olid(a.key)})</option>`)}
                    </select></div>` : nothing}
                <div class="row"><span>${this.t('author')}</span>
                    <ol-autocomplete kind="author" placeholder=${this.t('authorPlaceholder')} label=${this.t('author')} @ol-autocomplete-select=${(e) => this.set('author', e.detail.key)} @ol-autocomplete-input=${(e) => { if (!e.detail.value) this.set('author', ''); }}></ol-autocomplete>
                </div>
                <label class="opt"><input type="checkbox" .checked=${!!p.include_editions} @change=${(e) => this.set('include_editions', e.target.checked)}>${this.t('includeEditions')}</label>`;
        }
        case 'move_editions':
            return html`
                <div class="row"><span>${this.t('targetWork')}</span>
                    <div class="inline" role="radiogroup">
                        <label class="opt"><input type="radio" name="target" .checked=${p.target !== 'new'} @change=${() => this.set('target', '')}>${this.t('work')}</label>
                        <label class="opt"><input type="radio" name="target" .checked=${p.target === 'new'} @change=${() => this.set('target', 'new')}>${this.t('newWork')}</label>
                    </div>
                </div>
                ${p.target === 'new'
        ? html`<div class="row"><span>${this.t('newWorkTitle')}</span><input type="text" .value=${p.new_title || ''} @input=${(e) => this.set('new_title', e.target.value)}></div>`
        : html`<div class="row"><span>${this.t('work')}</span><ol-autocomplete kind="work" placeholder=${this.t('workPlaceholder')} label=${this.t('work')} @ol-autocomplete-select=${(e) => this.set('target', e.detail.key)} @ol-autocomplete-input=${(e) => { if (!e.detail.value) this.set('target', ''); }}></ol-autocomplete></div>`}`;
        case 'tag':
            return html`
                ${SUBJECT_TYPES.map(([type, label]) => html`
                    <div class="row"><span>${this.t(label)}</span>
                        <div class="inline">
                            <label class="lbl" style="flex:1"><span class="muted">${this.t('subjectsAdd')}</span><input type="text" placeholder=${this.t('commaSeparated')} .value=${this.subjectList('add', type)} @change=${(e) => this.setSubjects('add', type, e.target.value)}></label>
                            <label class="lbl" style="flex:1"><span class="muted">${this.t('subjectsRemove')}</span><input type="text" placeholder=${this.t('commaSeparated')} .value=${this.subjectList('remove', type)} @change=${(e) => this.setSubjects('remove', type, e.target.value)}></label>
                        </div>
                    </div>`)}`;
        case 'set_field': {
            const kind = this.config?.settable_fields?.[this.recordType]?.[p.field];
            return html`
                <div class="row"><span>${this.t('fieldName')}</span>
                    <select @change=${(e) => this.set('field', e.target.value)}>${this.fieldNames.map((f) => html`<option value=${f} ?selected=${p.field === f}>${f.replace(/_/g, ' ')}</option>`)}</select>
                </div>
                <div class="row"><span>${this.t('fieldValue')}</span>
                    <input type=${kind === 'int' ? 'number' : 'text'} placeholder=${kind === 'list' || kind === 'keys' ? this.t('commaSeparated') : ''} .value=${p.value ?? ''} @input=${(e) => this.set('value', e.target.value)}>
                </div>
                ${kind === 'list' || kind === 'keys' ? html`<div class="inline" role="radiogroup">
                    <label class="opt"><input type="radio" name="fmode" .checked=${p.mode === 'set'} @change=${() => this.set('mode', 'set')}>${this.t('modeSetValue')}</label>
                    <label class="opt"><input type="radio" name="fmode" .checked=${p.mode === 'append'} @change=${() => this.set('mode', 'append')}>${this.t('modeAppend')}</label>
                </div>` : nothing}`;
        }
        case 'merge_editions':
            return html`
                <div class="row"><span>${this.t('master')}</span>
                    <select @change=${(e) => this.set('master', e.target.value)}>
                        ${this.records.map((r) => html`<option value=${r.key} ?selected=${p.master === r.key}>${r.title} · ${olid(r.key)}${r.key === this.lowestKey ? ` (${this.t('lowestOlid')})` : ''}</option>`)}
                    </select>
                </div>`;
        case 'flag':
            return html`
                <div class="row"><span>${this.t('reason')}</span>
                    <div class="inline" role="radiogroup">${REASONS.map(([v, l]) => html`<label class="opt"><input type="radio" name="reason" .checked=${p.reason === v} @change=${() => this.set('reason', v)}>${this.t(l)}</label>`)}</div>
                </div>`;
        case 'delete':
            return this.records.some((r) => r.type === 'work')
                ? html`<label class="opt"><input type="checkbox" .checked=${!!p.include_editions} @change=${(e) => this.set('include_editions', e.target.checked)}>${this.t('includeEditionsDelete')}</label>`
                : nothing;
        case 'add_to_list':
            return html`
                <div class="row"><span>${this.t('list')}</span>
                    <select @change=${(e) => this.set('list', e.target.value)}>
                        <option value="">${this.t('chooseList')}</option>
                        ${(this._lists || []).map((l) => html`<option value=${l.url || l.key} ?selected=${p.list === (l.url || l.key)}>${l.name}</option>`)}
                    </select>
                </div>`;
        default:
            return nothing;
        }
    }

    render() {
        if (!this._open) return nothing;
        return html`
            <ol-dialog label=${this.title} width="medium" fullscreen-on-mobile @ol-after-close=${() => { this._open = false; }}>
                <div class="body">
                    <span class="count">${this.t('selected', { count: this.records.length })}</span>
                    ${this._error ? html`<div class="error" role="alert">${this._error}</div>` : nothing}
                    ${this.renderForm()}
                </div>
                <div slot="footer" class="footer">
                    <ol-button variant="ghost" @click=${this.close}>${this.t('cancel')}</ol-button>
                    <ol-button variant="primary" ?disabled=${!this.valid} @click=${this.submit}>${this.kind === 'add_to_list' ? this.t('apply') : this.t('preview')}</ol-button>
                </div>
            </ol-dialog>`;
    }
}

customElements.define('ol-workbench-action-form', OlWorkbenchActionForm);
