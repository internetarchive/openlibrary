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
 * @element ol-button
 *
 * @prop {String}  variant    - "primary" | "secondary" | "destructive". Default: "primary"
 * @prop {String}  size       - "small" | "medium" | "large". Default: "medium"
 * @prop {String}  type       - "button" | "submit" | "reset". Default: "button"
 * @prop {Boolean} loading    - Shows a spinner and disables interaction.
 * @prop {Boolean} disabled   - Disables interaction.
 * @prop {Boolean} fullWidth  - Button expands to fill its container.
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
        this.variant = 'primary';
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
    }

    _handleClick(e) {
        if (this.loading || this.disabled) {
            e.preventDefault();
            e.stopImmediatePropagation();
            return;
        }
        if (this.type === 'submit') {
            const form = this.closest('form');
            if (!form) return;
            if (typeof form.requestSubmit === 'function') {
                form.requestSubmit();
            } else {
                form.submit();
            }
        } else if (this.type === 'reset') {
            this.closest('form')?.reset();
        }
    }

    render() {
        return html`
            <button
                type="button"
                ?disabled=${this.loading || this.disabled}
                aria-busy=${this.loading ? 'true' : 'false'}
                @click=${this._handleClick}
            >${this._label}</button>
        `;
    }
}

customElements.define('ol-button', OLButton);
