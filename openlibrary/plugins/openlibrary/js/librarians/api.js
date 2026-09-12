/**
 * Fetch wrappers for the /librarians endpoints (openlibrary/fastapi/librarians.py).
 * Every call resolves to parsed JSON and rejects with an Error carrying
 * `.status` and, when the server sent one, `.detail`.
 */

async function send(url, init = {}) {
    const response = await fetch(url, {
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...(init.headers || {}) },
        ...init,
    });
    let body = null;
    try { body = await response.json(); } catch { /* empty */ }
    if (!response.ok) {
        const detail = body && body.detail;
        const message = (detail && (detail.error || detail)) || response.statusText;
        const error = new Error(typeof message === 'string' ? message : JSON.stringify(message));
        error.status = response.status;
        error.detail = detail;
        throw error;
    }
    return body;
}

const json = (body) => JSON.stringify(body);

export const api = {
    // Workbench
    config: () => send('/librarians/workbench/config.json'),
    query: (body) => send('/librarians/workbench/query.json', { method: 'POST', body: json(body) }),
    keys: (keys) => send(`/librarians/workbench/keys.json?keys=${encodeURIComponent(keys.join(','))}`),
    worklists: (counts = true) => send(`/librarians/workbench/worklists.json?counts=${counts}`),
    createWorklist: (body) => send('/librarians/workbench/worklists.json', { method: 'POST', body: json(body) }),
    updateWorklist: (id, body) => send(`/librarians/workbench/worklists/${id}.json`, { method: 'PUT', body: json(body) }),
    deleteWorklist: (id) => send(`/librarians/workbench/worklists/${id}.json`, { method: 'DELETE' }),
    record: (key) => send(`/librarians/workbench/record.json?key=${encodeURIComponent(key)}`),
    // Batches
    batch: (body) => send('/librarians/batch.json', { method: 'POST', body: json(body) }),
    batches: (params = {}) => send(`/librarians/batches.json?${new URLSearchParams(params)}`),
    batchApply: (id, comment, overrides = []) => send(`/librarians/batch/${id}/apply.json`, { method: 'POST', body: json({ comment, overrides }) }),
    batchDecline: (id, comment) => send(`/librarians/batch/${id}/decline.json`, { method: 'POST', body: json({ comment }) }),
    batchRevert: (id, key, force = false) => send(`/librarians/batch/${id}/revert.json`, { method: 'POST', body: json({ key, force }) }),
    context: (key) => send(`/librarians/context.json?key=${encodeURIComponent(key)}`),
    checks: (action, keys) => send(`/librarians/checks.json?action=${action}&keys=${encodeURIComponent(keys.join(','))}`),
    // Lists (existing endpoints)
    myLists: (username) => send(`/people/${username}/lists.json?limit=100`),
    addSeeds: (username, listOlid, keys) => send(`/people/${username}/lists/${listOlid}/seeds.json`, {
        method: 'POST',
        body: json({ add: keys.map((key) => ({ key })), remove: [] }),
    }),
};

/** "OL1W", "/works/OL1W" or a URL → "/works/OL1W"; null when it isn't a record. */
export function normalizeKey(value) {
    if (!value) return null;
    const m = String(value).match(/\/(works|books|authors)\/(OL\d+[WMA])/);
    if (m) return `/${m[1]}/${m[2]}`;
    const olid = String(value).trim().match(/^OL\d+([WMA])$/);
    if (olid) return `/${{ W: 'works', M: 'books', A: 'authors' }[olid[1]]}/${olid[0]}`;
    return null;
}

export function keyType(key) {
    if (!key) return null;
    return { '/works': 'work', '/books': 'edition', '/authors': 'author' }[key.slice(0, key.lastIndexOf('/'))] || null;
}

export function olid(key) {
    return key ? key.slice(key.lastIndexOf('/') + 1) : '';
}
