/**
 * Thin fetch wrappers for the books-display components. Every function
 * resolves to parsed JSON and rejects with an Error carrying `.status`, so
 * callers can branch on 401 (send to login) vs anything else (toast).
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
    return response.json();
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

/** GET /books-display.json — public, cacheable book cards for a query. */
export function fetchBooks({ q, sort, limit, offset, hasFulltextOnly = true, safeMode = true }) {
    const params = new URLSearchParams({
        q,
        sort,
        limit: String(limit),
        offset: String(offset),
        has_fulltext_only: String(hasFulltextOnly),
        safe_mode: String(safeMode),
    });
    return request(`/books-display.json?${params}`);
}

/** GET /books-display/user-state.json — the current user's shelf + rating per work. */
export function fetchUserState(workKeys) {
    if (!workKeys.length) return Promise.resolve({ shelves: {}, ratings: {} });
    const ids = workKeys.map(olid).join(',');
    return request(`/books-display/user-state.json?work_ids=${encodeURIComponent(ids)}`);
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

/**
 * Mirror of js/utils.js `queueAction` (that bundle can't be imported here):
 * remember what the visitor was doing, then send them to log in.
 */
export function redirectToLogin({ action, title, type = 'book', resumeUrl } = {}) {
    const target = resumeUrl || window.location.pathname + window.location.search;
    if (action && title) {
        const data = encodeURIComponent(JSON.stringify({ name: title, url: target, action, type }));
        document.cookie = `pending_action=${data}; path=/; max-age=129600; samesite=lax`;
    }
    window.location.href = `/account/login?redirect=${encodeURIComponent(target)}`;
}
