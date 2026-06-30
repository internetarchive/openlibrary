import { LitElement, html, css } from 'lit';

/**
 * OLActivityFeed — "What's Happening Now" homepage widget.
 *
 * Displays a sliding window of 3 public reading-log activity cards.
 * Auto-advances every 15 seconds by pulling from an internal buffer;
 * fetches the next page from the API when the buffer is exhausted.
 * A right-arrow lets the patron advance manually. When all pages are
 * consumed, the arrow becomes a "More →" link to /trending.
 *
 * @element ol-activity-feed
 *
 * @prop {String} apiUrl        - Endpoint to fetch activity JSON from.
 *                                Default: "/api/internal/activity.json"
 * @prop {Number} cardsPerPage  - Cards shown at once. Default: 3
 */

const SHELF_LABELS = {
    1: 'added to Want to Read',
    2: 'is Currently Reading',
    3: 'has Already Read',
    4: 'stopped reading',
};

const COVERS_BASE = 'https://covers.openlibrary.org/b/id';
const FALLBACK_COVER = '/static/images/icons/avatar_book-sm.png';
const FALLBACK_AVATAR = '/static/images/icons/avatar_book-sm.png';

function timeAgo(updated) {
    if (!updated) return '';
    const diff = Date.now() - new Date(updated).getTime();
    const days = Math.floor(diff / 86400000);
    if (days === 0) return 'today';
    if (days === 1) return '1d ago';
    return `${days}d ago`;
}

export class OLActivityFeed extends LitElement {
    static properties = {
        apiUrl: { type: String, attribute: 'api-url' },
        cardsPerPage: { type: Number, attribute: 'cards-per-page' },
        viewerUsername: { type: String, attribute: 'viewer-username' },
        _displayed: { state: true },
        _queue: { state: true },
        _loading: { state: true },
        _atEnd: { state: true },
        _nextPage: { state: true },
        _followed: { state: true },
    };

    static styles = css`
        :host {
            display: block;
            font-family: inherit;
        }

        .feed {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        /* Individual activity card */
        .card {
            background: var(--white, #fff);
            border-radius: var(--border-radius-card, 9px);
            box-shadow: 0 1px 4px rgba(0,0,0,.1);
            overflow: hidden;
        }

        /* TOP: patron identity + action text */
        .card-header {
            padding: 12px 14px 10px;
        }

        .patron-row {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 4px;
        }

        .avatar {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            object-fit: cover;
            flex-shrink: 0;
            border: 2px solid #eee;
        }

        .username {
            font-size: 13px;
            font-weight: 600;
            color: #222;
            text-decoration: none;
            flex: 1;
            min-width: 0;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .username:hover { text-decoration: underline; }

        .btn-follow {
            background: var(--primary-blue, #1565c0);
            color: var(--white, #fff);
            border: 1.5px solid var(--primary-blue, #1565c0);
            border-radius: var(--border-radius-pill, 9999px);
            padding: 4px 12px;
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            flex-shrink: 0;
            transition: background-color .15s, border-color .15s;
        }
        .btn-follow:hover {
            background: var(--link-blue, #0d47a1);
            border-color: var(--link-blue, #0d47a1);
        }
        .btn-follow.following {
            background: var(--white, #fff);
            border-color: var(--color-border-subtle, #ccc);
            color: var(--dark-grey, #444);
        }
        .btn-follow.following:hover {
            background: var(--lightest-grey, #f5f5f5);
        }

        .action-text {
            font-size: 12px;
            color: #666;
        }

        .card-divider {
            margin: 0 14px;
            border: none;
            border-top: 1px solid #eee;
        }

        /* BOTTOM: book content */
        .card-body {
            padding: 12px 14px 14px;
        }

        .book-row {
            display: flex;
            gap: 12px;
            margin-bottom: 10px;
            text-decoration: none;
            color: inherit;
        }

        .book-cover {
            width: 58px;
            height: 82px;
            object-fit: cover;
            border-radius: var(--border-radius-thumbnail, 3px);
            flex-shrink: 0;
            box-shadow: 0 1px 3px rgba(0,0,0,.2);
        }

        .book-meta {
            flex: 1;
            min-width: 0;
            padding-top: 2px;
        }

        .book-title {
            font-size: 14px;
            font-weight: 700;
            color: #111;
            line-height: 1.3;
            margin-bottom: 4px;
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .book-author {
            font-size: 12px;
            color: #666;
        }

        .btn-row {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .btn-primary {
            display: block;
            background: var(--primary-blue, #1565c0);
            color: var(--white, #fff);
            border: 1.5px solid var(--primary-blue, #1565c0);
            border-radius: var(--border-radius-button, 6px);
            padding: 8px 0;
            font-size: var(--font-size-body-medium, 13px);
            font-weight: 500;
            text-align: center;
            text-decoration: none;
            cursor: pointer;
            transition: background-color .15s, border-color .15s;
        }
        .btn-primary:hover {
            background: var(--link-blue, #0d47a1);
            border-color: var(--link-blue, #0d47a1);
        }

        /* Navigation footer */
        .feed-footer {
            display: flex;
            justify-content: flex-end;
            padding-top: 4px;
        }

        .btn-next {
            background: none;
            border: 1.5px solid var(--color-border-subtle, #ccc);
            border-radius: var(--border-radius-circle, 50%);
            width: 36px;
            height: 36px;
            font-size: 20px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--dark-grey, #444);
            transition: border-color .15s, color .15s;
        }
        .btn-next:hover {
            border-color: var(--primary-blue, #1565c0);
            color: var(--primary-blue, #1565c0);
        }

        .btn-more {
            font-size: var(--font-size-body-medium, 13px);
            font-weight: 500;
            color: var(--primary-blue, #1565c0);
            text-decoration: none;
            padding: 8px 4px;
            border-bottom: 2px solid transparent;
            transition: border-color .15s;
        }
        .btn-more:hover { border-bottom-color: var(--primary-blue, #1565c0); }

        .loading {
            padding: 24px;
            text-align: center;
            color: #888;
            font-size: 14px;
        }
    `;

    constructor() {
        super();
        this.apiUrl = '/api/internal/activity.json';
        this.cardsPerPage = 3;
        this.viewerUsername = '';
        this._displayed = [];
        this._queue = [];
        this._loading = true;
        this._atEnd = false;
        this._nextPage = 1;
        this._followed = new Set();
        this._timer = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._fetchPage();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._stopTimer();
    }

    _startTimer() {
        this._stopTimer();
        this._timer = setInterval(() => this._advance(), 15000);
    }

    _stopTimer() {
        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }
    }

    async _fetchPage() {
        try {
            const res = await fetch(
                `${this.apiUrl}?limit=12&page=${this._nextPage}`
            );
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            const items = data.activity || [];

            if (items.length === 0) {
                this._atEnd = true;
                this._loading = false;
                return;
            }

            this._nextPage++;
            const combined = [...this._queue, ...items];
            this._displayed = combined.slice(0, this.cardsPerPage);
            this._queue = combined.slice(this.cardsPerPage);
            this._loading = false;
            this._startTimer();
        } catch (_) {
            this._loading = false;
            this._atEnd = true;
        }
    }

    _advance() {
        if (this._queue.length >= this.cardsPerPage) {
            this._displayed = this._queue.slice(0, this.cardsPerPage);
            this._queue = this._queue.slice(this.cardsPerPage);
        } else if (this._queue.length > 0 && this._atEnd) {
            this._displayed = this._queue;
            this._queue = [];
        } else {
            // Fetch another page to refill
            this._fetchPage();
        }
    }

    async _toggleFollow(username) {
        if (!this.viewerUsername) {
            window.location = `/account/login?redir_url=${encodeURIComponent(window.location.pathname)}`;
            return;
        }
        const following = this._followed.has(username);
        const next = new Set(this._followed);
        following ? next.delete(username) : next.add(username);
        this._followed = next;

        const body = new FormData();
        body.append('publisher', username);
        body.append('state', following ? '1' : '0');
        body.append('redir_url', window.location.pathname);

        try {
            await fetch(`/people/${this.viewerUsername}/follows.json`, {
                method: 'POST',
                body,
                redirect: 'manual',
            });
        } catch (_) {
            // Revert optimistic update on network failure
            const reverted = new Set(this._followed);
            following ? reverted.add(username) : reverted.delete(username);
            this._followed = reverted;
        }
    }

    _renderCard(item) {
        const label = SHELF_LABELS[item.shelf_id] || 'logged';
        const ago = timeAgo(item.updated);
        const coverSrc = item.cover_id
            ? `${COVERS_BASE}/${item.cover_id}-M.jpg`
            : FALLBACK_COVER;
        const isViewer = item.username === this.viewerUsername;
        const following = this._followed.has(item.username);

        return html`
            <div class="card">
                <div class="card-header">
                    <div class="patron-row">
                        <img class="avatar" src="${item.avatar_url}"
                            alt="@${item.username}"
                            @error=${(e) => { e.target.src = FALLBACK_AVATAR; }}>
                        <a class="username" href="/people/${item.username}">@${item.username}</a>
                        ${!isViewer ? html`
                            <button
                                class="btn-follow ${following ? 'following' : ''}"
                                @click=${() => this._toggleFollow(item.username)}
                                aria-label="${following ? `Unfollow ${item.username}` : `Follow ${item.username}`}">
                                ${following ? 'Following' : 'Follow +'}
                            </button>
                        ` : ''}
                    </div>
                    <div class="action-text">${item.username} ${label} · ${ago}</div>
                </div>
                <hr class="card-divider">
                <div class="card-body">
                    <a class="book-row" href="${item.work_key}">
                        <img class="book-cover" src="${coverSrc}"
                            alt="${item.title}"
                            @error=${(e) => { e.target.src = FALLBACK_COVER; }}>
                        <div class="book-meta">
                            <div class="book-title">${item.title}</div>
                            ${item.author ? html`<div class="book-author">by ${item.author}</div>` : ''}
                        </div>
                    </a>
                    <div class="btn-row">
                        <a class="btn-primary" href="${item.work_key}">View Book</a>
                    </div>
                </div>
            </div>
        `;
    }

    render() {
        if (this._loading) {
            return html`<div class="loading">Loading activity…</div>`;
        }
        if (!this._displayed.length) {
            return html``;
        }

        const exhausted = this._atEnd && this._queue.length === 0;

        return html`
            <div class="feed">
                ${this._displayed.map((item) => this._renderCard(item))}
                <div class="feed-footer">
                    ${exhausted
        ? html`<a class="btn-more" href="/trending">More →</a>`
        : html`<button class="btn-next" @click=${() => this._advance()} aria-label="Next activity">›</button>`
}
                </div>
            </div>
        `;
    }
}

customElements.define('ol-activity-feed', OLActivityFeed);
