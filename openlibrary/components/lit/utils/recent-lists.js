/**
 * The lists a reader has been working in, remembered across page loads.
 *
 * Curation runs in bursts — many books into one list in a sitting — but every
 * book is a fresh popover. The server already orders lists by last_modified,
 * so this only carries that recency across the gap the client opens: the
 * store loads once per page and freezes the order it arrived in.
 *
 * Names ride along with the keys so a popover can offer the shortcut before
 * the lists themselves have loaded, and the panel doesn't grow a row mid-open.
 */

const STORAGE_KEY = 'ol.recentLists';
/** Enough for the two or three lists a themed session runs on, no more. */
const LIMIT = 3;
/** Older than this is not recency any more, it is a stale guess. */
const TTL_MS = 14 * 24 * 60 * 60 * 1000;

/** Stands in for localStorage where it throws: private mode, blocked storage. */
let memory = null;

function read() {
    if (memory) return memory;
    try {
        return JSON.parse(window.localStorage.getItem(STORAGE_KEY)) || {};
    } catch {
        memory = {};
        return memory;
    }
}

function write(all) {
    if (memory) {
        memory = all;
        return;
    }
    try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(all));
    } catch {
        memory = all;
    }
}

/**
 * Most recent first, `[{ key, name }]`. Keyed by user so a shared browser
 * never offers one account's lists to another.
 */
export function getRecentLists(userKey) {
    if (!userKey) return [];
    const cutoff = Date.now() - TTL_MS;
    return (read()[userKey] || [])
        .filter(entry => entry?.key && entry.ts > cutoff)
        .slice(0, LIMIT)
        .map(({ key, name }) => ({ key, name }));
}

/** Records a list as the one being worked in. Adds and removals both count. */
export function noteListUsed(userKey, listKey, name) {
    if (!userKey || !listKey) return;
    const all = read();
    const rest = (all[userKey] || []).filter(entry => entry?.key && entry.key !== listKey);
    all[userKey] = [{ key: listKey, name: name || '', ts: Date.now() }, ...rest].slice(0, LIMIT);
    write(all);
}

/** Forget everything (tests). */
export function clearRecentLists() {
    memory = null;
    try {
        window.localStorage.removeItem(STORAGE_KEY);
    } catch {
        memory = {};
    }
}
