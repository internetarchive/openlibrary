/**
 * Which of a list's members are this book, however it was filed.
 *
 * A list records whichever copy the reader was looking at, so the same book
 * can sit on it as the edition on screen, as another edition, or as the work
 * with no edition named. The shelf popover and the "On your lists" strip both
 * answer from here, so they never disagree about what a list holds.
 */

import { fetchWorkEditions } from './books-api.js';

/**
 * Work key → promise of its edition keys. Module-level, so every component
 * asking about the same book shares one request.
 */
const EDITION_KEYS = new Map();

/** Forget the cached editions (tests). */
export function resetWorkEditionsCache() {
    EDITION_KEYS.clear();
}

/**
 * The work's edition keys, asked for once per work per page. A failure
 * resolves to nothing rather than rejecting: callers then match on the keys
 * they already have instead of waiting on an answer that is not coming.
 */
export function loadWorkEditionKeys(workKey) {
    if (!workKey?.startsWith('/works/')) return null;
    if (!EDITION_KEYS.has(workKey)) {
        EDITION_KEYS.set(workKey, fetchWorkEditions(workKey).catch(() => []));
    }
    return EDITION_KEYS.get(workKey);
}

/**
 * What else of this book the list holds, beside `seedKey` (the key this page
 * records): `{ kind: 'edition', count }` for other editions, `{ kind: 'work' }`
 * for the book with no edition named, or null.
 */
export function otherForm(members, { seedKey, workKey, editionKeys }) {
    const count = members.filter(key => key !== seedKey && editionKeys.includes(key)).length;
    if (count) return { kind: 'edition', count };
    if (workKey && workKey !== seedKey && members.includes(workKey)) return { kind: 'work' };
    return null;
}
