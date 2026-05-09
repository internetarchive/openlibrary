import { LitElement, html, css, nothing } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import '../../../../components/lit/OlDialog.js';
import '../../../../components/lit/OlOptionsPopover.js';
import '../../../../components/lit/OlSelectPopover.js';
import { debounce } from '../nonjquery_utils.js';
import { mode as searchMode } from '../SearchUtils.js';
import { AVAILABILITY_OPTIONS, DEFAULT_AVAILABILITY, LANGUAGE_OPTIONS } from './constants.js';

/**
 * Maps availability filter values to /search query params. The backend
 * recognizes `has_fulltext` and `public_scan` as facet-rewrite inputs
 * (see `openlibrary/plugins/worksearch/schemes/works.py` `facet_rewrites`),
 * which Solr translates to `ebook_access:[borrowable TO *]` and
 * `ebook_access:public` respectively. There's no public param for
 * "borrowable only" specifically, so we splice an `ebook_access:borrowable`
 * Solr clause directly into the `q` (see `_buildSearchJsonUrl`).
 */
const AVAILABILITY_TO_PARAMS = {
    all: {},
    readable: { has_fulltext: 'true' },
    borrowable: {},  // handled via q clause below
    open: { public_scan: 'true' },
};

/** Extra Solr `q` clause to AND into the user query for certain availability values. */
const AVAILABILITY_TO_Q_CLAUSE = {
    borrowable: 'ebook_access:borrowable',
};

/**
 * Solr fields requested for autocomplete results. Deliberately omits
 * `editions` even though the legacy SearchBar requests it: when
 * `editions:[subquery]` is in the field list, the worksearch backend
 * rewrites the work query to additionally require a matching edition
 * (see `WorkSearchScheme.process_user_query()` — the parent-block-join
 * filter). That silently drops works that match the user query only via
 * work-level fields like `series_name` or `subject` (e.g. `q=narnia`
 * loses every Narnia book because no edition contains "narnia"). For
 * autocomplete, completeness of the result set matters more than the
 * edition-level cover fallback.
 */
const SEARCH_FIELDS = [
    'key',
    'cover_i',
    'title',
    'subtitle',
    'author_name',
];

const RESULTS_LIMIT = 10;
const MIN_QUERY_LENGTH = 2;
const COVER_PLACEHOLDER = '/static/images/icons/avatar_book-sm.png';

/**
 * Header search modal. Replaces the legacy inline autocomplete dropdown.
 *
 * Mounts itself dynamically (no template change required) and attaches to
 * a trigger input via `attachToTrigger()`. Composes `<ol-dialog>`,
 * `<ol-options-popover>`, `<ol-select-popover>`, and `<ol-chip>` — owns
 * search query state, filter state, the /search.json fetch, and the URL
 * built when the user clicks "See all results".
 *
 * Per the building-components doc, this is an orchestrator (knows about
 * the search API and URL shape), not a design-system component.
 *
 * @element ol-search-modal
 *
 * @example
 * import { initSearchModal } from './SearchModal.js';
 * initSearchModal(document.querySelector('header .search-bar-input input'));
 */
export class SearchModal extends LitElement {
    static properties = {
        open: { type: Boolean, reflect: true },
        _query: { state: true },
        _availability: { state: true },
        _languages: { state: true },
        _results: { state: true },
        _loading: { state: true },
        _hasSearched: { state: true },
    };

    static styles = css`
        :host {
            font-family: var(--font-family-body);
            color: var(--darker-grey);
        }

        /* ── Header (search input row) ───────────────────────────── */

        .bar {
            display: flex;
            align-items: center;
            gap: var(--spacing-sm);
            padding: var(--spacing-md) var(--spacing-lg);
            border-bottom: 1px solid var(--color-border-subtle);
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
            font-size: 18px;
            line-height: 1.4;
        }

        .search-input::placeholder {
            color: var(--accessible-grey);
        }

        .search-input:focus {
            outline: none;
        }

        .esc-pill {
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
            .esc-pill:hover {
                background: var(--lightest-grey);
            }
        }

        .esc-pill:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        /* Hide ESC pill on touch devices — they have no ESC key */
        @media (hover: none) and (pointer: coarse) {
            .esc-pill {
                display: none;
            }
        }

        /* ── Selected filters chip row ───────────────────────────── */

        .chips {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: var(--spacing-sm);
            padding: var(--spacing-sm) var(--spacing-lg);
            border-bottom: 1px solid var(--color-border-subtle);
        }

        .chip-pill {
            display: inline-flex;
            align-items: center;
            gap: var(--spacing-2xs);
            padding: var(--spacing-2xs) var(--spacing-sm);
            background: hsla(202, 96%, 37%, 0.08);
            border: 1px solid hsla(202, 96%, 37%, 0.2);
            border-radius: var(--border-radius-pill);
            color: var(--link-blue);
            font: inherit;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
        }

        @media (hover: hover) and (pointer: fine) {
            .chip-pill:hover {
                background: hsla(202, 96%, 37%, 0.12);
            }
        }

        .chip-pill:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        .chip-pill__remove {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 14px;
            height: 14px;
            color: currentColor;
            opacity: 0.7;
        }

        .chip-pill__remove svg {
            width: 100%;
            height: 100%;
        }

        .clear-all {
            margin-left: auto;
            padding: var(--spacing-2xs) var(--spacing-sm);
            background: transparent;
            border: 1px solid transparent;
            border-radius: var(--border-radius-button);
            color: var(--dark-red);
            font: inherit;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
        }

        @media (hover: hover) and (pointer: fine) {
            .clear-all:hover {
                background: hsla(8, 70%, 44%, 0.08);
            }
        }

        .clear-all:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        /* ── Filter row ──────────────────────────────────────────── */

        .filters {
            display: flex;
            flex-wrap: wrap;
            gap: var(--spacing-sm);
            padding: var(--spacing-sm) var(--spacing-lg);
            border-bottom: 1px solid var(--color-border-subtle);
        }

        /* ── Results region ──────────────────────────────────────── */

        .results {
            flex: 1;
            min-height: 120px;
            max-height: 50vh;
            overflow-y: auto;
            padding: var(--spacing-sm) 0;
        }

        .results-heading {
            margin: 0;
            padding: var(--spacing-sm) var(--spacing-lg) var(--spacing-2xs);
            color: var(--accessible-grey);
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        .results-list {
            list-style: none;
            margin: 0;
            padding: 0;
        }

        .result {
            display: flex;
            align-items: center;
            gap: var(--spacing-md);
            padding: var(--spacing-sm) var(--spacing-lg);
            color: inherit;
            text-decoration: none;
        }

        @media (hover: hover) and (pointer: fine) {
            .result:hover {
                background: var(--icon-link-grey);
            }
        }

        .result:focus-visible {
            outline: none;
            background: var(--icon-link-grey);
            box-shadow: inset 2px 0 0 var(--color-focus-ring);
        }

        .result__cover {
            flex-shrink: 0;
            width: 40px;
            height: 56px;
            object-fit: cover;
            background: var(--lightest-grey);
            border-radius: var(--border-radius-thumbnail);
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

        .empty,
        .placeholder,
        .loading {
            padding: var(--spacing-xl) var(--spacing-lg);
            color: var(--accessible-grey);
            font-size: 14px;
            text-align: center;
        }

        /* ── Footer ──────────────────────────────────────────────── */

        .footer {
            display: flex;
            justify-content: flex-end;
            padding: var(--spacing-md) var(--spacing-lg);
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
        }

        @media (hover: hover) and (pointer: fine) {
            .see-all:hover {
                filter: brightness(1.1);
            }
        }

        .see-all:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        .see-all:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }
    `;

    constructor() {
        super();
        this.open = false;
        this._query = '';
        this._availability = DEFAULT_AVAILABILITY;
        this._languages = [];
        this._results = [];
        this._loading = false;
        this._hasSearched = false;

        this._debouncedFetch = debounce(() => this._fetchResults(), 250, false);
        this._activeFetchKey = null;
    }

    /**
     * Wires a header search input to open this modal on focus or click.
     * Suppresses the input's own focus side-effects by immediately moving
     * focus into the modal once it's open.
     * @param {HTMLInputElement} input
     */
    attachToTrigger(input) {
        if (!input) return;
        const openModal = (e) => {
            if (this.open) return;
            // Prevent the original input from holding focus — focus moves
            // into the modal's own input on open.
            e.preventDefault?.();
            input.blur();
            this._openModal();
        };
        input.addEventListener('focus', openModal);
        input.addEventListener('click', openModal);
    }

    _openModal() {
        this.open = true;
    }

    _closeModal() {
        this.open = false;
    }

    // ── Render ───────────────────────────────────────────────────

    render() {
        const hasFilters = this._availability !== DEFAULT_AVAILABILITY || this._languages.length > 0;

        return html`
            <ol-dialog
                ?open=${this.open}
                without-header
                fullscreen-on-mobile
                width="large"
                placement="top"
                aria-label="Search Open Library"
                style="--ol-dialog-padding: 0"
                @ol-after-open=${this._onDialogOpened}
                @ol-after-close=${this._onDialogClosed}
            >
                <div slot="header" class="bar">
                    ${SearchModal._searchIcon}
                    <input
                        type="search"
                        class="search-input"
                        placeholder="Book, author, series…"
                        aria-label="Search"
                        .value=${this._query}
                        @input=${this._onQueryInput}
                        @keydown=${this._onInputKeydown}
                    />
                    <button
                        type="button"
                        class="esc-pill"
                        aria-label="Close search"
                        @click=${this._closeModal}
                    >ESC</button>
                </div>

                ${hasFilters ? this._renderChips() : nothing}
                ${this._renderFilters()}
                ${this._renderResults()}

                <div slot="footer" class="footer">
                    <button
                        type="button"
                        class="see-all"
                        ?disabled=${this._query.trim().length < MIN_QUERY_LENGTH}
                        @click=${this._onSeeAllResults}
                    >See all results</button>
                </div>
            </ol-dialog>
        `;
    }

    _renderChips() {
        const chips = [];

        if (this._availability !== DEFAULT_AVAILABILITY) {
            const opt = AVAILABILITY_OPTIONS.find(o => o.value === this._availability);
            if (opt) {
                chips.push({
                    key: `availability:${opt.value}`,
                    label: opt.label,
                    onRemove: () => this._setAvailability(DEFAULT_AVAILABILITY),
                });
            }
        }

        for (const value of this._languages) {
            const opt = LANGUAGE_OPTIONS.find(o => o.value === value);
            if (!opt) continue;
            chips.push({
                key: `language:${value}`,
                label: opt.label,
                onRemove: () => this._removeLanguage(value),
            });
        }

        return html`
            <div class="chips">
                ${repeat(chips, c => c.key, c => html`
                    <button
                        type="button"
                        class="chip-pill"
                        aria-label="Remove ${c.label}"
                        @click=${c.onRemove}
                    >
                        ${c.label}
                        <span class="chip-pill__remove" aria-hidden="true">
                            ${SearchModal._closeIcon}
                        </span>
                    </button>
                `)}
                <button
                    type="button"
                    class="clear-all"
                    @click=${this._clearAllFilters}
                >Clear all</button>
            </div>
        `;
    }

    _renderFilters() {
        return html`
            <div class="filters">
                <ol-options-popover
                    label="Availability"
                    heading="AVAILABILITY"
                    .items=${AVAILABILITY_OPTIONS}
                    .selected=${this._availability}
                    @ol-options-popover-change=${this._onAvailabilityChange}
                ></ol-options-popover>
                <ol-select-popover
                    label="Language"
                    placeholder="Filter languages…"
                    unselected-heading="LANGUAGES"
                    .items=${LANGUAGE_OPTIONS}
                    .selected=${this._languages}
                    @ol-select-popover-change=${this._onLanguagesChange}
                ></ol-select-popover>
            </div>
        `;
    }

    _renderResults() {
        const trimmed = this._query.trim();

        if (trimmed.length < MIN_QUERY_LENGTH) {
            return html`<div class="results"><div class="placeholder">Start typing to search…</div></div>`;
        }

        if (this._loading && this._results.length === 0) {
            return html`<div class="results"><div class="loading">Searching…</div></div>`;
        }

        if (this._results.length === 0 && this._hasSearched) {
            return html`<div class="results"><div class="empty">No matches</div></div>`;
        }

        return html`
            <div class="results">
                <h3 class="results-heading">Top results</h3>
                <ul class="results-list">
                    ${repeat(this._results, r => r.key, r => this._renderResult(r))}
                </ul>
            </div>
        `;
    }

    _renderResult(work) {
        const author = work.author_name?.[0] || '';
        const cover = work.cover_i
            ? `https://covers.openlibrary.org/b/id/${work.cover_i}-S.jpg`
            : COVER_PLACEHOLDER;
        return html`
            <li>
                <a class="result" href=${work.key}>
                    <img class="result__cover" src=${cover} alt="" loading="lazy" width="40" height="56"/>
                    <span class="result__meta">
                        <span class="result__title">${work.title || 'Untitled'}</span>
                        ${author ? html`<span class="result__author">${author}</span>` : nothing}
                    </span>
                </a>
            </li>
        `;
    }

    // ── Event handlers ───────────────────────────────────────────

    _onDialogOpened() {
        const input = this.renderRoot.querySelector('.search-input');
        input?.focus();
    }

    _onDialogClosed() {
        this.open = false;
    }

    _onQueryInput(e) {
        this._query = e.target.value;
        if (this._query.trim().length < MIN_QUERY_LENGTH) {
            this._results = [];
            this._loading = false;
            this._hasSearched = false;
            return;
        }
        this._loading = true;
        this._debouncedFetch();
    }

    _onInputKeydown(e) {
        if (e.key === 'Enter' && this._query.trim().length >= MIN_QUERY_LENGTH) {
            e.preventDefault();
            this._onSeeAllResults();
        }
    }

    _onAvailabilityChange(e) {
        this._setAvailability(e.detail.selected);
    }

    _onLanguagesChange(e) {
        this._languages = [...e.detail.selected];
        this._refetchIfActive();
    }

    _setAvailability(value) {
        this._availability = value;
        this._refetchIfActive();
    }

    _removeLanguage(value) {
        this._languages = this._languages.filter(v => v !== value);
        this._refetchIfActive();
    }

    _clearAllFilters() {
        this._availability = DEFAULT_AVAILABILITY;
        this._languages = [];
        this._refetchIfActive();
    }

    _refetchIfActive() {
        if (this._query.trim().length >= MIN_QUERY_LENGTH) {
            this._loading = true;
            this._debouncedFetch();
        }
    }

    _onSeeAllResults() {
        const url = this._buildSearchUrl();
        if (url) window.location.assign(url);
    }

    // ── Data layer ───────────────────────────────────────────────

    _fetchResults() {
        const trimmed = this._query.trim();
        if (trimmed.length < MIN_QUERY_LENGTH) return;

        const url = this._buildSearchJsonUrl(trimmed);
        const fetchKey = url;
        this._activeFetchKey = fetchKey;

        fetch(url)
            .then(r => r.ok ? r.json() : Promise.reject(new Error(`Search failed: ${r.status}`)))
            .then(data => {
                if (this._activeFetchKey !== fetchKey) return;
                this._results = data.docs || [];
                this._loading = false;
                this._hasSearched = true;
            })
            .catch(() => {
                if (this._activeFetchKey !== fetchKey) return;
                this._results = [];
                this._loading = false;
                this._hasSearched = true;
            });
    }

    _buildSearchJsonUrl(query) {
        const params = new URLSearchParams();
        params.set('q', this._composeQ(query));
        params.set('limit', String(RESULTS_LIMIT));
        params.set('fields', SEARCH_FIELDS.join(','));
        params.set('_spellcheck_count', '0');
        params.set('mode', searchMode.read());
        this._appendFilterParams(params);
        return `/search.json?${params.toString()}`;
    }

    _buildSearchUrl() {
        const trimmed = this._query.trim();
        if (trimmed.length < MIN_QUERY_LENGTH) return null;

        const params = new URLSearchParams();
        params.set('q', this._composeQ(trimmed));
        params.set('mode', searchMode.read());
        this._appendFilterParams(params);
        return `/search?${params.toString()}`;
    }

    /**
     * Combines the user's query with any availability-driven Solr clauses.
     * Wraps the user query in parens so AND'd clauses don't change precedence.
     */
    _composeQ(userQuery) {
        const clause = AVAILABILITY_TO_Q_CLAUSE[this._availability];
        return clause ? `(${userQuery}) AND ${clause}` : userQuery;
    }

    /**
     * Appends filter params to the URLSearchParams. Multi-value filters like
     * `language` are serialized as repeated keys (`language=eng&language=spa`)
     * because that's what the /search backend expects.
     */
    _appendFilterParams(params) {
        const availParams = AVAILABILITY_TO_PARAMS[this._availability] || {};
        for (const [key, value] of Object.entries(availParams)) {
            params.append(key, value);
        }
        for (const lang of this._languages) {
            params.append('language', lang);
        }
    }

    // ── Static SVGs ──────────────────────────────────────────────

    static _searchIcon = html`<svg class="search-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>`;

    static _closeIcon = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
}

customElements.define('ol-search-modal', SearchModal);

/**
 * Mounts a single SearchModal instance and wires it to a header trigger.
 * Idempotent — calling more than once with the same trigger has no effect.
 * @param {HTMLInputElement} triggerInput
 * @returns {SearchModal}
 */
export function initSearchModal(triggerInput) {
    if (!triggerInput || triggerInput.dataset.olSearchModalAttached === 'true') {
        return null;
    }
    const modal = document.createElement('ol-search-modal');
    document.body.appendChild(modal);
    modal.attachToTrigger(triggerInput);
    triggerInput.dataset.olSearchModalAttached = 'true';
    return modal;
}
