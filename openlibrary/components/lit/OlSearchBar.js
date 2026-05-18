import { LitElement, html, css, nothing } from 'lit';
import {
    POPULAR_AUTHORS, POPULAR_SUBJECTS, AVAILABILITY_OPTIONS, LANGUAGE_OPTIONS, SORT_OPTIONS,
    EMPTY_FILTERS, shufflePick, bestEdition,
    buildChips,
} from './search/filters.js';
import { BREAKPOINTS } from './search/breakpoints.js';
import { fetchAuthorSuggestions, fetchSubjectSuggestions } from './search/facets.js';
import './OlHowtoModal.js';
import './OlFacetDrop.js';
import './OlFacetSelect.js';
import './OlSelectPopover.js';

/**
 * Unified search bar used in two modes:
 *
 *   showFacets=true  ("droppable" / header mode)
 *     - owns local filter state (_localFilters)
 *     - chips shown in input row, always visible
 *     - panel opens on focus: facets + autocomplete cards
 *
 *   showFacets=false (embedded / search-page mode)
 *     - chips and filters passed as props, shown in input row
 *     - NO panel — just a query input; submit triggers ol-search
 *
 * @element ol-search-bar
 */
export class OlSearchBar extends LitElement {
    static properties = {
        q: { type: String },
        chips: { type: Array },
        showFacets: { type: Boolean, attribute: 'show-facets' },
        filters: { type: Object },
        siteBase: { type: String },
        placeholder: { type: String },

        _q: { state: true },
        _suggestions: { state: true },
        _open: { state: true },
        _loading: { state: true },
        _total: { state: true },
        _localFilters: { state: true },
        _howtoOpen: { state: true },
        _authorResults: { state: true },
        _subjectResults: { state: true },
        _defaultAuthors: { state: true },
        _defaultSubjects: { state: true },
        _facetsLoading: { state: true },
        _acFocusIdx: { state: true },
        _mobileExpanded: { state: true },
        _acError: { state: true },
    };

    constructor() {
        super();
        this.q           = '';
        this.chips       = [];
        this.showFacets  = false;
        this.filters     = { ...EMPTY_FILTERS };
        this.siteBase    = '';
        this.placeholder = 'Search books, authors…';

        this._q             = '';
        this._suggestions   = [];
        this._open          = false;
        this._loading       = false;
        this._total         = 0;
        this._acError       = false;
        this._timer         = null;
        this._localFilters  = { ...EMPTY_FILTERS };

        this._howtoOpen       = false;
        this._authorResults   = [];
        this._subjectResults  = [];
        this._defaultAuthors  = shufflePick(POPULAR_AUTHORS, 6);
        this._defaultSubjects = shufflePick(POPULAR_SUBJECTS, 6);
        this._facetsLoading   = false;
        this._acFocusIdx      = -1;
        this._mobileExpanded  = false;
        this._authorTimer     = null;
        this._subjectTimer    = null;
        this._acAbort         = null;
        this._authorAbort     = null;
        this._subjectAbort    = null;

        this._onWinResize = () => {
            if (!this._open) return;
            const isMobile = window.matchMedia(`(max-width: ${BREAKPOINTS.mobile}px)`).matches;
            if (isMobile && !this._mobileExpanded) {
                this._mobileExpanded = true;
            } else if (!isMobile && this._mobileExpanded) {
                this._mobileExpanded = false;
                requestAnimationFrame(() => this._positionPanel());
            } else if (!isMobile) {
                requestAnimationFrame(() => this._positionPanel());
            }
        };

        this._onDoc = e => {
            const path = e.composedPath();
            if (!path.includes(this)) this._closePanel();
        };
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('click', this._onDoc, true);
        window.addEventListener('resize', this._onWinResize);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('click', this._onDoc, true);
        window.removeEventListener('resize', this._onWinResize);
        this._acAbort?.abort();
        this._authorAbort?.abort();
        this._subjectAbort?.abort();
        clearTimeout(this._timer);
        clearTimeout(this._authorTimer);
        clearTimeout(this._subjectTimer);
        if (this._scrollLockActive) {
            document.body.style.overflow            = this._prevBodyOverflow ?? '';
            document.documentElement.style.overflow = this._prevDocumentOverflow ?? '';
            this._scrollLockActive = false;
        }
    }

    updated(changed) {
        if (changed.has('q') && this.q !== null && this.q !== this._q) {
            this._q = this.q;
        }
        if (!this.showFacets && changed.has('filters') && this.filters) {
            this._localFilters = { ...this.filters };
        }
        this.classList.toggle('mobile-exp', this._mobileExpanded);
        if (changed.has('_open')) {
            const shouldLock = this._open && this.showFacets;
            if (shouldLock && !this._scrollLockActive) {
                this._prevBodyOverflow            = document.body.style.overflow;
                this._prevDocumentOverflow        = document.documentElement.style.overflow;
                this._scrollLockActive            = true;
                document.body.style.overflow      = 'hidden';
                document.documentElement.style.overflow = 'hidden';
            } else if (!shouldLock && this._scrollLockActive) {
                document.body.style.overflow            = this._prevBodyOverflow ?? '';
                document.documentElement.style.overflow = this._prevDocumentOverflow ?? '';
                this._scrollLockActive      = false;
                this._prevBodyOverflow      = undefined;
                this._prevDocumentOverflow  = undefined;
            }
        }
        if (changed.has('_open') && this._open && this.showFacets) {
            if (!this._mobileExpanded) this._positionPanel();
            requestAnimationFrame(() => this.shadowRoot?.querySelector('.panel-input')?.focus());
        }
    }

    _positionPanel() {
        if (this._mobileExpanded) return;
        const trigger = this.shadowRoot?.querySelector('.input-row');
        if (!trigger) return;
        const rect = trigger.getBoundingClientRect();
        const vw   = window.innerWidth;
        this.style.setProperty('--ol-panel-top', `${rect.top}px`);
        if (vw > BREAKPOINTS.wide) {
            const desired = Math.max(600, Math.min(860, rect.width));
            const panelW  = Math.min(desired, rect.right - 8);
            this.style.setProperty('--ol-panel-width', `${panelW}px`);
            this.style.setProperty('--ol-panel-right', `${Math.max(0, vw - rect.right)}px`);
            this.style.setProperty('--ol-panel-left',  'auto');
        } else {
            const panelW = Math.max(600, Math.round(vw * 0.85));
            const left   = Math.round((vw - panelW) / 2);
            this.style.setProperty('--ol-panel-width', `${panelW}px`);
            this.style.setProperty('--ol-panel-left',  `${left}px`);
            this.style.setProperty('--ol-panel-right', 'auto');
        }
    }

    _hasActiveFilters() {
        const f = this._localFilters;
        const nonDefaultAvail = f.availability && f.availability !== EMPTY_FILTERS.availability;
        return !!(nonDefaultAvail || f.fictionFilter ||
            f.languages?.length || f.genres?.length ||
            f.authors?.length   || f.subjects?.length);
    }

    _onTriggerClick(e) {
        e.stopPropagation();
        this._open = true;
        if (window.matchMedia(`(max-width: ${BREAKPOINTS.mobile}px)`).matches) {
            this._mobileExpanded = true;
        }
    }

    _closePanel() {
        this._open           = false;
        this._mobileExpanded = false;
        this._acFocusIdx     = -1;
    }

    _onInput(e) {
        this._q = e.target.value;
        if (this.showFacets) this._open = true;
        clearTimeout(this._timer);
        if (this._q.trim().length < 2 && !this._hasActiveFilters()) {
            this._suggestions = [];
            this._acError     = false;
            this._loading     = false;
            return;
        }
        this._loading = true;
        this._timer = setTimeout(() => this._fetchAutocomplete(), 300);
    }

    async _fetchAutocomplete() {
        this._acAbort?.abort();
        this._acAbort = new AbortController();
        const { signal } = this._acAbort;
        this._acError = false;

        const q = this._q.trim();
        const f = this._localFilters;
        try {
            // OL search API: /search.json with OL-specific param names
            const p = new URLSearchParams({ limit: 5 });
            p.set('fields', 'key,title,author_name,cover_i,first_publish_year,ratings_average,ebook_access,editions');
            if (q)               p.set('q', q);
            if (f.availability)  p.set('availability', f.availability);
            // OL uses 'subject' for fiction, genres, and subjects (all map to subject param)
            if (f.fictionFilter) p.append('subject', f.fictionFilter);
            for (const v of f.languages ?? []) p.append('language', v);
            for (const v of f.genres    ?? []) p.append('subject',  v);
            for (const v of f.authors   ?? []) p.append('author',   v);
            for (const v of f.subjects  ?? []) p.append('subject',  v);
            const d = await (await fetch(`/search.json?${p}`, { signal })).json();
            this._suggestions = d.docs ?? [];
            this._total       = d.numFound ?? 0;  // OL uses numFound, not num_found
            this._acFocusIdx  = -1;
        } catch (err) {
            if (err.name !== 'AbortError') {
                this._suggestions = []; this._total = 0; this._acFocusIdx = -1;
                this._acError = true;
            }
        } finally {
            if (!signal.aborted) this._loading = false;
        }
    }

    _clearInput() {
        this._acAbort?.abort();
        clearTimeout(this._timer);
        this._q           = '';
        this._suggestions = [];
        this._acError     = false;
        this._total       = 0;
        this._acFocusIdx  = -1;
        this._loading     = false;
        this.shadowRoot?.querySelector('.text-input')?.focus();
    }

    _onKeyDown(e) {
        if (e.key === 'Escape') {
            this._closePanel(); return;
        }
        if (this._open && this._suggestions.length > 0) {
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                this._acFocusIdx = Math.min(this._acFocusIdx + 1, this._suggestions.length - 1);
                return;
            }
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                this._acFocusIdx = Math.max(this._acFocusIdx - 1, -1);
                return;
            }
            if (e.key === 'Enter' && this._acFocusIdx >= 0) {
                e.preventDefault();
                this.shadowRoot?.querySelectorAll('.ac-row')?.[this._acFocusIdx]?.click();
                return;
            }
        }
        if (e.key === 'Enter') this._submit();
    }

    _buildSearchUrl(q, f = {}) {
        const p = new URLSearchParams();
        if (q) p.set('q', q);
        if (f.sort)           p.set('sort', f.sort);
        if (f.availability)   p.set('availability', f.availability);
        if (f.fictionFilter)  p.append('subject', f.fictionFilter);
        (f.languages ?? []).forEach(l => p.append('language', l));
        (f.genres    ?? []).forEach(g => p.append('subject', g));
        (f.authors   ?? []).forEach(a => p.append('author', a));
        (f.subjects  ?? []).forEach(s => p.append('subject', s));
        // siteBase may be '' in OL — fall back to origin for URL construction
        const base = this.siteBase || window.location.origin;
        const url = new URL('/search', base);
        url.search = p.toString();
        // Return relative URL when siteBase is empty
        return this.siteBase ? url.toString() : url.pathname + url.search;
    }

    _submit() {
        if (!this._q.trim() && !this._hasActiveFilters()) return;
        this._mobileExpanded = false;
        const event = new CustomEvent('ol-search', {
            detail: { q: this._q.trim(), filters: this._localFilters },
            bubbles: true, composed: true, cancelable: true,
        });
        this.dispatchEvent(event);
        if (this.showFacets && !event.defaultPrevented) {
            window.location.href = this._buildSearchUrl(this._q.trim(), this._localFilters);
        }
    }

    _clearAllFilters() {
        if (this.showFacets) {
            const f = this._localFilters;
            const fields = [
                ['availability',  EMPTY_FILTERS.availability],
                ['fictionFilter', EMPTY_FILTERS.fictionFilter],
                ['languages',     EMPTY_FILTERS.languages],
                ['genres',        EMPTY_FILTERS.genres],
                ['authors',       EMPTY_FILTERS.authors],
                ['subjects',      EMPTY_FILTERS.subjects],
                ['sort',          EMPTY_FILTERS.sort],
            ];
            for (const [field, empty] of fields) {
                const cur = f[field];
                const isDiff = Array.isArray(cur) ? cur.length > 0 : cur !== empty;
                if (isDiff) this._emitFilter(field, empty);
            }
        } else {
            this.dispatchEvent(new CustomEvent('ol-clear-all-filters', {
                bubbles: true, composed: true,
            }));
        }
    }

    _handleChipRemove(c) {
        if (this.showFacets) {
            const f = this._localFilters;
            if      (c.type === 'access')  this._emitFilter('availability',  '');
            else if (c.type === 'fiction') this._emitFilter('fictionFilter', '');
            else if (c.type === 'lang')    this._emitFilter('languages', []);
            else if (c.type === 'genre')   this._emitFilter('genres',    (f.genres    ?? []).filter(v => v !== c.value));
            else if (c.type === 'author')  this._emitFilter('authors',   (f.authors   ?? []).filter(v => v !== c.value));
            else if (c.type === 'subject') this._emitFilter('subjects',  (f.subjects  ?? []).filter(v => v !== c.value));
        } else {
            const f = this.filters ?? this._localFilters;
            let filter, value;
            if      (c.type === 'access')  { filter = 'availability';  value = ''; }
            else if (c.type === 'fiction') { filter = 'fictionFilter'; value = ''; }
            else if (c.type === 'lang')    { filter = 'languages';     value = []; }
            else if (c.type === 'genre')   { filter = 'genres';        value = (f.genres    ?? []).filter(v => v !== c.value); }
            else if (c.type === 'author')  { filter = 'authors';       value = (f.authors   ?? []).filter(v => v !== c.value); }
            else if (c.type === 'subject') { filter = 'subjects';      value = (f.subjects  ?? []).filter(v => v !== c.value); }
            if (filter !== undefined) {
                this.dispatchEvent(new CustomEvent('ol-filter-change', {
                    detail: { filter, value }, bubbles: true, composed: true,
                }));
            }
        }
    }

    _emitFilter(filter, value) {
        this._localFilters = { ...this._localFilters, [filter]: value };
        this.dispatchEvent(new CustomEvent('ol-filter-change', {
            detail: { filter, value }, bubbles: true, composed: true,
        }));
        this._open = true;
        clearTimeout(this._timer);
        this._loading = true;
        this._timer = setTimeout(() => this._fetchAutocomplete(), 150);
    }

    _onDropFacetChange(e) {
        this._emitFilter(e.detail.filter, e.detail.value);
    }

    _onDropAuthorSearch(e) {
        clearTimeout(this._authorTimer);
        this._authorAbort?.abort();
        const q = e.detail.q;
        if (q.trim().length < 2) { this._authorResults = []; this._facetsLoading = false; return; }
        this._facetsLoading = true;
        this._authorAbort = new AbortController();
        const { signal } = this._authorAbort;
        this._authorTimer = setTimeout(async() => {
            try {
                this._authorResults = await fetchAuthorSuggestions(q, { signal });
            } catch {
                this._authorResults = [];
            } finally {
                if (!signal.aborted) this._facetsLoading = false;
            }
        }, 250);
    }

    _onDropSubjectSearch(e) {
        clearTimeout(this._subjectTimer);
        this._subjectAbort?.abort();
        const q = e.detail.q;
        if (q.trim().length < 2) { this._subjectResults = []; this._facetsLoading = false; return; }
        this._facetsLoading = true;
        this._subjectAbort = new AbortController();
        const { signal } = this._subjectAbort;
        this._subjectTimer = setTimeout(async() => {
            try {
                this._subjectResults = await fetchSubjectSuggestions(q, { signal });
            } catch {
                this._subjectResults = [];
            } finally {
                if (!signal.aborted) this._facetsLoading = false;
            }
        }, 250);
    }

    static styles = css`
        :host { display: block; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; text-align: left; }

        .search-outer { position: relative; }

        .input-row {
            display: flex; align-items: center;
            background: white; border: 1.5px solid hsl(0,0%,78%); border-radius: 8px;
            padding: 6px 8px; transition: border-color .15s, box-shadow .15s;
            cursor: text;
        }
        .input-row:focus-within {
            border-color: hsl(202,96%,37%);
            box-shadow: 0 0 0 3px hsla(202,96%,37%,.12);
        }
        .search-outer.open .input-row {
            background: white;
            border-color: hsl(202,96%,37%);
            border-bottom-left-radius: 0;
            border-bottom-right-radius: 0;
            box-shadow: 0 0 0 3px hsla(202,96%,37%,.12);
        }

        .chip-bar {
            display: flex; flex-wrap: wrap; gap: 4px;
            padding: 6px 2px 0;
        }
        .panel-chips {
            display: flex; flex-wrap: wrap; gap: 4px;
            padding: 8px 14px 6px;
            border-bottom: 1px solid hsl(0,0%,90%);
            background: hsl(0,0%,98.5%);
        }

        .chip {
            display: inline-flex; align-items: center; gap: 3px;
            padding: 2px 7px 2px 9px; border-radius: 9999px;
            font-size: 12px; font-weight: 500; border: 1px solid; white-space: nowrap; line-height: 1.5;
            flex-shrink: 0;
        }
        .chip-access   { background:hsl(142,50%,91%); color:hsl(142,50%,22%); border-color:hsl(142,50%,72%); }
        .chip-fiction  { background:hsl(270,45%,92%); color:hsl(270,45%,30%); border-color:hsl(270,45%,76%); }
        .chip-lang     { background:hsl(217,70%,92%); color:hsl(217,70%,28%); border-color:hsl(217,70%,76%); }
        .chip-genre    { background:hsl(270,35%,93%); color:hsl(270,35%,32%); border-color:hsl(270,35%,78%); }
        .chip-author   { background:hsl(25,80%,92%);  color:hsl(25,80%,28%);  border-color:hsl(25,80%,72%); }
        .chip-subject  { background:hsl(340,60%,92%); color:hsl(340,60%,28%); border-color:hsl(340,60%,76%); }
        .chip-x {
            background:none; border:none; cursor:pointer;
            padding:0 1px; font-size:15px; line-height:1; opacity:.5;
        }
        .chip-x:hover { opacity:1; }

        .clear-all-btn {
            flex-shrink:0; margin-left:auto; background:none; border:none;
            cursor:pointer; font-size:11px; font-family:inherit;
            font-weight:500; color:hsl(0,0%,50%);
            padding:2px 8px; border-radius:4px;
            white-space:nowrap; line-height:1.5;
            transition:color .1s, background .1s;
        }
        .clear-all-btn:hover { color:hsl(0,72%,35%); background:hsl(0,72%,96%); }

        .text-input {
            flex:1; min-width:80px; border:none; outline:none;
            font-size:14px; font-family:inherit; color:hsl(0,0%,15%);
            background:white; padding:2px 4px;
            -webkit-appearance:none; appearance:none;
        }
        .text-input::placeholder { color:hsl(0,0%,52%); }

        .input-controls {
            display:flex; align-items:center; flex:1; gap:5px;
        }

        .submit {
            flex-shrink:0; margin-left:auto;
            background:hsl(202,96%,37%); color:white; border:none;
            border-radius:6px; padding:6px 14px; font-size:13px;
            font-weight:500; font-family:inherit; cursor:pointer;
            display:inline-flex; align-items:center; gap:5px;
            white-space:nowrap; transition:background .12s;
        }
        .submit:hover { background:hsl(202,96%,28%); }

        .scan-sep { width:1px; height:20px; background:hsl(0,0%,82%); flex-shrink:0; margin:0 2px; }
        .scan-btn {
            flex-shrink:0; padding:5px 7px; border:1px solid hsl(0,0%,84%); border-radius:6px;
            background:white; cursor:pointer; display:inline-flex; align-items:center;
            transition:background .1s, border-color .1s;
        }
        .scan-btn:hover { background:hsl(0,0%,96%); border-color:hsl(0,0%,70%); }
        .scan-btn img { display:block; width:18px; height:18px; }

        .trigger-btn {
            flex:1; min-width:0; border:none; outline:none; cursor:pointer;
            background:transparent; font-size:14px; font-family:inherit;
            padding:2px 4px; text-align:left; color:hsl(0,0%,15%);
            overflow:hidden; white-space:nowrap; text-overflow:ellipsis;
        }
        .trigger-placeholder { color:hsl(0,0%,52%); }

        .panel-input-row {
            display:flex; align-items:center; min-width:0; gap:6px;
            padding:6px 8px; border-bottom:1px solid hsl(0,0%,90%);
            background:white; border-radius:6.5px 6.5px 0 0;
        }

        .panel {
            position:fixed;
            top:var(--ol-panel-top, auto);
            right:var(--ol-panel-right, 0px);
            width:var(--ol-panel-width, 600px);
            left:var(--ol-panel-left, auto);
            background:white;
            border:1.5px solid hsl(202,96%,37%);
            border-radius:8px;
            box-shadow:0 12px 32px rgba(0,0,0,.16);
            z-index:500; overflow:visible;
        }

        .pf-bar {
            display:flex; border-bottom:1px solid hsl(0,0%,90%);
            background:hsl(0,0%,98.5%);
        }
        .pf-wrap { flex:1; position:relative; display:flex; }
        .pf-wrap + .pf-wrap { border-left:1px solid hsl(0,0%,90%); }
        .pf-wrap--cog { flex:0 0 38px; }
        .pf-wrap--first { border-bottom-left-radius:9px; }
        .pf-wrap--first .pf-btn { border-bottom-left-radius:9px; }
        .pf-wrap--last  { border-bottom-right-radius:9px; }
        .pf-wrap--last  .pf-btn { border-bottom-right-radius:9px; }
        .pf-btn {
            flex:1; padding:7px 4px; border:none; background:transparent;
            font-size:11px; font-family:inherit; color:hsl(0,0%,35%);
            cursor:pointer; display:flex; align-items:center; justify-content:center;
            gap:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
            transition:background .08s;
        }
        .pf-btn:hover  { background:hsl(0,0%,95%); color:hsl(202,96%,28%); }
        .pf-btn.active { color:hsl(202,96%,28%); font-weight:600; }

        /* OL primitive selectors within the facet bar — match pf-btn visual style */
        .pf-wrap > ol-facet-select,
        .pf-wrap > ol-facet-drop {
            flex:1; align-self:stretch;
            --ol-trigger-bg: transparent;
            --ol-trigger-border-right: none;
            --ol-trigger-border-radius: 0;
            --ol-trigger-padding: 7px 4px;
            --ol-trigger-font-size: 11px;
            --ol-trigger-min-height: 0;
            --darker-grey: hsl(0,0%,35%);
            font-family: inherit;
        }
        .pf-wrap > ol-facet-select:hover,
        .pf-wrap > ol-facet-drop:hover { --ol-trigger-bg-hover: hsl(0,0%,95%); }
        .pf-wrap > ol-select-popover {
            flex:1; align-self:stretch;
            /* ol-select-popover is inline-block, which makes its flex-stretched
               cross-size non-definite for child % resolution (unlike inline-flex).
               Overriding display to inline-flex matches ol-facet-drop/:host behavior
               and makes height:100% on the slotted trigger resolve correctly. */
            display: inline-flex; align-items: stretch;
            --ol-popover-trigger-align: stretch;
        }
        .pf-wrap > ol-select-popover > [slot="trigger"] {
            width: 100%; height: 100%;
        }

        /* SVG chevron for Language slot="trigger" button */
        .pf-chevron {
            display: inline-block;
            width: 12px; height: 12px;
            flex-shrink: 0;
            opacity: .55;
            transition: transform 150ms ease-out;
        }
        .pf-wrap > ol-select-popover[data-open] > [slot="trigger"] .pf-chevron {
            transform: rotate(180deg);
        }
        @media (prefers-reduced-motion: reduce) {
            .pf-chevron { transition: none; }
        }

        .clear-btn {
            flex-shrink:0; background:none; border:none; cursor:pointer;
            padding:2px 4px; color:hsl(0,0%,55%); font-size:16px; line-height:1;
            border-radius:50%; display:inline-flex; align-items:center; justify-content:center;
            transition:color .1s, background .1s;
        }
        .clear-btn:hover { color:hsl(0,0%,20%); background:hsl(0,0%,93%); }

        .ac-scroll { max-height:280px; overflow-y:auto; }
        .ac-spin, .ac-hint-msg, .ac-empty {
            padding:16px; text-align:center; font-size:13px; color:hsl(0,0%,55%);
        }
        .ac-error {
            padding:16px; text-align:center; font-size:13px;
            color:hsl(0,72%,40%); background:hsl(0,72%,97%);
            border-bottom-left-radius: 6.5px; border-bottom-right-radius: 6.5px;
        }
        .ac-row {
            display:flex; align-items:center; gap:12px; padding:10px 14px;
            text-decoration:none; border-bottom:1px solid hsl(0,0%,94%);
            transition:background .1s; cursor:pointer; color:inherit;
        }
        .ac-row:hover, .ac-row.focused { background:hsl(0,0%,97%); }
        .ac-row.focused { outline:2px solid hsl(202,96%,37%); outline-offset:-2px; }
        .ac-row:last-of-type { border-bottom:none; }
        .ac-cover {
            width:36px; height:54px; object-fit:cover; border-radius:3px;
            background:hsl(0,0%,90%); flex-shrink:0; display:block;
            box-shadow:1px 1px 3px rgba(0,0,0,.15);
        }
        .ac-blank {
            width:36px; height:54px; flex-shrink:0; border-radius:3px;
            background:hsl(48,20%,88%); display:flex;
            align-items:center; justify-content:center; font-size:18px;
        }
        .ac-body { flex:1; min-width:0; text-align:left; }
        .ac-title {
            font-family:Georgia,serif; font-size:14px; font-weight:600;
            color:hsl(202,96%,22%); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
        }
        .ac-author { font-size:12px; color:hsl(0,0%,45%); margin-top:2px; }
        .ac-year   { font-size:11px; color:hsl(0,0%,58%); }
        .ac-meta   { display:flex; flex-direction:column; align-items:flex-end; gap:4px; flex-shrink:0; }
        .ac-badge  { font-size:10px; font-weight:600; padding:2px 6px; border-radius:3px; white-space:nowrap; }
        .ac-badge--readable { background:hsl(142,50%,91%); color:hsl(142,50%,22%); }
        .ac-badge--catalog  { background:hsl(0,0%,92%); color:hsl(0,0%,42%); }
        .ac-star   { font-size:11px; color:hsl(40,80%,38%); white-space:nowrap; }
        .ac-foot {
            display:flex; align-items:center; justify-content:space-between;
            padding:10px 14px; border-top:1px solid hsl(0,0%,92%);
        }
        .ac-add-book {
            font-size:12px; color:hsl(202,96%,37%); text-decoration:none;
            font-weight:500; padding:5px 10px; border-radius:5px;
            border:1px solid hsl(202,96%,80%); transition:background .1s; white-space:nowrap;
        }
        .ac-add-book:hover { background:hsl(202,96%,96%); }
        .ac-see-all {
            background:hsl(202,96%,37%); color:white; border:none;
            border-radius:6px; padding:7px 18px; font-size:13px;
            font-weight:500; font-family:inherit; cursor:pointer;
            white-space:nowrap; transition:background .12s;
        }
        .ac-see-all:hover { background:hsl(202,96%,28%); }

        @media (max-width: 785px) {
            :host { height: 100%; }
            .search-outer { display: flex; justify-content: flex-end; align-items: center; height: 100%; }
            .input-row,
            .input-row:focus-within,
            .search-outer.open .input-row {
                border: none; box-shadow: none; background: transparent;
                padding: 0; border-radius: 8px; flex: none;
            }
            .input-row .trigger-btn { display: none; }
            .input-row .submit { margin-left: 0; padding: 6px 8px; }
        }

        :host(.mobile-exp) {
            position: fixed; inset: 0; z-index: 9000;
            width: 100dvw; height: 100dvh;
            display: flex; flex-direction: column;
            background: white; overflow: hidden;
        }
        :host(.mobile-exp) .search-outer {
            flex: 1; min-height: 0; display: flex; flex-direction: column;
        }
        :host(.mobile-exp) .input-row { display: none; }
        :host(.mobile-exp) .panel {
            position: static; flex: 1; min-height: 0;
            width: 100%; box-sizing: border-box;
            display: flex; flex-direction: column; overflow: hidden; max-height: none;
            border: none; box-shadow: none; border-radius: 0;
            border-top: none;
        }
        :host(.mobile-exp) .panel-chips { max-height: none; }
        :host(.mobile-exp) .ac-scroll { flex: 1; min-height: 0; max-height: none; overflow-y: auto; }
        :host(.mobile-exp) .pf-bar { overflow: visible; flex-wrap: wrap; }

        .mob-back-bar {
            padding: 8px 12px 4px;
            border-bottom: 1px solid hsl(0,0%,92%);
            background: hsl(0,0%,98.5%);
        }
        .mob-back-btn {
            background: none; border: none; cursor: pointer;
            font-size: 14px; font-family: inherit; color: hsl(202,96%,37%);
            padding: 4px 0; font-weight: 500;
        }
        .mob-back-btn:hover { color: hsl(202,96%,28%); }

        @media (max-width: 600px) {
            .pf-bar { overflow-x: auto; scrollbar-width: none; flex-wrap: nowrap; }
            .pf-bar::-webkit-scrollbar { display: none; }
            .pf-btn { font-size: 10px; padding: 11px 4px; }
            .submit { padding: 6px 10px; }
            :host(:not(.mobile-exp)) .ac-scroll { max-height: 40vh; }
            .panel-chips { max-height: 72px; overflow-y: auto; }
        }
    `;

    _renderFacetBar() {
        const f = this._localFilters;
        const facetDropProps = {
            filters: this._localFilters,
            authorResults: this._authorResults,
            subjectResults: this._subjectResults,
            defaultAuthors: this._defaultAuthors,
            defaultSubjects: this._defaultSubjects,
            facetsLoading: this._facetsLoading,
        };
        return html`
            <div class="pf-bar">
                <div class="pf-wrap pf-wrap--first">
                    <ol-facet-select
                        accessible-label="Availability"
                        trigger-label="Availability"
                        .options=${AVAILABILITY_OPTIONS.map(o => ({
        value: o.value, label: o.label,
        count: o.staticCount, subParts: o.subParts,
    }))}
                        .value=${f.availability ?? ''}
                        @ol-facet-select-change=${e => this._emitFilter('availability', e.detail.value)}
                    ></ol-facet-select>
                </div>
                <div class="pf-wrap">
                    <ol-select-popover
                        label="Language"
                        .items=${LANGUAGE_OPTIONS}
                        .selected=${f.languages ?? []}
                        placeholder="Filter languages…"
                        selected-heading="Selected"
                        suggestions-heading="Languages"
                        clear-label="Clear"
                        @ol-select-popover-change=${e => this._emitFilter('languages', e.detail.selected)}
                    >
                        <button slot="trigger" type="button"
                                class="pf-btn ${(f.languages ?? []).length ? 'active' : ''}">
                            ${(f.languages ?? []).length
        ? `Language (${f.languages.length})`
        : 'Language'}
                            <svg class="pf-chevron" xmlns="http://www.w3.org/2000/svg"
                                 viewBox="0 0 24 24" fill="none" stroke="currentColor"
                                 stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
                                 aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>
                        </button>
                    </ol-select-popover>
                </div>
                <div class="pf-wrap">
                    <ol-facet-drop
                        name="genre"
                        placement="bottom-start"
                        .filters=${facetDropProps.filters}
                        .authorResults=${facetDropProps.authorResults}
                        .subjectResults=${facetDropProps.subjectResults}
                        .defaultAuthors=${facetDropProps.defaultAuthors}
                        .defaultSubjects=${facetDropProps.defaultSubjects}
                        .facetsLoading=${facetDropProps.facetsLoading}
                        @ol-facet-change=${this._onDropFacetChange}
                        @ol-facet-search-authors=${this._onDropAuthorSearch}
                        @ol-facet-search-subjects=${this._onDropSubjectSearch}
                        @ol-facet-shuffle-authors=${() => { this._defaultAuthors = shufflePick(POPULAR_AUTHORS, 6); }}
                        @ol-facet-shuffle-subjects=${() => { this._defaultSubjects = shufflePick(POPULAR_SUBJECTS, 6); }}
                    ></ol-facet-drop>
                </div>
                <div class="pf-wrap">
                    <ol-facet-drop
                        name="subject"
                        placement="bottom-end"
                        .filters=${facetDropProps.filters}
                        .authorResults=${facetDropProps.authorResults}
                        .subjectResults=${facetDropProps.subjectResults}
                        .defaultAuthors=${facetDropProps.defaultAuthors}
                        .defaultSubjects=${facetDropProps.defaultSubjects}
                        .facetsLoading=${facetDropProps.facetsLoading}
                        @ol-facet-change=${this._onDropFacetChange}
                        @ol-facet-search-authors=${this._onDropAuthorSearch}
                        @ol-facet-search-subjects=${this._onDropSubjectSearch}
                        @ol-facet-shuffle-authors=${() => { this._defaultAuthors = shufflePick(POPULAR_AUTHORS, 6); }}
                        @ol-facet-shuffle-subjects=${() => { this._defaultSubjects = shufflePick(POPULAR_SUBJECTS, 6); }}
                    ></ol-facet-drop>
                </div>
                <div class="pf-wrap">
                    <ol-facet-drop
                        name="author"
                        placement="bottom-end"
                        .filters=${facetDropProps.filters}
                        .authorResults=${facetDropProps.authorResults}
                        .subjectResults=${facetDropProps.subjectResults}
                        .defaultAuthors=${facetDropProps.defaultAuthors}
                        .defaultSubjects=${facetDropProps.defaultSubjects}
                        .facetsLoading=${facetDropProps.facetsLoading}
                        @ol-facet-change=${this._onDropFacetChange}
                        @ol-facet-search-authors=${this._onDropAuthorSearch}
                        @ol-facet-search-subjects=${this._onDropSubjectSearch}
                        @ol-facet-shuffle-authors=${() => { this._defaultAuthors = shufflePick(POPULAR_AUTHORS, 6); }}
                        @ol-facet-shuffle-subjects=${() => { this._defaultSubjects = shufflePick(POPULAR_SUBJECTS, 6); }}
                    ></ol-facet-drop>
                </div>
                <div class="pf-wrap">
                    <ol-facet-select
                        accessible-label="Sort by"
                        .options=${SORT_OPTIONS}
                        .value=${f.sort ?? ''}
                        @ol-facet-select-change=${e => this._emitFilter('sort', e.detail.value)}
                    ></ol-facet-select>
                </div>
                <div class="pf-wrap pf-wrap--cog pf-wrap--last">
                    <button class="pf-btn" title="Search help"
                            @click=${e => { e.stopPropagation(); this._howtoOpen = true; }}>⚙️</button>
                </div>
            </div>
            <ol-howto-modal .open=${this._howtoOpen} @close=${() => this._howtoOpen = false}></ol-howto-modal>`;
    }

    _renderChipItems(chips) {
        return chips.map(c => html`
            <span class="chip chip-${c.type}">
                ${c.label}
                <button class="chip-x"
                        @click=${e => { e.stopPropagation(); this._handleChipRemove(c); }}>×</button>
            </span>`);
    }

    _renderResults(q) {
        const showResults = q.length >= 2 || this._hasActiveFilters();
        if (this._loading) return html`<div class="ac-spin" role="status" aria-live="polite">Searching…</div>`;
        if (this._acError) return html`<div class="ac-error" role="alert">Search is unavailable — check your connection and try again.</div>`;
        if (!showResults)  return html`<div class="ac-hint-msg" aria-live="polite">Start typing to search, or pick a filter above…</div>`;
        return html`
            <div class="ac-scroll" id="ac-listbox" role="listbox" aria-label="Search suggestions">
                ${this._suggestions.length === 0
        ? html`<div class="ac-empty" aria-live="polite">No results</div>`
        : this._suggestions.map((w, idx) => {
            const ed = bestEdition(w.editions);
            const coverId = ed?.cover_i ?? w.cover_i;
            const edOlid  = ed?.key?.split('/').pop();
            const wOlid   = w.key?.split('/').pop();
            const linkKey = ed?.key ?? w.key;
            const access  = ed?.ebook_access ?? w.ebook_access;
            const cover = edOlid  ? `https://covers.openlibrary.org/b/olid/${edOlid}-S.jpg`
                : coverId ? `https://covers.openlibrary.org/b/id/${coverId}-S.jpg`
                    : wOlid   ? `https://covers.openlibrary.org/b/olid/${wOlid}-S.jpg`
                        : null;
            const isReadable = access === 'public' || access === 'borrowable';
            return html`
                            <a class="ac-row ${this._acFocusIdx === idx ? 'focused' : ''}"
                               id="ac-opt-${idx}"
                               href="${this.siteBase}${linkKey}"
                               target="_blank" rel="noopener"
                               role="option"
                               @click=${() => this._closePanel()}>
                                ${cover
        ? html`<img class="ac-cover" src=${cover} alt="" loading="lazy">`
        : html`<div class="ac-blank">📖</div>`}
                                <div class="ac-body">
                                    <div class="ac-title">${ed?.title ?? w.title}</div>
                                    <div class="ac-author">${(w.author_name ?? []).slice(0, 2).join(', ')}</div>
                                    ${w.first_publish_year ? html`<div class="ac-year">${w.first_publish_year}</div>` : ''}
                                </div>
                                <div class="ac-meta">
                                    <span class="ac-badge ${isReadable ? 'ac-badge--readable' : 'ac-badge--catalog'}">
                                        ${isReadable ? 'Readable' : 'Catalog'}
                                    </span>
                                    ${w.ratings_average
        ? html`<span class="ac-star">★ ${w.ratings_average.toFixed(1)}</span>`
        : ''}
                                </div>
                            </a>`;})}
            </div>
            <div class="ac-foot">
                <a class="ac-add-book" href="${this.siteBase}/books/add"
                   target="_blank" rel="noopener"
                   @click=${e => e.stopPropagation()}>+ Add Book</a>
                <button class="ac-see-all" @click=${() => {
        this._closePanel();
        if (!q && !this._hasActiveFilters()) return;
        const event = new CustomEvent('ol-search', {
            detail: { q, filters: this._localFilters }, bubbles: true, composed: true, cancelable: true,
        });
        this.dispatchEvent(event);
        if (this.showFacets && !event.defaultPrevented) {
            window.location.href = this._buildSearchUrl(q, this._localFilters);
        }
    }}>See all ${this._total.toLocaleString()} results →</button>
            </div>`;
    }

    render() {
        const q        = this._q.trim();
        const chips    = this.showFacets ? buildChips(this._localFilters) : (this.chips ?? []);
        const chipItems = this._renderChipItems(chips);

        if (!this.showFacets) {
            return html`
                <div class="search-outer" role="search">
                    <div class="input-row">
                        <div class="input-controls">
                            <input class="text-input" type="text" autocomplete="off"
                                   placeholder="${this.placeholder}" .value=${this._q}
                                   @input=${this._onInput}
                                   @keydown=${this._onKeyDown}>
                            ${this._q ? html`
                                <button class="clear-btn" aria-label="Clear search"
                                        @click=${e => { e.stopPropagation(); this._clearInput(); }}>✕</button>
                            ` : ''}
                            <button class="submit" @click=${() => this._submit()} aria-label="Search">
                                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                                    <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1 1 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z"/>
                                </svg>
                            </button>
                            <span class="scan-sep"></span>
                            <a class="scan-btn" title="Scan ISBN barcode"
                               href="/barcodescanner?returnTo=/isbn/$$$"
                               target="_blank" rel="noopener"
                               @click=${e => e.stopPropagation()}>
                                <img src="/static/images/icons/barcode_scanner.svg"
                                     alt="Scan barcode" width="18" height="18">
                            </a>
                        </div>
                    </div>
                    ${chips.length ? html`
                        <div class="chip-bar">
                            ${chipItems}
                            ${this._hasActiveFilters() ? html`<button class="clear-all-btn"
                                    aria-label="Clear all filters"
                                    @click=${e => { e.stopPropagation(); this._clearAllFilters(); }}>Clear all</button>` : ''}
                        </div>` : ''}
                </div>`;
        }

        return html`
            <div class="search-outer ${this._open ? 'open' : ''}" role="search">

                <div class="input-row">
                    <button class="trigger-btn"
                            @click=${this._onTriggerClick}
                            aria-expanded=${this._open ? 'true' : 'false'}
                            aria-haspopup="true"
                            aria-controls="search-panel"
                            aria-label="${this.placeholder}">
                        <span class="${!this._q ? 'trigger-placeholder' : ''}">${this._q || this.placeholder}</span>
                    </button>
                    <button class="submit" @click=${this._onTriggerClick} aria-label="Search">
                        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                            <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1 1 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z"/>
                        </svg>
                    </button>
                    <span class="scan-sep"></span>
                    <a class="scan-btn" title="Scan ISBN barcode"
                       href="/barcodescanner?returnTo=/isbn/$$$"
                       target="_blank" rel="noopener"
                       @click=${e => e.stopPropagation()}>
                        <img src="/static/images/icons/barcode_scanner.svg"
                             alt="Scan barcode" width="18" height="18">
                    </a>
                </div>

                ${this._open ? html`
                    <div class="panel" id="search-panel" role="dialog" aria-modal=${this._mobileExpanded ? 'true' : 'false'} aria-label="${this.placeholder}">
                        ${this._mobileExpanded ? html`
                            <div class="mob-back-bar">
                                <button class="mob-back-btn" aria-label="Close search"
                                        @click=${e => { e.stopPropagation(); this._closePanel(); }}>
                                    ← Back
                                </button>
                            </div>` : nothing}

                        <div class="panel-input-row">
                            <input class="text-input panel-input" type="text" autocomplete="off"
                                   placeholder="${this.placeholder}" .value=${this._q}
                                   role="combobox"
                                   aria-label="${this.placeholder}"
                                   aria-expanded="true"
                                   aria-autocomplete="list"
                                   aria-haspopup="listbox"
                                   aria-controls="ac-listbox"
                                   aria-activedescendant=${this._acFocusIdx >= 0 ? `ac-opt-${this._acFocusIdx}` : nothing}
                                   @input=${this._onInput}
                                   @keydown=${this._onKeyDown}>
                            ${this._q ? html`
                                <button class="clear-btn" aria-label="Clear search"
                                        @click=${e => { e.stopPropagation(); this._clearInput(); }}>✕</button>
                            ` : ''}
                            <button class="submit" @click=${() => this._submit()} aria-label="Search">
                                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                                    <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1 1 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z"/>
                                </svg>
                            </button>
                            <span class="scan-sep"></span>
                            <a class="scan-btn" title="Scan ISBN barcode"
                               href="/barcodescanner?returnTo=/isbn/$$$"
                               target="_blank" rel="noopener"
                               @click=${e => e.stopPropagation()}>
                                <img src="/static/images/icons/barcode_scanner.svg"
                                     alt="Scan barcode" width="18" height="18">
                            </a>
                        </div>

                        ${chips.length ? html`
                            <div class="panel-chips">
                                ${chipItems}
                                ${this._hasActiveFilters() ? html`<button class="clear-all-btn"
                                        aria-label="Clear all filters"
                                        @click=${e => { e.stopPropagation(); this._clearAllFilters(); }}>Clear all</button>` : ''}
                            </div>` : ''}
                        ${this._renderFacetBar()}
                        ${this._renderResults(q)}
                    </div>` : ''}
            </div>`;
    }
}

customElements.define('ol-search-bar', OlSearchBar);
