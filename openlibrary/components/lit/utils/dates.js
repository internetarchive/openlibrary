/**
 * Date helpers shared by the book components. The reading log stores partial
 * dates — "2026", "2026-08" and "2026-08-22" are all valid — and these
 * functions are the two directions of that schema plus the small pieces of
 * calendar the UI needs.
 */

let _months = null;
/** Month names in the page's language. Cached: the list never changes. */
export function MONTHS() {
    if (!_months) {
        const lang = document.documentElement.lang || 'en';
        const format = new Intl.DateTimeFormat(lang, { month: 'long' });
        _months = Array.from({ length: 12 }, (_, i) => format.format(new Date(2000, i, 1)));
    }
    return _months;
}

/**
 * A stored (possibly partial) date for display, showing only what is known:
 * "2026", "Aug 2026" or "Aug 22, 2026".
 */
export function formatReadDate(value) {
    const [year, month, day] = String(value).split('-').map(Number);
    if (!year) return '';
    const lang = document.documentElement.lang || 'en';
    const options = month
        ? (day ? { year: 'numeric', month: 'short', day: 'numeric' } : { year: 'numeric', month: 'short' })
        : null;
    if (!options) return String(year);
    return new Intl.DateTimeFormat(lang, options).format(new Date(year, month - 1, day || 1));
}

/**
 * The years the check-in prompt offers as one tap. For the first 30 days of a
 * new year the year just gone stays on offer: that is when a reader is most
 * likely logging something they finished before the turn, and "In 2025" on
 * 25 January saves them the date picker.
 */
export function quickYears(now = new Date()) {
    const year = now.getFullYear();
    const daysIn = Math.floor((now - new Date(year, 0, 1)) / 86400000);
    return daysIn < 30 ? [year, year - 1] : [year];
}

/** The inverse of `formatReadDate`: `{year, month, day}` as the schema stores it. */
export function partialDate({ year, month, day }) {
    const pad = n => String(n).padStart(2, '0');
    if (!month) return String(year);
    return day ? `${year}-${pad(month)}-${pad(day)}` : `${year}-${pad(month)}`;
}
