import { LitElement, html, css, nothing } from 'lit';
import { FocusableHostMixin } from './utils/focusable-host-mixin.js';
import { FormAssociatedMixin } from './utils/form-associated-mixin.js';
import { slotHasContent } from './utils/slot-utils.js';
import { focusRingLayered, pressable, raised } from './control-styles.js';

/**
 * OlToggle - A switch/toggle web component.
 *
 * Renders a sliding switch followed by a label and an optional greyed
 * sublabel. The whole control is a single `role="switch"` button, so the
 * entire surface is clickable and Enter/Space activate it.
 *
 * Unlike `ol-chip` (which leaves selection state to its listener), a toggle
 * owns its on/off state: clicking flips `checked` and fires
 * `ol-toggle-change` with the new value.
 *
 * @element ol-toggle
 *
 * @property {Boolean} checked - On/off state. Default false.
 * @property {Boolean} disabled - Disables interaction. Default false.
 * @property {String} name - Form field name. When set and the toggle is
 *   checked, it submits with the enclosing `<form>` (see FormAssociatedMixin).
 * @property {String} value - Value submitted when checked. Default "on".
 * @property {"button"} variant - Omit for the default (plain) toggle, or
 *   "button" for a bordered, raised container styled like
 *   ol-button[variant="secondary"] (subtle drop shadow, inset specular edge on
 *   hover) that fills with a soft blue tint when checked.
 * @property {String} label - Primary label text.
 * @property {String} sublabel - Secondary greyed text shown after the label.
 * @property {String} accessibleLabel - Override aria-label on the switch.
 *   Needed when supplying label content via the default slot.
 *
 * @slot - Custom label content. Overrides the label/sublabel properties when
 *   provided (they render as the slot's fallback content).
 *
 * @fires ol-toggle-change - Fired on toggle. detail: { checked: Boolean }
 *
 * @example
 * <ol-toggle label="Readable Only" sublabel="4.6M"></ol-toggle>
 *
 * @example
 * <!-- Raised, button-like container that fills blue when on -->
 * <ol-toggle variant="button" label="Readable Only" sublabel="4.6M" checked></ol-toggle>
 *
 * @example
 * <!-- Custom label content via the slot -->
 * <ol-toggle accessible-label="Dark mode">
 *   <strong>Dark mode</strong>
 * </ol-toggle>
 */
export class OlToggle extends FormAssociatedMixin(FocusableHostMixin(LitElement)) {
    static properties = {
        checked: { type: Boolean, reflect: true },
        disabled: { type: Boolean, reflect: true },
        variant: { type: String, reflect: true },
        label: { type: String },
        sublabel: { type: String },
        accessibleLabel: { type: String, attribute: 'accessible-label' },
        value: { type: String },
        // Internal: whether the default slot holds real content — see
        // slotHasContent() for why native <slot> fallback can't be used.
        _hasSlottedLabel: { state: true }
    };

    static styles = [
        raised,
        pressable,
        focusRingLayered,
        css`
            :host {
                --toggle-track-width: 36px;
                --toggle-track-height: 20px;
                --toggle-knob-size: 16px;
                --toggle-knob-inset: 2px;
                --toggle-gap: 10px;

                /* The knob rests at the inline start and travels toward the inline
               end, so the sign flips under RTL. */
                --_toggle-knob-travel: calc(var(--toggle-track-width) - var(--toggle-knob-size) - 2 * var(--toggle-knob-inset));

                /* Color slots. Default = plain, unchecked toggle; overridden below
               by [checked] and by the [variant="button"] container states. */
                --_toggle-bg: transparent;
                --_toggle-fg: var(--color-text);
                --_toggle-sublabel-fg: var(--color-text-muted);
                --_toggle-border: transparent;
                --_toggle-track: var(--color-neutral-object);
                --_toggle-knob: var(--white);

                display: inline-block;
            }

            .toggle {
                display: inline-flex;
                align-items: center;
                gap: var(--toggle-gap);
                margin: 0;
                padding: 0;
                border: var(--border-width) solid var(--_toggle-border);
                border-radius: var(--border-radius-card);
                background: var(--_toggle-bg);
                color: var(--_toggle-fg);
                font-family: var(--font-family-button);
                font-size: var(--font-size-body-medium);
                line-height: var(--line-height-control);
                text-align: start;
                cursor: pointer;
                user-select: none;
            }

            /* The plain switch has no lift to preserve, so its ring hugs the box.
           Scoped to the plain variant: the button variant takes the shared
           .focus-ring-layered, which this would otherwise tie with. */
            :host(:not([variant='button'])) .toggle:focus-visible {
                outline: none;
                box-shadow: var(--box-shadow-focus);
            }

            :host(:disabled) .toggle {
                opacity: 0.5;
                cursor: not-allowed;
            }

            /* ── The switch ─────────────────────────────────────────────────── */
            .toggle__switch {
                position: relative;
                flex-shrink: 0;
                width: var(--toggle-track-width);
                height: var(--toggle-track-height);
                border-radius: var(--border-radius-pill);
                background: var(--_toggle-track);
                transition: background-color var(--duration-fast) var(--ease-state);
            }

            .toggle__knob {
                position: absolute;
                top: var(--toggle-knob-inset);
                inset-inline-start: var(--toggle-knob-inset);
                width: var(--toggle-knob-size);
                height: var(--toggle-knob-size);
                border-radius: var(--border-radius-circle);
                background: var(--_toggle-knob);
                box-shadow: var(--box-shadow-floating);
                transition: transform var(--duration-fast) var(--ease-state);
            }

            /* The knob rests at the inline start and travels toward the inline end,
           so the sign flips under RTL. */
            :host {
                --_toggle-knob-travel: calc(var(--toggle-track-width) - var(--toggle-knob-size) - 2 * var(--toggle-knob-inset));
            }

            :host(:dir(rtl)) {
                --_toggle-knob-travel: calc(-1 * (var(--toggle-track-width) - var(--toggle-knob-size) - 2 * var(--toggle-knob-inset)));
            }

            :host(:dir(rtl)) {
                --_toggle-knob-travel: calc(-1 * (var(--toggle-track-width) - var(--toggle-knob-size) - 2 * var(--toggle-knob-inset)));
            }

            :host([checked]) .toggle__knob {
                transform: translateX(var(--_toggle-knob-travel));
            }

            @media (prefers-reduced-motion: reduce) {
                .toggle,
                .toggle__switch,
                .toggle__knob {
                    transition: none;
                }
            }

            /* ── Label text ─────────────────────────────────────────────────── */
            .toggle__text {
                display: inline-flex;
                align-items: baseline;
                gap: var(--spacing-xs);
            }

            .toggle__sublabel {
                color: var(--_toggle-sublabel-fg);
                font-weight: 400;
            }

            /* ── Checked (plain): just the track turns blue ─────────────────── */
            :host([checked]) {
                --_toggle-track: var(--color-primary);
            }

            /* ── Button variant: bordered, raised container ─────────────────── */
            :host([variant='button']) {
                --_toggle-border: var(--color-control-border);
                --_toggle-bg: var(--color-control-bg);

                display: inline-block;
            }

            :host([variant='button']) .toggle {
                /* Height-locked to the shared control-height token (like ol-button,
               ol-segmented-control, inputs) so the button lines up exactly with
               its sibling controls in the filter row regardless of its switch
               or text metrics. Setting the outer height (not vertical padding)
               with box-sizing: border-box is what makes the alignment exact —
               see /developers/design ("Control alignment"). Match the sibling
               dropdown trigger's inline padding and corner radius too. */
                box-sizing: border-box;
                height: var(--control-height-medium);
                padding: 0 var(--spacing-md);
                border-radius: var(--border-radius-button);
                /* The shared .raised lift, but with the specular top edge off at rest;
               it lights up on hover (below), unlike ol-button where it is always
               on. A transparent surface keeps the 0% mix fully transparent. */
                --control-surface: transparent;
                --control-highlight-strength: 0%;
                /* Hover colors snap in; only the press-scale animates. */
                transition: transform var(--duration-press);
            }

            /* Button + checked: soft blue tint fill (matching the selected row in
           the sibling ol-select-popover) with a darker primary-blue border and
           dark-blue text, so the active state reads clearly without the harsh
           solid-blue block. The switch track stays solid primary-blue so the
           on-state remains obvious against the pale surface. */
            :host([variant='button'][checked]) {
                --_toggle-bg: var(--color-control-selected-bg);
                --_toggle-fg: var(--color-link);
                --_toggle-sublabel-fg: var(--color-primary);
                --_toggle-border: var(--color-control-selected-border);
                --_toggle-track: var(--color-primary);
                --_toggle-knob: var(--white);
            }

            /* Hover for the button variant: the neutral button fills with
           --color-control-hover, and the checked button deepens its blue tint and
           border (matching the selected-row hover in ol-select-popover). Both
           states also light up the inset specular top edge — toned to the hover
           fill at ol-button's strength. */
            @media (hover: hover) and (pointer: fine) {
                :host([variant='button']:not(:disabled)) .toggle:hover {
                    --_toggle-bg: var(--color-control-hover);
                    /* Nudge the border darker in step with the fill, matching
                   ol-button[variant="secondary"] so the whole control reads as
                   one shape on hover. */
                    --_toggle-border: var(--color-border-muted);
                    --control-surface: var(--color-control-hover);
                    --control-highlight-strength: 35%;
                }

                :host([variant='button'][checked]:not(:disabled)) .toggle:hover {
                    --_toggle-bg: var(--color-control-selected-bg-hover);
                    --_toggle-border: var(--color-control-selected-border-hover);
                    /* The opaque twin of the tint — a translucent surface washes
                   out the highlight. */
                    --control-surface: var(--color-control-selected-surface-hover);
                    --control-highlight-strength: 35%;
                }
            }
        `
    ];

    constructor() {
        super();
        this.checked = false;
        this.disabled = false;
        this.variant = null;
        this.label = null;
        this.sublabel = null;
        this.accessibleLabel = null;
        this.value = 'on';
    }

    connectedCallback() {
        super.connectedCallback();
        // Capture the authored default for <form>.reset(). Runs after the
        // attribute→property upgrade, so `checked` reflects the markup.
        if (this._defaultChecked === undefined) this._defaultChecked = this.checked;
    }

    // ── Form participation (FormAssociatedMixin) ─────────────────────────
    // A switch behaves like a checkbox: it submits its `value` only when on,
    // and contributes nothing when off.
    /**
     * @override
     * @returns {string|null} The value when on, nothing when off.
     */
    get formAssociatedValue() {
        return this.checked ? this.value : null;
    }

    /**
     * @override
     * @returns {void}
     */
    formAssociatedReset() {
        this.checked = this._defaultChecked;
    }

    firstUpdated() {
        this._syncFormValue();
    }

    updated(changed) {
        if (changed.has('checked') || changed.has('value')) this._syncFormValue();
    }

    _handleLabelSlotChange(event) {
        this._hasSlottedLabel = slotHasContent(event.target);
    }

    _handleClick() {
        if (this.isDisabled) return;
        this.checked = !this.checked;
        this.dispatchEvent(
            new CustomEvent('ol-toggle-change', {
                bubbles: true,
                composed: true,
                detail: { checked: this.checked }
            })
        );
    }

    render() {
        return html`
            <button
                class="toggle ${this.variant === 'button' ? 'raised pressable focus-ring-layered' : ''}"
                type="button"
                role="switch"
                aria-checked=${this.checked ? 'true' : 'false'}
                aria-label=${this.accessibleLabel || nothing}
                ?disabled=${this.isDisabled}
                @click=${this._handleClick}
            >
                <span class="toggle__switch" aria-hidden="true">
                    <span class="toggle__knob"></span>
                </span>
                <span class="toggle__text">
                    <slot @slotchange=${this._handleLabelSlotChange}></slot>
                    ${
                        this._hasSlottedLabel
                            ? nothing
                            : html`
                                  ${this.label ? html`<span>${this.label}</span>` : nothing}
                                  ${this.sublabel ? html`<span class="toggle__sublabel">${this.sublabel}</span>` : nothing}
                              `
                    }
                </span>
            </button>
        `;
    }
}

if (!customElements.get('ol-toggle')) {
    customElements.define('ol-toggle', OlToggle);
}
