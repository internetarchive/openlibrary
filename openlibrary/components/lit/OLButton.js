import { LitElement, html } from 'lit';

/**
 * OLButton - A pure-presentation button primitive.
 *
 * Renders a real <button> element into the light DOM so global CSS styles
 * it both before and after hydration. Handles variants, sizes, loading,
 * disabled, and form submission for type="submit" / type="reset".
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
 * @element ol-button
 *
 * @prop {String}  variant    - "primary" | "secondary" | "destructive". Default: "secondary"
 * @prop {String}  size       - "small" | "medium" | "large". Default: "medium"
 * @prop {String}  type       - "button" | "submit" | "reset". Default: "button"
 * @prop {Boolean} loading    - Shows a spinner and disables interaction.
 * @prop {Boolean} disabled   - Disables interaction.
 * @prop {Boolean} fullWidth  - Button expands to fill its container.
 *
 * @attr {Boolean} no-chevron - Suppresses the automatic disclosure chevron
 *   shown when the button is a popover/menu trigger (has `aria-haspopup`).
 *
 * @slot - Default slot carries the button label.
 *
 * @example
 *   <ol-button variant="destructive" size="medium">Delete</ol-button>
 *   <ol-button type="submit" loading>Saving…</ol-button>
 */
export class OLButton extends LitElement {
    static properties = {
        variant: { type: String, reflect: true },
        size: { type: String, reflect: true },
        type: { type: String, reflect: true },
        loading: { type: Boolean, reflect: true },
        disabled: { type: Boolean, reflect: true },
        fullWidth: { type: Boolean, reflect: true, attribute: 'full-width' },
    };

    // Render into the light DOM so global stylesheets apply — no shadow DOM,
    // no FOUC beyond the normal custom-element upgrade window.
    createRenderRoot() {
        return this;
    }

    constructor() {
        super();
        this.variant = 'secondary';
        this.size = 'medium';
        this.type = 'button';
        this.loading = false;
        this.disabled = false;
        this.fullWidth = false;
    }

    connectedCallback() {
        // Capture the author's children (the label) before Lit's first render
        // so we can re-insert them inside the <button> we render.
        if (!this._label) {
            this._label = document.createElement('span');
            this._label.className = 'ol-btn-label';
            while (this.firstChild) {
                this._label.appendChild(this.firstChild);
            }
        }
        super.connectedCallback();
        // Flush the first render synchronously within the upgrade task so the
        // inner <button> exists before any paint. Paired with the `hydrated`
        // attribute in firstUpdated(), this avoids a flash where the host has
        // collapsed to a transparent wrapper but the inner button hasn't
        // rendered yet.
        this.performUpdate();
    }

    firstUpdated() {
        // Signals to CSS that the inner <button> is now in the DOM, so the
        // host can collapse from "pre-upgrade styled" to transparent wrapper.
        this.setAttribute('hydrated', '');
    }

    render() {
        // The label and spinner are both always in the DOM so we can crossfade
        // between them via CSS. The spinner has its own element (rather than a
        // ::before on the button) because the scale-in transition and the
        // rotation animation both need `transform` — splitting them across the
        // wrapper span and its ::before keeps them from stepping on each other.
        //
        // The chevron is always rendered but hidden by CSS unless the button is
        // a disclosure trigger (ol-popover / ol-select-popover set aria-haspopup
        // on it). That keeps the trigger affordance automatic — no consumer markup.
        return html`
            <button
                type=${this.type}
                ?disabled=${this.loading || this.disabled}
                aria-busy=${this.loading ? 'true' : 'false'}
            >${this._label}<span class="ol-btn-spinner" aria-hidden="true"></span><span class="ol-btn-chevron" aria-hidden="true"></span></button>
        `;
    }
}

customElements.define('ol-button', OLButton);
