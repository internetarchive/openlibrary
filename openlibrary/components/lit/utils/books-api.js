/**
 * Thin fetch wrappers for the book components. Every function resolves to
 * parsed JSON and rejects with an Error carrying `.status`, so callers can
 * branch on 401 (send to login) vs anything else (toast).
 */

import { queueAction, buildPartialsUrl } from '../../../plugins/openlibrary/js/utils.js';

export const SHELF = Object.freeze({
    WANT_TO_READ: 1,
    CURRENTLY_READING: 2,
    ALREADY_READ: 3,
    STOPPED_READING: 4,
});

/** Shelf id → key into the components' label objects. */
export const SHELF_LABEL = Object.freeze({
    [SHELF.WANT_TO_READ]: 'wantToRead',
    [SHELF.CURRENTLY_READING]: 'currentlyReading',
    [SHELF.ALREADY_READ]: 'alreadyRead',
    [SHELF.STOPPED_READING]: 'stoppedReading',
});

/**
 * Matomo action names, kept identical to the legacy dropper's
 * `data-ol-link-track`. Indexed by shelf id; `null` (no shelf) is the removal.
 */
export const SHELF_EVENT = Object.freeze({
    [SHELF.WANT_TO_READ]: 'WantToRead',
    [SHELF.CURRENTLY_READING]: 'CurrentlyReading',
    [SHELF.ALREADY_READ]: 'AlreadyRead',
    [SHELF.STOPPED_READING]: 'StoppedReading',
    null: 'RemoveFromShelf',
});

/** Work key "/works/OL1W" → "OL1W". */
export function olid(key) {
    return key.split('/').pop();
}

/** The shared half: fetch and reject non-2xx with a `.status`-carrying Error. */
async function send(url, init) {
    const response = await fetch(url, { credentials: 'same-origin', ...init });
    if (!response.ok) {
        const error = new Error(`${init?.method || 'GET'} ${url} → ${response.status}`);
        error.status = response.status;
        throw error;
    }
    return response;
}

async function request(url, init) {
    const response = await send(url, init);
    const data = await response.json();
    // `bookshelves.json` answers a rejected write with 200 and an `error` key,
    // so checking the status alone would let a failed write look like a save.
    if (data && data.error) {
        const error = new Error(`${init?.method || 'GET'} ${url} → ${data.error}`);
        error.status = response.status;
        error.body = data;
        throw error;
    }
    return data;
}

function form(data) {
    const body = new URLSearchParams();
    for (const [k, v] of Object.entries(data)) {
        if (v !== undefined && v !== null) body.set(k, String(v));
    }
    return { method: 'POST', body, headers: { 'Content-Type': 'application/x-www-form-urlencoded' } };
}

function json(data) {
    return { method: 'POST', body: JSON.stringify(data), headers: { 'Content-Type': 'application/json' } };
}

/**
 * POST /works/OL..W/bookshelves.json. Posting the shelf the work is already
 * on removes it; `-1` removes unconditionally.
 */
export function setShelf(workKey, shelfId, { editionKey } = {}) {
    return request(`/works/${olid(workKey)}/bookshelves.json`, form({ bookshelf_id: shelfId, edition_id: editionKey }));
}

/** POST /works/OL..W/ratings.json. `null` clears the rating. */
export function setRating(workKey, rating, { editionKey } = {}) {
    return request(`/works/${olid(workKey)}/ratings.json`, form({ rating, edition_id: editionKey }));
}

/** BookshelfEvent.FINISH — the only event type this client records. */
const FINISH_EVENT = 3;

/**
 * POST /works/OL..W/check-ins — when the reader finished the book.
 * `month` and `day` are optional: a year alone, or a year and month, are both
 * valid check-ins, which is what lets the UI offer "in 2026".
 *
 * `eventId` edits that check-in in place. Without it the server records another
 * one, which would count as a second book finished — so pass it whenever the
 * reader is changing a date they already gave.
 */
export function setCheckIn(workKey, { year, month = null, day = null, editionKey, eventId = null } = {}) {
    return request(`/works/${olid(workKey)}/check-ins`, json({
        event_type: FINISH_EVENT,
        year,
        month,
        day,
        edition_key: editionKey || null,
        event_id: eventId || null,
    }));
}

/**
 * DELETE /check-ins/:id — drops a recorded date, leaving the book on its shelf.
 * Answers 200 with an empty body, so it goes through `send` rather than
 * `request`. The reader's own events only; the server 403s on anyone else's.
 */
export async function deleteCheckIn(eventId) {
    await send(`/check-ins/${eventId}`, { method: 'DELETE' });
}

/**
 * The user's lists with membership: `{ [listKey]: { listName, members: [seedKey…] } }`.
 * Reuses the dropper partial so the list-modelling stays in one place.
 */
export async function fetchUserLists() {
    const data = await request(String(buildPartialsUrl('MyBooksDropperLists')));
    return data.listData || {};
}

export function addToList(listKey, seedKey) {
    return request(`${listKey}/seeds.json`, json({ add: [{ key: seedKey }] }));
}

export function removeFromList(listKey, seedKey) {
    return request(`${listKey}/seeds.json`, json({ remove: [{ key: seedKey }] }));
}

/** Resolves to `{ key, ... }` of the new list. */
export function createList(userKey, name, seedKey) {
    return request(`${userKey}/lists.json`, json({ name, description: '', seeds: seedKey ? [{ key: seedKey }] : [] }));
}

/** Where a logged-out visitor lands back after signing in. */
function resumeTarget(resumeUrl) {
    return resumeUrl || window.location.pathname + window.location.search;
}

/**
 * Queue the action (js/utils.js `queueAction`, so the page the visitor lands
 * on after signing in can pick it back up), then send them to log in.
 */
export function redirectToLogin({ action, title, type = 'book', resumeUrl } = {}) {
    const target = resumeTarget(resumeUrl);
    if (action && title) queueAction(action, title, target, type);
    window.location.href = `/account/login?redirect=${encodeURIComponent(target)}`;
}
