import { LitElement, html, css, nothing } from 'lit';

/**
 * OLSubjectHero - A visual masthead for subject (and later, genre) pages.
 *
 * Renders a darkened, blurred "cover wall" backdrop built from a list of book
 * cover IDs, with the page's heading content layered on top via a default slot.
 *
 * The textual content (heading, stats, description, search) is passed as
 * light-DOM slotted children so it stays server-rendered and crawlable, and
 * degrades gracefully to a plain heading if the component never hydrates.
 *
 * @property {Array<Number>} covers - Book cover IDs used to build the backdrop.
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

    static styles = css`
        :host {
            display: block;
            position: relative;
            overflow: hidden;
            border-radius: var(--border-radius-large, 12px);
            /* A warm fallback while/if covers are unavailable */
            background:
                linear-gradient(135deg, var(--dark-blue, #036) 0%, var(--primary-blue, #0376c2) 100%);
            color: var(--white, #fff);
            isolation: isolate;
        }

        .wall {
            position: absolute;
            inset: 0;
            display: flex;
            gap: 0;
            z-index: -2;
            /* Slight scale so the blur doesn't reveal the host edges */
            transform: scale(1.1);
            filter: blur(2px) saturate(1.1);
        }

        .wall img {
            flex: 1 0 auto;
            width: auto;
            height: 100%;
            object-fit: cover;
            min-width: 0;
            /* Covers are decorative here */
            opacity: 0.9;
        }

        /* Scrim: dark on the inline-start (where text sits), fading out */
        .scrim {
            position: absolute;
            inset: 0;
            z-index: -1;
            background:
                linear-gradient(
                    to right,
                    hsla(210, 60%, 12%, 0.92) 0%,
                    hsla(210, 60%, 12%, 0.78) 45%,
                    hsla(210, 60%, 12%, 0.5) 100%
                );
        }

        .content {
            position: relative;
            padding: 2.5rem 2rem;
            max-width: 46rem;
        }

        @media (max-width: 768px) {
            .content {
                padding: 1.75rem 1.25rem;
            }
        }

        /* Slotted content inherits the light text and gets sensible spacing. */
        ::slotted(h1) {
            margin: 0 0 0.5rem;
            color: var(--white, #fff);
            font-size: 2.4rem;
            line-height: 1.1;
        }

        ::slotted(*) {
            color: inherit;
        }
    `;

    constructor() {
        super();
        this.covers = [];
    }

    _coverUrl(id) {
        return `https://covers.openlibrary.org/b/id/${id}-M.jpg`;
    }

    _renderWall() {
        const ids = (this.covers || []).filter(Boolean);
        if (!ids.length) return nothing;

        return html`
            <div class="wall" aria-hidden="true">
                ${ids.map((id) => html`<img src=${this._coverUrl(id)} alt="" loading="lazy" />`)}
            </div>
        `;
    }

    render() {
        return html`
            ${this._renderWall()}
            <div class="scrim" aria-hidden="true"></div>
            <div class="content">
                <slot></slot>
            </div>
        `;
    }
}

customElements.define('ol-subject-hero', OLSubjectHero);
