import { LitElement, html, css, nothing } from 'lit';
import { ifDefined } from 'lit/directives/if-defined.js';
import { focusRing, menuRow } from './control-styles.js';
import { FocusableHostMixin } from './utils/focusable-host-mixin.js';
import { FormAssociatedMixin } from './utils/form-associated-mixin.js';
import { topLayerAttr, promoteToTopLayer, demoteFromTopLayer } from './utils/top-layer.js';

let _idCounter = 0;

/** How long typing must pause before the suggestions are asked for. */
const DEBOUNCE_MS = 300;
/** Gap between the field and its panel, and the least room the panel keeps from a viewport edge. */
const PANEL_GAP = 4;
const PANEL_MAX_HEIGHT = 320;
// Room for a long name and its count on one line.
const PANEL_MIN_WIDTH = 384;

/**
 * A text field that suggests values already in use as you type, and still
 * takes one that isn't.
 *
 * For a field where most answers are a name the catalog already has (a
 * publisher, a series), so that the same name is spelled the same way each
 * time. Suggestions come from `src`, asked with `?q=<text>` and answered as a
 * JSON array of `{ value, count?, similar? }`: `count` shows beside the name,
 * and `similar` marks near misses offered because nothing matched as typed.
 * When the text matches no suggestion, the field says so (`label-new` in the
 * list, `hint-new` under the field) and keeps the text as the value.
 *
 * The input and its listbox share this shadow root, so the combobox's ARIA
 * references resolve. It takes part in forms under `name`, and a `<label for>`
 * pointing at it names the field.
 *
 * @element ol-autocomplete
 *
 * @prop {String} value - The field's text.
 * @prop {String} name - The name the value is submitted under.
 * @prop {String} src - Where suggestions come from; `?q=` is added to it.
 * @prop {Number} minLength - Fewest characters before suggestions are asked
 *     for. Default: 2. Attribute: `min-length`.
 * @prop {String} placeholder - Placeholder for the field.
 * @prop {String} label - Accessible name, when no `<label for>` points here.
 * @prop {Boolean} required - Whether a form needs a value to submit.
 * @prop {Boolean} disabled - Whether the field is disabled.
 * @prop {String} labelSuggestions - Accessible name of the list of
 *     suggestions. Attribute: `label-suggestions`.
 * @prop {String} labelSimilar - Heading over near misses, such as "Did you
 *     mean". Attribute: `label-similar`.
 * @prop {String} labelNew - The last row of the list when the text matches no
 *     suggestion, with `{value}` standing for the text, such as
 *     "Add “{value}” as a new publisher". Attribute: `label-new`.
 * @prop {String} hintNew - Shown under the field, once the list is closed,
 *     while its text matches no suggestion. Attribute: `hint-new`.
 *
 * @fires input - The text changed, by typing or by picking a suggestion.
 * @fires change - A suggestion was picked, or the field was left with new text.
 * @fires ol-autocomplete-select - A row of the list was picked.
 *     detail: { value: String, isNew: Boolean }
 *
 * @cssprop [--ol-autocomplete-max-width=none] - Widest the field grows.
 *
 * @example
 * <label for="publisher">Publisher</label>
 * <ol-autocomplete id="publisher" name="publisher" src="/publishers/_autocomplete"
 *     label-new="Add “{value}” as a new publisher"></ol-autocomplete>
 */
export class OlAutocomplete extends FormAssociatedMixin(FocusableHostMixin(LitElement)) {
    static properties = {
        value: { type: String },
        src: { type: String },
        minLength: { type: Number, attribute: 'min-length' },
        placeholder: { type: String },
        label: { type: String },
        required: { type: Boolean, reflect: true },
        disabled: { type: Boolean, reflect: true },
        labelSuggestions: { type: String, attribute: 'label-suggestions' },
        labelSimilar: { type: String, attribute: 'label-similar' },
        labelNew: { type: String, attribute: 'label-new' },
        hintNew: { type: String, attribute: 'hint-new' },
        _items: { state: true },
        _open: { state: true },
        _active: { state: true },
        _settled: { state: true }
    };

    static styles = [
        menuRow,
        focusRing,
        css`
            :host {
                --ol-autocomplete-max-width: none;

                display: block;
                max-width: var(--ol-autocomplete-max-width);
                font-family: var(--font-family-body);
            }

            .input {
                box-sizing: border-box;
                width: 100%;
                min-height: var(--control-height-medium);
                padding: var(--spacing-inset-xs) var(--spacing-inset-sm);
                border: var(--border-input);
                border-radius: var(--border-radius-input);
                background: var(--color-surface);
                font: inherit;
                font-size: var(--font-size-body-medium);
                color: var(--color-text);
            }

            .input::placeholder {
                color: var(--color-text-muted);
            }

            @media (hover: hover) and (pointer: fine) {
                .input:hover:not(:disabled) {
                    border: var(--border-input-hovered);
                }
            }

            .input:focus-visible {
                border: var(--border-input-focused);
            }

            .input:disabled {
                color: var(--color-text-muted);
                cursor: not-allowed;
            }

            /* --width-breakpoint-tablet: iOS zooms in on focus when the field's font is under 16px. */
            @media (max-width: 767px) {
                .input {
                    font-size: var(--font-size-body-large);
                }
            }

            .hint {
                margin: var(--spacing-stack-xs) 0 0;
                font-size: var(--font-size-body-small);
                color: var(--color-text-secondary);
            }

            /* ── Panel ── */

            .panel {
                position: fixed;
                box-sizing: border-box;
                margin: 0;
                padding: var(--menu-row-inset) 0;
                overflow-y: auto;
                overscroll-behavior: contain;
                border: var(--border-overlay);
                border-radius: var(--border-radius-overlay);
                background: var(--color-surface);
                box-shadow: var(--box-shadow-overlay);
                font-size: var(--font-size-body-medium);
                color: var(--color-text);
                z-index: var(--z-index-dropdown);
            }

            /* The UA sizes and centres [popover]; every property it sets is
               restated so the inline top/left/width place the panel. */
            .panel[popover] {
                inset: auto;
                width: auto;
                height: auto;
            }

            .panel:not(.is-open) {
                display: none;
            }

            .heading {
                padding: var(--spacing-inset-xs) calc(var(--menu-row-inset) + var(--menu-row-padding-inline));
                font-size: var(--font-size-overline);
                font-weight: var(--font-weight-overline);
                letter-spacing: var(--letter-spacing-overline);
                text-transform: var(--text-transform-overline);
                color: var(--color-text-secondary);
            }

            .option {
                gap: var(--spacing-inline-md);
                justify-content: space-between;
            }

            /* The row the arrow keys are on. Focus stays in the field, so the
               row shows it with the fill a pointer's hover would give. */
            .option[aria-selected='true'] {
                background: var(--color-hover-overlay);
            }

            .option-value {
                min-width: 0;
                overflow-wrap: anywhere;
            }

            /* Sets the row that adds the typed text apart from the names in use. */
            .divider {
                margin-block: var(--menu-row-inset);
                border-block-start: var(--border-width) solid var(--color-border-subtle);
            }

            /* Annotations inside a row go back to the regular weight. */
            .option-meta {
                flex: none;
                font-weight: var(--font-weight-regular);
                font-variant-numeric: tabular-nums;
                color: var(--color-text-secondary);
            }
        `
    ];

    constructor() {
        super();
        this.value = '';
        this.src = '';
        this.minLength = 2;
        this.placeholder = '';
        this.label = '';
        this.required = false;
        this.disabled = false;
        this.labelSuggestions = '';
        this.labelSimilar = '';
        this.labelNew = '';
        this.hintNew = '';

        /** @type {Array<{value: String, count?: Number, similar?: Boolean}>} */
        this._items = [];
        this._open = false;
        /** Index into the rows the list shows, or -1 when the arrow keys are on none. */
        this._active = -1;
        /** The text the current `_items` answer, or null while none has been answered. */
        this._settled = null;

        this._uid = ++_idCounter;
        this._debounce = null;
        /** @type {AbortController|null} */
        this._request = null;
        this._defaultValue = '';
        /** The value when the field was last focused or committed, to tell whether leaving it is a change. */
        this._committed = '';
        this._reposition = this._reposition.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        this._defaultValue = this.value;
        this._committed = this.value;
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        clearTimeout(this._debounce);
        this._request?.abort();
        this._stopTracking();
    }

    // ── Form participation ──────────────────────────────────────

    get formAssociatedValue() {
        return this.value;
    }

    formAssociatedReset() {
        this.value = this._defaultValue;
        this._close();
    }

    /** Mirror the inner field's validity, so `required` blocks a submit and the browser's message points at the field. */
    _syncValidity() {
        const input = this._input;
        if (!input || !this._internals?.setValidity) return;
        if (input.validity.valid) this._internals.setValidity({});
        else
            this._internals.setValidity(
                { valueMissing: input.validity.valueMissing, customError: !input.validity.valueMissing },
                input.validationMessage,
                input
            );
    }

    // ── Derived state ───────────────────────────────────────────

    /** @returns {HTMLInputElement|null} */
    get _input() {
        return this.renderRoot?.querySelector('.input') ?? null;
    }

    /** @returns {HTMLElement|null} */
    get _panel() {
        return this.renderRoot?.querySelector('.panel') ?? null;
    }

    get _text() {
        return (this.value || '').trim();
    }

    /**
     * Whether the text is a value no suggestion carries. Only once the
     * suggestions for this exact text have arrived: until then nothing is known.
     * @returns {Boolean}
     */
    get isNew() {
        const text = this._text;
        if (!text || this._settled !== text) return false;
        const folded = text.toLowerCase();
        return !this._items.some(item => !item.similar && item.value.toLowerCase() === folded);
    }

    /** The list's rows: the suggestions, then the typed text itself when it is new. */
    get _rows() {
        const rows = this._items.map(item => ({ ...item, isNew: false }));
        if (this.isNew && this.labelNew) rows.push({ value: this._text, isNew: true });
        return rows;
    }

    // ── Fetching ────────────────────────────────────────────────

    _scheduleFetch() {
        clearTimeout(this._debounce);
        this._request?.abort();
        const text = this._text;
        if (!this.src || text.length < this.minLength) {
            // Assigned only when they change: this also runs from updated(), where a write schedules another update.
            if (this._items.length) this._items = [];
            if (this._settled !== null) this._settled = null;
            this._close();
            return;
        }
        this._debounce = setTimeout(() => this._fetch(text), DEBOUNCE_MS);
    }

    async _fetch(text) {
        const request = new AbortController();
        this._request = request;
        try {
            const response = await fetch(`${this.src}${this.src.includes('?') ? '&' : '?'}q=${encodeURIComponent(text)}`, {
                signal: request.signal,
                headers: { Accept: 'application/json' }
            });
            if (!response.ok) throw new Error(`ol-autocomplete: ${response.status}`);
            const items = await response.json();
            if (request.signal.aborted || text !== this._text) return;
            this._items = Array.isArray(items) ? items.filter(item => item && typeof item.value === 'string') : [];
            this._settled = text;
            this._active = -1;
            // Suggestions only open under a field that is still being typed in.
            if (this._rows.length && this.matches(':focus-within')) this._openPanel();
            else this._close();
        } catch {
            // No suggestions is a plain text field, which still works; an aborted request is a newer keystroke's.
            if (!request.signal.aborted) {
                this._items = [];
                this._settled = null;
                this._close();
            }
        }
    }

    // ── Panel ───────────────────────────────────────────────────

    _openPanel() {
        if (this._open) {
            this.updateComplete.then(this._reposition);
            return;
        }
        this._open = true;
        this.updateComplete.then(() => {
            // Promote before measuring: [popover] is display: none until shown.
            promoteToTopLayer(this._panel);
            this._reposition();
            window.addEventListener('scroll', this._reposition, true);
            window.addEventListener('resize', this._reposition);
        });
    }

    _close() {
        if (!this._open) return;
        this._open = false;
        this._active = -1;
        this._stopTracking();
        demoteFromTopLayer(this._panel);
    }

    _stopTracking() {
        window.removeEventListener('scroll', this._reposition, true);
        window.removeEventListener('resize', this._reposition);
    }

    /** Place the panel under the field, at least as wide as it, or above it when there is more room there. */
    _reposition() {
        const input = this._input;
        const panel = this._panel;
        if (!input || !panel || !this._open) return;
        const field = input.getBoundingClientRect();
        const below = window.innerHeight - field.bottom - PANEL_GAP * 2;
        const above = field.top - PANEL_GAP * 2;
        const wanted = Math.min(panel.scrollHeight + 2, PANEL_MAX_HEIGHT);
        const flip = below < wanted && above > below;
        const height = Math.max(0, Math.min(wanted, flip ? above : below));
        // Never narrower than a long name needs, even under a short field; kept inside the viewport.
        const width = Math.max(field.width, Math.min(PANEL_MIN_WIDTH, window.innerWidth - PANEL_GAP * 2));
        const left = Math.max(PANEL_GAP, Math.min(field.left, window.innerWidth - PANEL_GAP - width));
        panel.style.left = `${left}px`;
        panel.style.width = `${width}px`;
        panel.style.maxHeight = `${height}px`;
        panel.style.top = flip ? `${field.top - PANEL_GAP - height}px` : `${field.bottom + PANEL_GAP}px`;
    }

    // ── Events ──────────────────────────────────────────────────

    _emit(type, detail) {
        this.dispatchEvent(detail ? new CustomEvent(type, { detail, bubbles: true, composed: true }) : new Event(type, { bubbles: true, composed: true }));
    }

    _onInput(event) {
        // The inner event is composed and reaches the page as this element's own `input`.
        this.value = event.target.value;
        this._scheduleFetch();
    }

    _onFocus() {
        this._committed = this.value;
        if (this._rows.length && this._settled === this._text) this._openPanel();
    }

    _onBlur() {
        this._close();
        if (this.value !== this._committed) {
            this._committed = this.value;
            this._emit('change');
        }
    }

    _onKeyDown(event) {
        const rows = this._rows;
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            if (!rows.length) return;
            event.preventDefault();
            if (!this._open) this._openPanel();
            const step = event.key === 'ArrowDown' ? 1 : -1;
            // -1 is "back in the field", one stop in the cycle between the last row and the first.
            const next = this._active + step;
            this._active = next >= rows.length ? -1 : next < -1 ? rows.length - 1 : next;
            this.updateComplete.then(() => this.renderRoot.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' }));
        } else if (event.key === 'Enter') {
            if (this._open && this._active >= 0) {
                event.preventDefault();
                this._select(rows[this._active]);
            } else {
                this._submit(event);
            }
        } else if (event.key === 'Escape' && this._open) {
            // Handled here, so a drawer or dialog around the field stays open.
            event.preventDefault();
            event.stopPropagation();
            this._close();
        }
    }

    /**
     * Enter in the field submits its form, as it does from a native input.
     * The inner input is in this shadow root, outside the form, so the
     * browser's implicit submission never runs for it.
     */
    _submit(event) {
        const form = this.form;
        if (!form) return;
        event.preventDefault();
        this._close();
        const submitter = form.querySelector('button[type="submit"]:not([disabled]), input[type="submit"]:not([disabled])');
        if (submitter) form.requestSubmit(submitter);
        else form.requestSubmit();
    }

    _select(row) {
        this.value = row.value;
        this._committed = row.value;
        // A picked suggestion is a known value; the typed text picked as new stays new.
        if (!row.isNew) {
            this._items = [{ value: row.value, count: row.count }];
            this._settled = row.value.trim();
        }
        clearTimeout(this._debounce);
        this._request?.abort();
        this._close();
        this._emit('input');
        this._emit('change');
        this._emit('ol-autocomplete-select', { value: row.value, isNew: row.isNew });
    }

    // ── Rendering ───────────────────────────────────────────────

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('value') || changed.has('required')) {
            this._syncFormValue();
            this._syncValidity();
        }
        // Set from outside (a suggestion chip, a form reset), the text has no suggestions of its own yet.
        if (changed.has('value') && this._input && this.shadowRoot.activeElement !== this._input && this._settled !== this._text) {
            this._scheduleFetch();
        }
    }

    firstUpdated() {
        this._syncFormValue();
        this._syncValidity();
    }

    _renderRow(row, index) {
        const meta = !row.isNew && typeof row.count === 'number' ? row.count.toLocaleString() : '';
        return html`
            ${row.isNew && index > 0 ? html`<div class="divider" role="presentation"></div>` : nothing}
            <div
                id="option-${this._uid}-${index}"
                class="menu-row option"
                role="option"
                aria-selected=${index === this._active ? 'true' : 'false'}
                @mousedown=${event => event.preventDefault()}
                @click=${() => this._select(row)}
            >
                <span class="option-value">${row.isNew ? this.labelNew.replace('{value}', () => row.value) : row.value}</span>
                ${meta ? html`<span class="option-meta">${meta}</span>` : nothing}
            </div>
        `;
    }

    render() {
        const rows = this._rows;
        const listId = `list-${this._uid}`;
        const hintId = `hint-${this._uid}`;
        // While the list is open its own row says the text is new; the hint is for the field at rest.
        const showHint = this.isNew && this.hintNew && !this._open;
        const similar = rows.length > 0 && this._items.length > 0 && this._items.every(item => item.similar);
        // A <label for> names the host; the inner field needs the same name spelled out.
        const name = this.label || this.labels[0]?.textContent.trim() || undefined;
        return html`
            <input
                class="input focus-ring"
                type="text"
                role="combobox"
                autocomplete="off"
                autocapitalize="off"
                spellcheck="false"
                aria-autocomplete="list"
                aria-expanded=${this._open ? 'true' : 'false'}
                aria-controls=${listId}
                aria-activedescendant=${ifDefined(this._open && this._active >= 0 ? `option-${this._uid}-${this._active}` : undefined)}
                aria-describedby=${ifDefined(showHint ? hintId : undefined)}
                aria-label=${ifDefined(name)}
                placeholder=${ifDefined(this.placeholder || undefined)}
                .value=${this.value || ''}
                ?required=${this.required}
                ?disabled=${this.isDisabled}
                @input=${this._onInput}
                @focus=${this._onFocus}
                @blur=${this._onBlur}
                @keydown=${this._onKeyDown}
            />
            <div
                id=${listId}
                class="panel ${this._open ? 'is-open' : ''}"
                role="listbox"
                aria-label=${ifDefined(this.labelSuggestions || name)}
                popover=${ifDefined(topLayerAttr())}
            >
                ${similar && this.labelSimilar ? html`<div class="heading" role="presentation">${this.labelSimilar}</div>` : nothing}
                ${rows.map((row, index) => this._renderRow(row, index))}
            </div>
            ${showHint ? html`<p class="hint" id=${hintId} role="status">${this.hintNew}</p>` : nothing}
        `;
    }
}

if (!customElements.get('ol-autocomplete')) {
    customElements.define('ol-autocomplete', OlAutocomplete);
}
