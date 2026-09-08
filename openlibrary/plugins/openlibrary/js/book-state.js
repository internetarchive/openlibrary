/**
 * The surface behind every <ol-shelf-button> on a page.
 *
 * The button is stateless: it reports a change and expects whatever owns the
 * book to apply it. On the site that owner is the page, so this module
 * listens at the document and writes each change onto every button for the
 * same work — the same book in a carousel and in a search row stay in step.
 *
 * It also fills in what the server could not. Rows arrive with their state
 * (`data-hydrated`); carousel buttons do not, because their HTML is cached
 * across readers or fetched lazily. Those get the reader's key from
 * <body data-user-key> and their shelf, rating and finish date from one
 * batched request per page, repeated for buttons that arrive later (a lazy
 * carousel, a load-more page). Translated labels come from the hidden input
 * site/body.html renders.
 *
 * @module book-state
 */
import { buildPartialsUrl } from './utils';

/** What one ReadingState.json request may ask for; matches the server's cap. */
export const BATCH_SIZE = 100;
const LABELS_INPUT = 'input[name="shelf-button-i18n-strings"]';

let labels = null;
/** Buttons that have their labels and user key. */
const seen = new WeakSet();
/** Buttons whose state has been fetched, or is in flight. */
const requested = new WeakSet();
let scheduled = false;

/** The translated labels site/body.html rendered, or null if the page has none. */
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
    // Work keys are "/works/OL…W": nothing to escape, but quote anyway.
    return document.querySelectorAll(`ol-shelf-button[work-key="${workKey}"]`);
}

/** Write one ReadingState entry onto a button; `null` state means no state. */
export function applyState(button, state) {
    button.shelf = state?.shelf ?? null;
    button.rating = state?.rating ?? null;
    button.readDate = state?.read_date ?? null;
    button.eventId = state?.event_id ?? null;
    button.setAttribute('data-hydrated', '');
}

function onStateChange(e) {
    const { key, shelf, rating } = e.detail;
    for (const button of buttonsFor(key)) {
        button.shelf = shelf ?? null;
        button.rating = rating ?? null;
        // Off the shelf takes the check-ins with it (the server deletes them).
        if (shelf === null || shelf === undefined) {
            button.readDate = null;
            button.eventId = null;
        }
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
            // Let the next pass (a later mutation) try these again.
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
 * Give every button on the page its labels and, signed in, the reader's key;
 * then fetch state for the ones the server left without it.
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
            fresh.push(button);
        }
    }
    if (fresh.length) await fetchState(fresh);
}

/** Coalesce a burst of DOM insertions (a carousel's worth of cards) into one pass. */
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

/** Forget every button (tests). */
export function resetBookState() {
    labels = null;
    scheduled = false;
    document.removeEventListener('ol-book-state-change', onStateChange);
    document.removeEventListener('ol-book-check-in', onCheckIn);
}
