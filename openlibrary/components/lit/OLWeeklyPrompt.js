import { LitElement, html, css, nothing } from 'lit';

/**
 * OLWeeklyPrompt - Weekly staff-curated book prompt widget
 *
 * Mobile-first: horizontal-scroll book strip on mobile, two-column grid on desktop (≥ 640px).
 * Data is passed via attributes/properties from the server-rendered template.
 * The `nominations-json` attribute accepts a JSON array of nomination objects.
 *
 * @property {String} prompt-title     - The prompt question
 * @property {String} prompt-desc      - Label, e.g. "Staff pick · Week of June 2"
 * @property {String} nominations-json - JSON array: [{title, coverUrl, score, workKey}]
 * @property {Number} total-voters     - Number of distinct voters across all nominations
 * @property {String} username         - Logged-in OL username, or empty string if anonymous
 * @property {String} prompt-url       - URL for the full prompt history page
 *
 * @fires ol-weekly-prompt-nominate - Fired when the "Nominate a Book" CTA is clicked.
 *   detail: { username: String }
 *
 * @example
 * <ol-weekly-prompt
 *   prompt-title="Non-fiction books that expanded your understanding of the world"
 *   prompt-desc="Staff pick · Week of June 2"
 *   nominations-json='[{"title":"Sapiens","coverUrl":"...","score":42,"workKey":"/works/OL16311446W"}]'
 *   total-voters="18"
 *   username="mekarpeles"
 * ></ol-weekly-prompt>
 */
export class OLWeeklyPrompt extends LitElement {
    static properties = {
        promptTitle: { type: String, attribute: 'prompt-title' },
        promptDesc: { type: String, attribute: 'prompt-desc' },
        nominationsJson: { type: String, attribute: 'nominations-json' },
        totalVoters: { type: Number, attribute: 'total-voters' },
        username: { type: String },
        promptUrl: { type: String, attribute: 'prompt-url' },
    };

    static styles = css`
        :host {
            display: block;
            container-type: inline-size;
        }

        /* ── Card wrapper ─────────────────────────────────── */
        .prompt-card {
            background: var(--white, #fff);
            border: 1px solid var(--color-border-subtle, #d8d8d8);
            border-radius: 8px;
            padding: 20px 16px 16px;
            display: flex;
            flex-direction: column;
            gap: 14px;
        }

        /* ── Header (label + title) ───────────────────────── */
        .prompt-label {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.75rem;
            font-family: var(--font-family-body, sans-serif);
            color: var(--mid-grey, #666);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 600;
        }

        .prompt-label svg {
            flex-shrink: 0;
        }

        .prompt-title {
            margin: 0;
            font-size: 1.125rem;
            font-family: var(--font-family-body, sans-serif);
            font-weight: 700;
            color: var(--dark-grey, #222);
            line-height: 1.4;
        }

        /* ── Book strip (mobile: horizontal scroll) ───────── */
        .book-strip {
            display: flex;
            gap: 10px;
            overflow-x: auto;
            scroll-snap-type: x mandatory;
            -webkit-overflow-scrolling: touch;
            padding-bottom: 4px;
            /* Hide scrollbar but keep scroll functionality */
            scrollbar-width: none;
        }

        .book-strip::-webkit-scrollbar {
            display: none;
        }

        .book-item {
            flex: 0 0 auto;
            scroll-snap-align: start;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 6px;
            width: 80px;
            text-decoration: none;
            color: inherit;
        }

        .book-cover-wrap {
            position: relative;
            width: 80px;
            height: 116px;
            border-radius: 3px;
            overflow: hidden;
            box-shadow: 0 2px 6px rgba(0,0,0,0.18);
            background: var(--lightest-grey, #f0f0f0);
            flex-shrink: 0;
        }

        .book-cover {
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }

        .book-cover-placeholder {
            width: 100%;
            height: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            background: var(--lightest-grey, #f0f0f0);
            color: var(--mid-grey, #999);
            font-size: 1.5rem;
        }

        .rank-badge {
            position: absolute;
            top: 4px;
            inset-inline-start: 4px;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            font-size: 0.65rem;
            font-weight: 800;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #fff;
            line-height: 1;
        }

        .rank-badge[data-rank="1"] { background: #c5922a; }
        .rank-badge[data-rank="2"] { background: #8d9498; }
        .rank-badge[data-rank="3"] { background: #a0714f; }

        .book-score {
            font-size: 0.7rem;
            color: var(--mid-grey, #666);
            font-family: var(--font-family-body, sans-serif);
        }

        .book-score-arrow {
            color: var(--primary-blue, #2075c2);
        }

        /* ── Empty state ──────────────────────────────────── */
        .empty-strip {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 0;
            color: var(--mid-grey, #888);
            font-size: 0.875rem;
            font-style: italic;
            font-family: var(--font-family-body, sans-serif);
        }

        .empty-strip svg {
            flex-shrink: 0;
            opacity: 0.4;
        }

        /* ── Stats + CTA row ──────────────────────────────── */
        .footer-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            flex-wrap: wrap;
        }

        .prompt-stats {
            font-size: 0.8rem;
            color: var(--mid-grey, #666);
            font-family: var(--font-family-body, sans-serif);
        }

        .nominate-btn {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 8px 16px;
            background: var(--primary-blue, #2075c2);
            color: #fff;
            border: none;
            border-radius: var(--border-radius-chip, 20px);
            font-family: var(--font-family-button, sans-serif);
            font-size: 0.875rem;
            font-weight: 600;
            cursor: pointer;
            white-space: nowrap;
            text-decoration: none;
        }

        @media (hover: hover) and (pointer: fine) {
            .nominate-btn:hover {
                filter: brightness(1.1);
            }
        }

        .nominate-btn:active {
            transform: scale(0.97);
        }

        .nominate-btn:focus-visible {
            outline: none;
            box-shadow: var(--box-shadow-focus, 0 0 0 3px rgba(32, 117, 194, 0.35));
        }

        /* ── View all link ────────────────────────────────── */
        .view-all {
            font-size: 0.8rem;
            color: var(--primary-blue, #2075c2);
            text-decoration: none;
            font-family: var(--font-family-body, sans-serif);
        }

        .view-all:hover {
            text-decoration: underline;
        }

        /* ── Desktop: two-column layout ───────────────────── */
        @container (min-width: 560px) {
            .prompt-card {
                flex-direction: row;
                align-items: flex-start;
                gap: 24px;
                padding: 24px;
            }

            .prompt-text-col {
                flex: 0 0 220px;
                display: flex;
                flex-direction: column;
                gap: 12px;
            }

            .prompt-title {
                font-size: 1.2rem;
            }

            .books-col {
                flex: 1;
                min-width: 0;
            }

            .book-strip {
                overflow-x: visible;
                flex-wrap: wrap;
                gap: 12px;
            }

            .book-item {
                width: 72px;
            }

            .book-cover-wrap {
                width: 72px;
                height: 104px;
            }
        }
    `;

    constructor() {
        super();
        this.promptTitle = '';
        this.promptDesc = '';
        this.nominationsJson = '[]';
        this.totalVoters = 0;
        this.username = '';
        this.promptUrl = '';
    }

    get _nominations() {
        try {
            return JSON.parse(this.nominationsJson);
        } catch {
            return [];
        }
    }

    _handleNominateClick() {
        this.dispatchEvent(new CustomEvent('ol-weekly-prompt-nominate', {
            bubbles: true,
            composed: true,
            detail: { username: this.username },
        }));
    }

    _renderLabel() {
        if (!this.promptDesc) return nothing;
        return html`
            <p class="prompt-label">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
                    stroke="currentColor" stroke-width="2.5"
                    stroke-linecap="round" stroke-linejoin="round"
                    aria-hidden="true">
                    <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
                    <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
                </svg>
                ${this.promptDesc}
            </p>
        `;
    }

    _renderCover(nom, rank) {
        const badge = rank <= 3 ? html`
            <span class="rank-badge" data-rank="${rank}" aria-label="Rank ${rank}">
                ${rank}
            </span>
        ` : nothing;

        const cover = nom.coverUrl ? html`
            <img class="book-cover" src="${nom.coverUrl}" alt="" loading="lazy" />
        ` : html`
            <div class="book-cover-placeholder" aria-hidden="true">📚</div>
        `;

        return html`
            <a class="book-item" href="${nom.workKey || '#'}"
               aria-label="${nom.title} — ${nom.score} vote${nom.score !== 1 ? 's' : ''}">
                <div class="book-cover-wrap">
                    ${cover}
                    ${badge}
                </div>
                <span class="book-score">
                    <span class="book-score-arrow" aria-hidden="true">▲</span>${nom.score}
                </span>
            </a>
        `;
    }

    _renderBooks() {
        const noms = this._nominations;
        if (noms.length === 0) {
            return html`
                <div class="empty-strip" role="status">
                    <svg width="28" height="28" viewBox="0 0 24 24" fill="none"
                        stroke="currentColor" stroke-width="1.5"
                        stroke-linecap="round" stroke-linejoin="round"
                        aria-hidden="true">
                        <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
                        <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
                    </svg>
                    Be the first to nominate a book
                </div>
            `;
        }
        return html`
            <div class="book-strip" role="list" aria-label="Top nominations">
                ${noms.map((nom, i) => html`
                    <div role="listitem">${this._renderCover(nom, i + 1)}</div>
                `)}
            </div>
        `;
    }

    _renderStats() {
        const noms = this._nominations;
        if (noms.length === 0 && !this.totalVoters) return nothing;
        const parts = [];
        if (noms.length) parts.push(`${noms.length} book${noms.length !== 1 ? 's' : ''}`);
        if (this.totalVoters) parts.push(`${this.totalVoters} reader${this.totalVoters !== 1 ? 's' : ''}`);
        return html`<span class="prompt-stats">${parts.join(' · ')}</span>`;
    }

    _renderCTA() {
        const href = this.username
            ? (this.promptUrl ? `${this.promptUrl}#nominate` : '#nominate')
            : (this.promptUrl ? `/account/login?redirect=${encodeURIComponent(this.promptUrl)}` : '/account/login');

        return html`
            <a class="nominate-btn" href="${href}" @click=${this._handleNominateClick}>
                Nominate a Book
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                    stroke="currentColor" stroke-width="2.5"
                    stroke-linecap="round" stroke-linejoin="round"
                    aria-hidden="true">
                    <path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>
                </svg>
            </a>
        `;
    }

    render() {
        const textCol = html`
            <div class="prompt-text-col">
                ${this._renderLabel()}
                <h2 class="prompt-title">${this.promptTitle}</h2>
                <div class="footer-row">
                    ${this._renderStats()}
                    ${this._renderCTA()}
                </div>
                ${this.promptUrl ? html`
                    <a class="view-all" href="${this.promptUrl}">See all prompts →</a>
                ` : nothing}
            </div>
        `;

        const booksCol = html`
            <div class="books-col">
                ${this._renderBooks()}
            </div>
        `;

        return html`
            <div class="prompt-card">
                ${textCol}
                ${booksCol}
            </div>
        `;
    }
}

customElements.define('ol-weekly-prompt', OLWeeklyPrompt);
