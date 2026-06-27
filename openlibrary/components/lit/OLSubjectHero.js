import { LitElement, html, css, nothing } from 'lit';

/**
 * OLSubjectHero - A visual masthead for subject (and later, genre) pages.
 *
 * Renders a soft-tinted masthead with the page's heading content on the left
 * (a default slot) and an overlapping, fanned stack of representative book
 * covers on the right.
 *
 * The textual content (heading, stats, description, search) is passed as
 * light-DOM slotted children so it stays server-rendered and crawlable, and
 * degrades gracefully to a plain heading if the component never hydrates.
 *
 * @property {Array<Number>} covers - Book cover IDs used to build the stack.
 *   Pass as a JSON array attribute, e.g. covers="[123,456,789]".
 *
 * @example
 * <ol-subject-hero covers="[8231856, 240727]">
 *   <h1>Science Fiction</h1>
 * </ol-subject-hero>
 */
export class OLSubjectHero extends LitElement {
    static properties = {
        covers: { type: Array },
    };

    /** Max covers shown in the fanned stack. */
    static MAX_COVERS = 6;

    static styles = css`
        :host {
            display: block;
            position: relative;
            overflow: hidden;
            /* Rounded top, flat bottom so the masthead reads as one piece with
               the content that follows it. */
            border-radius: var(--border-radius-sm, 4px) var(--border-radius-sm, 4px) 0 0;
            /* Soft, warm tint; themeable per genre via --ol-subject-hero-bg. */
            background: var(--ol-subject-hero-bg, hsl(41, 34%, 91%));
            color: var(--dark-grey, #333);
            isolation: isolate;
        }

        .inner {
            display: flex;
            align-items: center;
            gap: 1rem;
            min-height: 220px;
        }

        .content {
            position: relative;
            flex: 1 1 auto;
            padding: 2.5rem 2rem;
            max-width: 46rem;
        }

        /* Fanned, overlapping cover stack on the inline-end side. */
        .cover-stack {
            flex: 0 0 auto;
            display: flex;
            align-items: flex-end;
            padding: 1.75rem 2rem 1.75rem 0;
            /* Purely decorative; never react to the pointer. */
            pointer-events: none;
        }

        .cover-stack__item {
            width: 5rem;
            aspect-ratio: 2 / 3;
            object-fit: cover;
            border-radius: var(--border-radius-sm, 4px);
            background: var(--lighter-grey, #e0e0e0);
            box-shadow: 0 4px 14px hsla(0, 0%, 0%, 0.22);
            /* Pivot from a point below the covers so they splay like a hand of
               cards: bases converge, tops fan out in an arc. */
            transform-origin: 50% 175%;
        }

        .cover-stack__item:not(:first-child) {
            margin-inline-start: -3.25rem;
        }

        @media (max-width: 900px) {
            .cover-stack {
                display: none;
            }
        }

        @media (max-width: 768px) {
            .content {
                padding: 1.75rem 1.25rem;
            }
        }

        @media (prefers-reduced-motion: reduce) {
            .cover-stack__item {
                transition: none;
            }
        }

        /* Slotted content gets sensible spacing. Colours come from
           subject-hero.css since slotted nodes live in the light DOM. */
        ::slotted(h1) {
            margin: 0 0 0.5rem;
            font-size: 2.6rem;
            line-height: 1.08;
            letter-spacing: -0.01em;
        }
    `;

    constructor() {
        super();
        this.covers = [];
    }

    _coverUrl(id) {
        return `https://covers.openlibrary.org/b/id/${id}-M.jpg`;
    }

    _renderStack() {
        const ids = (this.covers || []).filter(Boolean).slice(0, OLSubjectHero.MAX_COVERS);
        if (!ids.length) return nothing;

        const mid = (ids.length - 1) / 2;
        return html`
            <div class="cover-stack" aria-hidden="true">
                ${ids.map((id, i) => {
        // Rotate around the shared pivot below the covers; the arc/lift falls
        // out of the rotation, like spreading a hand of cards.
        const rot = (i - mid) * 8;
        return html`<img
                        class="cover-stack__item"
                        style="transform: rotate(${rot}deg); z-index: ${i};"
                        src=${this._coverUrl(id)}
                        alt=""
                        loading="lazy" />`;
    })}
            </div>
        `;
    }

    render() {
        return html`
            <div class="inner">
                <div class="content"><slot></slot></div>
                ${this._renderStack()}
            </div>
        `;
    }
}

customElements.define('ol-subject-hero', OLSubjectHero);
