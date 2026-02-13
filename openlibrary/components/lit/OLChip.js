import { LitElement, html, css, nothing } from 'lit';

/**
 * OLChip - A pill-shaped interactive chip web component
 *
 * Supports two sizes, a selected state with a checkmark icon,
 * click events, and optional link behavior via href.
 *
 * @property {Boolean} selected - Whether the chip is in a selected state
 * @property {String} size - Chip size: "small" or "medium" (default)
 * @property {String} href - When set, the chip renders as a link
 * @property {String} count - Optional count displayed to the right of the label
 *
 * @fires chip-click - Fired on click. detail: { selected: Boolean }
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
    };

    static styles = css`
        :host {
            display: inline-block;
        }

        .chip {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 6px 12px;
            border: var(--border-width, 1px) solid var(--color-border-subtle, hsl(0, 0%, 87%));
            border-radius: var(--border-radius-pill, 9999px);
            font-family: var(--font-family-sans, sans-serif);
            font-size: var(--font-size-body-medium, 14px);
            line-height: 1.1;
            background: var(--white, hsl(0, 0%, 100%));
            color: var(--dark-grey, hsl(0, 0%, 20%));
            cursor: pointer;
            user-select: none;
            text-decoration: none;
        }

        .chip:hover {
            background: var(--lightest-grey, hsl(0, 0%, 93%));
        }

        .chip:focus-visible {
            outline: none;
            box-shadow: var(--box-shadow-focus, 0 0 0 2px hsl(202, 96%, 37%));
        }

        /* Selected state */
        :host([selected]) .chip {
            background: var(--primary-blue, hsl(202, 96%, 37%));
            border-color: var(--primary-blue, hsl(202, 96%, 37%));
            color: var(--white, hsl(0, 0%, 100%));
        }

        :host([selected]) .chip:hover {
            background: var(--primary-blue, hsl(202, 96%, 37%));
            filter: brightness(1.1);
        }

        /* Small size */
        :host([size="small"]) .chip {
            padding: 4px 8px;
            font-size: var(--font-size-label-medium, 12px);
        }

        /* Check icon */
        .check-icon {
            width: 14px;
            height: 14px;
            flex-shrink: 0;
        }

        :host([size="small"]) .check-icon {
            width: 12px;
            height: 12px;
        }

        /* Count */
        .count {
            color: var(--mid-grey);
            font-size: 0.85em;
        }
    `;

    constructor() {
        super();
        this.selected = false;
        this.size = 'medium';
        this.href = null;
        this.count = null;
    }

    _handleClick() {
        this.dispatchEvent(new CustomEvent('chip-click', {
            bubbles: true,
            composed: true,
            detail: { selected: this.selected },
        }));
    }

    _renderCheckIcon() {
        if (!this.selected) return nothing;

        return html`
            <svg
                class="check-icon"
                aria-hidden="true"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="3"
                stroke-linecap="round"
                stroke-linejoin="round"
            >
                <path d="M20 6 9 17l-5-5"/>
            </svg>
        `;
    }

    _renderCount() {
        if (this.count === null) return nothing;

        return html`<span class="count">${this.count}</span>`;
    }

    render() {
        const content = html`
            ${this._renderCheckIcon()}
            <slot></slot>
            ${this._renderCount()}
        `;

        if (this.href) {
            return html`
                <a class="chip" href=${this.href} @click=${this._handleClick}>
                    ${content}
                </a>
            `;
        }

        return html`
            <button class="chip" type="button" @click=${this._handleClick}>
                ${content}
            </button>
        `;
    }
}

customElements.define('ol-chip', OLChip);
