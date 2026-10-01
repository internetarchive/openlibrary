/**
 * The surface behind every <ol-shelf-button> on a page.
 *
 * The button is stateless: it reports a change and expects its owner to apply
 * it. This module listens at the document and writes each change onto every
 * button for the same work, so a book in a carousel and in a search row stay
 * in step.
 *
 * It also fills in what the server could not. Carousel buttons arrive without
 * state (their HTML is cached, or fetched lazily): they get the
 * reader's key from <body data-user-key>, labels from the hidden input in
 * site.html.jinja, and their state from one batched request, repeated for
 * buttons that arrive later. They stay pending until that lands, so nobody can
 * act on a shelf we have not read yet.
 *
 * On a page that lists one shelf (`[data-shelf]` on the list), a row whose
 * book has left that shelf stays where it is and says so, with a way back;
 * the next load drops it. Every `[data-shelf-count-for]` on the page moves with
 * the change, so the sidebar and heading agree without a reload.
 *
 * @module book-state
 */
import { SHELF_LABEL, setShelf } from '../../../components/lit/utils/books-api.js';
import { translate } from '../../../components/lit/utils/labels.js';
import { debounce } from './nonjquery_utils.js';
import { FadingToast } from './Toast.js';
import { buildPartialsUrl } from './utils';

/** The server's cap on one ReadingState.json request. */
export const BATCH_SIZE = 100;
/** How long insertions are pooled before a pass. Long enough to outlast a lazy carousel's fetch. */
export const HYDRATE_DELAY = 100;
const LABELS_INPUT = 'input[name="shelf-button-i18n-strings"]';
/** English fallbacks for the left-shelf notice; my_books/shelf_button_i18n.html carries the translations. */
const NOTICE_LABELS = {
    wantToRead: 'Want to Read',
    currentlyReading: 'Currently Reading',
    alreadyRead: 'Already Read',
    stoppedReading: 'Stopped Reading',
    movedTo: 'Moved to %(shelf)s',
    removedFromShelf: 'Removed from shelf',
    undo: 'Undo',
    errorGeneric: 'Something went wrong. Please try again.',
};

/** @type {Object<string, string|Object<string, string>>|null} */
let labels = null;
/** Buttons that have their labels and user key. */
const seen = new WeakSet();
/** Buttons whose state has been fetched, or is in flight. */
const requested = new WeakSet();
/** Whether the document listeners are attached; a pending pass is dropped once they are not. */
let listening = false;

/**
 * The labels site.html.jinja rendered.
 * @returns {Object<string, string|Object<string, string>>|null}
 */
export function readLabels() {
    const input = document.querySelector(LABELS_INPUT);
    if (!input) return null;
    try {
        return JSON.parse(input.value);
    } catch {
        return null;
    }
}

/** @returns {string} The reader's key, e.g. "/people/foo", or "" when logged out. */
function userKey() {
    return document.body.dataset.userKey || '';
}

/**
 * @param {string} workKey e.g. "/works/OL1W"
 * @returns {NodeListOf<HTMLElement>} Every shelf button for that work.
 */
function buttonsFor(workKey) {
    return document.querySelectorAll(`ol-shelf-button[work-key="${workKey}"]`);
}

/**
 * Write one ReadingState entry onto a button, and let it act again.
 * @param {HTMLElement} button An <ol-shelf-button>.
 * @param {{shelf?: number|null, rating?: number|null, read_date?: string|null, event_id?: number|null}|null} state
 */
export function applyState(button, state) {
    button.shelf = state?.shelf ?? null;
    button.rating = state?.rating ?? null;
    button.readDate = state?.read_date ?? null;
    button.eventId = state?.event_id ?? null;
    button.pending = false;
    button.setAttribute('data-hydrated', '');
}

/**
 * @param {string} key A key of NOTICE_LABELS.
 * @param {Object<string, string|number>} [vars] Values for its %(name)s placeholders.
 * @returns {string}
 */
function t(key, vars) {
    labels ??= readLabels();
    return translate(labels, NOTICE_LABELS, key, vars);
}

/**
 * @param {string} workKey
 * @param {number|null} shelf
 * @param {number|null} rating
 */
function emit(workKey, shelf, rating) {
    document.dispatchEvent(new CustomEvent('ol-book-state-change', { detail: { key: workKey, shelf, rating } }));
}

/** @param {CustomEvent<{key: string, shelf: number|null, rating: number|null}>} e */
function onStateChange(e) {
    const { key, shelf, rating } = e.detail;
    const next = shelf ?? null;
    const buttons = [...buttonsFor(key)];
    const previous = renderedShelf(buttons);
    for (const button of buttons) {
        button.shelf = next;
        button.rating = rating ?? null;
        // Off the shelf takes the check-ins with it (the server deletes them).
        if (next === null) {
            button.readDate = null;
            button.eventId = null;
        }
    }
    if (previous !== undefined && previous !== next) shiftShelfCounts(previous, next);
    for (const button of buttons) markRowLeftShelf(button, key, next);
}

/**
 * The shelf the page showed before a change, read from a button that had state.
 * @param {HTMLElement[]} buttons
 * @returns {number|null|undefined} undefined when no button had state.
 */
function renderedShelf(buttons) {
    const known = buttons.find(b => b.hasAttribute('data-hydrated'));
    return known ? (known.shelf ?? null) : undefined;
}

/**
 * Add delta to the first number in the element's text: "27", or "Already Read (194)".
 * @param {HTMLElement} el
 * @param {number} delta
 */
function adjustCountText(el, delta) {
    const text = el.textContent;
    const match = /\d+/.exec(text);
    if (!match) return;
    const count = Math.max(0, Number(match[0]) + delta);
    el.textContent = text.slice(0, match.index) + count + text.slice(match.index + match[0].length);
}

/**
 * Move one book between the `[data-shelf-count-for]` elements of two shelves.
 * The attribute holds the shelf id; the count is the number in the element's text.
 * @param {number|null} from
 * @param {number|null} to
 */
function shiftShelfCounts(from, to) {
    for (const el of document.querySelectorAll('[data-shelf-count-for]')) {
        const id = Number(el.dataset.shelfCountFor);
        if (id === from) adjustCountText(el, -1);
        else if (id === to) adjustCountText(el, 1);
    }
}

/**
 * On a page listing one shelf, give a result row whose book has left that shelf
 * a notice saying where it went, or remove the notice once the book is back.
 * @param {HTMLElement} button The <ol-shelf-button> in the row.
 * @param {string} workKey
 * @param {number|null} next The book's new shelf; null when it is on none.
 */
function markRowLeftShelf(button, workKey, next) {
    const list = button.closest('[data-shelf]');
    const row = button.closest('.searchResultItem');
    if (!list || !row) return;
    const pageShelf = Number(list.dataset.shelf);
    const existing = row.querySelector('.left-shelf-notice');
    if (next === pageShelf) {
        existing?.remove();
        return;
    }
    const notice = existing ?? createLeftShelfNotice(row, workKey, pageShelf);
    notice.querySelector('.left-shelf-notice__text').textContent = next === null
        ? t('removedFromShelf')
        : t('movedTo', { shelf: t(SHELF_LABEL[next]) });
    notice.dataset.from = next ?? '';
}

/**
 * Build the "Moved to …" notice with its Undo, and attach it to the row.
 * @param {HTMLElement} row A .searchResultItem.
 * @param {string} workKey
 * @param {number} pageShelf The shelf this page lists; Undo puts the book back there.
 * @returns {HTMLElement}
 */
function createLeftShelfNotice(row, workKey, pageShelf) {
    const notice = document.createElement('p');
    notice.className = 'left-shelf-notice';
    notice.setAttribute('role', 'status');
    const text = document.createElement('span');
    text.className = 'left-shelf-notice__text';
    const undo = document.createElement('button');
    undo.type = 'button';
    undo.className = 'left-shelf-notice__undo';
    undo.textContent = t('undo');
    undo.addEventListener('click', () => undoShelfChange(workKey, pageShelf, notice));
    notice.append(text, ' ', undo);
    (row.querySelector('.searchResultItemCTA__shelf') ?? row.querySelector('.searchResultItemCTA') ?? row).append(notice);
    return notice;
}

/**
 * Put the book back on the page's shelf: optimistic, like the button, and rolled back the same way.
 * @param {string} workKey
 * @param {number} pageShelf
 * @param {HTMLElement} notice Its data-from holds the shelf to roll back to.
 * @returns {Promise<void>}
 */
async function undoShelfChange(workKey, pageShelf, notice) {
    const button = buttonsFor(workKey)[0];
    const rating = button?.rating ?? null;
    const from = notice.dataset.from === '' ? null : Number(notice.dataset.from);
    emit(workKey, pageShelf, rating);
    try {
        await setShelf(workKey, pageShelf, { editionKey: button?.editionKey });
    } catch {
        emit(workKey, from, rating);
        new FadingToast(t('errorGeneric')).show();
    }
}

/** @param {CustomEvent<{key: string, date: string, eventId: number}>} e */
function onCheckIn(e) {
    const { key, date, eventId } = e.detail;
    for (const button of buttonsFor(key)) {
        button.readDate = date;
        button.eventId = eventId;
    }
}

/**
 * Fetch ReadingState for these buttons in batches, and apply it.
 * @param {HTMLElement[]} buttons
 * @returns {Promise<void>}
 */
async function fetchState(buttons) {
    const olids = [...new Set(buttons.map(b => b.getAttribute('work-key').split('/').pop()))];
    for (let i = 0; i < olids.length; i += BATCH_SIZE) {
        const chunk = olids.slice(i, i + BATCH_SIZE);
        let works;
        try {
            const response = await fetch(buildPartialsUrl('ReadingState', { work_ids: chunk.join(',') }), { credentials: 'same-origin' });
            if (!response.ok) throw new Error(`ReadingState → ${response.status}`);
            works = (await response.json()).works;
        } catch {
            // Retried on the next pass.
            buttons.forEach(b => requested.delete(b));
            continue;
        }
        for (const button of buttons) {
            const olid = button.getAttribute('work-key').split('/').pop();
            if (olid in works) applyState(button, works[olid]);
        }
    }
}

/**
 * Give every button its labels and the reader's key, then fetch state for the ones the server left without it.
 * @returns {Promise<void>}
 */
export async function hydrate() {
    const key = userKey();
    const fresh = [];
    for (const button of document.querySelectorAll('ol-shelf-button')) {
        if (!seen.has(button)) {
            seen.add(button);
            labels ??= readLabels();
            if (labels) button.labels = labels;
            if (key && !button.hasAttribute('user-key')) button.userKey = key;
        }
        if (key && !button.hasAttribute('data-hydrated') && !requested.has(button)) {
            requested.add(button);
            // Held until its state lands: the shelf POST is a toggle, so a tap
            // now would read the unknown shelf as "none" and take the book off it.
            button.pending = true;
            fresh.push(button);
        }
    }
    if (fresh.length) await fetchState(fresh);
}

/**
 * Coalesce a burst of DOM insertions into one pass. Each lazy carousel fetches and
 * inserts in its own macrotask, so the window has to outlast a round trip: a trailing
 * wait turns a page of carousels into one request instead of one per carousel.
 */
const scheduleHydrate = debounce(() => {
    if (listening) hydrate();
}, HYDRATE_DELAY);

export function initBookState() {
    listening = true;
    document.addEventListener('ol-book-state-change', onStateChange);
    document.addEventListener('ol-book-check-in', onCheckIn);
    hydrate();
    new MutationObserver(scheduleHydrate).observe(document.body, { childList: true, subtree: true });
}

/** For tests. */
export function resetBookState() {
    labels = null;
    listening = false;
    document.removeEventListener('ol-book-state-change', onStateChange);
    document.removeEventListener('ol-book-check-in', onCheckIn);
}
