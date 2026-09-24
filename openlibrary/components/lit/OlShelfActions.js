import { LitElement, html, css, nothing } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { styleMap } from 'lit/directives/style-map.js';
import { ifDefined } from 'lit/directives/if-defined.js';
import { repeat } from 'lit/directives/repeat.js';
import './OlIcon.js';
import { SHELF, SHELF_LABEL, SHELF_ICON, SHELF_EVENT, setShelf, setRating, setCheckIn, deleteCheckIn, redirectToLogin, fetchWorkEditions } from './utils/books-api.js';
import { getLists, subscribeToLists, loadLists, toggleListSeed, createUserList } from './utils/lists-store.js';
import { getRecentLists, noteListUsed } from './utils/recent-lists.js';
import { FILTER_THRESHOLD } from './utils/filter-threshold.js';
import { MONTHS, formatReadDate, quickYears, partialDate } from './utils/dates.js';
import { showToast } from './OlToastRegion.js';
import { trackEvent } from '../../plugins/openlibrary/js/ol.analytics.js';
import { translate } from './utils/labels.js';
import { getNextKeyboardFocusIndex } from './utils/keyboard-nav.js';
import './OlPopover.js';
import './OLButton.js';

export const DEFAULT_LABELS = {
    actionsFor: 'Actions for %(title)s',
    readingLog: 'Reading log',
    wantToRead: 'Want to Read',
    currentlyReading: 'Currently Reading',
    alreadyRead: 'Already Read',
    stoppedReading: 'Stopped Reading',
    // Live-region announcements: a change is confirmed to a screen reader
    // the way the checkmark confirms it on screen.
    addedToShelf: 'Added to %(shelf)s',
    removedFromShelf: 'Removed from shelf',
    rated: 'Rated %(rating)s of 5',
    ratingCleared: 'Rating cleared',
    dateSaved: 'Finished %(date)s',
    dateRemoved: 'Date removed',
    addDate: 'Add date',
    rateThisBook: 'Rate this book',
    rateStar: 'Rate %(rating)s of 5',
    clearRating: 'Clear rating',
    addToList: 'Add to list',
    // A plural set: how many other editions of this book the list already holds.
    otherEditions: { one: '%(count)s other edition', other: '%(count)s other editions' },
    anyEdition: 'Any edition',
    back: 'Back',
    createList: 'Create a list',
    listName: 'List name',
    create: 'Create',
    filterLists: 'Filter lists…',
    createFirstList: 'Create your first list',
    noMatchingLists: 'No lists match.',
    loadingLists: 'Loading lists…',
    // A plural set: the form is picked for `count` by the page language's rules.
    itemsInList: { one: '%(count)s item', other: '%(count)s items' },
    // A plural set: how many of the reader's lists hold this book.
    onLists: { one: 'On %(count)s list', other: 'On %(count)s lists' },
    recentLists: 'Recently used',
    pinnedLists: 'On this book and recently used',
    otherLists: 'Other lists',
    addedToList: 'Added to %(name)s',
    removedFromList: 'Removed from %(name)s',
    manageLists: 'Manage lists',
    errorGeneric: 'Something went wrong. Please try again.',
    whenFinished: 'When did you finish this book?',
    skipDate: 'Skip',
    today: 'Today',
    inYear: 'In %(year)s',
    otherDate: 'Other date',
    year: 'Year',
    month: 'Month',
    day: 'Day',
    saveDate: 'Save',
    removeDate: 'Remove date',
};

const SHELF_ROWS = Object.values(SHELF).map((id) => ({ id, icon: SHELF_ICON[id], label: SHELF_LABEL[id] }));

/**
 * Lists needed before the lists the book is on, and the recent ones, are
 * pinned to the top. Lower than the shared FILTER_THRESHOLD the field answers
 * to: pinning costs a hairline and starts paying before there is enough to
 * scroll, a filter costs a control.
 */
const PIN_THRESHOLD = 5;

/**
 * Recent lists offered on the main pane. A curation burst alternates between
 * one list and maybe a second; a third row is a menu, and the pane is for that.
 */
const SHORTCUT_LIMIT = 2;

/**
 * The panes in the track, in order. The track's width and slide are both
 * derived from this, so a new pane is an entry here plus a `_render*`.
 */
const PANES = ['main', 'lists', 'checkIn'];

/**
 * Work key → promise of its edition keys. Module-level, so several buttons for
 * the same book share one request and re-opening costs nothing.
 */
const EDITION_KEYS = new Map();

/** Forget the cached editions (tests). */
export function resetWorkEditionsCache() {
    EDITION_KEYS.clear();
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
 * @prop {Boolean} pending - The reader's state is not known yet. The shelf and
 *     rating rows dim and ignore clicks until it is: posting the shelf a book
 *     is already on removes it, so a guess could undo a save
 * @prop {Object} labels   - Translated strings (see DEFAULT_LABELS)
 * @prop {String} placement - ol-popover placement; unset uses its default
 * @prop {Boolean} hideRating - Always drop the stars. Without it they go on
 *     their own whenever a visible `.star-rating-form` for the same book is
 *     on the page, checked at each open
 * @prop {Boolean} listsOnly - Only the lists pane, opened straight into: for
 *     a seed with no work to shelve, an author or an edition on its own.
 *     `book.key` is then that seed's key, and its title the heading
 *
 * @fires ol-book-state-change - After a shelf or rating change is accepted by
 *     the server. detail: { key, shelf, rating }
 * @fires ol-book-check-in - After a finish date is saved or removed. The
 *     component keeps its own copy (`readDate`/`eventId`); the event is for
 *     the surface to persist it across renders. detail: { key, date, eventId }
 *     — `date` is whole or partial, as stored, and both are null on removal.
 *     A book coming off its shelf drops its date too, which the surface hears
 *     as ol-book-state-change instead.
 * @fires ol-list-created - After the inline form creates a list. Sibling
 *     popovers share the lists store and need no event; this is for surfaces
 *     outside the components. detail: { key, name, seedKey }
 * @fires ol-list-change - After the book is put in a list or taken out of one.
 *     detail: { key, name, seedKey, member } — `member` is whether it is in the list now
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
        listsOnly: { type: Boolean, attribute: 'lists-only' },
        pending: { type: Boolean, reflect: true },
        _starsElsewhere: { state: true },
        _editionKeys: { state: true },
        _matchPending: { state: true },
        _pane: { state: true },
        _snap: { state: true },
        _trackHeight: { state: true },
        _listsLoading: { state: true },
        _listsFailed: { state: true },
        _listFilter: { state: true },
        _order: { state: true },
        _recent: { state: true },
        _members: { state: true },
        _announce: { state: true },
        _creating: { state: true },
        _createBusy: { state: true },
        _hoverRating: { state: true },
        _busy: { state: true },
        _pickingDate: { state: true },
        _amending: { state: true },
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
        .group.lists-entry::before,
        .group.retract::before {
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
        .group.lists-entry,
        .group.retract {
            position: relative;
        }

        .group.rating::before,
        .group.lists-entry::before,
        .group.retract::before {
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
            margin-inline: var(--menu-row-inset);
            padding-block: var(--spacing-inset-sm);
            padding-inline: var(--menu-row-padding-inline);
            border-radius: var(--border-radius-menu-row);
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

        /* Press feedback — the fill, not the squeeze <ol-button> gives. A row
           has no resting fill, so the press paints one; on touch, where :hover
           never runs, there would otherwise be nothing at all. The scale stays
           with real buttons: a menu row that shrinks reads as the panel
           moving rather than the row being pressed. */
        .row:active,
        .list-row:active {
            background: var(--color-hover-overlay);
        }

        .row:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: -2px;
        }

        /* The shelf a book is on, and the date it was finished on, are the same
           kind of answer — both mark their row the same way. */
        .row[aria-pressed="true"] {
            color: var(--color-link);
            font-weight: 600;
        }

        .row[aria-pressed="true"] .obd-icon {
            color: var(--color-link);
        }

        /* Already Read on the shelf: the label toggles like the other rows,
           the date is a second target into the date pane. Each half keeps its
           own hover pill; the pair takes the inset a single row would. */
        .row-split {
            display: flex;
            margin-inline: var(--menu-row-inset);
        }

        .row-split > .row {
            margin-inline: 0;
        }

        .row-split > .row:first-child {
            flex: 1;
            min-width: 0;
        }

        .date-link {
            flex: 0 1 auto;
            max-width: 50%;
            gap: var(--spacing-inline-xs);
            padding-inline: var(--spacing-inset-sm);
        }

        .date-link .count {
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }


        /* A request in flight dims the group rather than disabling its rows:
           disabling the focused row would drop focus to the document. The
           handlers ignore clicks while busy, so this is feedback only. */
        [aria-busy="true"] .row,
        [aria-busy="true"] .star,
        [aria-busy="true"] .clear {
            cursor: default;
            opacity: 0.6;
        }

        /* Stars */
        .stars {
            display: flex;
            align-items: center;
            gap: var(--spacing-inline-md);
            box-sizing: border-box;
            /* min-height, not height: the 24px star targets and the caption
               have to fit whatever the row height is, and the row has to stay
               level with the shelf rows above it. */
            min-height: var(--menu-row-height);
            padding: 0 var(--spacing-inset-md);
        }

        .star-buttons,
        .stars .caption {
            line-height: 1;
        }

        .star-buttons {
            display: inline-flex;
        }

        /* 24px hit target (WCAG 2.5.8) around a 20px glyph. */
        .star {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 24px;
            height: 24px;
            padding: 0;
            border: 0;
            background: none;
            cursor: pointer;
            line-height: 0;
        }

        /* Sized to the row icons, and only the filled stars carry the gold —
           an all-gold band outweighs the shelves above it. Filled vs. empty is
           the whole rating to a sighted reader, so both sit at 3:1 on white
           (--amber-400 and --color-icon-muted are decorative-tier). */
        .star .obd-icon {
            width: 20px;
            height: 20px;
            color: var(--color-text-muted);
            --ol-icon-stroke-width: 1.5;
        }

        .star .obd-icon[filled] {
            color: var(--amber-500);
        }

        .star:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            border-radius: var(--border-radius-sm);
        }

        .stars .caption {
            /* The check-in pane's .caption padding would push this 16px
               further from the stars than the Clear-rating button sits. */
            padding: 0;
            color: var(--color-text-secondary);
            font-size: var(--font-size-label-medium);
        }

        /* Clear rating: a quiet text link, so it never competes with the stars
           it undoes. Padding comes from .caption, which the stars row zeroes. */
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
            outline: var(--focus-width) solid var(--color-focus-ring);
            border-radius: var(--border-radius-sm);
        }

        /* Check-in pane */

        /* Muted like the question above it: these rows undo an answer rather
           than giving one, so they must not read as more dates to pick. */
        .retract .row {
            color: var(--color-text-secondary);
            font-size: var(--font-size-label-medium);
        }

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
            outline: var(--focus-width) solid var(--color-focus-ring);
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

        /* Lists-only in a split frame: the slotted trigger is the whole
           button, so the popover (its flex parent) must fill the host. */
        :host([lists-only]) ol-popover {
            flex: 1;
            min-width: 0;
        }

        /* Lists-only: the seed's title stands where Back would be. */
        .lists-title {
            min-width: 0;
            overflow: hidden;
            white-space: nowrap;
            text-overflow: ellipsis;
            color: var(--color-text-secondary);
            font-size: var(--font-size-label-medium);
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

        /* Small ghost <ol-button>s. The negative margin pulls the button's own
           padding back so the chevron / label sits flush with the content below. */
        .back,
        .lists-link {
            margin-left: calc(-1 * var(--spacing-sm));
        }

        /* The way out to the lists themselves, below the rows so it is never
           in reach of a tick. Same ghost button as Back, mirrored. */
        .lists-footer {
            position: relative;
            padding: var(--spacing-inset-xs) var(--spacing-inset-md);
        }

        .lists-footer::before {
            content: "";
            position: absolute;
            top: 0;
            inset-inline: var(--spacing-inset-md);
            height: 1px;
            background: var(--color-border-subtle);
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
            outline: var(--focus-width) solid var(--color-focus-ring);
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

        /* Same breathing room off the header rule as the main pane's groups. */
        .list-items {
            max-height: 240px;
            overflow-y: auto;
            padding-block: var(--spacing-inset-xs);
        }

        .list-row {
            position: relative;
            display: flex;
            align-items: center;
            gap: var(--spacing-inline-md);
            margin-inline: var(--menu-row-inset);
            padding-block: var(--spacing-inset-sm);
            padding-inline: var(--menu-row-padding-inline);
            border-radius: var(--border-radius-menu-row);
            cursor: pointer;
        }

        @media (hover: hover) and (pointer: fine) {
            .list-row:hover {
                background: var(--color-hover-overlay);
            }
        }

        /* Plus or check, marked like the main pane's recent-list shortcuts, so
           a list the book is on looks the same in both panes. */
        .list-row .obd-icon {
            width: 20px;
            height: 20px;
            flex: 0 0 20px;
            color: var(--color-icon-muted);
        }

        .list-row.checked {
            color: var(--color-link);
            font-weight: 600;
        }

        .list-row.checked .obd-icon {
            color: var(--color-link);
        }

        /* The annotations describe the list, not the answer. */
        .list-row .count,
        .list-row .other-form {
            font-weight: normal;
        }

        /* The checkbox is hidden, so the row wears its focus. */
        .list-row:has(input:focus-visible) {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: -2px;
        }

        /* What Enter commits to, marked so the key is never a guess. */
        .list-row.target {
            box-shadow: inset 0 0 0 1px var(--color-border-subtle);
        }

        /* Name over label. The name is what the reader is looking for, so it
           keeps the full width and the annotation goes under it rather than
           taking room from it. */
        .list-row .text {
            flex: 1;
            min-width: 0;
            display: flex;
            flex-direction: column;
        }

        .list-row .name {
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .count {
            color: var(--color-text-secondary);
            font-size: var(--font-size-label-medium);
        }

        /* A prompt, not an answer: it must not take the pressed row's weight. */
        .count.hint {
            font-weight: normal;
        }

        .shortcuts {
            display: flex;
            flex-direction: column;
        }

        /* Says the book is on this list already, as another edition or with no
           edition named. Tight leading, so a labelled row grows by one small
           line rather than by a whole row. */
        .list-row .other-form {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            line-height: 1.3;
            color: var(--color-text-secondary);
            font-size: var(--font-size-label-small);
        }

        /* Live region and the list rows' checkboxes: read out, never laid out. */
        .sr-only,
        .list-row input {
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
        this.listsOnly = false;
        this._starsElsewhere = false;
        this._editionKeys = [];
        this._matchPending = false;
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
        this._members = [];
        this._announce = '';
        this._creating = false;
        this._createBusy = false;
        this._hoverRating = 0;
        this._busy = false;
        this.pending = false;
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
        // Checked on every open, not once: a layout toggle can hide or show
        // the row's star form between two opens of the same popover.
        const starsElsewhere = this._findStarsElsewhere();
        const changed = starsElsewhere !== this._starsElsewhere;
        this._starsElsewhere = starsElsewhere;
        if (this._warm && !changed) return;
        this._warm = true;
        this.requestUpdate();
        this.performUpdate();
    };

    /**
     * A visible star form for this book elsewhere on the page makes the
     * popover's stars a second control for the same thing, so they go.
     * `checkVisibility` sees through hidden ancestors; the fallback catches
     * `display: none` on the form itself, which is what the grid layout does.
     */
    _findStarsElsewhere() {
        const key = this.book?.key;
        if (!key) return false;
        return [...document.querySelectorAll(`.star-rating-form[data-work-key="${key}"]`)]
            .some(form => (form.checkVisibility ? form.checkVisibility() : form.getClientRects().length > 0));
    }

    /** Open the popover without a trigger click; the split button's main half does this for a book on a reading shelf. */
    open() {
        this._warmUp();
        const popover = this.shadowRoot?.querySelector('ol-popover');
        if (popover && !popover.open) popover.open = true;
    }

    /** @param {string} name */
    _renderPane(name) {
        if (name === 'lists') return this._renderLists();
        // Lists-only never leaves its pane, so the other two stay empty.
        if (this.listsOnly) return nothing;
        if (name === 'checkIn') return this._renderCheckIn();
        return this._renderMain();
    }

    /** @param {string} key */
    t(key, vars) {
        return translate(this.labels, DEFAULT_LABELS, key, vars);
    }

    /**
     * The key a list records: the edition when the surface knows one, else the
     * work. A list is a shelf of editions, so which edition the reader was looking
     * at is worth keeping — that was the old dropper's default too. A
     * `lists-only` seed (an author, an edition with no work) carries its own
     * key in `book.key` and is never rewritten.
     */
    get _seedKey() {
        const edition = this.book?.editionKey;
        if (!edition || this.listsOnly) return this.book?.key || '';
        return edition.startsWith('/') ? edition : `/books/${edition}`;
    }

    /**
     * The work's other editions, asked for once per book and shared by every
     * popover on the page. A failure resolves to nothing rather than rejecting:
     * the pane then matches on the two keys it already has, which is where it
     * stood before, instead of spinning for an answer that is not coming.
     */
    _loadEditionKeys() {
        const workKey = this.book?.key;
        if (!workKey || this.listsOnly || !workKey.startsWith('/works/')) return null;
        if (!EDITION_KEYS.has(workKey)) {
            EDITION_KEYS.set(workKey, fetchWorkEditions(workKey).catch(() => []));
        }
        return EDITION_KEYS.get(workKey);
    }

    /**
     * Whether the list holds this exact seed — the edition in front of the reader.
     * This is what the checkbox says, and all it ever adds or removes.
     */
    _holdsSeed(list) {
        return !!list && list.members.includes(this._seedKey);
    }

    /**
     * What else of this book the list holds, beside the edition this row is for:
     * `{ kind: 'edition', count }` for other editions of it, `{ kind: 'work' }`
     * for the book with no edition named, or null. Ticking the row adds this
     * edition alongside — some lists collect editions on purpose — so this
     * stands whether the row is ticked or not: before, it is the warning that
     * the book is already here; after, it is the count of editions on the list.
     */
    _otherForm(list) {
        if (!list) return null;
        const count = list.members.filter(key => key !== this._seedKey && this._editionKeys.includes(key)).length;
        if (count) return { kind: 'edition', count };
        if (this.book?.key && this.book.key !== this._seedKey && list.members.includes(this.book.key)) return { kind: 'work' };
        return null;
    }

    /** Whether this book is on the list at all, however it was filed. Counts and pinning ask this. */
    _inList(list) {
        return this._holdsSeed(list) || !!this._otherForm(list);
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
                block-outside-clicks
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
                                <div
                                    class="pane"
                                    ?inert=${this._pane !== name}
                                    role=${name === 'lists' ? 'group' : nothing}
                                    aria-label=${name === 'lists' ? this.t('addToList') : nothing}
                                >${this._renderPane(name)}</div>
                            `)}
                        </div>
                    ` : nothing}
                    <!-- Outside the track: a pane goes inert when it slides
                         away, and a live region inside one would go with it. -->
                    <span class="sr-only" role="status">${this._announce}</span>
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
            <!-- Toggle buttons, not a menu: the panel is a dialog holding
                 several kinds of control, and menuitem roles promise arrow-key
                 navigation the rows don't have. aria-pressed marks the shelf
                 the book is on, which is what the checkmark shows. -->
            <div class="group shelves" role="group" aria-label=${this.t('readingLog')} aria-busy=${this._held}>
                ${SHELF_ROWS.map(row => {
        const toggle = html`
                        <button
                            type="button"
                            class="row"
                            data-shelf=${row.id}
                            aria-pressed=${this.shelf === row.id ? 'true' : 'false'}
                            @click=${() => this._onShelfClick(row.id)}
                        >
                            <ol-icon class="obd-icon" name=${row.icon}></ol-icon>
                            <span class="label">${this.t(row.label)}</span>
                            <!-- Already Read's date half sits where the check would; the pressed color marks it. -->
                            ${this.shelf === row.id && row.id !== SHELF.ALREADY_READ ? html`<ol-icon class="obd-icon trail" name="check"></ol-icon>` : nothing}
                        </button>
                    `;
        // Wrapped whether or not the date shows, so toggling the
        // shelf re-renders neither half and focus stays put.
        return row.id === SHELF.ALREADY_READ
            ? html`<div class="row-split">${toggle}${this._renderDateLink()}</div>`
            : toggle;
    })}
            </div>
            ${this.hideRating || this._starsElsewhere ? nothing : html`
                <div class="group rating" aria-busy=${this._held}>
                    ${this._renderStars()}
                </div>
            `}
            <div class="group lists-entry">
                <button type="button" class="row" @click=${this._openLists}>
                    <ol-icon class="obd-icon" name="list-plus"></ol-icon>
                    <span class="label">${this.t('addToList')}</span>
                    ${this._listCount && !this._matchPending ? html`<span class="count">${this.t('onLists', { count: this._listCount })}</span>` : nothing}
                    <ol-icon class="obd-icon trail" name="chevron-right"></ol-icon>
                </button>
                ${this._renderRecentShortcuts()}
            </div>
        `;
    }

    /**
     * The lists the reader was last working in, one tap away, as shortcuts under
     * "Add to list" rather than headed as a section of their own; the plus or
     * check says what a tap does. A curation session is many books into the same list, and on mobile the
     * filter costs a tap and a keyboard over the names — so the pane is the
     * slow path there, and this is the whole flow.
     */
    _renderRecentShortcuts() {
        const lists = getLists();
        // Loaded lists are the authority on the name and on membership; until
        // they arrive the remembered names carry the rows, so the panel does
        // not grow one mid-open. A list that has gone takes its row with it.
        const rows = this._recent
            .slice(0, SHORTCUT_LIMIT)
            .map(recent => ({ recent, list: lists?.[recent.key] }))
            .filter(({ list }) => !lists || list);
        if (!rows.length) return nothing;
        return html`
            <div class="shortcuts" role="group" aria-label=${this.t('recentLists')}>
                ${rows.map(({ recent, list }) => this._renderRecentShortcut(recent, list))}
            </div>
        `;
    }

    _renderRecentShortcut(recent, list) {
        const inList = this._holdsSeed(list);
        return html`
            <button
                type="button"
                class="row shortcut"
                aria-pressed=${inList ? 'true' : 'false'}
                @click=${() => this._onListToggle(recent.key, !inList)}
            >
                <ol-icon class="obd-icon" name=${inList ? 'check' : 'plus'}></ol-icon>
                <span class="label">${list?.listName || recent.name}</span>
            </button>
        `;
    }

    /**
     * The second half of the Already Read row: the date, or "Add date", leading
     * to the date pane. Its own target, so the shelf half toggles like the other
     * three and the chevron only ever navigates.
     *
     * Only while the book is on the shelf. A move keeps the check-in (only
     * coming off the shelves deletes it), but a finish date shown against a
     * shelf the book has left reads as the wrong state.
     */
    _renderDateLink() {
        if (this.shelf !== SHELF.ALREADY_READ) return nothing;
        const date = this.readDate ? formatReadDate(this.readDate) : null;
        return html`
            <button
                type="button"
                class="row date-link"
                aria-label=${date ? this.t('dateSaved', { date }) : nothing}
                @click=${() => this._openCheckIn({ amending: true })}
            >
                <span class=${date ? 'count' : 'count hint'}>${date ?? this.t('addDate')}</span>
                <ol-icon class="obd-icon trail" name="chevron-right"></ol-icon>
            </button>
        `;
    }

    /**
     * A radio group with one tab stop: Tab lands on the current rating (or the
     * first star), arrows move between stars and preview them the way hover
     * does, Enter or Space commits. Selection does not follow the arrows —
     * every change is a request, and five of them for one keypress-run would
     * race the busy guard.
     */
    _renderStars() {
        const shown = this._hoverRating || this.rating || 0;
        const tabStop = this.rating || 1;
        // Once rated, the caption becomes an actionable "Clear rating" link.
        const caption = this.rating
            ? html`<button type="button" class="caption clear" @click=${() => this._onRate(this.rating)}>${this.t('clearRating')}</button>`
            : html`<span class="caption">${this.t('rateThisBook')}</span>`;
        return html`
            <div class="stars">
                <span
                    class="star-buttons"
                    role="radiogroup"
                    aria-label=${this.t('rateThisBook')}
                    @keydown=${this._onStarKeydown}
                    @mouseleave=${() => { this._hoverRating = 0; }}
                >
                    ${[1, 2, 3, 4, 5].map(n => html`
                        <button
                            type="button"
                            class="star"
                            role="radio"
                            aria-checked=${this.rating === n ? 'true' : 'false'}
                            aria-label=${this.t('rateStar', { rating: n })}
                            tabindex=${n === tabStop ? '0' : '-1'}
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

    _onStarKeydown(e) {
        const stars = [...this.shadowRoot.querySelectorAll('.star')];
        const current = stars.indexOf(e.target);
        if (current === -1) return;
        const target = getNextKeyboardFocusIndex(e.key, { count: stars.length, current, orientation: 'both', wrap: true });
        if (target === -1) return;
        e.preventDefault();
        stars[target].focus();
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
                <ol-button class="back" variant="ghost" size="small" @click=${this._backToMain}>
                    <ol-icon slot="icon-start" name="chevron-left"></ol-icon>${this.t('back')}
                </ol-button>
            </div>
            <!-- The question names the group, so focus landing on a row
                 (which is where the pane opens) is read with it. -->
            <div class="caption" id="check-in-question">${this.t('whenFinished')}</div>
            <div class="group dates" role="group" aria-labelledby="check-in-question" aria-busy=${this._dateBusy}>
                <!-- The date is optional, and Back alone doesn't say so. Only
                     while there is none: with one, Skip would read as clearing it. -->
                ${this.readDate ? nothing : html`
                    <button type="button" class="row skip" @click=${this._onSkipDate}>
                        <ol-icon class="obd-icon" name="arrow-right"></ol-icon>
                        <span class="label">${this.t('skipDate')}</span>
                    </button>
                `}
                <button
                    type="button"
                    class="row today"
                    aria-pressed=${answered === 'today' ? 'true' : 'false'}
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
                        aria-pressed=${answered === String(year) ? 'true' : 'false'}
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
                    aria-pressed=${answered === 'other' ? 'true' : 'false'}
                    aria-expanded=${this._pickingDate}
                    aria-controls=${ifDefined(this._pickingDate ? 'date-fields' : undefined)}
                    @click=${this._toggleDatePicker}
                >
                    <ol-icon class="obd-icon" name="calendar-days"></ol-icon>
                    <span class="label">${this.t('otherDate')}</span>
                    ${answered === 'other' ? html`<span class="count">${formatReadDate(this.readDate)}</span>` : nothing}
                    <ol-icon class="obd-icon trail" name="chevron-down"></ol-icon>
                </button>
                ${this._pickingDate ? this._renderDateFields() : nothing}
            </div>
            <!-- Taking back an answer rather than giving another one, so it
                 stands outside the group the question names. Keeps the shelf:
                 coming off it is the shelf row's job. Only when amending:
                 someone who just chose the shelf is here to date the read. -->
            ${this._amending && this.eventId ? html`<div class="group retract">
                <button type="button" class="row remove-date" @click=${this._onRemoveDate}>
                    <ol-icon class="obd-icon" name="x"></ol-icon>
                    <span class="label">${this.t('removeDate')}</span>
                </button>
            </div>` : nothing}
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
                    <ol-button type="submit" variant="primary" size="small" ?disabled=${!year}>${this.t('saveDate')}</ol-button>
                </div>
            </form>
        `;
    }

    _renderLists() {
        const creating = this._creating || this._firstList;
        return html`
            <div class="lists-header">
                ${this.listsOnly ? html`
                    <span class="lists-title">${this.book.title}</span>
                ` : html`
                    <ol-button class="back" variant="ghost" size="small" @click=${this._backToMain}>
                        <ol-icon slot="icon-start" name="chevron-left"></ol-icon>${this.t('back')}
                    </ol-button>
                `}
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
                        aria-busy=${this._createBusy}
                        @keydown=${e => { if (e.key === 'Escape') { e.stopPropagation(); this._cancelCreate(); } }}
                    />
                    <ol-button type="submit" variant="primary" size="small">${this.t('create')}</ol-button>
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
            ${!this._listTotal || !this.userKey ? nothing : html`
                <div class="lists-footer">
                    <ol-button class="lists-link" variant="ghost" size="small" href=${`${this.userKey}/lists`}>
                        ${this.t('manageLists')}<ol-icon slot="icon-end" name="arrow-right"></ol-icon>
                    </ol-button>
                </div>
            `}
        `;
    }

    _renderListItems() {
        const lists = getLists();
        if (this._listsLoading || this._matchPending || (lists === null && !this._listsFailed)) {
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
        const group = (keys, label) => html`
            <div class="group-lists" role="group" aria-label=${this.t(label)}>
                ${this._renderListRows(lists, keys, target)}
            </div>
        `;
        // The pinned group's label follows what is actually in it, so it never
        // promises rows for this book when there are none.
        const pinnedLabel = pinned.some(key => this._members.includes(key)) ? 'pinnedLists' : 'recentLists';
        return html`
            ${group(pinned, pinnedLabel)}
            ${rest.length ? group(rest, 'otherLists') : nothing}
        `;
    }

    _renderListRows(lists, keys, target) {
        // Filtering shuffles which list sits at each index, so key the rows
        // to keep Lit from rebuilding them; the other lists in this file are
        // static and fine with index reconciliation.
        return repeat(keys, key => key, key => {
            const list = lists[key];
            const checked = this._holdsSeed(list);
            const other = this._otherForm(list);
            return html`
                <label class="list-row ${classMap({ target: key === target, checked })}">
                    <!-- Still a checkbox to assistive tech and the keyboard; the icon is what shows. -->
                    <input type="checkbox" .checked=${checked} @change=${e => this._onListToggle(key, e.target.checked)} />
                    <ol-icon class="obd-icon" name=${checked ? 'check' : 'plus'}></ol-icon>
                    <span class="text">
                        <span class="name">${list.listName}</span>
                        ${other ? html`<span class="other-form">${other.kind === 'edition' ? this.t('otherEditions', { count: other.count }) : this.t('anyEdition')}</span>` : nothing}
                    </span>
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
        this._creating = false;
        this._pickingDate = false;
        this._listFilter = '';
        this._announce = '';
        this._snapshotLists();
        // Lists-only lands on the pane itself, with nothing to slide in from.
        if (this.listsOnly) {
            this._snap = true;
            this._openLists();
            return;
        }
        this._pane = 'main';
        this._snap = false;
        // Prefetch so the "in N lists" count is right on the first open, not
        // only after a trip to the lists pane. One request per page — every
        // popover reads the shared lists store.
        if (this.userKey) this._loadLists({ quiet: true }).then(() => this._snapshotLists());
        // Which editions count as this book is the other half of that answer,
        // so the count and the ticks wait for it rather than show a list the
        // book is already on as empty. The shelf rows stay live throughout.
        const editions = this.userKey && this._loadEditionKeys();
        if (editions) {
            this._matchPending = this._editionKeys.length === 0;
            editions.then(keys => {
                this._editionKeys = keys;
                this._matchPending = false;
                this._snapshotLists();
            });
        }
    }

    _onCloseRequest(e) {
        // Escape from a sub-pane goes back a step instead of closing.
        if (e.detail?.reason === 'escape' && this._pane !== 'main' && !this.listsOnly) {
            e.preventDefault();
            this._backToMain();
            return;
        }
        // Reset to the main pane now, so the next open doesn't slide back from
        // the lists pane. `snap` skips the slide while the popover fades out.
        this._snap = true;
        this._pane = this.listsOnly ? 'lists' : 'main';
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
     * Read `message` out through the live region. Cleared first so the same
     * message twice running still counts as a change — Lit would otherwise
     * leave the text node alone and nothing would be spoken.
     */
    async _say(message) {
        this._announce = '';
        await this.updateComplete;
        this._announce = message;
    }

    /**
     * Applies `optimistic` to our own state, runs `action`, and puts every
     * property it touched back if that throws — rolling back from a snapshot is
     * what keeps a handler from restoring one property and forgetting another.
     * The busy flag dims the rows and drops a click that beats the re-render.
     * `announce` is spoken with the optimistic change, as the checkmark is
     * shown with it; a rollback is announced by the error toast.
     */
    /** No shelf or rating change while one is in flight, or before the state is known. */
    get _held() {
        return this._busy || this.pending;
    }

    async _mutate(optimistic, action, announce) {
        if (this._held) return;
        const snapshot = Object.fromEntries(Object.keys(optimistic).map(key => [key, this[key]]));
        Object.assign(this, optimistic);
        if (announce) this._say(announce);
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

    /** Every shelf row toggles; Already Read's date has its own target (`_renderDateLink`). */
    _onShelfClick(shelfId) {
        return this._postShelf(shelfId);
    }

    /** Posting the current shelf toggles it off server-side; any other shelf moves the book. */
    async _postShelf(shelfId) {
        const previous = this.shelf;
        const removing = previous === shelfId;
        // Coming off a shelf deletes the book's check-in events with it, so the
        // date goes too — a kept event id would make the next check-in amend an
        // event the server no longer has, and 404.
        const announce = removing
            ? this.t('removedFromShelf')
            : this.t('addedToShelf', { shelf: this.t(SHELF_LABEL[shelfId]) });
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
        }, announce);
    }

    // ── Rating ───────────────────────────────────────────────

    async _onRate(n) {
        const next = this.rating === n ? null : n;
        // Mirrors the server, which moves a rated book to Already Read only when
        // it is unshelved or on Want to Read — Currently Reading and Stopped
        // Reading are explicit choices it will not overwrite.
        const autoShelves = !this.shelf || this.shelf === SHELF.WANT_TO_READ;
        const optimistic = next && autoShelves ? { rating: next, shelf: SHELF.ALREADY_READ } : { rating: next };
        // Say the shelf move too when there is one: a rating that quietly moved
        // the book would be a surprise on the next open.
        const announce = [
            next ? this.t('rated', { rating: next }) : this.t('ratingCleared'),
            optimistic.shelf && optimistic.shelf !== this.shelf ? this.t('addedToShelf', { shelf: this.t(SHELF_LABEL[optimistic.shelf]) }) : '',
        ].filter(Boolean).join('. ');
        return this._mutate(optimistic, async() => {
            await setRating(this.book.key, next, { editionKey: this.book.editionKey });
            trackEvent('StarRating', next ? 'BookRated' : 'RatingCleared');
            this._emitState();
        }, announce);
    }

    // ── Check-in ─────────────────────────────────────────────

    /** `amending`: the book was already on the shelf, so the pane offers a way off it too. */
    async _openCheckIn({ amending = false } = {}) {
        this._pane = 'checkIn';
        this._amending = amending;
        // The prompt asked unbidden is counted as shown, so the answers and
        // skips it gets can be read as a rate. Amending an existing date is
        // the old prompt's "Edit" link, under the name its dashboards use.
        if (!amending) trackEvent('CheckInPrompt', 'Shown');
        else if (this.readDate) trackEvent('CheckInPrompt', 'EditDate');
        // A date the shortcuts cannot express would otherwise sit unseen
        // behind a collapsed row, so the pane opens on it. Focus still lands
        // on Today: the reader is being shown their answer, not asked to
        // retype it, and Skip above it is not the answer to land on.
        this._pickingDate = this._answeredBy === 'other';
        // Seeded from the date already given, so "Other date" opens on it
        // rather than making the reader re-enter what they are amending.
        const [year = '', month = '', day = ''] = (this.readDate || '').split('-');
        this._date = { year, month: month.replace(/^0/, ''), day: day.replace(/^0/, '') };
        await this.updateComplete;
        this.shadowRoot.querySelector(`.pane:nth-child(${PANES.indexOf('checkIn') + 1}) .row.today`)?.focus({ preventScroll: true });
    }

    /** Focus follows the disclosure: into the selects, and back to the row on collapse. */
    async _toggleDatePicker() {
        this._pickingDate = !this._pickingDate;
        // Opening the fields is what the old prompt's "Other" link did.
        if (this._pickingDate) trackEvent('CheckInPrompt', 'SetDateCustom');
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

    /** Keeps the shelf, gives no date. Tracked so we learn how often the question goes unanswered. */
    _onSkipDate() {
        trackEvent('CheckInPrompt', 'Skip');
        return this._backToMain();
    }

    // The analytics events are the ones the old check-in prompt and form sent
    // for the same answers, so their dashboards carry on across the move into
    // the popover: the two quick rows were the prompt's links, the fields
    // were its form.

    _onToday() {
        const now = new Date();
        return this._saveCheckIn({ year: now.getFullYear(), month: now.getMonth() + 1, day: now.getDate() }, ['CheckInPrompt', 'SetDateToday']);
    }

    _onYear(year) {
        return this._saveCheckIn({ year }, ['CheckInPrompt', 'SetDateCurrentYear']);
    }

    _onSaveDate(e) {
        e.preventDefault();
        const { year, month, day } = this._date;
        if (!year) return;
        return this._saveCheckIn({
            year: Number(year),
            month: month ? Number(month) : null,
            day: day ? Number(day) : null,
        }, ['CheckInForm', 'SubmitCheckIn']);
    }

    /** Drops the date but keeps the shelf, as the old form's Delete Event did, under its event name. */
    async _onRemoveDate() {
        if (this._dateBusy || !this.eventId) return;
        this._dateBusy = true;
        try {
            await deleteCheckIn(this.eventId);
            this.readDate = null;
            this.eventId = null;
            trackEvent('CheckInForm', 'DeleteCheckIn');
            this.dispatchEvent(new CustomEvent('ol-book-check-in', {
                bubbles: true,
                composed: true,
                detail: { key: this.book.key, date: null, eventId: null },
            }));
            this._say(this.t('dateRemoved'));
            this._backToMain();
        } catch (error) {
            this._fail(error);
        } finally {
            this._dateBusy = false;
        }
    }

    /** @param {[string, string]} event - The analytics category and action for this answer. */
    async _saveCheckIn(date, event) {
        if (this._dateBusy) return;
        this._dateBusy = true;
        try {
            const saved = await setCheckIn(this.book.key, { ...date, editionKey: this.book.editionKey, eventId: this.eventId });
            // Keep our own copy so the main pane's Already Read row shows the
            // date, and re-saving amends this event instead of adding one.
            this.readDate = partialDate(date);
            this.eventId = saved?.id ?? this.eventId ?? null;
            trackEvent(...event);
            this.dispatchEvent(new CustomEvent('ol-book-check-in', {
                bubbles: true,
                composed: true,
                detail: { key: this.book.key, date: this.readDate, eventId: this.eventId },
            }));
            this._say(this.t('dateSaved', { date: formatReadDate(this.readDate) }));
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
     * the focus came from is inert now and would strand it. Opening and
     * closing the create form go through here too, for the same reason.
     */
    _focusListsPane() {
        const pane = `.pane:nth-child(${PANES.indexOf('lists') + 1})`;
        const mobile = window.matchMedia('(max-width: 767px)').matches;
        // A selector list matches the first of them in document order, and the
        // fields both sit above the rows.
        // Lists-only has no back button; on mobile the first row stands in for it.
        const target = mobile ? (this.listsOnly ? '.list-row input, ol-button' : '.back') : '.input, .list-row input';
        const el = this.shadowRoot.querySelector(`${pane} ${target}`);
        if (!el) return false;
        // A fresh <ol-button> has no inner control to take focus until its own first render.
        if (el.updateComplete) el.updateComplete.then(() => el.focus({ preventScroll: true }));
        else el.focus({ preventScroll: true });
        return true;
    }

    /** Focus goes back to the row that led to the pane being left. Lists-only has no main pane: leaving the lists closes. */
    async _backToMain() {
        if (this.listsOnly) {
            const popover = this.shadowRoot.querySelector('ol-popover');
            if (popover) popover.open = false;
            return;
        }
        const from = this._pane;
        const amending = this._amending;
        this._pane = 'main';
        this._creating = false;
        this._pickingDate = false;
        await this.updateComplete;
        // From the date pane: whichever half of Already Read led there. The
        // shelf half when the date half has gone with the shelf.
        const main = this.shadowRoot.querySelector('.pane:nth-child(1)');
        const shelfHalf = main?.querySelector(`.row[data-shelf="${SHELF.ALREADY_READ}"]`);
        const row = from === 'checkIn'
            ? (amending && main?.querySelector('.date-link')) || shelfHalf
            : main?.querySelector('.group.lists-entry .row');
        row?.focus({ preventScroll: true });
    }

    /**
     * Freeze the order the lists are shown in, and which of them count as
     * recent, for as long as the popover stays open. Adding to a list moves it
     * to the front of the store; taking the order live would move the row the
     * reader just used out from under the one they are reaching for next.
     */
    _snapshotLists() {
        const lists = getLists() || {};
        this._order = Object.keys(lists);
        this._recent = getRecentLists(this.userKey);
        this._members = this._order.filter(key => this._inList(lists[key]));
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

    /**
     * The lists worth pinning above the rest, once there are enough lists to
     * matter: the ones this book is already on first — which of them it is on
     * is the pane's first question, and the answer must not be below the fold
     * — then the recently used ones. Both come off the open-time snapshot, so
     * ticking a box never moves a row.
     */
    _pinnedKeys(lists) {
        if (this._listTotal < PIN_THRESHOLD) return [];
        const members = this._members.filter(key => key in lists);
        const seen = new Set(members);
        const recent = this._recent.map(entry => entry.key).filter(key => key in lists && !seen.has(key));
        return [...members, ...recent];
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
        return Object.values(lists).filter(list => this._inList(list)).length;
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
            this.dispatchEvent(new CustomEvent('ol-list-change', {
                bubbles: true,
                composed: true,
                detail: { key: listKey, name, seedKey: this._seedKey, member: checked },
            }));
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
        const checked = !this._holdsSeed(lists[key]);
        this._say(this.t(checked ? 'addedToList' : 'removedFromList', { name }));
        this._onListToggle(key, checked);
    }

    async _startCreate() {
        this._creating = true;
        await this.updateComplete;
        this._focusListsPane();
    }

    async _cancelCreate() {
        // With no lists the pane is the form; there is nothing to cancel back to.
        if (this._firstList) return this._backToMain();
        this._creating = false;
        await this.updateComplete;
        this._focusListsPane();
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
            // The form is gone with the field that had focus; the new list is
            // the first row, already checked, and says so when focused.
            await this.updateComplete;
            this.shadowRoot.querySelector('.pane:nth-child(2) .list-row input')?.focus({ preventScroll: true });
        } catch (error) {
            this._fail(error);
        } finally {
            this._createBusy = false;
        }
    }
}

customElements.define('ol-shelf-actions', OlShelfActions);
