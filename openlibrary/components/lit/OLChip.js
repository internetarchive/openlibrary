import { LitElement, html, css, nothing } from 'lit';

/**
 * OLChip - A pill-shaped interactive chip web component
 *
 * Supports two sizes, a selected state with a close icon,
 * click events, and optional link behavior via href.
 *
 * @property {Boolean} selected - Whether the chip is in a selected state
 * @property {String} size - Chip size: "small" or "medium" (default)
 * @property {String} href - When set, the chip renders as a link
 * @property {String} count - Optional count displayed to the right of the label
 * @property {String} accessibleLabel - Override aria-label on the inner interactive element
 *
 * @fires ol-chip-select - Fired on click. detail: { selected: Boolean }
 *
 * @example
 * <ol-chip>Fiction</ol-chip>
 *
 * @example
 * <ol-chip selected>History</ol-chip>
 *
 * @example
 * <ol-chip size="small" count="76" href="/subjects/fiction">Fiction</ol-chip>
 */
export class OLChip extends LitElement {
    static properties = {
        selected: { type: Boolean, reflect: true },
        size: { type: String, reflect: true },
        href: { type: String },
        count: { type: String },
        accessibleLabel: { type: String, attribute: 'accessible-label' },
    };

    static styles = css`
        :host {
            --chip-padding-block: 6px;
            --chip-padding-inline: 12px;
            --chip-icon-size: 14px;
            --chip-icon-gap: 4px;
            display: inline-block;
        }

        :host([size="small"]) {
            --chip-padding-block: 4px;
            --chip-padding-inline: 8px;
            --chip-icon-size: 12px;
        }

        .chip {
            position: relative;
            display: inline-flex;
            align-items: center;
            padding: var(--chip-padding-block) var(--chip-padding-inline);
            border: var(--border-width) solid var(--color-border-subtle);
            border-radius: var(--border-radius-chip);
            font-family: var(--font-family-button);
            font-size: var(--font-size-body-medium);
            line-height: var(--line-height-chip);
            background: var(--white);
            color: var(--dark-grey);
            cursor: pointer;
            user-select: none;
            text-decoration: none;
        }

        @media (hover: hover) and (pointer: fine) {
            .chip:hover {
                background: var(--lightest-grey);
            }
        }

        .chip:active {
            transform: scale(0.97);
        }

        .chip:focus-visible {
            outline: none;
            box-shadow: var(--box-shadow-focus);
        }

        /* Selected state */
        :host([selected]) .chip {
            padding-inline-start: calc(var(--chip-padding-inline) + var(--chip-icon-size) + var(--chip-icon-gap));
            background: var(--primary-blue);
            border-color: var(--primary-blue);
            color: var(--white);
        }

        @media (hover: hover) and (pointer: fine) {
            :host([selected]) .chip:hover {
                background: var(--primary-blue);
                filter: brightness(1.1);
            }
        }

        /* Small size */
        :host([size="small"]) .chip {
            font-size: var(--font-size-label-medium);
        }

        /* Close icon for selected state */
        .icon-slot {
            position: absolute;
            inset-inline-start: var(--chip-padding-inline);
            top: 50%;
            transform: translateY(-50%);
            width: var(--chip-icon-size);
            height: var(--chip-icon-size);
        }

        .icon {
            width: var(--chip-icon-size);
            height: var(--chip-icon-size);
        }

        /* Count */
        .count {
            margin-inline-start: 4px;
            color: #777;
            font-size: 0.85em;
            font-variant-numeric: tabular-nums;
        }

        :host([selected]) .count {
            color: #c6e1f0;
        }
    `;

    constructor() {
        super();
        this.selected = false;
        this.size = 'medium';
        this.href = null;
        this.count = null;
        this.accessibleLabel = null;
    }

    _handleClick() {
        this.dispatchEvent(new CustomEvent('ol-chip-select', {
            bubbles: true,
            composed: true,
            detail: { selected: !this.selected },
        }));
    }

    _renderIcons() {
        if (!this.selected) return nothing;

        return html`
            <span class="icon-slot">
                <svg
                    class="icon"
                    aria-hidden="true"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="3"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                >
                    <path d="M18 6 6 18"/><path d="m6 6 12 12"/>
                </svg>
            </span>
        `;
    }

    _renderCount() {
        if (this.count === null) return nothing;

        return html`<span class="count">${this.count}</span>`;
    }

    render() {
        const content = html`
            ${this._renderIcons()}
            <slot></slot>
            ${this._renderCount()}
        `;

        if (this.href) {
            return html`
                <a class="chip" href=${this.href}
                    aria-label=${this.accessibleLabel || nothing}
                    @click=${this._handleClick}>
                    ${content}
                </a>
            `;
        }

        return html`
            <button class="chip" type="button"
                aria-label=${this.accessibleLabel || nothing}
                aria-pressed=${this.selected}
                @click=${this._handleClick}>
                ${content}
            </button>
        `;
    }
}

customElements.define('ol-chip', OLChip);
