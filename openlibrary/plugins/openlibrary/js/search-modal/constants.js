/**
 * Filter options for the header search modal.
 */

export const AVAILABILITY_OPTIONS = [
    {
        value: 'all',
        label: 'All',
        description: 'Every book in the catalog',
        count: '~50M',
    },
    {
        value: 'readable',
        label: 'Read now (free)',
        description: 'Fully readable – public domain & open access',
        count: '~4.6M',
    },
    {
        value: 'borrowable',
        label: 'Borrowable',
        description: 'Borrow via Internet Archive\'s lending library',
        count: '~2.7M',
    },
    {
        value: 'open',
        label: 'Preview only',
        description: 'Limited preview available',
        count: '~1.8M',
    },
];

export const DEFAULT_AVAILABILITY = 'all';

/**
 * The 20 default languages shown immediately when the Language popover
 * opens (before any API response arrives, or if the fetch fails).
 *
 * Chosen by OL catalogue volume – the languages most likely to be useful
 * to a patron on the first click. Sorted by global speaker population /
 * OL catalog representation.
 *
 * SearchModal._loadAllLanguages() fetches the full OL language catalogue
 * and replaces this list with a merged, sorted set so every language in
 * the OL catalogue becomes searchable.
 */
export const DEFAULT_LANGUAGE_OPTIONS = [
    { value: 'eng', label: 'English' },
    { value: 'fre', label: 'French' },
    { value: 'ger', label: 'German' },
    { value: 'spa', label: 'Spanish' },
    { value: 'por', label: 'Portuguese' },
    { value: 'ita', label: 'Italian' },
    { value: 'rus', label: 'Russian' },
    { value: 'chi', label: 'Chinese' },
    { value: 'jpn', label: 'Japanese' },
    { value: 'ara', label: 'Arabic' },
    { value: 'dut', label: 'Dutch' },
    { value: 'pol', label: 'Polish' },
    { value: 'swe', label: 'Swedish' },
    { value: 'tur', label: 'Turkish' },
    { value: 'hin', label: 'Hindi' },
    { value: 'kor', label: 'Korean' },
    { value: 'lat', label: 'Latin' },
    { value: 'per', label: 'Persian' },
    { value: 'heb', label: 'Hebrew' },
    { value: 'ben', label: 'Bengali' },
];

/**
 * Full static language list – retained as a label-lookup map used by
 * SearchModal._loadAllLanguages() when merging OL API results.
 *
 * Any language code returned by the OL facet API that appears here gets
 * a human-readable label; unknown codes fall back to title-cased code.
 *
 * Values are ISO 639-2/B codes as expected by the /search?language= param.
 */
export const LANGUAGE_OPTIONS = [
    // ── Tier 1 – highest OL catalog volume ──────────────────────────────
    { value: 'eng', label: 'English' },
    { value: 'fre', label: 'French' },
    { value: 'ger', label: 'German' },
    { value: 'spa', label: 'Spanish' },
    { value: 'por', label: 'Portuguese' },
    { value: 'ita', label: 'Italian' },
    { value: 'rus', label: 'Russian' },
    { value: 'chi', label: 'Chinese' },
    { value: 'jpn', label: 'Japanese' },
    { value: 'ara', label: 'Arabic' },
    { value: 'dut', label: 'Dutch' },
    { value: 'pol', label: 'Polish' },
    { value: 'swe', label: 'Swedish' },
    { value: 'tur', label: 'Turkish' },
    { value: 'lat', label: 'Latin' },
    // ── Tier 2 – well-represented in OL ─────────────────────────────────
    { value: 'hin', label: 'Hindi' },
    { value: 'kor', label: 'Korean' },
    { value: 'cze', label: 'Czech' },
    { value: 'gre', label: 'Greek' },
    { value: 'heb', label: 'Hebrew' },
    { value: 'dan', label: 'Danish' },
    { value: 'nor', label: 'Norwegian' },
    { value: 'fin', label: 'Finnish' },
    { value: 'hun', label: 'Hungarian' },
    { value: 'rum', label: 'Romanian' },
    { value: 'ukr', label: 'Ukrainian' },
    { value: 'bul', label: 'Bulgarian' },
    { value: 'hrv', label: 'Croatian' },
    { value: 'cat', label: 'Catalan' },
    { value: 'vie', label: 'Vietnamese' },
    { value: 'tha', label: 'Thai' },
    { value: 'ind', label: 'Indonesian' },
    { value: 'may', label: 'Malay' },
    { value: 'per', label: 'Persian' },
    { value: 'ben', label: 'Bengali' },
    { value: 'tam', label: 'Tamil' },
    { value: 'tel', label: 'Telugu' },
    { value: 'mar', label: 'Marathi' },
    { value: 'urd', label: 'Urdu' },
    { value: 'pan', label: 'Punjabi' },
    { value: 'guj', label: 'Gujarati' },
    { value: 'mal', label: 'Malayalam' },
    { value: 'kan', label: 'Kannada' },
    // ── Tier 3 – smaller but present collections ─────────────────────────
    { value: 'afr', label: 'Afrikaans' },
    { value: 'alb', label: 'Albanian' },
    { value: 'arm', label: 'Armenian' },
    { value: 'aze', label: 'Azerbaijani' },
    { value: 'baq', label: 'Basque' },
    { value: 'bel', label: 'Belarusian' },
    { value: 'bos', label: 'Bosnian' },
    { value: 'est', label: 'Estonian' },
    { value: 'geo', label: 'Georgian' },
    { value: 'ice', label: 'Icelandic' },
    { value: 'kaz', label: 'Kazakh' },
    { value: 'lav', label: 'Latvian' },
    { value: 'lit', label: 'Lithuanian' },
    { value: 'mac', label: 'Macedonian' },
    { value: 'mlt', label: 'Maltese' },
    { value: 'mon', label: 'Mongolian' },
    { value: 'nep', label: 'Nepali' },
    { value: 'sin', label: 'Sinhala' },
    { value: 'slv', label: 'Slovenian' },
    { value: 'slo', label: 'Slovak' },
    { value: 'srp', label: 'Serbian' },
    { value: 'swa', label: 'Swahili' },
    { value: 'tgl', label: 'Tagalog' },
    { value: 'uzb', label: 'Uzbek' },
    { value: 'wel', label: 'Welsh' },
    { value: 'yid', label: 'Yiddish' },
];

/**
 * sessionStorage keys for per-session filter persistence.
 */
export const SS_AVAILABILITY_KEY = 'ol-header-search-availability';
export const SS_LANGUAGES_KEY    = 'ol-header-search-languages';
