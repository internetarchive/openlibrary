import { LitElement, html, css } from 'lit';

/**
 * A customizable button web component built with Lit
 *
 * @element ol-button
 *
 * @prop {string} variant - Button style variant: 'primary', 'secondary', 'destructive' (default: 'primary')
 * @prop {string} size - Button size: 'small', 'medium', 'large' (default: 'medium')
 * @prop {string} type - Button type: 'button', 'submit', 'reset' (default: 'button')
 * @prop {boolean} loading - Loading state, shows "Loading..." text and disables button (default: false)
 * @prop {boolean} fullWidth - Makes button take full width of container (default: false)
 *
 * @slot - Button text content
 *
 * @example
 * <ol-button variant="primary" size="medium">Click me</ol-button>
 * <ol-button variant="destructive" loading>Delete</ol-button>
 * <ol-button type="submit">Submit Form</ol-button>
 * <ol-button full-width>Full Width Button</ol-button>
 */
export class OLButton extends LitElement {
    static properties = {
        variant: { type: String, reflect: true },
        size: { type: String, reflect: true },
        type: { type: String, reflect: true },
        loading: { type: Boolean, reflect: true },
        fullWidth: { type: Boolean, reflect: true, attribute: 'full-width' }
    };

    static styles = css`
        :host {
            display: inline-block;
        }

        :host([full-width]) {
            display: block;
        }

        button {
            font-family: "Lucida Sans", "Lucida Sans Unicode", "Lucida Grande", Verdana, sans-serif;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-weight: normal;
            text-align: center;
            white-space: nowrap;
            transition: background-color 0.2s ease, opacity 0.2s ease;
            box-sizing: border-box;
            width: 100%;
        }

        /* Size variants */
        button.small {
            font-size: 14px;
            padding: 5px 10px;
            line-height: 1.4em;
        }

        button.medium {
            font-size: 16px;
            padding: 7px 15px;
            line-height: 1.5em;
        }

        button.large {
            font-size: 18px;
            padding: 10px 20px;
            line-height: 1.6em;
        }

        /* Variant styles */
        button.primary {
            background-color:  hsl(202, 96%, 37%);
            color: white;
        }

        button.primary:hover:not(:disabled) {
            background-color: #135C7A;
        }

        button.secondary {
            background-color: transparent;
            color: #1B7FA7;
            border: 2px solid #1B7FA7;
        }

        button.secondary:hover:not(:disabled) {
            background-color: rgba(27, 127, 167, 0.1);
        }

        button.destructive {
            background-color: #C03;
            color: white;
        }

        button.destructive:hover:not(:disabled) {
            background-color: #900;
        }

        /* Disabled state */
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        /* Focus state */
        button:focus-visible {
            outline: 2px solid #000;
            outline-offset: 2px;
        }

        /* Loading state */
        button.loading {
            position: relative;
        }
    `;

    constructor() {
        super();
        this.variant = 'primary';
        this.size = 'medium';
        this.type = 'button';
        this.loading = false;
        this.fullWidth = false;
    }

    /**
     * Handle button clicks and form submission
     * Since Shadow DOM buttons can't directly submit forms in the light DOM,
     * we need to manually find and submit the form when type="submit"
     */
    _handleClick() {
        if (this.type === 'submit' && !this.loading) {
            // Find the closest form element in the light DOM
            const form = this.closest('form');
            if (form) {
                // Request form submission
                // Using requestSubmit() instead of submit() to trigger validation and submit events
                if (form.requestSubmit) {
                    form.requestSubmit();
                } else {
                    // Fallback for older browsers
                    form.submit();
                }
            }
        } else if (this.type === 'reset' && !this.loading) {
            const form = this.closest('form');
            if (form) {
                form.reset();
            }
        }
        // For type="button", we don't do anything special - events bubble normally
    }

    render() {
        const classes = `${this.variant} ${this.size} ${this.loading ? 'loading' : ''}`;

        return html`
            <button
                type="button"
                class=${classes}
                ?disabled=${this.loading}
                aria-busy=${this.loading ? 'true' : 'false'}
                @click=${this._handleClick}
            >
                ${this.loading ? 'Loading...' : html`<slot></slot>`}
            </button>
        `;
    }
}

// Register the custom element
customElements.define('ol-button', OLButton);

