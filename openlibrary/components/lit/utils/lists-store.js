/**
 * The signed-in reader's lists, shared by every book popover on the page.
 *
 * One canonical copy lives here. Components read `getLists()` and re-render
 * on `subscribeToLists`; the mutating calls own both the optimistic update
 * and its rollback. A change made through one popover is therefore correct
 * in all of them, with no cross-component syncing.
 */

import { fetchUserLists, addToList, removeFromList, createList } from './books-api.js';

/** `{ [listKey]: { listName, members: [seedKey…] } }`, or null before the first load. */
let lists = null;
let inflight = null;
const subscribers = new Set();

export function getLists() {
    return lists;
}

/** Called after every store change. Returns the matching unsubscribe. */
export function subscribeToLists(fn) {
    subscribers.add(fn);
    return () => subscribers.delete(fn);
}

function notify() {
    subscribers.forEach(fn => fn());
}

/**
 * Fetch once per page; concurrent callers share the request. A failure clears
 * the in-flight request so the next call retries.
 */
export async function loadLists() {
    if (lists) return lists;
    inflight ||= fetchUserLists();
    try {
        lists = await inflight;
    } catch (error) {
        inflight = null;
        throw error;
    }
    notify();
    return lists;
}

/** Optimistic membership toggle; rolls back and rethrows on failure. */
export async function toggleListSeed(listKey, seedKey, inList) {
    const list = lists[listKey];
    const before = list.members;
    list.members = inList ? [...before, seedKey] : before.filter(k => k !== seedKey);
    notify();
    try {
        await (inList ? addToList(listKey, seedKey) : removeFromList(listKey, seedKey));
    } catch (error) {
        list.members = before;
        notify();
        throw error;
    }
}

/**
 * Create on the server, then prepend so the new list renders first
 * everywhere. Resolves to the new list's key.
 */
export async function createUserList(userKey, name, seedKey) {
    const created = await createList(userKey, name, seedKey);
    lists = { [created.key]: { listName: name, members: seedKey ? [seedKey] : [] }, ...(lists || {}) };
    notify();
    return created.key;
}

/** Forget everything (tests, or a mutation made outside the store). */
export function resetListsStore() {
    lists = null;
    inflight = null;
    notify();
}
