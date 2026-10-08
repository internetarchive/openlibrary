/**
 * Fetches the real language options for the search filters.
 *
 * Uses the `/languages.json` endpoint (openlibrary/fastapi/languages.py), which
 * returns languages ordered by OL catalogue volume with names already
 * translated to the patron's UI language. This is the single source of truth —
 * preferred over a hardcoded code→label map.
 */

import { DEFAULT_LANGUAGE_OPTIONS } from './constants.js';

const ENDPOINT = '/languages.json';

/**
 * @typedef {{ value: string, label: string }} LanguageOption
 */

/**
 * Fetch language options as `{ value: marc_code, label: name }`, sorted by
 * catalogue volume. Falls back to DEFAULT_LANGUAGE_OPTIONS if the request
 * fails so the popover is never empty.
 *
 * @param {Object} [opts]
 * @param {number} [opts.limit=500] - max languages to request (covers ~all).
 * @param {number} [opts.timeout=8000] - abort the fetch after this many ms.
 * @returns {Promise<LanguageOption[]>}
 */
export async function fetchLanguageOptions({ limit = 500, timeout = 8000 } = {}) {
    try {
        const res = await fetch(
            `${ENDPOINT}?limit=${limit}&sort=count`,
            { signal: AbortSignal.timeout?.(timeout) }
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        const options = (Array.isArray(data) ? data : [])
            .filter(lang => lang && lang.marc_code && lang.name)
            .map(lang => ({ value: lang.marc_code, label: lang.name }));
        return options.length ? options : DEFAULT_LANGUAGE_OPTIONS;
    } catch {
        return DEFAULT_LANGUAGE_OPTIONS;
    }
}
