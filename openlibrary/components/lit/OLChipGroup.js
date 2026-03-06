import { LitElement, html, css } from 'lit';

/**
 * OLChipGroup - A flex-wrap container for ol-chip components
 *
 * Provides consistent spacing and wrapping behavior for groups of chips.
 *
 * @property {String} gap - Gap size: "small" (4px), "medium" (8px, default), or "large" (12px)
 *
 * @example
 * <ol-chip-group>
 *   <ol-chip>Fiction</ol-chip>
 *   <ol-chip>History</ol-chip>
 *   <ol-chip>Science</ol-chip>
 * </ol-chip-group>
 */
export class OLChipGroup extends LitElement {
    static properties = {
        gap: { type: String, reflect: true },
    };

    static styles = css`
        :host {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }

        :host([gap="small"]) {
            gap: 4px;
        }

        :host([gap="large"]) {
            gap: 12px;
        }
    `;

    constructor() {
        super();
        this.gap = 'medium';
    }

    render() {
        return html`<slot></slot>`;
    }
}

customElements.define('ol-chip-group', OLChipGroup);
