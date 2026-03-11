import { LitElement, html, css } from 'lit';

/**
 * OLReadMore - A web component for expandable/collapsible content
 *
 * Uses height-based truncation via `max-height` attribute.
 *
 * Important: The default max-height is 80px. If you want to use a different max-height, you must
 * also set a min-height on the component with an inline style. The value of the min-height should
 * be the max-height + 41px or max-height + 27px if using a small label size.
 *
 * Example:
 * <ol-read-more max-height="100px" style="min-height: 141px">
 *   <p>Long content here...</p>
 * </ol-read-more>
 *
 * @property {String} background-color - Background color for the gradient fade (default: white)
 * @property {String} label-size - Size of the toggle button text: "medium" (default) or "small" (12px)
 *
 * @csspart toggle-btn - The toggle button element (targets both "more" and "less" buttons)
 *
 * @example
 * <ol-read-more max-height="100px" more-text="Read more" less-text="Read less">
 *   <p>Long content here...</p>
 * </ol-read-more>
 */
export class OLReadMore extends LitElement {
    static properties = {
        maxHeight: { type: String, attribute: 'max-height' },
        moreText: { type: String, attribute: 'more-text' },
        lessText: { type: String, attribute: 'less-text' },
        backgroundColor: { type: String, attribute: 'background-color' },
        labelSize: { type: String, attribute: 'label-size' },
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

        .content-wrapper.expanded {
            max-height: none !important;
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
            border-radius: 0 0 4px 4px;
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
                text-align: left;
                padding-left: 0;
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

        .toggle-btn.small {
            font-size: 12px;
            padding-top: 16px;
            padding-bottom: 8px;
        }
    `;

    constructor() {
        super();
        this.maxHeight = '80px';
        this.moreText = 'Read More';
        this.lessText = 'Read Less';
        this.backgroundColor = null;
        this.labelSize = 'medium';
        this._expanded = false;
        this._unnecessary = false;
    }

    firstUpdated() {
        this._checkIfTruncationNeeded();
        this._updateBackgroundColor();
        // Remove styles that were used to prevent layout shift
        // Now that the component has rendered, it can size naturally
        this.style.minHeight = 'auto';
        this.style.visibility = 'visible';
        this.style.overflow = 'visible';
    }

    updated(changedProperties) {
        if (changedProperties.has('backgroundColor')) {
            this._updateBackgroundColor();
        }
    }

    _updateBackgroundColor() {
        if (this.backgroundColor) {
            this.style.setProperty('--ol-readmore-gradient-color', this.backgroundColor);
        }
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

        return '';
    }

    render() {
        const showMoreBtn = !this._expanded && !this._unnecessary;
        const showLessBtn = this._expanded && !this._unnecessary;
        const sizeClass = this.labelSize === 'small' ? 'small' : '';

        return html`
            <div
                class="content-wrapper ${this._expanded ? 'expanded' : ''}"
                style="${this._getContentStyle()}"
            >
                <slot></slot>
            </div>
            <button
                part="toggle-btn"
                class="toggle-btn more ${sizeClass} ${showMoreBtn ? '' : 'hidden'}"
                aria-expanded="false"
                @click="${this._handleMoreClick}"
            >
                ${this.moreText}
                <svg class="chevron" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>
            </button>
            <button
                part="toggle-btn"
                class="toggle-btn less ${sizeClass} ${showLessBtn ? '' : 'hidden'}"
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
