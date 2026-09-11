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
        }

        /* Wraps the cover link only, keeping the overlay out of the trigger area. */
        ol-tooltip {
            display: block;
            height: 100%;
        }

        .img {
            display: block;
            width: 100%;
            height: 100%;
            object-fit: cover;
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
            ? html`<a class="link" href=${this.href} @click=${this._onClick}>${this._renderArt()}</a>`
            : this._renderArt();
        return html`
            <ol-tooltip placement="top" arrow>${art}${this._renderTip()}</ol-tooltip>
            <slot name="overlay"></slot>
        `;
    }

    _renderArt() {
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

    _onClick() {
        this.dispatchEvent(new CustomEvent('ol-book-cover-click', {
            bubbles: true,
            composed: true,
            detail: { href: this.href },
        }));
    }
}

customElements.define('ol-book-cover', OlBookCover);
