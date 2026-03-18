import { LitElement, html, css, nothing } from 'lit';

/**
 * A reusable autocomplete input web component.
 *
 * @element ol-autocomplete
 *
 * @prop {String} sourceUrl - API endpoint for autocomplete results (e.g. `/languages/_autocomplete`)
 * @prop {String} value - Display text of current selection
 * @prop {String} selectedKey - Key of current selection (e.g. `/languages/eng`)
 * @prop {String} placeholder - Input placeholder text
 *
 * @fires ol-autocomplete-select - Fired when a result is selected. detail: { key, name }
 * @fires ol-autocomplete-clear - Fired when the input is cleared. detail: {}
 */
export class OlAutocomplete extends LitElement {
    static properties = {
        sourceUrl: { type: String, attribute: 'source-url' },
        value: { type: String },
        selectedKey: { type: String, attribute: 'selected-key' },
        placeholder: { type: String },
        clearable: { type: Boolean },
        _query: { type: String, state: true },
        _results: { type: Array, state: true },
        _isOpen: { type: Boolean, state: true },
        _activeIndex: { type: Number, state: true },
        _debounceTimer: { state: true },
    };

    static styles = css`
        :host {
            display: inline-block;
            position: relative;
            font-family: system-ui, -apple-system, sans-serif;
            font-size: 14px;
        }

        .input-wrapper {
            display: flex;
            align-items: center;
            position: relative;
        }

        input {
            width: 100%;
            box-sizing: border-box;
            padding: 6px 28px 6px 8px;
            border: var(--border-input, 1px solid hsl(0, 0%, 87%));
            border-radius: var(--border-radius-input, 4px);
            font: inherit;
            line-height: 1.4;
            outline: none;
            background: var(--white, #fff);
            color: inherit;
        }

        input:focus {
            border-color: var(--color-border-focused, hsl(202, 96%, 37%));
            box-shadow: var(--box-shadow-focus, 0 0 0 2px hsl(202, 96%, 37%));
        }

        .clear-btn {
            position: absolute;
            right: 4px;
            top: 50%;
            transform: translateY(-50%);
            background: none;
            border: none;
            cursor: pointer;
            padding: 2px 4px;
            font-size: 16px;
            color: var(--grey, hsl(0, 0%, 40%));
            line-height: 1;
            border-radius: 2px;
        }

        .clear-btn:hover {
            color: var(--dark-grey, hsl(0, 0%, 20%));
        }

        .listbox {
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            margin-top: 2px;
            background: var(--white, #fff);
            border: 1px solid var(--color-border-subtle, hsl(0, 0%, 87%));
            border-radius: var(--border-radius-input, 4px);
            box-shadow: 0 4px 12px var(--boxshadow-black, hsla(0, 0%, 0%, 0.15));
            z-index: 10;
            max-height: 200px;
            overflow-y: auto;
            list-style: none;
            margin-block: 2px 0;
            padding: 4px 0;
        }

        .option {
            padding: 6px 8px;
            cursor: pointer;
        }

        .option[aria-selected="true"] {
            background: var(--lightest-grey, hsl(0, 0%, 93%));
        }

        .option:hover {
            background: var(--lightest-grey, hsl(0, 0%, 93%));
        }

        .option mark {
            background: transparent;
            font-weight: 700;
            color: inherit;
        }

        .no-results {
            padding: 6px 8px;
            color: var(--grey, hsl(0, 0%, 40%));
            font-style: italic;
        }
    `;

    constructor() {
        super();
        this.sourceUrl = '';
        this.value = '';
        this.selectedKey = '';
        this.placeholder = '';
        this.clearable = true;
        this._query = '';
        this._results = [];
        this._isOpen = false;
        this._activeIndex = -1;
        this._debounceTimer = null;
    }

    get _listboxId() {
        return 'listbox';
    }

    get _activeDescendant() {
        return this._activeIndex >= 0 ? `option-${this._activeIndex}` : '';
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        clearTimeout(this._debounceTimer);
    }

    render() {
        const showClear = this.clearable && (this.value || this._query);
        return html`
            <div class="input-wrapper">
                <input
                    type="text"
                    role="combobox"
                    autocomplete="off"
                    aria-autocomplete="list"
                    aria-expanded="${this._isOpen}"
                    aria-controls="${this._listboxId}"
                    aria-activedescendant="${this._activeDescendant}"
                    .value="${this.value || this._query}"
                    placeholder="${this.placeholder}"
                    @input="${this._onInput}"
                    @keydown="${this._onKeydown}"
                    @focus="${this._onFocus}"
                    @blur="${this._onBlur}"
                />
                ${showClear ? html`
                    <button
                        class="clear-btn"
                        tabindex="-1"
                        aria-label="Clear"
                        @mousedown="${this._onClear}"
                    >&times;</button>
                ` : nothing}
            </div>
            ${this._isOpen ? html`
                <ul
                    class="listbox"
                    id="${this._listboxId}"
                    role="listbox"
                >
                    ${this._renderOptions()}
                </ul>
            ` : nothing}
        `;
    }

    _renderOptions() {
        if (this._results.length > 0) {
            return this._results.map((r, i) => html`
                <li
                    class="option"
                    id="option-${i}"
                    role="option"
                    aria-selected="${i === this._activeIndex}"
                    @mousedown="${() => this._selectResult(r)}"
                >${this._highlightMatch(r.name, this._query)}</li>
            `);
        }
        if (this._query.length > 0) {
            return html`<li class="no-results">No results</li>`;
        }
        return nothing;
    }

    _onInput(e) {
        const query = e.target.value;
        this._query = query;
        // Clear selection when user types
        if (this.value) {
            this.value = '';
            this.selectedKey = '';
            this.dispatchEvent(new CustomEvent('ol-autocomplete-clear', {
                bubbles: true, composed: true, detail: {}
            }));
        }
        this._activeIndex = -1;

        clearTimeout(this._debounceTimer);
        if (query.trim()) {
            this._debounceTimer = setTimeout(() => this._fetchResults(query), 300);
        } else {
            this._results = [];
            this._isOpen = false;
        }
    }

    _onFocus() {
        if (this._query.trim() && this._results.length > 0 && !this.value) {
            this._isOpen = true;
        }
    }

    _onBlur() {
        // Delay to allow mousedown on option to fire
        setTimeout(() => {
            this._isOpen = false;
            this._activeIndex = -1;
        }, 200);
    }

    _onKeydown(e) {
        if (!this._isOpen) {
            if (e.key === 'ArrowDown' && this._results.length > 0) {
                this._isOpen = true;
                this._activeIndex = 0;
                e.preventDefault();
            }
            return;
        }

        switch (e.key) {
        case 'ArrowDown':
            e.preventDefault();
            this._activeIndex = Math.min(this._activeIndex + 1, this._results.length - 1);
            break;
        case 'ArrowUp':
            e.preventDefault();
            this._activeIndex = Math.max(this._activeIndex - 1, 0);
            break;
        case 'Enter':
            e.preventDefault();
            if (this._activeIndex >= 0 && this._results[this._activeIndex]) {
                this._selectResult(this._results[this._activeIndex]);
            }
            break;
        case 'Escape':
            e.preventDefault();
            this._isOpen = false;
            this._activeIndex = -1;
            break;
        }
    }

    _onClear(e) {
        e.preventDefault();
        this.value = '';
        this.selectedKey = '';
        this._query = '';
        this._results = [];
        this._isOpen = false;
        this._activeIndex = -1;
        this.dispatchEvent(new CustomEvent('ol-autocomplete-clear', {
            bubbles: true, composed: true, detail: {}
        }));
        // Re-focus input
        this.updateComplete.then(() => {
            this.shadowRoot.querySelector('input')?.focus();
        });
    }

    async _fetchResults(query) {
        try {
            const url = `${this.sourceUrl}?q=${encodeURIComponent(query)}&limit=5`;
            const resp = await fetch(url);
            if (!resp.ok) return;
            const data = await resp.json();
            this._results = data;
            this._isOpen = data.length > 0;
            this._activeIndex = -1;
        } catch {
            this._results = [];
            this._isOpen = false;
        }
    }

    _selectResult(result) {
        this.value = result.name;
        this.selectedKey = result.key;
        this._query = '';
        this._results = [];
        this._isOpen = false;
        this._activeIndex = -1;
        this.dispatchEvent(new CustomEvent('ol-autocomplete-select', {
            bubbles: true, composed: true,
            detail: { key: result.key, name: result.name }
        }));
    }

    _highlightMatch(text, query) {
        if (!query) return text;
        const idx = text.toLowerCase().indexOf(query.toLowerCase());
        if (idx === -1) return text;
        const before = text.slice(0, idx);
        const match = text.slice(idx, idx + query.length);
        const after = text.slice(idx + query.length);
        return html`${before}<mark>${match}</mark>${after}`;
    }

    /** Public method to focus the input */
    focusInput() {
        this.updateComplete.then(() => {
            this.shadowRoot.querySelector('input')?.focus();
        });
    }
}

customElements.define('ol-autocomplete', OlAutocomplete);
