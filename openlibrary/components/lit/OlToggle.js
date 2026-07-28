import { LitElement, html, css, nothing } from 'lit';
import { FocusableHostMixin } from './utils/focusable-host-mixin.js';

/**
 * OlToggle - A switch/toggle web component.
 *
 * Renders a sliding switch followed by a bold label and an optional greyed
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
 * @property {String} variant - Omit for the default (plain) toggle, or
 *   "card" for a bordered container that fills with a solid primary-blue
 *   background (white text, like a selected ol-chip) when checked.
 * @property {String} label - Primary (bold) label text.
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
 * <!-- Bordered container that fills blue when on -->
 * <ol-toggle variant="card" label="Readable Only" sublabel="4.6M" checked></ol-toggle>
 *
 * @example
 * <!-- Custom label content via the slot -->
 * <ol-toggle accessible-label="Dark mode">
 *   <strong>Dark mode</strong>
 * </ol-toggle>
 */
export class OlToggle extends FocusableHostMixin(LitElement) {
    static properties = {
        checked: { type: Boolean, reflect: true },
        disabled: { type: Boolean, reflect: true },
        variant: { type: String, reflect: true },
        label: { type: String },
        sublabel: { type: String },
        accessibleLabel: { type: String, attribute: 'accessible-label' },
    };

    static styles = css`
        :host {
            --toggle-track-width: 36px;
            --toggle-track-height: 20px;
            --toggle-knob-size: 16px;
            --toggle-knob-inset: 2px;
            --toggle-gap: 10px;

            /* Color slots. Default = plain, unchecked toggle; overridden below
               by [checked] and by the [variant="card"] container states. */
            --_toggle-bg: transparent;
            --_toggle-fg: var(--dark-grey);
            --_toggle-sublabel-fg: var(--accessible-grey);
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

        .toggle__label {
            font-weight: 700;
        }

        .toggle__sublabel {
            color: var(--_toggle-sublabel-fg);
            font-weight: 400;
        }

        /* ── Checked (plain): just the track turns blue ─────────────────── */
        :host([checked]) {
            --_toggle-track: var(--primary-blue);
        }

        /* ── Card variant: bordered container ───────────────────────────── */
        :host([variant="card"]) {
            --_toggle-border: var(--color-border-subtle);
            --_toggle-bg: var(--white);

            /* Shrink the switch so it no longer out-measures the label's text
               line box. The sibling dropdown trigger is sized by its 14px/1.4
               text (19.6px tall); with the default 20px switch the toggle's
               switch would drive the height instead, making the card ~0.4px
               taller. An 18px track (with a 14px knob) stays under the text
               line so the two controls end up exactly the same height. */
            --toggle-track-height: 18px;
            --toggle-knob-size: 14px;

            display: inline-block;
        }

        :host([variant="card"]) .toggle {
            /* Match the sibling dropdown trigger (ol-select-popover's
               .default-trigger) so the filter row reads as one set of
               equally-sized controls — same padding and corner radius. */
            padding: var(--spacing-inset-xs) var(--spacing-inset-sm);
            border-radius: var(--border-radius-button);
        }

        /* Drive the card's height by the same text metrics as the dropdown
           trigger (14px/1.4) rather than the tighter chip line-height, so the
           two controls compute to an identical height. */
        :host([variant="card"]) .toggle__text {
            line-height: 1.4;
        }

        /* The card sits next to a dropdown whose label is regular weight and
           14px; match it (the toggle's base font-size is already
           --font-size-body-medium = 14px) so the two controls read alike. */
        :host([variant="card"]) .toggle__label {
            font-weight: 400;
        }

        /* Card + checked: soft blue tint fill (matching the selected row in
           the sibling ol-select-popover) with a darker primary-blue border and
           dark-blue text, so the active state reads clearly without the harsh
           solid-blue block. The switch track stays solid primary-blue so the
           on-state remains obvious against the pale surface. */
        :host([variant="card"][checked]) {
            --_toggle-bg: hsla(202, 96%, 37%, 0.08);
            --_toggle-fg: var(--link-blue);
            --_toggle-sublabel-fg: var(--primary-blue);
            --_toggle-border: hsla(202, 96%, 37%, 0.35);
            --_toggle-track: var(--primary-blue);
            --_toggle-knob: var(--white);
        }

        /* Hover backgrounds for the card variant: the neutral card fills with
           --lightest-grey, and the checked card deepens its blue tint and
           border (matching the selected-row hover in ol-select-popover). */
        @media (hover: hover) and (pointer: fine) {
            :host([variant="card"]:not([disabled])) .toggle:hover {
                --_toggle-bg: var(--lightest-grey);
            }

            :host([variant="card"][checked]:not([disabled])) .toggle:hover {
                --_toggle-bg: hsla(202, 96%, 37%, 0.12);
                --_toggle-border: hsla(202, 96%, 37%, 0.5);
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
                        ${this.label ? html`<span class="toggle__label">${this.label}</span>` : nothing}
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
