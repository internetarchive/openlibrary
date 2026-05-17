// Fetch helpers for author and subject typeahead suggestions.
// Adapted from archivelabs/openlibrary-components for Open Library's own endpoints.

import { POPULAR_SUBJECTS } from './filters.js';

/**
 * Fetch author suggestions from OL's author search API.
 * Endpoint: /search/authors.json?q=...&limit=8
 * Returns { docs: [{key, name, work_count}] }
 */
export async function fetchAuthorSuggestions(q, { signal } = {}) {
    if (q.trim().length < 2) return [];
    try {
        const url = `/search/authors.json?q=${encodeURIComponent(q.trim())}&limit=8`;
        const d = await (await fetch(url, { signal })).json();
        return (d.docs ?? []).map(a => ({ name: a.name, work_count: a.work_count }));
    } catch (err) {
        if (err.name === 'AbortError') return [];
        throw err;
    }
}

/**
 * Return subject suggestions by filtering the static POPULAR_SUBJECTS list.
 * OL has no dedicated subject typeahead API; client-side filtering is fast enough.
 */
export async function fetchSubjectSuggestions(q) {
    if (q.trim().length < 2) return [];
    const lower = q.trim().toLowerCase();
    return POPULAR_SUBJECTS
        .filter(s => s.toLowerCase().includes(lower))
        .slice(0, 8)
        .map(name => ({ name }));
}
