/**
 * Thin fetch wrappers for the book components. Every function resolves to
 * parsed JSON and rejects with an Error carrying `.status`, so callers can
 * branch on 401 (send to login) vs anything else (toast).
 */

export const SHELF = Object.freeze({
    WANT_TO_READ: 1,
    CURRENTLY_READING: 2,
    ALREADY_READ: 3,
    STOPPED_READING: 4,
});

/** Work key "/works/OL1W" → "OL1W". */
export function olid(key) {
    return key.split('/').pop();
}

async function request(url, init) {
    const response = await fetch(url, { credentials: 'same-origin', ...init });
    if (!response.ok) {
        const error = new Error(`${init?.method || 'GET'} ${url} → ${response.status}`);
        error.status = response.status;
        throw error;
    }
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

/** Reading-log event types (BookshelfEvent). */
export const EVENT = Object.freeze({ START: 1, UPDATE: 2, FINISH: 3 });

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
        event_type: EVENT.FINISH,
        year,
        month,
        day,
        edition_key: editionKey || null,
        event_id: eventId || null,
    }));
}

/**
 * The user's lists with membership: `{ [listKey]: { listName, members: [seedKey…] } }`.
 * Reuses the dropper partial so the list-modelling stays in one place.
 */
export async function fetchUserLists() {
    const data = await request('/partials/MyBooksDropperLists.json');
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
 * Mirror of js/utils.js `queueAction` (that bundle can't be imported here):
 * remember what the visitor was doing so the page they land on after signing
 * in can pick it back up. Does not navigate — the caller decides whether the
 * click continues to its href or diverts to the login page.
 */
export function queuePendingAction({ action, title, type = 'book', resumeUrl } = {}) {
    if (!action || !title) return;
    const target = resumeTarget(resumeUrl);
    const data = encodeURIComponent(JSON.stringify({ name: title, url: target, action, type }));
    document.cookie = `pending_action=${data}; path=/; max-age=129600; samesite=lax`;
}

/** Queue the action, then send the visitor to log in. */
export function redirectToLogin({ action, title, type = 'book', resumeUrl } = {}) {
    queuePendingAction({ action, title, type, resumeUrl });
    window.location.href = `/account/login?redirect=${encodeURIComponent(resumeTarget(resumeUrl))}`;
}
