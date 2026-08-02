import { LitElement, css, html } from 'lit';

/**
 * OlSocialFeed -- the social activity feed for My Books.
 *
 * Renders a stream of what other patrons are doing with books: shelving them,
 * rating them, gathering them into lists, liking each other's lists. Every
 * event carries the actions a reader would want next -- borrow or shelve the
 * book, open the list, follow the patron.
 *
 * ## One container for every activity type
 *
 * Following Goodreads' Updates panel, every event type renders into the *same*
 * card skeleton rather than getting its own bespoke layout:
 *
 *     avatar   Actor  verb  target                            when   [Follow]
 *              ┌───────┐  Title
 *              │ media │  subtitle
 *              └───────┘  [primary action] [secondary]  ★★★★☆
 *
 * A shelving fills `media` with a book cover and `target` with the shelf; a
 * list update fills `media` with a fan of three covers and `subtitle` with a
 * book count. Nothing about the frame changes. Adding an event type means
 * writing one `_present` branch, not a new template -- and a card means the
 * same thing to a reader wherever it appears.
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
 * @prop {String} scope - `auto`, `public`, or `following`
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
        viewerUsername: { type: String, attribute: 'viewer-username' },
        refreshInterval: { type: Number, attribute: 'refresh-interval' },
        heading: { type: String },
        headingHref: { type: String, attribute: 'heading-href' },
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
        this.headingHref = '';
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

    // -- the presenter ----------------------------------------------------

    /**
     * Map one event onto the card's slots.
     *
     * This is the only place that knows how event types differ. Everything
     * downstream sees the same shape, which is what lets one skeleton serve
     * all of them.
     */
    _present(item) {
        const isList = Boolean(item.list);

        if (isList) {
            const ids = item.list.cover_ids.length ? item.list.cover_ids : [null];
            return {
                href: item.list.key,
                covers: ids.slice(0, 3),
                coverAlt: item.list.name,
                title: item.list.name,
                subtitle: `${item.list.book_count} ${item.list.book_count === 1 ? 'book' : 'books'}`,
                subtitleHref: null,
                actions: [{ label: 'View List', href: item.list.key, primary: true }],
            };
        }

        const work = item.work;
        // A borrowable book leads with Borrow; everything else leads with the shelf.
        const borrowable = work.ebook_access === 'borrowable' || work.ebook_access === 'public';
        return {
            href: work.key,
            covers: [work.cover_id],
            coverAlt: `Cover of ${work.title}`,
            title: work.title,
            subtitle: work.author ? `by ${work.author}` : 'Unknown author',
            subtitleHref: work.author ? work.author_key : null,
            actions: borrowable
                ? [
                    { label: 'Borrow', href: work.key, primary: true },
                    { label: 'Want to Read', href: work.key, primary: false },
                ]
                : [{ label: 'Want to Read', href: work.key, primary: true }],
        };
    }

    // -- the one card skeleton --------------------------------------------

    _renderCard(item) {
        const slot = this._present(item);
        const following = this._following.has(item.username);
        const isViewer = item.username === this.viewerUsername;
        const stacked = slot.covers.length > 1;

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
                <a class="cover ${stacked ? 'cover--stack' : ''}" href=${slot.href}
                    aria-label=${stacked ? slot.coverAlt : ''}>
                    ${slot.covers.map(
        (id) => html`<img src=${coverUrl(id)} alt=${stacked ? '' : slot.coverAlt} loading="lazy"
                            @error=${(e) => { e.target.src = FALLBACK_COVER; }} />`
    )}
                </a>
                <div class="body">
                    <a class="title" href=${slot.href}>${slot.title}</a>
                    <span class="byline">
                        ${slot.subtitleHref
        ? html`by <a href=${slot.subtitleHref}>${slot.subtitle.replace(/^by /, '')}</a>`
        : slot.subtitle}
                    </span>
                    ${item.rating
        ? html`<span class="stars" aria-label="Rated ${item.rating} out of 5"
                            >${'★'.repeat(item.rating)}<span class="stars__empty">${'★'.repeat(5 - item.rating)}</span></span>`
        : ''}
                    <div class="actions">
                        ${slot.actions.map(
        (a) => html`<a class="btn ${a.primary ? 'btn--primary' : 'btn--ghost'}" href=${a.href}>${a.label}</a>`
    )}
                    </div>
                </div>
            </div>
        </article>`;
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
                                <img src=${coverUrl(slot.covers[0])} alt=${slot.coverAlt} loading="lazy"
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
            inner = html`<div class="state" aria-busy="true">Loading activity&hellip;</div>`;
        } else if (this._error) {
            inner = html`<div class="state">
                Could not load the activity feed.
                <button class="btn btn--ghost" type="button" @click=${() => this._load()}>Retry</button>
            </div>`;
        } else if (!this._items.length) {
            inner = html`<div class="state">
                No recent activity yet. Follow other readers and their updates will show up here.
            </div>`;
        } else {
            inner = html`<div class="feed feed--${variant.slug}" aria-live="polite">
                ${this.variant === 10
        ? this._renderPeople()
        : this._items.map(
            (item) => html`<div class="slot ${this._freshKeys.has(this._key(item)) ? 'is-fresh' : ''}">
                            ${this._renderCard(item)}
                        </div>`
        )}
            </div>`;
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

        /* Three list covers fanned horizontally, overlapping, so each stays
           legible in the footprint a single cover would take. */
        .cover--stack { width: 90px; align-items: flex-start; }
        .cover--stack img {
            width: 60%;
            border: var(--border-width, 1px) solid var(--white, #fff);
        }
        .cover--stack img + img { margin-left: -40%; }

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
        .feed--river .cover--stack { width: 150px; height: 140px; }
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
        .feed--cover-tiles .cover--stack { align-items: stretch; }
        .feed--cover-tiles .cover--stack img { width: 33.34%; margin-left: 0; border: 0; }
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
        .feed--timeline .cover--stack { width: 50px; }
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
        .feed--thread .cover--stack { width: 72px; height: 68px; }
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
        .feed--magazine .cover--stack { height: 140px; }
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
        .feed--bubbles .cover--stack { width: 56px; }
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
        .feed--ticker .cover--stack { width: 40px; }
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
        .feed--editorial .cover--stack { width: 110px; height: 104px; }
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
        }
    `;
}

customElements.define('ol-social-feed', OlSocialFeed);
