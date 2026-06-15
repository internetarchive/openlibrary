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
 * @typedef {{ value: string, label: string, count?: string }} LanguageOption
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

function normalizeFacetCounts(facetCounts) {
    if (!Array.isArray(facetCounts)) return new Map();
    return new Map(
        facetCounts
            .map((facet) => {
                if (Array.isArray(facet)) {
                    return [facet[0], Number(facet[2]) || 0];
                }
                return [facet?.value ?? facet?.key, Number(facet?.count) || 0];
            })
            .filter(([value, count]) => value && count > 0)
    );
}

/**
 * Add result counts to language options once a search response includes a
 * language facet. Counted languages sort highest-first; selected languages stay
 * in the item list even when the current facet response does not include them.
 *
 * @param {LanguageOption[]} options
 * @param {Array<[string, string, number]>|Array<{value?: string, key?: string, count?: number}>|null} facetCounts
 * @param {string[]} selected
 * @returns {LanguageOption[]}
 */
export function languageOptionsWithCounts(options, facetCounts, selected = []) {
    const baseOptions = options?.length ? options : DEFAULT_LANGUAGE_OPTIONS;
    const counts = normalizeFacetCounts(facetCounts);
    if (!counts.size) {
        return baseOptions.map(({ value, label }) => ({ value, label }));
    }

    const selectedSet = new Set(selected);
    return baseOptions
        .filter(option => counts.has(option.value) || selectedSet.has(option.value))
        .map((option) => {
            const count = counts.get(option.value) || 0;
            return {
                value: option.value,
                label: option.label,
                count: count.toLocaleString(),
                countValue: count,
            };
        })
        .sort((a, b) => {
            const selectedDiff = Number(selectedSet.has(b.value)) - Number(selectedSet.has(a.value));
            if (selectedDiff) return selectedDiff;
            return b.countValue - a.countValue || a.label.localeCompare(b.label);
        })
        .map(({ value, label, count }) => ({ value, label, count }));
}
