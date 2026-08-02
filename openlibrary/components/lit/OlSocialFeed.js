import { LitElement, css, html } from 'lit';

/**
 * OlSocialFeed -- the social activity feed for My Books.
 *
 * Renders a stream of what other patrons are doing with books: shelving them,
 * rating them, gathering them into lists. Every event carries the actions a
 * reader would want next -- borrow or shelve the book, follow the patron.
 *
 * The `variant` property selects one of ten layout treatments. They are all
 * driven off the same feed response and the same card content, so switching
 * between them is an honest comparison of presentation rather than of data.
 * Nine of them are scaffolding for a design decision and will be removed once
 * one is chosen.
 *
 * @element ol-social-feed
 *
 * @prop {String} apiUrl - Endpoint to fetch feed JSON from
 * @prop {Number} variant - Layout treatment, 1-10
 * @prop {Number} limit - Events to request per page
 * @prop {String} scope - `auto`, `public`, or `following`
 * @prop {String} viewerUsername - Logged-in patron, for follow state and self-filtering
 * @prop {Number} refreshInterval - Seconds between background refreshes; 0 disables
 * @prop {String} heading - Optional heading rendered above the feed
 * @fires ol-social-feed-load - Fired after each successful fetch. detail: { count: Number, scope: String }
 */

const COVERS_BASE = 'https://covers.openlibrary.org/b/id';
const FALLBACK_COVER = '/static/images/icons/avatar_book-sm.png';

/** Every layout treatment, in the order the gallery presents them. */
export const FEED_VARIANTS = [
    { id: 1, slug: 'spec-card', name: 'Spec card', blurb: 'The reviewed design: patron and follow above the rule, book and actions below. Three up on desktop.' },
    { id: 2, slug: 'river', name: 'Goodreads river', blurb: 'Full-width rows, one continuous sentence, generous cover, text actions.' },
    { id: 3, slug: 'cover-tiles', name: 'Cover tiles', blurb: 'The cover is the card. Caption strip overlays the bottom. Scrolls horizontally.' },
    { id: 4, slug: 'timeline', name: 'Dense timeline', blurb: 'A rail of small avatars down the left. Maximum events per screen.' },
    { id: 5, slug: 'thread', name: 'Social thread', blurb: 'Bluesky shape: avatar column, prose, and the book as an embedded quote card.' },
    { id: 6, slug: 'magazine', name: 'Magazine', blurb: 'Two-column masonry, big covers, serif titles, lots of air.' },
    { id: 7, slug: 'bubbles', name: 'Conversation', blurb: 'Activity as messages. Reads as live chatter rather than a log.' },
    { id: 8, slug: 'ticker', name: 'Ticker', blurb: 'One compact line each. Sized to sit under a heading as a teaser strip.' },
    { id: 9, slug: 'editorial', name: 'Editorial', blurb: 'Uppercase eyebrow, large type, almost no chrome. Actions on hover.' },
    { id: 10, slug: 'people', name: 'People first', blurb: 'Grouped by patron: who they are, then a strip of what they touched.' },
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

/**
 * The action most worth offering for a book, given how it can be read.
 * A borrowable book leads with Borrow; everything else leads with the shelf.
 */
function primaryAction(item) {
    const work = item.work;
    if (!work) return null;
    if (work.ebook_access === 'borrowable' || work.ebook_access === 'public') {
        return { label: 'Borrow', href: work.key };
    }
    return { label: 'Want to Read', href: work.key };
}

export class OlSocialFeed extends LitElement {
    static properties = {
        apiUrl: { type: String, attribute: 'api-url' },
        variant: { type: Number, reflect: true },
        limit: { type: Number },
        scope: { type: String },
        viewerUsername: { type: String, attribute: 'viewer-username' },
        refreshInterval: { type: Number, attribute: 'refresh-interval' },
        heading: { type: String },
        _items: { state: true },
        _loading: { state: true },
        _error: { state: true },
        _following: { state: true },
        _freshKeys: { state: true },
    };

    constructor() {
        super();
        this.apiUrl = '/api/internal/activity/feed.json';
        this.variant = 1;
        this.limit = 12;
        this.scope = 'auto';
        this.viewerUsername = '';
        this.refreshInterval = 60;
        this.heading = '';
        this._items = [];
        this._loading = true;
        this._error = false;
        this._following = new Set();
        this._freshKeys = new Set();
        this._timer = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._load();
        this._startTimer();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._stopTimer();
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

    async _load({ background = false } = {}) {
        if (!background) this._loading = true;
        const url = `${this.apiUrl}?limit=${this.limit}&scope=${this.scope}`;
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

            this._items = items;
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

    // -- shared card pieces ----------------------------------------------
    // Every variant composes these, so the same information is on offer in all
    // ten and the comparison is about presentation only.

    _avatar(item, size = 'md') {
        return html`<img
            class="avatar avatar--${size}"
            src=${item.avatar_url}
            alt=""
            loading="lazy"
            @error=${(e) => { e.target.src = FALLBACK_COVER; }}
        />`;
    }

    _followButton(item) {
        if (item.username === this.viewerUsername) return '';
        const following = this._following.has(item.username);
        return html`<button
            class="follow ${following ? 'is-following' : ''}"
            type="button"
            aria-pressed=${following}
            @click=${() => this._toggleFollow(item.username)}
        >${following ? 'Following' : 'Follow'}</button>`;
    }

    _stars(rating) {
        if (!rating) return '';
        return html`<span class="stars" aria-label="Rated ${rating} out of 5">
            ${'★'.repeat(rating)}<span class="stars__empty">${'★'.repeat(5 - rating)}</span>
        </span>`;
    }

    /** "added to Want to Read", with the shelf linked when there is one. */
    _action(item) {
        if (item.shelf_url) {
            return html`<a class="action-link" href=${item.shelf_url}>${item.label}</a>`;
        }
        return html`<span class="action-link">${item.label}</span>`;
    }

    _cover(item, size = 'M') {
        if (item.list) return this._listCovers(item);
        const work = item.work;
        return html`<a class="cover" href=${work.key}>
            <img
                src=${coverUrl(work.cover_id, size)}
                alt="Cover of ${work.title}"
                loading="lazy"
                @error=${(e) => { e.target.src = FALLBACK_COVER; }}
            />
        </a>`;
    }

    /** Three covers fanned out horizontally, per the reviewed list-card design. */
    _listCovers(item) {
        const ids = item.list.cover_ids.length ? item.list.cover_ids : [null];
        return html`<a class="cover cover--stack" href=${item.list.key} aria-label=${item.list.name}>
            ${ids.slice(0, 3).map(
        (id) => html`<img src=${coverUrl(id, 'M')} alt="" loading="lazy"
                    @error=${(e) => { e.target.src = FALLBACK_COVER; }} />`
    )}
        </a>`;
    }

    _title(item) {
        if (item.list) {
            return html`<a class="title" href=${item.list.key}>${item.list.name}</a>`;
        }
        return html`<a class="title" href=${item.work.key}>${item.work.title}</a>`;
    }

    _byline(item) {
        if (item.list) {
            return html`<span class="byline">${item.list.book_count} books</span>`;
        }
        const { author, author_key: authorKey } = item.work;
        if (!author) return html`<span class="byline">Unknown author</span>`;
        return html`<span class="byline">by ${authorKey ? html`<a href=${authorKey}>${author}</a>` : author}</span>`;
    }

    _actions(item) {
        if (item.list) {
            return html`<a class="btn btn--primary" href=${item.list.key}>View List</a>`;
        }
        const action = primaryAction(item);
        return html`
            <a class="btn btn--primary" href=${action.href}>${action.label}</a>
            ${action.label === 'Borrow' ? html`<a class="btn btn--ghost" href=${item.work.key}>Want to Read</a>` : ''}
        `;
    }

    // -- variants ---------------------------------------------------------

    /** 1 -- the reviewed design: patron and follow above the rule, book below. */
    _renderSpecCard(item) {
        return html`<article class="card">
            <header class="card__head">
                <a class="patron" href=${item.patron_url}>${this._avatar(item)}<span class="handle">@${item.username}</span></a>
                ${this._followButton(item)}
            </header>
            <p class="card__action">${this._action(item)} <span class="dot">&middot;</span> ${timeAgo(item.created)}</p>
            <hr class="rule" />
            <div class="card__body">
                ${this._cover(item)}
                <div class="meta">
                    ${this._title(item)}
                    ${this._byline(item)}
                    ${this._stars(item.rating)}
                </div>
            </div>
            <footer class="card__actions">${this._actions(item)}</footer>
        </article>`;
    }

    /** 2 -- Goodreads' shape: one sentence, one big cover, text actions. */
    _renderRiver(item) {
        return html`<article class="card">
            <header class="card__head">
                <a class="patron" href=${item.patron_url} aria-label=${`${item.username}'s profile`}>${this._avatar(item, 'lg')}</a>
                <p class="sentence">
                    <a class="handle" href=${item.patron_url}>${item.username}</a>
                    ${this._action(item)}
                    ${this._stars(item.rating)}
                </p>
                <time class="when">${timeAgo(item.created)}</time>
            </header>
            <div class="card__body">
                ${this._cover(item, 'L')}
                <div class="meta">
                    ${this._title(item)}
                    ${this._byline(item)}
                    <div class="textactions">
                        ${this._actions(item)}
                        ${this._followButton(item)}
                    </div>
                </div>
            </div>
        </article>`;
    }

    /** 3 -- the cover is the card; the caption sits over its foot. */
    _renderCoverTile(item) {
        return html`<article class="card">
            ${this._cover(item, 'L')}
            <div class="caption">
                <a class="patron" href=${item.patron_url}>${this._avatar(item, 'sm')}<span class="handle">${item.username}</span></a>
                <span class="what">${item.label} &middot; ${timeAgo(item.created)}</span>
            </div>
        </article>`;
    }

    /** 4 -- maximum events per screen, on a rail. */
    _renderTimeline(item) {
        return html`<article class="card">
            <a class="rail" href=${item.patron_url} aria-label=${`${item.username}'s profile`}>${this._avatar(item, 'sm')}</a>
            <div class="line">
                <p class="sentence">
                    <a class="handle" href=${item.patron_url}>${item.username}</a>
                    ${this._action(item)}
                    ${this._title(item)}
                    ${this._stars(item.rating)}
                    <time class="when">${timeAgo(item.created)}</time>
                </p>
            </div>
            ${this._cover(item, 'S')}
        </article>`;
    }

    /** 5 -- Bluesky's shape: prose, with the book as an embedded quote card. */
    _renderThread(item) {
        return html`<article class="card">
            <a class="gutter" href=${item.patron_url} aria-label=${`${item.username}'s profile`}>${this._avatar(item)}</a>
            <div class="stream">
                <p class="sentence">
                    <a class="handle" href=${item.patron_url}>@${item.username}</a>
                    <span class="dot">&middot;</span>
                    <time class="when">${timeAgo(item.created)}</time>
                    ${this._followButton(item)}
                </p>
                <p class="what">${this._action(item)} ${this._stars(item.rating)}</p>
                <div class="quote">
                    ${this._cover(item, 'S')}
                    <div class="meta">
                        ${this._title(item)}
                        ${this._byline(item)}
                    </div>
                </div>
                <div class="tray">${this._actions(item)}</div>
            </div>
        </article>`;
    }

    /** 6 -- covers given room to breathe, in two columns. */
    _renderMagazine(item) {
        return html`<article class="card">
            ${this._cover(item, 'L')}
            <div class="meta">
                <p class="eyebrow">
                    <a class="handle" href=${item.patron_url}>${item.username}</a> ${item.label}
                </p>
                ${this._title(item)}
                ${this._byline(item)}
                ${this._stars(item.rating)}
                <footer class="card__actions">${this._actions(item)}</footer>
            </div>
        </article>`;
    }

    /** 7 -- activity as chatter rather than a log. */
    _renderBubble(item) {
        return html`<article class="card">
            <a class="gutter" href=${item.patron_url} aria-label=${`${item.username}'s profile`}>${this._avatar(item)}</a>
            <div class="bubble">
                <p class="sentence">
                    <a class="handle" href=${item.patron_url}>${item.username}</a> ${this._action(item)}
                </p>
                <a class="chip" href=${item.list ? item.list.key : item.work.key}>
                    ${this._cover(item, 'S')}
                    <span class="chip__meta">${this._title(item)}${this._byline(item)}</span>
                </a>
                <p class="foot">${this._stars(item.rating)}<time class="when">${timeAgo(item.created)}</time></p>
            </div>
        </article>`;
    }

    /** 8 -- one line each, sized to sit under a My Books heading. */
    _renderTicker(item) {
        return html`<article class="card">
            ${this._cover(item, 'S')}
            <p class="sentence">
                <a class="handle" href=${item.patron_url}>${item.username}</a>
                ${this._action(item)}
                ${this._title(item)}
            </p>
            <time class="when">${timeAgo(item.created)}</time>
        </article>`;
    }

    /** 9 -- big type, no chrome, actions only on hover or focus. */
    _renderEditorial(item) {
        return html`<article class="card">
            ${this._cover(item, 'M')}
            <div class="meta">
                <p class="eyebrow">${item.label}</p>
                ${this._title(item)}
                ${this._byline(item)}
                <p class="attrib">
                    <a class="handle" href=${item.patron_url}>${item.username}</a>
                    <span class="dot">&middot;</span>
                    <time class="when">${timeAgo(item.created)}</time>
                    ${this._stars(item.rating)}
                </p>
            </div>
            <div class="reveal">${this._actions(item)}${this._followButton(item)}</div>
        </article>`;
    }

    /**
     * 10 -- regroups the same events by patron, to push following rather than
     * individual books. Presentation-level grouping; the data is unchanged.
     */
    _renderPeople() {
        const groups = new Map();
        for (const item of this._items) {
            if (!groups.has(item.username)) groups.set(item.username, []);
            groups.get(item.username).push(item);
        }
        return html`${[...groups.entries()].map(
            ([username, items]) => html`<article class="card">
                <header class="card__head">
                    <a class="patron" href=${items[0].patron_url}>
                        ${this._avatar(items[0], 'lg')}
                        <span class="handle">@${username}</span>
                    </a>
                    ${this._followButton(items[0])}
                </header>
                <p class="summary">
                    ${items.length} recent ${items.length === 1 ? 'update' : 'updates'}
                    <span class="dot">&middot;</span>
                    ${timeAgo(items[0].created)}
                </p>
                <div class="strip">
                    ${items.map(
        (item) => html`<figure class="strip__item">
                            ${this._cover(item, 'M')}
                            <figcaption>${item.label}</figcaption>
                        </figure>`
    )}
                </div>
            </article>`
        )}`;
    }

    _renderItem(item) {
        switch (this.variant) {
        case 2: return this._renderRiver(item);
        case 3: return this._renderCoverTile(item);
        case 4: return this._renderTimeline(item);
        case 5: return this._renderThread(item);
        case 6: return this._renderMagazine(item);
        case 7: return this._renderBubble(item);
        case 8: return this._renderTicker(item);
        case 9: return this._renderEditorial(item);
        default: return this._renderSpecCard(item);
        }
    }

    render() {
        const variant = VARIANT_BY_ID.get(this.variant) || FEED_VARIANTS[0];

        if (this._loading) {
            return html`<div class="state" aria-busy="true">Loading activity&hellip;</div>`;
        }
        if (this._error) {
            return html`<div class="state">
                Could not load the activity feed.
                <button class="btn btn--ghost" type="button" @click=${() => this._load()}>Retry</button>
            </div>`;
        }
        if (!this._items.length) {
            return html`<div class="state">
                No recent activity yet. Follow other readers and their updates will show up here.
            </div>`;
        }

        return html`
            ${this.heading ? html`<h2 class="heading">${this.heading}</h2>` : ''}
            <div class="feed feed--${variant.slug}" aria-live="polite">
                ${this.variant === 10
        ? this._renderPeople()
        : this._items.map(
            (item) => html`<div class="slot ${this._freshKeys.has(this._key(item)) ? 'is-fresh' : ''}">
                            ${this._renderItem(item)}
                        </div>`
        )}
            </div>
        `;
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
        }

        .heading {
            font-size: 1.15rem;
            margin: 0 0 12px;
        }

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

        /* -- shared primitives -- */

        a { color: inherit; }

        .avatar {
            border-radius: var(--border-radius-avatar, 50%);
            object-fit: cover;
            flex-shrink: 0;
            background: var(--grey-f3f3f3, #f3f3f3);
        }
        .avatar--sm { width: 22px; height: 22px; }
        .avatar--md { width: 32px; height: 32px; }
        .avatar--lg { width: 44px; height: 44px; }

        .patron {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            text-decoration: none;
            min-width: 0;
        }

        .handle {
            font-weight: 600;
            text-decoration: none;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .handle:hover { text-decoration: underline; }

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

        .action-link {
            color: var(--link-blue, #04618f);
            text-decoration: none;
        }
        .action-link:hover { text-decoration: underline; }

        .cover {
            display: block;
            flex-shrink: 0;
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

        /* Three list covers fanned out, per the reviewed list-card design. */
        .cover--stack {
            display: flex;
            gap: 4px;
        }
        .cover--stack img { width: 33%; }

        .title {
            display: block;
            font-weight: 700;
            line-height: 1.25;
            text-decoration: none;
        }
        .title:hover { text-decoration: underline; }

        .byline {
            display: block;
            font-size: 0.82rem;
            color: var(--feed-muted);
        }
        .byline a { text-decoration: none; }
        .byline a:hover { text-decoration: underline; }

        .stars { color: var(--orange, #e8a33d); white-space: nowrap; }
        .stars__empty { color: var(--grey-e7e7e7, #ddd); }

        .when, .dot { color: var(--feed-muted); font-size: 0.8rem; }

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
            display: flex;
            flex-direction: column;
            gap: 8px;
            height: 100%;
        }
        .feed--spec-card .card__head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
        }
        .feed--spec-card .card__action { margin: 0; font-size: 0.82rem; }
        .feed--spec-card .rule { border: 0; border-top: 1px solid var(--feed-rule); margin: 2px 0; width: 100%; }
        .feed--spec-card .card__body { display: flex; gap: 12px; flex: 1; }
        .feed--spec-card .cover { width: 62px; height: 90px; }
        .feed--spec-card .cover--stack { width: 90px; height: 90px; }
        .feed--spec-card .meta { min-width: 0; }
        .feed--spec-card .title { font-size: 0.95rem; margin-bottom: 3px; }
        .feed--spec-card .card__actions { display: flex; flex-direction: column; gap: 6px; }

        /* == 2. Goodreads river =========================================== */

        .feed--river { display: flex; flex-direction: column; }
        .feed--river .card {
            border-bottom: 1px solid var(--feed-rule);
            padding: 20px 4px;
        }
        .feed--river .card__head {
            display: grid;
            grid-template-columns: auto 1fr auto;
            align-items: center;
            gap: 12px;
            margin-bottom: 12px;
        }
        .feed--river .sentence { margin: 0; }
        .feed--river .card__body { display: flex; gap: 20px; padding-left: 56px; }
        .feed--river .cover { width: 110px; height: 165px; }
        .feed--river .cover--stack { width: 150px; height: 140px; }
        .feed--river .title { font-size: 1.15rem; margin-bottom: 4px; }
        .feed--river .textactions { display: flex; align-items: center; gap: 10px; margin-top: 12px; flex-wrap: wrap; }

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
        }
        .feed--cover-tiles .cover { width: 100%; height: 100%; }
        .feed--cover-tiles .cover img { border-radius: 0; box-shadow: none; }
        .feed--cover-tiles .cover--stack { align-items: stretch; }
        .feed--cover-tiles .cover--stack img { width: 33.34%; margin-left: 0; border: 0; }
        .feed--cover-tiles .caption {
            position: absolute;
            inset: auto 0 0 0;
            padding: 10px;
            display: flex;
            flex-direction: column;
            gap: 2px;
            color: var(--white, #fff);
            background: linear-gradient(to top, hsla(0, 0%, 0%, 0.85), hsla(0, 0%, 0%, 0));
        }
        .feed--cover-tiles .what { font-size: 0.75rem; opacity: 0.9; }
        .feed--cover-tiles .handle { font-size: 0.85rem; }

        /* == 4. Dense timeline ============================================ */

        .feed--timeline { display: flex; flex-direction: column; }
        .feed--timeline .card {
            display: grid;
            grid-template-columns: auto 1fr auto;
            align-items: center;
            gap: 10px;
            padding: 8px 4px;
            border-bottom: 1px solid var(--feed-rule);
        }
        .feed--timeline .sentence {
            margin: 0;
            font-size: 0.88rem;
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
            align-items: baseline;
        }
        .feed--timeline .title { display: inline; font-size: 0.88rem; }
        .feed--timeline .cover { width: 32px; height: 46px; }
        .feed--timeline .cover--stack { width: 50px; }

        /* == 5. Social thread ============================================= */

        .feed--thread { display: flex; flex-direction: column; }
        .feed--thread .card {
            display: grid;
            grid-template-columns: auto 1fr;
            gap: 12px;
            padding: 16px 4px;
            border-bottom: 1px solid var(--feed-rule);
        }
        .feed--thread .sentence,
        .feed--thread .what { margin: 0 0 6px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
        .feed--thread .quote {
            display: flex;
            gap: 12px;
            border: 1px solid var(--feed-rule);
            border-radius: var(--border-radius-card, 9px);
            padding: 10px;
            margin: 4px 0 10px;
        }
        .feed--thread .cover { width: 46px; height: 68px; }
        .feed--thread .cover--stack { width: 72px; height: 68px; }
        .feed--thread .title { font-size: 0.92rem; }
        .feed--thread .tray { display: flex; gap: 8px; }
        .feed--thread .follow { margin-left: auto; }

        /* == 6. Magazine ================================================== */

        .feed--magazine {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 32px;
        }
        .feed--magazine .card { display: flex; flex-direction: column; gap: 14px; }
        .feed--magazine .cover { width: 100%; height: 260px; }
        .feed--magazine .cover img { object-fit: contain; }
        .feed--magazine .cover--stack { height: 140px; }
        .feed--magazine .eyebrow {
            margin: 0 0 6px;
            font-size: 0.76rem;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: var(--feed-muted);
        }
        .feed--magazine .title {
            font-family: var(--font-family-serif, Georgia, serif);
            font-size: 1.4rem;
            line-height: 1.15;
            margin-bottom: 6px;
        }
        .feed--magazine .card__actions { display: flex; gap: 8px; margin-top: 14px; }

        /* == 7. Conversation ============================================== */

        .feed--bubbles { display: flex; flex-direction: column; gap: 14px; }
        .feed--bubbles .card { display: grid; grid-template-columns: auto 1fr; gap: 10px; align-items: start; }
        .feed--bubbles .bubble {
            background: var(--grey-f3f3f3, #f3f3f3);
            border-radius: var(--border-radius-xl, 12px);
            border-top-left-radius: var(--border-radius-sm, 3px);
            padding: 12px 14px;
        }
        .feed--bubbles .sentence { margin: 0 0 8px; }
        .feed--bubbles .chip {
            display: flex;
            gap: 10px;
            align-items: center;
            background: var(--white, #fff);
            border-radius: var(--border-radius-md, 6px);
            padding: 8px;
            text-decoration: none;
        }
        .feed--bubbles .cover { width: 34px; height: 50px; }
        .feed--bubbles .cover--stack { width: 56px; }
        .feed--bubbles .title { font-size: 0.9rem; }
        .feed--bubbles .foot { margin: 8px 0 0; display: flex; gap: 10px; align-items: center; }

        /* == 8. Ticker ==================================================== */

        .feed--ticker { display: flex; flex-direction: column; }
        .feed--ticker .card {
            display: grid;
            grid-template-columns: auto 1fr auto;
            align-items: center;
            gap: 10px;
            padding: 6px 8px;
            border-radius: var(--border-radius-md, 6px);
        }
        .feed--ticker .slot:nth-child(odd) .card { background: var(--grey-fafafa, #fafafa); }
        .feed--ticker .cover { width: 26px; height: 38px; }
        .feed--ticker .cover--stack { width: 40px; }
        .feed--ticker .sentence {
            margin: 0;
            font-size: 0.85rem;
            display: flex;
            gap: 5px;
            min-width: 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .feed--ticker .title { display: inline; font-weight: 700; }

        /* == 9. Editorial ================================================= */

        .feed--editorial { display: flex; flex-direction: column; }
        .feed--editorial .card {
            display: grid;
            grid-template-columns: auto 1fr;
            gap: 20px;
            align-items: center;
            padding: 22px 4px;
            border-bottom: 1px solid var(--feed-rule);
            position: relative;
        }
        .feed--editorial .cover { width: 70px; height: 104px; }
        .feed--editorial .cover--stack { width: 110px; height: 104px; }
        .feed--editorial .eyebrow {
            margin: 0 0 4px;
            font-size: 0.7rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: var(--feed-muted);
        }
        .feed--editorial .title { font-size: 1.5rem; line-height: 1.1; }
        .feed--editorial .attrib { margin: 8px 0 0; display: flex; gap: 8px; align-items: center; font-size: 0.82rem; }
        .feed--editorial .reveal {
            display: flex;
            gap: 8px;
            opacity: 0;
            transition: opacity 150ms;
            position: absolute;
            right: 4px;
            bottom: 22px;
        }
        .feed--editorial .card:hover .reveal,
        .feed--editorial .card:focus-within .reveal { opacity: 1; }
        /* Touch has no hover, so the actions must simply be present. */
        @media (hover: none) {
            .feed--editorial .reveal { opacity: 1; position: static; grid-column: 2; margin-top: 10px; }
        }

        /* == 10. People first ============================================= */

        .feed--people { display: flex; flex-direction: column; gap: 20px; }
        .feed--people .card {
            border: 1px solid var(--feed-rule);
            border-radius: var(--border-radius-card, 9px);
            padding: 14px;
            background: var(--feed-card-bg);
        }
        .feed--people .card__head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
        }
        .feed--people .summary { margin: 6px 0 12px; font-size: 0.8rem; color: var(--feed-muted); }
        .feed--people .strip {
            display: flex;
            gap: 12px;
            overflow-x: auto;
            padding-bottom: 6px;
        }
        .feed--people .strip__item { margin: 0; width: 78px; flex-shrink: 0; }
        .feed--people .cover { width: 78px; height: 116px; }
        .feed--people .cover--stack { height: 116px; }
        .feed--people figcaption {
            font-size: 0.7rem;
            color: var(--feed-muted);
            margin-top: 4px;
            line-height: 1.2;
        }

        /* -- mobile ------------------------------------------------------- */

        @media (max-width: 767px) {
            .feed--spec-card { grid-template-columns: 1fr; }
            /* One card per row means nothing needs to stretch to a shared
               height, and stretching just opens a gap above the actions. */
            .feed--spec-card .card { height: auto; }
            .feed--spec-card .card__body { flex: 0 1 auto; }
            .feed--river .card__body { padding-left: 0; gap: 14px; }
            .feed--river .cover { width: 80px; height: 120px; }
            .feed--river .title { font-size: 1rem; }
            .feed--magazine { grid-template-columns: 1fr; gap: 24px; }
            .feed--magazine .cover { height: 200px; }
            .feed--magazine .title { font-size: 1.2rem; }
            .feed--editorial .card { grid-template-columns: auto 1fr; gap: 14px; padding: 16px 4px; }
            .feed--editorial .title { font-size: 1.1rem; }
            .feed--editorial .cover { width: 54px; height: 80px; }
            /* Absolutely positioned, the action tray is wider than a phone-width
               card and pushes the page sideways. Do not rely on the hover:none
               query alone -- device emulation does not always report it. */
            .feed--editorial .reveal { opacity: 1; position: static; grid-column: 2; margin-top: 10px; flex-wrap: wrap; }
            .feed--timeline .cover { width: 26px; height: 38px; }
        }
    `;
}

customElements.define('ol-social-feed', OlSocialFeed);
