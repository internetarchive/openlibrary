import { LitElement, html, css } from 'lit';

/**
 * STATUS: EXPERIMENTAL - Minimal implementation for single scenario production testing.
 *
* A destructive button web component built with Lit
 *
 * @element ol-button
 *
 * @slot - Button text content
 *
 * @attr {Boolean} disabled - Disables the button
 *
 * @example
 * <ol-button>Delete</ol-button>
 * <ol-button disabled>Delete</ol-button>
 */
export class OlButton extends LitElement {
    static properties = {
        disabled: { type: Boolean }
    };

    static styles = css`
    :host {
      display: inline-block;

      /* Temporarily hardcoding CSS values in component file for testing. */
      --color-bg-error: #de351b;
      --color-bg-error-hovered: #ce2d14;
      --color-bg-error-disabled: #de7f6c;
      --color-text-on-error: #fff;

      --radius-button: 4px;
      --border-width-control: 1px;
      --button-padding-y: 12px;
      --button-padding-x: 16px;

      --focus-ring-width: 2px;
    }

    button {
      background-color: var(--color-bg-error);
      border: var(--border-width-control) solid var(--color-bg-error);
      border-radius: var(--radius-button);
      color: var(--color-text-on-error);
      cursor: pointer;
      font-size: 1.2em;
      padding: var(--button-padding-y) var(--button-padding-x);
      text-align: center;
      white-space: nowrap;
      box-sizing: border-box;
      width: 100%;
    }

    button:hover:not(:disabled) {
      background-color: var(--color-bg-error-hovered);
    }

    button:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }

    button:focus-visible {
      outline: var(--focus-ring-width) solid var(--color-primary);
    }
  `;

    render() {
        return html`
      <button type="button" ?disabled=${this.disabled}>
        <slot></slot>
      </button>
    `;
    }
}

// Register the custom element
customElements.define('ol-button', OlButton);
