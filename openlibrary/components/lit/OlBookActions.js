import { LitElement, html, css, nothing } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { styleMap } from 'lit/directives/style-map.js';
import { ifDefined } from 'lit/directives/if-defined.js';
import './OlIcon.js';
import { SHELF, setShelf, setRating, setCheckIn, fetchUserLists, addToList, removeFromList, createList } from './utils/books-api.js';
import { showToast } from './OlToastRegion.js';
import { trackEvent } from './utils/analytics.js';
// Re-exported: several components were importing `fmt` from here before it
// moved to the shared helper.
export { fmt } from './utils/labels.js';
import { translate } from './utils/labels.js';
import './OlPopover.js';
import './OLButton.js';

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
    whenFinished: 'When did you finish this book?',
    today: 'Today',
    inYear: 'In %(year)s',
    otherDate: 'Other date',
    year: 'Year',
    month: 'Month',
    day: 'Day',
    saveDate: 'Save',
};

const SHELF_ROWS = [
    { id: SHELF.WANT_TO_READ, icon: 'bookmark', label: 'wantToRead' },
    { id: SHELF.CURRENTLY_READING, icon: 'book-open', label: 'currentlyReading' },
    { id: SHELF.ALREADY_READ, icon: 'circle-check', label: 'alreadyRead' },
    { id: SHELF.STOPPED_READING, icon: 'circle-pause', label: 'stoppedReading' },
];

/** Matomo action names, kept identical to the legacy dropper's `data-ol-link-track`. */
const SHELF_EVENT = {
    [SHELF.WANT_TO_READ]: 'WantToRead',
    [SHELF.CURRENTLY_READING]: 'CurrentlyReading',
    [SHELF.ALREADY_READ]: 'AlreadyRead',
    [SHELF.STOPPED_READING]: 'StoppedReading',
};

/**
 * The panes in the track, in order. The track's width and slide are both
 * derived from this, so a new pane is an entry here plus a `_render*`.
 */
const PANES = ['main', 'lists', 'checkIn'];

let _months = null;
/** Month names in the page's language. Cached: the list never changes. */
function MONTHS() {
    if (!_months) {
        const lang = document.documentElement.lang || 'en';
        const format = new Intl.DateTimeFormat(lang, { month: 'long' });
        _months = Array.from({ length: 12 }, (_, i) => format.format(new Date(2000, i, 1)));
    }
    return _months;
}

/**
 * A check-in date for display. The schema stores partial dates, so "2026",
 * "2026-08" and "2026-08-22" are all valid and each shows only what is known.
 */
function formatReadDate(value) {
    const [year, month, day] = String(value).split('-').map(Number);
    if (!year) return '';
    const lang = document.documentElement.lang || 'en';
    const options = month
        ? (day ? { year: 'numeric', month: 'short', day: 'numeric' } : { year: 'numeric', month: 'short' })
        : null;
    if (!options) return String(year);
    return new Intl.DateTimeFormat(lang, options).format(new Date(year, month - 1, day || 1));
}

/**
 * The years offered as one tap. For the first 30 days of a new year the year
 * just gone stays on offer: that is when a reader is most likely logging
 * something they finished before the turn, and "In 2025" on 25 January saves
 * them the date picker.
 */
export function quickYears(now = new Date()) {
    const year = now.getFullYear();
    const daysIn = Math.floor((now - new Date(year, 0, 1)) / 86400000);
    return daysIn < 30 ? [year, year - 1] : [year];
}

/** The inverse: `{year, month, day}` as the schema stores it. */
function partialDate({ year, month, day }) {
    const pad = n => String(n).padStart(2, '0');
    if (!month) return String(year);
    return day ? `${year}-${pad(month)}-${pad(day)}` : `${year}-${pad(month)}`;
}

// One in-flight lists request shared by every popover on the page.
let _listsPromise = null;
/** Drop the shared lists cache (tests, or after a mutation elsewhere). */
export function resetListsCache() {
    _listsPromise = null;
}


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
 * @prop {String} readDate - The check-in date, whole or partial ("2026",
 *     "2026-08", "2026-08-22"), or null when the reader has not given one
 * @prop {Number} eventId - Id of that check-in, so changing the date edits it
 *     rather than recording a second finish
 * @prop {String} userKey  - "/people/<username>", needed to create lists
 * @prop {Object} labels   - Translated strings (see DEFAULT_LABELS)
 * @prop {String} placement - ol-popover placement; unset uses its default
 *
 * @fires ol-book-state-change - After a shelf or rating change is accepted by
 *     the server. detail: { key, shelf, rating }
 * @fires ol-book-check-in - After a finish date is accepted by the server, so
 *     the surface can hand it back. detail: { key, date, eventId } — `date` is
 *     whole or partial, as stored.
 * @fires ol-list-created - After the inline form creates a list, so sibling
 *     popovers and any legacy droppers on the page can add the row. The legacy
 *     side dispatches the same event on `document` when it creates one.
 *     detail: { key, name, seedKey }
 *
 * @slot trigger - The button that opens the popover.
 */
export class OlBookActions extends LitElement {
    static properties = {
        book: { type: Object },
        shelf: { type: Number },
        rating: { type: Number },
        readDate: { type: String, attribute: 'read-date' },
        eventId: { type: Number, attribute: 'event-id' },
        userKey: { type: String, attribute: 'user-key' },
        labels: { type: Object },
        placement: { type: String },
        hideRating: { type: Boolean, attribute: 'hide-rating' },
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
        _pickingDate: { state: true },
        _dateBusy: { state: true },
        _date: { state: true },
    };

    static styles = css`
        :host {
            display: inline-flex;
            font-family: var(--font-family-body);
        }

        .panel {
            /* A fixed measure: the popover shrink-wraps its content, and the
               title would otherwise size the panel per book. */
            width: 300px;
            /* Keeps the first and last rows off the rounded corners. */
            padding-block: var(--spacing-inset-xs);
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

        /* Metadata, not a title bar: quiet enough that the rows below it read
           as the actionable part of the panel. */
        .header {
            position: relative;
            padding: var(--spacing-inset-sm) var(--spacing-inset-md);
            color: var(--color-text-secondary);
            font-size: var(--font-size-label-medium);
        }

        /* Clamped as one block so the year wraps with the title. */
        .header .heading {
            display: -webkit-box;
            -webkit-box-orient: vertical;
            -webkit-line-clamp: 2;
            overflow: hidden;
        }

        /* Inset rules read as separators inside the surface; a full-bleed one
           reads as a panel edge. */
        .header::after,
        .lists-header::after,
        .pane-header::after,
        .group.rating::before,
        .group.lists-entry::before {
            content: "";
            position: absolute;
            inset-inline: var(--spacing-inset-md);
            height: 1px;
            background: var(--color-border-subtle);
        }

        .header::after,
        .lists-header::after,
        .pane-header::after {
            bottom: 0;
        }

        /* Panes side by side in a track --pane-count panels wide; the track
           slides to bring one into view. Its height is set inline to the active
           pane's height (measured), so the panel doesn't stretch to the tallest
           one. Both the width and the slide come from --pane-count, so adding a
           pane to PANES is the whole change. */
        .track {
            display: flex;
            align-items: flex-start;
            width: calc(100% * var(--pane-count));
            transition:
                transform 220ms cubic-bezier(0.165, 0.84, 0.44, 1),
                height 220ms cubic-bezier(0.165, 0.84, 0.44, 1);
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
            width: calc(100% / var(--pane-count));
            flex: 0 0 calc(100% / var(--pane-count));
            box-sizing: border-box;
        }

        /* Off-screen pane must not be reachable */
        .pane[inert] {
            visibility: hidden;
        }

        .group {
            display: flex;
            flex-direction: column;
            padding: var(--spacing-inset-xs) 0;
        }

        .group.rating,
        .group.lists-entry {
            position: relative;
        }

        .group.rating::before,
        .group.lists-entry::before {
            top: 0;
        }

        /* Inset so the hover fill reads as a pill inside the panel rather
           than a band running to its edges; the padding gives back what the
           margin takes, so the icon column stays put. */
        .row {
            display: flex;
            align-items: center;
            gap: var(--spacing-inline-md);
            box-sizing: border-box;
            margin: 0;
            margin-inline: var(--spacing-inset-xs);
            padding-block: var(--spacing-inset-sm);
            padding-inline: calc(var(--spacing-inset-md) - var(--spacing-inset-xs));
            border-radius: var(--border-radius-button);
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

        /* Press feedback, the same tactile squeeze <ol-button> gives: colour
           changes are instant, only the scale animates. A row has no resting
           fill, so the press paints one — on touch, where :hover never runs,
           there would otherwise be nothing to squeeze. */
        .row,
        .list-row {
            transition: transform 0.08s;
        }

        .row:active,
        .list-row:active {
            background: var(--color-hover-overlay);
            transform: scale(0.97);
        }

        /* Except the shelf rows: clicking one re-renders it — label weight and
           colour change, a check mark appears — and re-laying out mid-scale
           reads as a flicker. They keep the press fill, not the squeeze. */
        .group.shelves .row {
            transition: none;
        }

        .group.shelves .row:active {
            transform: none;
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
            cursor: pointer;
            line-height: 0;
        }

        /* Sized to the row icons, and only the filled stars carry the gold —
           an all-gold band outweighs the shelves above it. */
        .star .obd-icon {
            width: 20px;
            height: 20px;
            color: var(--color-icon-muted);
            --ol-icon-stroke-width: 1.5;
        }

        .star .obd-icon[filled] {
            color: var(--gold);
        }

        /* Icon-only, so 3% would be sub-pixel — <ol-button> presses its icon
           shapes harder for the same reason. */
        .star {
            transition: transform 0.08s;
        }

        .star:active {
            transform: scale(0.93);
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
            color: var(--color-text-secondary);
            font: inherit;
            font-size: var(--font-size-label-medium);
            cursor: pointer;
        }

        .stars .clear:hover {
            color: var(--color-text);
            text-decoration: underline;
        }

        .stars .clear:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            border-radius: var(--border-radius-sm);
        }

        /* Check-in pane */

        /* The question, not a heading: the rows under it are the answer. */
        .caption {
            padding: var(--spacing-inset-sm) var(--spacing-inset-md);
            color: var(--color-text-secondary);
            font-size: var(--font-size-label-medium);
        }

        /* A disclosure, not a link onwards: the chevron points down at the
           fields the row opens and flips once they are showing. */
        .date-toggle .trail {
            transition: transform 180ms cubic-bezier(0.165, 0.84, 0.44, 1);
        }

        .date-toggle[aria-expanded='true'] .trail {
            transform: rotate(180deg);
        }

        @media (prefers-reduced-motion: reduce) {
            .date-toggle .trail {
                transition: none;
            }
        }

        /* Sits directly under the row that opened it, so the gap reads as a
           seam between row and fields rather than a new section. */
        .date-form {
            padding-top: var(--spacing-inset-xs);
        }

        /* Three selects on one line only fit at small size — the same height
           and radius the small web-component controls use. */
        .date-fields {
            display: flex;
            gap: var(--spacing-inline-sm);
            padding: 0 var(--spacing-inset-md) var(--spacing-inset-sm);
        }

        .select {
            flex: 1;
            min-width: 0;
            height: var(--control-height-small);
            box-sizing: border-box;
            padding: 0 var(--spacing-inset-xs);
            border: var(--border-input);
            border-radius: var(--border-radius-input);
            background: var(--color-surface);
            color: inherit;
            font: inherit;
            font-size: var(--font-size-label-medium);
        }

        /* Year is the only one that is always meaningful, so it gets the room. */
        .select.year {
            flex: 0 0 84px;
        }

        .select:focus {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: -1px;
        }

        .select:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .date-actions {
            display: flex;
            justify-content: flex-end;
            padding: 0 var(--spacing-inset-md) var(--spacing-inset-sm);
        }

        /* Lists pane */
        .lists-header,
        .pane-header {
            position: relative;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: var(--spacing-inline-sm);
            padding: var(--spacing-inset-sm) var(--spacing-inset-md);
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
            margin-inline: var(--spacing-inset-xs);
            padding-block: var(--spacing-inset-sm);
            padding-inline: calc(var(--spacing-inset-md) - var(--spacing-inset-xs));
            border-radius: var(--border-radius-button);
            cursor: pointer;
        }

        @media (hover: hover) and (pointer: fine) {
            .list-row:hover {
                background: var(--color-hover-overlay);
            }
        }

        /* 20px like the main pane's row icons, so both panes share one row
           height and one label column. */
        .list-row input {
            width: 20px;
            height: 20px;
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
            color: var(--color-text-secondary);
            font-size: var(--font-size-label-medium);
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
        this.hideRating = false;
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
        this._pickingDate = false;
        this._dateBusy = false;
        this._date = { year: '', month: '', day: '' };
    }

    get _paneIndex() {
        const index = PANES.indexOf(this._pane);
        return index === -1 ? 0 : index;
    }

    /** @param {string} name */
    _renderPane(name) {
        if (name === 'lists') return this._renderLists();
        if (name === 'checkIn') return this._renderCheckIn();
        return this._renderMain();
    }

    /** @param {string} key */
    t(key, vars) {
        return translate(this.labels, DEFAULT_LABELS, key, vars);
    }

    get _seedKey() {
        return this.book?.key || '';
    }

    render() {
        if (!this.book) return html`<slot name="trigger"></slot>`;
        const title = this.book.title || '';
        const track = {
            '--pane-count': String(PANES.length),
            transform: `translateX(${(-100 / PANES.length) * this._paneIndex}%)`,
            height: this._trackHeight ? `${this._trackHeight}px` : null,
        };
        return html`
            <ol-popover
                placement=${ifDefined(this.placement)}
                offset="6"
                aria-label=${this.t('actionsFor', { title })}
                @ol-popover-open=${this._onOpen}
                @ol-popover-close=${this._onCloseRequest}
            >
                <slot name="trigger" slot="trigger"></slot>
                <div class="panel">
                    <div
                        class="track ${classMap({ snap: this._snap })}"
                        style=${styleMap(track)}
                    >
                        ${PANES.map(name => html`
                            <div class="pane" ?inert=${this._pane !== name}>${this._renderPane(name)}</div>
                        `)}
                    </div>
                </div>
            </ol-popover>
        `;
    }

    _renderMain() {
        const year = this.book.firstPublishYear;
        return html`
            <div class="header">
                <span class="heading">${this.book.title}${year ? ` (${year})` : ''}</span>
            </div>
            <div class="group shelves" role="group">
                ${SHELF_ROWS.map(row => html`
                    <button
                        type="button"
                        class="row"
                        role="menuitemradio"
                        aria-checked=${this.shelf === row.id ? 'true' : 'false'}
                        ?disabled=${this._busy}
                        @click=${() => this._onShelfClick(row.id)}
                    >
                        <ol-icon class="obd-icon" name=${row.icon}></ol-icon>
                        <span class="label">${this.t(row.label)}</span>
                        ${this._renderShelfTrail(row)}
                    </button>
                `)}
            </div>
            ${this.hideRating ? nothing : html`
                <div class="group rating">
                    ${this._renderStars()}
                </div>
            `}
            <div class="group lists-entry">
                <button type="button" class="row" @click=${this._openLists}>
                    <ol-icon class="obd-icon" name="list-plus"></ol-icon>
                    <span class="label">${this.t('addToList')}</span>
                    ${this._listCount ? html`<span class="count" aria-label=${this.t('inLists', { count: this._listCount })}>${this._listCount}</span>` : nothing}
                    <ol-icon class="obd-icon trail" name="chevron-right"></ol-icon>
                </button>
            </div>
        `;
    }

    /**
     * The end of a shelf row. Already Read carries the date it holds and a
     * chevron, because it leads to the date pane; the others only mark the
     * shelf the book is on.
     */
    _renderShelfTrail(row) {
        if (row.id === SHELF.ALREADY_READ) {
            return html`
                ${this.readDate ? html`<span class="count">${formatReadDate(this.readDate)}</span>` : nothing}
                <ol-icon class="obd-icon trail" name="chevron-right"></ol-icon>
            `;
        }
        return this.shelf === row.id ? html`<ol-icon class="obd-icon trail" name="check"></ol-icon>` : nothing;
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
                        ><ol-icon class="obd-icon" name="star" ?filled=${n <= shown}></ol-icon></button>
                    `)}
                </span>
                ${caption}
            </div>
        `;
    }

    /**
     * Which row the recorded date is, so the pane shows the answer it already
     * holds instead of reading as unanswered. Anything that is neither exactly
     * today nor one of the offered years — a partial date included — belongs
     * to "Other date".
     */
    get _answeredBy() {
        if (!this.readDate) return null;
        const now = new Date();
        if (this.readDate === partialDate({ year: now.getFullYear(), month: now.getMonth() + 1, day: now.getDate() })) return 'today';
        if (quickYears(now).some(y => this.readDate === String(y))) return this.readDate;
        return 'other';
    }

    /**
     * Asked straight after the reader marks a book read. Two one-tap answers
     * cover most cases; "Other date" discloses the selects underneath itself
     * rather than replacing the rows or taking a fourth pane, so the two quick
     * answers stay one tap away and the row you pressed stays on screen as the
     * anchor. The track measures the pane, so the growth animates for free.
     *
     * A year on its own is a valid check-in, which is what makes "In 2026"
     * offerable at all.
     */
    _renderCheckIn() {
        const answered = this._answeredBy;
        return html`
            <div class="pane-header">
                <button type="button" class="back" @click=${this._backToMain}>
                    <ol-icon class="obd-icon" name="chevron-left"></ol-icon>${this.t('back')}
                </button>
            </div>
            <div class="caption">${this.t('whenFinished')}</div>
            <div class="group" role="group">
                <button
                    type="button"
                    class="row"
                    aria-current=${answered === 'today' ? 'true' : 'false'}
                    ?disabled=${this._dateBusy}
                    @click=${this._onToday}
                >
                    <ol-icon class="obd-icon" name="calendar-check"></ol-icon>
                    <span class="label">${this.t('today')}</span>
                    ${answered === 'today' ? html`<ol-icon class="obd-icon trail" name="check"></ol-icon>` : nothing}
                </button>
                ${quickYears().map(year => html`
                    <button
                        type="button"
                        class="row year"
                        aria-current=${answered === String(year) ? 'true' : 'false'}
                        ?disabled=${this._dateBusy}
                        @click=${() => this._onYear(year)}
                    >
                        <ol-icon class="obd-icon" name="calendar"></ol-icon>
                        <span class="label">${this.t('inYear', { year })}</span>
                        ${answered === String(year) ? html`<ol-icon class="obd-icon trail" name="check"></ol-icon>` : nothing}
                    </button>
                `)}
                <button
                    type="button"
                    class="row date-toggle"
                    aria-current=${answered === 'other' ? 'true' : 'false'}
                    aria-expanded=${this._pickingDate}
                    aria-controls="date-fields"
                    ?disabled=${this._dateBusy}
                    @click=${this._toggleDatePicker}
                >
                    <ol-icon class="obd-icon" name="calendar-days"></ol-icon>
                    <span class="label">${this.t('otherDate')}</span>
                    ${answered === 'other' ? html`<span class="count">${formatReadDate(this.readDate)}</span>` : nothing}
                    <ol-icon class="obd-icon trail" name="chevron-down"></ol-icon>
                </button>
            </div>
            ${this._pickingDate ? this._renderDateFields() : nothing}
        `;
    }

    /** Year → month → day, each enabled by the one before it. */
    _renderDateFields() {
        const { year, month, day } = this._date;
        const thisYear = new Date().getFullYear();
        const years = Array.from({ length: 121 }, (_, i) => thisYear - i);
        const days = month ? new Date(Number(year), Number(month), 0).getDate() : 31;
        return html`
            <form
                id="date-fields"
                class="date-form"
                @submit=${this._onSaveDate}
                @keydown=${e => { if (e.key === 'Escape') { e.stopPropagation(); this._toggleDatePicker(); } }}
            >
                <!-- Selection rides on each option's .selected rather than the
                     select's .value: Lit commits the select's own bindings
                     before its children, so a .value set from a seeded date
                     lands on an empty select and is dropped. -->
                <div class="date-fields">
                    <select class="select year" aria-label=${this.t('year')} @change=${e => this._setDatePart('year', e.target.value)}>
                        <option value="" .selected=${!year}>${this.t('year')}</option>
                        ${years.map(y => html`<option value=${y} .selected=${String(y) === year}>${y}</option>`)}
                    </select>
                    <select class="select" aria-label=${this.t('month')} ?disabled=${!year} @change=${e => this._setDatePart('month', e.target.value)}>
                        <option value="" .selected=${!month}>${this.t('month')}</option>
                        ${MONTHS().map((name, i) => html`<option value=${i + 1} .selected=${String(i + 1) === month}>${name}</option>`)}
                    </select>
                    <select class="select" aria-label=${this.t('day')} ?disabled=${!month} @change=${e => this._setDatePart('day', e.target.value)}>
                        <option value="" .selected=${!day}>${this.t('day')}</option>
                        ${Array.from({ length: days }, (_, i) => i + 1).map(d => html`<option value=${d} .selected=${String(d) === day}>${d}</option>`)}
                    </select>
                </div>
                <div class="date-actions">
                    <ol-button type="submit" variant="primary" size="small" ?disabled=${!year || this._dateBusy}>${this.t('saveDate')}</ol-button>
                </div>
            </form>
        `;
    }

    _renderLists() {
        return html`
            <div class="lists-header">
                <button type="button" class="back" @click=${this._backToMain}>
                    <ol-icon class="obd-icon" name="chevron-left"></ol-icon>${this.t('back')}
                </button>
                ${this._creating ? nothing : html`
                    <ol-button size="small" @click=${this._startCreate}>
                        <ol-icon slot="icon-start" name="plus"></ol-icon>${this.t('createList')}
                    </ol-button>
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
                    <ol-button type="submit" variant="primary" size="small" ?disabled=${this._createBusy}>${this.t('create')}</ol-button>
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
            return html`<div class="loading" role="status"><ol-icon class="obd-icon spinner" name="loader"></ol-icon>${this.t('loadingLists')}</div>`;
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

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('ol-list-created', this._onListCreatedElsewhere);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._resizeObserver?.disconnect();
        document.removeEventListener('ol-list-created', this._onListCreatedElsewhere);
    }

    /**
     * A list created elsewhere on the page — a sibling popover or the legacy
     * dropper — folded into this popover's pane so it stays honest without a
     * refetch. Legacy creations also drop the shared cache: popovers that have
     * not loaded yet must not resolve from a promise that predates the list.
     */
    _onListCreatedElsewhere = (e) => {
        if (e.target === this) return;
        const { key, name, seedKey } = e.detail || {};
        if (!key) return;
        if (e.target?.tagName !== 'OL-BOOK-ACTIONS') resetListsCache();
        if (this._lists && !(key in this._lists)) {
            this._lists = { [key]: { listName: name, members: seedKey ? [seedKey] : [] }, ...this._lists };
        }
    };

    /** Size the track to the active pane so the panel doesn't stretch to the taller one. */
    _syncTrackHeight() {
        const pane = this.shadowRoot.querySelector(`.pane:nth-child(${this._paneIndex + 1})`);
        // 0 means the popover is hidden; keep the last real height.
        if (pane?.offsetHeight) this._trackHeight = pane.offsetHeight;
    }

    // ── Popover lifecycle ────────────────────────────────────

    _onOpen() {
        this._pane = 'main';
        this._snap = false;
        this._creating = false;
        this._pickingDate = false;
        this._listFilter = '';
        // Prefetch so the "in N lists" count is right on the first open, not
        // only after a trip to the lists pane. One request per page — every
        // popover shares `_listsPromise`.
        if (this.userKey) this._loadLists({ quiet: true });
    }

    _onCloseRequest(e) {
        // Escape from a sub-pane goes back a step instead of closing.
        if (e.detail?.reason === 'escape' && this._pane !== 'main') {
            e.preventDefault();
            this._backToMain();
            return;
        }
        // Reset to the main pane now, so the next open doesn't slide back from
        // the lists pane. `snap` skips the slide while the popover fades out.
        this._snap = true;
        this._pane = 'main';
        this._creating = false;
        this._pickingDate = false;
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
        // Already Read leads to the date pane — that is what its chevron says,
        // and it is the only way to change a date once given. Coming off the
        // shelf is the main button's job.
        if (shelfId === SHELF.ALREADY_READ && previous === SHELF.ALREADY_READ) {
            return this._openCheckIn();
        }
        const removing = previous === shelfId;
        this.shelf = removing ? null : shelfId;
        this._busy = true;
        try {
            // Posting the current shelf toggles it off server-side.
            await setShelf(this.book.key, shelfId, { editionKey: this.book.editionKey });
            trackEvent('ReadingLog', removing ? 'RemoveFromShelf' : SHELF_EVENT[shelfId]);
            this._emitState();
            // Only on the way in, and only when they chose the shelf themselves:
            // rating moves a book to Already Read too, and interrupting that
            // would turn one tap into two.
            if (!removing && shelfId === SHELF.ALREADY_READ && previous !== SHELF.ALREADY_READ) {
                this._openCheckIn();
            }
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
            trackEvent('StarRating', next ? 'BookRated' : 'RatingCleared');
            this._emitState();
        } catch (error) {
            this.rating = previous;
            this.shelf = previousShelf;
            this._fail(error);
        } finally {
            this._busy = false;
        }
    }

    // ── Check-in ─────────────────────────────────────────────

    async _openCheckIn() {
        this._pane = 'checkIn';
        // A date the shortcuts cannot express would otherwise sit unseen
        // behind a collapsed row, so the pane opens on it. Focus still lands
        // on the first row: the reader is being shown their answer, not asked
        // to retype it.
        this._pickingDate = this._answeredBy === 'other';
        // Seeded from the date already given, so "Other date" opens on it
        // rather than making the reader re-enter what they are amending.
        const [year = '', month = '', day = ''] = (this.readDate || '').split('-');
        this._date = { year, month: month.replace(/^0/, ''), day: day.replace(/^0/, '') };
        await this.updateComplete;
        this.shadowRoot.querySelector(`.pane:nth-child(${PANES.indexOf('checkIn') + 1}) .row`)?.focus({ preventScroll: true });
    }

    /** Focus follows the disclosure: into the selects, and back to the row on collapse. */
    async _toggleDatePicker() {
        this._pickingDate = !this._pickingDate;
        await this.updateComplete;
        const target = this._pickingDate ? '.select.year' : '.date-toggle';
        this.shadowRoot.querySelector(target)?.focus({ preventScroll: true });
    }

    /** Clearing a coarser part clears the finer ones, which the selects disable. */
    _setDatePart(part, value) {
        const next = { ...this._date, [part]: value };
        if (part === 'year' && !value) next.month = next.day = '';
        if (part === 'month') next.day = value ? next.day : '';
        this._date = next;
    }

    _onToday() {
        const now = new Date();
        return this._saveCheckIn({ year: now.getFullYear(), month: now.getMonth() + 1, day: now.getDate() });
    }

    _onYear(year) {
        return this._saveCheckIn({ year });
    }

    _onSaveDate(e) {
        e.preventDefault();
        const { year, month, day } = this._date;
        if (!year) return;
        return this._saveCheckIn({
            year: Number(year),
            month: month ? Number(month) : null,
            day: day ? Number(day) : null,
        });
    }

    async _saveCheckIn(date) {
        if (this._dateBusy) return;
        this._dateBusy = true;
        try {
            const saved = await setCheckIn(this.book.key, { ...date, editionKey: this.book.editionKey, eventId: this.eventId });
            trackEvent('CheckInPrompt', date.day ? 'SetDateDay' : date.month ? 'SetDateMonth' : 'SetDateYear');
            this.dispatchEvent(new CustomEvent('ol-book-check-in', {
                bubbles: true,
                composed: true,
                detail: { key: this.book.key, date: partialDate(date), eventId: saved?.id ?? this.eventId ?? null },
            }));
            this._backToMain();
        } catch (error) {
            this._fail(error);
        } finally {
            this._dateBusy = false;
        }
    }

    // ── Lists ────────────────────────────────────────────────

    async _openLists() {
        this._pane = 'lists';
        await this.updateComplete;
        this.shadowRoot.querySelector(`.pane:nth-child(${PANES.indexOf('lists') + 1}) .input`)?.focus({ preventScroll: true });
        this._loadLists();
    }

    async _backToMain() {
        this._pane = 'main';
        this._creating = false;
        this._pickingDate = false;
        await this.updateComplete;
        this.shadowRoot.querySelector('.pane:nth-child(1) .group:last-child .row')?.focus({ preventScroll: true });
    }

    /** How many of the user's (loaded) lists contain this book. */
    get _listCount() {
        if (!this._lists) return 0;
        return Object.values(this._lists).filter(l => l.members.includes(this._seedKey)).length;
    }

    /** `quiet` is for the open-time prefetch: no toast, no login bounce. */
    async _loadLists({ quiet = false } = {}) {
        if (this._lists !== null && !this._listsLoading) return;
        this._listsLoading = true;
        try {
            _listsPromise ||= fetchUserLists();
            this._lists = await _listsPromise;
        } catch (error) {
            _listsPromise = null;
            // Leave `_lists` null so opening the pane retries and reports.
            if (quiet) return;
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
            trackEvent('Lists', checked ? 'AddSeed' : 'RemoveSeed');
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
            trackEvent('Lists', 'CreateList');
            // Prepend so the new list is visible immediately. Sibling popovers
            // and the legacy dropper hear about it through `ol-list-created`.
            this._lists = { [created.key]: { listName: name, members: [this._seedKey] }, ...this._lists };
            _listsPromise = Promise.resolve(this._lists);
            this._creating = false;
            this.dispatchEvent(new CustomEvent('ol-list-created', {
                bubbles: true,
                composed: true,
                detail: { key: created.key, name, seedKey: this._seedKey },
            }));
        } catch (error) {
            this._fail(error);
        } finally {
            this._createBusy = false;
        }
    }
}

customElements.define('ol-book-actions', OlBookActions);
