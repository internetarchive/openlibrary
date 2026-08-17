import { LitElement, css, html, nothing } from 'lit';
import { FocusableHostMixin } from './utils/focusable-host-mixin.js';

/**
 * OLButton - A pure-presentation button primitive.
 *
 * Renders a real <button> (or <a>, when `href` is set) into its shadow root and
 * paints it there, so it can be composed inside any other component — light or
 * shadow DOM — with no global stylesheet involved. Handles variants, sizes,
 * shapes, loading, disabled, and form submission for type="submit" / "reset".
 *
 * Before the JS runs, the host tag is styled by the pre-upgrade rules in
 * `static/css/components/ol-button.css` (keyed on `ol-button:not(:defined)`)
 * so server-rendered buttons look right on first paint. Once defined, the
 * component takes over; the first render is flushed synchronously in the
 * upgrade task so there is no frame in between.
 *
 * Links: set `href` and it renders an <a> instead, styled identically, so a
 * button-shaped navigation CTA ("Read", "Borrow") needs no separate recipe.
 * `disabled` / `loading` on a link drop the href and set aria-disabled.
 *
 * Forms: the element is form-associated, so `type="submit"` submits the
 * enclosing <form> (via `requestSubmit()`, so native validation runs) and
 * `type="reset"` resets it. Because the button itself is not a native submit
 * button: `submit` events have no `event.submitter`, the button contributes no
 * name/value to `FormData`, and `formaction` / `formmethod` are not supported.
 *
 * Contains no application-specific logic, copy, or translations. The
 * consuming page owns what the button *does* — this component only owns
 * how it looks and basic interaction semantics.
 *
 * Disclosure chevron: when the button is wired as a popover/menu trigger,
 * the controller (ol-popover / ol-select-popover) sets `aria-haspopup` and
 * `aria-expanded` on it. CSS keys off those attributes to show a chevron
 * that rotates 180° while expanded — automatically, with no consumer markup.
 * Suppress it with the `no-chevron` attribute.
 *
 * ARIA forwarding: `aria-label` / `aria-haspopup` / `aria-expanded` set on the
 * host are mirrored onto the inner control — on the roleless host they never
 * reach AT. The host keeps them too; the chevron CSS selectors key off it.
 * IDREF attributes (`aria-controls`, `aria-describedby`) are not mirrored:
 * an id in another tree can't resolve from inside this shadow root.
 *
 * @element ol-button
 *
 * @prop {"primary" | "secondary" | "destructive" | "ghost"} variant - Default: "secondary".
 *   Ghost is transparent with no border or lift; it fills on hover.
 * @prop {"small" | "medium" | "large"}            size    - Default: "medium"
 * @prop {"icon" | "circle"} shape - Icon-only: width equals the size's height,
 *   no horizontal padding. "circle" additionally rounds it. Give it an aria-label.
 * @prop {"floating"} elevation - Heavier drop shadow for a control that sits
 *   over content (e.g. a save button on cover art) rather than on the page.
 * @prop {"button" | "submit" | "reset"}           type    - Default: "button"
 * @prop {String} href      - Renders an <a> instead of a <button>.
 * @prop {String} target    - Link target (only with href).
 * @prop {String} rel       - Link rel (only with href).
 * @prop {String} download  - Link download attribute (only with href).
 * @prop {Boolean} loading    - Shows a spinner and disables interaction.
 * @prop {Boolean} disabled   - Disables interaction.
 * @prop {Boolean} fullWidth  - Button expands to fill its container.
 *
 * @attr {Boolean} no-chevron - Suppresses the automatic disclosure chevron
 *   shown when the button is a popover/menu trigger (has `aria-haspopup`).
 * @attr {Boolean} selected - Renders the soft-blue "carries a selection" tint.
 *   Set by ol-select-popover on its disclosure trigger when the user has
 *   picked something; purely visual, no behavior attached.
 *
 * @slot - Default slot carries the button label.
 * @slot icon-start - Leading icon (an inline SVG). Sized to the button's size
 *   (14/16/18px) and separated from the label by a 4px gap only when filled.
 * @slot icon-end - Trailing icon, same treatment. Not for the disclosure
 *   chevron, which is automatic on popover triggers.
 *
 * @csspart control - The inner <button> or <a>.
 * @csspart label - The span wrapping the slotted label.
 *
 * @example
 *   <ol-button variant="destructive" size="medium">Delete</ol-button>
 *   <ol-button type="submit" loading>Saving…</ol-button>
 *   <ol-button variant="primary" href="/borrow/OL1M">Borrow</ol-button>
 *   <ol-button shape="circle" elevation="floating" aria-label="Save">+</ol-button>
 */
export class OLButton extends FocusableHostMixin(LitElement) {
    // Lets `type="submit"` / `type="reset"` reach the enclosing <form> from
    // inside the shadow root, and makes <fieldset disabled> propagate.
    static formAssociated = true;

    static properties = {
        variant: { type: String, reflect: true },
        size: { type: String, reflect: true },
        shape: { type: String, reflect: true },
        elevation: { type: String, reflect: true },
        type: { type: String, reflect: true },
        href: { type: String, reflect: true },
        target: { type: String },
        rel: { type: String },
        download: { type: String },
        loading: { type: Boolean, reflect: true },
        disabled: { type: Boolean, reflect: true },
        fullWidth: { type: Boolean, reflect: true, attribute: 'full-width' },
        // Observed so host changes re-render the mirror; prefixed to avoid
        // shadowing the platform's ARIAMixin accessors. IDREF attributes
        // (aria-controls, aria-describedby) are omitted — see the class doc.
        a11yLabel: { type: String, attribute: 'aria-label' },
        a11yHasPopup: { type: String, attribute: 'aria-haspopup' },
        a11yExpanded: { type: String, attribute: 'aria-expanded' },
    };

    static styles = css`
        :host {
            display: inline-block;
            vertical-align: middle;
        }

        :host([hidden]) {
            display: none;
        }

        :host([full-width]) {
            display: block;
            width: 100%;
        }

        /* Disable pointer events on the host when disabled/loading so :hover
           rules on the inner control don't fire. */
        :host([disabled]),
        :host([loading]) {
            pointer-events: none;
        }

        .control {
            position: relative;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: var(--spacing-inline-md);
            box-sizing: border-box;
            /* Height is a custom property so the icon-only shapes can square up on it. */
            --ol-button-height: var(--control-height-medium);
            height: var(--ol-button-height);
            padding: 0 var(--spacing-md);
            font-family: var(--font-family-button);
            font-size: var(--font-size-body-medium);
            line-height: var(--line-height-control);
            text-align: center;
            white-space: nowrap;
            border: 1px solid var(--color-border-subtle);
            border-radius: var(--border-radius-button);
            background-color: var(--white);
            color: var(--dark-grey);
            /* Strength of the specular top edge. Full on light fills (secondary); the
               dark-filled variants (primary/destructive) dial it down — see below. */
            --control-highlight-strength: 35%;
            box-shadow:
                var(--box-shadow-raised),
                inset 0 1px 0
                    color-mix(
                        in srgb,
                        var(--white) var(--control-highlight-strength),
                        var(--control-surface)
                    );
            cursor: pointer;
            user-select: none;
            text-decoration: none;
            /* Hover color changes are instant (see docs/ai/design.md); only the
               :active press-scale animates. */
            transition: transform 0.08s;
        }

        /* Press feedback — tactile scale on activation. The raised shadow and
           specular highlight stay put through the press. */
        .control:active {
            transform: scale(0.97);
        }

        /* Icon-only shapes are small enough that 3% is sub-pixel; press harder so
           the feedback registers. */
        :host([shape]) .control:active {
            transform: scale(0.93);
        }

        :host([full-width]) .control {
            width: 100%;
        }

        /* Sizes */
        :host([size="small"]) .control {
            --ol-button-height: var(--control-height-small);
            padding: 0 var(--spacing-sm);
            font-size: var(--font-size-label-medium);
        }

        :host([size="large"]) .control {
            --ol-button-height: var(--control-height-large);
            padding: 0 var(--spacing-lg);
            font-size: var(--font-size-body-large);
        }

        /* Icon-only shapes: a square whose side is the size's control height, so it
           sits flush with a same-size text button. The slot holds just the glyph;
           consumers must supply aria-label. */
        :host([shape="icon"]) .control,
        :host([shape="circle"]) .control {
            width: var(--ol-button-height);
            padding: 0;
        }

        :host([shape="circle"]) .control {
            border-radius: var(--border-radius-circle);
        }

        /* Floating — the control sits over content (cover art, a sticky bar) rather
           than on the page surface, so it carries a heavier drop shadow. The inset
           specular edge is unchanged. */
        :host([elevation="floating"]) .control {
            box-shadow:
                var(--box-shadow-floating),
                inset 0 1px 0
                    color-mix(
                        in srgb,
                        var(--white) var(--control-highlight-strength),
                        var(--control-surface)
                    );
        }

        /* Primary — opt-in via variant="primary". */
        :host([variant="primary"]) .control {
            background-color: var(--primary-blue);
            border-color: var(--primary-blue);
            color: var(--white);
            /* Tone the specular highlight to the blue fill instead of pure white, and
               soften it — the white edge reads much louder on a dark fill than on white. */
            --control-surface: var(--primary-blue);
            --control-highlight-strength: 18%;
        }

        /* Secondary is the default (already set above). Explicit selector for clarity. */
        :host([variant="secondary"]) .control {
            background-color: var(--white);
            border-color: var(--color-border-subtle);
            color: var(--dark-grey);
        }

        /* Destructive — solid red fill, mirroring primary but in the danger hue. */
        :host([variant="destructive"]) .control {
            background-color: var(--red);
            border-color: var(--red);
            color: var(--white);
            /* Tone the specular highlight to the red fill and soften it, matching primary. */
            --control-surface: var(--red);
            --control-highlight-strength: 18%;
        }

        /* Ghost — text and icon only, no fill, border, or lift at rest; picks up the
           neutral hover fill. For low-emphasis actions ("Show more", toolbar icons).
           The border stays (transparent) so ghost lines up pixel-for-pixel with
           secondary. */
        :host([variant="ghost"]) .control {
            background-color: transparent;
            border-color: transparent;
            color: var(--dark-grey);
            box-shadow: none;
        }

        /* Selected — a neutral button carrying a selection, e.g. ol-select-popover's
           trigger once a language is picked. Must stay after the variant fills, which
           it ties on specificity. */
        :host([selected]) .control {
            background-color: var(--color-control-selected-bg);
            border-color: var(--color-control-selected-border);
            color: var(--link-blue);
            /* Opaque twin of the tint — a translucent surface washes out the highlight. */
            --control-surface: var(--color-control-selected-surface);
        }

        /* Hover (never fires while disabled/loading — pointer-events is none on
           the host). Hover changes the fill, so --control-surface moves with it —
           otherwise the specular highlight stays toned to the resting color (e.g. a
           blown-out white edge once destructive fills red). Keep
           --control-surface == background-color. */
        @media (hover: hover) and (pointer: fine) {
            :host([variant="secondary"]) .control:hover {
                background-color: var(--color-control-hover);
                /* Nudge the border a touch darker in step with the fill (both drop ~7%
                   in lightness) so the whole button reads as one shape on hover, rather
                   than the fill darkening inside a static outline. */
                border-color: var(--light-grey);
                --control-surface: var(--color-control-hover);
            }

            :host([variant="ghost"]) .control:hover {
                background-color: var(--color-control-hover);
            }

            /* Deepens its tint rather than going grey. After the secondary hover rule,
               which it ties on specificity. */
            :host([selected]) .control:hover {
                background-color: var(--color-control-selected-bg-hover);
                border-color: var(--color-control-selected-border-hover);
                --control-surface: var(--color-control-selected-surface-hover);
            }

            /* The two solid, saturated fills lighten on hover — the mirror image of the
               light secondary control darkening above, and matching the selected chip.
               brightness() carries the fill, border, and inset specular edge together, so
               there's no per-property override or --control-surface retoning to keep in
               sync. The press-scale on :active still reads as the "down" step. */
            :host([variant="primary"]) .control:hover,
            :host([variant="destructive"]) .control:hover {
                filter: brightness(1.1);
            }
        }

        /* Focus ring — delegatesFocus lands focus on the inner control. */
        .control:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: var(--spacing-3xs);
        }

        /* Loading: the label and spinner crossfade. Both are always in the DOM so
           the button width stays stable and we can animate between states. */
        :host([loading]) .control {
            cursor: progress;
        }

        /* Disabled — scoped away from [loading] so the loading state keeps
           full-strength colors while still being non-interactive. Links have no
           :disabled; the component sets aria-disabled and drops the href instead. */
        :host(:not([loading])) button.control:disabled,
        :host(:not([loading])) a.control[aria-disabled="true"] {
            opacity: 0.55;
            cursor: not-allowed;
        }

        /* Label: visible by default; shrinks, blurs, and fades out on loading.
           Flex so the icon slots sit on the box center rather than the text
           baseline. Empty named slots generate no box, so the gap only shows
           up when an icon is slotted. */
        .label {
            --_icon-size: 16px;

            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: var(--spacing-2xs);
            transition:
                opacity 0.24s ease,
                transform 0.24s ease,
                filter 0.24s ease;
        }

        /* Slotted icons take the size's icon dimension regardless of the SVG's own
           width/height attributes, so mixed-source icons line up. */
        ::slotted([slot="icon-start"]),
        ::slotted([slot="icon-end"]) {
            display: block;
            flex-shrink: 0;
            width: var(--_icon-size);
            height: var(--_icon-size);
        }

        :host([size="small"]) .label {
            --_icon-size: 14px;
        }

        :host([size="large"]) .label {
            --_icon-size: 18px;
        }

        :host([loading]) .label {
            opacity: 0;
            transform: scale(0.8);
            filter: blur(2px);
        }

        /* Spinner wrapper: hidden by default; grows, sharpens, and fades in on
           loading. Absolute so it doesn't affect layout. The rotation lives on
           the inner ::before so it doesn't conflict with the scale transition. */
        .spinner {
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            opacity: 0;
            transform: scale(0.4);
            filter: blur(3px);
            pointer-events: none;
            transition:
                opacity 0.24s ease,
                transform 0.24s ease,
                filter 0.24s ease;
        }

        .spinner::before {
            content: "";
            display: block;
            box-sizing: border-box;
            width: 1em;
            height: 1em;
            border: 2px solid currentcolor;
            border-right-color: transparent;
            border-radius: 50%;
        }

        :host([loading]) .spinner {
            opacity: 1;
            transform: scale(1);
            filter: blur(0);
        }

        :host([loading]) .spinner::before {
            animation: ol-button-spin 0.7s linear infinite;
        }

        @keyframes ol-button-spin {
            to {
                transform: rotate(360deg);
            }
        }

        /* Disclosure chevron. Hidden by default; shown only when the button is wired
           as a popover/menu trigger — ol-popover / ol-select-popover set aria-haspopup
           and aria-expanded directly on the trigger element, so the affordance is
           automatic with no consumer markup. Opt out with the \`no-chevron\` attribute.
           The glyph is a mask painted with currentcolor so it matches the label color. */
        .chevron {
            display: none;
        }

        :host([aria-haspopup]) .chevron {
            /* Same glyph as static/images/icons/chevron-down.svg, inlined: this literal
               never passes through the CSS formatter that mangled data URIs in the
               global sheet, and inlining spares a request inside every shadow root. */
            --chevron: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E");

            display: inline-block;
            width: 16px;
            height: 16px;
            flex-shrink: 0;
            /* Tuck against the label and the edge; margins rather than gap/padding so the
               per-size paddings still apply. Nets a 4px gap, 4/8/12px inset by size. */
            margin-left: calc(var(--spacing-2xs) * -1);
            margin-right: calc(var(--spacing-2xs) * -1);
            background: currentcolor;
            transition: transform 150ms ease-out;
            -webkit-mask: var(--chevron) center / 16px no-repeat;
            mask: var(--chevron) center / 16px no-repeat;
        }

        /* Opt out — stays hidden even when wired as a trigger. Comes after the show
           rule (equal specificity) so it wins. */
        :host([no-chevron]) .chevron {
            display: none;
        }

        /* Rotate 180° while the popover is open. aria-expanded="true" only appears on
           disclosure triggers, so [aria-haspopup] is redundant here. */
        :host([aria-expanded="true"]) .chevron {
            transform: rotate(180deg);
        }

        @media (prefers-reduced-motion: reduce) {
            .label,
            .spinner,
            :host([loading]) .label,
            :host([loading]) .spinner {
                transform: none;
                filter: none;
                transition-property: opacity;
            }

            :host([loading]) .spinner::before {
                animation-duration: 2s;
            }

            :host([aria-haspopup]) .chevron {
                transition: none;
            }
        }
    `;

    constructor() {
        super();
        this.variant = 'secondary';
        this.size = 'medium';
        this.type = 'button';
        this.loading = false;
        this.disabled = false;
        this.fullWidth = false;
        // Optional-chained for non-browser contexts where the method is absent.
        this._internals = this.attachInternals?.() ?? null;
    }

    connectedCallback() {
        super.connectedCallback();
        // Flush the first render synchronously within the upgrade task, so the
        // pre-upgrade host styling (ol-button.css, `:not(:defined)`) hands off
        // to the shadow-rendered control with no frame in between.
        this.performUpdate();
    }

    /** @returns {HTMLFormElement|null} The form this button submits or resets. */
    get form() {
        return this._internals?.form ?? null;
    }

    /**
     * Browser callback: an ancestor <fieldset disabled> (or the host's own
     * `disabled` attribute) toggled the element's form-disabled state.
     *
     * @param {boolean} disabled
     * @returns {void}
     */
    formDisabledCallback(disabled) {
        this.disabled = disabled;
    }

    /**
     * The inner <button> has no form owner (it lives in the shadow root), so
     * submit / reset are forwarded to the host's form via ElementInternals.
     * `requestSubmit()` (not `submit()`) so native validation and the form's
     * `submit` event both run.
     *
     * @param {MouseEvent} e
     * @returns {void}
     */
    _onControlClick(e) {
        if (this.loading || this.disabled) {
            e.preventDefault();
            return;
        }
        if (this.href !== undefined && this.href !== null) return;
        const form = this.form;
        if (!form) return;
        if (this.type === 'submit') {
            form.requestSubmit ? form.requestSubmit() : form.submit();
        } else if (this.type === 'reset') {
            form.reset();
        }
    }

    render() {
        // The label and spinner are both always in the DOM so we can crossfade
        // between them via CSS. The spinner has its own element (rather than a
        // ::before on the control) because the scale-in transition and the
        // rotation animation both need `transform` — splitting them across the
        // wrapper span and its ::before keeps them from stepping on each other.
        //
        // The chevron is always rendered but hidden by CSS unless the button is
        // a disclosure trigger (ol-popover / ol-select-popover set aria-haspopup
        // on it). That keeps the trigger affordance automatic — no consumer markup.
        const inert = this.loading || this.disabled;
        const content = html`<span class="label" part="label"><slot name="icon-start"></slot><slot></slot><slot name="icon-end"></slot></span><span class="spinner" aria-hidden="true"></span><span class="chevron" aria-hidden="true"></span>`;

        if (this.href !== undefined && this.href !== null) {
            // A link can't be disabled natively: drop the href (no navigation,
            // no tab stop) and say so via aria-disabled. The host's
            // pointer-events: none handles clicks.
            return html`
                <a
                    class="control"
                    part="control"
                    href=${inert ? nothing : this.href}
                    target=${this.target ?? nothing}
                    rel=${this.rel ?? nothing}
                    download=${this.download ?? nothing}
                    aria-disabled=${inert ? 'true' : nothing}
                    aria-busy=${this.loading ? 'true' : 'false'}
                    aria-label=${this.a11yLabel ?? nothing}
                    aria-haspopup=${this.a11yHasPopup ?? nothing}
                    aria-expanded=${this.a11yExpanded ?? nothing}
                >${content}</a>
            `;
        }

        // Always type="button": the inner element has no form owner, so a
        // native submit type would be inert anyway; _onControlClick forwards
        // submit/reset to the host's form.
        return html`
            <button
                class="control"
                part="control"
                type="button"
                ?disabled=${inert}
                aria-busy=${this.loading ? 'true' : 'false'}
                aria-label=${this.a11yLabel ?? nothing}
                aria-haspopup=${this.a11yHasPopup ?? nothing}
                aria-expanded=${this.a11yExpanded ?? nothing}
                @click=${this._onControlClick}
            >${content}</button>
        `;
    }
}

customElements.define('ol-button', OLButton);
