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

        .toggle-btn {
            display: block;
            position: relative;
            color: var(--ol-readmore-link-color);
            font-family: inherit;
            font-weight: 500;
            text-align: center;
            width: 100%;
            padding: 24px 12px 12px 12px;
            background: linear-gradient(
                var(--ol-readmore-gradient-color-transparent) 0,
                var(--ol-readmore-gradient-color) 12px
            );
            border: none;
            cursor: pointer;
        }

        .toggle-btn.more {
            margin-top: -12px;
        }

        .toggle-btn:hover {
            text-decoration: underline;
        }

        .toggle-btn.hidden {
            display: none;
        }

        @media only screen and (min-width: 800px) {
            .toggle-btn {
                padding-left: 0;
                text-align: left;
            }
        }

        .toggle-btn.less {
            position: sticky;
            bottom: 0;
            margin-top: 0;
        }

        .chevron {
            width: 1.2em;
            height: 1.2em;
            vertical-align: middle;
        }

        .chevron.up {
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

    _handleMoreClick() {
        if (this._unnecessary) return;
        this._expanded = true;
    }

    _handleLessClick() {
        if (this._unnecessary) return;
        this._expanded = false;

        // Scroll back to top when collapsing if component is off-screen
        const rect = this.getBoundingClientRect();
        if (rect.top < 0) {
            this.scrollIntoView({
                behavior: 'smooth',
                block: 'start',
            });
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
        const showMoreBtn = !this._expanded && !this._unnecessary;
        const showLessBtn = this._expanded && !this._unnecessary;

        return html`
            <div
                class="content-wrapper ${this._expanded ? 'expanded' : ''}"
                style="${this._getContentStyle()}"
            >
                <slot></slot>
            </div>
            <button
                class="toggle-btn more ${showMoreBtn ? '' : 'hidden'}"
                aria-expanded="false"
                @click="${this._handleMoreClick}"
            >
                ${this.moreText}
                <svg class="chevron" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
            </button>
            <button
                class="toggle-btn less ${showLessBtn ? '' : 'hidden'}"
                aria-expanded="true"
                @click="${this._handleLessClick}"
            >
                ${this.lessText}
                <svg class="chevron up" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
            </button>
        `;
    }
}

customElements.define('ol-read-more', OLReadMore);
