import { LitElement, html, css, nothing } from 'lit';
import { ifDefined } from 'lit/directives/if-defined.js';
import { getNextKeyboardFocusIndex } from './utils/keyboard-nav.js';
import './OlPopover.js';

let _idCounter = 0;

/**
 * A trigger button paired with a popover menu of mutually-exclusive choices —
 * the sort-menu shape used by YouTube, Reddit, and friends. Items render as a
 * plain list; the current one is highlighted rather than marked with a control.
 *
 * Composes `<ol-popover>` for animation, focus trap, mobile tray, and
 * Escape/outside-click dismissal.
 *
 * Choosing `<ol-options-popover>` vs this:
 *
 *   ol-options-popover is a *form control* — a radiogroup that holds a value,
 *   participates in forms, shows its radios, and moves its selection as you
 *   arrow (selection follows focus). Use it for filters that sit in a form or
 *   whose value is read later.
 *
 *   ol-menu-popover is an *action menu* — arrows move focus only, and
 *   activating an item does something and closes. Nothing is committed until
 *   the user presses Enter or clicks, so it's the right control when acting on
 *   a choice navigates, mutates, or otherwise can't be undone by arrowing back.
 *   It is deliberately not form-associated.
 *
 * Keyboard follows the WAI-ARIA menu pattern: Arrow/Home/End move focus between
 * items without selecting; Enter/Space/click activate the focused item and
 * close. A roving tabindex keeps the menu a single tab stop.
 *
 * @element ol-menu-popover
 *
 * @prop {Array}  items   - `{ value, label, nested? }` objects. Settable as a
 *     JSON attribute or a property. `nested: true` indents the item to show
 *     it's a subset of the item above it.
 * @prop {String} value   - The active item's `value`. Reflects to attribute.
 * @prop {String} label   - Names the menu for assistive tech, and supplies the
 *     default panel heading and trigger text.
 * @prop {String} heading - Visible heading above the items (default:
 *     uppercased `label`). Pass an empty string to omit it.
 *
 * @attr aria-label - Accessible name for the popover dialog. Falls back to
 *     `label` if unset.
 *
 * @fires ol-menu-popover-select - Fires when the user activates an item, just
 *     before the popover closes. Fires even when the activated item was already
 *     the current one — activating is an explicit act, so consumers that want
 *     to skip that case should compare against their own state.
 *     detail: { value: String }
 *
 * @slot trigger - Optional custom trigger element. When omitted, an
 *     `<ol-button>` is injected showing the active item's label (see
 *     _createDefaultTrigger); its disclosure chevron comes from ol-button.
 *
 * @example
 *   <ol-menu-popover
 *       label="Sort by"
 *       value="relevance"
 *       items='[{"value":"relevance","label":"Relevance"},{"value":"new","label":"Most Recent"}]'
 *   ></ol-menu-popover>
 */
// NOT a FocusableHostMixin host: the focusable is the light-DOM trigger, not an
// element in this shadow root. See the mixin's "NOT for" note.
export class OlMenuPopover extends LitElement {
    static properties = {
        items: { type: Array },
        value: { type: String, reflect: true },
        label: { type: String },
        heading: { type: String },
        _focusIndex: { state: true },
    };

    static styles = css`
        :host {
            display: inline-block;
            font-family: var(--font-family-body);
        }

        /* The default trigger is a light-DOM <ol-button> (see
           _createDefaultTrigger), painted by the global ol-button.css — there
           are no trigger styles here. That keeps this trigger on the shared
           control-height tokens and gives it ol-button's disclosure chevron, so
           it lines up with the other popover triggers beside it. */

        .panel {
            display: flex;
            flex-direction: column;
            min-width: 200px;
            max-width: min(90vw, 360px);
            max-height: min(70vh, 480px);
        }

        .menu {
            display: flex;
            flex-direction: column;
            padding: var(--spacing-inset-xs) 0;
            overflow-y: auto;
        }

        .menu-heading {
            margin: 0;
            padding: var(--spacing-inset-sm) var(--spacing-inset-md) var(--spacing-inset-xs);
            color: var(--accessible-grey);
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        /* Items are real <button>s so Enter/Space activate them natively — the
           keydown handler below only has to move focus. Reset the UA button box
           so they read as menu rows, not controls. */
        .item {
            display: block;
            width: 100%;
            box-sizing: border-box;
            margin: 0;
            padding: var(--spacing-inset-sm) var(--spacing-inset-md);
            border: 0;
            background: none;
            color: var(--darker-grey);
            font-family: inherit;
            font-size: 14px;
            font-weight: 500;
            line-height: 1.4;
            text-align: left;
            cursor: pointer;
        }

        /* Nested items are a subset of the item above them. */
        .item--nested {
            padding-left: var(--spacing-inset-xl);
        }

        @media (hover: hover) and (pointer: fine) {
            .item:hover {
                background: var(--lightest-grey);
            }
        }

        /* With no radio to carry the state, the row itself has to show which
           item is current — tint plus weight, the same pair ol-options-popover
           uses for its selected row. */
        .item[aria-checked="true"] {
            background: hsla(202, 96%, 37%, 0.08);
            color: var(--link-blue);
            font-weight: 600;
        }

        .item[aria-checked="true"]:hover {
            background: hsla(202, 96%, 37%, 0.12);
        }

        .item:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: -2px;
        }
    `;

    constructor() {
        super();
        this.items = [];
        this.value = '';
        this.label = '';
        this.heading = '';
        this._focusIndex = 0;
        this._menuId = `ol-menu-popover-${++_idCounter}`;
    }

    connectedCallback() {
        super.connectedCallback();
        const hasConsumerTrigger = Array.from(this.children).some(
            el => el !== this._defaultTrigger && el.getAttribute?.('slot') === 'trigger',
        );
        if (!hasConsumerTrigger && !this._defaultTrigger) {
            this._createDefaultTrigger();
        }
    }

    updated(changedProperties) {
        // The default trigger lives in light DOM, outside Lit's template, so it
        // has to be refreshed by hand when anything it displays changes.
        if (changedProperties.has('label') || changedProperties.has('value') || changedProperties.has('items')) {
            this._updateDefaultTriggerLabel();
        }
    }

    render() {
        return html`
            <ol-popover
                placement="bottom-start"
                aria-label=${ifDefined(this.getAttribute('aria-label') || this.label || undefined)}
                @ol-popover-open=${this._onPopoverOpen}
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
     * Build the default trigger in *light* DOM, so the global ol-button.css can
     * paint it — that sheet can't cross a shadow boundary. Mirrors
     * <ol-options-popover>._createDefaultTrigger.
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
     * A menu trigger names the *current choice* ("Relevance"), not the category
     * — that's the convention these menus follow, and it means the active sort
     * or view is readable without opening anything. The category is still
     * announced, via the trigger's aria-label.
     *
     * @returns {void}
     */
    _updateDefaultTriggerLabel() {
        const btn = this._defaultTrigger;
        if (!btn || !this._defaultTriggerText) return;
        const current = (this.items || []).find(it => it.value === this.value);
        this._defaultTriggerText.textContent = current ? current.label : this.label;
        if (current && this.label) {
            btn.setAttribute('aria-label', `${this.label}, ${current.label}`);
        } else {
            btn.removeAttribute('aria-label');
        }
    }

    _renderPanel() {
        const items = this.items || [];
        const heading = this.heading || (this.label || '').toUpperCase();
        return html`
            <div class="panel">
                <div class="menu" role="menu" aria-label=${ifDefined(this.label || undefined)} id=${this._menuId} @keydown=${this._onKeydown}>
                    ${heading ? html`<div class="menu-heading" aria-hidden="true">${heading}</div>` : nothing}
                    ${items.map((item, i) => this._renderItem(item, i))}
                </div>
            </div>
        `;
    }

    _renderItem(item, i) {
        const isCurrent = item.value === this.value;
        return html`
            <button
                class="item ${item.nested ? 'item--nested' : ''}"
                type="button"
                role="menuitemradio"
                aria-checked=${isCurrent ? 'true' : 'false'}
                tabindex=${i === this._focusIndex ? '0' : '-1'}
                @click=${() => this._activate(item.value)}
            >${item.label}</button>
        `;
    }

    // ── Event handlers ───────────────────────────────────────────

    /** Index of the current value, or 0 when it matches nothing. */
    get _currentIndex() {
        const i = (this.items || []).findIndex(it => it.value === this.value);
        return i === -1 ? 0 : i;
    }

    _onTriggerKeydown(e) {
        if (e.key === 'ArrowDown' && !this._isOpen) {
            e.preventDefault();
            const popover = this.renderRoot?.querySelector('ol-popover');
            if (!popover) return;
            popover.open = true;
        }
    }

    _onPopoverOpen() {
        this._isOpen = true;
        // Open onto the current item, the way a menu should — Escape then lands
        // the user back where they started.
        this._focusIndex = this._currentIndex;
        this.updateComplete.then(() => this._focusItem(this._focusIndex));
    }

    /**
     * Arrows move focus only. Nothing is selected until the user activates an
     * item — that's the whole difference from ol-options-popover, and it's why
     * this control is safe to wire to navigation.
     */
    _onKeydown(e) {
        const items = this.items || [];
        const target = getNextKeyboardFocusIndex(e.key, {
            count: items.length,
            current: this._focusIndex,
            orientation: 'vertical',
            wrap: true,
        });
        if (target === -1) return;
        e.preventDefault();
        this._focusIndex = target;
        this.updateComplete.then(() => this._focusItem(target));
    }

    _focusItem(index) {
        const buttons = this.renderRoot.querySelectorAll('.item');
        buttons[index]?.focus();
    }

    _activate(value) {
        this.value = value;
        this.dispatchEvent(new CustomEvent('ol-menu-popover-select', {
            bubbles: true, composed: true,
            detail: { value },
        }));
        const popover = this.renderRoot?.querySelector('ol-popover');
        if (popover) {
            popover.open = false;
            this._isOpen = false;
        }
    }
}

if (!customElements.get('ol-menu-popover')) {
    customElements.define('ol-menu-popover', OlMenuPopover);
}
