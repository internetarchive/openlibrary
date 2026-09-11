/**
 * The surface behind every <ol-shelf-button> on a page.
 *
 * The button is stateless: it reports a change and expects its owner to apply
 * it. This module listens at the document and writes each change onto every
 * button for the same work, so a book in a carousel and in a search row stay
 * in step.
 *
 * It also fills in what the server could not. Carousel buttons arrive without
 * state (their HTML is cached across readers, or fetched lazily): they get the
 * reader's key from <body data-user-key>, labels from the hidden input in
 * site/body.html, and their state from one batched request, repeated for
 * buttons that arrive later.
 *
 * On a page that lists one shelf (`[data-shelf]` on the list), a row whose
 * book has left that shelf stays where it is and says so, with a way back;
 * the next load drops it. Every `[data-shelf-count]` on the page moves with
 * the change, so the sidebar and heading agree without a reload.
 *
 * @module book-state
 */
import { SHELF_LABEL, setShelf } from '../../../components/lit/utils/books-api.js';
import { translate } from '../../../components/lit/utils/labels.js';
import { FadingToast } from './Toast.js';
import { buildPartialsUrl } from './utils';

/** The server's cap on one ReadingState.json request. */
export const BATCH_SIZE = 100;
const LABELS_INPUT = 'input[name="shelf-button-i18n-strings"]';
/** English fallbacks for the row note; my_books/shelf_button_i18n.html carries the translations. */
const NOTE_LABELS = {
    wantToRead: 'Want to Read',
    currentlyReading: 'Currently Reading',
    alreadyRead: 'Already Read',
    stoppedReading: 'Stopped Reading',
    movedTo: 'Moved to %(shelf)s',
    removedFromShelf: 'Removed from shelf',
    undo: 'Undo',
    errorGeneric: 'Something went wrong. Please try again.',
};

let labels = null;
/** Buttons that have their labels and user key. */
const seen = new WeakSet();
/** Buttons whose state has been fetched, or is in flight. */
const requested = new WeakSet();
let scheduled = false;

/** The labels site/body.html rendered, or null. */
export function readLabels() {
    const input = document.querySelector(LABELS_INPUT);
    if (!input) return null;
    try {
        return JSON.parse(input.value);
    } catch {
        return null;
    }
}

function userKey() {
    return document.body.dataset.userKey || '';
}

function buttonsFor(workKey) {
    return document.querySelectorAll(`ol-shelf-button[work-key="${workKey}"]`);
}

/** Write one ReadingState entry onto a button. */
export function applyState(button, state) {
    button.shelf = state?.shelf ?? null;
    button.rating = state?.rating ?? null;
    button.readDate = state?.read_date ?? null;
    button.eventId = state?.event_id ?? null;
    button.setAttribute('data-hydrated', '');
}

function t(key, vars) {
    labels ??= readLabels();
    return translate(labels, NOTE_LABELS, key, vars);
}

function emit(key, shelf, rating) {
    document.dispatchEvent(new CustomEvent('ol-book-state-change', { detail: { key, shelf, rating } }));
}

function onStateChange(e) {
    const { key, shelf, rating } = e.detail;
    const next = shelf ?? null;
    const buttons = [...buttonsFor(key)];
    const previous = knownShelf(buttons);
    for (const button of buttons) {
        button.shelf = next;
        button.rating = rating ?? null;
        // Off the shelf takes the check-ins with it (the server deletes them).
        if (next === null) {
            button.readDate = null;
            button.eventId = null;
        }
    }
    if (previous !== undefined && previous !== next) moveCounts(previous, next);
    for (const button of buttons) noteMove(button, key, next);
}

/** The shelf the page showed before a change, from a button that had state; undefined when none did. */
function knownShelf(buttons) {
    const known = buttons.find(b => b.hasAttribute('data-hydrated'));
    return known ? (known.shelf ?? null) : undefined;
}

/** The count is the first number in the element's text: "27", or "Already Read (194)". */
function bump(el, delta) {
    const text = el.textContent;
    const match = /\d+/.exec(text);
    if (!match) return;
    const count = Math.max(0, Number(match[0]) + delta);
    el.textContent = text.slice(0, match.index) + count + text.slice(match.index + match[0].length);
}

function moveCounts(from, to) {
    for (const el of document.querySelectorAll('[data-shelf-count]')) {
        const id = Number(el.dataset.shelfCount);
        if (id === from) bump(el, -1);
        else if (id === to) bump(el, 1);
    }
}

/** On a page listing one shelf, mark a row whose book has left it, or clear the mark once it is back. */
function noteMove(button, key, next) {
    const list = button.closest('[data-shelf]');
    const row = button.closest('.searchResultItem');
    if (!list || !row) return;
    const home = Number(list.dataset.shelf);
    const existing = row.querySelector('.shelf-moved-note');
    if (next === home) {
        existing?.remove();
        return;
    }
    const note = existing ?? buildNote(row, key, home);
    note.querySelector('.shelf-moved-note__text').textContent = next === null
        ? t('removedFromShelf')
        : t('movedTo', { shelf: t(SHELF_LABEL[next]) });
    note.dataset.from = next ?? '';
}

function buildNote(row, key, home) {
    const note = document.createElement('p');
    note.className = 'shelf-moved-note';
    note.setAttribute('role', 'status');
    const text = document.createElement('span');
    text.className = 'shelf-moved-note__text';
    const undo = document.createElement('button');
    undo.type = 'button';
    undo.className = 'shelf-moved-note__undo';
    undo.textContent = t('undo');
    undo.addEventListener('click', () => undoMove(key, home, note));
    note.append(text, ' ', undo);
    (row.querySelector('.searchResultItemCTA__shelf') ?? row.querySelector('.searchResultItemCTA') ?? row).append(note);
    return note;
}

/** Put the book back on the page's shelf: optimistic, like the button, and rolled back the same way. */
async function undoMove(key, home, note) {
    const button = buttonsFor(key)[0];
    const rating = button?.rating ?? null;
    const from = note.dataset.from === '' ? null : Number(note.dataset.from);
    emit(key, home, rating);
    try {
        await setShelf(key, home, { editionKey: button?.editionKey });
    } catch {
        emit(key, from, rating);
        new FadingToast(t('errorGeneric')).show();
    }
}

function onCheckIn(e) {
    const { key, date, eventId } = e.detail;
    for (const button of buttonsFor(key)) {
        button.readDate = date;
        button.eventId = eventId;
    }
}

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

/** Give every button its labels and the reader's key, then fetch state for the ones the server left without it. */
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
            fresh.push(button);
        }
    }
    if (fresh.length) await fetchState(fresh);
}

/** Coalesce a burst of DOM insertions into one pass. */
function scheduleHydrate() {
    if (scheduled) return;
    scheduled = true;
    setTimeout(() => {
        scheduled = false;
        hydrate();
    }, 0);
}

export function initBookState() {
    document.addEventListener('ol-book-state-change', onStateChange);
    document.addEventListener('ol-book-check-in', onCheckIn);
    hydrate();
    new MutationObserver(scheduleHydrate).observe(document.body, { childList: true, subtree: true });
}

/** For tests. */
export function resetBookState() {
    labels = null;
    scheduled = false;
    document.removeEventListener('ol-book-state-change', onStateChange);
    document.removeEventListener('ol-book-check-in', onCheckIn);
}
