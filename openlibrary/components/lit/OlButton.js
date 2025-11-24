import { LitElement, html, css } from 'lit';

/**
 * STATUS: EXPERIMENTAL - Minimal implementation for single scenario production testing.
 *
 * A customizable button web component built with Lit
 *
 * @element ol-button
 *
 * @prop {string} variant - Button style variant: 'primary', 'secondary', 'destructive' (default: 'destructive')
 * @prop {string} size - Button size: 'small', 'medium', 'large' (default: 'medium')
 * @prop {string} type - Button type: 'button', 'submit', 'reset' (default: 'button')
 * @prop {boolean} loading - Loading state, shows "Loading..." text and disables button (default: false)
 * @prop {boolean} fullWidth - Makes button take full width of container (default: true)
 * @prop {boolean} disabled - Disables the button (default: false)
 *
 * @slot - Button text content
 *
 * @example
 * <ol-button variant="primary" size="medium">Click me</ol-button>
 * <ol-button variant="destructive" loading>Delete</ol-button>
 * <ol-button type="submit">Submit Form</ol-button>
 * <ol-button full-width>Full Width Button</ol-button>
 */
export class OlButton extends LitElement {
    static properties = {
        variant: { type: String, reflect: true },
        size: { type: String, reflect: true },
        type: { type: String, reflect: true },
        loading: { type: Boolean, reflect: true },
        fullWidth: { type: Boolean, reflect: true, attribute: 'full-width' },
        disabled: { type: Boolean, reflect: true }
    };

    static styles = css`
    :host {
      display: inline-block;

      /* Temporarily hardcoding CSS values in component file for testing. */
      --color-brand-primary: #2e7bcf;
      --color-bg-primary: #2e7bcf;
      --color-bg-primary-hovered: #1e5a9e;
      --color-text-on-primary: #fff;

      --color-bg-elevated: #fff;
      --color-bg-elevated-hovered: #f5f5f5;
      --color-text: #333;
      --color-border: #ccc;

      --color-bg-error: #de351b;
      --color-bg-error-hovered: #ce2d14;
      --color-text-on-error: #fff;

      --radius-button: 4px;
      --border-width-control: 1px;
      --button-padding-y: 12px;
      --button-padding-x: 16px;
      --button-sm-padding-y: 0.25em;
      --button-sm-padding-x: 0.75em;

      --body-font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen-Sans, Ubuntu, Cantarell, "Helvetica Neue", sans-serif;
      --body-font-size: 1rem;
      --body-font-size-sm: 0.75rem;
      --font-weight-semibold: 600;

      --focus-ring-width: 2px;
      --color-primary: #2e7bcf;
    }

    :host([full-width]) {
      display: block;
    }

    button {
      border: var(--border-width-control) solid var(--color-brand-primary);
      border-radius: var(--radius-button);
      cursor: pointer;
      font-family: var(--body-font-family);
      text-align: center;
      white-space: nowrap;
      box-sizing: border-box;
      width: 100%;
      font-weight: var(--font-weight-semibold);
    }

    /* Size variants */
    button.small {
      font-size: var(--body-font-size-sm);
      padding: var(--button-sm-padding-y) var(--button-sm-padding-x);
    }

    button.medium {
      font-size: var(--body-font-size);
      padding: var(--button-padding-y) var(--button-padding-x);
    }

    button.large {
      font-size: 18px;
      padding: 10px 20px;
      line-height: 1.6em;
    }

    /* Variant styles */
    button.primary {
      background-color: var(--color-bg-primary);
      color: var(--color-text-on-primary);
    }

    button.primary:hover:not(:disabled) {
      background-color: var(--color-bg-primary-hovered);
    }

    button.secondary {
      background-color: var(--color-bg-elevated);
      color: var(--color-text);
      border: var(--border-width-control) solid var(--color-border);
    }

    button.secondary:hover:not(:disabled) {
      background-color: var(--color-bg-elevated-hovered);
    }

    button.destructive {
      background-color: var(--color-bg-error);
      border: var(--border-width-control) solid var(--color-bg-error);
      color: var(--color-text-on-error);
    }

    button.destructive:hover:not(:disabled) {
      background-color: var(--color-bg-error-hovered);
    }

    /* Disabled state */
    button:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }

    /* Focus state */
    button:focus-visible {
      outline: var(--focus-ring-width) solid var(--color-primary);
    }

    /* Loading state */
    button.loading {
      position: relative;
    }
  `;

    constructor() {
        super();
        this.variant = 'destructive'; // Default to destructive to maintain backward compatibility
        this.size = 'medium';
        this.type = 'button';
        this.loading = false;
        this.fullWidth = true; // Default to true to maintain backward compatibility
        this.disabled = false;
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
        ?disabled=${this.loading || this.disabled}
        aria-busy=${this.loading ? 'true' : 'false'}
        @click=${this._handleClick}
      >
        ${this.loading ? 'Loading...' : html`<slot></slot>`}
      </button>
    `;
    }
}

// Register the custom element
customElements.define('ol-button', OlButton);
