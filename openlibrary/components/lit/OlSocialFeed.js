import { LitElement, css, html } from 'lit';

/**
 * OlSocialFeed -- the social activity feed for My Books.
 *
 * Renders a stream of what other patrons are doing with books: shelving them,
 * rating them, gathering them into lists, liking each other's lists. Every
 * event carries the actions a reader would want next -- borrow or shelve the
 * book, open the list, follow the patron.
 *
 * ## One container, three card types
 *
 * Following Goodreads' Updates panel, every activity type renders into the
 * *same* card skeleton rather than getting its own bespoke layout:
 *
 *     avatar   Actor  verb  target                            when   [Follow]
 *              ┌───────┐  Title
 *              │ media │  subtitle
 *              └───────┘  [add to reading log]  [type-specific action]
 *
 * Three types fill it today, in the order they matter:
 *
 * 1. `shelf_change` -- shelved on Want to Read / Currently Reading /
 *    Already Read. Actions: follow, add the book to your own reading log.
 * 2. `rating` -- gave the book stars. Its own card, not a decoration on the
 *    shelving. Same actions.
 * 3. `list_add` -- added the book to one of their lists. The book is the
 *    subject and the list is context, so the actions are the same two plus
 *    hearting the list.
 *
 * Follow is offered on every card. `_present` is the only code that knows how
 * the types differ -- a fourth type is one branch there, not a new template.
 *
 * The `variant` property then selects one of ten CSS treatments over that one
 * skeleton. Because they are the same markup and the same data, switching
 * between them is an honest comparison of presentation. Nine are scaffolding
 * for a design decision and get removed once one is chosen.
 *
 * @element ol-social-feed
 *
 * @prop {String} apiUrl - Endpoint to fetch feed JSON from
 * @prop {Number} variant - Layout treatment, 1-10
 * @prop {Number} limit - Events to request per page
 * @prop {String} scope - `auto`, `public`, `following`, or `popular`
 * @prop {Boolean} balanced - Keep every card type on screen instead of strict newest-first
 * @prop {Boolean} controls - Show the refresh and older/newer controls
 * @prop {Boolean} tabs - Show Discover / Following / Popular tabs that switch scope
 * @prop {Boolean} infinite - Scroll in a fixed-height column, appending pages as you reach the end
 * @prop {String} viewerUsername - Logged-in patron, for follow state and self-filtering
 * @prop {Number} refreshInterval - Seconds between background refreshes; 0 disables
 * @prop {String} heading - Panel heading; omit to render the feed without a panel
 * @prop {String} headingHref - Makes the panel heading a link
 * @fires ol-social-feed-load - Fired after each successful fetch. detail: { count: Number, scope: String }
 */

const COVERS_BASE = 'https://covers.openlibrary.org/b/id';
const FALLBACK_COVER = '/static/images/icons/avatar_book-sm.png';

/** Every layout treatment, in the order the gallery presents them. */
export const FEED_VARIANTS = [
    { id: 1, slug: 'spec-card', name: 'Spec card', blurb: 'The reviewed design: patron and follow above the rule, book and actions below. Three up on desktop.' },
    { id: 2, slug: 'river', name: 'Goodreads river', blurb: 'Full-width rows, one continuous sentence, generous cover, actions beside the book.' },
    { id: 3, slug: 'cover-tiles', name: 'Cover tiles', blurb: 'The cover is the card. Caption strip overlays the bottom. Scrolls horizontally.' },
    { id: 4, slug: 'timeline', name: 'Dense timeline', blurb: 'A rail of small avatars down the left. Maximum events per screen.' },
    { id: 5, slug: 'thread', name: 'Social thread', blurb: 'Bluesky shape: avatar column, prose, and the book as an embedded quote card.' },
    { id: 6, slug: 'magazine', name: 'Magazine', blurb: 'Two-column masonry, big covers, serif titles, lots of air.' },
    { id: 7, slug: 'bubbles', name: 'Conversation', blurb: 'Activity as messages. Reads as live chatter rather than a log.' },
    { id: 8, slug: 'ticker', name: 'Ticker', blurb: 'One compact line each. Sized to sit under a heading as a teaser strip.' },
    { id: 9, slug: 'editorial', name: 'Editorial', blurb: 'Uppercase eyebrow, large type, almost no chrome. Actions on hover.' },
    { id: 10, slug: 'people', name: 'People first', blurb: 'Grouped by patron: who they are, then a strip of what they touched.' },
    { id: 11, slug: 'showcase', name: 'Showcase row', blurb: 'Three cards across on desktop, stacked on mobile. Refresh the whole row; swipe or press next for older activity.' },
    { id: 12, slug: 'tabbed', name: 'Discover / Following / Popular', blurb: 'Bluesky shape: tabs over one scrolling column that loads more as you reach the end. Popular shows one card each from the most-followed readers.' },
];

const VARIANT_BY_ID = new Map(FEED_VARIANTS.map((v) => [v.id, v]));

/** Compact relative time: `3d`, `2h`, `just now`. */
export function timeAgo(iso) {
    if (!iso) return '';
    const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    const units = [
        ['y', 31536000],
        ['mo', 2592000],
        ['w', 604800],
        ['d', 86400],
        ['h', 3600],
        ['m', 60],
    ];
    for (const [suffix, size] of units) {
        if (seconds >= size) return `${Math.floor(seconds / size)}${suffix}`;
    }
    return 'just now';
}

function coverUrl(coverId, size = 'M') {
    return coverId ? `${COVERS_BASE}/${coverId}-${size}.jpg` : FALLBACK_COVER;
}

export class OlSocialFeed extends LitElement {
    static properties = {
        apiUrl: { type: String, attribute: 'api-url' },
        variant: { type: Number, reflect: true },
        limit: { type: Number },
        scope: { type: String },
        balanced: { type: Boolean },
        controls: { type: Boolean },
        tabs: { type: Boolean },
        infinite: { type: Boolean },
        viewerUsername: { type: String, attribute: 'viewer-username' },
        refreshInterval: { type: Number, attribute: 'refresh-interval' },
        heading: { type: String },
        headingHref: { type: String, attribute: 'heading-href' },
        _items: { state: true },
        _loading: { state: true },
        _error: { state: true },
        _following: { state: true },
        _freshKeys: { state: true },
        _hearted: { state: true },
        _page: { state: true },
        _hasMore: { state: true },
        _busy: { state: true },
        _scope: { state: true },
    };

    constructor() {
        super();
        this.apiUrl = '/api/internal/activity/feed.json';
        this.variant = 1;
        this.limit = 12;
        this.scope = 'auto';
        this.balanced = false;
        this.controls = false;
        this.tabs = false;
        this.infinite = false;
        this.viewerUsername = '';
        this.refreshInterval = 60;
        this.heading = '';
        this.headingHref = '';
        this._items = [];
        this._loading = true;
        this._error = false;
        this._following = new Set();
        this._freshKeys = new Set();
        this._hearted = new Set();
        this._page = 1;
        this._hasMore = false;
        this._busy = false;
        this._scope = '';
        this._timer = null;
    }

    connectedCallback() {
        super.connectedCallback();
        // `scope` is the configured default; `_scope` is what the tabs change.
        // With tabs on, `auto` names no tab, so nothing would look selected --
        // start on Discover instead.
        this._scope = this.tabs && this.scope === 'auto' ? 'public' : this.scope;
        this._load();
        this._startTimer();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._stopTimer();
        this._observer?.disconnect();
    }

    updated() {
        this._watchForTheEnd();
    }

    /** Append the next page once the foot of the column comes into view. */
    _watchForTheEnd() {
        if (!this.infinite) return;
        const sentinel = this.renderRoot.querySelector('.sentinel');
        if (!sentinel || sentinel === this._watched) return;
        this._observer?.disconnect();
        this._observer = new IntersectionObserver(
            (entries) => {
                if (entries.some((entry) => entry.isIntersecting)) this._loadMore();
            },
            { root: this.renderRoot.querySelector('.scroller'), rootMargin: '300px' }
        );
        this._observer.observe(sentinel);
        this._watched = sentinel;
    }

    _startTimer() {
        this._stopTimer();
        if (!this.refreshInterval) return;
        this._timer = setInterval(() => this._load({ background: true }), this.refreshInterval * 1000);
    }

    _stopTimer() {
        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }
    }

    /** Stable identity for an event, so a refresh can tell new from seen. */
    _key(item) {
        return `${item.type}:${item.username}:${item.work?.key || item.list?.key}:${item.created}`;
    }

    async _load({ background = false, append = false } = {}) {
        if (!background && !append) this._loading = true;
        const scope = this._scope || this.scope;
        const url = `${this.apiUrl}?limit=${this.limit}&page=${this._page}&scope=${scope}${this.balanced ? '&balanced=true' : ''}`;
        try {
            const response = await fetch(url, { headers: { Accept: 'application/json' } });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            const items = data.activity || [];

            // On a background refresh, mark what the patron has not seen yet so
            // new arrivals can announce themselves instead of silently shuffling.
            if (background) {
                const seen = new Set(this._items.map((item) => this._key(item)));
                this._freshKeys = new Set(items.map((item) => this._key(item)).filter((key) => !seen.has(key)));
            }

            this._items = append ? [...this._items, ...items] : items;
            // A short page means there is nothing older to turn to. Popular is
            // one card per patron, so it is a single page by definition.
            this._hasMore = data.scope !== 'popular' && items.length >= this.limit;
            this._error = false;
            this.dispatchEvent(
                new CustomEvent('ol-social-feed-load', {
                    detail: { count: items.length, scope: data.scope },
                    bubbles: true,
                    composed: true,
                })
            );
        } catch {
            // A failed background refresh keeps whatever is already on screen.
            if (!background) this._error = true;
        } finally {
            this._loading = false;
        }
    }

    /** Reload the current page in place -- the refresh control. */
    async _refresh() {
        this._busy = true;
        await this._load({ background: true });
        this._busy = false;
        this._scope = '';
    }

    /** Pull the next page in beneath what is already on screen. */
    async _loadMore() {
        if (this._busy || !this._hasMore) return;
        this._busy = true;
        this._page += 1;
        await this._load({ append: true });
        this._busy = false;
    }

    /** Switch between Discover and Following, starting over at page one. */
    async _selectScope(scope) {
        if (this._scope === scope || this._busy) return;
        this._scope = scope;
        this._page = 1;
        this._busy = true;
        await this._load();
        this._busy = false;
    }

    _renderTabs() {
        if (!this.tabs) return '';
        const tab = (scope, label) => html`<button
            class="tab ${this._scope === scope ? 'is-current' : ''}"
            type="button"
            role="tab"
            aria-selected=${this._scope === scope}
            @click=${() => this._selectScope(scope)}
        >${label}</button>`;
        return html`<div class="tabs" role="tablist" aria-label="Feed">
            ${tab('public', 'Discover')}${tab('following', 'Following')}${tab('popular', 'Popular')}
        </div>`;
    }

    _renderMore() {
        if (!this.infinite) return '';
        return html`
            <div class="sentinel" aria-hidden="true"></div>
            ${this._hasMore
        ? html`<button class="load-more" type="button" ?disabled=${this._busy}
                    @click=${() => this._loadMore()}>${this._busy ? 'Loading\u2026' : 'Load more'}</button>`
        : html`<p class="end">You are all caught up.</p>`}
        `;
    }

    /** Turn to older or newer activity. */
    async _turnTo(page) {
        if (page < 1 || this._busy) return;
        this._page = page;
        this._busy = true;
        await this._load();
        this._busy = false;
        this._scope = '';
        this._startTimer();
    }

    _onTouchStart(e) {
        this._touchX = e.changedTouches[0].clientX;
    }

    _onTouchEnd(e) {
        if (this._touchX === undefined) return;
        const dx = e.changedTouches[0].clientX - this._touchX;
        this._touchX = undefined;
        // Swiping left pulls the next page in from the right, matching how the
        // arrow beside the row reads.
        if (dx < -60 && this._hasMore) this._turnTo(this._page + 1);
        else if (dx > 60 && this._page > 1) this._turnTo(this._page - 1);
    }

    _renderControls() {
        if (!this.controls) return '';
        return html`<div class="controls">
            <button class="ctl" type="button" ?disabled=${this._busy}
                @click=${() => this._refresh()} aria-label="Refresh activity">
                <span aria-hidden="true">↻</span>
            </button>
            <button class="ctl" type="button" ?disabled=${this._page <= 1 || this._busy}
                @click=${() => this._turnTo(this._page - 1)} aria-label="Newer activity">
                <span aria-hidden="true">‹</span>
            </button>
            <button class="ctl ctl--next" type="button" ?disabled=${!this._hasMore || this._busy}
                @click=${() => this._turnTo(this._page + 1)} aria-label="Older activity">
                <span class="ctl__text">Older</span> <span aria-hidden="true">›</span>
            </button>
        </div>`;
    }

    async _toggleFollow(username) {
        if (!this.viewerUsername) {
            window.location = `/account/login?redir_url=${encodeURIComponent(window.location.pathname)}`;
            return;
        }
        const wasFollowing = this._following.has(username);
        const next = new Set(this._following);
        if (wasFollowing) next.delete(username);
        else next.add(username);
        this._following = next;

        const body = new FormData();
        body.append('publisher', username);
        body.append('state', wasFollowing ? '1' : '0');
        body.append('redir_url', window.location.pathname);

        try {
            const response = await fetch(`/people/${this.viewerUsername}/follows.json`, {
                method: 'POST',
                body,
                redirect: 'manual',
            });
            if (!response.ok && response.type !== 'opaqueredirect') throw new Error('follow failed');
        } catch {
            const reverted = new Set(this._following);
            if (wasFollowing) reverted.add(username);
            else reverted.delete(username);
            this._following = reverted;
        }
    }

    // -- the presenter ----------------------------------------------------

    /**
     * Map one event onto the card's slots.
     *
     * This is the only place that knows how event types differ. Everything
     * downstream sees the same shape, which is what lets one skeleton serve
     * all of them.
     */
    _present(item) {
        const work = item.work;
        // Adding the book to your own reading log is offered on all three
        // card types, because all three are ultimately about a book.
        const actions = [{ kind: 'shelve', label: 'Want to Read', href: work.key }];

        if (item.list) {
            actions.unshift({
                kind: 'heart',
                label: item.list.like_count ? `♥ ${item.list.like_count}` : '♥',
                accessibleLabel: `Heart the list ${item.list.name}`,
                listKey: item.list.key,
            });
        }

        // Card three shows what the book was filed alongside: the added book,
        // accented, with up to two of its new shelf-mates behind it.
        const others = item.list
            ? (item.list.cover_ids || []).filter((id) => id !== work.cover_id).slice(0, 2)
            : [];

        return {
            href: work.key,
            coverId: work.cover_id,
            coverAlt: `Cover of ${work.title}`,
            otherCoverIds: others,
            title: work.title,
            author: work.author,
            authorKey: work.author_key,
            actions,
        };
    }

    async _toggleHeart(listKey) {
        if (!this.viewerUsername) {
            window.location = `/account/login?redir_url=${encodeURIComponent(window.location.pathname)}`;
            return;
        }
        const hearted = this._hearted.has(listKey);
        const next = new Set(this._hearted);
        if (hearted) next.delete(listKey);
        else next.add(listKey);
        this._hearted = next;

        try {
            const response = await fetch('/api/like', {
                method: hearted ? 'DELETE' : 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: listKey, value: 1 }),
            });
            if (!response.ok) throw new Error('heart failed');
        } catch {
            const reverted = new Set(this._hearted);
            if (hearted) reverted.add(listKey);
            else reverted.delete(listKey);
            this._hearted = reverted;
        }
    }

    // -- the one card skeleton --------------------------------------------

    _renderCard(item) {
        const slot = this._present(item);
        const following = this._following.has(item.username);
        const isViewer = item.username === this.viewerUsername;

        return html`<article class="card" data-type=${item.type}>
            <div class="head">
                <a class="gutter" href=${item.patron_url} aria-label=${`${item.username}'s profile`}>
                    <img class="avatar" src=${item.avatar_url} alt="" loading="lazy"
                        @error=${(e) => { e.target.src = FALLBACK_COVER; }} />
                </a>
                <p class="sentence">
                    <a class="handle" href=${item.patron_url}>${item.username}</a>
                    ${item.shelf_url
        ? html`<a class="verb" href=${item.shelf_url}>${item.label}</a>`
        : html`<span class="verb">${item.label}</span>`}
                    ${item.list
        ? html`<a class="target" href=${item.list.key}>${item.list.name}</a>`
        : ''}
                </p>
                <time class="when">${timeAgo(item.created)}</time>
                ${isViewer
        ? ''
        : html`<button
                        class="follow ${following ? 'is-following' : ''}"
                        type="button"
                        aria-pressed=${following}
                        @click=${() => this._toggleFollow(item.username)}
                    >${following ? 'Following' : 'Follow'}</button>`}
            </div>

            <div class="content">
                <a class="cover ${slot.otherCoverIds.length ? 'cover--group' : ''}" href=${slot.href}>
                    ${slot.otherCoverIds.map(
        (id) => html`<img class="cover__mate" src=${coverUrl(id)} alt="" aria-hidden="true" loading="lazy"
                            @error=${(e) => { e.target.src = FALLBACK_COVER; }} />`
    )}
                    <img class="cover__subject" src=${coverUrl(slot.coverId)} alt=${slot.coverAlt} loading="lazy"
                        @error=${(e) => { e.target.src = FALLBACK_COVER; }} />
                </a>
                <div class="body">
                    <a class="title" href=${slot.href}>${slot.title}</a>
                    <span class="byline">
                        ${slot.author
        ? html`by ${slot.authorKey ? html`<a href=${slot.authorKey}>${slot.author}</a>` : slot.author}`
        : 'Unknown author'}
                    </span>
                    ${item.rating
        ? html`<span class="stars" aria-label="Rated ${item.rating} out of 5"
                            >${'★'.repeat(item.rating)}<span class="stars__empty">${'★'.repeat(5 - item.rating)}</span></span>`
        : ''}
                    <div class="actions">
                        ${slot.actions.map((action) => this._renderAction(action))}
                    </div>
                </div>
            </div>
        </article>`;
    }

    _renderAction(action) {
        if (action.kind === 'heart') {
            const hearted = this._hearted.has(action.listKey);
            return html`<button
                class="btn btn--ghost heart ${hearted ? 'is-hearted' : ''}"
                type="button"
                aria-pressed=${hearted}
                aria-label=${action.accessibleLabel}
                @click=${() => this._toggleHeart(action.listKey)}
            >${action.label}</button>`;
        }
        return html`<a class="btn btn--primary" href=${action.href}>${action.label}</a>`;
    }

    /**
     * Variant 10 is the one treatment that regroups the data rather than
     * restyling it -- one card per patron, with a strip of what they touched --
     * so it cannot reuse the per-event skeleton.
     */
    _renderPeople() {
        const groups = new Map();
        for (const item of this._items) {
            if (!groups.has(item.username)) groups.set(item.username, []);
            groups.get(item.username).push(item);
        }
        return html`${[...groups.entries()].map(([username, items]) => {
            const first = items[0];
            const following = this._following.has(username);
            return html`<article class="card card--person">
                <div class="head">
                    <a class="gutter" href=${first.patron_url} aria-label=${`${username}'s profile`}>
                        <img class="avatar" src=${first.avatar_url} alt="" loading="lazy"
                            @error=${(e) => { e.target.src = FALLBACK_COVER; }} />
                    </a>
                    <p class="sentence"><a class="handle" href=${first.patron_url}>${username}</a></p>
                    <time class="when">${timeAgo(first.created)}</time>
                    ${username === this.viewerUsername
        ? ''
        : html`<button class="follow ${following ? 'is-following' : ''}" type="button"
                            aria-pressed=${following} @click=${() => this._toggleFollow(username)}
                        >${following ? 'Following' : 'Follow'}</button>`}
                </div>
                <p class="summary">
                    ${items.length} recent ${items.length === 1 ? 'update' : 'updates'}
                </p>
                <div class="strip">
                    ${items.map((item) => {
        const slot = this._present(item);
        return html`<figure class="strip__item">
                            <a class="cover" href=${slot.href}>
                                <img src=${coverUrl(slot.coverId)} alt=${slot.coverAlt} loading="lazy"
                                    @error=${(e) => { e.target.src = FALLBACK_COVER; }} />
                            </a>
                            <figcaption>${item.label}</figcaption>
                        </figure>`;
    })}
                </div>
            </article>`;
        })}`;
    }

    render() {
        const variant = VARIANT_BY_ID.get(this.variant) || FEED_VARIANTS[0];

        let inner;
        if (this._loading) {
            inner = html`${this._renderTabs()}<div class="state" aria-busy="true">Loading activity&hellip;</div>`;
        } else if (this._error) {
            inner = html`<div class="state">
                Could not load the activity feed.
                <button class="btn btn--ghost" type="button" @click=${() => this._load()}>Retry</button>
            </div>`;
        } else if (!this._items.length) {
            inner = html`${this._renderTabs()}<div class="state">
                ${{
        following: 'Nobody you follow has been active lately. Try Discover.',
        popular: 'No activity yet from the most-followed readers.',
    }[this._scope] || 'No recent activity yet. Follow other readers and their updates will show up here.'}
            </div>`;
        } else {
            inner = html`${this._renderTabs()}
            <div class="${this.infinite ? 'scroller' : ''}">
            <div class="feed feed--${variant.slug}" aria-live="polite" aria-busy=${this._busy}
                @touchstart=${(e) => this._onTouchStart(e)} @touchend=${(e) => this._onTouchEnd(e)}>
                ${this.variant === 10
        ? this._renderPeople()
        : this._items.map(
            (item) => html`<div class="slot ${this._freshKeys.has(this._key(item)) ? 'is-fresh' : ''}">
                            ${this._renderCard(item)}
                        </div>`
        )}
            </div>
            ${this._renderMore()}
            </div>
            ${this._renderControls()}`;
        }

        // The panel is the outer common container: one frame around every
        // activity type, the way Goodreads wraps its Updates column.
        if (!this.heading) return inner;
        return html`<section class="panel">
            <header class="panel__head">
                <h2>${this.headingHref
        ? html`<a href=${this.headingHref}>${this.heading}</a>`
        : this.heading}</h2>
                <slot name="panel-action"></slot>
            </header>
            ${inner}
        </section>`;
    }

    static styles = css`
        :host {
            display: block;
            font-family: inherit;
            color: var(--grey-464646, #464646);

            --feed-card-bg: var(--white, #fff);
            --feed-rule: var(--grey-e7e7e7, #e7e7e7);
            --feed-muted: var(--grey, #666);
            --feed-shadow: 2px 2px 4px hsla(0, 0%, 0%, 0.1);
            --feed-gutter: 40px;
        }

        /* -- outer panel -- */

        .panel {
            border: var(--border-width-thin, 1px) solid var(--feed-rule);
            border-radius: var(--border-radius-card, 9px);
            background: var(--grey-fafafa, #fafafa);
            padding: 14px 16px 16px;
        }
        .panel__head {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: 12px;
            margin-bottom: 12px;
        }
        .panel__head h2 {
            margin: 0;
            font-size: 0.95rem;
            letter-spacing: 0.06em;
            text-transform: uppercase;
        }
        .panel__head a { text-decoration: none; }
        .panel__head a:hover { text-decoration: underline; }

        .state {
            padding: 24px;
            text-align: center;
            color: var(--feed-muted);
        }

        /* A background refresh brings in new events; they fade rather than pop. */
        .slot.is-fresh { animation: settle 900ms ease-out; }

        @keyframes settle {
            from { opacity: 0; transform: translateY(-6px); }
            to { opacity: 1; transform: none; }
        }

        @media (prefers-reduced-motion: reduce) {
            .slot.is-fresh { animation: none; }
        }

        /* -- the one card skeleton --
           Every event type renders this exact markup. Variants below restyle
           it; none of them add or remove elements. */

        a { color: inherit; }

        .card {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .head {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .gutter { display: flex; flex-shrink: 0; }

        .avatar {
            width: 32px;
            height: 32px;
            border-radius: var(--border-radius-avatar, 50%);
            object-fit: cover;
            background: var(--grey-f3f3f3, #f3f3f3);
        }

        .sentence {
            margin: 0;
            min-width: 0;
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            align-items: baseline;
            font-size: 0.88rem;
        }

        .handle {
            font-weight: 600;
            text-decoration: none;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .handle:hover { text-decoration: underline; }

        .verb { color: var(--link-blue, #04618f); text-decoration: none; }
        a.verb:hover { text-decoration: underline; }

        .target {
            font-weight: 600;
            text-decoration: none;
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .target:hover { text-decoration: underline; }

        .when {
            color: var(--feed-muted);
            font-size: 0.8rem;
            margin-left: auto;
            white-space: nowrap;
        }

        .follow {
            border: var(--border-width-thin, 1px) solid var(--primary-blue, #0577b5);
            background: var(--primary-blue, #0577b5);
            color: var(--white, #fff);
            border-radius: var(--border-radius-pill, 9999px);
            padding: 4px 14px;
            font: inherit;
            font-size: 0.78rem;
            font-weight: 600;
            cursor: pointer;
            flex-shrink: 0;
        }
        .follow:hover { background: var(--link-blue, #04618f); }
        .follow.is-following {
            background: transparent;
            color: var(--primary-blue, #0577b5);
        }

        /* Indented to sit under the sentence, not under the avatar. */
        .content {
            display: flex;
            gap: 12px;
            min-width: 0;
        }

        .cover {
            display: flex;
            flex-shrink: 0;
            width: 62px;
            height: 90px;
        }
        .cover img {
            display: block;
            width: 100%;
            height: 100%;
            object-fit: cover;
            border-radius: var(--border-radius-thumbnail, 6px);
            box-shadow: var(--feed-shadow);
            background: var(--grey-f3f3f3, #f3f3f3);
        }


        /* Card three: the added book sits proud of the list-mates it joined.
           The mates are blurred and dimmed so they read as context, not as
           three equal covers. */
        .cover--group { position: relative; width: 96px; }
        .cover--group .cover__mate {
            position: absolute;
            top: 8px;
            width: 46px;
            height: 68px;
            filter: blur(1.5px);
            opacity: 0.55;
            border-radius: var(--border-radius-thumbnail, 6px);
        }
        .cover--group .cover__mate:nth-of-type(1) { right: 0; transform: rotate(4deg); }
        .cover--group .cover__mate:nth-of-type(2) { right: 18px; transform: rotate(-3deg); }
        .cover--group .cover__subject {
            position: relative;
            z-index: 1;
            width: 62px;
            outline: var(--border-width-thick, 2px) solid var(--primary-blue, #0577b5);
            outline-offset: 1px;
        }

        .body {
            min-width: 0;
            display: flex;
            flex-direction: column;
            gap: 3px;
        }

        .title {
            font-weight: 700;
            line-height: 1.25;
            text-decoration: none;
            font-size: 0.95rem;
        }
        .title:hover { text-decoration: underline; }

        .byline { font-size: 0.82rem; color: var(--feed-muted); }
        .byline a { text-decoration: none; }
        .byline a:hover { text-decoration: underline; }

        .stars { color: var(--orange, #e8a33d); white-space: nowrap; font-size: 0.85rem; }
        .stars__empty { color: var(--grey-e7e7e7, #ddd); }

        .actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }

        .btn {
            display: inline-block;
            text-align: center;
            text-decoration: none;
            border-radius: var(--border-radius-button, 6px);
            padding: 7px 12px;
            font-size: 0.85rem;
            font-weight: 600;
            border: var(--border-width-thin, 1px) solid transparent;
            cursor: pointer;
        }
        .btn--primary {
            background: var(--primary-blue, #0577b5);
            color: var(--white, #fff);
        }
        .btn--primary:hover { background: var(--link-blue, #04618f); }
        .btn--ghost {
            background: transparent;
            border-color: var(--feed-rule);
            color: inherit;
        }

        .heart { font: inherit; font-size: 0.85rem; font-weight: 600; }
        .heart.is-hearted {
            color: var(--red, #c0392b);
            border-color: currentColor;
        }

        :focus-visible {
            outline: var(--border-width-thick, 2px) solid var(--primary-blue, #0577b5);
            outline-offset: 2px;
        }

        /* == 1. Spec card ================================================= */

        .feed--spec-card {
            display: grid;
            gap: 16px;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
        }
        .feed--spec-card .card {
            background: var(--feed-card-bg);
            border: var(--border-width-thin, 1px) solid var(--feed-rule);
            border-radius: var(--border-radius-card, 9px);
            box-shadow: var(--feed-shadow);
            padding: 12px 14px 14px;
            height: 100%;
        }
        /* Per the June review: avatar, follow and the action all sit above the
           separator, and the separator sits above the book. */
        .feed--spec-card .head {
            display: grid;
            grid-template-columns: auto 1fr auto;
            grid-template-areas:
                "gutter . follow"
                "sentence sentence when";
            row-gap: 6px;
        }
        .feed--spec-card .gutter { grid-area: gutter; }
        .feed--spec-card .follow { grid-area: follow; }
        .feed--spec-card .sentence { grid-area: sentence; }
        .feed--spec-card .when { grid-area: when; margin-left: 0; align-self: baseline; }
        .feed--spec-card .content {
            flex: 1;
            border-top: 1px solid var(--feed-rule);
            padding-top: 10px;
        }
        .feed--spec-card .actions { flex-direction: column; margin-top: auto; }
        .feed--spec-card .actions .btn { width: 100%; box-sizing: border-box; }

        /* == 2. Goodreads river =========================================== */

        .feed--river { display: flex; flex-direction: column; }
        .feed--river .card {
            border-bottom: 1px solid var(--feed-rule);
            padding: 20px 4px;
        }
        .feed--river .content { padding-left: calc(var(--feed-gutter) + 8px); }
        .feed--river .cover { width: 110px; height: 165px; }
        .feed--river .title { font-size: 1.15rem; }
        .feed--river .avatar { width: var(--feed-gutter); height: var(--feed-gutter); }

        /* == 3. Cover tiles =============================================== */

        .feed--cover-tiles {
            display: grid;
            grid-auto-flow: column;
            grid-auto-columns: 190px;
            gap: 14px;
            overflow-x: auto;
            padding-bottom: 10px;
            scroll-snap-type: x mandatory;
        }
        .feed--cover-tiles .slot { scroll-snap-align: start; }
        .feed--cover-tiles .card {
            position: relative;
            border-radius: var(--border-radius-card, 9px);
            overflow: hidden;
            box-shadow: var(--feed-shadow);
            background: var(--grey-f3f3f3, #f3f3f3);
            height: 280px;
            gap: 0;
        }
        .feed--cover-tiles .head {
            position: absolute;
            inset: auto 0 0 0;
            z-index: 1;
            padding: 10px;
            color: var(--white, #fff);
            background: linear-gradient(to top, hsla(0, 0%, 0%, 0.85), hsla(0, 0%, 0%, 0));
        }
        .feed--cover-tiles .verb, .feed--cover-tiles .when { color: hsla(0, 0%, 100%, 0.85); }
        .feed--cover-tiles .avatar { width: 22px; height: 22px; }
        .feed--cover-tiles .follow { display: none; }
        .feed--cover-tiles .content { height: 100%; }
        .feed--cover-tiles .cover { width: 100%; height: 100%; }
        .feed--cover-tiles .cover img { border-radius: 0; box-shadow: none; }
        .feed--cover-tiles .body { display: none; }

        /* == 4. Dense timeline ============================================ */
        /* display:contents flattens the wrapper so head and content lay out
           as one row without changing the markup. */

        .feed--timeline { display: flex; flex-direction: column; }
        .feed--timeline .card {
            flex-direction: row;
            align-items: center;
            gap: 10px;
            padding: 8px 4px;
            border-bottom: 1px solid var(--feed-rule);
            position: relative;
            padding-right: 56px;
        }
        .feed--timeline .head { flex: 0 1 auto; min-width: 0; }
        .feed--timeline .content { display: contents; }
        .feed--timeline .when {
            position: absolute;
            right: 4px;
            top: 50%;
            transform: translateY(-50%);
            margin-left: 0;
        }
        .feed--timeline .body { flex: 1; }
        .feed--timeline .avatar { width: 22px; height: 22px; }
        .feed--timeline .cover { width: 32px; height: 46px; }
        .feed--timeline .body { flex-direction: row; align-items: baseline; gap: 6px; min-width: 0; }
        .feed--timeline .title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .feed--timeline .byline, .feed--timeline .actions, .feed--timeline .follow { display: none; }
        .feed--timeline .title { font-size: 0.88rem; }

        /* == 5. Social thread ============================================= */

        .feed--thread { display: flex; flex-direction: column; }
        .feed--thread .card {
            padding: 16px 4px;
            border-bottom: 1px solid var(--feed-rule);
        }
        .feed--thread .content {
            margin-left: calc(var(--feed-gutter) + 8px);
            border: 1px solid var(--feed-rule);
            border-radius: var(--border-radius-card, 9px);
            padding: 10px;
        }
        .feed--thread .avatar { width: var(--feed-gutter); height: var(--feed-gutter); }
        .feed--thread .cover { width: 46px; height: 68px; }
        .feed--thread .title { font-size: 0.92rem; }

        /* == 6. Magazine ================================================== */

        .feed--magazine {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 32px;
        }
        .feed--magazine .card { gap: 14px; }
        .feed--magazine .head { order: 2; }
        .feed--magazine .content { order: 1; flex-direction: column; }
        .feed--magazine .cover { width: 100%; height: 260px; }
        .feed--magazine .cover img { object-fit: contain; }
        .feed--magazine .title {
            font-family: var(--font-family-serif, Georgia, serif);
            font-size: 1.4rem;
            line-height: 1.15;
        }

        /* == 7. Conversation ============================================== */

        .feed--bubbles { display: flex; flex-direction: column; gap: 14px; }
        .feed--bubbles .card {
            background: var(--grey-f3f3f3, #f3f3f3);
            border-radius: var(--border-radius-xl, 12px);
            padding: 12px 14px 12px 40px;
            position: relative;
        }
        /* Pull the avatar out of the bubble rather than restructuring the card. */
        .feed--bubbles .gutter { position: absolute; left: -6px; top: 10px; }
        .feed--bubbles .content {
            background: var(--white, #fff);
            border-radius: var(--border-radius-md, 6px);
            padding: 8px;
        }
        .feed--bubbles .cover { width: 34px; height: 50px; }
        .feed--bubbles .title { font-size: 0.9rem; }
        .feed--bubbles .actions { display: none; }

        /* == 8. Ticker ==================================================== */

        .feed--ticker { display: flex; flex-direction: column; }
        .feed--ticker .card {
            flex-direction: row;
            align-items: center;
            gap: 10px;
            padding: 6px 8px;
            border-radius: var(--border-radius-md, 6px);
            position: relative;
            padding-right: 52px;
        }
        .feed--ticker .slot:nth-child(odd) .card { background: var(--grey-fafafa, #fafafa); }
        .feed--ticker .head { flex: 0 1 auto; min-width: 0; }
        .feed--ticker .content { display: contents; }
        .feed--ticker .when {
            position: absolute;
            right: 8px;
            top: 50%;
            transform: translateY(-50%);
            margin-left: 0;
        }
        .feed--ticker .body { flex: 1; }
        .feed--ticker .avatar { width: 20px; height: 20px; }
        .feed--ticker .cover { width: 26px; height: 38px; }
        .feed--ticker .body { flex-direction: row; align-items: baseline; gap: 6px; min-width: 0; }
        .feed--ticker .title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .feed--ticker .byline,
        .feed--ticker .actions,
        .feed--ticker .follow,
        .feed--ticker .stars { display: none; }
        .feed--ticker .title { font-size: 0.85rem; }

        /* == 9. Editorial ================================================= */

        .feed--editorial { display: flex; flex-direction: column; }
        .feed--editorial .card {
            padding: 22px 4px;
            border-bottom: 1px solid var(--feed-rule);
            position: relative;
        }
        .feed--editorial .head { order: 2; font-size: 0.8rem; }
        .feed--editorial .content { order: 1; }
        .feed--editorial .avatar { width: 22px; height: 22px; }
        .feed--editorial .verb {
            letter-spacing: 0.12em;
            text-transform: uppercase;
            font-size: 0.7rem;
            color: var(--feed-muted);
        }
        .feed--editorial .cover { width: 70px; height: 104px; }
        .feed--editorial .title { font-size: 1.5rem; line-height: 1.1; }
        .feed--editorial .actions {
            opacity: 0;
            transition: opacity 150ms;
        }
        .feed--editorial .card:hover .actions,
        .feed--editorial .card:focus-within .actions { opacity: 1; }
        /* Touch has no hover, so the actions must simply be present. */
        @media (hover: none) {
            .feed--editorial .actions { opacity: 1; }
            .feed--timeline .card { padding-right: 40px; gap: 6px; }
            .feed--timeline .cover { width: 26px; height: 38px; }
            .feed--ticker .card { padding-right: 38px; gap: 6px; }
            .feed--tabbed .content { padding-left: 0; }
            .scroller { max-height: 65vh; }

            /* Same cards, stacked. Refresh stays reachable at the top, and
               paging moves to a full-width control at the foot of the list. */
            .feed--showcase { grid-template-columns: 1fr; }
            .feed--showcase .card { height: auto; }
            .feed--showcase .content { flex: 0 1 auto; }
            .controls { justify-content: stretch; }
            .ctl--next { flex: 1; justify-content: center; }
        }

        /* == 10. People first ============================================= */

        .feed--people { display: flex; flex-direction: column; gap: 20px; }
        .feed--people .card {
            border: 1px solid var(--feed-rule);
            border-radius: var(--border-radius-card, 9px);
            padding: 14px;
            background: var(--feed-card-bg);
        }
        .feed--people .avatar { width: 44px; height: 44px; }
        .feed--people .summary { margin: 0; font-size: 0.8rem; color: var(--feed-muted); }
        .feed--people .strip {
            display: flex;
            gap: 12px;
            overflow-x: auto;
            padding-bottom: 6px;
        }
        .feed--people .strip__item { margin: 0; width: 78px; flex-shrink: 0; }
        .feed--people .cover { width: 78px; height: 116px; }
        .feed--people figcaption {
            font-size: 0.7rem;
            color: var(--feed-muted);
            margin-top: 4px;
            line-height: 1.2;
        }

        /* == 11. Showcase row ============================================= */
        /* Three across on desktop, the same cards stacked on mobile. Paging
           rather than infinite scroll, so the row always holds three. */

        .feed--showcase {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 16px;
            align-items: stretch;
        }
        .feed--showcase .card {
            background: var(--feed-card-bg);
            border: var(--border-width-thin, 1px) solid var(--feed-rule);
            border-radius: var(--border-radius-card, 9px);
            box-shadow: var(--feed-shadow);
            padding: 12px 14px 14px;
            height: 100%;
        }
        .feed--showcase .head {
            display: grid;
            grid-template-columns: auto 1fr auto;
            grid-template-areas:
                "gutter . follow"
                "sentence sentence when";
            row-gap: 6px;
        }
        .feed--showcase .gutter { grid-area: gutter; }
        .feed--showcase .follow { grid-area: follow; }
        .feed--showcase .sentence { grid-area: sentence; }
        .feed--showcase .when { grid-area: when; margin-left: 0; align-self: baseline; }
        .feed--showcase .content {
            flex: 1;
            border-top: 1px solid var(--feed-rule);
            padding-top: 10px;
        }
        .feed--showcase .actions { margin-top: auto; }

        .controls {
            display: flex;
            justify-content: flex-end;
            align-items: center;
            gap: 8px;
            margin-top: 12px;
        }
        .ctl {
            font: inherit;
            font-size: 0.85rem;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            min-height: 36px;
            padding: 0 12px;
            border: var(--border-width-thin, 1px) solid var(--feed-rule);
            border-radius: var(--border-radius-pill, 9999px);
            background: var(--feed-card-bg);
            color: inherit;
            cursor: pointer;
        }
        .ctl:hover:not(:disabled) { border-color: var(--primary-blue, #0577b5); color: var(--primary-blue, #0577b5); }
        .ctl:disabled { opacity: 0.4; cursor: default; }

        /* == 12. Discover / Following ===================================== */
        /* One scrolling column under two tabs, appending as you reach the end. */

        .tabs {
            display: flex;
            border-bottom: var(--border-width-thin, 1px) solid var(--feed-rule);
            margin-bottom: 4px;
        }
        .tab {
            font: inherit;
            font-size: 0.92rem;
            font-weight: 600;
            flex: 1;
            padding: 12px 8px;
            background: none;
            border: 0;
            border-bottom: var(--border-width-heavy, 3px) solid transparent;
            color: var(--feed-muted);
            cursor: pointer;
        }
        .tab:hover { color: inherit; }
        .tab.is-current {
            color: inherit;
            border-bottom-color: var(--primary-blue, #0577b5);
        }

        .scroller {
            max-height: 70vh;
            overflow-y: auto;
            overscroll-behavior: contain;
        }

        .sentinel { height: 1px; }

        .load-more {
            font: inherit;
            font-size: 0.88rem;
            font-weight: 600;
            display: block;
            width: 100%;
            padding: 14px;
            margin-top: 4px;
            background: none;
            border: 0;
            border-top: 1px solid var(--feed-rule);
            color: var(--primary-blue, #0577b5);
            cursor: pointer;
        }
        .load-more:hover:not(:disabled) { background: var(--grey-fafafa, #fafafa); }
        .load-more:disabled { color: var(--feed-muted); cursor: default; }

        .end {
            margin: 0;
            padding: 18px;
            text-align: center;
            color: var(--feed-muted);
            font-size: 0.85rem;
            border-top: 1px solid var(--feed-rule);
        }

        .feed--tabbed { display: flex; flex-direction: column; }
        .feed--tabbed .card {
            padding: 16px 4px;
            border-bottom: 1px solid var(--feed-rule);
        }
        .feed--tabbed .content { padding-left: calc(var(--feed-gutter) + 8px); }
        .feed--tabbed .avatar { width: var(--feed-gutter); height: var(--feed-gutter); }
        .feed--tabbed .cover { width: 62px; height: 92px; }
        .feed--tabbed .cover--group { width: 96px; }
        .feed--tabbed .title { font-size: 1rem; }

        /* -- mobile ------------------------------------------------------- */

        @media (max-width: 767px) {
            .feed--spec-card { grid-template-columns: 1fr; }
            /* One card per row means nothing needs to stretch to a shared
               height, and stretching just opens a gap above the actions. */
            .feed--spec-card .card { height: auto; }
            .feed--spec-card .content { flex: 0 1 auto; }
            .feed--river .content { padding-left: 0; }
            .feed--river .cover { width: 80px; height: 120px; }
            .feed--river .title { font-size: 1rem; }
            .feed--magazine { grid-template-columns: 1fr; gap: 24px; }
            .feed--magazine .cover { height: 200px; }
            .feed--magazine .title { font-size: 1.2rem; }
            .feed--thread .content { margin-left: 0; }
            .feed--editorial .title { font-size: 1.1rem; }
            .feed--editorial .cover { width: 54px; height: 80px; }
            /* Absolutely positioned, the action tray is wider than a phone-width
               card and pushes the page sideways. Do not rely on the hover:none
               query alone -- device emulation does not always report it. */
            .feed--editorial .actions { opacity: 1; }
            .feed--timeline .card { padding-right: 40px; gap: 6px; }
            .feed--timeline .cover { width: 26px; height: 38px; }
            .feed--ticker .card { padding-right: 38px; gap: 6px; }
            .feed--tabbed .content { padding-left: 0; }
            .scroller { max-height: 65vh; }

            /* Same cards, stacked. Refresh stays reachable at the top, and
               paging moves to a full-width control at the foot of the list. */
            .feed--showcase { grid-template-columns: 1fr; }
            .feed--showcase .card { height: auto; }
            .feed--showcase .content { flex: 0 1 auto; }
            .controls { justify-content: stretch; }
            .ctl--next { flex: 1; justify-content: center; }
        }
    `;
}

customElements.define('ol-social-feed', OlSocialFeed);
