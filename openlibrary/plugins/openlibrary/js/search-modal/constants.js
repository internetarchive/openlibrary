/**
 * Filter options for the header search modal.
 *
 * Counts are placeholder strings for v1; wire to live counts later.
 * Availability `value` strings map to /search.json query params in
 * `SearchModal._buildSearchUrl()`.
 */

export const AVAILABILITY_OPTIONS = [
    {
        value: 'all',
        label: 'Full Card Catalog',
        description: 'Info on every book published',
        count: '~50M',
    },
    {
        value: 'readable',
        label: 'Readable Books Only',
        description: 'Older digitized, preserved, physical books',
        count: '~4.6M',
    },
    {
        value: 'borrowable',
        label: 'Borrowable Only',
        description: 'From Internet Archive\'s lending library',
        count: '~2.7M',
    },
    {
        value: 'open',
        label: 'Open Access Only',
        description: 'From Trusted Book Providers',
        count: '~1.8M',
    },
];

export const DEFAULT_AVAILABILITY = 'all';

/**
 * Top languages by Open Library catalog volume. Curated short list keeps the
 * popover usable; uncommon languages remain reachable via Advanced Search.
 * `value` is the ISO 639-2 code passed to /search?language=.
 */
export const LANGUAGE_OPTIONS = [
    { value: 'eng', label: 'English' },
    { value: 'spa', label: 'Spanish' },
    { value: 'fre', label: 'French' },
    { value: 'ger', label: 'German' },
    { value: 'ita', label: 'Italian' },
    { value: 'por', label: 'Portuguese' },
    { value: 'rus', label: 'Russian' },
    { value: 'jpn', label: 'Japanese' },
    { value: 'chi', label: 'Chinese' },
    { value: 'ara', label: 'Arabic' },
    { value: 'hin', label: 'Hindi' },
    { value: 'kor', label: 'Korean' },
    { value: 'dut', label: 'Dutch' },
    { value: 'pol', label: 'Polish' },
    { value: 'swe', label: 'Swedish' },
    { value: 'tur', label: 'Turkish' },
    { value: 'cze', label: 'Czech' },
    { value: 'gre', label: 'Greek' },
    { value: 'heb', label: 'Hebrew' },
    { value: 'lat', label: 'Latin' },
];
