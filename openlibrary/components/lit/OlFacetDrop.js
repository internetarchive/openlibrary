import { LitElement, html, css } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import {
    GENRE_OPTIONS, FICTION_OPTIONS,
    toggleArrayValue,
} from './search/filters.js';
import './OlPopover.js';

/**
 * Multi-select facet dropdown for genre, author, and subject.
 * Composes `<ol-popover>` for animation, focus trap, and dismissal.
 *
 * @element ol-facet-drop
 *
 * @prop {String}  name            - 'genre'|'author'|'subject'
 * @prop {String}  placement       - OlPopover placement (default 'bottom-start')
 * @prop {Object}  filters         - current filter state
 * @prop {Array}   authorResults   - author search results from parent
 * @prop {Array}   subjectResults  - subject search results from parent
 * @prop {Array}   defaultAuthors  - random author suggestions
 * @prop {Array}   defaultSubjects - random subject suggestions
 * @prop {Boolean} facetsLoading   - true while parent fetches
 *
 * @fires ol-facet-change          - { filter, value, keepOpen }
 * @fires ol-facet-search-authors  - { q }
 * @fires ol-facet-search-subjects - { q }
 * @fires ol-facet-shuffle-authors
 * @fires ol-facet-shuffle-subjects
 */
export class OlFacetDrop extends LitElement {
    static properties = {
        name: { type: String },
        placement: { type: String },
        filters: { type: Object },
        authorResults: { type: Array },
        subjectResults: { type: Array },
        defaultAuthors: { type: Array },
        defaultSubjects: { type: Array },
        facetsLoading: { type: Boolean },

        _isOpen: { state: true },
        _genreSearch: { state: true },
        _authorSearch: { state: true },
        _subjectSearch: { state: true },
    };

    constructor() {
        super();
        this.name            = '';
        this.placement       = 'bottom-start';
        this.filters         = {};
        this.authorResults   = [];
        this.subjectResults  = [];
        this.defaultAuthors  = [];
        this.defaultSubjects = [];
        this.facetsLoading   = false;
        this._isOpen        = false;
        this._genreSearch   = '';
        this._authorSearch  = '';
        this._subjectSearch = '';
    }

    get _label() {
        const f = this.filters ?? {};
        switch (this.name) {
        case 'genre': {
            const total = (f.genres?.length ?? 0) + (f.fictionFilter ? 1 : 0);
            return total ? `Genre (${total})` : 'Genre';
        }
        case 'author':  return f.authors?.length  ? `Author (${f.authors.length})`   : 'Author';
        case 'subject': return f.subjects?.length ? `Subject (${f.subjects.length})` : 'Subject';
        default: return this.name;
        }
    }

    get _isActive() {
        const f = this.filters ?? {};
        switch (this.name) {
        case 'genre':   return (f.genres?.length > 0) || !!f.fictionFilter;
        case 'author':  return f.authors?.length  > 0;
        case 'subject': return f.subjects?.length > 0;
        default: return false;
        }
    }

    _change(filter, value, keepOpen = false) {
        this.dispatchEvent(new CustomEvent('ol-facet-change', {
            detail: { filter, value, keepOpen }, bubbles: true, composed: true,
        }));
    }

    _fireAuthorSearch(q) {
        this._authorSearch = q;
        this.dispatchEvent(new CustomEvent('ol-facet-search-authors', {
            detail: { q }, bubbles: true, composed: true,
        }));
    }

    _fireSubjectSearch(q) {
        this._subjectSearch = q;
        this.dispatchEvent(new CustomEvent('ol-facet-search-subjects', {
            detail: { q }, bubbles: true, composed: true,
        }));
    }

    _onOpen() {
        this._isOpen = true;
        this.setAttribute('data-open', '');
        requestAnimationFrame(() => {
            const input = this.shadowRoot?.querySelector('.search-input, .search-inline');
            input?.focus();
        });
    }

    _onClose() {
        this._isOpen = false;
        this.removeAttribute('data-open');
    }

    static styles = css`
        :host {
            display: inline-flex;
            align-items: stretch;
            font-family: var(--font-family-body, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif);
        }

        /* stretch ol-popover to fill the host */
        ol-popover {
            flex: 1;
            align-self: stretch;
        }

        /* ── Trigger button (matches OlFacetSelect) ─────────────── */

        .trigger {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
            padding: var(--ol-trigger-padding, 0 8px);
            height: 100%;
            min-height: var(--ol-trigger-min-height, 34px);
            flex: 1;
            background: var(--ol-trigger-bg, transparent);
            border: none;
            border-right: var(--ol-trigger-border-right, 1px solid var(--color-border-subtle, #ddd));
            border-radius: var(--ol-trigger-border-radius, 0);
            color: var(--darker-grey, #333);
            font: inherit;
            font-size: var(--ol-trigger-font-size, 14px);
            font-weight: 500;
            line-height: 1.4;
            cursor: pointer;
            white-space: nowrap;
            transition: background 100ms ease;
        }

        @media (hover: hover) and (pointer: fine) {
            .trigger:hover {
                background: var(--ol-trigger-bg-hover, var(--lightest-grey, #f5f5f5));
            }
        }

        .trigger:active { transform: scale(0.97); }
        .trigger:focus { outline: none; }
        .trigger:focus-visible {
            outline: 2px solid var(--color-focus-ring, #0070b8);
            outline-offset: -2px;
        }

        .trigger-chevron {
            display: inline-block;
            width: 14px; height: 14px;
            flex-shrink: 0;
            color: var(--accessible-grey, #666);
            transition: transform 150ms ease-out;
        }

        :host([data-open]) .trigger-chevron { transform: rotate(180deg); }

        @media (prefers-reduced-motion: reduce) {
            .trigger-chevron { transition: none; }
        }

        /* ── Panel content ──────────────────────────────────────── */

        .panel { min-width: 210px; }

        .section-hdr {
            padding: 5px 12px 4px;
            font-size: 11px; font-weight: 600; color: hsl(0,0%,40%);
            background: hsl(0,0%,98%); border-bottom: 1px solid hsl(0,0%,93%);
            letter-spacing: 0.03em; text-transform: uppercase;
        }
        .section-sep { height: 1px; background: hsl(0,0%,90%); }

        .search-wrap {
            position: relative; border-bottom: 1px solid hsl(0,0%,90%);
        }
        .search-icon {
            position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
            color: hsl(0,0%,58%); pointer-events: none;
            display: inline-flex; align-items: center;
        }
        .search-input {
            border: none; padding: 8px 12px 8px 30px;
            font-size: 12px; font-family: inherit; width: 100%;
            box-sizing: border-box; outline: none; color: hsl(0,0%,15%); background: transparent;
        }
        .search-input::placeholder { color: hsl(0,0%,58%); }

        .search-row {
            position: relative; display: flex; align-items: stretch;
            border-bottom: 1px solid hsl(0,0%,90%);
        }
        .search-row-icon {
            position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
            color: hsl(0,0%,58%); pointer-events: none;
            display: inline-flex; align-items: center;
        }
        .search-inline {
            flex: 1; border: none; padding: 8px 12px 8px 30px; font-size: 12px;
            font-family: inherit; outline: none; color: hsl(0,0%,15%); background: transparent;
        }
        .search-inline::placeholder { color: hsl(0,0%,58%); }
        .dice {
            padding: 4px 9px; border: none; border-left: 1px solid hsl(0,0%,90%);
            background: transparent; cursor: pointer; font-size: 15px; flex-shrink: 0; line-height: 1;
        }
        .dice:hover { background: hsl(0,0%,96%); }
        .dice-icon { display: inline-block; transition: transform .2s; }
        .dice:hover .dice-icon { transform: rotate(120deg); }

        .fiction-section { background: hsl(270,20%,97%); padding: 2px 0; }
        .fiction-sep { height: 1px; background: hsl(0,0%,88%); }

        .scroll { max-height: 220px; overflow-y: auto; }

        .item {
            display: flex; align-items: center; gap: 8px;
            padding: 7px 12px; font-size: 12px; font-family: inherit;
            color: hsl(0,0%,20%); cursor: pointer; border: none;
            background: transparent; width: 100%; text-align: left; transition: background .07s;
        }
        .item:hover  { background: hsl(202,96%,96%); color: hsl(202,96%,28%); }
        .item.sel    { background: hsl(202,96%,97%); font-weight: 600; color: hsl(202,96%,28%); }
        .item input[type="checkbox"] { accent-color: hsl(202,96%,37%); flex-shrink: 0; cursor: pointer; }
        .count { margin-left: auto; font-size: 11px; color: hsl(0,0%,55%); }
        .empty { padding: 10px 12px; font-size: 12px; color: hsl(0,0%,55%); text-align: center; }
        .hint  { padding: 6px 12px; font-size: 11px; color: hsl(0,0%,55%); font-style: italic; }

        .footer {
            border-top: 1px solid hsl(0,0%,90%); background: white;
            padding: 5px 10px; display: flex; justify-content: center;
        }
        .clear {
            width: 100%;
            font-size: 11px; color: hsl(0,72%,38%); background: none; border: none;
            cursor: pointer; padding: 6px 8px; border-radius: 4px; font-family: inherit;
            font-weight: 500; transition: background .1s; text-align: center;
        }
        .clear:hover { background: hsl(0,72%,95%); }
    `;

    static _chevronIcon = html`
        <svg class="trigger-chevron" xmlns="http://www.w3.org/2000/svg"
             viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"
             aria-hidden="true">
            <path d="m6 9 6 6 6-6"/>
        </svg>`;

    get _searchSvg() {
        return html`<svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
            <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1 1 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z"/>
        </svg>`;
    }

    _renderGenre(f) {
        const selectedGenres = f.genres ?? [];
        const selGenreOpts   = GENRE_OPTIONS.filter(o => selectedGenres.includes(o.value));
        const unselVisible   = GENRE_OPTIONS.filter(o =>
            !selectedGenres.includes(o.value) &&
            (!this._genreSearch || o.label.toLowerCase().includes(this._genreSearch.toLowerCase()))
        );
        const hasAnySelection = selectedGenres.length > 0 || !!f.fictionFilter;
        return html`
            <div class="search-wrap">
                <span class="search-icon">${this._searchSvg}</span>
                <input class="search-input" placeholder="Filter genres…" .value=${this._genreSearch}
                       @input=${e => { this._genreSearch = e.target.value; }}
                       @click=${e => e.stopPropagation()}>
            </div>
            <div class="fiction-section">
                ${FICTION_OPTIONS.map(o => html`
                    <button class="item ${f.fictionFilter === o.value ? 'sel' : ''}"
                            @click=${() => this._change('fictionFilter', f.fictionFilter === o.value ? '' : o.value, true)}>
                        <input type="checkbox" .checked=${f.fictionFilter === o.value} readonly> ${o.label}
                    </button>`)}
            </div>
            <div class="fiction-sep"></div>
            ${selGenreOpts.length ? html`
                <div class="section-hdr">Selected</div>
                ${selGenreOpts.map(o => html`
                    <button class="item sel"
                            @click=${() => this._change('genres', toggleArrayValue(selectedGenres, o.value), true)}>
                        <input type="checkbox" .checked=${true} readonly> ${o.label}
                    </button>`)}
                <div class="section-sep"></div>
            ` : ''}
            <div class="section-hdr">${selGenreOpts.length ? 'Suggestions' : 'Genres'}</div>
            <div class="scroll">
                ${unselVisible.length === 0
        ? html`<div class="empty">${this._genreSearch ? 'No matches' : 'All selected'}</div>`
        : ''}
                ${repeat(unselVisible, o => o.value, o => html`
                    <button class="item"
                            @click=${() => this._change('genres', toggleArrayValue(selectedGenres, o.value), true)}>
                        <input type="checkbox" .checked=${false} readonly> ${o.label}
                    </button>`)}
            </div>
            ${hasAnySelection ? html`
                <div class="footer">
                    <button class="clear" @click=${e => {
        e.stopPropagation();
        this._change('genres', []);
        this._change('fictionFilter', '', true);
    }}>Clear selections</button>
                </div>` : ''}`;
    }

    _renderAuthor(f) {
        const searching       = this._authorSearch.trim().length >= 2;
        const selectedAuthors = f.authors ?? [];
        const suggestions     = searching ? this.authorResults : this.defaultAuthors;
        const unselSugg       = suggestions
            .map(a => typeof a === 'string' ? { name: a } : a)
            .filter(a => !selectedAuthors.includes(a.name));

        return html`
            <div class="search-row">
                <span class="search-row-icon">${this._searchSvg}</span>
                <input class="search-inline" placeholder="Search authors…" .value=${this._authorSearch}
                       @input=${e => this._fireAuthorSearch(e.target.value)}
                       @click=${e => e.stopPropagation()}>
                <button class="dice" title="Shuffle suggestions"
                        @click=${e => { e.stopPropagation(); this.dispatchEvent(new CustomEvent('ol-facet-shuffle-authors', { bubbles: true, composed: true })); }}>
                    <span class="dice-icon">🎲</span>
                </button>
            </div>
            ${selectedAuthors.length ? html`
                <div class="section-hdr">Selected</div>
                ${selectedAuthors.map(name => html`
                    <button class="item sel"
                            @click=${() => this._change('authors', toggleArrayValue(selectedAuthors, name), true)}>
                        <input type="checkbox" .checked=${true} readonly> ${name}
                    </button>`)}
                <div class="section-sep"></div>
            ` : ''}
            <div class="section-hdr">${selectedAuthors.length ? 'Suggestions' : 'Authors'}</div>
            <div class="scroll">
                ${this.facetsLoading ? html`<div class="empty">Loading…</div>` : ''}
                ${!searching && !this.facetsLoading && this.defaultAuthors.length === 0
        ? html`<div class="hint">Type to search authors</div>` : ''}
                ${searching && !this.facetsLoading && this.authorResults.length === 0
        ? html`<div class="empty">No authors found</div>` : ''}
                ${!this.facetsLoading ? repeat(unselSugg, a => a.name, a => html`
                    <button class="item"
                            @click=${() => this._change('authors', toggleArrayValue(selectedAuthors, a.name), true)}>
                        <input type="checkbox" .checked=${false} readonly>
                        ${a.name}
                        ${a.work_count ? html`<span class="count">${a.work_count.toLocaleString()}</span>` : ''}
                    </button>`) : ''}
            </div>
            ${selectedAuthors.length ? html`
                <div class="footer">
                    <button class="clear"
                            @click=${e => { e.stopPropagation(); this._change('authors', []); }}>
                        Clear selections
                    </button>
                </div>` : ''}`;
    }

    _renderSubject(f) {
        const searching        = this._subjectSearch.trim().length >= 2;
        const selectedSubjects = f.subjects ?? [];
        const suggestions      = searching ? this.subjectResults : this.defaultSubjects;
        const unselSugg        = suggestions
            .map(s => typeof s === 'string' ? { name: s } : s)
            .filter(s => !selectedSubjects.includes(s.name));

        return html`
            <div class="search-row">
                <span class="search-row-icon">${this._searchSvg}</span>
                <input class="search-inline" placeholder="Search subjects…" .value=${this._subjectSearch}
                       @input=${e => this._fireSubjectSearch(e.target.value)}
                       @click=${e => e.stopPropagation()}>
                <button class="dice" title="Shuffle suggestions"
                        @click=${e => { e.stopPropagation(); this.dispatchEvent(new CustomEvent('ol-facet-shuffle-subjects', { bubbles: true, composed: true })); }}>
                    <span class="dice-icon">🎲</span>
                </button>
            </div>
            ${selectedSubjects.length ? html`
                <div class="section-hdr">Selected</div>
                ${selectedSubjects.map(name => html`
                    <button class="item sel"
                            @click=${() => this._change('subjects', toggleArrayValue(selectedSubjects, name), true)}>
                        <input type="checkbox" .checked=${true} readonly> ${name}
                    </button>`)}
                <div class="section-sep"></div>
            ` : ''}
            <div class="section-hdr">${selectedSubjects.length ? 'Suggestions' : 'Subjects'}</div>
            <div class="scroll">
                ${this.facetsLoading ? html`<div class="empty">Loading…</div>` : ''}
                ${!searching && !this.facetsLoading && this.defaultSubjects.length === 0
        ? html`<div class="hint">Type to search subjects</div>` : ''}
                ${searching && !this.facetsLoading && this.subjectResults.length === 0
        ? html`<div class="empty">No subjects found</div>` : ''}
                ${!this.facetsLoading ? repeat(unselSugg, s => s.name, s => html`
                    <button class="item"
                            @click=${() => this._change('subjects', toggleArrayValue(selectedSubjects, s.name), true)}>
                        <input type="checkbox" .checked=${false} readonly>
                        ${s.name}
                        ${s.work_count ? html`<span class="count">${s.work_count.toLocaleString()}</span>` : ''}
                    </button>`) : ''}
            </div>
            ${selectedSubjects.length ? html`
                <div class="footer">
                    <button class="clear"
                            @click=${e => { e.stopPropagation(); this._change('subjects', []); }}>
                        Clear selections
                    </button>
                </div>` : ''}`;
    }

    render() {
        const f = this.filters ?? {};
        let panelContent;
        switch (this.name) {
        case 'genre':   panelContent = this._renderGenre(f);   break;
        case 'author':  panelContent = this._renderAuthor(f);  break;
        case 'subject': panelContent = this._renderSubject(f); break;
        default: panelContent = html``;
        }

        return html`
            <ol-popover
                placement=${this.placement}
                aria-label=${`Filter by ${this.name}`}
                @ol-popover-open=${this._onOpen}
                @ol-popover-close=${this._onClose}
            >
                <button
                    slot="trigger"
                    type="button"
                    class="trigger"
                    aria-haspopup="dialog"
                >
                    ${this._label}
                    ${OlFacetDrop._chevronIcon}
                </button>
                <div class="panel">${panelContent}</div>
            </ol-popover>
        `;
    }
}

customElements.define('ol-facet-drop', OlFacetDrop);
