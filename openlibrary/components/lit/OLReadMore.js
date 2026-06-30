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
 * @prop {String} maxHeight - Collapsed height of the content before truncating (default: "80px")
 * @prop {String} moreText - Label for the expand toggle (default: "Read more")
 * @prop {String} lessText - Label for the collapse toggle (default: "Read less")
 * @prop {String} backgroundColor - Background color for the gradient fade (default: white)
 * @prop {String} labelSize - Size of the toggle button text: "medium" (default) or "small" (12px)
 *
 * @slot - The collapsible content
 *
 * @csspart toggle-btn - The toggle button element (targets both "more" and "less" buttons)
 *
 * @cssprop [--ol-readmore-link-color=hsl(202, 96%, 28%)] - Color of the more/less toggle button
 * @cssprop [--ol-readmore-gradient-color=white] - Solid color the fade gradient blends toward (match the surrounding background)
 * @cssprop [--ol-readmore-gradient-color-transparent=rgba(255, 255, 255, 0)] - Transparent end of the fade gradient
 *
 * @example
 * <ol-read-more max-height="100px" more-text="Read more" less-text="Read less">
 *   <p>Long content here...</p>
 * </ol-read-more>
 */
export class OLReadMore extends LitElement {
    // Number of lines worth hiding before a "Read more" button earns its place.
    // Expressed in lines (not px) so font/spacing tweaks don't silently shift the threshold.
    static BUFFER_LINES = 4;

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
            padding: var(--spacing-inset-lg) var(--spacing-md) var(--spacing-md) var(--spacing-md);
            background: linear-gradient(
                var(--ol-readmore-gradient-color-transparent) 0,
                var(--ol-readmore-gradient-color) var(--spacing-md)
            );
            border: none;
            border-radius: 0 0 4px 4px;
            cursor: pointer;
        }

        .toggle-btn.more {
            margin-top: calc(-1 * var(--spacing-md));
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
            padding-top: var(--spacing-inset-md);
            padding-bottom: var(--spacing-inset-sm);
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

    // Resolve an element's line-height to px, approximating `normal` from font-size.
    _getLineHeight(el) {
        const cs = getComputedStyle(el);
        const lh = parseFloat(cs.lineHeight);
        // `line-height: normal` parses to NaN — fall back to a typical ratio.
        return Number.isNaN(lh) ? parseFloat(cs.fontSize) * 1.5 : lh;
    }

    _checkIfTruncationNeeded() {
        const content = this.shadowRoot.querySelector('.content-wrapper');
        if (!content) return;

        // Measure the real slotted text, not the shadow wrapper — the wrapper
        // inherits the host's line-height, which may differ from the content's.
        const slot = this.shadowRoot.querySelector('slot');
        const sample = slot?.assignedElements?.()[0] ?? content;
        const buffer = OLReadMore.BUFFER_LINES * this._getLineHeight(sample);

        const isOverflowingEnough = content.scrollHeight > content.clientHeight + buffer;
        this._unnecessary = !isOverflowingEnough;

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
