import { LitElement, html, css, nothing } from 'lit';
import { normalizeKey, olid } from '../../plugins/openlibrary/js/librarians/api.js';
import { debounce } from '../../plugins/openlibrary/js/nonjquery_utils.js';

/** Per-kind endpoint and the two lines each suggestion shows. */
const KINDS = {
    author: {
        endpoint: '/authors/_autocomplete',
        primary: (d) => d.name,
        secondary: (d) => [d.birth_date || d.death_date ? `${d.birth_date || '?'} – ${d.death_date || ''}` : '', d.works?.[0]].filter(Boolean).join(' · '),
    },
    work: {
        endpoint: '/works/_autocomplete',
        primary: (d) => d.full_title || d.title,
        secondary: (d) => [d.author_name?.join(', '), d.first_publish_year].filter(Boolean).join(' · '),
    },
    subject: { endpoint: '/subjects_autocomplete', primary: (d) => d.name, secondary: (d) => (d.work_count ? `${d.work_count} works` : '') },
    language: { endpoint: '/languages/_autocomplete', primary: (d) => d.name, secondary: (d) => d.code || '' },
};

let nextId = 0;

/**
 * A text input with typeahead suggestions from one of the site's
 * `_autocomplete` endpoints. Typing searches; picking a suggestion fills the
 * field with the record's name and remembers its key. An OLID or URL typed
 * straight in is accepted as-is without searching, so the field never blocks
 * a librarian who already has the key.
 *
 * @element ol-autocomplete
 *
 * @prop {String} kind - author | work | subject | language. Picks the endpoint.
 * @prop {String} value - Current text of the field
 * @prop {String} key - Record key of the pick, or null for free text. Settable, so a
 *   parent can restore a pick it made earlier.
 * @prop {String} placeholder
 * @prop {String} label - Accessible name for the input
 * @prop {String} noResultsText - Status line when a search finds nothing
 * @prop {Boolean} clearOnSelect - Empty the field after a pick, for
 *   "add one more" style inputs. Off, the picked name stays in the field.
 *
 * @fires ol-autocomplete-input - detail: { value } on every edit
 * @fires ol-autocomplete-select - detail: { key, name, item } on a pick
 * @fires ol-autocomplete-submit - detail: { value } on Enter with no pick
 */
export class OlAutocomplete extends LitElement {
    static properties = {
        kind: { type: String },
        value: { type: String },
        key: { type: String },
        placeholder: { type: String },
        label: { type: String },
        noResultsText: { type: String, attribute: 'no-results-text' },
        clearOnSelect: { type: Boolean, attribute: 'clear-on-select' },
        _items: { state: true },
        _open: { state: true },
        _active: { state: true },
        _status: { state: true },
    };

    static styles = css`
        :host { display: block; position: relative; font-family: var(--font-family-body); font-size: var(--font-size-body-small); color: var(--color-text); }
        .box { position: relative; display: flex; align-items: center; }
        input { flex: 1; min-width: 0; width: 100%; box-sizing: border-box; font: inherit; font-size: 16px; padding: var(--spacing-xs); border: var(--border-input); border-radius: var(--border-radius-input); background: var(--color-surface); color: var(--color-text); }
        input:focus-visible { outline: none; border: var(--border-input-focused); box-shadow: var(--box-shadow-focus); }
        input.picked { padding-right: calc(var(--spacing-xs) + 7ch); }
        @media (hover: hover) and (pointer: fine) { input { font-size: var(--font-size-body-medium); } }
        .key { position: absolute; right: var(--spacing-xs); font-family: var(--font-family-mono); font-size: var(--font-size-label-small); color: var(--color-text-muted); pointer-events: none; }
        ul { position: absolute; z-index: 1; left: 0; right: 0; top: 100%; margin: var(--spacing-3xs) 0 0; padding: var(--spacing-3xs); list-style: none; max-height: 40vh; overflow: auto; background: var(--color-surface); border: var(--border-width) solid var(--color-border); border-radius: var(--border-radius-md); box-shadow: var(--box-shadow-floating); }
        li { display: grid; gap: 1px; padding: var(--spacing-2xs) var(--spacing-xs); border-radius: var(--border-radius-sm); cursor: pointer; }
        li[aria-selected="true"] { background: var(--color-control-selected-bg); }
        @media (hover: hover) and (pointer: fine) { li:hover { background: var(--color-hover-overlay); } }
        .p { font-weight: var(--font-weight-medium); }
        .s, .status { color: var(--color-text-secondary); font-size: var(--font-size-label-medium); }
        .status { position: absolute; z-index: 1; left: 0; right: 0; top: 100%; margin-top: var(--spacing-3xs); padding: var(--spacing-2xs) var(--spacing-xs); background: var(--color-surface); border: var(--border-width) solid var(--color-border); border-radius: var(--border-radius-md); box-shadow: var(--box-shadow-floating); }
    `;

    constructor() {
        super();
        this.kind = 'author';
        this.value = '';
        this.placeholder = '';
        this.label = '';
        this.noResultsText = 'No matches';
        this.clearOnSelect = false;
        this._items = [];
        this._open = false;
        this._active = -1;
        this.key = null;
        this._status = '';
        this._listId = `ol-ac-list-${nextId++}`;
        this._search = debounce(() => this.search(), 250);
        this._onDocPointer = (e) => { if (!e.composedPath().includes(this)) this.close(); };
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('pointerdown', this._onDocPointer);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('pointerdown', this._onDocPointer);
        this._abort?.abort();
    }

    get spec() {
        return KINDS[this.kind] || KINDS.author;
    }

    focus() {
        this.renderRoot.querySelector('input')?.focus();
    }

    onInput(e) {
        this.value = e.target.value;
        this.key = null;
        this.emit('ol-autocomplete-input', { value: this.value });
        const q = this.value.trim();
        if (q.length < 2 || normalizeKey(q)) { this.close(); this._abort?.abort(); return; }
        this._search();
    }

    async search() {
        const q = this.value.trim();
        if (q.length < 2 || normalizeKey(q)) return;
        this._abort?.abort();
        const controller = new AbortController();
        this._abort = controller;
        try {
            const response = await fetch(`${this.spec.endpoint}?${new URLSearchParams({ q, limit: '8' })}`, { signal: controller.signal, headers: { Accept: 'application/json' } });
            const items = response.ok ? await response.json() : [];
            if (controller.signal.aborted) return;
            this._items = Array.isArray(items) ? items : [];
            this._active = -1;
            this._status = this._items.length ? '' : this.noResultsText;
            this._open = true;
        } catch (e) {
            if (e.name !== 'AbortError') { this._items = []; this._status = this.noResultsText; this._open = true; }
        }
    }

    close() {
        this._open = false;
        this._active = -1;
    }

    pick(item) {
        const name = this.spec.primary(item) || item.name || '';
        this.key = item.key;
        this.value = this.clearOnSelect ? '' : name;
        this.close();
        this.emit('ol-autocomplete-select', { key: item.key, name, item });
    }

    onKeydown(e) {
        const n = this._items.length;
        if (e.key === 'ArrowDown' && this._open && n) {
            e.preventDefault();
            this._active = (this._active + 1) % n;
        } else if (e.key === 'ArrowUp' && this._open && n) {
            e.preventDefault();
            this._active = (this._active - 1 + n) % n;
        } else if (e.key === 'Enter') {
            if (this._open && this._active >= 0) { e.preventDefault(); this.pick(this._items[this._active]); return; }
            this.emit('ol-autocomplete-submit', { value: this.value });
        } else if (e.key === 'Escape' && this._open) {
            e.stopPropagation();
            this.close();
        } else if (e.key === 'Tab') {
            this.close();
        }
    }

    emit(name, detail) {
        this.dispatchEvent(new CustomEvent(name, { bubbles: true, composed: true, detail }));
    }

    render() {
        const open = this._open && (this._items.length > 0 || this._status);
        const activeId = (i) => `${this._listId}-${i}`;
        return html`
            <div class="box">
                <input type="text" role="combobox" autocomplete="off" spellcheck="false"
                    class=${this.key ? 'picked' : ''}
                    .value=${this.value}
                    placeholder=${this.placeholder || nothing}
                    aria-label=${this.label || nothing}
                    aria-autocomplete="list"
                    aria-expanded=${open ? 'true' : 'false'}
                    aria-controls=${this._listId}
                    aria-activedescendant=${this._active >= 0 ? activeId(this._active) : nothing}
                    @input=${this.onInput}
                    @keydown=${this.onKeydown}
                    @focus=${() => { if (this._items.length && !this.key) this._open = true; }}>
                ${this.key ? html`<span class="key" aria-hidden="true">${olid(this.key)}</span>` : nothing}
            </div>
            <ul id=${this._listId} role="listbox" aria-label=${this.label || nothing} ?hidden=${!(open && this._items.length)}>
                ${this._items.map((item, i) => html`
                    <li id=${activeId(i)} role="option" aria-selected=${i === this._active ? 'true' : 'false'}
                        @pointerdown=${(e) => e.preventDefault()} @click=${() => this.pick(item)}>
                        <span class="p">${this.spec.primary(item)}</span>
                        ${this.spec.secondary(item) ? html`<span class="s">${this.spec.secondary(item)}</span>` : nothing}
                    </li>`)}
            </ul>
            <div class="status" role="status" ?hidden=${!(open && !this._items.length)}>${this._status}</div>`;
    }
}

customElements.define('ol-autocomplete', OlAutocomplete);
