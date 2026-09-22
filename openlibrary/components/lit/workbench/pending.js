/**
 * Bookkeeping for the workbench's staged field edits: `{ key: { field: value } }`
 * that nothing writes until each (field, value) group is previewed and applied
 * as its own set_field batch. Pure functions, so the flow is testable without
 * mounting the workbench.
 */

/** Group staged edits by (field, value); each group becomes one set_field batch. */
export function groupPending(pending) {
    const groups = new Map();
    for (const [key, fields] of Object.entries(pending || {})) {
        for (const [field, value] of Object.entries(fields)) {
            const id = `${field}\u0000${JSON.stringify(value)}`;
            if (!groups.has(id)) groups.set(id, { field, value, keys: [] });
            groups.get(id).keys.push(key);
        }
    }
    return [...groups.values()];
}

/** How many (record, field) edits are staged. */
export function countPending(pending) {
    return Object.values(pending || {}).reduce((n, f) => n + Object.keys(f).length, 0);
}

/**
 * The staged edits left after a batch was applied. Only the field a set_field
 * batch wrote is cleared on the records it touched; edits to other fields, and
 * edits behind any other action, stay staged for their own preview.
 */
export function withoutApplied(pending, keys, action, params) {
    if (action !== 'set_field' || !params?.field) return pending;
    const touched = new Set(keys || []);
    const next = {};
    for (const [key, fields] of Object.entries(pending || {})) {
        const rest = touched.has(key) ? Object.fromEntries(Object.entries(fields).filter(([f]) => f !== params.field)) : fields;
        if (Object.keys(rest).length) next[key] = rest;
    }
    return next;
}
