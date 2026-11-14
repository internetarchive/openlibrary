import { LitElement, css, html } from 'lit';

/**
 * OlSocialFeed -- social activity feed web component for Open Library.
 *
 * Renders community activity (shelving, reading actions) in a responsive Showcase row
 * preview consuming /trending/now.json or internal activity feeds.
 *
 * @element ol-social-feed
 *
 * @prop {String} apiUrl - Endpoint to fetch feed JSON from (defaults to '/trending/now.json')
 * @prop {Number} variant - Layout treatment id (11 = showcase row)
 * @prop {Number} limit - Number of items to display
 * @prop {Boolean} controls - Display refresh and pagination controls
 * @prop {String} viewerUsername - Current logged-in user handle
 * @prop {Number} refreshInterval - Auto-refresh interval in seconds (0 disables)
 * @prop {String} heading - Optional panel heading title
 * @prop {String} headingHref - Optional link for heading
 * @fires ol-social-feed-load - Fired after each successful feed fetch
 */

const COVERS_BASE = 'https://covers.openlibrary.org/b/id';
const FALLBACK_COVER = '/static/images/icons/avatar_book-sm.png';
const FALLBACK_AVATAR = '/static/images/icons/avatar_author-lg.png';

/** Compact relative time helper: `3d`, `2h`, `just now`. */
export function timeAgo(iso) {
    if (!iso) return '';
    const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    const units = [
        ['y', 31536000],
        ['mo', 2592000],
        ['w', 604800],
        ['d', 86400],
        ['h', 3600],
        ['m', 60]
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
        controls: { type: Boolean },
        viewerUsername: { type: String, attribute: 'viewer-username' },
        refreshInterval: { type: Number, attribute: 'refresh-interval' },
        heading: { type: String },
        headingHref: { type: String, attribute: 'heading-href' },
        _items: { state: true },
        _loading: { state: true },
        _error: { state: true },
        _following: { state: true },
        _page: { state: true },
        _hasMore: { state: true },
        _busy: { state: true }
    };

    constructor() {
        super();
        this.apiUrl = '/trending/now.json';
        this.variant = 11;
        this.limit = 3;
        this.controls = true;
        this.viewerUsername = '';
        this.refreshInterval = 60;
        this.heading = '';
        this.headingHref = '';
        this._items = [];
        this._loading = true;
        this._error = false;
        this._following = new Set();
        this._page = 1;
        this._hasMore = false;
        this._busy = false;
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

    async _load({ background = false } = {}) {
        if (!background) this._loading = true;
        const sep = this.apiUrl.includes('?') ? '&' : '?';
        const url = `${this.apiUrl}${sep}limit=${this.limit}&page=${this._page}`;
        try {
            const response = await fetch(url, { headers: { Accept: 'application/json' } });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            let items = data.activity || [];
            if (!items.length && Array.isArray(data.works) && data.works.length) {
                items = data.works.map(work => ({
                    type: 'shelf_change',
                    username: 'community',
                    patron_url: '/trending/now',
                    avatar_url: FALLBACK_AVATAR,
                    created: null,
                    label: 'shelved recently',
                    shelf_url: '/trending/now',
                    work: {
                        key: work.key,
                        title: work.title,
                        author: Array.isArray(work.author_name) ? work.author_name[0] : work.author_name || 'Unknown Author',
                        author_key: Array.isArray(work.author_key) ? `/authors/${work.author_key[0]}` : work.author_key,
                        cover_id: work.cover_i,
                        first_publish_year: work.first_publish_year,
                        ebook_access: work.ebook_access
                    }
                }));
            }
            this._items = items;
            this._hasMore = items.length >= this.limit;
            this._error = false;
            this.dispatchEvent(
                new CustomEvent('ol-social-feed-load', {
                    detail: { count: items.length },
                    bubbles: true,
                    composed: true
                })
            );
        } catch {
            if (!background) this._error = true;
        } finally {
            this._loading = false;
        }
    }

    async _refresh() {
        this._busy = true;
        await this._load({ background: true });
        this._busy = false;
    }

    async _turnTo(page) {
        if (page < 1 || this._busy) return;
        this._page = page;
        this._busy = true;
        await this._load();
        this._busy = false;
        this._startTimer();
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
                redirect: 'manual'
            });
            if (!response.ok && response.type !== 'opaqueredirect') throw new Error('follow failed');
        } catch {
            const reverted = new Set(this._following);
            if (wasFollowing) reverted.add(username);
            else reverted.delete(username);
            this._following = reverted;
        }
    }

    _onTouchStart(e) {
        this._touchX = e.changedTouches[0].clientX;
    }

    _onTouchEnd(e) {
        if (this._touchX === undefined) return;
        const dx = e.changedTouches[0].clientX - this._touchX;
        this._touchX = undefined;
        if (dx < -60 && this._hasMore) this._turnTo(this._page + 1);
        else if (dx > 60 && this._page > 1) this._turnTo(this._page - 1);
    }

    _renderControls() {
        if (!this.controls) return '';
        return html`<div class="controls">
            <button class="ctl ctl--refresh" type="button" ?disabled=${this._busy} @click=${() => this._refresh()} aria-label="Refresh activity">
                <span aria-hidden="true">↻</span>
            </button>
            <button
                class="ctl ctl--prev"
                type="button"
                ?disabled=${this._page <= 1 || this._busy}
                @click=${() => this._turnTo(this._page - 1)}
                aria-label="Newer activity"
            >
                <span aria-hidden="true">‹</span> <span class="ctl__text">Newer</span>
            </button>
            <button
                class="ctl ctl--next"
                type="button"
                ?disabled=${!this._hasMore || this._busy}
                @click=${() => this._turnTo(this._page + 1)}
                aria-label="Older activity"
            >
                <span class="ctl__text">Older</span> <span aria-hidden="true">›</span>
            </button>
        </div>`;
    }

    _renderCard(item) {
        const work = item.work || {};
        const following = this._following.has(item.username);
        const isViewer = item.username === this.viewerUsername;
        const coverSrc = coverUrl(work.cover_id);

        return html`<article class="card" data-type=${item.type || 'shelf_change'}>
            <div class="head">
                <a class="gutter" href=${item.patron_url || '#'} aria-label=${`${item.username}'s profile`}>
                    <img
                        class="avatar"
                        src=${item.avatar_url || FALLBACK_AVATAR}
                        alt=""
                        loading="lazy"
                        @error=${e => {
                            e.target.src = FALLBACK_AVATAR;
                        }}
                    />
                </a>
                <p class="sentence">
                    <a class="handle" href=${item.patron_url || '#'}>${item.username}</a>
                    ${item.shelf_url ? html`<a class="verb" href=${item.shelf_url}>${item.label}</a>` : html`<span class="verb">${item.label}</span>`}
                </p>
                <time class="when">${timeAgo(item.created)}</time>
                ${
                    isViewer
                        ? ''
                        : html`<button
                              class="follow ${following ? 'is-following' : ''}"
                              type="button"
                              aria-pressed=${following ? 'true' : 'false'}
                              @click=${() => this._toggleFollow(item.username)}
                          >
                              ${following ? 'Following' : 'Follow'}
                          </button>`
                }
            </div>

            <div class="content">
                <a class="cover" href=${work.key || '#'}>
                    <img
                        src=${coverSrc}
                        alt=${`Cover of ${work.title || 'book'}`}
                        loading="lazy"
                        @error=${e => {
                            e.target.src = FALLBACK_COVER;
                        }}
                    />
                </a>
                <div class="body">
                    <a class="title" href=${work.key || '#'}>${work.title}</a>
                    <span class="byline">
                        ${work.author ? html`by ${work.author_key ? html`<a href=${work.author_key}>${work.author}</a>` : work.author}` : 'Unknown author'}
                    </span>
                    <div class="actions">
                        <a class="btn btn--primary" href=${work.key || '#'}>Want to Read</a>
                    </div>
                </div>
            </div>
        </article>`;
    }

    render() {
        let inner;
        if (this._loading) {
            inner = html`<div class="state" aria-busy="true">Loading activity&hellip;</div>`;
        } else if (this._error) {
            inner = html`<div class="state">
                Could not load the activity feed.
                <button class="btn btn--ghost" type="button" @click=${() => this._load()}>Retry</button>
            </div>`;
        } else if (!this._items.length) {
            inner = html`<div class="state">No recent activity yet. Follow other readers and their updates will show up here.</div>`;
        } else {
            inner = html`
                <div
                    class="feed feed--showcase"
                    aria-live="polite"
                    aria-busy=${this._busy}
                    @touchstart=${e => this._onTouchStart(e)}
                    @touchend=${e => this._onTouchEnd(e)}
                >
                    ${this._items.map(item => html`<div class="slot">${this._renderCard(item)}</div>`)}
                </div>
                ${this._renderControls()}
            `;
        }

        if (!this.heading) return inner;
        return html`<section class="panel">
            <header class="panel__head">
                <h2>${this.headingHref ? html`<a href=${this.headingHref}>${this.heading}</a>` : this.heading}</h2>
                <slot name="panel-action"></slot>
            </header>
            ${inner}
        </section>`;
    }

    static styles = css`
        *,
        *::before,
        *::after {
            box-sizing: border-box;
        }

        :host {
            box-sizing: border-box;
            display: block;
            font-family: inherit;
            color: var(--grey-464646, #464646);
            max-width: var(--page-max-width, 1060px);
            margin-inline: auto;

            --feed-card-bg: var(--white, #fff);
            --feed-rule: var(--grey-e7e7e7, #e7e7e7);
            --feed-muted: var(--grey, #666);
            --feed-shadow: 2px 2px 4px hsla(0, 0%, 0%, 0.1);
        }

        a {
            color: inherit;
        }

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

        .panel__head a {
            text-decoration: none;
        }

        .panel__head a:hover {
            text-decoration: underline;
        }

        .state {
            padding: 24px;
            text-align: center;
            color: var(--feed-muted);
        }

        .feed--showcase {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 16px;
            align-items: stretch;
        }

        .slot {
            display: flex;
            flex-direction: column;
            min-width: 0;
        }

        .card {
            display: flex;
            flex-direction: column;
            gap: 8px;
            min-width: 0;
            background: var(--feed-card-bg);
            border: var(--border-width-thin, 1px) solid var(--feed-rule);
            border-radius: var(--border-radius-card, 9px);
            box-shadow: var(--feed-shadow);
            padding: 12px 14px 14px;
            height: 100%;
            flex: 1;
        }

        .head {
            display: grid;
            grid-template-columns: auto 1fr auto;
            grid-template-areas:
                'gutter . follow'
                'sentence sentence when';
            row-gap: 6px;
            align-items: center;
        }

        .gutter {
            grid-area: gutter;
            display: flex;
            flex-shrink: 0;
        }

        .avatar {
            width: 32px;
            height: 32px;
            border-radius: var(--border-radius-avatar, 50%);
            object-fit: cover;
            background: var(--grey-e7e7e7, #e7e7e7);
        }

        .sentence {
            grid-area: sentence;
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

        .handle:hover {
            text-decoration: underline;
        }

        .verb {
            color: var(--link-blue, #04618f);
            text-decoration: none;
        }

        a.verb:hover {
            text-decoration: underline;
        }

        .when {
            grid-area: when;
            color: var(--feed-muted);
            font-size: 0.8rem;
            margin-left: 0;
            align-self: baseline;
            white-space: nowrap;
        }

        .follow {
            grid-area: follow;
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
            transition: transform var(--duration-press, 100ms);
        }

        .follow:hover {
            background: var(--link-blue, #04618f);
        }

        .follow:active {
            transform: scale(var(--press-scale, 0.97));
        }

        .follow.is-following {
            background: transparent;
            color: var(--primary-blue, #0577b5);
        }

        .content {
            display: flex;
            gap: 12px;
            min-width: 0;
            flex: 1;
            border-top: var(--border-width-thin, 1px) solid var(--feed-rule);
            padding-top: 10px;
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

        .body {
            min-width: 0;
            display: flex;
            flex-direction: column;
            gap: 3px;
            flex: 1;
        }

        .title {
            font-weight: 700;
            line-height: 1.25;
            text-decoration: none;
            font-size: 0.95rem;
            overflow: hidden;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
        }

        .title:hover {
            text-decoration: underline;
        }

        .byline {
            font-size: 0.82rem;
            color: var(--feed-muted);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .byline a {
            text-decoration: none;
        }

        .byline a:hover {
            text-decoration: underline;
        }

        .actions {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-top: auto;
            padding-top: 6px;
        }

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
            transition: transform var(--duration-press, 100ms);
        }

        .btn:active {
            transform: scale(var(--press-scale, 0.97));
        }

        .btn--primary {
            background: var(--primary-blue, #0577b5);
            color: var(--white, #fff);
        }

        .btn--primary:hover {
            background: var(--link-blue, #04618f);
        }

        .btn--ghost {
            background: transparent;
            border-color: var(--feed-rule);
            color: inherit;
        }

        .controls {
            display: flex;
            justify-content: flex-end;
            align-items: center;
            gap: var(--spacing-inline-md, 8px);
            margin-top: var(--spacing-stack-lg, 24px);
            padding-top: var(--spacing-3xs, 2px);
        }

        .ctl {
            font: inherit;
            font-size: 0.85rem;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            min-height: 36px;
            padding: 0 16px;
            border: var(--border-width-thin, 1px) solid var(--feed-rule);
            border-radius: var(--border-radius-pill, 9999px);
            background: var(--feed-card-bg);
            color: inherit;
            cursor: pointer;
            user-select: none;
            transition:
                background 120ms ease,
                border-color 120ms ease,
                color 120ms ease,
                transform var(--duration-press, 100ms);
        }

        .ctl:focus-visible,
        .btn:focus-visible,
        .follow:focus-visible {
            outline: 2px solid var(--color-focus-ring, var(--primary-blue, #0577b5));
            outline-offset: 2px;
        }

        .ctl:active:not(:disabled) {
            transform: scale(var(--press-scale, 0.97));
        }

        .ctl--refresh:active:not(:disabled) {
            transform: scale(var(--press-scale-compact, 0.92));
        }

        @media (hover: hover) and (pointer: fine) {
            .ctl:hover:not(:disabled) {
                background: var(--color-control-hover, #fbfbfb);
                border-color: var(--color-border-hover, var(--primary-blue, #0577b5));
                color: var(--primary-blue, #0577b5);
            }
        }

        .ctl:disabled {
            opacity: 0.45;
            cursor: not-allowed;
            border-color: var(--grey-e7e7e7, #e7e7e7);
            background: var(--grey-fafafa, #fafafa);
        }

        @media (max-width: 767px) {
            .feed--showcase {
                grid-template-columns: 1fr;
            }
            .feed--showcase .card {
                height: auto;
            }
            .feed--showcase .content {
                flex: 0 1 auto;
            }
            .controls {
                justify-content: stretch;
                margin-top: var(--spacing-stack-md, 16px);
            }
            .ctl--prev,
            .ctl--next {
                flex: 1;
                justify-content: center;
            }
        }
    `;
}

customElements.define('ol-social-feed', OlSocialFeed);
