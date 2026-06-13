import { LitElement, html, css, nothing } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
// The <ol-*> custom elements this modal uses (ol-dialog, ol-toggle,
// ol-select-popover) are registered by the site-wide
// Lit bundle: build/lit-components/production/ol-components.js, loaded from
// openlibrary/templates/site/footer.html. Do NOT re-import those component
// modules here — re-running customElements.define() throws NotSupportedError.
import { debounce } from '../nonjquery_utils.js';
import { sprintf } from '../i18n.js';
import { mode as searchMode } from '../SearchUtils.js';
import {
    AVAILABILITY_OPTIONS,
    AVAILABILITY_TO_PARAMS,
    DEFAULT_AVAILABILITY,
    DEFAULT_LANGUAGE_OPTIONS,
    DEFAULT_SEARCH_MODAL_STRINGS,
    SS_AVAILABILITY_KEY,
    SS_LANGUAGES_KEY,
    ssGet,
    ssSet,
    availabilityOptionsFromElement,
    readableLanguageMismatch,
    readStoredLanguages,
    searchModalStringsFromElement,
    siteLanguageToMarc,
    readRecentSearches,
    saveRecentSearch,
    removeRecentSearch,
} from './constants.js';
import { fetchLanguageOptions } from './languages.js';
import { deriveAuthors } from './authorSuggestion.js';

// `editions` is requested not to render it, but to opt /search.json into the
// edition-level block-join (see WorkSearchScheme.q_to_solr_params). Without it,
// availability filters like "Readable Books Only" (public_scan/print_disabled)
// only match the work-level `ebook_access` aggregate, so the modal would surface
// works the /search page hides — e.g. a work whose only query-matching edition
// is non-readable. Requesting `editions` makes the modal match /search exactly.
// `author_key` rides along with `author_name` so each result's author can link
// to the author page (and so deriveAuthors() can surface author rows for the
// top results whose author the query names).
// `ia` lets _renderResult fall back to the Internet Archive scanned cover when a
// book has no OL-uploaded cover (cover_i is null) — mirroring the rest of the
// site (Edition.get_cover_url → get_ia_cover). Requesting `ia` also propagates
// it into the `editions:[subquery]` docs (see WorkSearchScheme), so both the
// work-level `ia` and the top edition's `ia` are available. See issue #12893.
// `ebook_access` is the access level (Solr enum: no_ebook, unclassified,
// printdisabled, borrowable, public). It rides along at both levels: the
// promoted edition's value drives the per-result "Readable" badge (the badge
// describes the copy this row opens — see _renderResult), and the work-level
// aggregate is the fallback when no edition is promoted. It says only what kind
// of access a copy has, not whether it's currently on loan; live "checked out"
// state is not in Solr.
// `language` propagates into the `editions:[subquery]` docs (WORK_FIELD_TO_ED_FIELD),
// so the promoted readable edition carries its own language — letting
// _renderResult flag a readable copy that isn't in the patron's site language
// (see _readableLanguageMismatch).
const SEARCH_FIELDS = ['key', 'cover_i', 'ia', 'title', 'subtitle', 'author_name', 'author_key', 'first_publish_year', 'ebook_access', 'language', 'editions'];

// `ebook_access` values that earn the "Readable" badge: `public` (free to read
// now) and `borrowable` (lendable) — everything any patron can read without
// special access, mirroring the modal's "Readable Only" filter
// (ebook_access:[borrowable TO *]). `unclassified` and `no_ebook` get no badge —
// a badge there would over-promise access.
const READABLE_ACCESS = new Set(['public', 'borrowable']);

// `printdisabled` scans are readable only by patrons verified for print-disabled
// access. For those patrons the server's "Readable Only" filter and count widen
// to ebook_access:[printdisabled TO *] (see get_fulltext_min), so the badge must
// widen too — otherwise the toggle counts a book the row then shows no badge for
// (the exact mismatch this guards against). _isReadableAccess folds this in per
// patron; everyone else still gets no badge on printdisabled.
const PRINT_DISABLED_ACCESS = 'printdisabled';

const RESULTS_LIMIT     = 10;
// Matches the legacy SearchBar autocomplete threshold: fire the header
// autocomplete only at 3+ chars (see _shouldAutocomplete for the "the" skip).
const MIN_QUERY_LENGTH  = 3;
const COVER_PLACEHOLDER = '/static/images/icons/avatar_book-sm.png';

// The bare common-word "the" matches almost everything and isn't worth a Solr
// round-trip, so the legacy SearchBar skipped it for autocomplete. Navigation
// to /search is still allowed for it (handled by the length-only gates).
const AUTOCOMPLETE_STOPWORDS = new Set(['the']);

export class SearchModal extends LitElement {
    static properties = {
        open: { type: Boolean, reflect: true },
        _query: { state: true },
        _availability: { state: true },
        _languages: { state: true },
        _results: { state: true },
        _authorSuggestions: { state: true },
        _numFound: { state: true },
        _readableCount: { state: true },
        _loading: { state: true },
        _seeAllLoading: { state: true },
        _hasSearched: { state: true },
        _languageItems: { state: true },
        _langsLoading: { state: true },
        _navigatingKey: { state: true },
        _recentSearches: { state: true },
    };

    static styles = css`
        :host {
            font-family: var(--font-family-body);
            color: var(--darker-grey);
        }

        /* Visually hidden but available to screen readers (used by the
           aria-live results-count region). Standard clip-rect technique. */
        .sr-only {
            position: absolute;
            width: 1px;
            height: 1px;
            margin: -1px;
            padding: 0;
            border: 0;
            overflow: hidden;
            clip: rect(0, 0, 0, 0);
            white-space: nowrap;
        }

        /* ── Search input row ──────────────────────────────────────── */

        .bar {
            display: flex;
            align-items: center;
            gap: var(--spacing-sm);
            padding: var(--spacing-md) var(--spacing-lg);
            border-bottom: var(--border-divider);
        }

        /* Wraps the icon + input (+ ESC pill). Transparent on desktop so the
           bar reads as one flat row; becomes an inset rounded box on mobile. */
        .search-field {
            display: flex;
            flex: 1;
            min-width: 0;
            align-items: center;
            gap: var(--spacing-sm);
        }

        .search-icon {
            flex-shrink: 0;
            width: 20px;
            height: 20px;
            color: var(--accessible-grey);
        }

        .search-input {
            flex: 1;
            min-width: 0;
            padding: var(--spacing-sm) 0;
            background: transparent;
            border: none;
            color: inherit;
            font: inherit;
            font-size: 17px;
            line-height: 1.4;
        }

        .search-input::placeholder { color: var(--accessible-grey); }
        .search-input:focus         { outline: none; }

        /* Drop the native type="search" clear affordance — the modal renders
           its own clear button (.clear-btn) once the query is non-empty. */
        .search-input::-webkit-search-cancel-button,
        .search-input::-webkit-search-decoration {
            -webkit-appearance: none;
            appearance: none;
        }

        .esc-pill {
            flex-shrink: 0;
            display: inline-flex;
            align-items: center;
            padding: var(--spacing-2xs) var(--spacing-sm);
            background: var(--white);
            border: 1px solid var(--color-border-subtle);
            border-radius: var(--border-radius-button);
            color: var(--accessible-grey);
            font: inherit;
            font-size: var(--font-size-label-medium);
            font-weight: 600;
            letter-spacing: 0.04em;
            cursor: pointer;
            white-space: nowrap;
        }

        @media (hover: hover) and (pointer: fine) {
            .esc-pill:hover { background: var(--lightest-grey); }
        }

        .esc-pill:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        @media (hover: none) and (pointer: coarse) { .esc-pill { display: none; } }

        /* ── Back button (mobile) ──────────────────────────────────── */

        /* Touch devices don't have an Esc key, so the modal closes via a back
           arrow to the left of the search field (replacing the desktop ESC
           pill). Hidden on desktop, where Esc / the ESC pill do the job. */
        .back-btn {
            flex-shrink: 0;
            display: none;
            align-items: center;
            justify-content: center;
            width: 36px;
            height: 36px;
            margin-left: calc(var(--spacing-xs) * -1);
            background: transparent;
            border: none;
            border-radius: var(--border-radius-button);
            color: var(--accessible-grey);
            cursor: pointer;
        }

        .back-btn svg {
            width: 24px;
            height: 24px;
        }

        .back-btn:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        @media (hover: none) and (pointer: coarse) { .back-btn { display: inline-flex; } }

        /* ── Clear input button ────────────────────────────────────── */

        /* A small X inside the field, shown only once the query is non-empty.
           Clears the text and refocuses the input without closing the modal. */
        .clear-btn {
            flex-shrink: 0;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 24px;
            height: 24px;
            padding: 0;
            background: transparent;
            border: none;
            border-radius: var(--border-radius-circle);
            color: var(--accessible-grey);
            cursor: pointer;
        }

        .clear-btn svg {
            width: 16px;
            height: 16px;
        }

        @media (hover: hover) and (pointer: fine) {
            .clear-btn:hover {
                background: var(--lightest-grey);
                color: var(--darker-grey);
            }
        }

        .clear-btn:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        /* ── Filter section (filter buttons + active chip row) ─────── */

        /* The filter buttons and active-filter chips read as one box: the
           padding and divider live on the wrapper, and a gap spaces the rows.
           When there are no chips the buttons keep the same breathing room
           above the divider. */
        .filter-section {
            display: flex;
            flex-direction: column;
            gap: var(--spacing-sm);
            /* No horizontal padding here: the filter row scrolls on mobile and
               needs the full viewport width as its scroll track. The inline
               inset lives on .filters instead (as scroll-container padding) so
               items still line up with the search field above. */
            padding: var(--spacing-md) 0;
        }

        .clear-all {
            margin-left: auto;
            padding: 3px var(--spacing-sm);
            background: transparent;
            border: 1px solid transparent;
            border-radius: var(--border-radius-button);
            color: var(--darker-grey);
            font: inherit;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
        }

        @media (hover: hover) and (pointer: fine) {
            .clear-all:hover { background: var(--lightest-grey); }
        }

        .clear-all:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        /* ── Filter button row ─────────────────────────────────────── */

        /* A single horizontal-scrolling row: filters keep their natural size
           and overflow off-screen (mobile, or future extra filters) rather
           than wrapping. "Clear all" sits at the far right via margin-left:auto
           when there's spare room, and falls in line after the filters when the
           row overflows. */
        .filters {
            display: flex;
            flex-wrap: nowrap;
            gap: var(--spacing-xs);
            overflow-x: auto;
            /* Inline inset (matches the search field above). Lives here rather
               than on .filter-section so the scroll track spans the full width
               and the trailing inset shows after scrolling. */
            padding-inline: var(--spacing-lg);
            /* Vertical breathing room so focus rings / the active scale aren't
               clipped by the scroll container; the negative margin keeps the
               row's position in the column unchanged. */
            padding-block: var(--spacing-2xs);
            margin-block: calc(var(--spacing-2xs) * -1);
            scrollbar-width: none;
        }

        .filters::-webkit-scrollbar {
            display: none;
        }

        .filters > * {
            flex-shrink: 0;
        }

        /* ── Results ───────────────────────────────────────────────── */

        .results {
            flex: 1;
            min-height: 80px;
            max-height: 480px;
            overflow-y: auto;
        }

        .results-heading {
            margin: 0;
            padding: var(--spacing-sm) var(--spacing-lg) var(--spacing-2xs);
            color: var(--accessible-grey);
            font-size: var(--font-size-label-small);
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        .results-list {
            list-style: none;
            margin: 0;
            padding: 0;
        }

        /* Hairline above every row. Deliberately fainter than the
           modal's section dividers (--color-border-subtle) so the lines read
           as texture rather than structure. Adjacent rows share one line. */
        .results-list li { border-top: 1px solid var(--lightest-grey); }

        /* Sets the author suggestion apart from the "Top results" works below.
           The row hairlines draw the dividing line; this just adds air. */
        .author-suggestion { margin-bottom: var(--spacing-2xs); }

        .result {
            display: flex;
            align-items: flex-start;
            gap: var(--spacing-md);
            padding: var(--spacing-sm) var(--spacing-lg);
            color: inherit;
            text-decoration: none;
            /* Hover background is instant (see docs/ai/design.md); only the
               result fade-in and press-transform animate. */
            transition:
                opacity 160ms ease,
                transform 100ms ease;
        }

        @media (hover: hover) and (pointer: fine) {
            .result:hover { background: var(--lightest-grey); }
        }

        /* Both the author suggestion and the work rows are single anchors, so
           the same focus highlight covers the whole row. */
        .result:focus-visible {
            outline: none;
            background: var(--lightest-grey);
            box-shadow: inset var(--focus-width) 0 0 var(--color-focus-ring);
        }

        @media (prefers-reduced-motion: reduce) { .result { transition: none; } }

        .result__cover-link {
            position: relative;
            display: flex;
            flex-shrink: 0;
        }

        .result__cover {
            flex-shrink: 0;
            width: 36px;
            height: 50px;
            object-fit: cover;
            background: var(--lightest-grey);
            border-radius: var(--border-radius-thumbnail);
        }

        /* Circular author avatar. The person glyph sits underneath as the
           always-present fallback; the photo (when the author has one) is
           layered over it and covers the circle. If the photo 404s, it's hidden
           to reveal the glyph — so there's never a broken-image flash. */
        .result__avatar {
            position: relative;
            display: flex;
            flex-shrink: 0;
            align-items: center;
            justify-content: center;
            width: 36px;
            height: 36px;
            overflow: hidden;
            color: var(--accessible-grey);
            background: var(--lightest-grey);
            border-radius: var(--border-radius-avatar);
        }

        .result__avatar svg { width: 20px; height: 20px; }

        .result__avatar-photo {
            position: absolute;
            inset: 0;
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .result__meta {
            flex: 1;
            min-width: 0;
            font-size: var(--font-size-body-medium);
            line-height: var(--line-height-meta);
        }

        .result__title {
            display: block;
            overflow: hidden;
            color: var(--darker-grey);
            font-weight: 600;
            text-decoration: none;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .result__author {
            display: block;
            overflow: hidden;
            color: var(--accessible-grey);
            font-size: 13px;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .result__year {
            display: block;
            color: var(--accessible-grey);
            font-size: var(--font-size-label-medium);
            font-weight: 400;
        }

        /* Trailing column at the row's edge (.result__meta's flex:1 pushes it
           right): the "Readable" pill, with the "In <language>" hint stacked
           directly beneath it. Right-aligned and top-aligned so the access
           information reads as one unit, apart from the title/author block. */
        .result__access-col {
            flex-shrink: 0;
            align-self: flex-start;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: var(--spacing-3xs);
        }

        /* "Readable" pill — a quiet status indicator, not a button (the whole
           row is the link). Green echoes the site's "you can read this" hue. */
        .result__access {
            padding: var(--spacing-3xs) var(--spacing-xs);
            border-radius: var(--border-radius-button);
            font-size: var(--font-size-label-small);
            font-weight: 700;
            letter-spacing: 0.02em;
            white-space: nowrap;
            color: var(--open-green);
            background: hsla(126, 100%, 30%, 0.1);
        }

        /* Quiet "In <language>" hint shown under the Readable pill when the
           readable copy isn't in the patron's site language. Informational, not
           a button — muted so it sits below the pill without competing with it. */
        .result__lang {
            color: var(--accessible-grey);
            font-size: var(--font-size-label-small);
            font-weight: 400;
            white-space: nowrap;
        }

        .empty, .loading {
            padding: var(--spacing-lg) var(--spacing-lg);
            color: var(--accessible-grey);
            font-size: var(--font-size-body-medium);
            text-align: center;
        }

        /* Animated trailing dots on the "Searching" label. The three dots
           cycle 1 → 2 → 3 → 2 → 1 (a bounce) on a shared 4-step timeline:
           dot 1 is always shown, dot 2 hides only in the first step, dot 3
           shows only in the third. Opacity (not display) keeps all three in
           flow, so the label width never shifts as dots blink. */
        .loading-dots .dot { opacity: 0; }
        .loading-dots .dot:nth-child(1) { opacity: 1; }
        .loading-dots .dot:nth-child(2) { animation: ol-search-dots-2 1.4s linear infinite; }
        .loading-dots .dot:nth-child(3) { animation: ol-search-dots-3 1.4s linear infinite; }

        @keyframes ol-search-dots-2 {
            0%, 24.99%   { opacity: 0; }
            25%, 100%    { opacity: 1; }
        }

        @keyframes ol-search-dots-3 {
            0%, 49.99%   { opacity: 0; }
            50%, 74.99%  { opacity: 1; }
            75%, 100%    { opacity: 0; }
        }

        @media (prefers-reduced-motion: reduce) {
            .loading-dots .dot { opacity: 1; animation: none; }
        }

        /* ── Recent-search row ──────────────────────────────────────────── */

        /* The whole row is one actionable item (a div with role="button",
           since the remove button is nested inside it and buttons can't nest
           in anchors). .result supplies the flex layout and hover/focus
           treatment; the div just needs the pointer cursor anchors get free. */
        .recent-result {
            cursor: pointer;
            /* Tighter than book/author rows — no cover or avatar to clear,
               so the rows can sit closer together. */
            padding-top: var(--spacing-2xs);
            padding-bottom: var(--spacing-2xs);
        }

        /* The row is top-aligned (see .result), but recent rows have only a
           single line of text flanked by fixed-height icons — center the query
           and the clock icon so everything lines up on one baseline. */
        .recent-result .result__meta,
        .recent-result .result__recent-icon { align-self: center; }

        .result__recent-icon {
            flex-shrink: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            height: 28px;
            color: var(--accessible-grey);
        }

        .result__recent-icon svg { width: 18px; height: 18px; }

        .result__remove-recent {
            flex-shrink: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 36px;
            height: 36px;
            /* Keep the full 36px tap target without it propping the
               tightened row back open. */
            margin-top: -2px;
            margin-bottom: -2px;
            background: transparent;
            border: none;
            border-radius: var(--border-radius-button);
            color: var(--accessible-grey);
            cursor: pointer;
            opacity: 0;
            transition: opacity 100ms ease;
        }

        .recent-result:hover .result__remove-recent,
        .recent-result:focus-within .result__remove-recent { opacity: 1; }

        /* One step darker than the row's hover background, so the button
           reads as its own target inside the highlighted row. */
        @media (hover: hover) and (pointer: fine) {
            .result__remove-recent:hover { background: var(--lighter-grey); }
        }

        .result__remove-recent svg { width: 16px; height: 16px; }

        .result__remove-recent:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 2px;
            opacity: 1;
        }

        /* Always show remove button on touch devices (no hover state). */
        @media (hover: none) and (pointer: coarse) {
            .result__remove-recent { opacity: 1; }
        }

        @media (prefers-reduced-motion: reduce) { .result__remove-recent { transition: none; } }
        /* ── Navigating (pressed result → page loading) ────────────── */

        /* Pressing a result navigates the whole window, and the next page can
           take a moment to start painting. During that gap the chosen row
           holds full opacity while the rest dim back and its cover darkens
           under a spinner. */
        .results.is-navigating .result { opacity: 0.4; }

        .results.is-navigating .result.is-target {
            opacity: 1;
            background: var(--lightest-grey);
        }

        .result.is-target .result__cover,
        .result.is-target .result__avatar-photo {
            filter: brightness(0.5);
        }

        /* Spinner centered over the thumbnail. Mirrors the <ol-button> loading
           spinner — a currentcolor ring with one transparent edge spun by
           keyframes — but white here to read over the darkened cover. */
        .result__spinner {
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            opacity: 0;
            pointer-events: none;
            transition: opacity 160ms ease;
        }

        .result__spinner::before {
            content: "";
            box-sizing: border-box;
            width: 18px;
            height: 18px;
            border: 2px solid var(--white);
            border-right-color: transparent;
            border-radius: var(--border-radius-circle);
        }

        .result.is-target .result__spinner { opacity: 1; }

        .result.is-target .result__spinner::before {
            animation: ol-search-result-spin 0.7s linear infinite;
        }

        @keyframes ol-search-result-spin {
            to { transform: rotate(360deg); }
        }

        @media (prefers-reduced-motion: reduce) {
            .results.is-navigating .result.is-target { transform: none; }
            .result.is-target .result__spinner::before { animation-duration: 2s; }
        }

        /* ── Footer ────────────────────────────────────────────────── */

        .footer {
            display: flex;
            justify-content: flex-end;
            padding: var(--spacing-sm) var(--spacing-lg);
            border-top: var(--border-divider);
        }

        /* The footer button is the shared <ol-button> primitive (registered by
           the site-wide Lit bundle — no import here, same as ol-dialog above).
           ol-button is a light-DOM element styled entirely by the global
           static/css/components/ol-button.css, but that sheet can't cross into
           this modal's shadow root — so the primary-variant rules it needs are
           mirrored below. Keep in sync with ol-button.css. */

        ol-button { display: inline-block; }

        /* Once hydrated the host is a bare wrapper; the inner <button> paints. */
        ol-button[hydrated] {
            padding: 0;
            border: 0;
            background: transparent;
            color: inherit;
        }

        ol-button[disabled],
        ol-button[loading] { pointer-events: none; }

        /* Shared appearance: the host pre-upgrade, the inner button post-upgrade. */
        ol-button:not([hydrated]),
        ol-button > button {
            position: relative;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            box-sizing: border-box;
            height: 38px;
            padding: 0 var(--spacing-inset-md);
            font-family: var(--font-family-button);
            font-size: var(--font-size-body-medium);
            font-weight: 500;
            line-height: var(--line-height-control);
            white-space: nowrap;
            background-color: var(--primary-blue);
            border: 1.5px solid var(--primary-blue);
            border-radius: var(--border-radius-button);
            color: var(--white);
            cursor: pointer;
            user-select: none;
            transition: transform 0.08s;
        }

        ol-button > button:active { transform: scale(0.97); }

        @media (hover: hover) and (pointer: fine) {
            ol-button > button:hover {
                background-color: var(--link-blue);
                border-color: var(--link-blue);
            }
        }

        ol-button > button:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: var(--spacing-3xs);
        }

        ol-button[loading] > button { cursor: progress; }

        /* Scoped away from [loading] so the loading state keeps full-strength
           colors while still being non-interactive. */
        ol-button:not([loading]) > button:disabled {
            opacity: 0.55;
            cursor: not-allowed;
        }

        /* Loading: the label and spinner crossfade. Both are always in the DOM
           so the button width stays stable. */
        ol-button > button > .ol-btn-label {
            display: inline-block;
            transition:
                opacity 0.24s ease,
                transform 0.24s ease,
                filter 0.24s ease;
        }

        ol-button[loading] > button > .ol-btn-label {
            opacity: 0;
            transform: scale(0.8);
            filter: blur(2px);
        }

        ol-button > button > .ol-btn-spinner {
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            opacity: 0;
            transform: scale(0.4);
            filter: blur(3px);
            pointer-events: none;
            transition:
                opacity 0.24s ease,
                transform 0.24s ease,
                filter 0.24s ease;
        }

        ol-button > button > .ol-btn-spinner::before {
            content: "";
            display: block;
            box-sizing: border-box;
            width: 1em;
            height: 1em;
            border: 2px solid currentcolor;
            border-right-color: transparent;
            border-radius: var(--border-radius-circle);
        }

        ol-button[loading] > button > .ol-btn-spinner {
            opacity: 1;
            transform: scale(1);
            filter: blur(0);
        }

        ol-button[loading] > button > .ol-btn-spinner::before {
            animation: ol-button-spin 0.7s linear infinite;
        }

        @keyframes ol-button-spin {
            to { transform: rotate(360deg); }
        }

        @media (prefers-reduced-motion: reduce) {
            ol-button > button,
            ol-button > button > .ol-btn-label,
            ol-button > button > .ol-btn-spinner {
                transform: none;
                filter: none;
                transition-property: opacity;
            }

            ol-button[loading] > button > .ol-btn-spinner::before {
                animation-duration: 2s;
            }
        }

        /* ── Mobile overrides ──────────────────────────────────────── */

        @media (max-width: 767px) {
            .search-input { font-size: var(--font-size-body-large); }
            .results { max-height: none; flex: 1; }
            /* The footer is pinned by the dialog's flex column (it sits
               outside the scrolling body). */
            .footer { background: var(--white); }

            /* Flat search row: no boxed field — the back arrow and input read
               as one line under the bar's bottom divider (kept from the base
               .bar style). The magnifying glass is dropped (the back arrow
               anchors the left edge instead). */
            .bar { padding: var(--spacing-sm) var(--spacing-md); }
            .search-field {
                padding: 0;
                border: none;
                border-radius: 0;
            }
            .search-icon { display: none; }
            .back-btn { margin-left: 0; }
        }
    `;

    constructor() {
        super();
        this.open          = false;
        this._query        = '';
        this._results      = [];
        this._authorSuggestions = [];
        this._numFound     = null;
        // Live count of how many of the current query's hits are readable, shown
        // on the "Readable Only" toggle once a search lands. null before the
        // first search (the toggle falls back to the static corpus figure).
        this._readableCount = null;
        this._loading      = false;
        // Whether the footer "See all results" button shows its loading spinner.
        // Set when the patron commits to /search (click or Enter) and the page
        // begins navigating; mirrors how a pressed result uses _navigatingKey.
        this._seeAllLoading = false;
        this._hasSearched  = false;
        this._langsLoading = false;
        this._navigatingKey = null;

        // Availability options. Defaults to the built-in English list; the
        // localized list (from the trigger's data-i18n) is set in
        // initSearchModal before the modal first renders.
        this._availabilityOptions = AVAILABILITY_OPTIONS;

        // Chrome strings (labels, placeholders, status messages). Defaults to
        // English; the translated set (from the trigger's data-i18n-ui) is set
        // in initSearchModal before the modal first renders.
        this._i18n = DEFAULT_SEARCH_MODAL_STRINGS;

        // Curated set shown instantly; replaced by the real catalogue list
        // (translated names, volume-ranked) once _loadAllLanguages() resolves.
        this._languageItems = DEFAULT_LANGUAGE_OPTIONS;

        // The patron's site language as a MARC code (e.g. 'eng'), matching Solr's
        // `language` field. Mapped from the trigger's 2-letter data-search-lang in
        // initSearchModal; '' when unknown, in which case the mismatch pill is
        // suppressed rather than guessed.
        this._siteLanguage = '';

        // Whether the patron is verified for print-disabled access (the `pd`
        // cookie, surfaced as data-print-disabled on the trigger). Widens the
        // "Readable" badge to printdisabled scans for these patrons, matching the
        // server's per-patron readable count (see _isReadableAccess). Defaults to
        // false; set in initSearchModal before the first render.
        this._printDisabled = false;

        // Availability is now a binary All / Readable Only toggle. Honor only an
        // explicit stored 'readable'; everything else — no preference, or a
        // legacy 'open'/'borrowable' value from before the toggle — collapses to
        // the default 'all' (toggle off).
        const _storedAvailability = ssGet(SS_AVAILABILITY_KEY);
        this._availability = _storedAvailability === 'readable' ? 'readable' : DEFAULT_AVAILABILITY;
        this._languages    = readStoredLanguages();

        this._recentSearches = readRecentSearches();

        this._debouncedFetch = debounce(() => this._fetchResults(), 400, false);
        this._activeFetchKey = null;
        this._allLangsLoaded = false;
    }

    connectedCallback() {
        super.connectedCallback();
        // The back button can restore this page (and modal) from the bfcache
        // with a row (or the footer button) still flagged as navigating — clear
        // both so their spinners don't linger on a page the user has returned to.
        this._onPageShow = () => {
            this._navigatingKey = null;
            this._seeAllLoading = false;
        };
        window.addEventListener('pageshow', this._onPageShow);
    }

    disconnectedCallback() {
        window.removeEventListener('pageshow', this._onPageShow);
        super.disconnectedCallback();
    }

    attachToTrigger(trigger) {
        if (!trigger) return;
        // The trigger is a <button>, so a click (incl. keyboard Enter/Space)
        // is the open intent — focus alone should not pop the modal open.
        trigger.addEventListener('click', (e) => {
            if (this.open) return;
            e.preventDefault();
            this._openModal();
        });
        // Open the modal when text is dragged over the trigger so the patron
        // can complete the drop into the search input. Without this the modal
        // never opens during a drag (clicking ends the drag) and the drop is lost.
        trigger.addEventListener('dragover', (e) => {
            e.preventDefault();
            if (!this.open) this._openModal();
        });
    }

    _openModal() {
        this.open = true;
        if (!this._allLangsLoaded && !this._langsLoading) {
            this._loadAllLanguages();
        }
        // Lit updates are async, which would defer the dialog's showModal()
        // and the input focus past the trigger click's call stack. Mobile
        // browsers only raise the soft keyboard for focus() calls made inside
        // the user gesture, so flush both renders and focus synchronously.
        // (ol-after-open re-focuses after the animation — that's a no-op here.)
        this.performUpdate();
        this.renderRoot.querySelector('ol-dialog')?.performUpdate();
        this.renderRoot.querySelector('.search-input')?.focus();
    }

    _closeModal() { this.open = false; }

    // Empties the result list and its derived counts. `hasSearched` records
    // whether this is a post-search empty state (true) or a pre-search reset
    // (false); `clearReadableCount` is false in the main fetch's error path,
    // where the separate readable-count request owns that field.
    _resetResults({ hasSearched, clearReadableCount = true } = {}) {
        this._results           = [];
        this._authorSuggestions = [];
        this._numFound          = null;
        if (clearReadableCount) this._readableCount = null;
        this._loading           = false;
        this._hasSearched       = hasSearched;
    }

    // The small X inside the field: clear the query without closing the modal,
    // then refocus so the patron can keep typing. Mirrors the reset
    // _onQueryInput does when the query drops below the autocomplete threshold,
    // and drops _activeFetchKey so an in-flight fetch can't repopulate results.
    _clearInput() {
        this._query          = '';
        this._navigatingKey  = null;
        this._seeAllLoading  = false;
        this._activeFetchKey = null;
        this._resetResults({ hasSearched: false });
        const input = this.renderRoot.querySelector('.search-input');
        if (input) {
            input.value = '';
            input.focus();
        }
    }

    async _loadAllLanguages() {
        this._langsLoading = true;
        try {
            this._languageItems = await fetchLanguageOptions();
        } finally {
            this._allLangsLoaded = true;
            this._langsLoading   = false;
        }
    }

    // ── Render ────────────────────────────────────────────────────────────

    render() {
        return html`
            <ol-dialog
                ?open=${this.open}
                without-header
                fullscreen-on-mobile
                width="large"
                placement="top"
                label=${this._i18n.dialogAria}
                style="
                    --ol-dialog-padding: 0;
                    --ol-dialog-top-offset: 54px;
                    --ol-dialog-animation-duration: 160ms;
                    --ol-dialog-width-large: min(680px, 92vw);
                    --ol-dialog-backdrop-color: hsla(0,0%,0%,0.18);
                "
                @ol-after-open=${this._onDialogOpened}
                @ol-after-close=${this._onDialogClosed}
            >
                <div slot="header" class="bar">
                    <button
                        type="button"
                        class="back-btn"
                        aria-label=${this._i18n.closeAria}
                        @click=${this._closeModal}
                    >${SearchModal._backIcon}</button>
                    <div class="search-field">
                        ${SearchModal._searchIcon}
                        <input
                            type="search"
                            enterkeyhint="search"
                            class="search-input"
                            autocomplete="off"
                            autocorrect="off"
                            autocapitalize="off"
                            spellcheck="false"
                            placeholder=${this._i18n.inputPlaceholder}
                            aria-label=${this._i18n.inputAria}
                            .value=${this._query}
                            @input=${this._onQueryInput}
                            @keydown=${this._onInputKeydown}
                            @drop=${this._onDrop}
                            @dragover=${this._onDragOver}
                        />
                        ${this._query.length ? html`
                            <button
                                type="button"
                                class="clear-btn"
                                aria-label=${this._i18n.clearAria}
                                @click=${this._clearInput}
                            >${SearchModal._closeIcon}</button>
                        ` : nothing}
                        <button
                            type="button"
                            class="esc-pill"
                            aria-label=${this._i18n.closeAria}
                            @click=${this._closeModal}
                        >ESC</button>
                    </div>
                </div>

                <!-- Visually-hidden live region: announces the result count to
                     screen readers as the list updates (sighted users just see
                     it appear). Rendered unconditionally so the region is already
                     in the a11y tree before its text changes — a live region
                     inserted at the same time as its content isn't reliably
                     announced. -->
                <div class="sr-only" role="status" aria-live="polite" aria-atomic="true">
                    ${this._resultsAnnouncement()}
                </div>

                <div class="filter-section">
                    ${this._renderFilters()}
                </div>
                ${this._renderResults()}

                <div slot="footer" class="footer">
                    <ol-button
                        variant="primary"
                        ?disabled=${this._query.trim().length < MIN_QUERY_LENGTH}
                        ?loading=${this._seeAllLoading}
                        @click=${this._onSeeAllResults}
                    >${this._seeAllLabel()}</ol-button>
                </div>
            </ol-dialog>
        `;
    }

    _renderFilters() {
        // Binary availability: off = "All books", on = "Readable Only". The
        // label comes from the (localized) 'readable' option so the toggle reads
        // the same as the old dropdown's Readable Only row.
        const readable = this._availabilityOptions.find(o => o.value === 'readable');
        // The sublabel shows how many of the current query's results are readable,
        // scoped to the query + language. We only show it once a search lands and a
        // live count is in hand — before that there's no honest number to display
        // (the whole-corpus figure ignores the query/language), so we show nothing.
        const sublabel = this._hasSearched && typeof this._readableCount === 'number'
            ? this._readableCount.toLocaleString()
            : '';
        // "Clear all" only earns its place once there's more than one filter to
        // clear — i.e. readable-only is on *and* a language is selected. With a
        // single filter active the user just toggles/deselects it directly.
        const showClearAll = this._availability === 'readable' && this._languages.length > 0;
        return html`
            <div class="filters" role="group" aria-label=${this._i18n.filtersAria}>
                <ol-toggle
                    variant="card"
                    label=${readable?.label ?? this._i18n.availabilityLabel}
                    sublabel=${sublabel}
                    ?checked=${this._availability === 'readable'}
                    @ol-toggle-change=${this._onAvailabilityToggle}
                ></ol-toggle>
                <ol-select-popover
                    label=${this._i18n.languageLabel}
                    placeholder=${this._i18n.languagePlaceholder}
                    unselected-heading=${this._i18n.languageHeading}
                    .items=${this._languageItems}
                    .selected=${this._languages}
                    @ol-select-popover-change=${this._onLanguagesChange}
                ></ol-select-popover>
                ${showClearAll ? html`
                    <button
                        type="button"
                        class="clear-all"
                        @click=${this._clearAllFilters}
                    >${this._i18n.clearAll}</button>
                ` : nothing}
            </div>
        `;
    }

    _renderResults() {
        if (!this._shouldAutocomplete()) {
            return this._recentSearches.length > 0
                ? this._renderRecentSearches()
                : html`<div class="results"></div>`;
        }

        if (this._loading && this._results.length === 0) {
            // Strip any trailing ellipsis/period(s) from the (translated) label
            // so the animated dots that follow aren't doubled up.
            const searchingLabel = this._i18n.searching.replace(/[.…。]+$/, '');
            return html`<div class="results"><div class="loading"
                >${searchingLabel}<span class="loading-dots" aria-hidden="true"><span class="dot">.</span><span class="dot">.</span><span class="dot">.</span></span></div></div>`;
        }

        if (this._results.length === 0 && this._hasSearched) {
            return html`<div class="results"><div class="empty">${this._i18n.noResults}</div></div>`;
        }

        return html`
            <div class="results ${this._navigatingKey ? 'is-navigating' : ''}" @keydown=${this._onResultsKeydown}>
                ${this._authorSuggestions.length ? html`
                    <ul class="results-list author-suggestion">
                        ${repeat(this._authorSuggestions, a => a.key, a => this._renderAuthorSuggestion(a))}
                    </ul>
                ` : nothing}
                <h3 class="results-heading">${this._i18n.topResults}</h3>
                <ul class="results-list">${repeat(this._results, r => r.key, r => this._renderResult(r))}</ul>
            </div>
        `;
    }

    _renderRecentSearches() {
        return html`
            <div class="results" @keydown=${this._onResultsKeydown}>
                <h3 class="results-heading">${this._i18n.recentSearches}</h3>
                <ul class="results-list">
                    ${repeat(this._recentSearches, s => s, s => html`
                        <li>
                            <div
                                class="result recent-result"
                                role="button"
                                tabindex="0"
                                @click=${() => this._onRecentSearchClick(s)}
                                @keydown=${(e) => this._onRecentSearchKeydown(e, s)}
                            >
                                <span class="result__recent-icon" aria-hidden="true">
                                    ${SearchModal._clockIcon}
                                </span>
                                <span class="result__meta">
                                    <span class="result__title">${s}</span>
                                </span>
                                <button
                                    type="button"
                                    class="result__remove-recent"
                                    aria-label=${sprintf(this._i18n.removeRecent, s)}
                                    @click=${(e) => { e.stopPropagation(); this._recentSearches = removeRecentSearch(s); }}
                                >${SearchModal._closeIcon}</button>
                            </div>
                        </li>
                    `)}
                </ul>
            </div>
        `;
    }

    // Clicking a recent-search row fills the input and kicks off a search,
    // rather than hard-navigating, so the patron sees inline results first.
    _onRecentSearchClick(query) {
        this._query = query;
        const input = this.renderRoot.querySelector('.search-input');
        if (input) input.value = query;
        this._loading = true;
        this._debouncedFetch();
    }

    // role="button" rows activate on Enter and Space. Keydowns bubbling up
    // from the nested remove button are ignored.
    _onRecentSearchKeydown(e, query) {
        if (e.target !== e.currentTarget) return;
        if (e.key !== 'Enter' && e.key !== ' ') return;
        e.preventDefault(); // keep Space from scrolling the results
        this._onRecentSearchClick(query);
    }

    // Save the current query to recent searches. Called before any navigation.
    _saveCurrentSearch() {
        const trimmed = this._query.trim();
        if (trimmed.length < MIN_QUERY_LENGTH) return;
        saveRecentSearch(trimmed);
        this._recentSearches = readRecentSearches();
    }

    // A "go to the author page" row shown above the works for each top-result
    // author the query names (see deriveAuthors). The whole row is a single link
    // to the author page, so it's a plain anchor (no nested-link concern).
    _renderAuthorSuggestion(author) {
        const href = `/authors/${author.key}`;
        return html`<li>
                <a
                    class="result ${this._navigatingKey === href ? 'is-target' : ''}"
                    href=${href}
                    @click=${(e) => this._onResultPress(e, href)}
                >
                    <span class="result__avatar">
                        ${SearchModal._personIcon}
                        <img
                            class="result__avatar-photo"
                            src="https://covers.openlibrary.org/a/olid/${author.key}-S.jpg?default=false"
                            srcset="https://covers.openlibrary.org/a/olid/${author.key}-M.jpg?default=false 2x"
                            alt=""
                            loading="lazy"
                            @error=${this._onAvatarError}
                        />
                        <span class="result__spinner" aria-hidden="true"></span>
                    </span>
                    <span class="result__meta">
                        <span class="result__title">${author.name}</span>
                        <span class="result__author">${this._i18n.authorLabel}</span>
                    </span>
                </a>
            </li>`;
    }

    // Direct archive.org cover URLs (used as the IA fallback in _renderResult)
    // have no `?default=` graceful-fallback param, so a missing scan 404s with a
    // broken image. Swap in the placeholder once; the guard avoids a reload loop
    // if the placeholder itself ever fails.
    _onCoverError(e) {
        const img = e.currentTarget;
        if (img.dataset.coverFallback) return;
        img.dataset.coverFallback = '1';
        img.srcset = '';
        img.src = COVER_PLACEHOLDER;
    }

    // Whether an `ebook_access` value earns the "Readable" badge for this patron.
    // `public`/`borrowable` are readable for everyone; `printdisabled` only for
    // patrons verified for print-disabled access — mirroring the server's
    // per-patron readable filter/count (get_fulltext_min) so the badge and the
    // "Readable Only" count never disagree about the same book.
    _isReadableAccess(access) {
        if (READABLE_ACCESS.has(access)) return true;
        return this._printDisabled && access === PRINT_DISABLED_ACCESS;
    }

    // The whole row is a single link to the work — the author is surfaced in
    // its own suggestion row, so there's no separate author link here (which
    // also keeps this a plain anchor with no nested-link concern).
    _renderResult(work) {
        // Promote the hit to the specific edition that best matches the query —
        // its OL edition page — so the result opens on (and displays) that copy
        // rather than the work page. The edition is editions.docs[0] from the
        // block-join subquery, ranked by text relevance + a site-language boost
        // and already constrained to any active availability/language filter at
        // the edition level (see SEARCH_FIELDS note). Promotion is unconditional:
        // a query like "kammer" should land on the matching German edition whether
        // or not Readable Only is on.
        //
        // We render the row from that edition's own title and cover — not the
        // work's — so the row matches where it links. The work's display title is
        // its canonical (often English) title, but the matched edition can be in
        // another language: a German edition wins "kammer", a French/Persian scan
        // wins "chambre des secrets". Showing the work title over an edition link
        // would send the patron to a surprise-language book — and clicking the
        // bare work would instead land on the work page's own "best edition" pick
        // (get_best_edition), unrelated to their query. Falls back to the work
        // (both link and display) when the block-join returns no edition (e.g.
        // editions disabled via the SOLR_EDITIONS flag, or an edition-less work).
        const edition = work.editions?.docs?.[0];
        const display = edition?.key ? edition : work;
        const href    = display === edition ? edition.key : work.key;

        // Author and year stay work-level: authors aren't indexed on editions,
        // and first_publish_year is the work's original-publication year.
        const author = work.author_name?.[0] || '';
        const year   = work.first_publish_year || '';

        // Whether the promoted edition — the copy weighted toward the patron's
        // site language, and the one this row opens — is itself readable for this
        // patron. Drives both the badge and the language hint below.
        const editionReadable = this._isReadableAccess(edition?.ebook_access);

        // "Readable" badge. When an edition is promoted, the badge reflects
        // whether *that* copy is readable — not the work-level ebook_access
        // aggregate. So a work whose only readable copies are in another language
        // no longer flashes "Readable" off a copy the patron can't read in their
        // language: with Readable Only off the language-matched edition wins
        // promotion and, when it isn't readable, the row carries no badge. (Turn
        // Readable Only on and the subquery instead promotes the readable foreign
        // copy, which earns the badge plus an "In <language>" hint.) Falls back to
        // the work-level aggregate only when no edition was promoted — editions
        // disabled via SOLR_EDITIONS, or an edition-less work — so those still
        // badge from the work.
        const readable = edition ? editionReadable : this._isReadableAccess(work.ebook_access);

        // Name the promoted edition's language when it isn't the patron's site
        // language, so they see the readable copy this row opens is "In French",
        // etc. Gated on the promoted edition's own readability (so we only name a
        // language for a copy we've confirmed readable) and independent of the
        // toggle. Since the badge now keys off this same edition, the hint never
        // shows without it. null on a language match, a chosen language filter, or
        // an unknown site language.
        //
        // Edge (rare, accepted): Solr promotes one edition via a soft
        // site-language boost (works.py bq `language:{user_lang}^40`), not a hard
        // sort, and we read only that edition (editions.rows=1). A strongly
        // text-matching readable foreign edition can outrank a readable
        // same-language copy, so the hint may name a foreign language even when a
        // readable site-language copy exists deeper in the work. Eliminating it
        // would mean fetching every readable edition's language, which we don't.
        const otherLang = editionReadable
            ? readableLanguageMismatch({
                edition,
                languages: this._languages,
                siteLanguage: this._siteLanguage,
                options: this._languageItems,
            })
            : null;

        // Cover resolution mirrors the rest of the site (Edition.get_cover_url →
        // get_ia_cover): prefer an OL-uploaded cover (cover_i), else fall back to
        // the Internet Archive scan (ia), else the placeholder — resolved from the
        // displayed record so the cover matches the title and link. Without the IA
        // fallback, IA-only books (lending/print-disabled scans with no uploaded
        // cover) render a blank placeholder here while every other surface shows
        // the scanned cover. The trailing work-edition `ia` keeps that fallback
        // for the un-promoted work row too. See issue #12893.
        const ia = display.ia?.[0] || work.ia?.[0] || work.editions?.docs?.[0]?.ia?.[0];
        let cover, coverSrcset;
        if (display.cover_i) {
            cover       = `https://covers.openlibrary.org/b/id/${display.cover_i}-S.jpg`;
            coverSrcset = `https://covers.openlibrary.org/b/id/${display.cover_i}-M.jpg 2x`;
        } else if (ia) {
            // IA cover size map matches get_ia_cover: S = 116×58, M = 180×360.
            // archive.org URLs have no `?default=` fallback, so a missing scan
            // 404s and the <img> @error handler swaps in the placeholder.
            cover       = `https://archive.org/download/${ia}/page/cover_w116_h58.jpg`;
            coverSrcset = `https://archive.org/download/${ia}/page/cover_w180_h360.jpg 2x`;
        } else {
            cover       = COVER_PLACEHOLDER;
            coverSrcset = nothing;
        }

        return html`<li>
                <a
                    class="result ${this._navigatingKey === href ? 'is-target' : ''}"
                    href=${href}
                    @click=${(e) => this._onResultPress(e, href)}
                >
                    <span class="result__cover-link">
                        <img class="result__cover" src=${cover} srcset=${coverSrcset} alt="" loading="lazy" width="36" height="50" @error=${this._onCoverError}/>
                        <span class="result__spinner" aria-hidden="true"></span>
                    </span>
                    <span class="result__meta">
                        <span class="result__title">${display.title || work.title || this._i18n.untitled}</span>
                        ${author ? html`<span class="result__author">${author}</span>` : nothing}
                        ${year ? html`<span class="result__year">${year}</span>` : nothing}
                    </span>
                    ${readable ? html`<span class="result__access-col">
                        <span class="result__access">${this._i18n.accessReadable}</span>
                        ${otherLang ? html`<span class="result__lang">${sprintf(this._i18n.inLanguage, otherLang)}</span>` : nothing}
                    </span>` : nothing}
                </a>
            </li>`;
    }

    // The footer button shows the actual hit count once a search lands
    // (e.g. "See all 1,234 results"); the bare "See all results" label is
    // used before any results are in (initial open, query under MIN_QUERY_LENGTH,
    // or fetch error).
    _seeAllLabel() {
        const n = this._numFound;
        if (typeof n !== 'number' || n <= 0) return this._i18n.seeAll;
        const template = n === 1 ? this._i18n.seeAllOne : this._i18n.seeAllMany;
        return sprintf(template, n.toLocaleString());
    }

    // ── Event handlers ───────────────────────────────────────────────────

    _onDialogOpened() {
        this.renderRoot.querySelector('.search-input')?.focus();
    }

    _onDialogClosed() {
        this.open = false;
        this._navigatingKey = null;
        // Drop any in-flight spinner so a search interrupted by closing the
        // modal doesn't show a stale "Searching…" on reopen. The next keystroke
        // would clear it, but reopening to a frozen spinner looks broken.
        this._loading = false;
        this._seeAllLoading = false;
    }

    // A result is a native anchor, so pressing it navigates the whole window.
    // The new page can take a beat to start painting; flag the chosen row so it
    // shows its loading treatment (cover spinner, dimmed siblings) during that
    // gap. Modified clicks (open in new tab/window) don't navigate this page —
    // leave them untreated.
    _onResultPress(e, key) {
        if (e.defaultPrevented || e.button !== 0) return;
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        this._saveCurrentSearch();
        this._navigatingKey = key;
    }

    // The author photo is requested with ?default=false, so a missing photo
    // 404s and fires this — hide the <img> to reveal the person glyph beneath.
    _onAvatarError(e) { e.target.hidden = true; }

    _onDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
    }

    _onDrop(e) {
        e.preventDefault();
        const text = e.dataTransfer.getData('text/plain');
        if (!text) return;
        this._query = text;
        const input = this.renderRoot.querySelector('.search-input');
        if (input) input.value = text;
        if (this._shouldAutocomplete()) {
            this._loading = true;
            this._debouncedFetch();
        }
    }

    _onQueryInput(e) {
        this._query = e.target.value;
        this._navigatingKey = null;
        if (!this._shouldAutocomplete()) {
            this._resetResults({ hasSearched: false });
            return;
        }
        // Drop the previous query's author suggestion immediately. Stale book
        // results linger for the debounce window (which avoids a list flicker),
        // but an author row names one specific person — keeping it under a new,
        // unrelated query is actively misleading. It repopulates when the fetch
        // resolves.
        this._authorSuggestions = [];
        this._loading = true;
        this._debouncedFetch();
    }

    _onInputKeydown(e) {
        if (e.key === 'Enter' && this._query.trim().length >= MIN_QUERY_LENGTH) {
            e.preventDefault();
            this._onSeeAllResults();
            return;
        }
        // ArrowDown/Up step from the input into the result rows — ↓ to the first
        // row, ↑ to the last — so the suggestions are reachable by arrow key the
        // way the old header autocomplete was, alongside (not instead of) Tab.
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            const rows = this._focusableRows();
            if (rows.length === 0) return;
            e.preventDefault();
            (e.key === 'ArrowDown' ? rows[0] : rows[rows.length - 1]).focus();
        }
    }

    // The actionable rows in the results region (book + author links and recent-
    // search rows), in DOM order. Both carry the `.result` class and are natively
    // focusable, so arrow navigation just walks this list.
    _focusableRows() {
        return [...this.renderRoot.querySelectorAll('.results .result')];
    }

    // ArrowUp/Down move focus between adjacent rows; stepping off either end
    // returns focus to the input so the patron can keep editing the query.
    // (Enter on a focused row activates the native link/button as usual.)
    _onResultsKeydown(e) {
        if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
        const row = e.target.closest('.result');
        if (!row) return;
        const rows = this._focusableRows();
        const idx  = rows.indexOf(row);
        if (idx === -1) return;
        e.preventDefault();
        const next = e.key === 'ArrowDown' ? idx + 1 : idx - 1;
        if (next < 0 || next >= rows.length) {
            this.renderRoot.querySelector('.search-input')?.focus();
        } else {
            rows[next].focus();
        }
    }

    // Screen-reader announcement for the live region: the result count once a
    // search lands, "no results" when a search came back empty, and nothing
    // while idle/typing/loading (so the region stays quiet until there's news).
    _resultsAnnouncement() {
        if (!this._shouldAutocomplete()) return '';
        if (this._results.length === 0) {
            return this._hasSearched && !this._loading ? this._i18n.noResults : '';
        }
        const shown = this._results.length;
        const total = typeof this._numFound === 'number' ? this._numFound : shown;
        return sprintf(this._i18n.resultsAnnounce, shown.toLocaleString(), total.toLocaleString());
    }

    _onAvailabilityToggle(e) {
        this._setAvailability(e.detail.checked ? 'readable' : DEFAULT_AVAILABILITY);
    }

    _onLanguagesChange(e) {
        this._languages = [...e.detail.selected];
        ssSet(SS_LANGUAGES_KEY, JSON.stringify(this._languages));
        this._refetchIfActive();
    }

    _setAvailability(value) {
        this._availability = value;
        ssSet(SS_AVAILABILITY_KEY, value);
        this._refetchIfActive();
    }

    _clearAllFilters() {
        this._availability = DEFAULT_AVAILABILITY;
        this._languages    = [];
        ssSet(SS_AVAILABILITY_KEY, DEFAULT_AVAILABILITY);
        ssSet(SS_LANGUAGES_KEY, JSON.stringify([]));
        this._refetchIfActive();
    }

    _refetchIfActive() {
        if (this._shouldAutocomplete()) {
            this._loading = true;
            this._debouncedFetch();
        }
    }

    _onSeeAllResults() {
        this._saveCurrentSearch();
        const url = this._buildSearchUrl();
        if (!url) return;
        // Flag the footer button so its spinner shows during the navigation
        // delay (the page keeps painting until /search arrives). Mirrors how a
        // pressed result sets _navigatingKey before the window navigates.
        this._seeAllLoading = true;
        window.location.assign(url);
    }

    // ── Data layer ───────────────────────────────────────────────────────

    // Whether the current query should trigger the header autocomplete. Mirrors
    // the legacy SearchBar gate: long enough, and not a bare autocomplete stopword.
    _shouldAutocomplete() {
        const trimmed = this._query.trim();
        return trimmed.length >= MIN_QUERY_LENGTH && !AUTOCOMPLETE_STOPWORDS.has(trimmed.toLowerCase());
    }

    _fetchResults() {
        const trimmed = this._query.trim();
        // Nothing to fetch (query too short, or a stopword) — make sure we don't
        // leave a spinner spinning. _onRecentSearchClick can land here with a
        // saved query that no longer autocompletes.
        if (!this._shouldAutocomplete()) {
            this._loading = false;
            return;
        }

        const url      = this._buildSearchJsonUrl(trimmed);
        const fetchKey = url;
        this._activeFetchKey = fetchKey;

        // When the readable filter is off, the main numFound is the all-books
        // total and says nothing about the readable subset, so fetch that count
        // separately. When it's on, the main numFound already *is* the readable
        // count (set in the .then below) — no extra round-trip needed.
        if (this._availability !== 'readable') {
            this._fetchReadableCount(trimmed, fetchKey);
        }

        fetch(url)
            .then(r => r.ok ? r.json() : Promise.reject(new Error(`Search failed: ${r.status}`)))
            .then(data => {
                if (this._activeFetchKey !== fetchKey) return;
                this._results           = data.docs || [];
                this._authorSuggestions = deriveAuthors(this._results, trimmed);
                this._numFound          = typeof data.numFound === 'number' ? data.numFound : null;
                if (this._availability === 'readable') this._readableCount = this._numFound;
                this._loading           = false;
                this._hasSearched       = true;
            })
            .catch(() => {
                if (this._activeFetchKey !== fetchKey) return;
                this._resetResults({
                    hasSearched: true,
                    clearReadableCount: this._availability === 'readable',
                });
            });
    }

    // Counts how many of the current query's hits are readable (has_fulltext),
    // for the "Readable Only" toggle sublabel. limit=0 returns just the count —
    // no docs — so it's a cheap second round-trip. The `editions` field opts
    // into the edition-level block-join so this count matches what flipping the
    // toggle on actually yields (see the SEARCH_FIELDS note above). Shares the
    // main search's fetchKey so a stale count never lands after the query moves on.
    _fetchReadableCount(query, fetchKey) {
        fetch(this._buildReadableCountUrl(query))
            .then(r => r.ok ? r.json() : Promise.reject(new Error(`Count failed: ${r.status}`)))
            .then(data => {
                if (this._activeFetchKey !== fetchKey) return;
                this._readableCount = typeof data.numFound === 'number' ? data.numFound : null;
            })
            .catch(() => {
                if (this._activeFetchKey !== fetchKey) return;
                this._readableCount = null;
            });
    }

    // q + mode + spellcheck shared by every /search.json request the modal makes;
    // callers layer on limit/fields and the availability/language filters.
    _baseSearchParams(query) {
        const params = new URLSearchParams();
        params.set('q', query);
        params.set('_spellcheck_count', '0');
        params.set('mode', searchMode.read());
        return params;
    }

    _buildSearchJsonUrl(query) {
        const params = this._baseSearchParams(query);
        params.set('limit', String(RESULTS_LIMIT));
        params.set('fields', SEARCH_FIELDS.join(','));
        this._appendFilterParams(params);
        return `/search.json?${params.toString()}`;
    }

    // Same query + language context as the main search, but forced to the
    // readable subset and limit=0 so Solr returns only the count.
    _buildReadableCountUrl(query) {
        const params = this._baseSearchParams(query);
        params.set('limit', '0');
        params.set('fields', 'key,editions');
        this._appendFilterParams(params, 'readable');
        return `/search.json?${params.toString()}`;
    }

    _buildSearchUrl() {
        const trimmed = this._query.trim();
        if (trimmed.length < MIN_QUERY_LENGTH) return null;

        const params = new URLSearchParams();
        params.set('q', trimmed);
        params.set('mode', searchMode.read());
        this._appendFilterParams(params);
        return `/search?${params.toString()}`;
    }

    // `availability` defaults to the patron's current selection; the readable
    // count query forces 'readable' so it mirrors the main search's language
    // context while overriding only the availability subset.
    _appendFilterParams(params, availability = this._availability) {
        const availParams = AVAILABILITY_TO_PARAMS[availability] || {};
        for (const [key, value] of Object.entries(availParams)) {
            params.append(key, value);
        }
        for (const lang of this._languages) {
            params.append('language', lang);
        }
    }

    // ── Static SVGs ──────────────────────────────────────────────────────

    static _clockIcon = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`;

    static _searchIcon = html`<svg class="search-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>`;

    static _closeIcon = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;

    static _backIcon = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/></svg>`;

    static _personIcon = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;
}

customElements.define('ol-search-modal', SearchModal);

/**
 * Mounts a single SearchModal and wires it to the header search trigger button.
 * Idempotent – safe to call multiple times with the same element.
 * @param {HTMLButtonElement} trigger
 * @returns {SearchModal|null}
 */
export function initSearchModal(trigger) {
    if (!trigger || trigger.dataset.olSearchModalAttached === 'true') {
        return null;
    }

    const modal = document.createElement('ol-search-modal');

    // Translated strings are rendered into the trigger's data-i18n
    // (availability options) and data-i18n-ui (chrome) attributes by
    // search/availability_i18n.html and search/search_modal_i18n.html. Apply
    // them before the modal mounts so the first render is already localized.
    modal._availabilityOptions = availabilityOptionsFromElement(trigger);
    modal._i18n = searchModalStringsFromElement(trigger);
    // The patron's site language as a MARC code, matching Solr's `language`
    // field so the modal can compare it against a readable edition's language.
    // The trigger carries the 2-letter UI code (data-search-lang); map it to
    // MARC here. '' when absent or not a known UI language.
    modal._siteLanguage = siteLanguageToMarc(trigger.dataset.searchLang || '');
    // Whether the patron is verified for print-disabled access (data-print-disabled,
    // from ctx.user.is_printdisabled()). Widens the "Readable" badge to
    // printdisabled scans for these patrons, matching the readable count.
    modal._printDisabled = trigger.dataset.printDisabled === 'true';

    document.body.appendChild(modal);
    modal.attachToTrigger(trigger);
    trigger.dataset.olSearchModalAttached = 'true';
    return modal;
}
