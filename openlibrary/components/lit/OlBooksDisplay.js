import { LitElement, css, html, nothing } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { ifDefined } from 'lit/directives/if-defined.js';
import { icon } from './utils/book-icons.js';
import { fetchBooks, fetchUserState, setShelf, queuePendingAction, redirectToLogin, SHELF } from './utils/books-api.js';
import { trackEvent } from '../../plugins/openlibrary/js/ol.analytics.js';
import { fmt, DEFAULT_LABELS as ACTION_LABELS } from './OlBookActions.js';
import { showToast } from './OlToastRegion.js';
import './OLButton.js';
import './OlCarousel.js';
import './OlTooltip.js';
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
 * Renders into its shadow root, so its styles live in `static styles` and the
 * page cascade can't reach them. The two sitewide click delegations that a
 * shadow boundary defeats are handled here instead: Matomo events are pushed
 * by hand through `trackEvent`, and a logged-out CTA queues its own pending
 * action rather than relying on the `.js-login-intent` document handler.
 * `static/css/components/ol-books-display.css` keeps only the pre-upgrade
 * rules for the host tag.
 *
 * @element ol-books-display
 *
 * @prop {String} query   - Solr work query
 * @prop {String} fallbackQuery - Query to retry with when `query` returns nothing
 *     (e.g. the same query without the user-language filter)
 * @prop {Array} books    - Book cards to render instead of querying: same shape
 *     as the `docs` the endpoint returns. No search request is made and there
 *     is no next page, so the whole set is passed at once (used by the design
 *     gallery); the signed-in reader's state is still overlaid
 * @prop {String} sort    - Solr sort (default "new")
 * @prop {Number} limit   - Page size (default 20)
 * @prop {String} title   - Section heading
 * @prop {String} url     - "See all" link
 * @prop {String} view    - "covers" | "list" (default "covers")
 * @prop {Boolean} hasFulltextOnly - Restrict to readable books (default true; attr has-fulltext-only="false" to disable)
 * @prop {Boolean} safeMode - Hide content-warning covers (default true; attr safe-mode="false" to disable)
 * @prop {String} userKey - "/people/<username>" when signed in; empty when not
 * @prop {String} analyticsKey - Label on the Matomo events this reports
 * @prop {Object} labels  - Translated strings, merged over DEFAULT_LABELS
 *
 * @fires ol-books-display-view-change - detail: { view }
 */
export const DEFAULT_LABELS = {
    ...ACTION_LABELS,
    by: 'by %(name)s',
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
    ratingsOne: '%(count)s rating',
    ratingsMany: '%(count)s ratings',
    ratingsAverage: 'Rated %(average)s out of 5',
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
        books: { type: Array },
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

    static styles = css`
        :host {
            display: block;
            /* Hold to the container even inside flex/grid parents: the
               carousel's track is wide, and must never set this element's
               width. */
            width: 100%;
            min-width: 0;
            box-sizing: border-box;
            font-family: var(--font-family-body);
            color: var(--color-text);
        }

        .obd__header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: var(--spacing-inline-md);
            margin-bottom: var(--spacing-stack-sm);
        }

        /* Color and weight came from the page's h1-h6 rule until this moved
           into a shadow root; they are declared here to keep the same look. */
        .obd__title {
            margin: 0;
            font-family: var(--font-family-heading);
            font-size: var(--font-size-title-large);
            font-weight: 600;
            line-height: var(--line-height-heading);
            color: var(--color-text-secondary);
        }

        /* Inherit the surrounding text color; the page's a:link rules stop
           at the shadow boundary. */
        .obd-link {
            color: inherit;
            text-decoration: none;
        }

        .obd-link:hover {
            text-decoration: underline;
        }

        .obd__status {
            display: flex;
            align-items: center;
            gap: var(--spacing-inline-md);
            padding: var(--spacing-inset-lg);
            color: var(--color-text-secondary);
        }

        .obd__link-btn {
            padding: 0;
            border: 0;
            background: none;
            color: var(--color-link);
            font: inherit;
            cursor: pointer;
            text-decoration: none;
        }

        .obd__link-btn:hover {
            text-decoration: underline;
        }

        .obd__link-btn:disabled {
            color: var(--color-text-muted);
            cursor: default;
            text-decoration: none;
        }

        .obd__link-btn:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: 2px;
            border-radius: var(--border-radius-sm);
        }

        /* ── Shared: covers, CTAs ─────────────────────────────────── */

        .obd-cover {
            position: relative;
            display: block;
            aspect-ratio: 2 / 3;
            border-radius: var(--border-radius-thumbnail);
            overflow: hidden;
            background: var(--color-surface-sunken);
        }

        .obd-cover__link {
            display: block;
            height: 100%;
        }

        /* Wraps the cover link only, keeping the save button out of the trigger
           area. */
        .obd-cover > ol-tooltip {
            display: block;
            height: 100%;
        }

        /* Slotted content lives in the light DOM; only the panel comes from ol-tooltip. */
        .obd-tip {
            font-size: var(--font-size-body-medium);
        }

        .obd-tip__title {
            font-weight: 600;
        }

        .obd-tip__year,
        .obd-tip__byline {
            color: var(--neutral-300);
        }

        .obd-tip__byline {
            font-size: var(--font-size-label-medium);
        }

        .obd-cover__img {
            display: block;
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .obd-cover__blank {
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            height: 100%;
            box-sizing: border-box;
            padding: var(--spacing-inset-md);
            background: linear-gradient(160deg, var(--neutral-600), var(--neutral-800));
            color: var(--color-text-inverse);
            text-align: center;
        }

        .obd-cover__blank-title {
            font-family: var(--font-family-heading);
            font-size: var(--font-size-title-medium);
            font-weight: 700;
            line-height: var(--line-height-tight);
            overflow: hidden;
            display: -webkit-box;
            -webkit-box-orient: vertical;
            -webkit-line-clamp: 4;
        }

        .obd-cover__blank-author {
            font-size: var(--font-size-label-small);
            letter-spacing: 0.08em;
            text-transform: uppercase;
            opacity: 0.85;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .obd-cta-form {
            margin: 0;
        }

        /* ── Covers view (carousel cards) ─────────────────────────── */

        .obd__carousel {
            --ol-carousel-viewport-padding: 6px;

            min-width: 0;
        }

        .obd-card {
            display: flex;
            flex-direction: column;
            gap: var(--spacing-stack-xs);
            min-width: 0;
        }

        .obd-card .obd-cover {
            margin-bottom: var(--spacing-stack-xs);
        }

        .obd-card__meta {
            display: flex;
            flex-direction: column;
            gap: var(--spacing-stack-xs);
            min-width: 0;
        }

        /* On a fine pointer the cover tooltip carries title/year/author instead. Same
           query ol-tooltip arms with, so exactly one of the two shows. */
        @media (hover: hover) and (pointer: fine) {
            .obd-card__meta {
                display: none;
            }
        }

        /* Clamped as one line so the year wraps with the title. */
        .obd-card__heading {
            overflow: hidden;
            display: -webkit-box;
            -webkit-box-orient: vertical;
            -webkit-line-clamp: 2;
        }

        .obd-card__title {
            font-family: var(--font-family-heading);
            font-size: var(--font-size-title-small);
            font-weight: 600;
            line-height: var(--line-height-tight);
            color: var(--color-text);
            text-decoration: none;
        }

        .obd-card__title:hover {
            text-decoration: underline;
        }

        .obd-card__year {
            font-size: var(--font-size-title-small);
            color: var(--color-text-secondary);
        }

        .obd-card__author {
            font-size: var(--font-size-label-medium);
            color: var(--color-text-secondary);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .obd-card__cta {
            margin-top: auto;
        }

        /* Corner save button: "+" until the book is on a shelf, then a filled check.
           Signed in, the button is slotted into <ol-book-actions>, whose popover host
           is position: relative — so the wrapper takes the corner and the button
           goes static inside it. */
        .obd-save,
        .obd-cover > ol-book-actions {
            position: absolute;
            top: 4px;
            right: 4px;
        }

        .obd-save {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 32px;
            height: 32px;
            padding: 0;
            border: 0;
            background: transparent;
            color: var(--color-text);
            cursor: pointer;
            --control-highlight-strength: 35%;
            transition: transform 0.08s;
        }

        /* The visible circle is smaller than the 32px hit target. Same inset
           specular edge as ol-button; the drop shadow is heavier since it floats
           over cover art. */
        .obd-save::before {
            content: "";
            position: absolute;
            inset: 4px;
            border-radius: var(--border-radius-circle);
            background: var(--white);
            box-shadow:
                0 1px 4px var(--boxshadow-black),
                inset 0 1px 0
                    color-mix(
                        in srgb,
                        var(--white) var(--control-highlight-strength),
                        var(--control-surface)
                    );
        }

        .obd-save .obd-icon {
            position: relative;
            width: 14px;
            height: 14px;
        }

        .obd-save:hover {
            transform: scale(1.08);
        }

        .obd-save:active {
            transform: scale(0.95);
        }

        .obd-save:focus-visible {
            outline: none;
        }

        .obd-save:focus-visible::before {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        .obd-save--on {
            color: var(--white);
            --control-surface: var(--primary-blue);
            --control-highlight-strength: 18%;
        }

        .obd-save--on::before {
            background: var(--primary-blue);
        }

        .obd-cover > ol-book-actions .obd-save {
            position: relative;
            top: auto;
            right: auto;
        }

        /* ── List view (rows) ─────────────────────────────────────── */

        .obd__list-wrap {
            border: var(--border-card);
            border-radius: var(--border-radius-card);
            background: var(--color-surface);
        }

        .obd__list {
            margin: 0;
            padding: 0;
            list-style: none;
        }

        .obd-row {
            display: grid;
            grid-template-columns: 72px minmax(0, 1fr) auto;
            gap: var(--spacing-inline-lg);
            align-items: start;
            padding: var(--spacing-inset-md);
            border-bottom: var(--border-divider);
        }

        .obd-row:last-child {
            border-bottom: 0;
        }

        .obd-row__cover {
            width: 72px;
        }

        .obd-row__body {
            display: flex;
            flex-direction: column;
            gap: 2px;
            min-width: 0;
        }

        .obd-row__title {
            font-family: var(--font-family-heading);
            font-size: var(--font-size-title-medium);
            font-weight: 600;
            line-height: var(--line-height-tight);
            color: var(--color-text);
            text-decoration: none;
        }

        .obd-row__title:hover {
            text-decoration: underline;
        }

        .obd-row__author {
            font-size: var(--font-size-body-medium);
            color: var(--color-text-secondary);
            margin-bottom: var(--spacing-stack-xs);
        }

        .obd-row__year {
            font-size: var(--font-size-title-medium);
            color: var(--color-text-secondary);
        }

        .obd-row__rating {
            display: flex;
            align-items: center;
            gap: var(--spacing-inline-xs);
            font-size: var(--font-size-label-medium);
            color: var(--color-text-secondary);
        }

        .obd-stars {
            display: inline-flex;
            color: var(--gold);
        }

        .obd-stars .obd-icon {
            width: 14px;
            height: 14px;
        }

        .obd-row__actions {
            display: flex;
            flex-direction: column;
            align-items: stretch;
            gap: var(--spacing-stack-xs);
            width: 200px;
        }

        /* Split shelf button: main toggles the shown shelf, chevron opens the menu. */
        .obd-shelf {
            display: flex;
            border: 1px solid var(--color-border-subtle);
            border-radius: var(--border-radius-button);
            overflow: hidden;
            background: var(--white);
        }

        .obd-shelf--on {
            border-color: var(--color-control-selected-border);
            background: var(--color-control-selected-bg);
        }

        .obd-shelf__main,
        .obd-shelf__more {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
            height: calc(var(--control-height-medium) - 2px);
            border: 0;
            background: none;
            color: var(--color-text);
            font-family: var(--font-family-button);
            font-size: var(--font-size-body-medium);
            font-weight: 600;
            cursor: pointer;
        }

        .obd-shelf__main {
            flex: 1;
            min-width: 0;
            padding: 0 var(--spacing-sm);
            white-space: nowrap;
            overflow: hidden;
        }

        .obd-shelf__main span {
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .obd-shelf__main--on {
            color: var(--color-link);
        }

        .obd-shelf > ol-book-actions {
            display: flex;
        }

        .obd-shelf__more {
            width: 40px;
            border-left: 1px solid var(--color-border-subtle);
        }

        .obd-shelf--on .obd-shelf__more {
            border-left-color: var(--color-control-selected-border);
            color: var(--color-link);
        }

        .obd-shelf__main:hover,
        .obd-shelf__more:hover {
            background: var(--color-hover-overlay);
        }

        .obd-shelf__main:focus-visible,
        .obd-shelf__more:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: -2px;
        }

        .obd-shelf .obd-icon {
            width: 16px;
            height: 16px;
            flex: 0 0 16px;
        }

        .obd__list-footer {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: var(--spacing-inline-md);
            padding: var(--spacing-inset-md);
            border-top: var(--border-divider);
            font-size: var(--font-size-body-medium);
        }

        .obd__dot {
            color: var(--color-text-muted);
        }

        @media (max-width: 600px) {
            .obd-row {
                grid-template-columns: 56px minmax(0, 1fr);
            }

            .obd-row__cover {
                width: 56px;
            }

            .obd-row__actions {
                grid-column: 1 / -1;
                flex-direction: row;
                width: auto;
            }

            /* Share the row by content width, not equal halves — an equal split
               ellipsizes "Want to Read" while a short CTA sits in dead space. */
            .obd-row__actions > * {
                flex: 1 1 auto;
            }

            /* Undo full-width so the CTA sizes to its label: both the host
               (its flex-basis) and the control ol-button stretches inside it.
               Left on, the CTA takes ~2/3 of the row and ellipsizes the shelf
               button beside it. */
            .obd-row__cta[full-width] {
                width: auto;
            }

            .obd-row__cta[full-width]::part(control) {
                width: auto;
            }

            .obd-row__title,
            .obd-row__year {
                font-size: var(--font-size-title-small);
            }

            /* Cards are narrow here, and the meta only shows on touch. */
            .obd-card__title,
            .obd-card__year {
                font-size: var(--font-size-label-medium);
            }

            .obd-card__author {
                font-size: var(--font-size-label-small);
            }
        }
    `;

    constructor() {
        super();
        this.query = '';
        this.books = null;
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
        // Nothing to fetch when the books were handed to us.
        if (this.books) {
            this.start();
            return;
        }
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
        if (this.books) {
            this._docs = this.books;
            this._numFound = this.books.length;
            // Nothing to fetch, but a signed-in reader's shelf and rating
            // still overlay a set that was handed to us.
            this._loadUserState(this._docs.map(doc => doc.key));
            return;
        }
        this.loadMore();
    }

    /** Fetch the next page and append it. Resolves when the DOM has updated. */
    async loadMore() {
        if (this.books || this._loading || !this.hasMore) return;
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
            ${this._renderHeader()}
            ${this._error ? this._renderError() : this._renderView()}
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

    /** "(1846)" — the year that trails the title, unbolded beside it. */
    _renderYear(doc, cls) {
        return doc.first_publish_year ? html`<span class=${cls}>(${doc.first_publish_year})</span>` : nothing;
    }

    /**
     * The cover's hover card: title, year and author. `ol-tooltip` arms on the
     * same media query the CSS hides the card text with, so a pointer gets the
     * tooltip and touch gets the card text — never both.
     */
    _renderCoverTip(doc) {
        const authors = this._authorsText(doc);
        return html`
            <div slot="content" class="obd-tip">
                <div class="obd-tip__heading">
                    <span class="obd-tip__title">${doc.title}</span> ${this._renderYear(doc, 'obd-tip__year')}
                </div>
                ${authors ? html`<div class="obd-tip__byline">${authors}</div>` : nothing}
            </div>
        `;
    }

    _renderCoverCard(doc) {
        const { shelf, rating } = this._stateFor(doc);
        return html`
            <div class="obd-card" data-key=${doc.key}>
                <div class="obd-cover">
                    <ol-tooltip placement="top" arrow>
                        <a class="obd-cover__link" href=${doc.key} @click=${() => this._track('CoverClick')}>
                            ${this._renderCover(doc)}
                        </a>
                        ${this._renderCoverTip(doc)}
                    </ol-tooltip>
                    ${this._renderSaveButton(doc, shelf, rating)}
                </div>
                <div class="obd-card__meta">
                    <div class="obd-card__heading">
                        <a class="obd-card__title" href=${doc.key}>${doc.title}</a> ${this._renderYear(doc, 'obd-card__year')}
                    </div>
                    ${this._renderByline(doc, 'obd-card__author')}
                </div>
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
                    <div class="obd-row__heading">
                        <a class="obd-row__title" href=${doc.key}>${doc.title}</a> ${this._renderYear(doc, 'obd-row__year')}
                    </div>
                    ${this._renderByline(doc, 'obd-row__author')}
                    ${this._renderRating(doc)}
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
        const primary = ['read', 'audiobook', 'borrow', 'special_access', 'preview'].includes(access.cta);
        const variant = primary ? 'primary' : 'secondary';

        // No URL: the CTA is reporting a state the reader can't act on
        // ("Checked Out", "Not in Library") rather than offering a way in.
        if (!access.url) {
            return html`<ol-button class=${cls} variant=${variant} full-width disabled>${label}</ol-button>`;
        }
        if (access.method === 'post') {
            return html`
                <form method="POST" action=${access.url} class="obd-cta-form">
                    <input type="hidden" name="action" value="join-waitinglist" />
                    <ol-button class=${cls} type="submit" variant=${variant} full-width @click=${() => this._track('CTAClick')}>${label}</ol-button>
                </form>
            `;
        }
        const loginIntent = access.login_intent && !this.userKey;
        return html`
            <ol-button
                class=${cls}
                variant=${variant}
                full-width
                href=${access.url}
                target=${ifDefined(access.external ? '_blank' : undefined)}
                rel=${ifDefined(access.external ? 'noopener noreferrer' : undefined)}
                @click=${() => this._onCtaClick(doc, label, loginIntent)}
            >${label}${access.external ? icon('arrow-up-right', { slot: 'icon-end' }) : nothing}</ol-button>
        `;
    }

    _actionsBook(doc) {
        return { key: doc.key, title: doc.title, firstPublishYear: doc.first_publish_year, editionKey: doc.edition_key };
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

    /**
     * Report a Matomo event. `data-ol-link-track` is invisible to Matomo's
     * document-level click trigger from in here — the click retargets to the
     * host on its way out of the shadow root — so report by hand.
     */
    _track(action) {
        trackEvent('BookCarousel', action, this.analyticsKey);
    }

    /**
     * The CTA is an ordinary navigation, and stays one: a logged-out visitor
     * still lands on the target URL, having queued what they were doing so the
     * page can resume it after they sign in. That queueing used to come from
     * the sitewide `.js-login-intent` handler, which the shadow boundary hides
     * this link from.
     */
    _onCtaClick(doc, label, loginIntent) {
        this._track('CTAClick');
        if (!loginIntent) return;
        queuePendingAction({
            action: label,
            title: doc.title,
            resumeUrl: doc.edition_key ? `/books/${doc.edition_key}` : undefined,
        });
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
