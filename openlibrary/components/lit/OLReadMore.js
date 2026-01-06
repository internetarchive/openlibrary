import { LitElement, html, css } from 'lit';

/**
 * OLReadMore - A web component for expandable/collapsible content
 *
 * Supports two truncation modes:
 * - Height-based: Use `max-height` attribute (e.g., "81px")
 * - Line-based: Use `max-lines` attribute (e.g., "4")
 *
 * @example
 * <ol-read-more max-height="100px" more-text="Read more" less-text="Read less">
 *   <p>Long content here...</p>
 * </ol-read-more>
 *
 * @example
 * <ol-read-more max-lines="4">
 *   <p>Long content here...</p>
 * </ol-read-more>
 */
export class OLReadMore extends LitElement {
    static properties = {
        maxHeight: { type: String, attribute: 'max-height' },
        maxLines: { type: Number, attribute: 'max-lines' },
        moreText: { type: String, attribute: 'more-text' },
        lessText: { type: String, attribute: 'less-text' },
        // Internal state
        _expanded: { type: Boolean, state: true },
        _unnecessary: { type: Boolean, state: true },
    };

    static styles = css`
        :host {
            display: block;
            position: relative;
            --ol-readmore-link-color: hsl(202, 96%, 28%);
            --ol-readmore-gradient-color: white;
            --ol-readmore-gradient-color-transparent: rgba(255, 255, 255, 0);
        }

        details {
            display: block;
        }

        summary {
            list-style: none;
            cursor: pointer;
        }

        summary::-webkit-details-marker {
            display: none;
        }

        summary::marker {
            display: none;
            content: '';
        }

        .content-wrapper {
            overflow: hidden;
        }

        /* Line-based mode */
        :host([max-lines]) .content-wrapper:not(.expanded) {
            display: -webkit-box;
            -webkit-box-orient: vertical;
            /* -webkit-line-clamp is set via inline style */
        }

        .content-wrapper.expanded {
            max-height: none !important;
            -webkit-line-clamp: unset !important;
            display: block !important;
        }

        .toggle {
            display: block;
            color: var(--ol-readmore-link-color);
            font-family: inherit;
            font-weight: 500;
            text-align: center;
            width: 100%;
            padding: 28px 12px 12px 12px;
            margin-top: -16px;
            background: linear-gradient(
                var(--ol-readmore-gradient-color-transparent) 0,
                var(--ol-readmore-gradient-color) 12px
            );
        }

        .toggle:hover {
            text-decoration: underline;
        }

        @media only screen and (min-width: 800px) {
            .toggle {
                padding-left: 0;
                text-align: left;
            }
        }

        details[open] .toggle {
            position: sticky;
            bottom: 0;
            margin-top: 0;
        }

        details.no-expand summary {
            cursor: default;
        }

        details.no-expand .toggle {
            display: none;
        }

        .chevron {
            width: 1.2em;
            height: 1.2em;
            vertical-align: middle;
        }

        details[open] .chevron {
            transform: rotate(180deg);
        }
    `;

    constructor() {
        super();
        this.maxHeight = null;
        this.maxLines = null;
        this.moreText = 'Read More';
        this.lessText = 'Read Less';
        this._expanded = false;
        this._unnecessary = false;
    }

    firstUpdated() {
        this._checkIfTruncationNeeded();
    }

    _checkIfTruncationNeeded() {
        const content = this.shadowRoot.querySelector('.content-wrapper');
        if (!content) return;

        const isOverflowing = content.scrollHeight > content.clientHeight;
        this._unnecessary = !isOverflowing;

        if (this._unnecessary) {
            this._expanded = true;
        }
    }

    _handleToggle(e) {
        // Prevent default so we control the state
        e.preventDefault();

        if (this._unnecessary) return;

        this._expanded = !this._expanded;

        // Scroll back to top when collapsing if component is off-screen
        if (!this._expanded) {
            const rect = this.getBoundingClientRect();
            if (rect.top < 0) {
                this.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start',
                });
            }
        }
    }

    _getContentStyle() {
        if (this._expanded) {
            return '';
        }

        if (this.maxHeight) {
            return `max-height: ${this.maxHeight}`;
        }

        if (this.maxLines) {
            return `-webkit-line-clamp: ${this.maxLines}`;
        }

        return '';
    }

    render() {
        const chevronSvg = html`<svg class="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>`;

        return html`
            <details
                class="${this._unnecessary ? 'no-expand' : ''}"
                ?open="${this._expanded}"
                @click="${this._handleToggle}"
            >
                <summary>
                    <div
                        class="content-wrapper ${this._expanded ? 'expanded' : ''}"
                        style="${this._getContentStyle()}"
                    >
                        <slot></slot>
                    </div>
                    <span class="toggle" role="button" aria-expanded="${this._expanded}">
                        ${this._expanded ? this.lessText : this.moreText}
                        ${chevronSvg}
                    </span>
                </summary>
            </details>
        `;
    }
}

customElements.define('ol-read-more', OLReadMore);
