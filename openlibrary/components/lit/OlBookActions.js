import { LitElement, html, css, nothing } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { styleMap } from 'lit/directives/style-map.js';
import { icon } from './utils/book-icons.js';
import { SHELF, setShelf, setRating, fetchUserLists, addToList, removeFromList, createList } from './utils/books-api.js';
import { showToast } from './OlToastRegion.js';
import './OlPopover.js';

/**
 * Per-book action popover: reading-log shelves, a star rating, and an
 * "Add to list" pane that slides in from the right. Composes `<ol-popover>`
 * for the shell; the caller supplies the trigger.
 *
 * Only for logged-in users — the caller sends logged-out visitors to login
 * instead of rendering this. State is optimistic: the UI updates first and
 * an error toast rolls back.
 *
 * @element ol-book-actions
 *
 * @prop {Object} book     - `{ key, title, firstPublishYear?, editionKey? }`
 * @prop {Number} shelf    - Current shelf id (1–4) or null
 * @prop {Number} rating   - Current rating (1–5) or null
 * @prop {String} userKey  - "/people/<username>", needed to create lists
 * @prop {Object} labels   - Translated strings (see DEFAULT_LABELS)
 * @prop {String} placement - ol-popover placement (default "bottom-end")
 *
 * @fires ol-book-state-change - After a shelf or rating change is accepted by
 *     the server. detail: { key, shelf, rating }
 *
 * @slot trigger - The button that opens the popover.
 */
export const DEFAULT_LABELS = {
    actionsFor: 'Actions for %(title)s',
    wantToRead: 'Want to Read',
    currentlyReading: 'Currently Reading',
    alreadyRead: 'Already Read',
    stoppedReading: 'Stopped Reading',
    rateThisBook: 'Rate this book',
    rateStar: 'Rate %(rating)s of 5',
    clearRating: 'Clear rating',
    addToList: 'Add to list',
    back: 'Back',
    createList: 'Create a list',
    listName: 'List name',
    create: 'Create',
    filterLists: 'Filter lists…',
    noLists: 'You have no lists yet.',
    noMatchingLists: 'No lists match.',
    loadingLists: 'Loading lists…',
    itemsInList: '%(count)s items',
    inLists: 'In %(count)s of your lists',
    errorGeneric: 'Something went wrong. Please try again.',
};

const SHELF_ROWS = [
    { id: SHELF.WANT_TO_READ, icon: 'bookmark', label: 'wantToRead' },
    { id: SHELF.CURRENTLY_READING, icon: 'book-open', label: 'currentlyReading' },
    { id: SHELF.ALREADY_READ, icon: 'circle-check', label: 'alreadyRead' },
    { id: SHELF.STOPPED_READING, icon: 'circle-pause', label: 'stoppedReading' },
];

// One in-flight lists request shared by every popover on the page.
let _listsPromise = null;
/** Drop the shared lists cache (tests, or after a mutation elsewhere). */
export function resetListsCache() {
    _listsPromise = null;
}

/** "%(name)s" style interpolation, matching the server-side i18n strings. */
export function fmt(template, vars) {
    return template.replace(/%\((\w+)\)s/g, (_, k) => (vars[k] ?? ''));
}

export class OlBookActions extends LitElement {
    static properties = {
        book: { type: Object },
        shelf: { type: Number },
        rating: { type: Number },
        userKey: { type: String, attribute: 'user-key' },
        labels: { type: Object },
        placement: { type: String },
        _pane: { state: true },
        _snap: { state: true },
        _trackHeight: { state: true },
        _lists: { state: true },
        _listsLoading: { state: true },
        _listFilter: { state: true },
        _creating: { state: true },
        _createBusy: { state: true },
        _hoverRating: { state: true },
        _busy: { state: true },
    };

    static styles = css`
        :host {
            display: inline-flex;
            font-family: var(--font-family-body);
        }

        .panel {
            /* A fixed measure: the popover shrink-wraps its content, and the
               nowrap title would otherwise size the panel per book. */
            width: 300px;
            color: var(--color-text);
            font-size: var(--font-size-body-medium);
            /* clip, not hidden: focusing the off-screen pane must not scroll
               the panel (that would double up with the track's translate). */
            overflow: clip;
            border-radius: var(--border-radius-overlay);
        }

        /* ol-popover becomes a full-bleed bottom tray here (keep in sync with
           its 767px breakpoint), so fill it instead of leaving a dead strip. */
        @media (max-width: 767px) {
            .panel {
                width: 100%;
            }
        }

        .header {
            padding: var(--spacing-inset-sm) var(--spacing-inset-md);
            border-bottom: var(--border-divider);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .header strong {
            font-weight: 700;
        }

        .header .year {
            color: var(--color-text-secondary);
        }

        /* Two panes side by side in a track twice the panel width; the track
           slides to reveal the second one. Its height is set inline to the
           active pane's height (measured), so the panel doesn't stretch to
           the taller pane. */
        .track {
            display: flex;
            align-items: flex-start;
            width: 200%;
            transition:
                transform 220ms cubic-bezier(0.165, 0.84, 0.44, 1),
                height 220ms cubic-bezier(0.165, 0.84, 0.44, 1);
        }

        .track.pane-lists {
            transform: translateX(-50%);
        }

        /* Reset to the main pane on close without a visible slide. */
        .track.snap {
            transition: none;
        }

        @media (prefers-reduced-motion: reduce) {
            .track {
                transition: none;
            }
        }

        .pane {
            width: 50%;
            flex: 0 0 50%;
            box-sizing: border-box;
        }

        /* Off-screen pane must not be reachable */
        .pane[inert] {
            visibility: hidden;
        }

        .group {
            padding: var(--spacing-inset-xs) 0;
        }

        .group + .group {
            border-top: var(--border-divider);
        }

        .row {
            display: flex;
            align-items: center;
            gap: var(--spacing-inline-md);
            width: 100%;
            box-sizing: border-box;
            margin: 0;
            padding: var(--spacing-inset-sm) var(--spacing-inset-md);
            border: 0;
            background: none;
            color: inherit;
            font: inherit;
            text-align: left;
            cursor: pointer;
            text-decoration: none;
        }

        .row .obd-icon {
            width: 20px;
            height: 20px;
            flex: 0 0 20px;
            color: var(--color-icon-muted);
        }

        .row .label {
            flex: 1;
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .row .trail {
            width: 16px;
            height: 16px;
            color: var(--color-icon-muted);
        }

        @media (hover: hover) and (pointer: fine) {
            .row:hover {
                background: var(--color-hover-overlay);
            }
        }

        .row:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: -2px;
        }

        .row[aria-checked="true"] {
            color: var(--color-link);
            font-weight: 600;
        }

        .row[aria-checked="true"] .obd-icon {
            color: var(--color-link);
        }

        .row[disabled] {
            cursor: default;
            opacity: 0.6;
        }

        /* Stars */
        .stars {
            display: flex;
            align-items: center;
            gap: var(--spacing-inline-md);
            padding: var(--spacing-inset-sm) var(--spacing-inset-md);
        }

        .star-buttons {
            display: inline-flex;
        }

        .star {
            padding: 0;
            border: 0;
            background: none;
            color: var(--gold);
            cursor: pointer;
            line-height: 0;
        }

        .star .obd-icon {
            width: 24px;
            height: 24px;
        }

        .star:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            border-radius: var(--border-radius-sm);
        }

        .stars .caption {
            color: var(--color-text-secondary);
            font-size: var(--font-size-label-medium);
        }

        .stars .clear {
            padding: 0;
            border: 0;
            background: none;
            font: inherit;
            font-size: var(--font-size-label-medium);
            text-decoration: underline;
            cursor: pointer;
        }

        .stars .clear:hover {
            color: var(--color-text-primary);
        }

        .stars .clear:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            border-radius: var(--border-radius-sm);
        }

        /* Lists pane */
        .lists-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: var(--spacing-inline-sm);
            padding: var(--spacing-inset-sm) var(--spacing-inset-md);
            border-bottom: var(--border-divider);
        }

        .back {
            display: inline-flex;
            align-items: center;
            gap: 2px;
            padding: 0;
            border: 0;
            background: none;
            color: inherit;
            font: inherit;
            font-weight: 600;
            cursor: pointer;
        }

        .back .obd-icon {
            width: 16px;
            height: 16px;
        }

        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
            height: var(--control-height-small);
            padding: 0 var(--spacing-inset-sm);
            border: 1px solid transparent;
            border-radius: var(--border-radius-button);
            background: var(--color-primary);
            color: var(--color-on-primary);
            font: inherit;
            font-size: var(--font-size-label-medium);
            font-weight: 600;
            white-space: nowrap;
            cursor: pointer;
        }

        .btn:hover {
            background: var(--color-primary-hover);
        }

        .btn:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        .btn[disabled] {
            background: var(--color-disabled-bg);
            color: var(--color-disabled-fg);
            cursor: default;
        }

        .btn .obd-icon {
            width: 14px;
            height: 14px;
        }

        .field {
            display: flex;
            gap: var(--spacing-inline-sm);
            padding: var(--spacing-inset-sm) var(--spacing-inset-md);
            margin-bottom: var(--spacing-stack-xs);
        }

        .input {
            flex: 1;
            min-width: 0;
            height: var(--control-height-small);
            box-sizing: border-box;
            padding: 0 var(--spacing-inset-sm);
            border: var(--border-input);
            border-radius: var(--border-radius-input);
            background: var(--color-surface);
            color: inherit;
            font: inherit;
        }

        .input:focus {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: -1px;
        }

        .list-items {
            max-height: 240px;
            overflow-y: auto;
            padding-bottom: var(--spacing-inset-xs);
        }

        .list-row {
            display: flex;
            align-items: center;
            gap: var(--spacing-inline-md);
            padding: var(--spacing-inset-xs) var(--spacing-inset-md);
            cursor: pointer;
        }

        @media (hover: hover) and (pointer: fine) {
            .list-row:hover {
                background: var(--color-hover-overlay);
            }
        }

        .list-row input {
            width: 18px;
            height: 18px;
            margin: 0;
            accent-color: var(--color-primary);
            flex: 0 0 auto;
        }

        .list-row .name {
            flex: 1;
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .count {
            min-width: 20px;
            padding: 1px 8px;
            border-radius: var(--border-radius-pill);
            background: var(--color-surface-sunken);
            color: var(--color-text-secondary);
            font-size: var(--font-size-label-small);
            text-align: center;
        }

        .empty,
        .loading {
            display: flex;
            align-items: center;
            gap: var(--spacing-inline-sm);
            padding: var(--spacing-inset-md);
            color: var(--color-text-secondary);
            font-size: var(--font-size-label-medium);
        }

        .spinner {
            width: 18px;
            height: 18px;
            animation: spin 0.9s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        @media (prefers-reduced-motion: reduce) {
            .spinner {
                animation-duration: 3s;
            }
        }
    `;

    constructor() {
        super();
        this.book = null;
        this.shelf = null;
        this.rating = null;
        this.userKey = '';
        this.labels = {};
        this.placement = 'bottom-end';
        this._pane = 'main';
        this._snap = false;
        this._trackHeight = 0;
        this._lists = null;
        this._listsLoading = false;
        this._listFilter = '';
        this._creating = false;
        this._createBusy = false;
        this._hoverRating = 0;
        this._busy = false;
    }

    /** @param {string} key */
    t(key, vars) {
        const s = this.labels?.[key] ?? DEFAULT_LABELS[key] ?? key;
        return vars ? fmt(s, vars) : s;
    }

    get _seedKey() {
        return this.book?.key || '';
    }

    render() {
        if (!this.book) return html`<slot name="trigger"></slot>`;
        const title = this.book.title || '';
        return html`
            <ol-popover
                placement=${this.placement}
                offset="6"
                aria-label=${this.t('actionsFor', { title })}
                @ol-popover-open=${this._onOpen}
                @ol-popover-close=${this._onCloseRequest}
            >
                <slot name="trigger" slot="trigger"></slot>
                <div class="panel">
                    <div
                        class="track ${classMap({ 'pane-lists': this._pane === 'lists', snap: this._snap })}"
                        style=${styleMap({ height: this._trackHeight ? `${this._trackHeight}px` : null })}
                    >
                        <div class="pane" ?inert=${this._pane !== 'main'}>${this._renderMain()}</div>
                        <div class="pane" ?inert=${this._pane !== 'lists'}>${this._renderLists()}</div>
                    </div>
                </div>
            </ol-popover>
        `;
    }

    _renderMain() {
        const year = this.book.firstPublishYear;
        return html`
            <div class="header">
                <strong>${this.book.title}</strong>
                ${year ? html` <span class="year">(${year})</span>` : nothing}
            </div>
            <div class="group" role="group">
                ${SHELF_ROWS.map(row => html`
                    <button
                        type="button"
                        class="row"
                        role="menuitemradio"
                        aria-checked=${this.shelf === row.id ? 'true' : 'false'}
                        ?disabled=${this._busy}
                        @click=${() => this._onShelfClick(row.id)}
                    >
                        ${icon(row.icon)}
                        <span class="label">${this.t(row.label)}</span>
                        ${this.shelf === row.id ? icon('check', { cls: 'obd-icon trail' }) : nothing}
                    </button>
                `)}
            </div>
            <div class="group">
                ${this._renderStars()}
            </div>
            <div class="group">
                <button type="button" class="row" @click=${this._openLists}>
                    ${icon('list-plus')}
                    <span class="label">${this.t('addToList')}</span>
                    ${this._listCount ? html`<span class="count" aria-label=${this.t('inLists', { count: this._listCount })}>${this._listCount}</span>` : nothing}
                    ${icon('chevron-right', { cls: 'obd-icon trail' })}
                </button>
            </div>
        `;
    }

    _renderStars() {
        const shown = this._hoverRating || this.rating || 0;
        // Once rated, the caption becomes an actionable "Clear rating" link.
        const caption = this.rating
            ? html`<button type="button" class="caption clear" ?disabled=${this._busy} @click=${() => this._onRate(this.rating)}>${this.t('clearRating')}</button>`
            : html`<span class="caption">${this.t('rateThisBook')}</span>`;
        return html`
            <div class="stars">
                <span class="star-buttons" role="radiogroup" aria-label=${this.t('rateThisBook')} @mouseleave=${() => { this._hoverRating = 0; }}>
                    ${[1, 2, 3, 4, 5].map(n => html`
                        <button
                            type="button"
                            class="star"
                            role="radio"
                            aria-checked=${this.rating === n ? 'true' : 'false'}
                            aria-label=${this.rating === n ? this.t('clearRating') : this.t('rateStar', { rating: n })}
                            ?disabled=${this._busy}
                            @mouseenter=${() => { this._hoverRating = n; }}
                            @focus=${() => { this._hoverRating = n; }}
                            @blur=${() => { this._hoverRating = 0; }}
                            @click=${() => this._onRate(n)}
                        >${icon('star', { fill: n <= shown ? 'currentColor' : 'none', strokeWidth: 1.5 })}</button>
                    `)}
                </span>
                ${caption}
            </div>
        `;
    }

    _renderLists() {
        return html`
            <div class="lists-header">
                <button type="button" class="back" @click=${this._closeLists}>
                    ${icon('chevron-left')}${this.t('back')}
                </button>
                ${this._creating ? nothing : html`
                    <button type="button" class="btn" @click=${this._startCreate}>
                        ${icon('plus')}${this.t('createList')}
                    </button>
                `}
            </div>
            ${this._creating ? html`
                <form class="field" @submit=${this._onCreateSubmit}>
                    <input
                        class="input"
                        name="name"
                        type="text"
                        required
                        maxlength="200"
                        placeholder=${this.t('listName')}
                        aria-label=${this.t('listName')}
                        ?disabled=${this._createBusy}
                        @keydown=${e => { if (e.key === 'Escape') { e.stopPropagation(); this._cancelCreate(); } }}
                    />
                    <button type="submit" class="btn" ?disabled=${this._createBusy}>${this.t('create')}</button>
                </form>
            ` : html`
                <div class="field">
                    <input
                        class="input"
                        type="search"
                        placeholder=${this.t('filterLists')}
                        aria-label=${this.t('filterLists')}
                        .value=${this._listFilter}
                        @input=${e => { this._listFilter = e.target.value; }}
                    />
                </div>
            `}
            <div class="list-items">${this._renderListItems()}</div>
        `;
    }

    _renderListItems() {
        if (this._listsLoading || this._lists === null) {
            return html`<div class="loading" role="status">${icon('loader', { cls: 'obd-icon spinner' })}${this.t('loadingLists')}</div>`;
        }
        const entries = Object.entries(this._lists);
        if (!entries.length) return html`<div class="empty">${this.t('noLists')}</div>`;
        const filter = this._listFilter.trim().toLowerCase();
        const shown = filter ? entries.filter(([, l]) => l.listName.toLowerCase().includes(filter)) : entries;
        if (!shown.length) return html`<div class="empty">${this.t('noMatchingLists')}</div>`;
        return shown.map(([key, list]) => {
            const checked = list.members.includes(this._seedKey);
            return html`
                <label class="list-row">
                    <input type="checkbox" .checked=${checked} @change=${e => this._onListToggle(key, e.target.checked)} />
                    <span class="name">${list.listName}</span>
                    <span class="count" aria-label=${this.t('itemsInList', { count: list.members.length })}>${list.members.length}</span>
                </label>
            `;
        });
    }

    updated(changed) {
        // Panes only exist once `book` is set, so observe them lazily.
        if (!this._resizeObserver) {
            const panes = this.shadowRoot.querySelectorAll('.pane');
            if (panes.length) {
                this._resizeObserver = new ResizeObserver(() => this._syncTrackHeight());
                panes.forEach(pane => this._resizeObserver.observe(pane));
            }
        }
        if (changed.has('_pane')) this._syncTrackHeight();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._resizeObserver?.disconnect();
    }

    /** Size the track to the active pane so the panel doesn't stretch to the taller one. */
    _syncTrackHeight() {
        const pane = this.shadowRoot.querySelector(`.pane:nth-child(${this._pane === 'lists' ? 2 : 1})`);
        // 0 means the popover is hidden; keep the last real height.
        if (pane?.offsetHeight) this._trackHeight = pane.offsetHeight;
    }

    // ── Popover lifecycle ────────────────────────────────────

    _onOpen() {
        this._pane = 'main';
        this._snap = false;
        this._creating = false;
        this._listFilter = '';
        // If another popover already fetched the user's lists, reuse them so
        // the "in N lists" count shows without opening the lists pane.
        if (this._lists === null && _listsPromise) this._loadLists();
    }

    _onCloseRequest(e) {
        // Escape from the lists pane goes back a step instead of closing.
        if (e.detail?.reason === 'escape' && this._pane === 'lists') {
            e.preventDefault();
            this._closeLists();
            return;
        }
        // Reset to the main pane now, so the next open doesn't slide back from
        // the lists pane. `snap` skips the slide while the popover fades out.
        this._snap = true;
        this._pane = 'main';
        this._creating = false;
    }

    _emitState() {
        this.dispatchEvent(new CustomEvent('ol-book-state-change', {
            bubbles: true,
            composed: true,
            detail: { key: this.book.key, shelf: this.shelf, rating: this.rating },
        }));
    }

    _fail(error) {
        if (error?.status === 401) {
            window.location.href = `/account/login?redirect=${encodeURIComponent(window.location.pathname + window.location.search)}`;
            return;
        }
        showToast(this.t('errorGeneric'), { type: 'error' });
    }

    // ── Shelves ──────────────────────────────────────────────

    async _onShelfClick(shelfId) {
        const previous = this.shelf;
        this.shelf = previous === shelfId ? null : shelfId;
        this._busy = true;
        try {
            // Posting the current shelf toggles it off server-side.
            await setShelf(this.book.key, shelfId, { editionKey: this.book.editionKey });
            this._emitState();
        } catch (error) {
            this.shelf = previous;
            this._fail(error);
        } finally {
            this._busy = false;
        }
    }

    // ── Rating ───────────────────────────────────────────────

    async _onRate(n) {
        const previous = this.rating;
        const previousShelf = this.shelf;
        const next = previous === n ? null : n;
        this.rating = next;
        // The server moves a rated book to Already Read.
        if (next) this.shelf = SHELF.ALREADY_READ;
        this._busy = true;
        try {
            await setRating(this.book.key, next, { editionKey: this.book.editionKey });
            this._emitState();
        } catch (error) {
            this.rating = previous;
            this.shelf = previousShelf;
            this._fail(error);
        } finally {
            this._busy = false;
        }
    }

    // ── Lists ────────────────────────────────────────────────

    async _openLists() {
        this._pane = 'lists';
        await this.updateComplete;
        this.shadowRoot.querySelector('.pane:nth-child(2) .input')?.focus({ preventScroll: true });
        this._loadLists();
    }

    async _closeLists() {
        this._pane = 'main';
        this._creating = false;
        await this.updateComplete;
        this.shadowRoot.querySelector('.pane:nth-child(1) .group:last-child .row')?.focus({ preventScroll: true });
    }

    /** How many of the user's (loaded) lists contain this book. */
    get _listCount() {
        if (!this._lists) return 0;
        return Object.values(this._lists).filter(l => l.members.includes(this._seedKey)).length;
    }

    async _loadLists() {
        if (this._lists !== null && !this._listsLoading) return;
        this._listsLoading = true;
        try {
            _listsPromise ||= fetchUserLists();
            this._lists = await _listsPromise;
        } catch (error) {
            _listsPromise = null;
            this._lists = {};
            this._fail(error);
        } finally {
            this._listsLoading = false;
        }
    }

    async _onListToggle(listKey, checked) {
        const list = this._lists[listKey];
        const before = list.members;
        list.members = checked ? [...before, this._seedKey] : before.filter(k => k !== this._seedKey);
        this.requestUpdate();
        try {
            await (checked ? addToList(listKey, this._seedKey) : removeFromList(listKey, this._seedKey));
        } catch (error) {
            list.members = before;
            this.requestUpdate();
            this._fail(error);
        }
    }

    async _startCreate() {
        this._creating = true;
        await this.updateComplete;
        this.shadowRoot.querySelector('form.field .input')?.focus({ preventScroll: true });
    }

    async _cancelCreate() {
        this._creating = false;
        await this.updateComplete;
        this.shadowRoot.querySelector('.field .input')?.focus({ preventScroll: true });
    }

    async _onCreateSubmit(e) {
        e.preventDefault();
        const name = e.target.querySelector('input').value.trim();
        if (!name || this._createBusy) return;
        this._createBusy = true;
        try {
            const created = await createList(this.userKey, name, this._seedKey);
            // Prepend so the new list is visible immediately; the shared cache
            // is the same object, so sibling popovers see it too.
            this._lists = { [created.key]: { listName: name, members: [this._seedKey] }, ...this._lists };
            _listsPromise = Promise.resolve(this._lists);
            this._creating = false;
        } catch (error) {
            this._fail(error);
        } finally {
            this._createBusy = false;
        }
    }
}

customElements.define('ol-book-actions', OlBookActions);
