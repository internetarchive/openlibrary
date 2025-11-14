import { LitElement, html, css } from 'lit';

/**
 * This component is incomplete, but being used to test the build pipeline.
 *
 * @element ol-heading
 *
 * @example
 * <ol-heading>My Page Title</ol-heading>
 */
export class OlHeading extends LitElement {
    static styles = css`
        :host {
            display: block;
        }

        h2 {
            color: #666;
            font-weight: 600;
        }
    `;

    render() {
        return html`
            <h2>
                <slot></slot>
            </h2>
        `;
    }
}

// Register the custom element
customElements.define('ol-heading', OlHeading);

