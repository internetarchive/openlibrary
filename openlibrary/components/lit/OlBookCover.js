import { LitElement, css, html, nothing } from 'lit';
import { translate } from './utils/labels.js';
import './OlTooltip.js';

export const DEFAULT_LABELS = {
    by: 'by %(name)s',
};

/**
 * A book cover at a fixed 2:3 ratio: the artwork when there is one, a generated
 * title/author panel when there isn't, and a corner for whatever the surface
 * wants to float over it.
 *
 * Knows nothing about shelves, availability or search — give it a URL and a
 * title. `overlay` is the slot the save button goes in; the component owns the
 * corner position so a consumer never has to.
 *
 * A pointer gets a hover card carrying the title, year and author.
 * `ol-tooltip` arms on the same media query a cover-card layout uses to
 * hide that text below the cover, so exactly one of the two shows.
 *
 * A linked cover gets a ring on hover and on keyboard focus, reaching 4px outside
 * the cover — leave that much room around it (e.g. ol-carousel's viewport padding).
 * Hover also dims the artwork under the ring.
 *
 * @element ol-book-cover
 *
 * @prop {String} src - Cover image URL; empty draws the generated blank cover
 * @prop {String} bookTitle - The book's title. Named `book-title` because a
 *     `title` attribute would draw a native browser tooltip over the whole host
 * @prop {String} authors - Author names, already joined for display
 * @prop {String} year - First publication year, shown in the hover card
 * @prop {String} href - Link target; empty renders the cover unlinked
 * @prop {String} size - "medium" (default) or "small"; small drops the author
 *     from the blank cover, which has no room for it
 * @prop {Boolean} deferred - Holds the artwork back, drawing only the cover's surface, until
 *     the attribute is removed. ol-carousel removes it as the cover comes within a page of
 *     view; anything else that sets it has to remove it too
 * @prop {Object} labels - Translated strings, merged over DEFAULT_LABELS
 *
 * @slot overlay - Pinned to the cover's top-right corner, over the artwork
 *
 * @fires ol-book-cover-click - The cover link was clicked. detail: { href }
 */
export class OlBookCover extends LitElement {
    static properties = {
        src: { type: String },
        bookTitle: { type: String, attribute: 'book-title' },
        authors: { type: String },
        year: { type: String },
        href: { type: String },
        size: { type: String, reflect: true },
        deferred: { type: Boolean, reflect: true },
        labels: { type: Object },
    };

    static styles = css`
        :host {
            position: relative;
            display: block;
            aspect-ratio: 2 / 3;
            border-radius: var(--border-radius-thumbnail);
            overflow: hidden;
            background: var(--color-surface-sunken);
            font-family: var(--font-family-body);
        }

        .link {
            display: block;
            height: 100%;
            outline: none;
        }

        /* Both rings sit outside the cover, which clips anything inside it. The
           host's surface needs 4px of room around it for them: the focus ring
           is 2px with a 2px gap, the hover ring 4px hugging the edge. */
        @media (hover: hover) and (pointer: fine) {
            /* At rest the hover ring is there at zero width, so hovering grows it out from the edge.
               It tucks one media-border width under the cover's edge, covering the light seam two
               antialiased curves leave at the corners; the extra width keeps its 4px reach outside. */
            :host([href]) {
                outline: 0 solid var(--color-border-pointed);
                outline-offset: calc(-1 * var(--border-width-media));
                transition: outline-width var(--duration-fast) var(--ease-exit);
            }

            :host([href]) .link {
                transition: filter var(--duration-fast) var(--ease-exit);
            }
        }

        :host([link-focus]) {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        @media (hover: hover) and (pointer: fine) {
            :host([href]:hover) {
                outline: calc(var(--pointed-ring-width) + var(--border-width-media)) solid var(--color-border-pointed);
                outline-offset: calc(-1 * var(--border-width-media));
                transition-timing-function: var(--ease-enter);
            }

            :host([href]:hover) .link {
                filter: var(--filter-pointed-dim);
                transition-timing-function: var(--ease-enter);
            }
        }

        @media (prefers-reduced-motion: reduce) {
            :host([href]),
            :host([href]) .link {
                transition: none;
            }
        }

        /* Wraps the overlay too, so pointing at the save button keeps the card
           up. The link stays the trigger: it alone is described by the card. */
        ol-tooltip {
            display: block;
            height: 100%;
        }

        /* The edge line is an inset outline, drawn over the artwork, so a pale
           cover still separates from a pale page. */
        .img {
            display: block;
            width: 100%;
            height: 100%;
            object-fit: cover;
            border-radius: var(--border-radius-thumbnail);
            outline: var(--border-width-media) solid var(--color-border-media);
            outline-offset: calc(-1 * var(--border-width-media));
        }

        /* A deferred cover: the host's own surface shows through until the artwork loads. */
        .pending {
            display: block;
            height: 100%;
        }

        .blank {
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            height: 100%;
            box-sizing: border-box;
            padding: var(--spacing-inset-sm);
            background: linear-gradient(160deg, var(--neutral-600), var(--neutral-800));
            color: var(--color-text-inverse);
            text-align: center;
        }

        .blank__title {
            font-family: var(--font-family-heading);
            font-size: var(--font-size-title-medium);
            font-weight: 500;
            line-height: var(--line-height-tight);
            overflow: hidden;
            display: -webkit-box;
            -webkit-box-orient: vertical;
            -webkit-line-clamp: 4;
        }

        /* A 72px cover has room for neither the padding nor the type of a
           full-size one. */
        :host([size="small"]) .blank {
            padding: var(--spacing-inset-xs);
        }

        :host([size="small"]) .blank__title {
            font-size: var(--font-size-label-medium);
        }

        .blank__author {
            font-size: var(--font-size-label-small);
            letter-spacing: 0.08em;
            text-transform: uppercase;
            opacity: 0.85;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        /* The corner is the cover's to own. Whatever is slotted in goes static
           inside it — a wrapper like <ol-shelf-actions> takes the corner and its
           own trigger sits inside that. */
        slot[name="overlay"]::slotted(*) {
            position: absolute;
            top: 4px;
            right: 4px;
        }

        /* Panel content: styled here because it is a light child of this
           component; only the panel chrome comes from ol-tooltip. */
        .tip {
            font-size: var(--font-size-body-medium);
        }

        .tip__title {
            font-weight: 600;
        }

        .tip__year,
        .tip__byline {
            color: var(--neutral-300);
        }

        .tip__byline {
            font-size: var(--font-size-label-medium);
        }
    `;

    constructor() {
        super();
        this.src = '';
        this.bookTitle = '';
        this.authors = '';
        this.year = '';
        this.href = '';
        this.size = 'medium';
        this.deferred = false;
        this.labels = {};
    }

    t(key, vars) {
        return translate(this.labels, DEFAULT_LABELS, key, vars);
    }

    get _alt() {
        return this.authors ? `${this.bookTitle} ${this.t('by', { name: this.authors })}` : this.bookTitle;
    }

    render() {
        const art = this.href
            ? html`<a class="link" href=${this.href} @click=${this._onClick} @focus=${this._onFocus} @blur=${this._onBlur}>${this._renderArt()}</a>`
            : this._renderArt();
        return html`
            <ol-tooltip placement="top" arrow>
                ${art}${this._renderTip()}
                <slot
                    name="overlay"
                    @pointerdown=${this._hideTip}
                    @ol-popover-open=${this._onOverlayOpen}
                    @ol-popover-close=${this._onOverlayClose}
                ></slot>
            </ol-tooltip>
        `;
    }

    get _tooltip() {
        return this.renderRoot.querySelector('ol-tooltip');
    }

    /** Pressing the overlay's button acts on the book; the card would only cover its menu. */
    _hideTip() {
        this._tooltip?.hide();
    }

    _onOverlayOpen() {
        this._tooltip.disabled = true;
        this._tooltip.hide();
    }

    _onOverlayClose(e) {
        if (!e.defaultPrevented) this._tooltip.disabled = false;
    }

    _renderArt() {
        if (this.src && this.deferred) {
            return html`<span class="pending" role="img" aria-label=${this._alt}></span>`;
        }
        if (this.src) {
            return html`<img class="img" src=${this.src} alt=${this._alt} loading="lazy" />`;
        }
        return html`
            <span class="blank" role="img" aria-label=${this._alt}>
                <span class="blank__title">${this.bookTitle}</span>
                ${this.authors && this.size !== 'small' ? html`<span class="blank__author">${this.authors}</span>` : nothing}
            </span>
        `;
    }

    _renderTip() {
        return html`
            <div slot="content" class="tip">
                <div>
                    <span class="tip__title">${this.bookTitle}</span>
                    ${this.year ? html`<span class="tip__year">(${this.year})</span>` : nothing}
                </div>
                ${this.authors ? html`<div class="tip__byline">${this.authors}</div>` : nothing}
            </div>
        `;
    }

    /** Reflects keyboard focus on the link to the host, which draws the ring. */
    _onFocus(e) {
        this.toggleAttribute('link-focus', e.target.matches(':focus-visible'));
    }

    _onBlur() {
        this.removeAttribute('link-focus');
    }

    _onClick() {
        this.dispatchEvent(new CustomEvent('ol-book-cover-click', {
            bubbles: true,
            composed: true,
            detail: { href: this.href },
        }));
    }
}

customElements.define('ol-book-cover', OlBookCover);
