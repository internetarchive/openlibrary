import { LitElement, html, css, nothing } from 'lit';
import { ifDefined } from 'lit/directives/if-defined.js';
import { repeat } from 'lit/directives/repeat.js';
import { FormAssociatedMixin } from './utils/form-associated-mixin.js';
import './OlPopover.js';
import './OLButton.js';

let _idCounter = 0;

/**
 * A trigger button paired with a popover containing a multi-select list of items,
 * an optional filter input, and a "clear selections" footer.
 *
 * Composes `<ol-popover>` internally for animation, focus trap, mobile tray, and
 * Escape/outside-click dismissal. The list is grouped: when items are selected,
 * a "SELECTED" group renders above a "SUGGESTIONS" group. Group membership is
 * reactive — checking an item moves it to the SELECTED group immediately.
 *
 * @element ol-select-popover
 *
 * @prop {Array} items - List of `{ value, label }` objects. Settable as JSON
 *     attribute (`items='[{"value":"en","label":"English"}]'`) or property.
 * @prop {Array} selected - Array of selected `value`s. Reflects to attribute
 *     as JSON.
 * @prop {String} name - Form field name. When set, each selected value submits
 *     with the enclosing `<form>` as a repeated `name` entry (see
 *     FormAssociatedMixin).
 * @prop {String} label - Default trigger button text (e.g. "Language").
 * @prop {Number} searchThreshold - Show the filter input when `items.length`
 *     exceeds this value. Default `8`. Use `0` to always show, a large number
 *     (e.g. `999`) to never show. Attribute: `search-threshold`.
 * @prop {String} placeholder - Filter input placeholder.
 * @prop {String} unselectedHeading - Heading for the list when nothing is
 *     selected (e.g. "LANGUAGES"). Falls back to `suggestionsHeading` if unset.
 * @prop {String} selectedHeading - Heading for the SELECTED group (default
 *     "SELECTED").
 * @prop {String} suggestionsHeading - Heading for the suggestions group when
 *     ≥1 item is selected (default "SUGGESTIONS").
 * @prop {String} clearLabel - Label for the clear-selections button (default
 *     "Clear selections").
 * @prop {String} noMatchesLabel - Empty-state text when the filter has no
 *     matches (default "No matches").
 *
 * @attr aria-label - Accessible name for the popover dialog. Falls back to
 *     `label` if unset.
 *
 * @fires ol-select-popover-change - Fires when the selection changes.
 *     detail: { selected: String[], added: String|null, removed: String|null }
 * @fires ol-select-popover-clear - Fires when the clear-selections button is
 *     clicked. A change event also fires with the cleared selection.
 *
 * @slot trigger - Optional custom trigger element. When omitted, a default
 *     `<ol-button>` is injected, labelled by the current selection: `label`
 *     when nothing is picked, the single item's own label when one is, and
 *     `label (n)` beyond that. It also carries ol-button's `selected` tint
 *     while a selection is active, and its disclosure chevron comes from
 *     ol-button automatically. A custom trigger owns its own label and state.
 *
 * @example
 * <ol-select-popover
 *     label="Language"
 *     placeholder="Filter languages…"
 *     unselected-heading="LANGUAGES"
 *     items='[{"value":"en","label":"English"},{"value":"es","label":"Spanish"}]'
 * ></ol-select-popover>
 *
 * @example
 * <!-- Custom trigger via slot -->
 * <ol-select-popover label="Genre" .items=${genreItems}>
 *   <ol-chip slot="trigger">Genre</ol-chip>
 * </ol-select-popover>
 *
 * @example
 * <!-- Listen for changes -->
 * <ol-select-popover
 *     .items=${items}
 *     @ol-select-popover-change=${e => updateUrl(e.detail.selected)}
 * ></ol-select-popover>
 */
// NOT a FocusableHostMixin host: the focusable is the light-DOM trigger, not an
// element in this shadow root. See the mixin's "NOT for" note.
export class OlSelectPopover extends FormAssociatedMixin(LitElement) {
    static properties = {
        items: { type: Array },
        selected: { type: Array, reflect: true },
        label: { type: String },
        searchThreshold: { type: Number, attribute: 'search-threshold' },
        placeholder: { type: String },
        unselectedHeading: { type: String, attribute: 'unselected-heading' },
        selectedHeading: { type: String, attribute: 'selected-heading' },
        suggestionsHeading: { type: String, attribute: 'suggestions-heading' },
        clearLabel: { type: String, attribute: 'clear-label' },
        noMatchesLabel: { type: String, attribute: 'no-matches-label' },
        _query: { state: true },
    };

    static styles = css`
        :host {
            display: inline-block;
            font-family: var(--font-family-body);
        }

        /* The default trigger is an <ol-button> injected as a light-DOM child
           (see _createDefaultTrigger); it paints itself, including the automatic
           disclosure chevron. No trigger styles live here. A consumer-supplied
           trigger is likewise their own light-DOM element. */

        /* ── Panel layout ────────────────────────────────────────── */

        .panel {
            display: flex;
            flex-direction: column;
            min-width: 240px;
            max-width: min(90vw, 360px);
            max-height: min(70vh, 480px);
        }

        /* ── Filter input ────────────────────────────────────────── */

        .filter {
            position: relative;
            padding: var(--spacing-inset-sm);
            border-bottom: var(--border-divider);
        }

        .filter-input {
            box-sizing: border-box;
            width: 100%;
            padding: var(--spacing-inset-sm) var(--spacing-inset-sm) var(--spacing-inset-sm) 32px;
            background: var(--white);
            border: 1px solid var(--color-border-subtle);
            border-radius: var(--border-radius-input);
            font: inherit;
            font-size: var(--font-size-body-medium);
            color: inherit;
        }

        .filter-input::placeholder {
            color: var(--color-text-muted);
        }

        .filter-input:focus {
            outline: none;
            border-color: var(--color-border-focused);
            box-shadow: 0 0 0 1px var(--color-border-focused);
        }

        /* iOS zooms in on focus when the input font is < 16px; bump it up on
           mobile to suppress that. */
        @media (max-width: 767px) {
            .filter-input { font-size: var(--font-size-body-large); }
        }

        .filter-icon {
            position: absolute;
            top: 50%;
            left: calc(var(--spacing-inset-sm) + 10px);
            width: 14px;
            height: 14px;
            color: var(--color-text-muted);
            pointer-events: none;
            transform: translateY(-50%);
        }

        /* ── Lists ───────────────────────────────────────────────── */

        .list-area {
            flex: 1;
            overflow-y: auto;
            min-height: 0;
        }

        .group {
            list-style: none;
            margin: 0;
            padding: var(--spacing-inset-xs) 0;
        }

        /* Pinned above the suggestions scroll region, like the filter input.
           Caps at ~5 items so a long selection doesn't dominate the panel;
           items scroll within when over the cap. flex-shrink: 0 prevents the
           flex layout from collapsing it below content size — needed because
           overflow-y: auto sets implied min-height to 0. */
        .group--selected {
            flex-shrink: 0;
            max-height: 200px;
            overflow-y: auto;
            border-bottom: var(--border-divider);
        }

        .group-heading {
            margin: 0;
            padding: var(--spacing-inset-sm) var(--spacing-inset-md) var(--spacing-inset-xs);
            color: var(--color-text-muted);
            font-size: var(--font-size-label-medium);
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        .item {
            font-size: var(--font-size-body-medium);
        }

        .item-row {
            display: flex;
            align-items: center;
            gap: var(--spacing-inline-md);
            padding: var(--spacing-inset-sm) var(--spacing-inset-md);
            cursor: pointer;
            user-select: none;
        }

        @media (hover: hover) and (pointer: fine) {
            .item-row:hover {
                background: var(--color-hover-overlay);
            }
        }

        .item-row:focus-within {
            outline: none;
            background: var(--color-hover-overlay);
        }

        .item--selected .item-row {
            background: var(--color-control-selected-bg);
            color: var(--color-link);
            font-weight: 600;
        }

        .item--selected .item-row:focus-within,
        .item--selected .item-row:hover {
            background: var(--color-control-selected-bg-hover);
        }

        .item-checkbox {
            flex-shrink: 0;
            width: 16px;
            height: 16px;
            margin: 0;
            accent-color: var(--primary-blue);
            cursor: pointer;
        }

        .item-checkbox:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 2px;
            border-radius: 2px;
        }

        .item-label {
            flex: 1;
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .empty-state {
            padding: var(--spacing-inset-md);
            text-align: center;
            color: var(--color-text-muted);
            font-size: var(--font-size-body-medium);
        }

        /* ── Footer ──────────────────────────────────────────────── */

        .footer {
            display: flex;
            justify-content: center;
            padding: var(--spacing-inset-sm);
            border-top: var(--border-divider);
        }

        .clear-button {
            padding: var(--spacing-inset-xs) var(--spacing-inset-sm);
            background: transparent;
            border: 1px solid transparent;
            border-radius: var(--border-radius-button);
            color: var(--color-text-muted);
            font: inherit;
            font-size: var(--font-size-label-large);
            font-weight: 500;
            cursor: pointer;
        }

        @media (hover: hover) and (pointer: fine) {
            .clear-button:hover {
                background: var(--color-hover-overlay);
            }
        }

        .clear-button:focus {
            outline: none;
        }

        .clear-button:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 2px;
        }
    `;

    /** Search icon for the filter input */
    static _searchIcon = html`<svg class="filter-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>`;

    constructor() {
        super();
        this.items = [];
        this.selected = [];
        this.label = '';
        this.searchThreshold = 8;
        this.placeholder = 'Filter…';
        this.unselectedHeading = '';
        this.selectedHeading = 'SELECTED';
        this.suggestionsHeading = 'SUGGESTIONS';
        this.clearLabel = 'Clear selections';
        this.noMatchesLabel = 'No matches';
        this._query = '';
        this._panelId = `ol-select-popover-${++_idCounter}`;
        // Mirrors the inner ol-popover's open state via its open/close events.
        this._isOpen = false;
        // One-shot flag set by ArrowDown on the trigger to focus into the list
        // after the popover opens (vs. just focusing the filter on plain click).
        this._pendingFocusFirst = false;
        // Item value to refocus after the next render — set by a toggle that
        // re-homes the item between the selected/suggestions groups (which
        // destroys its DOM node, so its focus is lost).
        this._restoreFocusToValue = null;
    }

    updated(changedProperties) {
        super.updated?.(changedProperties);
        // `items` too: at one selection the trigger shows that item's own label,
        // so a late-arriving catalogue has to re-label it. Mirrors OlOptionsPopover.
        if (changedProperties.has('label') || changedProperties.has('selected') || changedProperties.has('items')) {
            this._updateDefaultTriggerLabel();
        }
        // Ensure bare `el.selected = [...]` is also correctly reflected.
        if (changedProperties.has('selected')) {
            this._syncFormValue();
        }
        // Restore focus to the checkbox of an item that just moved between
        // the selected/suggestions groups (see _onItemToggle). Lit binds the
        // checkbox value via `.value=` (the JS property, not the attribute),
        // so we match by property at lookup time.
        if (this._restoreFocusToValue !== null && changedProperties.has('selected')) {
            const value = this._restoreFocusToValue;
            this._restoreFocusToValue = null;
            const checkboxes = this.shadowRoot?.querySelectorAll('.item-checkbox') ?? [];
            for (const cb of checkboxes) {
                if (cb.value === value) {
                    cb.focus({ preventScroll: true });
                    break;
                }
            }
        }
    }

    render() {
        return html`
            <ol-popover
                placement="bottom-start"
                aria-label="${ifDefined(this.getAttribute('aria-label') || this.label || undefined)}"
                @ol-popover-open=${this._onPopoverOpen}
                @ol-popover-close=${this._onPopoverClose}
            >
                <slot
                    name="trigger"
                    slot="trigger"
                    @keydown=${this._onTriggerKeydown}
                ></slot>
                ${this._renderPanel()}
            </ol-popover>
        `;
    }

    connectedCallback() {
        super.connectedCallback();
        // role="group" allows aria-label on the host (axe: aria-prohibited-attr).
        if (!this.getAttribute('role')) {
            this.setAttribute('role', 'group');
        }
        const hasConsumerTrigger = Array.from(this.children).some(
            el => el !== this._defaultTrigger && el.getAttribute?.('slot') === 'trigger',
        );
        if (!hasConsumerTrigger && !this._defaultTrigger) {
            this._createDefaultTrigger();
        }
        // Capture the authored default selection for <form>.reset().
        if (this._defaultSelected === undefined) this._defaultSelected = [...(this.selected || [])];
    }

    firstUpdated() {
        this._syncFormValue();
    }

    /**
     * @override
     * @returns {FormData|null} One `name` entry per selected value, mirroring a
     *   native `<select multiple>`; nothing when empty.
     */
    get formAssociatedValue() {
        const values = this.selected || [];
        if (values.length === 0 || !this.name) return null;
        const data = new FormData();
        for (const value of values) data.append(this.name, value);
        return data;
    }

    /**
     * @override
     * @returns {void}
     */
    formAssociatedReset() {
        this.selected = [...this._defaultSelected];
        this._updateDefaultTriggerLabel();
    }

    /**
     * Build the default trigger as a real light-DOM child. Injected on connect,
     * before the first render, so it's structurally identical to a
     * consumer-supplied trigger (slotted, focusable from the page). The chevron
     * comes from ol-button.
     *
     * @returns {void}
     */
    _createDefaultTrigger() {
        const btn = document.createElement('ol-button');
        btn.setAttribute('slot', 'trigger');
        // The span stays a light-DOM child (slotted into ol-button), so label
        // updates can mutate it in place.
        const text = document.createElement('span');
        // ol-button is nowrap with no max-width, so clamp long labels here (MARC
        // language names run long). Inline: this element has no stylesheet of
        // its own to reach a slotted node with.
        text.style.cssText = 'display:block;max-width:18ch;overflow:hidden;text-overflow:ellipsis';
        btn.appendChild(text);
        this._defaultTrigger = btn;
        this._defaultTriggerText = text;
        this._updateDefaultTriggerLabel();
        this.appendChild(btn);
    }

    /**
     * Label the trigger by the selection: the field name when nothing is picked
     * ("Language"), the item's own label at one ("English"), "Language (n)"
     * beyond that.
     *
     * @returns {void}
     */
    _updateDefaultTriggerLabel() {
        const btn = this._defaultTrigger;
        if (!btn || !this._defaultTriggerText) return;
        const selected = this.selected || [];
        const count = selected.length;
        const labelFor = (value) => (this.items || []).find(it => it.value === value)?.label ?? value;

        if (count === 0) {
            this._defaultTriggerText.textContent = this.label;
        } else if (count === 1) {
            this._defaultTriggerText.textContent = labelFor(selected[0]);
        } else {
            this._defaultTriggerText.textContent = `${this.label} (${count})`;
        }

        // Blue tint while a selection is active (see ol-button.css).
        btn.toggleAttribute('selected', count > 0);

        // Visible text loses the field name at 1 and the values beyond that, so
        // name both for AT.
        if (count > 0) {
            btn.setAttribute('aria-label', `${this.label}: ${selected.map(labelFor).join(', ')}`);
        } else {
            btn.removeAttribute('aria-label');
        }
    }

    _renderPanel() {
        const showSearch = this._showSearch;
        const selectedSet = new Set(this.selected || []);
        const items = this.items || [];

        const selectedItems = items.filter(it => selectedSet.has(it.value));
        const suggestionItems = items.filter(it => !selectedSet.has(it.value));

        const query = this._query.trim().toLowerCase();
        const filteredSuggestions = query
            ? suggestionItems.filter(it => (it.label || '').toLowerCase().includes(query))
            : suggestionItems;

        const hasSelected = selectedItems.length > 0;
        const suggestionsHeading = hasSelected
            ? this.suggestionsHeading
            : (this.unselectedHeading || this.suggestionsHeading);

        return html`
            <div class="panel">
                ${showSearch ? html`
                    <div class="filter">
                        ${OlSelectPopover._searchIcon}
                        <input
                            type="search"
                            class="filter-input"
                            role="searchbox"
                            aria-controls=${this._panelId}
                            placeholder=${this.placeholder}
                            .value=${this._query}
                            @input=${this._onQueryInput}
                            @keydown=${this._onListKeydown}
                        />
                    </div>
                ` : nothing}
                ${hasSelected ? html`
                    <ul
                        class="group group--selected"
                        role="group"
                        aria-label=${this.selectedHeading}
                        @keydown=${this._onListKeydown}
                    >
                        <li class="group-heading" aria-hidden="true">${this.selectedHeading}</li>
                        ${repeat(selectedItems, it => it.value, it => this._renderItem(it))}
                    </ul>
                ` : nothing}
                <div class="list-area" id=${this._panelId} @keydown=${this._onListKeydown}>
                    <ul
                        class="group group--suggestions"
                        role="group"
                        aria-label=${suggestionsHeading}
                    >
                        <li class="group-heading" aria-hidden="true">${suggestionsHeading}</li>
                        ${filteredSuggestions.length === 0 && query
        ? html`<li class="empty-state">${this.noMatchesLabel}</li>`
        : repeat(filteredSuggestions, it => it.value, it => this._renderItem(it))}
                    </ul>
                </div>
                ${hasSelected ? html`
                    <div class="footer">
                        <button
                            type="button"
                            class="clear-button"
                            @click=${this._onClear}
                        >${this.clearLabel}</button>
                    </div>
                ` : nothing}
            </div>
        `;
    }

    _renderItem(item) {
        const isSelected = (this.selected || []).includes(item.value);
        return html`
            <li class="item ${isSelected ? 'item--selected' : ''}">
                <label class="item-row">
                    <input
                        type="checkbox"
                        class="item-checkbox"
                        .checked=${isSelected}
                        .value=${item.value}
                        @change=${this._onItemToggle}
                    />
                    <span class="item-label">${item.label}</span>
                </label>
            </li>
        `;
    }

    // ── State helpers ────────────────────────────────────────────

    get _showSearch() {
        return (this.items?.length ?? 0) > this.searchThreshold;
    }

    // ── Event handlers ───────────────────────────────────────────

    _onTriggerKeydown(e) {
        // Native button click handles Enter/Space — let it bubble to ol-popover's
        // own click toggle. We only handle ArrowDown, which opens the popover and
        // moves focus into the list (vs. plain click, which focuses the filter).
        if (e.key === 'ArrowDown' && !this._isOpen) {
            e.preventDefault();
            const popover = this.shadowRoot?.querySelector('ol-popover');
            if (!popover) return;
            this._pendingFocusFirst = true;
            popover.open = true;
        }
    }

    _onPopoverOpen() {
        this._isOpen = true;
        this._query = '';

        if (this._pendingFocusFirst) {
            this._pendingFocusFirst = false;
            this._focusFirstItem();
        } else if (!window.matchMedia('(max-width: 767px)').matches) {
            // Desktop: focus the filter so the user can type immediately. Skipped
            // on mobile (matches ol-popover's tray breakpoint) so the soft
            // keyboard doesn't pop up and shrink the visible list area.
            const filter = this.shadowRoot?.querySelector('.filter-input');
            if (filter) filter.focus();
        }
    }

    _onPopoverClose() {
        this._isOpen = false;
        this._pendingFocusFirst = false;
    }

    _onQueryInput(e) {
        this._query = e.target.value;
    }

    _onItemToggle(e) {
        const value = e.target.value;
        const checked = e.target.checked;
        const current = new Set(this.selected || []);
        if (checked) current.add(value); else current.delete(value);
        const nextSelected = (this.items || [])
            .map(it => it.value)
            .filter(v => current.has(v));

        // The toggled item is about to move between the "selected" and
        // "suggestions" groups, which destroys its checkbox DOM node — focus
        // would fall back to <body>. Only restore if the checkbox actually
        // owned focus at toggle time (skips the mouse-click-without-focus
        // path on Safari).
        if (this.shadowRoot?.activeElement === e.target) {
            this._restoreFocusToValue = value;
        }

        this._emitChange(nextSelected, checked ? value : null, checked ? null : value);
    }

    _onClear() {
        if ((this.selected || []).length === 0) return;
        this._emitChange([], null, null);
        this.dispatchEvent(new CustomEvent('ol-select-popover-clear', {
            bubbles: true, composed: true,
        }));
    }

    _onListKeydown(e) {
        if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp' && e.key !== 'Home' && e.key !== 'End') {
            return;
        }
        const checkboxes = Array.from(this.shadowRoot.querySelectorAll('.item-checkbox'));
        if (checkboxes.length === 0) return;

        const active = this.shadowRoot.activeElement;
        const idx = checkboxes.indexOf(active);

        let next;
        if (e.key === 'ArrowDown') {
            next = idx === -1 ? 0 : Math.min(idx + 1, checkboxes.length - 1);
        } else if (e.key === 'ArrowUp') {
            // From a checkbox, ArrowUp at index 0 jumps back to the filter input.
            if (idx === 0) {
                const filter = this.shadowRoot.querySelector('.filter-input');
                if (filter) {
                    e.preventDefault();
                    filter.focus();
                    return;
                }
            }
            next = idx === -1 ? checkboxes.length - 1 : Math.max(idx - 1, 0);
        } else if (e.key === 'Home') {
            next = 0;
        } else if (e.key === 'End') {
            next = checkboxes.length - 1;
        }
        e.preventDefault();
        checkboxes[next].focus();
    }

    _focusFirstItem() {
        const filter = this.shadowRoot.querySelector('.filter-input');
        if (filter) {
            filter.focus();
            return;
        }
        const firstCheckbox = this.shadowRoot.querySelector('.item-checkbox');
        firstCheckbox?.focus();
    }

    _emitChange(nextSelected, added, removed) {
        this.selected = nextSelected;
        this._syncFormValue();
        this.dispatchEvent(new CustomEvent('ol-select-popover-change', {
            bubbles: true, composed: true,
            detail: { selected: nextSelected, added, removed },
        }));
    }
}

if (!customElements.get('ol-select-popover')) {
    customElements.define('ol-select-popover', OlSelectPopover);
}
