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
    availabilityOptionsFromElement,
    readStoredLanguages,
    searchModalStringsFromElement,
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
const SEARCH_FIELDS = ['key', 'cover_i', 'title', 'subtitle', 'author_name', 'author_key', 'first_publish_year', 'editions'];

const RESULTS_LIMIT     = 10;
// Matches the legacy SearchBar autocomplete threshold: fire the header
// autocomplete only at 3+ chars (see _shouldAutocomplete for the "the" skip).
const MIN_QUERY_LENGTH  = 3;
const COVER_PLACEHOLDER = '/static/images/icons/avatar_book-sm.png';

// The bare common-word "the" matches almost everything and isn't worth a Solr
// round-trip, so the legacy SearchBar skipped it for autocomplete. Navigation
// to /search is still allowed for it (handled by the length-only gates).
const AUTOCOMPLETE_STOPWORDS = new Set(['the']);

function ssGet(key)        { try { return sessionStorage.getItem(key); }        catch { return null; } }
function ssSet(key, value) { try { sessionStorage.setItem(key, value); }        catch { /* ignore */ } }

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

        /* ── Search input row ──────────────────────────────────────── */

        .bar {
            display: flex;
            align-items: center;
            gap: var(--spacing-sm);
            padding: var(--spacing-md) var(--spacing-lg);
            border-bottom: 1px solid var(--color-border-subtle);
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

        /* Drop the native type="search" clear affordance — the modal has its
           own close control and an empty field is cleared by deleting text. */
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
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 0.04em;
            cursor: pointer;
            white-space: nowrap;
        }

        @media (hover: hover) and (pointer: fine) {
            .esc-pill:hover { background: var(--lightest-grey); }
        }

        .esc-pill:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        @media (hover: none) and (pointer: coarse) { .esc-pill { display: none; } }

        /* ── Close button (mobile) ─────────────────────────────────── */

        /* Touch devices don't have an Esc key, so the ESC pill (above) is
           replaced by an explicit close affordance in the same slot. */
        .close-btn {
            flex-shrink: 0;
            display: none;
            align-items: center;
            justify-content: center;
            width: 36px;
            height: 36px;
            margin-right: calc(var(--spacing-sm) * -1);
            background: transparent;
            border: none;
            border-radius: var(--border-radius-button);
            color: var(--accessible-grey);
            cursor: pointer;
        }

        .close-btn svg {
            width: 22px;
            height: 22px;
        }

        .close-btn:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        @media (hover: none) and (pointer: coarse) { .close-btn { display: inline-flex; } }

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
            padding: var(--spacing-xs) 0 var(--spacing-sm);
            border-bottom: 1px solid var(--color-border-subtle);
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
            outline: 2px solid var(--color-focus-ring);
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
            padding-block: 4px;
            margin-block: -4px;
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
            padding: var(--spacing-xs) 0;
        }

        .results-heading {
            margin: 0;
            padding: var(--spacing-sm) var(--spacing-lg) var(--spacing-2xs);
            color: var(--accessible-grey);
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
        }

        .results-list {
            list-style: none;
            margin: 0;
            padding: 0;
        }

        /* Hairline above and below every row. Deliberately fainter than the
           modal's section dividers (--color-border-subtle) so the lines read
           as texture rather than structure. Adjacent rows share one line. */
        .results-list li { border-top: 1px solid var(--lightest-grey); }
        .results-list li:last-child { border-bottom: 1px solid var(--lightest-grey); }

        /* Sets the author suggestion apart from the "Top results" works below.
           The row hairlines draw the dividing line; this just adds air. */
        .author-suggestion { margin-bottom: var(--spacing-2xs); }

        .result {
            display: flex;
            align-items: center;
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
            box-shadow: inset 2px 0 0 var(--color-focus-ring);
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
            border-radius: 50%;
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
            font-size: 14px;
            line-height: 1.35;
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
            font-size: 12px;
            font-weight: 400;
        }

        .empty, .loading {
            padding: var(--spacing-lg) var(--spacing-lg);
            color: var(--accessible-grey);
            font-size: 14px;
            text-align: center;
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

        .result__recent-icon {
            flex-shrink: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            width: 36px; /* matches the cover column so the text gutter lines up */
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
            outline: 2px solid var(--color-focus-ring);
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
           holds full opacity while the rest dim back, its cover darkens under
           a spinner, and the row scales down — matching the header search
           field's press feedback (scale 0.985). */
        .results.is-navigating .result { opacity: 0.4; }

        .results.is-navigating .result.is-target {
            opacity: 1;
            background: var(--lightest-grey);
            transform: scale(0.985);
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
            border-radius: 50%;
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
            border-top: 1px solid var(--color-border-subtle);
        }

        .see-all {
            padding: var(--spacing-sm) var(--spacing-lg);
            background: var(--primary-blue);
            border: 1px solid var(--primary-blue);
            border-radius: var(--border-radius-button);
            color: var(--white);
            font: inherit;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: filter 150ms ease;
        }

        @media (hover: hover) and (pointer: fine) {
            .see-all:hover { filter: brightness(1.08); }
        }

        .see-all:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        .see-all:disabled {
            opacity: 0.45;
            cursor: not-allowed;
        }

        @media (prefers-reduced-motion: reduce) { .see-all { transition: none; } }

        /* ── Mobile overrides ──────────────────────────────────────── */

        @media (max-width: 767px) {
            .search-input { font-size: 16px; }
            .results { max-height: none; flex: 1; }
            /* The footer is pinned by the dialog's flex column (it sits
               outside the scrolling body). */
            .footer { background: var(--white); }

            /* Inset, rounded search field with the close (X) sitting outside it. */
            .bar {
                padding: var(--spacing-md) var(--spacing-md) var(--spacing-xs);
                border-bottom: none;
            }
            .search-field {
                padding: var(--spacing-sm) var(--spacing-md);
                border: 1px solid var(--color-border-subtle);
                border-radius: var(--border-radius-xl);
            }
            .close-btn { margin-right: 0; }
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

        // Availability is now a binary All / Readable Only toggle. Honor only an
        // explicit stored 'readable'; everything else — no preference, or a
        // legacy 'open'/'borrowable' value from before the toggle — collapses to
        // the default 'all' (toggle off).
        const _storedAvailability = ssGet(SS_AVAILABILITY_KEY);
        this._availability = _storedAvailability === 'readable' ? 'readable' : DEFAULT_AVAILABILITY;
        this._languages    = readStoredLanguages();

        this._recentSearches = readRecentSearches();

        this._debouncedFetch = debounce(() => this._fetchResults(), 250, false);
        this._activeFetchKey = null;
        this._allLangsLoaded = false;
    }

    connectedCallback() {
        super.connectedCallback();
        // The back button can restore this page (and modal) from the bfcache
        // with a row still flagged as navigating — clear it so its spinner
        // doesn't linger on a page the user has returned to.
        this._onPageShow = () => { this._navigatingKey = null; };
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
                aria-label=${this._i18n.dialogAria}
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
                    <div class="search-field">
                        ${SearchModal._searchIcon}
                        <input
                            type="search"
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
                        />
                        <button
                            type="button"
                            class="esc-pill"
                            aria-label=${this._i18n.closeAria}
                            @click=${this._closeModal}
                        >ESC</button>
                    </div>
                    <button
                        type="button"
                        class="close-btn"
                        aria-label=${this._i18n.closeAria}
                        @click=${this._closeModal}
                    >${SearchModal._closeIcon}</button>
                </div>

                <div class="filter-section">
                    ${this._renderFilters()}
                </div>
                ${this._renderResults()}

                <div slot="footer" class="footer">
                    <button
                        type="button"
                        class="see-all"
                        ?disabled=${this._query.trim().length < MIN_QUERY_LENGTH}
                        @click=${this._onSeeAllResults}
                    >${this._seeAllLabel()}</button>
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
            return html`<div class="results"><div class="loading">${this._i18n.searching}</div></div>`;
        }

        if (this._results.length === 0 && this._hasSearched) {
            return html`<div class="results"><div class="empty">${this._i18n.noResults}</div></div>`;
        }

        return html`
            <div class="results ${this._navigatingKey ? 'is-navigating' : ''}">
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
            <div class="results">
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

    // The whole row is a single link to the work — the author is surfaced in
    // its own suggestion row, so there's no separate author link here (which
    // also keeps this a plain anchor with no nested-link concern).
    _renderResult(work) {
        const author = work.author_name?.[0] || '';
        const year   = work.first_publish_year || '';
        const cover  = work.cover_i
            ? `https://covers.openlibrary.org/b/id/${work.cover_i}-S.jpg`
            : COVER_PLACEHOLDER;
        const coverSrcset = work.cover_i
            ? `https://covers.openlibrary.org/b/id/${work.cover_i}-M.jpg 2x`
            : nothing;

        // When Readable Only is on, promote the hit to the specific edition that
        // satisfied the filter — its OL edition page — so the result opens on the
        // readable copy rather than the work page, while keeping the user on OL.
        // The edition comes from the block-join subquery, which already applied
        // both the availability and language filters at the edition level (see
        // SEARCH_FIELDS note), so editions.docs[0] is the readable, in-language
        // copy. Falls back to the work page when no such edition is present.
        let href = work.key;
        if (this._availability === 'readable') {
            const editionKey = work.editions?.docs?.[0]?.key;
            if (editionKey) href = editionKey;
        }

        return html`<li>
                <a
                    class="result ${this._navigatingKey === href ? 'is-target' : ''}"
                    href=${href}
                    @click=${(e) => this._onResultPress(e, href)}
                >
                    <span class="result__cover-link">
                        <img class="result__cover" src=${cover} srcset=${coverSrcset} alt="" loading="lazy" width="36" height="50"/>
                        <span class="result__spinner" aria-hidden="true"></span>
                    </span>
                    <span class="result__meta">
                        <span class="result__title">${work.title || this._i18n.untitled}</span>
                        ${author ? html`<span class="result__author">${author}</span>` : nothing}
                        ${year ? html`<span class="result__year">${year}</span>` : nothing}
                    </span>
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

    _onQueryInput(e) {
        this._query = e.target.value;
        this._navigatingKey = null;
        if (!this._shouldAutocomplete()) {
            this._results           = [];
            this._authorSuggestions = [];
            this._numFound          = null;
            this._readableCount     = null;
            this._loading           = false;
            this._hasSearched       = false;
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
        }
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
        if (url) window.location.assign(url);
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
                this._results           = [];
                this._authorSuggestions = [];
                this._numFound          = null;
                if (this._availability === 'readable') this._readableCount = null;
                this._loading           = false;
                this._hasSearched       = true;
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

    _buildSearchJsonUrl(query) {
        const params = new URLSearchParams();
        params.set('q', query);
        params.set('limit', String(RESULTS_LIMIT));
        params.set('fields', SEARCH_FIELDS.join(','));
        params.set('_spellcheck_count', '0');
        params.set('mode', searchMode.read());
        this._appendFilterParams(params);
        return `/search.json?${params.toString()}`;
    }

    // Same query + language context as the main search, but forced to the
    // readable subset (has_fulltext) and limit=0 so Solr returns only the count.
    // Mirrors _buildSearchJsonUrl's params minus the result-shaping ones.
    _buildReadableCountUrl(query) {
        const params = new URLSearchParams();
        params.set('q', query);
        params.set('limit', '0');
        params.set('fields', 'key,editions');
        params.set('_spellcheck_count', '0');
        params.set('mode', searchMode.read());
        params.set('has_fulltext', 'true');
        for (const lang of this._languages) {
            params.append('language', lang);
        }
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

    _appendFilterParams(params) {
        const availParams = AVAILABILITY_TO_PARAMS[this._availability] || {};
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

    document.body.appendChild(modal);
    modal.attachToTrigger(trigger);
    trigger.dataset.olSearchModalAttached = 'true';
    return modal;
}
