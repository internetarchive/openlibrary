import { LitElement, html, css, nothing } from 'lit';
import { ifDefined } from 'lit/directives/if-defined.js';
import { repeat } from 'lit/directives/repeat.js';
import { FocusableHostMixin } from './utils/focusable-host-mixin.js';
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
 * @element ol-options-popover
 *
 * @prop {Array} items - List of `{ value, label, description?, count? }`
 *     objects. Settable as JSON attribute or property.
 * @prop {String} selected - Currently selected `value`, or empty string for
 *     no selection. Reflects to attribute.
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
 * @slot trigger - Optional custom trigger element. When omitted, a styled
 *     default button renders with `label` and a chevron icon.
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
export class OlOptionsPopover extends FocusableHostMixin(LitElement) {
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
            color: var(--accessible-grey);
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

        @media (hover: hover) and (pointer: fine) {
            .item-row:hover {
                background: var(--lightest-grey);
            }
        }

        .item-row:focus-within {
            outline: none;
            background: var(--lightest-grey);
        }

        .item--selected .item-row {
            background: hsla(202, 96%, 37%, 0.08);
        }

        .item--selected .item-row:focus-within,
        .item--selected .item-row:hover {
            background: hsla(202, 96%, 37%, 0.12);
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
            color: var(--link-blue);
            font-weight: 600;
        }

        .item-description {
            display: block;
            margin-top: 2px;
            color: var(--accessible-grey);
            font-size: 12px;
            line-height: 1.35;
        }

        .item--selected .item-description {
            color: var(--link-blue);
        }

        .item-count {
            flex-shrink: 0;
            margin-left: var(--spacing-inline-md);
            color: var(--accessible-grey);
            font-size: 13px;
            font-variant-numeric: tabular-nums;
        }
    `;

    /** Chevron icon for the default trigger */
    static _chevronIcon = html`<svg class="trigger-chevron" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>`;

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

    /**
     * Send focus to the default-trigger button rather than the first
     * focusable in shadow order (which could be a slotted user-provided
     * trigger — but the default-trigger is the one we want when it's there).
     */
    get _focusTarget() {
        return this.shadowRoot?.querySelector('.default-trigger')
            ?? this.querySelector('[slot="trigger"]')
            ?? null;
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
        // Trigger always shows the filter category (e.g. "Availability"); the
        // current selection is communicated by the consumer (e.g. via a chip
        // row above the popover). Consumers needing the selection in the
        // trigger itself can override via the `trigger` slot.
        const selectedItem = (this.items || []).find(it => it.value === this.selected);
        return html`
            <button
                type="button"
                class="default-trigger"
                aria-label=${ifDefined(selectedItem ? `${this.label}, ${selectedItem.label}` : undefined)}
            >
                <span>${this.label}</span>
                ${OlOptionsPopover._chevronIcon}
            </button>
        `;
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
        return html`<li class="item ${isSelected ? 'item--selected' : ''}">
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
        const value = e.target.value;
        if (value !== this.selected) {
            this.selected = value;
            this.dispatchEvent(new CustomEvent('ol-options-popover-change', {
                bubbles: true, composed: true,
                detail: { selected: value },
            }));
        }
        // Close on selection to match native <select> / dropdown filter
        // conventions. <ol-popover> restores focus to the trigger.
        const popover = this.shadowRoot?.querySelector('ol-popover');
        if (popover) popover.open = false;
    }

    _onListKeydown(e) {
        if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp' && e.key !== 'Home' && e.key !== 'End') {
            return;
        }
        const radios = Array.from(this.shadowRoot.querySelectorAll('.item-radio'));
        if (radios.length === 0) return;

        const active = this.shadowRoot.activeElement;
        const idx = radios.indexOf(active);

        let next;
        if (e.key === 'ArrowDown') {
            next = idx === -1 ? 0 : Math.min(idx + 1, radios.length - 1);
        } else if (e.key === 'ArrowUp') {
            next = idx === -1 ? radios.length - 1 : Math.max(idx - 1, 0);
        } else if (e.key === 'Home') {
            next = 0;
        } else if (e.key === 'End') {
            next = radios.length - 1;
        }
        e.preventDefault();
        radios[next].focus();
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
