import { LitElement, html, svg, css, nothing } from 'lit';
import { ifDefined } from 'lit/directives/if-defined.js';
import { repeat } from 'lit/directives/repeat.js';
import { FocusableHostMixin } from './utils/focusable-host-mixin.js';
import './OlPopover.js';

let _idCounter = 0;

/**
 * The search "Availability" filter: a trigger button paired with a popover of
 * single-select availability options, each with an icon, a label, a
 * description, a count, and a custom circular selection indicator.
 *
 * This is a bespoke component (not the generic `<ol-options-popover>`) because
 * availability has presentation the generic single-select doesn't model:
 *
 *   - a per-option icon column (book, globe, unlock, clock),
 *   - a two-state circular indicator — a *filled* check on the selected option
 *     and a hollow "in scope" check on each option that's a subset of the
 *     selection, and
 *   - a hierarchy where a nested option (e.g. "Free to read now") is contained
 *     by the broader option above it (e.g. "Readable online"), so selecting the
 *     parent marks its children as in-scope.
 *
 * It composes `<ol-popover>` directly for animation, focus trap, mobile tray,
 * and Escape/outside-click dismissal — exactly as `<ol-options-popover>` does —
 * so all of that robust behaviour is reused, not reimplemented.
 *
 * "In scope" is purely visual; the actual selection (the radio's checked state)
 * is the only thing exposed to assistive tech and to consumers.
 *
 * @element ol-availability-filter
 *
 * @prop {Array} items - List of `{ value, label, description?, count?, icon?,
 *     nested? }` objects. Settable as a JSON attribute or a property. `icon` is
 *     one of the known names in `OlAvailabilityFilter._icons` ("book", "globe",
 *     "unlock", "clock"); an unknown/absent name renders no icon. `nested: true`
 *     marks the option as a subset of the nearest non-nested option above it.
 * @prop {String} selected - Currently selected `value`, or empty string for no
 *     selection. Reflects to attribute.
 * @prop {String} label - Default trigger button text (e.g. "Availability").
 * @prop {String} heading - Heading shown above the list (default: uppercased
 *     `label`).
 *
 * @attr aria-label - Accessible name for the popover dialog. Falls back to
 *     `label` if unset.
 *
 * @fires ol-availability-filter-change - Fires when the selection changes.
 *     detail: { selected: String }
 *
 * @slot trigger - Optional custom trigger element. When omitted, a styled
 *     default button renders with `label` and a chevron icon.
 */
export class OlAvailabilityFilter extends FocusableHostMixin(LitElement) {
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
            min-width: 320px;
            max-width: min(92vw, 420px);
            max-height: min(72vh, 520px);
        }

        .group {
            list-style: none;
            margin: 0;
            padding: var(--spacing-inset-xs) 0 var(--spacing-inset-sm);
            overflow-y: auto;
        }

        .group-heading {
            margin: 0;
            padding: var(--spacing-inset-md) var(--spacing-inset-md) var(--spacing-inset-xs);
            color: var(--accessible-grey);
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
        }

        /* ── Items ───────────────────────────────────────────────── */

        .item {
            font-size: 14px;
            position: relative;
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
           whole row (icon included) so the hierarchy reads at a glance. */
        .item--nested .item-row {
            padding-left: var(--spacing-inset-xl);
        }

        /* Dial back the label and icon on nested options so they read as
           secondary to the top-level option they sit under. */
        .item--nested .item-label {
            font-size: 13px;
        }

        .item--nested .item-icon,
        .item--nested .icon-svg {
            width: 20px;
            height: 20px;
        }

        @media (hover: hover) and (pointer: fine) {
            .item-row:hover {
                background: var(--lightest-grey);
            }
        }

        /* The native radio is the focus target but visually hidden, so surface
           focus on the row instead. */
        .item-row:focus-within {
            outline: none;
            background: var(--lightest-grey);
        }

        /* A distinct keyboard-only focus ring (hover uses the tint above). */
        .item-row:has(.item-radio:focus-visible) {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: -2px;
        }

        /* An option that's part of the current selection's scope (a nested
           child of the selected parent) gets a faint tint and no accent bar. */
        .item--in-scope .item-row {
            background: hsla(202, 96%, 37%, 0.045);
        }

        /* The selected option: stronger tint plus a left accent bar. The bar is
           an inset box-shadow so it doesn't shift the row's contents. */
        .item--selected .item-row {
            background: hsla(202, 96%, 37%, 0.09);
            box-shadow: inset 3px 0 0 var(--primary-blue);
        }

        .item--selected .item-row:hover,
        .item--selected .item-row:focus-within {
            background: hsla(202, 96%, 37%, 0.13);
        }

        /* Visually-hidden native radio — kept in the DOM for semantics
           (role=radio via input) and keyboard/arrow-key navigation. */
        .item-radio {
            position: absolute;
            width: 1px;
            height: 1px;
            margin: 0;
            padding: 0;
            opacity: 0;
            pointer-events: none;
        }

        /* ── Icon column ─────────────────────────────────────────── */

        .item-icon {
            flex-shrink: 0;
            width: 24px;
            height: 24px;
            margin-top: 1px;
            color: var(--darker-grey);
        }

        .item--selected .item-icon,
        .item--in-scope .item-icon {
            color: var(--link-blue);
        }

        .icon-svg {
            display: block;
            width: 24px;
            height: 24px;
        }

        /* ── Text content ────────────────────────────────────────── */

        .item-content {
            flex: 1;
            min-width: 0;
            padding-top: 1px;
        }

        .item-label {
            display: block;
            color: var(--darker-grey);
            font-weight: 600;
        }

        .item--selected .item-label,
        .item--in-scope .item-label {
            color: var(--link-blue);
        }

        /* Count and description share one line below the label, separated by a
           middot. Keeping the count here (left) rather than in a right-hand
           column means it never collides with the indicator. */
        .item-meta {
            margin-top: 2px;
            color: var(--accessible-grey);
            font-size: 12px;
            line-height: 1.35;
        }

        .item-count {
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
        }

        .item--selected .item-count,
        .item--in-scope .item-count {
            color: var(--link-blue);
        }

        .item-sep {
            margin: 0 6px;
        }

        /* ── Indicator (right side) ──────────────────────────────── */

        .item-indicator {
            flex-shrink: 0;
            width: 22px;
            height: 22px;
            margin-top: 1px;
        }

        .item--selected .item-indicator {
            color: var(--primary-blue);
        }

        @media (hover: hover) and (pointer: fine) {
            .item-row:hover .item-indicator {
                color: var(--accessible-grey);
            }
        }

        .item--in-scope .item-indicator {
            color: var(--link-blue);
        }

        .indicator-svg {
            display: block;
            width: 22px;
            height: 22px;
        }
    `;

    /** Chevron icon for the default trigger */
    static _chevronIcon = html`<svg class="trigger-chevron" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>`;

    /**
     * Inner SVG geometry for each known option icon, keyed by the `icon` name on
     * an item. Feather-style 24×24 line icons, stroked with `currentColor` so
     * the per-state colour (grey / blue) flows down from `.item-icon`. Built
     * with Lit's `svg` tag (not `html`) so the fragments are created in the SVG
     * namespace when interpolated into the parent `<svg>`.
     */
    static _icons = {
        book: svg`<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>`,
        globe: svg`<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>`,
        unlock: svg`<rect x="3" y="11" width="18" height="10" rx="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/>`,
        clock: svg`<circle cx="12" cy="12" r="10"/><polyline points="12 7 12 12 15.5 14"/>`,
    };

    constructor() {
        super();
        this.items = [];
        this.selected = '';
        this.label = '';
        this.heading = '';
        this._panelId = `ol-availability-filter-${++_idCounter}`;
        this._radioName = `ol-availability-filter-radio-${_idCounter}`;
        this._isOpen = false;
        this._pendingFocusFirst = false;
    }

    /**
     * Send focus to the default-trigger button rather than the first focusable
     * in shadow order (which could be a slotted user-provided trigger — but the
     * default-trigger is the one we want when it's there).
     */
    get _focusTarget() {
        return this.shadowRoot?.querySelector('.default-trigger')
            ?? this.querySelector('[slot="trigger"]')
            ?? null;
    }

    /**
     * Map each nested item's value to the value of the non-nested item directly
     * above it (its "parent"). Used to decide which options are in the selected
     * option's scope. A nested item with no preceding top-level item has no
     * parent entry.
     */
    _parentMap(items) {
        const map = {};
        let lastTop = null;
        for (const it of items) {
            if (it.nested) {
                if (lastTop) map[it.value] = lastTop.value;
            } else {
                lastTop = it;
            }
        }
        return map;
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
        // current selection is surfaced separately (e.g. via a chip row above
        // the popover). Consumers needing the selection in the trigger itself
        // can override via the `trigger` slot.
        const selectedItem = (this.items || []).find(it => it.value === this.selected);
        return html`
            <button
                type="button"
                class="default-trigger"
                aria-label=${ifDefined(selectedItem ? `${this.label}, ${selectedItem.label}` : undefined)}
            >
                <span>${this.label}</span>
                ${OlAvailabilityFilter._chevronIcon}
            </button>
        `;
    }

    _renderPanel() {
        const items = this.items || [];
        const heading = this.heading || (this.label || '').toUpperCase();
        const parents = this._parentMap(items);

        // role="radiogroup" lives on a <div> (with the keyboard handler), NOT on
        // the <ul> — putting it there strips list semantics and makes the <li>
        // children invalid in the accessibility tree (WCAG 1.3.1).
        return html`
            <div class="panel">
                <div
                    role="radiogroup"
                    aria-label=${this.label}
                    @keydown=${this._onListKeydown}
                >
                    ${heading ? html`<div class="group-heading" aria-hidden="true">${heading}</div>` : nothing}
                    <ul class="group" id=${this._panelId}>${repeat(items, it => it.value, it => this._renderItem(it, parents))}</ul>
                </div>
            </div>
        `;
    }

    _renderItem(item, parents) {
        const isSelected = item.value === this.selected;
        // In scope = a nested child whose parent is the selected option. Decked
        // out visually (hollow check, tint) but never reported as selected.
        const inScope = !isSelected && item.nested && parents[item.value] === this.selected;
        const cls = [
            'item',
            isSelected ? 'item--selected' : '',
            inScope ? 'item--in-scope' : '',
            item.nested ? 'item--nested' : '',
        ].filter(Boolean).join(' ');

        // No leading whitespace/newline before <li> — template-literal
        // whitespace creates real text nodes that accesslint flags as direct
        // text content inside <ul> (WCAG 1.3.1).
        return html`<li class="${cls}">
                <label class="item-row">
                    <input
                        type="radio"
                        class="item-radio"
                        name=${this._radioName}
                        .checked=${isSelected}
                        .value=${item.value}
                        @change=${this._onItemChange}
                    />
                    ${this._renderIcon(item.icon)}
                    <span class="item-content">
                        <span class="item-label">${item.label}</span>
                        ${this._renderMeta(item)}
                    </span>
                    <span class="item-indicator">${this._renderIndicator(isSelected, inScope)}</span>
                </label>
            </li>`;
    }

    /**
     * The line below the label: the count and description, in that order,
     * joined by a middot when both are present. Renders nothing if the item has
     * neither.
     */
    _renderMeta(item) {
        if (!item.count && !item.description) return nothing;
        return html`<span class="item-meta">${item.count ? html`<span class="item-count">${item.count}</span>` : nothing}${item.count && item.description ? html`<span class="item-sep" aria-hidden="true">·</span>` : nothing}${item.description ? html`<span class="item-description">${item.description}</span>` : nothing}</span>`;
    }

    _renderIcon(name) {
        const paths = OlAvailabilityFilter._icons[name];
        if (!paths) return html`<span class="item-icon" aria-hidden="true"></span>`;
        return html`<span class="item-icon" aria-hidden="true"><svg class="icon-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">${paths}</svg></span>`;
    }

    /**
     * The circular selection indicator: a filled check for the selected option,
     * a hollow check for an in-scope option, and nothing otherwise (the fixed
     * width of `.item-indicator` keeps the counts column-aligned regardless).
     */
    _renderIndicator(isSelected, inScope) {
        if (isSelected) {
            return html`<svg class="indicator-svg" viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="12" cy="12" r="11" fill="currentColor"/>
                <path d="M7.25 12.5l3 3 6.25-6.75" fill="none" stroke="var(--white)" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>`;
        }
        if (inScope) {
            return html`<svg class="indicator-svg" viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="12" cy="12" r="10.5" fill="none" stroke="currentColor" stroke-width="1.5"/>
                <path d="M7.25 12.5l3 3 6.25-6.75" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>`;
        }
        return html`<svg class="indicator-svg" viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="10.5" fill="none" stroke="var(--color-border-subtle)" stroke-width="1.5"/>
        </svg>`;
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
        if (value === this.selected) return;
        this.selected = value;
        this.dispatchEvent(new CustomEvent('ol-availability-filter-change', {
            bubbles: true, composed: true,
            detail: { selected: value },
        }));
        // Intentionally stay open: unlike a native <select>, the popover shows a
        // hierarchy whose in-scope marks shift with the selection, and in the
        // header modal results update live — closing on each pick is jarring.
        // The user dismisses via Escape, outside-click, or the trigger.
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

customElements.define('ol-availability-filter', OlAvailabilityFilter);
