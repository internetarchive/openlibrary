import { LitElement, html, css, nothing } from 'lit';
import { ifDefined } from 'lit/directives/if-defined.js';
import { repeat } from 'lit/directives/repeat.js';
import './OlPopover.js';

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
 * @slot trigger - Optional custom trigger element. When omitted, a styled
 *     default button renders showing `label` plus a "(n)" badge when items
 *     are selected and a chevron icon.
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
export class OlSelectPopover extends LitElement {
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

        /* ── Default trigger ─────────────────────────────────────── */

        .default-trigger {
            display: inline-flex;
            align-items: center;
            gap: var(--spacing-inline-sm);
            padding: var(--spacing-inset-xs) var(--spacing-inset-sm);
            background: var(--white);
            border: 1px solid var(--color-border-subtle);
            border-radius: var(--border-radius-button);
            color: var(--darker-grey);
            font: inherit;
            font-size: 14px;
            font-weight: 500;
            line-height: 1.4;
            cursor: pointer;
            white-space: nowrap;
        }

        @media (hover: hover) and (pointer: fine) {
            .default-trigger:hover {
                background: var(--lightest-grey);
            }
        }

        .default-trigger:active {
            transform: scale(0.97);
        }

        .default-trigger:focus {
            outline: none;
        }

        .default-trigger:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        .trigger-count {
            font-variant-numeric: tabular-nums;
        }

        .trigger-chevron {
            display: inline-block;
            width: 16px;
            height: 16px;
            transition: transform 150ms ease-out;
            flex-shrink: 0;
        }

        :host([data-open]) .trigger-chevron {
            transform: rotate(180deg);
        }

        @media (prefers-reduced-motion: reduce) {
            .trigger-chevron {
                transition: none;
            }
        }

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
            border-bottom: 1px solid var(--color-border-subtle);
        }

        .filter-input {
            box-sizing: border-box;
            width: 100%;
            padding: var(--spacing-inset-sm) var(--spacing-inset-sm) var(--spacing-inset-sm) 32px;
            background: var(--white);
            border: 1px solid var(--color-border-subtle);
            border-radius: var(--border-radius-input);
            font: inherit;
            font-size: 14px;
            color: inherit;
        }

        .filter-input::placeholder {
            color: var(--accessible-grey);
        }

        .filter-input:focus {
            outline: none;
            border-color: var(--color-border-focused);
            box-shadow: 0 0 0 1px var(--color-border-focused);
        }

        .filter-icon {
            position: absolute;
            top: 50%;
            left: calc(var(--spacing-inset-sm) + 10px);
            width: 14px;
            height: 14px;
            color: var(--accessible-grey);
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
            border-bottom: 1px solid var(--color-border-subtle);
        }

        .group-heading {
            margin: 0;
            padding: var(--spacing-inset-sm) var(--spacing-inset-md) var(--spacing-inset-xs);
            color: var(--accessible-grey);
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        .item {
            font-size: 14px;
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
                background: var(--icon-link-grey);
            }
        }

        .item-row:focus-within {
            outline: none;
            background: var(--icon-link-grey);
        }

        .item--selected .item-row {
            background: hsla(202, 96%, 37%, 0.08);
            color: var(--link-blue);
            font-weight: 600;
        }

        .item--selected .item-row:focus-within,
        .item--selected .item-row:hover {
            background: hsla(202, 96%, 37%, 0.12);
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
            outline: 2px solid var(--color-focus-ring);
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
            color: var(--accessible-grey);
            font-size: 14px;
        }

        /* ── Footer ──────────────────────────────────────────────── */

        .footer {
            display: flex;
            justify-content: center;
            padding: var(--spacing-inset-sm);
            border-top: 1px solid var(--color-border-subtle);
        }

        .clear-button {
            padding: var(--spacing-inset-xs) var(--spacing-inset-sm);
            background: transparent;
            border: 1px solid transparent;
            border-radius: var(--border-radius-button);
            color: var(--dark-red);
            font: inherit;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
        }

        @media (hover: hover) and (pointer: fine) {
            .clear-button:hover {
                background: hsla(8, 70%, 44%, 0.08);
            }
        }

        .clear-button:focus {
            outline: none;
        }

        .clear-button:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: 2px;
        }
    `;

    /** Chevron icon for the default trigger */
    static _chevronIcon = html`<svg class="trigger-chevron" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>`;

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
                >${this._renderDefaultTrigger()}</slot>
                ${this._renderPanel()}
            </ol-popover>
        `;
    }

    _renderDefaultTrigger() {
        const count = (this.selected || []).length;
        const text = count > 0
            ? `${this.label} (${count})`
            : this.label;
        return html`
            <button
                type="button"
                class="default-trigger"
                aria-label=${ifDefined(count > 0 ? `${this.label}, ${count} selected` : undefined)}
            >
                ${OlSelectPopover._chevronIcon}
                <span>${text}</span>
            </button>
        `;
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
        this.setAttribute('data-open', '');

        if (this._pendingFocusFirst) {
            this._pendingFocusFirst = false;
            this._focusFirstItem();
        } else {
            // Plain open: focus the filter if present, otherwise let ol-popover's
            // panel focus take over for keyboard list scanning.
            const filter = this.shadowRoot?.querySelector('.filter-input');
            if (filter) filter.focus();
        }
    }

    _onPopoverClose() {
        this._isOpen = false;
        this._pendingFocusFirst = false;
        this.removeAttribute('data-open');
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
        this.dispatchEvent(new CustomEvent('ol-select-popover-change', {
            bubbles: true, composed: true,
            detail: { selected: nextSelected, added, removed },
        }));
    }
}

customElements.define('ol-select-popover', OlSelectPopover);
