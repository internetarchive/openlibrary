const STORAGE_KEY = 'ol_read_history';
const MAX_ENTRIES = 20;

/**
 * @typedef {Object} ReadHistoryEntry
 * @property {string} olid            - Work OLID (e.g. 'OL123W')
 * @property {string} workKey         - Full work key path (e.g. '/works/OL123W')
 * @property {string} title           - Book title
 * @property {number|null} coverId    - Numeric cover ID for covers.openlibrary.org/b/id/
 * @property {string|null} coverEditionKey - Edition OLID for /b/olid/ cover fallback
 * @property {string|null} ocaid      - Internet Archive identifier for /b/ia/ cover fallback
 * @property {string[]} authorNames   - List of author name strings
 * @property {number} timestamp       - Date.now() at the time of the read/borrow interaction
 */

/**
 * Reads and parses the history array from localStorage.
 * Returns an empty array on missing key or JSON parse failure (corrupt data).
 *
 * @returns {ReadHistoryEntry[]}
 */
function readFromStorage() {
    try {
        return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    } catch {
        return [];
    }
}

/**
 * Serialises the history array back to localStorage.
 * Silently no-ops when localStorage is unavailable (e.g. private-browsing
 * quota exceeded or SecurityError in sandboxed iframes).
 *
 * @param {ReadHistoryEntry[]} entries
 */
function writeToStorage(entries) {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
    } catch {
        // ignore — storage unavailable
    }
}

/**
 * Upserts a book into the reading history.
 *
 * - If a record with the same `olid` already exists it is removed first
 *   (so the updated record lands at position 0, i.e. most-recent).
 * - The list is capped at MAX_ENTRIES (20) oldest entries are dropped.
 * - Only public book metadata is stored; no PII.
 *
 * @param {ReadHistoryEntry} entry
 */
export function addEntry({ olid, workKey, title, coverId, coverEditionKey, ocaid, authorNames, timestamp }) {
    const history = readFromStorage().filter(e => e.olid !== olid);
    history.unshift({
        olid,
        workKey,
        title,
        coverId: coverId || null,
        coverEditionKey: coverEditionKey || null,
        ocaid: ocaid || null,
        authorNames: Array.isArray(authorNames) ? authorNames : [],
        timestamp: timestamp || Date.now(),
    });
    writeToStorage(history.slice(0, MAX_ENTRIES));
}

/**
 * Returns the full reading history sorted by timestamp descending
 * (most-recently interacted with first).
 *
 * @returns {ReadHistoryEntry[]}
 */
export function getHistory() {
    return readFromStorage().slice().sort((a, b) => b.timestamp - a.timestamp);
}

/**
 * Removes all entries from the reading history.
 * Intended for use in tests and user opt-out flows.
 */
export function clearHistory() {
    try {
        localStorage.removeItem(STORAGE_KEY);
    } catch {
        // ignore — storage unavailable
    }
}
