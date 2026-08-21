import { LitElement, html, css, nothing } from 'lit';
import { ifDefined } from 'lit/directives/if-defined.js';
import { getNextKeyboardFocusIndex } from './utils/keyboard-nav.js';
import './OlPopover.js';

let _idCounter = 0;

/**
 * A trigger paired with a popover menu of mutually-exclusive choices, e.g. a
 * sort menu. Items render as a plain list with the current one highlighted.
 * Composes `<ol-popover>` for the shell.
 *
 * Unlike `<ol-options-popover>` — a form-associated radiogroup whose selection
 * follows focus — this is an action menu: arrows move focus only, and nothing
 * is committed until Enter/click. That's what makes it safe to wire to
 * navigation. WAI-ARIA menu pattern, roving tabindex, one tab stop.
 *
 * @element ol-menu-popover
 *
 * @prop {Array}  items   - `{ value, label, nested? }` objects, as a JSON
 *     attribute or a property. `nested` indents the item under the one above.
 * @prop {String} value   - The active item's `value`. Reflects to attribute.
 * @prop {String} label   - Names the menu, and supplies the default panel
 *     heading and trigger text.
 * @prop {String} heading - Visible heading (default: uppercased `label`).
 *     Empty string omits it.
 *
 * @attr aria-label - Accessible name for the dialog. Falls back to `label`.
 *
 * @fires ol-menu-popover-select - User activated an item, just before close.
 *     Fires even when that item was already current. detail: { value: String }
 *
 * @slot trigger - Custom trigger. When omitted an `<ol-button>` is injected
 *     showing the active item's label. Either way the trigger gets an
 *     `aria-label` of "`label`, current item" so it doesn't announce a bare
 *     value; author one yourself to override.
 *
 * @example
 *   <ol-menu-popover
 *       label="Sort by"
 *       value="relevance"
 *       items='[{"value":"relevance","label":"Relevance"},{"value":"new","label":"Most Recent"}]'
 *   ></ol-menu-popover>
 */
// NOT a FocusableHostMixin host: the focusable is the light-DOM trigger. See
// the mixin's "NOT for" note.
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

        /* No trigger styles here: the default trigger is an <ol-button>,
           which paints itself. */

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
            color: var(--color-text-muted);
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        /* Real <button>s so Enter/Space activate natively; the keydown handler
           only moves focus. UA button box reset so they read as menu rows. */
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
                background: var(--color-hover-overlay);
            }
        }

        /* No radio to carry the state, so the row shows it — same tint and
           weight ol-options-popover uses. */
        .item[aria-checked="true"] {
            background: var(--color-control-selected-bg);
            color: var(--color-link);
            font-weight: 600;
        }

        .item[aria-checked="true"]:hover {
            background: var(--color-control-selected-bg-hover);
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
        // null, not '', so an authored heading="" can mean "no heading" rather
        // than falling through to the label-derived default.
        this.heading = null;
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
        // The trigger is light DOM, outside Lit's template — refresh by hand.
        if (changedProperties.has('label') || changedProperties.has('value') || changedProperties.has('items')) {
            this._updateTriggerLabel();
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
     * Build the default trigger as a real light-DOM child, so it is
     * structurally identical to a consumer-supplied trigger (slotted, focusable
     * from the page, and styled by ol-button itself).
     *
     * @returns {void}
     */
    _createDefaultTrigger() {
        const btn = document.createElement('ol-button');
        btn.setAttribute('slot', 'trigger');
        // ol-button moves this span on upgrade but keeps node identity, so
        // label updates can mutate it in place.
        const text = document.createElement('span');
        // ol-button is nowrap with no max-width; clamp long labels. Inline so
        // it applies inside other components' shadow roots too.
        text.style.cssText = 'display:block;max-width:18ch;overflow:hidden;text-overflow:ellipsis';
        btn.appendChild(text);
        this._defaultTrigger = btn;
        this._defaultTriggerText = text;
        this._updateTriggerLabel();
        this.appendChild(btn);
    }

    /**
     * Names the current choice ("Relevance"), not the category, so the active
     * sort reads without opening. The category goes in aria-label.
     *
     * The aria-label applies to a slotted trigger too, not just the injected
     * one — a consumer that server-renders its own trigger would otherwise
     * announce a bare value ("Relevance") with no clue what it's a value of.
     * A consumer-authored aria-label always wins.
     *
     * @returns {void}
     */
    _updateTriggerLabel() {
        const current = (this.items || []).find(it => it.value === this.value);

        // Only the injected trigger's text is ours to write; a slotted one is
        // the consumer's, and is server-rendered with the current label already.
        if (this._defaultTriggerText) {
            this._defaultTriggerText.textContent = current ? current.label : this.label;
        }

        // Direct children only — that's all a slot can assign anyway.
        const trigger = this._defaultTrigger || this.querySelector(':scope > [slot="trigger"]');
        if (!trigger) return;
        // Never clobber a label the consumer authored.
        if (trigger.hasAttribute('aria-label') && !this._ownsTriggerLabel) return;
        if (current && this.label) {
            trigger.setAttribute('aria-label', `${this.label}, ${current.label}`);
            this._ownsTriggerLabel = true;
        } else if (this._ownsTriggerLabel) {
            trigger.removeAttribute('aria-label');
            this._ownsTriggerLabel = false;
        }
    }

    _renderPanel() {
        const items = this.items || [];
        const heading = this.heading ?? (this.label || '').toUpperCase();
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
        if (e.key !== 'ArrowDown') return;
        // Read openness off the popover rather than tracking it here: Escape and
        // outside-click close it without telling us, so a local flag goes stale
        // after the first dismissal and this stops opening.
        const popover = this.renderRoot?.querySelector('ol-popover');
        if (!popover || popover.open) return;
        e.preventDefault();
        popover.open = true;
    }

    _onPopoverOpen() {
        // Open onto the current item, so Escape lands where they started.
        this._focusIndex = this._currentIndex;
        this.updateComplete.then(() => this._focusItem(this._focusIndex));
    }

    /** Arrows move focus only; nothing is selected until activation. */
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
        if (popover) popover.open = false;
    }
}

if (!customElements.get('ol-menu-popover')) {
    customElements.define('ol-menu-popover', OlMenuPopover);
}
