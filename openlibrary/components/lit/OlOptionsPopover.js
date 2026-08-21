import { LitElement, html, css, nothing } from 'lit';
import { ifDefined } from 'lit/directives/if-defined.js';
import { repeat } from 'lit/directives/repeat.js';
import { FormAssociatedMixin } from './utils/form-associated-mixin.js';
import './OlPopover.js';

let _idCounter = 0;

/**
 * A trigger button paired with a popover containing a single-select list of
 * rich options. Each option can show a label, a description, and a count
 * (e.g. "Readable Books Only — Primary older digitized, preserved, physical
 * books — ~4.6M"). Used for filters with a small fixed set of mutually
 * exclusive choices.
 *
 * Composes `<ol-popover>` for animation, focus trap, mobile tray, and
 * Escape/outside-click dismissal. Use `<ol-select-popover>` instead when
 * the user can pick multiple values or filter a long list.
 *
 * Keyboard follows the WAI-ARIA radiogroup pattern: Arrow/Home/End move focus
 * between options and select the focused one (selection follows focus, staying
 * open); Enter/Space/click commit the choice and close. Native same-name radios
 * provide the roving tab stop, so Tab treats the group as one stop.
 *
 * @element ol-options-popover
 *
 * @prop {Array} items - List of `{ value, label, description?, count?,
 *     nested? }` objects. Settable as JSON attribute or property. `nested: true`
 *     indents the option to show it's a subset of the option above it.
 * @prop {String} selected - Currently selected `value`, or empty string for
 *     no selection. Reflects to attribute.
 * @prop {String} name - Form field name. When set, the selected value submits
 *     with the enclosing `<form>` (see FormAssociatedMixin).
 * @prop {String} label - Default trigger button text (e.g. "Availability").
 * @prop {String} heading - Heading shown above the options list (default:
 *     uppercased `label`).
 *
 * @attr aria-label - Accessible name for the popover dialog. Falls back to
 *     `label` if unset.
 *
 * @fires ol-options-popover-change - Fires when the selection changes.
 *     detail: { selected: String }
 *
 * @slot trigger - Optional custom trigger element. When omitted, an
 *     `<ol-button>` showing `label` is injected (see _createDefaultTrigger);
 *     its disclosure chevron comes from ol-button automatically.
 *
 * @example
 * <ol-options-popover
 *     label="Availability"
 *     items='[
 *       {"value":"all","label":"Full Card Catalog","description":"Info on every book","count":"~50M"},
 *       {"value":"readable","label":"Readable Books Only","description":"Older digitized, preserved","count":"~4.6M"}
 *     ]'
 * ></ol-options-popover>
 */
// NOT a FocusableHostMixin host: the focusable is the light-DOM trigger, not an
// element in this shadow root. See the mixin's "NOT for" note.
export class OlOptionsPopover extends FormAssociatedMixin(LitElement) {
    static properties = {
        items: { type: Array },
        selected: { type: String, reflect: true },
        label: { type: String },
        heading: { type: String },
    };

    static styles = css`
        :host {
            display: inline-block;
            font-family: var(--font-family-body);
        }

        /* The default trigger is a light-DOM <ol-button> (see
           _createDefaultTrigger), which paints itself — there are no trigger
           styles here. That keeps this trigger on the shared control-height
           tokens and gives it ol-button's automatic disclosure chevron, so it
           lines up with <ol-select-popover> beside it. */

        /* ── Panel layout ────────────────────────────────────────── */

        .panel {
            display: flex;
            flex-direction: column;
            min-width: 280px;
            max-width: min(90vw, 400px);
            max-height: min(70vh, 480px);
        }

        .group {
            list-style: none;
            margin: 0;
            padding: var(--spacing-inset-xs) 0;
            overflow-y: auto;
        }

        .group-heading {
            margin: 0;
            padding: var(--spacing-inset-sm) var(--spacing-inset-md) var(--spacing-inset-xs);
            color: var(--color-text-muted);
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        /* ── Items ───────────────────────────────────────────────── */

        .item {
            font-size: 14px;
        }

        .item-row {
            display: flex;
            align-items: flex-start;
            gap: var(--spacing-inline-md);
            padding: var(--spacing-inset-sm) var(--spacing-inset-md);
            cursor: pointer;
            user-select: none;
        }

        /* Nested options are a subset of the option above them; indent the
           whole row so the hierarchy reads at a glance. */
        .item--nested .item-row {
            padding-left: var(--spacing-inset-xl);
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
        }

        .item--selected .item-row:focus-within,
        .item--selected .item-row:hover {
            background: var(--color-control-selected-bg-hover);
        }

        .item-radio {
            flex-shrink: 0;
            width: 16px;
            height: 16px;
            margin: 2px 0 0;
            accent-color: var(--primary-blue);
            cursor: pointer;
        }

        .item-radio:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: 2px;
            border-radius: 50%;
        }

        .item-content {
            flex: 1;
            min-width: 0;
        }

        .item-label {
            display: block;
            color: var(--darker-grey);
            font-weight: 500;
        }

        .item--selected .item-label {
            color: var(--color-link);
            font-weight: 600;
        }

        .item-description {
            display: block;
            margin-top: 2px;
            color: var(--color-text-muted);
            font-size: 12px;
            line-height: 1.35;
        }

        .item--selected .item-description {
            color: var(--color-link);
        }

        .item-count {
            flex-shrink: 0;
            margin-left: var(--spacing-inline-md);
            color: var(--color-text-muted);
            font-size: 13px;
            font-variant-numeric: tabular-nums;
        }
    `;

    constructor() {
        super();
        this.items = [];
        this.selected = '';
        this.label = '';
        this.heading = '';
        this._panelId = `ol-options-popover-${++_idCounter}`;
        this._radioName = `ol-options-popover-radio-${_idCounter}`;
        this._isOpen = false;
        this._pendingFocusFirst = false;
    }

    connectedCallback() {
        super.connectedCallback();
        const hasConsumerTrigger = Array.from(this.children).some(
            el => el !== this._defaultTrigger && el.getAttribute?.('slot') === 'trigger',
        );
        if (!hasConsumerTrigger && !this._defaultTrigger) {
            this._createDefaultTrigger();
        }
        // Capture the authored default selection for <form>.reset().
        if (this._defaultSelected === undefined) this._defaultSelected = this.selected;
    }

    firstUpdated() {
        this._syncFormValue();
    }

    updated(changedProperties) {
        super.updated?.(changedProperties);
        // The default trigger lives in light DOM, outside Lit's template, so it
        // has to be refreshed by hand when anything it displays changes.
        if (changedProperties.has('label') || changedProperties.has('selected') || changedProperties.has('items')) {
            this._updateDefaultTriggerLabel();
        }
        // Keep the form value in step with a programmatic `selected` change
        // (a documented, reflected property). The roving-selection path syncs
        // synchronously in _selectValue; a bare `el.selected = 'x'` only goes
        // through here, so without this the enclosing <form> would submit the
        // stale value. Mirrors OlToggle / OlSegmentedControl.
        if (changedProperties.has('selected')) {
            this._syncFormValue();
        }
    }

    /**
     * @override
     * @returns {string|null} The selected value, or nothing when unselected.
     */
    get formAssociatedValue() {
        return this.selected || null;
    }

    /**
     * @override
     * @returns {void}
     */
    formAssociatedReset() {
        this.selected = this._defaultSelected;
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

    /**
     * Build the default trigger as a real light-DOM child, structurally
     * identical to a consumer-supplied trigger. Mirrors
     * <ol-select-popover>._createDefaultTrigger.
     *
     * @returns {void}
     */
    _createDefaultTrigger() {
        const btn = document.createElement('ol-button');
        btn.setAttribute('slot', 'trigger');
        // ol-button moves this span into its own label wrapper on upgrade, but
        // the node identity survives, so label updates can mutate it in place.
        const text = document.createElement('span');
        // ol-button is nowrap with no max-width, so clamp long labels here.
        // Inline so it applies inside other components' shadow roots too.
        text.style.cssText = 'display:block;max-width:18ch;overflow:hidden;text-overflow:ellipsis';
        btn.appendChild(text);
        this._defaultTrigger = btn;
        this._defaultTriggerText = text;
        this._updateDefaultTriggerLabel();
        this.appendChild(btn);
    }

    /**
     * Label the trigger with the filter category (e.g. "Availability"). The
     * selection is surfaced by the consumer (e.g. a chip row), so the trigger
     * takes no `selected` tint; override via the `trigger` slot to change that.
     *
     * @returns {void}
     */
    _updateDefaultTriggerLabel() {
        const btn = this._defaultTrigger;
        if (!btn || !this._defaultTriggerText) return;
        this._defaultTriggerText.textContent = this.label;
        // Visible text names only the category, so name the choice for AT.
        const selectedItem = (this.items || []).find(it => it.value === this.selected);
        if (selectedItem) {
            btn.setAttribute('aria-label', `${this.label}, ${selectedItem.label}`);
        } else {
            btn.removeAttribute('aria-label');
        }
    }

    _renderPanel() {
        const items = this.items || [];
        const heading = this.heading || (this.label || '').toUpperCase();

        // FIX (WCAG 1.3.1): role="radiogroup" must NOT be on the <ul> because
        // that strips list semantics and makes <li> children invalid in the
        // accessibility tree. Separate the roles: a <div> owns radiogroup +
        // keyboard handler, the <ul> stays a pure list.
        return html`
            <div class="panel">
                <div
                    role="radiogroup"
                    aria-label=${this.label}
                    @keydown=${this._onListKeydown}
                >
                    ${heading ? html`<div class="group-heading" aria-hidden="true">${heading}</div>` : nothing}
                    <ul class="group" id=${this._panelId}>${repeat(items, it => it.value, it => this._renderItem(it))}</ul>
                </div>
            </div>
        `;
    }

    _renderItem(item) {
        const isSelected = item.value === this.selected;
        // FIX (WCAG 1.3.1): no leading whitespace/newline before <li> — Lit
        // template literal whitespace creates real text nodes that accesslint
        // flags as direct text content inside <ul>.
        return html`<li class="item ${isSelected ? 'item--selected' : ''} ${item.nested ? 'item--nested' : ''}">
                <label class="item-row">
                    <input
                        type="radio"
                        class="item-radio"
                        name=${this._radioName}
                        .checked=${isSelected}
                        .value=${item.value}
                        @change=${this._onItemChange}
                    />
                    <span class="item-content">
                        <span class="item-label">${item.label}</span>
                        ${item.description ? html`<span class="item-description">${item.description}</span>` : nothing}
                    </span>
                    ${item.count ? html`<span class="item-count">${item.count}</span>` : nothing}
                </label>
            </li>`;
    }

    // ── Event handlers ───────────────────────────────────────────

    _onTriggerKeydown(e) {
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
        this.setAttribute('data-open', '');

        if (this._pendingFocusFirst) {
            this._pendingFocusFirst = false;
            this._focusSelectedOrFirst();
        }
    }

    _onPopoverClose() {
        this._isOpen = false;
        this._pendingFocusFirst = false;
        this.removeAttribute('data-open');
    }

    _onItemChange(e) {
        // Native change fires from a pointer click (or a tap on the row label).
        // Treat it as an explicit commit: select and close.
        this._commitSelection(e.target.value);
    }

    /**
     * Selection follows focus (WAI-ARIA radiogroup pattern): update the
     * selected value and notify consumers, but keep the popover open so the
     * user can keep arrowing through options. Returns true when the value
     * actually changed.
     */
    _selectValue(value) {
        if (value === this.selected) return false;
        this.selected = value;
        this._syncFormValue();
        this.dispatchEvent(new CustomEvent('ol-options-popover-change', {
            bubbles: true, composed: true,
            detail: { selected: value },
        }));
        return true;
    }

    /**
     * Commit a choice: select it (if not already) and close. Mirrors native
     * <select> / dropdown-filter conventions where activating an option both
     * picks it and dismisses the menu. <ol-popover> restores focus to the
     * trigger.
     */
    _commitSelection(value) {
        this._selectValue(value);
        const popover = this.shadowRoot?.querySelector('ol-popover');
        if (popover) popover.open = false;
    }

    _onListKeydown(e) {
        const radios = Array.from(this.shadowRoot.querySelectorAll('.item-radio'));
        if (radios.length === 0) return;

        const active = this.shadowRoot.activeElement;

        // Enter / Space on the focused radio commits the choice and closes.
        // (Space on an already-checked radio fires no native change, so we
        // handle it here rather than relying on `_onItemChange`.)
        if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
            if (active && active.classList.contains('item-radio')) {
                e.preventDefault();
                this._commitSelection(active.value);
            }
            return;
        }

        if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp' && e.key !== 'Home' && e.key !== 'End') {
            return;
        }
        const idx = radios.indexOf(active);

        let next;
        if (e.key === 'ArrowDown') {
            next = idx === -1 ? 0 : (idx + 1) % radios.length;
        } else if (e.key === 'ArrowUp') {
            next = idx === -1 ? radios.length - 1 : (idx - 1 + radios.length) % radios.length;
        } else if (e.key === 'Home') {
            next = 0;
        } else if (e.key === 'End') {
            next = radios.length - 1;
        }
        e.preventDefault();
        // Roving selection: move focus to the next radio AND check it, staying
        // open. The keyed `repeat` reuses the radio nodes across re-render, so
        // focus is preserved when `_selectValue` flips `.checked`.
        radios[next].focus();
        this._selectValue(radios[next].value);
    }

    _focusSelectedOrFirst() {
        const radios = Array.from(this.shadowRoot.querySelectorAll('.item-radio'));
        if (radios.length === 0) return;
        const selectedRadio = radios.find(r => r.value === this.selected);
        (selectedRadio || radios[0]).focus();
    }
}

if (!customElements.get('ol-options-popover')) {
    customElements.define('ol-options-popover', OlOptionsPopover);
}
