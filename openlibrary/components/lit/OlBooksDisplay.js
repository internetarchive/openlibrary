import { LitElement, html, nothing } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { ifDefined } from 'lit/directives/if-defined.js';
import { icon } from './utils/book-icons.js';
import { fetchBooks, fetchUserState, setShelf, redirectToLogin, SHELF } from './utils/books-api.js';
import { fmt, DEFAULT_LABELS as ACTION_LABELS } from './OlBookActions.js';
import { showToast } from './OlToastRegion.js';
import './OlCarousel.js';
import './OlSegmentedControl.js';
import './OlBookActions.js';

/**
 * A titled set of books for a Solr query, switchable between views. Fetches
 * from `/books-display.json`, overlays the signed-in user's shelf/rating from
 * `/books-display/user-state.json`, and hands per-book actions to
 * `<ol-book-actions>`.
 *
 * `view` is an open enum: `covers` (an `<ol-carousel>` of cover cards) and
 * `list` (full-width rows) today; more layouts (e.g. a multi-row grid) slot in
 * alongside without changing the data path.
 *
 * Renders into the light DOM (like `<ol-button>`) so `<ol-carousel>` gets the
 * cards as real children, sitewide handlers (`.js-login-intent`, analytics)
 * keep working, and `static/css/components/ol-books-display.css` styles it.
 *
 * @element ol-books-display
 *
 * @prop {String} query   - Solr work query
 * @prop {String} fallbackQuery - Query to retry with when `query` returns nothing
 *     (e.g. the same query without the user-language filter)
 * @prop {String} sort    - Solr sort (default "new")
 * @prop {Number} limit   - Page size (default 20)
 * @prop {String} title   - Section heading
 * @prop {String} url     - "See all" link
 * @prop {String} view    - "covers" | "list" (default "covers")
 * @prop {Boolean} hasFulltextOnly - Restrict to readable books (default true; attr has-fulltext-only="false" to disable)
 * @prop {Boolean} safeMode - Hide content-warning covers (default true; attr safe-mode="false" to disable)
 * @prop {String} userKey - "/people/<username>" when signed in; empty when not
 * @prop {String} analyticsKey - Suffix for data-ol-link-track values
 * @prop {Object} labels  - Translated strings, merged over DEFAULT_LABELS
 *
 * @fires ol-books-display-view-change - detail: { view }
 */
export const DEFAULT_LABELS = {
    ...ACTION_LABELS,
    viewAs: 'View as',
    covers: 'Covers',
    list: 'List',
    save: 'Save %(title)s to your reading log',
    saved: '%(title)s is on your reading log',
    read: 'Read',
    audiobook: 'Audiobook',
    borrow: 'Borrow',
    specialAccess: 'Special Access',
    preview: 'Preview',
    joinWaitlist: 'Join Waitlist',
    checkedOut: 'Checked Out',
    findInLibrary: 'Find in a library',
    notInLibrary: 'Not in Library',
    notOnline: 'Not online',
    previewBadge: 'Preview',
    ratingsOne: '%(count)s rating',
    ratingsMany: '%(count)s ratings',
    ratingsAverage: 'Rated %(average)s out of 5',
    firstPublished: 'First published %(year)s',
    shelfMenu: 'More options for %(title)s',
    showMore: 'Show %(count)s more',
    collapse: 'Collapse',
    seeAll: 'See all',
    loading: 'Loading…',
    loadError: 'Couldn’t load these books.',
    retry: 'Retry',
    empty: 'No books found.',
};

const CTA_LABEL = {
    read: 'read',
    audiobook: 'audiobook',
    borrow: 'borrow',
    special_access: 'specialAccess',
    preview: 'preview',
    join_waitlist: 'joinWaitlist',
    checked_out: 'checkedOut',
    find_in_library: 'findInLibrary',
    not_in_library: 'notInLibrary',
};

const SHELF_LABEL = {
    [SHELF.WANT_TO_READ]: 'wantToRead',
    [SHELF.CURRENTLY_READING]: 'currentlyReading',
    [SHELF.ALREADY_READ]: 'alreadyRead',
    [SHELF.STOPPED_READING]: 'stoppedReading',
};

const VIEWS = ['covers', 'list'];

export class OlBooksDisplay extends LitElement {
    static properties = {
        query: { type: String },
        fallbackQuery: { type: String, attribute: 'fallback-query' },
        sort: { type: String },
        limit: { type: Number },
        title: { type: String },
        url: { type: String },
        view: { type: String, reflect: true },
        // Default-true flags: written as has-fulltext-only="false" to turn off,
        // since a bare boolean attribute can't express false.
        hasFulltextOnly: { attribute: 'has-fulltext-only', converter: v => v !== 'false' },
        safeMode: { attribute: 'safe-mode', converter: v => v !== 'false' },
        userKey: { type: String, attribute: 'user-key' },
        analyticsKey: { type: String, attribute: 'analytics-key' },
        labels: { type: Object },
        _docs: { state: true },
        _numFound: { state: true },
        _loading: { state: true },
        _error: { state: true },
        _visible: { state: true },
        _userState: { state: true },
    };

    createRenderRoot() {
        return this;
    }

    constructor() {
        super();
        this.query = '';
        this.fallbackQuery = '';
        this.sort = 'new';
        this.limit = 20;
        this.title = '';
        this.url = '';
        this.view = 'covers';
        this.hasFulltextOnly = true;
        this.safeMode = true;
        this.userKey = '';
        this.analyticsKey = '';
        this.labels = {};
        this._docs = [];
        this._numFound = null;
        this._loading = false;
        this._error = false;
        this._visible = 0;
        this._userState = { shelves: {}, ratings: {} };
        this._started = false;
    }

    t(key, vars) {
        const s = this.labels?.[key] ?? DEFAULT_LABELS[key] ?? key;
        return vars ? fmt(s, vars) : s;
    }

    get docs() {
        return this._docs;
    }

    get hasMore() {
        return this._numFound === null || this._docs.length < this._numFound;
    }

    connectedCallback() {
        super.connectedCallback();
        // Defer the first fetch until the section is near the viewport, as
        // the legacy lazy carousel does.
        if ('IntersectionObserver' in window) {
            this._observer = new IntersectionObserver(entries => {
                if (entries.some(e => e.isIntersecting)) {
                    this._observer.disconnect();
                    this.start();
                }
            }, { rootMargin: '200px' });
            this._observer.observe(this);
        } else {
            this.start();
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._observer?.disconnect();
    }

    /** Kick off the first fetch (idempotent). */
    start() {
        if (this._started) return;
        this._started = true;
        this._visible = this.limit;
        this.loadMore();
    }

    /** Fetch the next page and append it. Resolves when the DOM has updated. */
    async loadMore() {
        if (this._loading || !this.hasMore) return;
        this._loading = true;
        this._error = false;
        try {
            const page = await fetchBooks({
                q: this.query,
                sort: this.sort,
                limit: this.limit,
                offset: this._docs.length,
                hasFulltextOnly: this.hasFulltextOnly,
                safeMode: this.safeMode,
            });
            this._docs = [...this._docs, ...page.docs];
            this._numFound = page.num_found;
            this._loadUserState(page.docs.map(d => d.key));
            if (!this._docs.length && this.fallbackQuery && this.fallbackQuery !== this.query) {
                // Nothing under the narrow query (typically the user-language
                // filter): widen once and refetch.
                this.query = this.fallbackQuery;
                this._numFound = null;
                this._loading = false;
                return this.loadMore();
            }
        } catch (error) {
            this._error = true;
        } finally {
            this._loading = false;
        }
        await this.updateComplete;
    }

    async _loadUserState(keys) {
        if (!this.userKey || !keys.length) return;
        try {
            const state = await fetchUserState(keys);
            this._userState = {
                shelves: { ...this._userState.shelves, ...state.shelves },
                ratings: { ...this._userState.ratings, ...state.ratings },
            };
        } catch (error) {
            // Not fatal — cards simply show no shelf state.
        }
    }

    _stateFor(doc) {
        const id = doc.key.split('/').pop();
        return {
            shelf: this._userState.shelves[id] ?? null,
            rating: this._userState.ratings[id] ?? null,
        };
    }

    // ── Render ───────────────────────────────────────────────

    render() {
        return html`
            <div class="obd">
                ${this._renderHeader()}
                ${this._error ? this._renderError() : this._renderView()}
            </div>
        `;
    }

    _renderHeader() {
        return html`
            <div class="obd__header">
                <h2 class="obd__title">
                    ${this.url ? html`<a class="obd-link" href=${this.url}>${this.title}</a>` : this.title}
                </h2>
                <ol-segmented-control
                    class="obd__toggle"
                    size="small"
                    .value=${this.view}
                    accessible-label=${this.t('viewAs')}
                    @ol-segmented-control-change=${this._onViewChange}
                >
                    <ol-segment value="covers" label="">${icon('covers-row')} <span>${this.t('covers')}</span></ol-segment>
                    <ol-segment value="list" label="">${icon('list')} <span>${this.t('list')}</span></ol-segment>
                </ol-segmented-control>
            </div>
        `;
    }

    _renderError() {
        return html`
            <div class="obd__status" role="alert">
                ${this.t('loadError')}
                <button type="button" class="obd__link-btn" @click=${() => this.loadMore()}>${this.t('retry')}</button>
            </div>
        `;
    }

    _renderView() {
        if (!this._docs.length) {
            return html`<div class="obd__status" role="status">${this._loading || !this._started ? this.t('loading') : this.t('empty')}</div>`;
        }
        return this.view === 'list' ? this._renderList() : this._renderCovers();
    }

    _renderCovers() {
        return html`
            <ol-carousel
                class="obd__carousel"
                label=${this.title}
                gap="16"
                @ol-carousel-page-change=${this._onPageChange}
            >
                ${this._docs.map(doc => this._renderCoverCard(doc))}
            </ol-carousel>
        `;
    }

    _renderList() {
        const shown = this._docs.slice(0, this._visible);
        const remaining = (this._numFound ?? this._docs.length) - shown.length;
        return html`
            <div class="obd__list-wrap">
                <ul class="obd__list">
                    ${shown.map(doc => this._renderRow(doc))}
                </ul>
                <div class="obd__list-footer">
                    ${remaining > 0 ? html`
                        <button type="button" class="obd__link-btn" ?disabled=${this._loading} @click=${this._onShowMore}>
                            ${this.t('showMore', { count: Math.min(remaining, this.limit) })}
                        </button>
                    ` : nothing}
                    ${shown.length > this.limit ? html`
                        <span class="obd__dot" aria-hidden="true">·</span>
                        <button type="button" class="obd__link-btn" @click=${this._onCollapse}>${this.t('collapse')}</button>
                    ` : nothing}
                    ${this.url ? html`
                        <span class="obd__dot" aria-hidden="true">·</span>
                        <a class="obd__link-btn" href=${this.url}>${this.t('seeAll')} →</a>
                    ` : nothing}
                </div>
            </div>
        `;
    }

    _authorsText(doc) {
        return (doc.authors || []).map(a => a.name).filter(Boolean).join(', ');
    }

    _renderCover(doc, size) {
        const authors = this._authorsText(doc);
        const alt = authors ? `${doc.title} ${this.t('by', { name: authors })}` : doc.title;
        if (doc.cover_url) {
            return html`<img class="obd-cover__img" src=${doc.cover_url} alt=${alt} loading="lazy" />`;
        }
        return html`
            <span class="obd-cover__blank" role="img" aria-label=${alt}>
                <span class="obd-cover__blank-title">${doc.title}</span>
                ${authors && size !== 'small' ? html`<span class="obd-cover__blank-author">${authors}</span>` : nothing}
            </span>
        `;
    }

    _renderBadge(doc) {
        const badge = doc.access?.badge;
        if (!badge) return nothing;
        return html`<span class="obd-badge">${badge === 'preview' ? this.t('previewBadge') : this.t('notOnline')}</span>`;
    }

    _renderCoverCard(doc) {
        const { shelf, rating } = this._stateFor(doc);
        return html`
            <div class="obd-card" data-key=${doc.key}>
                <div class="obd-cover">
                    <a class="obd-cover__link" href=${doc.key} data-ol-link-track="BookCarousel|CoverClick|${this.analyticsKey}">
                        ${this._renderCover(doc)}
                    </a>
                    ${this._renderBadge(doc)}
                    ${this._renderSaveButton(doc, shelf, rating)}
                </div>
                <a class="obd-card__title" href=${doc.key}>${doc.title}</a>
                ${this._renderByline(doc, 'obd-card__author')}
                ${this._renderCta(doc, 'obd-card__cta')}
            </div>
        `;
    }

    _renderRow(doc) {
        const { shelf, rating } = this._stateFor(doc);
        return html`
            <li class="obd-row" data-key=${doc.key}>
                <a class="obd-row__cover obd-cover" href=${doc.key}>${this._renderCover(doc, 'small')}</a>
                <div class="obd-row__body">
                    <a class="obd-row__title" href=${doc.key}>${doc.title}</a>
                    ${this._renderByline(doc, 'obd-row__author')}
                    ${this._renderRating(doc)}
                    ${doc.first_publish_year ? html`<div class="obd-row__meta">${this.t('firstPublished', { year: doc.first_publish_year })}</div>` : nothing}
                </div>
                <div class="obd-row__actions">
                    ${this._renderCta(doc, 'obd-row__cta')}
                    ${this._renderShelfSplit(doc, shelf, rating)}
                </div>
            </li>
        `;
    }

    _renderByline(doc, cls) {
        const authors = doc.authors || [];
        if (!authors.length) return nothing;
        const names = authors.map((a, i) => html`${i ? ', ' : ''}${a.key ? html`<a class="obd-link" href=${a.key}>${a.name}</a>` : a.name}`);
        return html`<div class=${cls}>${names}</div>`;
    }

    _renderRating(doc) {
        if (!doc.ratings_count) return nothing;
        const avg = doc.ratings_average || 0;
        const rounded = Math.round(avg);
        const count = doc.ratings_count.toLocaleString();
        return html`
            <div class="obd-row__rating">
                <span class="obd-stars" role="img" aria-label=${this.t('ratingsAverage', { average: avg.toFixed(1) })}>
                    ${[1, 2, 3, 4, 5].map(n => icon('star', { fill: n <= rounded ? 'currentColor' : 'none', strokeWidth: 1.5 }))}
                </span>
                <span class="obd-row__rating-text">${avg.toFixed(1)} · ${this.t(doc.ratings_count === 1 ? 'ratingsOne' : 'ratingsMany', { count })}</span>
            </div>
        `;
    }

    _renderCta(doc, cls) {
        const access = doc.access || {};
        const label = this.t(CTA_LABEL[access.cta] || 'notInLibrary');
        const track = `BookCarousel|CTAClick|${this.analyticsKey}`;
        const primary = ['read', 'audiobook', 'borrow', 'special_access', 'preview'].includes(access.cta);
        const classes = { 'obd-cta': true, 'obd-cta--primary': primary, 'obd-cta--secondary': !primary, [cls]: true };

        if (!access.url) {
            return html`<span class="${classMap({ ...classes, 'obd-cta--static': true })}">${label}</span>`;
        }
        if (access.method === 'post') {
            return html`
                <form method="POST" action=${access.url} class="obd-cta-form">
                    <input type="hidden" name="action" value="join-waitinglist" />
                    <button type="submit" class=${classMap(classes)} data-ol-link-track=${track}>${label}</button>
                </form>
            `;
        }
        const loginIntent = access.login_intent && !this.userKey;
        return html`
            <a
                class="${classMap({ ...classes, 'js-login-intent': loginIntent })}"
                href=${access.url}
                target=${ifDefined(access.external ? '_blank' : undefined)}
                rel=${ifDefined(access.external ? 'noopener noreferrer' : undefined)}
                data-ol-link-track=${track}
                data-action=${ifDefined(loginIntent ? label : undefined)}
                data-title=${ifDefined(loginIntent ? doc.title : undefined)}
                data-type=${ifDefined(loginIntent ? 'book' : undefined)}
                data-resumeurl=${ifDefined(loginIntent && doc.edition_key ? `/books/${doc.edition_key}` : undefined)}
            >${label}${access.external ? icon('arrow-up-right', { cls: 'obd-icon obd-cta__ext' }) : nothing}</a>
        `;
    }

    _actionsBook(doc) {
        return { key: doc.key, title: doc.title, authors: doc.authors, editionKey: doc.edition_key };
    }

    _renderSaveButton(doc, shelf, rating) {
        const saved = shelf !== null;
        const button = html`
            <button
                type="button"
                slot="trigger"
                class="obd-save ${classMap({ 'obd-save--on': saved })}"
                aria-label=${saved ? this.t('saved', { title: doc.title }) : this.t('save', { title: doc.title })}
                @click=${this.userKey ? undefined : e => this._onLoggedOutAction(e, doc)}
            >${icon(saved ? 'check' : 'plus', { strokeWidth: 2.5 })}</button>
        `;
        if (!this.userKey) return button;
        return html`
            <ol-book-actions
                .book=${this._actionsBook(doc)}
                .shelf=${shelf}
                .rating=${rating}
                .labels=${this.labels}
                user-key=${this.userKey}
                @ol-book-state-change=${this._onStateChange}
            >${button}</ol-book-actions>
        `;
    }

    _renderShelfSplit(doc, shelf, rating) {
        const on = shelf !== null;
        const label = this.t(SHELF_LABEL[shelf ?? SHELF.WANT_TO_READ]);
        const main = html`
            <button
                type="button"
                class="obd-shelf__main ${classMap({ 'obd-shelf__main--on': on })}"
                @click=${e => this._onShelfMainClick(e, doc, shelf)}
            >${on ? icon('check') : nothing}<span>${label}</span></button>
        `;
        const chevron = html`
            <button
                type="button"
                slot="trigger"
                class="obd-shelf__more"
                aria-label=${this.t('shelfMenu', { title: doc.title })}
                @click=${this.userKey ? undefined : e => this._onLoggedOutAction(e, doc)}
            >${icon('chevron-down')}</button>
        `;
        return html`
            <div class="obd-shelf ${classMap({ 'obd-shelf--on': on })}">
                ${main}
                ${this.userKey ? html`
                    <ol-book-actions
                        .book=${this._actionsBook(doc)}
                        .shelf=${shelf}
                        .rating=${rating}
                        .labels=${this.labels}
                        user-key=${this.userKey}
                        @ol-book-state-change=${this._onStateChange}
                    >${chevron}</ol-book-actions>
                ` : chevron}
            </div>
        `;
    }

    // ── Events ───────────────────────────────────────────────

    _onViewChange(e) {
        const view = e.detail?.value;
        if (!VIEWS.includes(view) || view === this.view) return;
        this.view = view;
        this.dispatchEvent(new CustomEvent('ol-books-display-view-change', { bubbles: true, detail: { view } }));
    }

    _onPageChange(e) {
        const { page, totalPages } = e.detail;
        if (page >= totalPages - 2) this.loadMore();
    }

    async _onShowMore() {
        const target = this._visible + this.limit;
        if (this._docs.length < target && this.hasMore) await this.loadMore();
        this._visible = Math.min(target, this._docs.length);
    }

    _onCollapse() {
        this._visible = this.limit;
        this.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }

    _onLoggedOutAction(e, doc) {
        e.preventDefault();
        redirectToLogin({ action: this.t('wantToRead'), title: doc.title, resumeUrl: doc.key });
    }

    _onStateChange(e) {
        const { key, shelf, rating } = e.detail;
        this._applyState(key, shelf, rating);
    }

    _applyState(key, shelf, rating) {
        const id = key.split('/').pop();
        const shelves = { ...this._userState.shelves };
        const ratings = { ...this._userState.ratings };
        if (shelf === null || shelf === undefined) delete shelves[id]; else shelves[id] = shelf;
        if (rating === null || rating === undefined) delete ratings[id]; else ratings[id] = rating;
        this._userState = { shelves, ratings };
    }

    async _onShelfMainClick(e, doc, shelf) {
        if (!this.userKey) return this._onLoggedOutAction(e, doc);
        const { rating } = this._stateFor(doc);
        // On a shelf → clicking removes; otherwise → Want to Read.
        const target = shelf ?? SHELF.WANT_TO_READ;
        const next = shelf === null ? SHELF.WANT_TO_READ : null;
        this._applyState(doc.key, next, rating);
        try {
            await setShelf(doc.key, target, { editionKey: doc.edition_key });
        } catch (error) {
            this._applyState(doc.key, shelf, rating);
            if (error?.status === 401) return this._onLoggedOutAction(e, doc);
            showToast(this.t('errorGeneric'), { type: 'error' });
        }
    }
}

customElements.define('ol-books-display', OlBooksDisplay);
