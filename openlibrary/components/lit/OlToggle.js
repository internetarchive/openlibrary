import { LitElement, html, css, nothing } from 'lit';
import { FocusableHostMixin } from './utils/focusable-host-mixin.js';
import { FormAssociatedMixin } from './utils/form-associated-mixin.js';

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
 * @property {String} variant - Omit for the default (plain) toggle, or
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
    };

    static styles = css`
        :host {
            --toggle-track-width: 36px;
            --toggle-track-height: 20px;
            --toggle-knob-size: 16px;
            --toggle-knob-inset: 2px;
            --toggle-gap: 10px;

            /* Color slots. Default = plain, unchecked toggle; overridden below
               by [checked] and by the [variant="button"] container states. */
            --_toggle-bg: transparent;
            --_toggle-fg: var(--dark-grey);
            --_toggle-sublabel-fg: #777;
            --_toggle-border: transparent;
            --_toggle-track: var(--lighter-grey);
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
            text-align: start;
            cursor: pointer;
            user-select: none;
        }

        .toggle:focus-visible {
            outline: none;
            box-shadow: var(--box-shadow-focus);
        }

        :host([disabled]) .toggle {
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
            transition: background-color 150ms ease;
        }

        .toggle__knob {
            position: absolute;
            top: var(--toggle-knob-inset);
            inset-inline-start: var(--toggle-knob-inset);
            width: var(--toggle-knob-size);
            height: var(--toggle-knob-size);
            border-radius: var(--border-radius-circle);
            background: var(--_toggle-knob);
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
            transition: transform 150ms ease;
        }

        :host([checked]) .toggle__knob {
            transform: translateX(
                calc(var(--toggle-track-width) - var(--toggle-knob-size) - 2 * var(--toggle-knob-inset))
            );
        }

        @media (prefers-reduced-motion: reduce) {
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
            line-height: var(--line-height-chip);
        }

        .toggle__sublabel {
            color: var(--_toggle-sublabel-fg);
            font-weight: 400;
        }

        /* ── Checked (plain): just the track turns blue ─────────────────── */
        :host([checked]) {
            --_toggle-track: var(--primary-blue);
        }

        /* ── Button variant: bordered, raised container ─────────────────── */
        :host([variant="button"]) {
            --_toggle-border: var(--color-border-subtle);
            --_toggle-bg: var(--white);

            display: inline-block;
        }

        :host([variant="button"]) .toggle {
            /* Height-locked to the shared control-height token (like ol-button,
               ol-segmented-control, inputs) so the button lines up exactly with
               its sibling controls in the filter row regardless of its switch
               or text metrics. Setting the outer height (not vertical padding)
               with box-sizing: border-box is what makes the alignment exact —
               see /developers/design ("Control alignment"). Match the sibling
               dropdown trigger's corner radius too. */
            box-sizing: border-box;
            height: var(--control-height-medium);
            padding: 0 var(--spacing-inset-sm);
            border-radius: var(--border-radius-button);
            /* Raised look borrowed from ol-button[variant="secondary"]: a subtle
               drop shadow at rest, plus an inset specular top edge that fades in
               on hover (see the hover rules below). Held in a var so the
               focus-visible rule can re-add the focus ring on top without
               duplicating (or drifting from) the resting shadow. */
            --_toggle-inset-highlight: transparent;
            --_toggle-raised-shadow:
                var(--box-shadow-raised),
                inset 0 1px 0 var(--_toggle-inset-highlight);
            box-shadow: var(--_toggle-raised-shadow);
        }

        /* The base .toggle:focus-visible ring is a single box-shadow, but the
           button variant's own box-shadow rule above outranks it on specificity
           (:host([variant="button"]) .toggle), so the ring never showed. Re-add
           it here at higher specificity, layering the focus ring on top of the
           raised shadow so the lift survives focus too. */
        :host([variant="button"]) .toggle:focus-visible {
            box-shadow: var(--box-shadow-focus), var(--_toggle-raised-shadow);
        }

        /* Button + checked: soft blue tint fill (matching the selected row in
           the sibling ol-select-popover) with a darker primary-blue border and
           dark-blue text, so the active state reads clearly without the harsh
           solid-blue block. The switch track stays solid primary-blue so the
           on-state remains obvious against the pale surface. */
        :host([variant="button"][checked]) {
            --_toggle-bg: hsla(202, 96%, 37%, 0.08);
            --_toggle-fg: var(--link-blue);
            --_toggle-sublabel-fg: var(--primary-blue);
            --_toggle-border: hsla(202, 96%, 37%, 0.35);
            --_toggle-track: var(--primary-blue);
            --_toggle-knob: var(--white);
        }

        /* Hover for the button variant: the neutral button fills with
           --lightest-grey, and the checked button deepens its blue tint and
           border (matching the selected-row hover in ol-select-popover). Both
           states also light up the inset specular top edge — toned to the hover
           fill, the same color-mix ol-button uses for its highlight. */
        @media (hover: hover) and (pointer: fine) {
            :host([variant="button"]:not([disabled])) .toggle:hover {
                --_toggle-bg: var(--lightest-grey);
                /* Nudge the border a touch darker in step with the fill (both
                   drop ~7% in lightness), matching ol-button[variant="secondary"]
                   so the whole control reads as one shape on hover. */
                --_toggle-border: var(--light-grey);
                --_toggle-inset-highlight: color-mix(in srgb, var(--white) 35%, var(--lightest-grey));
            }

            :host([variant="button"][checked]:not([disabled])) .toggle:hover {
                --_toggle-bg: hsla(202, 96%, 37%, 0.12);
                --_toggle-border: hsla(202, 96%, 37%, 0.5);
                --_toggle-inset-highlight: color-mix(in srgb, var(--white) 35%, hsla(202, 96%, 37%, 0.12));
            }
        }
    `;

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
    get formValue() {
        return this.checked ? this.value : null;
    }

    formReset() {
        this.checked = this._defaultChecked;
    }

    firstUpdated() {
        this._syncFormValue();
    }

    updated(changed) {
        if (changed.has('checked') || changed.has('value')) this._syncFormValue();
    }

    _handleClick() {
        if (this.disabled) return;
        this.checked = !this.checked;
        this.dispatchEvent(new CustomEvent('ol-toggle-change', {
            bubbles: true,
            composed: true,
            detail: { checked: this.checked },
        }));
    }

    render() {
        return html`
            <button
                class="toggle"
                type="button"
                role="switch"
                aria-checked=${this.checked ? 'true' : 'false'}
                aria-label=${this.accessibleLabel || nothing}
                ?disabled=${this.disabled}
                @click=${this._handleClick}
            >
                <span class="toggle__switch" aria-hidden="true">
                    <span class="toggle__knob"></span>
                </span>
                <span class="toggle__text">
                    <slot>
                        ${this.label ? html`<span>${this.label}</span>` : nothing}
                        ${this.sublabel ? html`<span class="toggle__sublabel">${this.sublabel}</span>` : nothing}
                    </slot>
                </span>
            </button>
        `;
    }
}

if (!customElements.get('ol-toggle')) {
    customElements.define('ol-toggle', OlToggle);
}
