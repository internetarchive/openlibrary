import { LitElement, html, css, nothing } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import '../../../../components/lit/OlDialog.js';
import '../../../../components/lit/OlOptionsPopover.js';
import '../../../../components/lit/OlSelectPopover.js';
import { debounce } from '../nonjquery_utils.js';
import { mode as searchMode } from '../SearchUtils.js';
import {
    AVAILABILITY_OPTIONS,
    DEFAULT_AVAILABILITY,
    LANGUAGE_OPTIONS,
    SS_AVAILABILITY_KEY,
    SS_LANGUAGES_KEY,
} from './constants.js';

const AVAILABILITY_TO_PARAMS = {
    all: {},
    readable: { has_fulltext: 'true' },
    borrowable: {},
    open: { public_scan: 'true' },
};

const AVAILABILITY_TO_Q_CLAUSE = {
    borrowable: 'ebook_access:borrowable',
};

const SEARCH_FIELDS = ['key', 'cover_i', 'title', 'subtitle', 'author_name'];

const RESULTS_LIMIT     = 10;
const MIN_QUERY_LENGTH  = 2;
const COVER_PLACEHOLDER = '/static/images/icons/avatar_book-sm.png';

function ssGet(key)        { try { return sessionStorage.getItem(key); }        catch { return null; } }
function ssSet(key, value) { try { sessionStorage.setItem(key, value); }        catch { /* ignore */ } }

export class SearchModal extends LitElement {
    static properties = {
        open: { type: Boolean, reflect: true },
        _query: { state: true },
        _availability: { state: true },
        _languages: { state: true },
        _results: { state: true },
        _loading: { state: true },
        _hasSearched: { state: true },
        _languageItems: { state: true },
        _langsLoading: { state: true },
        barcodeHref: { type: String, attribute: 'barcode-href' },
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
            transition: background-color 150ms ease;
        }

        @media (hover: hover) and (pointer: fine) {
            .esc-pill:hover { background: var(--lightest-grey); }
        }

        .esc-pill:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        @media (hover: none) and (pointer: coarse) { .esc-pill { display: none; } }
        @media (prefers-reduced-motion: reduce)     { .esc-pill { transition: none; } }

        /* ── Barcode button ────────────────────────────────────────── */

        .barcode-btn {
            flex-shrink: 0;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 32px;
            height: 32px;
            border-radius: var(--border-radius-button);
            opacity: 0.55;
            transition: opacity 150ms ease;
            text-decoration: none;
        }

        @media (hover: hover) and (pointer: fine) {
            .barcode-btn:hover { opacity: 0.9; }
        }

        .barcode-btn:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: 2px;
            opacity: 0.9;
        }

        @media (prefers-reduced-motion: reduce) { .barcode-btn { transition: none; } }

        /* ── Active filter chip row ────────────────────────────────── */

        .chips {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: var(--spacing-xs);
            padding: var(--spacing-xs) var(--spacing-lg);
            border-bottom: 1px solid var(--color-border-subtle);
        }

        .chip-pill {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 3px var(--spacing-sm);
            background: hsla(202, 96%, 37%, 0.07);
            border: 1px solid hsla(202, 96%, 37%, 0.22);
            border-radius: var(--border-radius-pill);
            color: var(--link-blue);
            font: inherit;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: background-color 150ms ease;
        }

        @media (hover: hover) and (pointer: fine) {
            .chip-pill:hover { background: hsla(202, 96%, 37%, 0.13); }
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
            opacity: 0.65;
        }

        .chip-pill__remove svg { width: 100%; height: 100%; }

        .clear-all {
            margin-left: auto;
            padding: 3px var(--spacing-sm);
            background: transparent;
            border: 1px solid transparent;
            border-radius: var(--border-radius-button);
            color: var(--dark-red);
            font: inherit;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: background-color 150ms ease;
        }

        @media (hover: hover) and (pointer: fine) {
            .clear-all:hover { background: hsla(8, 70%, 44%, 0.07); }
        }

        .clear-all:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        @media (prefers-reduced-motion: reduce) {
            .chip-pill, .clear-all { transition: none; }
        }

        /* ── Filter button row ─────────────────────────────────────── */

        .filters {
            display: flex;
            flex-wrap: wrap;
            gap: var(--spacing-xs);
            padding: var(--spacing-xs) var(--spacing-lg) var(--spacing-sm);
            border-bottom: 1px solid var(--color-border-subtle);
        }

        /* ── Results ───────────────────────────────────────────────── */

        .results {
            flex: 1;
            min-height: 80px;
            max-height: 320px;
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

        .result {
            display: flex;
            align-items: center;
            gap: var(--spacing-md);
            padding: var(--spacing-sm) var(--spacing-lg);
            color: inherit;
            text-decoration: none;
            transition: background-color 100ms ease;
        }

        @media (hover: hover) and (pointer: fine) {
            .result:hover { background: var(--icon-link-grey); }
        }

        .result:focus-visible {
            outline: none;
            background: var(--icon-link-grey);
            box-shadow: inset 2px 0 0 var(--color-focus-ring);
        }

        @media (prefers-reduced-motion: reduce) { .result { transition: none; } }

        .result__cover {
            flex-shrink: 0;
            width: 36px;
            height: 50px;
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

        .empty, .placeholder, .loading {
            padding: var(--spacing-lg) var(--spacing-lg);
            color: var(--accessible-grey);
            font-size: 14px;
            text-align: center;
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
            .filters { padding: var(--spacing-xs) var(--spacing-md) var(--spacing-sm); }
            .footer {
                position: sticky;
                bottom: 0;
                background: var(--white);
                border-top: 1px solid var(--color-border-subtle);
            }
        }
    `;

    constructor() {
        super();
        this.open          = false;
        this._query        = '';
        this._results      = [];
        this._loading      = false;
        this._hasSearched  = false;
        this._langsLoading = false;
        this.barcodeHref   = '';

        this._languageItems = LANGUAGE_OPTIONS;

        this._availability = ssGet(SS_AVAILABILITY_KEY) || DEFAULT_AVAILABILITY;

        const storedLangs = ssGet(SS_LANGUAGES_KEY);
        this._languages = storedLangs
            ? (() => { try { return JSON.parse(storedLangs); } catch { return []; } })()
            : [];

        this._debouncedFetch = debounce(() => this._fetchResults(), 250, false);
        this._activeFetchKey = null;
        this._allLangsLoaded = false;
    }

    attachToTrigger(input) {
        if (!input) return;
        const openModal = (e) => {
            if (this.open) return;
            e.preventDefault?.();
            input.blur();
            this._openModal();
        };
        input.addEventListener('focus', openModal);
        input.addEventListener('click', openModal);
    }

    _openModal() {
        this.open = true;
        if (!this._allLangsLoaded && !this._langsLoading) {
            this._loadAllLanguages();
        }
    }

    _closeModal() { this.open = false; }

    async _loadAllLanguages() {
        this._langsLoading = true;
        try {
            const res = await fetch(
                '/search.json?q=*&facets=true&limit=0&facet=language',
                { signal: AbortSignal.timeout?.(8000) }
            );
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();

            const raw = data?.facet_counts?.facet_fields?.language || [];

            const codes = [];
            for (let i = 0; i < raw.length; i += 2) {
                if (typeof raw[i] === 'string') codes.push(raw[i]);
            }

            const staticMap = new Map(
                LANGUAGE_OPTIONS.map(o => [o.value, o.label])
            );

            const merged = codes
                .map(code => ({
                    value: code,
                    label: staticMap.get(code) || _titleCase(code),
                }))
                .filter(o => o.value);

            const seen    = new Set();
            const deduped = merged.filter(o => {
                if (seen.has(o.value)) return false;
                seen.add(o.value);
                return true;
            });
            deduped.sort((a, b) => a.label.localeCompare(b.label));

            this._languageItems  = deduped;
            this._allLangsLoaded = true;
        } catch {
            this._allLangsLoaded = true;
        } finally {
            this._langsLoading = false;
        }
    }

    // ── Render ────────────────────────────────────────────────────────────

    render() {
        const hasFilters = (
            this._availability !== DEFAULT_AVAILABILITY ||
            this._languages.length > 0
        );

        return html`
            <ol-dialog
                ?open=${this.open}
                without-header
                fullscreen-on-mobile
                width="large"
                placement="top"
                aria-label="Search Open Library"
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
                    ${SearchModal._searchIcon}
                    <input
                        type="search"
                        class="search-input"
                        placeholder="Search books, authors…"
                        aria-label="Search"
                        .value=${this._query}
                        @input=${this._onQueryInput}
                        @keydown=${this._onInputKeydown}
                    />
                    ${this.barcodeHref ? html`
                        <a
                            href=${this.barcodeHref}
                            class="barcode-btn"
                            aria-label="Scan a barcode"
                            title="Scan barcode"
                        >
                            <img
                                src="/static/images/icons/barcode_scanner.svg"
                                alt=""
                                width="24"
                                height="24"
                            />
                        </a>
                    ` : nothing}
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
            if (opt) chips.push({
                key: `availability:${opt.value}`,
                label: opt.label,
                onRemove: () => this._setAvailability(DEFAULT_AVAILABILITY),
            });
        }

        for (const value of this._languages) {
            const opt = this._languageItems.find(o => o.value === value);
            if (!opt) continue;
            chips.push({
                key: `language:${value}`,
                label: opt.label,
                onRemove: () => this._removeLanguage(value),
            });
        }

        return html`
            <div class="chips" role="group" aria-label="Active filters">
                ${repeat(chips, c => c.key, c => html`
                    <button
                        type="button"
                        class="chip-pill"
                        aria-label="Remove filter: ${c.label}"
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
            <div class="filters" role="group" aria-label="Search filters">
                <ol-options-popover
                    label="Availability"
                    heading="AVAILABILITY"
                    .items=${AVAILABILITY_OPTIONS}
                    .selected=${this._availability}
                    @ol-options-popover-change=${this._onAvailabilityChange}
                ></ol-options-popover>
                <ol-select-popover
                    label="Language"
                    placeholder="Search languages…"
                    unselected-heading="LANGUAGES"
                    .items=${this._languageItems}
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
            return html`<div class="results"><div class="empty">No results found</div></div>`;
        }

        return html`
            <div class="results">
                <h3 class="results-heading">Top results</h3>
                <ul class="results-list">${repeat(this._results, r => r.key, r => this._renderResult(r))}</ul>
            </div>
        `;
    }

    _renderResult(work) {
        const author = work.author_name?.[0] || '';
        const cover  = work.cover_i
            ? `https://covers.openlibrary.org/b/id/${work.cover_i}-S.jpg`
            : COVER_PLACEHOLDER;
        return html`<li>
                <a class="result" href=${work.key}>
                    <img class="result__cover" src=${cover} alt="" loading="lazy" width="36" height="50"/>
                    <span class="result__meta">
                        <span class="result__title">${work.title || 'Untitled'}</span>
                        ${author ? html`<span class="result__author">${author}</span>` : nothing}
                    </span>
                </a>
            </li>`;
    }

    // ── Event handlers ───────────────────────────────────────────────────

    _onDialogOpened() {
        this.renderRoot.querySelector('.search-input')?.focus();
    }

    _onDialogClosed() { this.open = false; }

    _onQueryInput(e) {
        this._query = e.target.value;
        if (this._query.trim().length < MIN_QUERY_LENGTH) {
            this._results     = [];
            this._loading     = false;
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

    _onAvailabilityChange(e) { this._setAvailability(e.detail.selected); }

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

    _removeLanguage(value) {
        this._languages = this._languages.filter(v => v !== value);
        ssSet(SS_LANGUAGES_KEY, JSON.stringify(this._languages));
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
        if (this._query.trim().length >= MIN_QUERY_LENGTH) {
            this._loading = true;
            this._debouncedFetch();
        }
    }

    _onSeeAllResults() {
        const url = this._buildSearchUrl();
        if (url) window.location.assign(url);
    }

    // ── Data layer ───────────────────────────────────────────────────────

    _fetchResults() {
        const trimmed = this._query.trim();
        if (trimmed.length < MIN_QUERY_LENGTH) return;

        const url      = this._buildSearchJsonUrl(trimmed);
        const fetchKey = url;
        this._activeFetchKey = fetchKey;

        fetch(url)
            .then(r => r.ok ? r.json() : Promise.reject(new Error(`Search failed: ${r.status}`)))
            .then(data => {
                if (this._activeFetchKey !== fetchKey) return;
                this._results     = data.docs || [];
                this._loading     = false;
                this._hasSearched = true;
            })
            .catch(() => {
                if (this._activeFetchKey !== fetchKey) return;
                this._results     = [];
                this._loading     = false;
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

    _composeQ(userQuery) {
        const clause = AVAILABILITY_TO_Q_CLAUSE[this._availability];
        return clause ? `(${userQuery}) AND ${clause}` : userQuery;
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

    static _searchIcon = html`<svg class="search-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>`;

    static _closeIcon  = html`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
}

customElements.define('ol-search-modal', SearchModal);

/**
 * Mounts a single SearchModal and wires it to a header trigger input.
 * Idempotent – safe to call multiple times with the same element.
 * @param {HTMLInputElement} triggerInput
 * @returns {SearchModal|null}
 */
export function initSearchModal(triggerInput) {
    if (!triggerInput || triggerInput.dataset.olSearchModalAttached === 'true') {
        return null;
    }

    const modal = document.createElement('ol-search-modal');

    const barcodeLink = document.querySelector('#barcode_scanner_link');
    if (barcodeLink) {
        modal.barcodeHref = barcodeLink.getAttribute('href') || '';
    }

    document.body.appendChild(modal);
    modal.attachToTrigger(triggerInput);
    triggerInput.dataset.olSearchModalAttached = 'true';
    return modal;
}

function _titleCase(str) {
    return str ? str.charAt(0).toUpperCase() + str.slice(1) : str;
}
