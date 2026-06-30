import { LitElement, html, css, nothing } from 'lit';
import './OlAutocomplete.js';

/**
 * Multi-value language picker for edit forms.
 *
 * Renders a list of `ol-autocomplete` rows and mirrors the current selection
 * into hidden light-DOM `<input>` elements named `${name}--${i}--key`. Those
 * inputs live in the light DOM (not the shadow root) so they submit with the
 * surrounding `<form>`; the edit-form POST handler reads them via
 * `utils.unflatten` (e.g. `edition--languages--0--key`). This mirrors the
 * hidden-input bridge already used by `IdentifiersInput`.
 *
 * @element ol-language-field
 *
 * @prop {String} name - form field prefix, e.g. `edition--languages`
 * @prop {String} sourceUrl - autocomplete endpoint (default `/languages/_autocomplete`)
 * @prop {Boolean} multiple - allow adding / removing / reordering languages
 * @prop {String} placeholder - placeholder text for each input
 * @prop {String} addLabel - label for the "add another" button (multiple only)
 * @prop {String} languages - JSON seed: `[{"key":"/languages/eng","name":"English"}]`
 */
export class OlLanguageField extends LitElement {
    static properties = {
        name: { type: String },
        sourceUrl: { type: String, attribute: 'source-url' },
        multiple: { type: Boolean },
        placeholder: { type: String },
        addLabel: { type: String, attribute: 'add-label' },
        languages: { type: String },
        _langs: { type: Array, state: true },
        _dragIndex: { type: Number, state: true },
    };

    static styles = css`
        :host {
            display: block;
        }

        .row {
            display: flex;
            align-items: center;
            gap: 6px;
            margin-bottom: 6px;
        }

        .row.dragging {
            opacity: 0.5;
        }

        .row ol-autocomplete {
            flex: 1;
        }

        .drag-handle {
            cursor: grab;
            user-select: none;
            touch-action: none;
            color: var(--grey);
            padding: 4px 6px;
            font-size: 16px;
            line-height: 1;
            border-radius: var(--border-radius-sm);
        }

        .drag-handle:active {
            cursor: grabbing;
        }

        .drag-handle:hover {
            color: var(--dark-grey);
        }

        .drag-handle:focus-visible {
            outline: 2px solid var(--primary-blue);
            outline-offset: 1px;
        }

        .icon-btn {
            background: none;
            border: none;
            cursor: pointer;
            padding: 4px 6px;
            font-size: 16px;
            line-height: 1;
            color: var(--grey);
            border-radius: var(--border-radius-sm);
        }

        .icon-btn:hover {
            color: var(--dark-grey);
        }

        .icon-btn:active {
            transform: scale(0.97);
        }

        .icon-btn:disabled {
            opacity: 0.3;
            cursor: default;
        }

        .remove-btn:hover {
            color: var(--red);
        }

        .add-btn {
            background: none;
            border: none;
            cursor: pointer;
            color: var(--primary-blue);
            font: inherit;
            padding: 2px 0;
        }

        .add-btn:hover {
            text-decoration: underline;
        }

        .add-btn:active {
            transform: scale(0.97);
        }
    `;

    constructor() {
        super();
        this.name = '';
        this.sourceUrl = '/languages/_autocomplete';
        this.multiple = false;
        this.placeholder = '';
        this.addLabel = 'Add another language?';
        this.languages = '[]';
        this._langs = [];
        this._dragIndex = null;
        this._seeded = false;
    }

    connectedCallback() {
        super.connectedCallback();
        // Seed working state from the JSON attribute once. Later edits live in
        // `_langs`; re-seeding would clobber them.
        if (this._seeded) return;
        this._seeded = true;
        let parsed;
        try {
            parsed = JSON.parse(this.languages);
        } catch {
            parsed = [];
        }
        this._langs = Array.isArray(parsed) && parsed.length
            ? parsed.map(l => ({ key: l.key || '', name: l.name || '' }))
            : [{ key: '', name: '' }];
    }

    render() {
        return html`
            ${this._langs.map((lang, i) => this._renderRow(lang, i))}
            ${this.multiple ? html`
                <button type="button" class="add-btn" @click="${this._addRow}">+ ${this.addLabel}</button>
            ` : nothing}
        `;
    }

    _renderRow(lang, i) {
        return html`
            <div class="row ${this._dragIndex === i ? 'dragging' : ''}">
                ${this.multiple ? html`
                    <span
                        class="drag-handle"
                        tabindex="0"
                        role="button"
                        aria-label="Drag to reorder language"
                        @pointerdown="${(e) => this._startDrag(i, e)}"
                        @pointermove="${this._onDragMove}"
                        @pointerup="${this._endDrag}"
                        @pointercancel="${this._endDrag}"
                        @keydown="${(e) => this._onHandleKeydown(i, e)}"
                    >&#8801;</span>
                ` : nothing}
                <ol-autocomplete
                    source-url="${this.sourceUrl}"
                    .value="${lang.name || ''}"
                    .selectedKey="${lang.key || ''}"
                    placeholder="${this.placeholder}"
                    @ol-autocomplete-select="${(e) => this._onSelect(i, e)}"
                    @ol-autocomplete-clear="${() => this._onClear(i)}"
                ></ol-autocomplete>
                ${this.multiple ? html`
                    <button type="button" class="icon-btn remove-btn" aria-label="Remove language"
                        ?disabled="${this._langs.length <= 1}" @click="${() => this._removeRow(i)}">&times;</button>
                ` : nothing}
            </div>
        `;
    }

    updated() {
        this._syncHiddenInputs();
    }

    // Rebuild the hidden light-DOM inputs (named `${name}--0--key`, `--1--key`, …)
    // so the form POST sees the current, contiguously-indexed selection.
    _syncHiddenInputs() {
        this.querySelectorAll(':scope > input[data-ol-language-field]').forEach(el => el.remove());
        this._langs.forEach((lang, i) => {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = `${this.name}--${i}--key`;
            input.value = lang.key || '';
            input.setAttribute('data-ol-language-field', '');
            this.appendChild(input);
        });
    }

    _onSelect(i, e) {
        const { key, name } = e.detail;
        this._update(i, { key, name });
    }

    _onClear(i) {
        this._update(i, { key: '', name: '' });
    }

    _update(i, patch) {
        this._langs = this._langs.map((l, idx) => (idx === i ? { ...l, ...patch } : l));
    }

    _addRow() {
        this._langs = [...this._langs, { key: '', name: '' }];
        this.updateComplete.then(() => {
            const fields = this.shadowRoot.querySelectorAll('ol-autocomplete');
            fields[fields.length - 1]?.focusInput();
        });
    }

    _removeRow(i) {
        if (this._langs.length <= 1) return;
        this._langs = this._langs.filter((_, idx) => idx !== i);
    }

    // --- Drag-to-reorder (pointer events: works for mouse and touch) ---

    _startDrag(i, e) {
        if (!this.multiple || this._langs.length <= 1) return;
        // Primary button / touch / pen only.
        if (e.button !== undefined && e.button !== 0) return;
        e.preventDefault();
        this._dragIndex = i;
        e.currentTarget.setPointerCapture(e.pointerId);
    }

    _onDragMove(e) {
        if (this._dragIndex === null) return;
        e.preventDefault();
        const rows = [...this.shadowRoot.querySelectorAll('.row')];
        const y = e.clientY;
        // Count rows (excluding the one being dragged) whose midpoint sits above
        // the pointer — that count is the dragged row's new insertion index.
        let target = 0;
        rows.forEach((row, j) => {
            if (j === this._dragIndex) return;
            const r = row.getBoundingClientRect();
            if (y > r.top + r.height / 2) target++;
        });
        if (target !== this._dragIndex) {
            this._moveTo(this._dragIndex, target);
            this._dragIndex = target;
        }
    }

    _endDrag(e) {
        if (this._dragIndex === null) return;
        try {
            e.currentTarget.releasePointerCapture(e.pointerId);
        } catch {
            // Pointer capture may already be gone; ignore.
        }
        this._dragIndex = null;
    }

    _onHandleKeydown(i, e) {
        if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (i > 0) {
                this._move(i, -1);
                this._refocusHandle(i - 1);
            }
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (i < this._langs.length - 1) {
                this._move(i, 1);
                this._refocusHandle(i + 1);
            }
        }
    }

    _refocusHandle(i) {
        this.updateComplete.then(() => {
            this.shadowRoot.querySelectorAll('.drag-handle')[i]?.focus();
        });
    }

    _moveTo(from, to) {
        const next = [...this._langs];
        const [moved] = next.splice(from, 1);
        next.splice(to, 0, moved);
        this._langs = next;
    }

    _move(i, delta) {
        this._moveTo(i, i + delta);
    }
}

customElements.define('ol-language-field', OlLanguageField);
