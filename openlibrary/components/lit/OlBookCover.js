import { LitElement, css, html, nothing } from 'lit';
import { translate } from './utils/labels.js';
import './OlTooltip.js';

export const DEFAULT_LABELS = {
    by: 'by %(name)s'
};

/**
 * A book cover standing in a 2:3 slot: the artwork when there is one, a generated
 * title/author panel when there isn't, and a corner for whatever the surface
 * wants to float over it.
 *
 * The slot is always 2:3, so a row of covers keeps one rhythm, but the artwork
 * inside it keeps its own proportions — as wide as the slot and as tall as the
 * book, standing on the slot's bottom edge, so a squat picture book and a tall
 * hardback read as different objects on one shelf. A cover taller than 2:3
 * shrinks to fit the slot's height instead. Until the image reports its size
 * the frame is 2:3, so a lazy cover lands where its placeholder was.
 *
 * Each cover carries a soft drop shadow and a faint spine shading along its
 * left edge, so it reads as a printed object lying on the page rather than a
 * tile. Both go on the frame, not the host — leave room for the shadow.
 *
 * Knows nothing about shelves, availability or search — give it a URL and a
 * title. `overlay` is the slot the save button goes in; the component owns the
 * corner position so a consumer never has to.
 *
 * A pointer gets a hover card carrying the title, year and author.
 * `ol-tooltip` arms on the same media query a cover-card layout uses to
 * hide that text below the cover, so exactly one of the two shows.
 *
 * A linked cover's hover/focus ring reaches 4px outside it; leave that much room.
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
 * @prop {Boolean} deferred - Holds the artwork back until removed (ol-carousel removes it near view)
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
        _ratio: { state: true }
    };

    static styles = css`
        :host {
            position: relative;
            display: block;
            aspect-ratio: 2 / 3;
            font-family: var(--font-family-body);
        }

        /* The frame stands on the slot's bottom edge, centred; the corner box
           sits in the same grid cell at the same size, so a slotted control
           tracks the artwork rather than the slot. */
        ol-tooltip {
            --_ratio: 0.6667;
            display: grid;
            place-items: end center;
            width: 100%;
            height: 100%;
        }

        /* Width/height of the artwork. 2:3 until the image reports its own.
           A tall cover is capped at the slot's height: the slot is 150% as
           tall as it is wide, so width = 150% × ratio hits that cap exactly. */
        .frame,
        .corner {
            grid-area: 1 / 1;
            box-sizing: border-box;
            width: min(100%, calc(150% * var(--_ratio)));
            aspect-ratio: var(--_ratio);
        }

        .frame {
            position: relative;
            display: block;
            border-radius: var(--border-radius-thumbnail);
            overflow: hidden;
            background: var(--color-surface-sunken);
            box-shadow: var(--box-shadow-cover);
        }

        /* Spine shading: a strip down the binding edge, darkest at the gutter,
           with a highlight where the board curves over. Fades toward the foot. */
        .frame--art::after {
            content: '';
            position: absolute;
            inset: 0;
            inset-inline-end: auto;
            width: 6%;
            pointer-events: none;
            background: linear-gradient(
                90deg,
                hsla(0, 0%, 0%, 0.35) 0%,
                hsla(0, 0%, 100%, 0.1) 12%,
                hsla(0, 0%, 100%, 0.4) 17%,
                hsla(0, 0%, 100%, 0.1) 37%,
                hsla(0, 0%, 0%, 0.1) 59%,
                hsla(0, 0%, 100%, 0.07) 85%,
                hsla(0, 0%, 100%, 0) 100%
            );
            mask-image: linear-gradient(hsla(0, 0%, 0%, 0.4) 0%, hsla(0, 0%, 0%, 1) 2.5%, hsla(0, 0%, 0%, 0.5) 40%, hsla(0, 0%, 0%, 0.2) 100%);
        }

        /* A book bound on the right has its spine there. */
        :host(:dir(rtl)) .frame--art::after {
            transform: scaleX(-1);
        }

        .corner {
            position: relative;
            pointer-events: none;
        }

        .link {
            outline: none;
        }

        @media (hover: hover) and (pointer: fine) {
            /* Zero-width at rest so hover grows it. Tucked under the edge to hide the corner seam. */
            :host([href]) .frame {
                outline: 0 solid var(--color-border-pointed);
                outline-offset: calc(-1 * var(--border-width-media));
                transition: outline-width var(--duration-fast) var(--ease-exit);
            }

            :host([href]) .link {
                transition: filter var(--duration-fast) var(--ease-exit);
            }
        }

        :host([link-focus]) .frame {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        @media (hover: hover) and (pointer: fine) {
            :host([href]:hover) .frame {
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
            :host([href]) .frame,
            :host([href]) .link {
                transition: none;
            }
        }

        /* Inset so a pale cover still separates from a pale page. */
        .img {
            display: block;
            width: 100%;
            height: 100%;
            object-fit: cover;
            border-radius: var(--border-radius-thumbnail);
            outline: var(--border-width-media) solid var(--color-border-media);
            outline-offset: calc(-1 * var(--border-width-media));
        }

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
        :host([size='small']) .blank {
            padding: var(--spacing-inset-xs);
        }

        :host([size='small']) .blank__title {
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
        slot[name='overlay']::slotted(*) {
            position: absolute;
            top: 4px;
            inset-inline-end: 4px;
            pointer-events: auto;
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
        this._ratio = 0;
    }

    t(key, vars) {
        return translate(this.labels, DEFAULT_LABELS, key, vars);
    }

    get _alt() {
        return this.authors ? `${this.bookTitle} ${this.t('by', { name: this.authors })}` : this.bookTitle;
    }

    render() {
        const hasArt = this.src && !this.deferred;
        const frame = `frame ${hasArt || !this.src ? 'frame--art' : ''}`;
        const art = this.href
            ? html`<a class="${frame} link" href=${this.href} @click=${this._onClick} @focus=${this._onFocus} @blur=${this._onBlur}>${this._renderArt()}</a>`
            : html`<span class=${frame}>${this._renderArt()}</span>`;
        const ratio = hasArt && this._ratio ? `--_ratio: ${this._ratio}` : nothing;
        return html`
            <ol-tooltip placement="top" arrow style=${ratio}>
                ${art}
                <div class="corner">
                    <slot name="overlay" @pointerdown=${this._hideTip} @ol-popover-open=${this._onOverlayOpen} @ol-popover-close=${this._onOverlayClose}></slot>
                </div>
                ${this._renderTip()}
            </ol-tooltip>
        `;
    }

    /** A cached image can be complete before its load event is wired up. */
    updated(changed) {
        if (changed.has('src')) this._ratio = 0;
        const img = this.renderRoot.querySelector('.img');
        if (img?.complete) this._onLoad({ target: img });
    }

    _onLoad(e) {
        const { naturalWidth, naturalHeight } = e.target;
        if (!naturalWidth || !naturalHeight) return;
        this._ratio = Math.round((naturalWidth / naturalHeight) * 1000) / 1000;
    }

    get _tooltip() {
        return this.renderRoot.querySelector('ol-tooltip');
    }

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
            return html`<img class="img" src=${this.src} alt=${this._alt} loading="lazy" @load=${this._onLoad} />`;
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

    /** The host draws the focus ring. */
    _onFocus(e) {
        this.toggleAttribute('link-focus', e.target.matches(':focus-visible'));
    }

    _onBlur() {
        this.removeAttribute('link-focus');
    }

    _onClick() {
        this.dispatchEvent(
            new CustomEvent('ol-book-cover-click', {
                bubbles: true,
                composed: true,
                detail: { href: this.href }
            })
        );
    }
}

customElements.define('ol-book-cover', OlBookCover);
