import { LitElement, css, html, nothing } from 'lit';
import { FocusableHostMixin } from './utils/focusable-host-mixin.js';
import { FormAssociatedMixin } from './utils/form-associated-mixin.js';

/** Host attributes copied verbatim onto the form proxy (see the class doc). */
const PROXY_FORM_ATTRS = ['formaction', 'formenctype', 'formmethod', 'formnovalidate', 'formtarget'];

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
 * `disabled` on a link drops the href and sets aria-disabled. `loading` keeps
 * the href — consumers set it from the link's own click to show a spinner
 * during navigation, and dropping it there would cancel the very navigation
 * being spun for (the browser reads the href *after* listeners run, and it
 * drains microtasks — a Lit re-render — between listeners of a user event).
 * Re-activation while loading is blocked in the click listener instead.
 *
 * Forms: `type="submit"` / `type="reset"` behave like a native button. The
 * shadow-rendered control can't be a form's submit button (it has no form
 * owner), so the element keeps a hidden native <button> *proxy* in its light
 * DOM — unslotted, so it never renders — carrying the same type, name/value,
 * disabled state, and form* attributes. Because the proxy is a real submit
 * button in the form's tree: pressing Enter in a text field submits (implicit
 * submission), `submit` events have `event.submitter` (the proxy — use
 * `submitter.closest('ol-button')`), the button's name/value are submitted, and
 * `formaction` / `formmethod` / `formnovalidate` / `formtarget` are honored.
 * A click on the visible control is forwarded to `form.requestSubmit(proxy)`
 * after the click has finished propagating, so `preventDefault()` on the host
 * or an ancestor cancels it, exactly as it does for a native button. When the
 * button sits inside another component's shadow root and the form is outside,
 * the proxy has no form owner and it falls back to `internals.form` (a plain
 * `requestSubmit()`, no submitter). Replacing the host's children wholesale
 * (`textContent =`) removes the proxy; a MutationObserver puts it back.
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
 * @prop {String} name      - Submitted with `value` when this button submits the form.
 * @prop {String} value     - See `name`.
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
export class OLButton extends FormAssociatedMixin(FocusableHostMixin(LitElement)) {
    static properties = {
        variant: { type: String, reflect: true },
        size: { type: String, reflect: true },
        shape: { type: String, reflect: true },
        elevation: { type: String, reflect: true },
        type: { type: String, reflect: true },
        value: { type: String, reflect: true },
        // Pass-throughs to the form proxy; same names as on a native <button>.
        formAction: { type: String, attribute: 'formaction', reflect: true },
        formEnctype: { type: String, attribute: 'formenctype', reflect: true },
        formMethod: { type: String, attribute: 'formmethod', reflect: true },
        formNoValidate: { type: Boolean, attribute: 'formnovalidate', reflect: true },
        formTarget: { type: String, attribute: 'formtarget', reflect: true },
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
           rules on the inner control don't fire. :disabled (not [disabled]) so
           an ancestor <fieldset disabled> counts too. */
        :host(:disabled),
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
            color: var(--color-text);
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
            transition: transform var(--duration-press);
        }

        /* Press feedback — tactile scale on activation. The raised shadow and
           specular highlight stay put through the press. The scale is tiered by
           width so the edge travels ~1.5px (see static/css/tokens/press.css). */
        .control:active {
            transform: scale(var(--press-scale));
        }

        /* Icon-only shapes are small enough that 3% is sub-pixel; press harder so
           the feedback registers. */
        :host([shape]) .control:active {
            transform: scale(var(--press-scale-compact));
        }

        /* Stretched buttons are wide enough that 3% reads as a lurch; press softer. */
        :host([full-width]) .control:active {
            transform: scale(var(--press-scale-wide));
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
            background-color: var(--color-primary);
            border-color: var(--color-primary);
            color: var(--white);
            /* Tone the specular highlight to the blue fill instead of pure white, and
               soften it — the white edge reads much louder on a dark fill than on white. */
            --control-surface: var(--color-primary);
            --control-highlight-strength: 18%;
        }

        /* Secondary is the default (already set above). Explicit selector for clarity. */
        :host([variant="secondary"]) .control {
            background-color: var(--white);
            border-color: var(--color-border-subtle);
            color: var(--color-text);
        }

        /* Destructive — solid red fill, mirroring primary but in the danger hue. */
        :host([variant="destructive"]) .control {
            background-color: var(--color-destructive);
            border-color: var(--color-border-error);
            color: var(--white);
            /* Tone the specular highlight to the red fill and soften it, matching primary. */
            --control-surface: var(--color-destructive);
            --control-highlight-strength: 18%;
        }

        /* Ghost — text and icon only, no fill, border, or lift at rest; picks up the
           neutral hover fill. For low-emphasis actions ("Show more", toolbar icons).
           The border stays (transparent) so ghost lines up pixel-for-pixel with
           secondary. */
        :host([variant="ghost"]) .control {
            background-color: transparent;
            border-color: transparent;
            color: var(--color-text);
            box-shadow: none;
        }

        /* Selected — a neutral button carrying a selection, e.g. ol-select-popover's
           trigger once a language is picked. Must stay after the variant fills, which
           it ties on specificity. */
        :host([selected]) .control {
            background-color: var(--color-control-selected-bg);
            border-color: var(--color-control-selected-border);
            color: var(--color-link);
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
                border-color: var(--color-border-muted);
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
            outline: var(--focus-width) solid var(--color-focus-ring);
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
                opacity var(--duration-base) var(--ease-state),
                transform var(--duration-base) var(--ease-state),
                filter var(--duration-base) var(--ease-state);
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
                opacity var(--duration-base) var(--ease-state),
                transform var(--duration-base) var(--ease-state),
                filter var(--duration-base) var(--ease-state);
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
            animation: ol-button-spin var(--duration-spin) linear infinite;
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
            transition: transform var(--duration-fast) var(--ease-enter);
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
        this.formNoValidate = false;
        /** @type {HTMLButtonElement|null} Light-DOM native button standing in for the form. */
        this._proxy = null;
        // Restores the proxy if a consumer replaces the host's children
        // (`textContent =`), which would otherwise break Enter-to-submit.
        this._childObserver = new MutationObserver(() => {
            if (this._proxy && this._proxy.parentNode !== this) this._syncProxy();
        });
    }

    connectedCallback() {
        super.connectedCallback();
        this._childObserver.observe(this, { childList: true });
        // Flush the first render synchronously within the upgrade task, so the
        // pre-upgrade host styling (ol-button.css, `:not(:defined)`) hands off
        // to the shadow-rendered control with no frame in between.
        this.performUpdate();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._childObserver.disconnect();
    }

    /** @returns {boolean} Whether this button acts on a form (submit/reset, not a link). */
    get _isFormButton() {
        return (this.type === 'submit' || this.type === 'reset') && (this.href === undefined || this.href === null);
    }

    /**
     * Keep the light-DOM proxy in step with the host, creating or removing it
     * as `type` / `href` change. Runs after every render.
     *
     * @param {Map<string, unknown>} changed
     * @returns {void}
     */
    updated(changed) {
        super.updated?.(changed);
        this._syncProxy();
    }

    /** @returns {void} */
    _syncProxy() {
        if (!this._isFormButton) {
            this._proxy?.remove();
            this._proxy = null;
            return;
        }
        let proxy = this._proxy;
        if (!proxy) {
            proxy = this._proxy = document.createElement('button');
            // Unslotted (no such slot) so it never renders and never reaches
            // AT; `hidden` is belt-and-braces for before the shadow root exists.
            proxy.setAttribute('slot', '__ol-button-form-proxy');
            proxy.hidden = true;
            proxy.tabIndex = -1;
            proxy.setAttribute('aria-hidden', 'true');
        }
        // Re-append if a consumer replaced the host's children.
        if (proxy.parentNode !== this) this.appendChild(proxy);
        proxy.type = this.type;
        proxy.disabled = this.loading || this.isDisabled;
        for (const attr of ['name', 'value', ...PROXY_FORM_ATTRS]) {
            const v = this.getAttribute(attr);
            if (v === null) proxy.removeAttribute(attr);
            else proxy.setAttribute(attr, v);
        }
    }

    /**
     * Forwards a click on the visible control to the form. Deferred with
     * setTimeout so it runs after the click has finished propagating and can
     * honor `preventDefault()` from the host or any ancestor, as a native
     * button's activation behavior does. (A microtask isn't late enough: for
     * user-initiated events the browser drains microtasks between listeners.)
     * Implicit submission (Enter in a text field) never comes through here —
     * the browser clicks the proxy directly.
     *
     * Also attached to the link control: the loading/disabled guard is what
     * blocks (keyboard) activation while loading, since a loading link keeps
     * its href (see render). The click that *starts* loading passes through —
     * `loading` is still false when this inner listener runs.
     *
     * @param {MouseEvent} e
     * @returns {void}
     */
    _onControlClick(e) {
        if (this.loading || this.isDisabled) {
            e.preventDefault();
            return;
        }
        if (!this._isFormButton) return;
        setTimeout(() => {
            if (e.defaultPrevented) return;
            this._submitOrReset();
        }, 0);
    }

    /**
     * Submits or resets via the proxy when it shares the form's tree, so the
     * submission carries a real submitter; otherwise via ElementInternals.
     * `requestSubmit()` (not `submit()`) so native validation and the form's
     * `submit` event both run.
     *
     * @returns {void}
     */
    _submitOrReset() {
        const proxy = this._proxy;
        const form = proxy?.form ?? this.form;
        if (!form) return;
        if (this.type === 'reset') {
            form.reset();
        } else if (proxy && proxy.form === form) {
            form.requestSubmit(proxy);
        } else {
            form.requestSubmit();
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
        const inert = this.loading || this.isDisabled;
        const content = html`<span class="label" part="label"><slot name="icon-start"></slot><slot></slot><slot name="icon-end"></slot></span><span class="spinner" aria-hidden="true"></span><span class="chevron" aria-hidden="true"></span>`;

        if (this.href !== undefined && this.href !== null) {
            // A link can't be disabled natively: drop the href (no navigation,
            // no tab stop) and say so via aria-disabled. Only `disabled` drops
            // it — `loading` must keep the href, or setting loading from the
            // link's own click re-renders the href away before the browser's
            // follow-the-hyperlink reads it, cancelling the navigation the
            // spinner is for. While loading, _onControlClick blocks keyboard
            // re-activation; the host's pointer-events: none blocks the mouse.
            return html`
                <a
                    class="control"
                    part="control"
                    href=${this.isDisabled ? nothing : this.href}
                    target=${this.target ?? nothing}
                    rel=${this.rel ?? nothing}
                    download=${this.download ?? nothing}
                    aria-disabled=${inert ? 'true' : nothing}
                    aria-busy=${this.loading ? 'true' : 'false'}
                    aria-label=${this.a11yLabel ?? nothing}
                    aria-haspopup=${this.a11yHasPopup ?? nothing}
                    aria-expanded=${this.a11yExpanded ?? nothing}
                    @click=${this._onControlClick}
                >${content}</a>
            `;
        }

        // Always type="button": the inner element has no form owner, so a
        // native submit type would be inert anyway; _onControlClick forwards
        // submit/reset to the form through the light-DOM proxy.
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
