import { LitElement, html, css, nothing } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { styleMap } from 'lit/directives/style-map.js';
import { ifDefined } from 'lit/directives/if-defined.js';
import { repeat } from 'lit/directives/repeat.js';
import './OlIcon.js';
import { SHELF, SHELF_LABEL, SHELF_EVENT, setShelf, setRating, setCheckIn, deleteCheckIn, redirectToLogin } from './utils/books-api.js';
import { getLists, subscribeToLists, loadLists, toggleListSeed, createUserList } from './utils/lists-store.js';
import { getRecentLists, noteListUsed } from './utils/recent-lists.js';
import { FILTER_THRESHOLD } from './utils/filter-threshold.js';
import { MONTHS, formatReadDate, quickYears, partialDate } from './utils/dates.js';
import { showToast } from './OlToastRegion.js';
import { trackEvent } from '../../plugins/openlibrary/js/ol.analytics.js';
import { translate } from './utils/labels.js';
import './OlPopover.js';
import './OLButton.js';

export const DEFAULT_LABELS = {
    actionsFor: 'Actions for %(title)s',
    wantToRead: 'Want to Read',
    currentlyReading: 'Currently Reading',
    alreadyRead: 'Already Read',
    stoppedReading: 'Stopped Reading',
    removeFromShelf: 'Remove from shelf',
    rateThisBook: 'Rate this book',
    rateStar: 'Rate %(rating)s of 5',
    clearRating: 'Clear rating',
    addToList: 'Add to list',
    back: 'Back',
    createList: 'Create a list',
    listName: 'List name',
    create: 'Create',
    filterLists: 'Filter lists…',
    createFirstList: 'Create your first list',
    noMatchingLists: 'No lists match.',
    loadingLists: 'Loading lists…',
    itemsInList: '%(count)s items',
    inLists: 'In %(count)s of your lists',
    recentLists: 'Recently used',
    otherLists: 'Other lists',
    addedToList: 'Added to %(name)s',
    removedFromList: 'Removed from %(name)s',
    errorGeneric: 'Something went wrong. Please try again.',
    whenFinished: 'When did you finish this book?',
    today: 'Today',
    inYear: 'In %(year)s',
    otherDate: 'Other date',
    year: 'Year',
    month: 'Month',
    day: 'Day',
    saveDate: 'Save',
    clearDate: 'Clear date',
};

const SHELF_ICON = {
    [SHELF.WANT_TO_READ]: 'bookmark',
    [SHELF.CURRENTLY_READING]: 'book-open',
    [SHELF.ALREADY_READ]: 'circle-check',
    [SHELF.STOPPED_READING]: 'circle-pause',
};

const SHELF_ROWS = Object.values(SHELF).map((id) => ({ id, icon: SHELF_ICON[id], label: SHELF_LABEL[id] }));

/**
 * Lists needed before the recent ones are pinned to the top. Lower than the
 * shared FILTER_THRESHOLD the field answers to: pinning costs a hairline and
 * starts paying before there is enough to scroll, a filter costs a control.
 */
const PIN_THRESHOLD = 5;

/**
 * The panes in the track, in order. The track's width and slide are both
 * derived from this, so a new pane is an entry here plus a `_render*`.
 */
const PANES = ['main', 'lists', 'checkIn'];

/**
 * Per-book action popover: reading-log shelves, a star rating, and an
 * "Add to list" pane that slides in from the right. Composes `<ol-popover>`
 * for the shell; the caller supplies the trigger.
 *
 * Only for logged-in users — the caller sends logged-out visitors to login
 * instead of rendering this. State is optimistic: the UI updates first and
 * an error toast rolls back.
 *
 * @element ol-shelf-actions
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
 * @fires ol-book-check-in - After a finish date is saved or removed. The
 *     component keeps its own copy (`readDate`/`eventId`); the event is for the
 *     surface to persist it across renders. detail: { key, date, eventId } —
 *     `date` is whole or partial, as stored, and both are null on a removal.
 * @fires ol-list-created - After the inline form creates a list. Sibling
 *     popovers share the lists store and need no event; this is for surfaces
 *     outside the components. detail: { key, name, seedKey }
 *
 * @slot trigger - The button that opens the popover.
 */
export class OlShelfActions extends LitElement {
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
        _listsLoading: { state: true },
        _listsFailed: { state: true },
        _listFilter: { state: true },
        _order: { state: true },
        _recent: { state: true },
        _announce: { state: true },
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
            /* One height for every row, so the panel never shifts as rows
               re-render (the rating caption swaps between a span and a button). */
            min-height: var(--menu-row-height);
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

        /* Except the shelf and date rows: clicking one re-renders it — label
           weight and colour change, a check mark appears — and re-laying out
           mid-scale reads as a flicker. They keep the press fill, not the
           squeeze. */
        .group.shelves .row,
        .group.dates .row,
        .row.shortcut {
            transition: none;
        }

        .group.shelves .row:active,
        .group.dates .row:active,
        .row.shortcut:active {
            transform: none;
        }

        .row:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: -2px;
        }

        /* The shelf a book is on, and the date it was finished on, are the same
           kind of answer — both mark their row the same way. */
        .row[aria-checked="true"],
        .row[aria-current="true"] {
            color: var(--color-link);
            font-weight: 600;
        }

        .row[aria-checked="true"] .obd-icon,
        .row[aria-current="true"] .obd-icon {
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
            box-sizing: border-box;
            height: var(--menu-row-height);
            padding: 0 var(--spacing-inset-md);
        }

        .star-buttons,
        .stars .caption {
            line-height: 1;
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
            /* The check-in pane's .caption padding would push this 16px
               further from the stars than the Clear-rating button sits. */
            padding: 0;
            color: var(--color-text-secondary);
            font-size: var(--font-size-label-medium);
        }

        /* Taking back an answer, shared by Clear rating and Clear date: a quiet
           text link, so it never competes with the rows that give one. Padding
           comes from .caption, which the stars row zeroes out. */
        .clear {
            border: 0;
            background: none;
            color: var(--color-text-secondary);
            font: inherit;
            font-size: var(--font-size-label-medium);
            cursor: pointer;
        }

        .clear:hover {
            color: var(--color-text);
            text-decoration: underline;
        }

        .clear:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            border-radius: var(--border-radius-sm);
        }

        /* The two that stand at the foot of a group rather than beside the
           control they undo: hug the text instead of stretching the column.
           Clear rating is nested in .stars, so it keeps that row's centring. */
        .group > .clear {
            align-self: flex-start;
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

        /* Header and field each hold a small control at most, and swap what
           they show when creating a list; a fixed height keeps the list below
           from jumping when they do. */
        .lists-header,
        .pane-header,
        .field {
            box-sizing: border-box;
            height: calc(var(--control-height-small) + 2 * var(--spacing-inset-sm));
        }

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
            align-items: center;
            gap: var(--spacing-inline-sm);
            padding: 0 var(--spacing-inset-md);
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

        /* iOS zooms in on focus when the field's font is < 16px; bump the
           text field and the date selects up on mobile to suppress that. */
        @media (max-width: 767px) {
            .input,
            .select {
                font-size: var(--font-size-body-large);
            }
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

        /* 16px like the other popover controls, but sitting in a 20px slot so
           it lines up with the main pane's row icons — one row height, one
           label column across both panes. */
        .list-row input {
            width: 16px;
            height: 16px;
            margin-inline: 2px;
            accent-color: var(--color-primary);
            flex: 0 0 auto;
        }

        /* The recent lists, above the rest. Same inset rule as the panel's
           other separators, drawn under the group rather than between rows. */
        .group-lists.pinned {
            position: relative;
            padding-bottom: var(--spacing-inset-xs);
            margin-bottom: var(--spacing-inset-xs);
        }

        .group-lists.pinned::after {
            content: "";
            position: absolute;
            inset-inline: var(--spacing-inset-md);
            bottom: 0;
            height: 1px;
            background: var(--color-border-subtle);
        }

        /* What Enter commits to, marked so the key is never a guess. */
        .list-row.target {
            box-shadow: inset 0 0 0 1px var(--color-border-subtle);
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

        /* Live region: read out, never laid out. */
        .sr-only {
            position: absolute;
            width: 1px;
            height: 1px;
            padding: 0;
            margin: -1px;
            overflow: hidden;
            clip-path: inset(50%);
            white-space: nowrap;
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
        this._warm = false;
        // Capture-phase, so the panes exist before ol-popover's own trigger
        // handling measures the panel.
        this.addEventListener('click', this._warmUp, true);
        this._pane = 'main';
        this._snap = false;
        this._trackHeight = 0;
        this._listsLoading = false;
        this._listsFailed = false;
        this._listFilter = '';
        this._order = [];
        this._recent = [];
        this._announce = '';
        this._creating = false;
        this._createBusy = false;
        this._hoverRating = 0;
        this._busy = false;
        this._pickingDate = false;
        this._dateBusy = false;
        this._date = { year: '', month: '', day: '' };
    }

    get _paneIndex() {
        return PANES.indexOf(this._pane);
    }

    /**
     * Build the pane DOM on the first click that could open the popover.
     * Every book on a page carries one of these, so the three panes and their
     * dozens of nested elements are only built for popovers someone opens.
     * The update must be synchronous: ol-popover positions itself from the
     * panel's measured size before it fires `ol-popover-open`.
     */
    _warmUp = () => {
        if (this._warm) return;
        this._warm = true;
        this.requestUpdate();
        this.performUpdate();
    };

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
                    ${this._warm ? html`
                        <div
                            class="track ${classMap({ snap: this._snap })}"
                            style=${styleMap(track)}
                        >
                            ${PANES.map(name => html`
                                <div class="pane" ?inert=${this._pane !== name}>${this._renderPane(name)}</div>
                            `)}
                        </div>
                    ` : nothing}
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
                <!-- Only Already Read: on the other shelves, clicking the row
                     you are on takes the book off it, but this one's row leads
                     to the date pane, leaving no other way out. -->
                ${this.shelf === SHELF.ALREADY_READ ? html`
                    <button type="button" class="caption clear clear-shelf" ?disabled=${this._busy} @click=${this._removeFromShelf}>${this.t('removeFromShelf')}</button>
                ` : nothing}
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
                ${this._renderRecentShortcut()}
            </div>
        `;
    }

    /**
     * The list the reader was last working in, one tap away. A curation
     * session is many books into the same list, and on mobile the filter
     * costs a tap and a keyboard over the names — so the pane is the slow
     * path there, and this is the whole flow.
     */
    _renderRecentShortcut() {
        const recent = this._recent[0];
        if (!recent) return nothing;
        const list = getLists()?.[recent.key];
        // Loaded lists are the authority on the name and on membership; until
        // they arrive the remembered name carries the row, so the panel does
        // not grow one mid-open. A list that has gone takes the row with it.
        if (getLists() && !list) return nothing;
        const inList = !!list?.members.includes(this._seedKey);
        return html`
            <button
                type="button"
                class="row shortcut"
                role="menuitemcheckbox"
                aria-checked=${inList ? 'true' : 'false'}
                @click=${() => this._onListToggle(recent.key, !inList)}
            >
                <!-- Not the entry row's list-plus: two rows with one icon read
                     as two ways to do the same thing. -->
                <ol-icon class="obd-icon" name="list"></ol-icon>
                <span class="label">${list?.listName || recent.name}</span>
                ${inList ? html`<ol-icon class="obd-icon trail" name="check"></ol-icon>` : nothing}
            </button>
        `;
    }

    /**
     * The end of a shelf row. Already Read carries a chevron, because it leads
     * to the date pane; the others only mark the shelf the book is on.
     *
     * The date rides along only while the book is actually on that shelf. A
     * move keeps the check-in — only coming off the shelves entirely deletes it
     * — so a book moved to, say, Currently Reading still has a finish date, and
     * showing it against a shelf the book has left reads as the wrong state.
     * The date pane still opens on it, which is where it belongs.
     */
    _renderShelfTrail(row) {
        if (row.id === SHELF.ALREADY_READ) {
            const onShelf = this.shelf === SHELF.ALREADY_READ;
            return html`
                ${this.readDate && onShelf ? html`<span class="count">${formatReadDate(this.readDate)}</span>` : nothing}
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
            <div class="group dates" role="group">
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
                ${this._pickingDate ? this._renderDateFields() : nothing}
                ${this.readDate ? html`
                    <button type="button" class="caption clear clear-date" ?disabled=${this._dateBusy} @click=${this._clearDate}>${this.t('clearDate')}</button>
                ` : nothing}
            </div>
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
        const creating = this._creating || this._firstList;
        return html`
            <div class="lists-header">
                <button type="button" class="back" @click=${this._backToMain}>
                    <ol-icon class="obd-icon" name="chevron-left"></ol-icon>${this.t('back')}
                </button>
                ${creating ? nothing : html`
                    <ol-button size="small" @click=${this._startCreate}>
                        <ol-icon slot="icon-start" name="plus"></ol-icon>${this.t('createList')}
                    </ol-button>
                `}
            </div>
            ${creating ? html`
                ${this._firstList ? html`<div class="caption">${this.t('createFirstList')}</div>` : nothing}
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
            ` : this._listTotal > FILTER_THRESHOLD ? html`
                <div class="field">
                    <input
                        class="input"
                        type="search"
                        placeholder=${this.t('filterLists')}
                        aria-label=${this.t('filterLists')}
                        .value=${this._listFilter}
                        @input=${e => { this._listFilter = e.target.value; }}
                        @keydown=${this._onFilterKeydown}
                    />
                </div>
            ` : nothing}
            <div class="list-items">${this._renderListItems()}</div>
            <span class="sr-only" role="status">${this._announce}</span>
        `;
    }

    _renderListItems() {
        const lists = getLists();
        if (this._listsLoading || (lists === null && !this._listsFailed)) {
            return html`<div class="loading" role="status"><ol-icon class="obd-icon spinner" name="loader"></ol-icon>${this.t('loadingLists')}</div>`;
        }
        // No lists at all: the create form above is the whole pane.
        if (!Object.keys(lists || {}).length) return nothing;
        const { pinned, rest } = this._visibleKeys(lists);
        if (!pinned.length && !rest.length) return html`<div class="empty">${this.t('noMatchingLists')}</div>`;
        // The first row is what Enter toggles, and says so once there is a
        // filter to have typed; without one, Enter has no obvious target.
        const target = this._listFilter.trim() ? (pinned[0] ?? rest[0]) : null;
        if (!pinned.length) return this._renderListRows(lists, rest, target);
        const group = (keys, label, isPinned) => html`
            <div class="group-lists ${classMap({ pinned: isPinned })}" role="group" aria-label=${this.t(label)}>
                ${this._renderListRows(lists, keys, target)}
            </div>
        `;
        // The rule under the pinned group is a separator, so it needs both
        // sides; a filter that matched only recents leaves the rows plain.
        return html`
            ${group(pinned, 'recentLists', rest.length > 0)}
            ${rest.length ? group(rest, 'otherLists', false) : nothing}
        `;
    }

    _renderListRows(lists, keys, target) {
        // Filtering shuffles which list sits at each index, so key the rows
        // to keep Lit from rebuilding them; the other lists in this file are
        // static and fine with index reconciliation.
        return repeat(keys, key => key, key => {
            const list = lists[key];
            const checked = list.members.includes(this._seedKey);
            return html`
                <label class="list-row ${classMap({ target: key === target })}">
                    <input type="checkbox" .checked=${checked} @change=${e => this._onListToggle(key, e.target.checked)} />
                    <span class="name">${list.listName}</span>
                    <span class="count" aria-label=${this.t('itemsInList', { count: list.members.length })}>${list.members.length}</span>
                </label>
            `;
        });
    }

    willUpdate(changed) {
        // The surface can take the book off its shelf without us — the split
        // button's main click does — and that deletes the check-ins too, so drop
        // the date we are holding rather than amend a deleted event.
        if (changed.has('shelf') && changed.get('shelf') && !this.shelf) {
            this.readDate = null;
            this.eventId = null;
        }
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
        // The store notifies on every lists change, wherever it was made, so
        // a create or toggle in a sibling popover re-renders this one too.
        this._unsubscribeLists = subscribeToLists(() => this.requestUpdate());
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._resizeObserver?.disconnect();
        this._unsubscribeLists?.();
    }

    /** Size the track to the active pane so the panel doesn't stretch to the taller one. */
    _syncTrackHeight() {
        const pane = this.shadowRoot.querySelector(`.pane:nth-child(${this._paneIndex + 1})`);
        // 0 means the popover is hidden; keep the last real height.
        if (pane?.offsetHeight) this._trackHeight = pane.offsetHeight;
    }

    // ── Popover lifecycle ────────────────────────────────────

    _onOpen() {
        this._warmUp(); // for opens that arrive without a click
        this._pane = 'main';
        this._snap = false;
        this._creating = false;
        this._pickingDate = false;
        this._listFilter = '';
        this._announce = '';
        this._snapshotLists();
        // Prefetch so the "in N lists" count is right on the first open, not
        // only after a trip to the lists pane. One request per page — every
        // popover reads the shared lists store.
        if (this.userKey) this._loadLists({ quiet: true }).then(() => this._snapshotLists());
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
        if (error?.status === 401) return redirectToLogin();
        showToast(this.t('errorGeneric'), { type: 'error' });
    }

    /**
     * Applies `optimistic` to our own state, runs `action`, and puts every
     * property it touched back if that throws — rolling back from a snapshot is
     * what keeps a handler from restoring one property and forgetting another.
     * The busy flag both disables the rows and drops a click that beats the
     * re-render.
     */
    async _mutate(optimistic, action) {
        if (this._busy) return;
        const snapshot = Object.fromEntries(Object.keys(optimistic).map(key => [key, this[key]]));
        Object.assign(this, optimistic);
        this._busy = true;
        try {
            await action();
        } catch (error) {
            Object.assign(this, snapshot);
            this._fail(error);
        } finally {
            this._busy = false;
        }
    }

    // ── Shelves ──────────────────────────────────────────────

    async _onShelfClick(shelfId) {
        const previous = this.shelf;
        // Already Read leads to the date pane — that is what its chevron says,
        // and it is the only way to change a date once given. Coming off the
        // shelf is the "Remove from shelf" link's job, which is why that link
        // is offered on this shelf alone.
        if (shelfId === SHELF.ALREADY_READ && previous === SHELF.ALREADY_READ) {
            return this._openCheckIn();
        }
        return this._postShelf(shelfId);
    }

    /** Takes the book off whichever shelf it is on. Also what the main button does. */
    _removeFromShelf() {
        if (this.shelf) return this._postShelf(this.shelf);
    }

    /** Posting the current shelf toggles it off server-side; any other shelf moves the book. */
    async _postShelf(shelfId) {
        const previous = this.shelf;
        const removing = previous === shelfId;
        // Coming off a shelf deletes the book's check-in events with it, so the
        // date goes too — a kept event id would make the next check-in amend an
        // event the server no longer has, and 404.
        return this._mutate(removing ? { shelf: null, readDate: null, eventId: null } : { shelf: shelfId }, async() => {
            await setShelf(this.book.key, shelfId, { editionKey: this.book.editionKey });
            trackEvent('ReadingLog', SHELF_EVENT[removing ? null : shelfId]);
            this._emitState();
            // Only on the way in, and only when they chose the shelf themselves:
            // rating moves a book to Already Read too, and interrupting that
            // would turn one tap into two.
            if (!removing && shelfId === SHELF.ALREADY_READ && previous !== SHELF.ALREADY_READ) {
                this._openCheckIn();
            }
        });
    }

    // ── Rating ───────────────────────────────────────────────

    async _onRate(n) {
        const next = this.rating === n ? null : n;
        // Mirrors the server, which moves a rated book to Already Read only when
        // it is unshelved or on Want to Read — Currently Reading and Stopped
        // Reading are explicit choices it will not overwrite.
        const autoShelves = !this.shelf || this.shelf === SHELF.WANT_TO_READ;
        const optimistic = next && autoShelves ? { rating: next, shelf: SHELF.ALREADY_READ } : { rating: next };
        return this._mutate(optimistic, async() => {
            await setRating(this.book.key, next, { editionKey: this.book.editionKey });
            trackEvent('StarRating', next ? 'BookRated' : 'RatingCleared');
            this._emitState();
        });
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
            // Keep our own copy so the main pane's Already Read row shows the
            // date, and re-saving amends this event instead of adding one.
            this.readDate = partialDate(date);
            this.eventId = saved?.id ?? this.eventId ?? null;
            trackEvent('CheckInPrompt', date.day ? 'SetDateDay' : date.month ? 'SetDateMonth' : 'SetDateYear');
            this.dispatchEvent(new CustomEvent('ol-book-check-in', {
                bubbles: true,
                composed: true,
                detail: { key: this.book.key, date: this.readDate, eventId: this.eventId },
            }));
            this._backToMain();
        } catch (error) {
            this._fail(error);
        } finally {
            this._dateBusy = false;
        }
    }

    /**
     * Unanswers the question, leaving the book on the shelf: the pane asks it
     * again next time. Deleting the event is the only way back to no date —
     * every other row here replaces one date with another.
     */
    async _clearDate() {
        if (this._dateBusy || !this.eventId) return;
        this._dateBusy = true;
        try {
            await deleteCheckIn(this.eventId);
            this.readDate = null;
            this.eventId = null;
            trackEvent('CheckInPrompt', 'ClearDate');
            this.dispatchEvent(new CustomEvent('ol-book-check-in', {
                bubbles: true,
                composed: true,
                detail: { key: this.book.key, date: null, eventId: null },
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
        const landed = this._focusListsPane();
        const loading = this._loadLists();
        if (landed) return;
        // Nothing to land on while the lists were still coming in. What the
        // pane leads with is decided by how many there turn out to be, so try
        // again once it knows.
        await loading;
        await this.updateComplete;
        if (this._pane === 'lists') this._focusListsPane();
    }

    /**
     * Desktop lands on whatever the pane leads with — the filter, the name
     * field of the create form, or the first list. On mobile (ol-popover's
     * tray breakpoint) a text field would raise the soft keyboard over the
     * lists they came here to see, so take the back button instead; the pane
     * the focus came from is inert now and would strand it.
     */
    _focusListsPane() {
        const pane = `.pane:nth-child(${PANES.indexOf('lists') + 1})`;
        const mobile = window.matchMedia('(max-width: 767px)').matches;
        // A selector list matches the first of them in document order, and the
        // fields both sit above the rows.
        const target = mobile ? '.back' : '.input, .list-row input';
        const el = this.shadowRoot.querySelector(`${pane} ${target}`);
        el?.focus({ preventScroll: true });
        return !!el;
    }

    async _backToMain() {
        this._pane = 'main';
        this._creating = false;
        this._pickingDate = false;
        await this.updateComplete;
        this.shadowRoot.querySelector('.pane:nth-child(1) .group:last-child .row')?.focus({ preventScroll: true });
    }

    /**
     * Freeze the order the lists are shown in, and which of them count as
     * recent, for as long as the popover stays open. Adding to a list moves it
     * to the front of the store; taking the order live would move the row the
     * reader just used out from under the one they are reaching for next.
     */
    _snapshotLists() {
        this._order = Object.keys(getLists() || {});
        this._recent = getRecentLists(this.userKey);
    }

    /**
     * The snapshot, minus lists that have gone and with anything the store has
     * gained since in front — a list created here or in a sibling popover
     * belongs at the top, which is where the store puts it.
     */
    _orderedKeys(lists) {
        const seen = new Set(this._order);
        return [
            ...Object.keys(lists).filter(key => !seen.has(key)),
            ...this._order.filter(key => key in lists),
        ];
    }

    /** The recent lists worth pinning above the rest: still real, and enough lists to matter. */
    _pinnedKeys(lists) {
        if (this._listTotal < PIN_THRESHOLD) return [];
        return this._recent.map(entry => entry.key).filter(key => key in lists);
    }

    /**
     * The list keys the pane shows, in render order and under the filter.
     * Shared with the Enter handler, so what it toggles is always the row the
     * reader can see is first.
     */
    _visibleKeys(lists) {
        const filter = this._listFilter.trim().toLowerCase();
        const keep = key => !filter || lists[key].listName.toLowerCase().includes(filter);
        const pinned = this._pinnedKeys(lists).filter(keep);
        const seen = new Set(pinned);
        return { pinned, rest: this._orderedKeys(lists).filter(key => !seen.has(key) && keep(key)) };
    }

    /** How many lists the reader has, once they are in. */
    get _listTotal() {
        return Object.keys(getLists() || {}).length;
    }

    /** Loaded, and there are none — so the pane opens on the create form. */
    get _firstList() {
        return getLists() !== null && !this._listTotal;
    }

    /** How many of the user's (loaded) lists contain this book. */
    get _listCount() {
        const lists = getLists();
        if (!lists) return 0;
        return Object.values(lists).filter(l => l.members.includes(this._seedKey)).length;
    }

    /** `quiet` is for the open-time prefetch: no toast, no login bounce. */
    async _loadLists({ quiet = false } = {}) {
        if (getLists()) return;
        this._listsLoading = true;
        try {
            await loadLists();
            this._listsFailed = false;
        } catch (error) {
            // A quiet failure keeps the pane on its spinner, so opening it
            // retries and reports.
            if (quiet) return;
            this._listsFailed = true;
            this._fail(error);
        } finally {
            this._listsLoading = false;
        }
    }

    async _onListToggle(listKey, checked) {
        const name = getLists()?.[listKey]?.listName || '';
        try {
            // The store applies the change optimistically and rolls it back
            // for us on failure.
            await toggleListSeed(listKey, this._seedKey, checked);
            // Either way round the reader is working in this list: taking a
            // book back out is as good a signal as putting one in.
            noteListUsed(this.userKey, listKey, name);
            trackEvent('Lists', checked ? 'AddSeed' : 'RemoveSeed');
        } catch (error) {
            this._fail(error);
        }
    }

    /**
     * Enter toggles the first row, so a filtered add is type-and-commit with
     * no reach for the mouse. Focus stays in the field, which is where the
     * next book's three characters go — and where nothing announces the row
     * that changed, hence the live region.
     */
    _onFilterKeydown(e) {
        if (e.key !== 'Enter') return;
        e.preventDefault();
        const lists = getLists();
        if (!lists || !this._listFilter.trim()) return;
        const { pinned, rest } = this._visibleKeys(lists);
        const key = pinned[0] ?? rest[0];
        if (!key) return;
        const name = lists[key].listName;
        const checked = !lists[key].members.includes(this._seedKey);
        this._announce = this.t(checked ? 'addedToList' : 'removedFromList', { name });
        this._onListToggle(key, checked);
    }

    async _startCreate() {
        this._creating = true;
        await this.updateComplete;
        this.shadowRoot.querySelector('form.field .input')?.focus({ preventScroll: true });
    }

    async _cancelCreate() {
        // With no lists the pane is the form; there is nothing to cancel back to.
        if (this._firstList) return this._backToMain();
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
            // The store prepends the new list, so every popover shows it first.
            const key = await createUserList(this.userKey, name, this._seedKey);
            // A list made mid-session is the one about to be filled. It renders
            // first without any help: the snapshot has never seen the key.
            noteListUsed(this.userKey, key, name);
            trackEvent('Lists', 'CreateList');
            this._creating = false;
            this.dispatchEvent(new CustomEvent('ol-list-created', {
                bubbles: true,
                composed: true,
                detail: { key, name, seedKey: this._seedKey },
            }));
        } catch (error) {
            this._fail(error);
        } finally {
            this._createBusy = false;
        }
    }
}

customElements.define('ol-shelf-actions', OlShelfActions);
