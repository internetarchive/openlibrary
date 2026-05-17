import { LitElement, html } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import './OlFacetSelect.js';

/**
 * Facet options for the header search bar.
 * Labels are in English; i18n can be added via a `labels` property
 * following the same pattern as OlPagination's label-* attributes.
 */
const FACET_OPTIONS = [
    { value: 'all',      label: 'All' },
    { value: 'title',    label: 'Title' },
    { value: 'author',   label: 'Author' },
    { value: 'text',     label: 'Text' },
    { value: 'subject',  label: 'Subject' },
    { value: 'lists',    label: 'Lists' },
    { value: 'advanced', label: 'Advanced' },
];

const COLLAPSE_BREAKPOINT = 568;

/**
 * Mobile-optimized search bar for the Open Library header.
 *
 * Renders the full search bar structure (.search-bar-component) as a
 * Light DOM component so that existing global CSS classes, jQuery event
 * handlers, and the SearchBar.js autocomplete bridge all continue to work
 * without modification.
 *
 * Replaces the native <select> facet picker with `<ol-facet-select>`.
 * Handles mobile collapse/expand behavior internally, removing that
 * responsibility from SearchBar.js when this component is present.
 *
 * SearchBar.js detects this element and switches to an event-driven path:
 *   - Listens for `ol-facet-change` events instead of native select change
 *   - Skips `initCollapsibleMode` (handled here)
 *
 * @element ol-search-bar
 *
 * @prop {String} facet - Initial facet value (default "all")
 * @prop {String} q     - Initial query value (default "")
 *
 * @fires ol-facet-change - Fired when the user changes the facet.
 *     detail: { facet: String, label: String }
 */
export class OlSearchBar extends LitElement {
    // Render into the element itself (light DOM) so that:
    // 1. Global CSS classes (.search-bar-component, .search-bar-input, etc.) apply
    // 2. jQuery in SearchBar.js can find form, input, and results elements
    // 3. No shadow DOM encapsulation — rollback is a one-line template change
    createRenderRoot() {
        return this;
    }

    static properties = {
        facet: { type: String },
        q: { type: String },
        _collapsible: { state: true },
        _collapsed: { state: true },
    };

    constructor() {
        super();
        this.facet = 'all';
        this.q = '';
        this._collapsible = false;
        this._collapsed = false;
        this._resizeHandler = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._resizeHandler = () => this._updateCollapsible();
        window.addEventListener('resize', this._resizeHandler);
        // Evaluate immediately (before first render queues)
        this._updateCollapsible();
        // Also handle clicks to expand/collapse
        document.addEventListener('click', this._onDocumentClick.bind(this));
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        window.removeEventListener('resize', this._resizeHandler);
        document.removeEventListener('click', this._onDocumentClick.bind(this));
    }

    firstUpdated() {
        // Set the initial query value once after first render.
        // We don't bind input.value in the template to avoid LIT overwriting
        // user-typed content or SearchBar.js-set values on subsequent renders.
        const input = this.querySelector('input[name="q"]');
        if (input && this.q) input.value = this.q;
        // Tell SearchBar.js the light-DOM is now queryable (form/input/results exist).
        this.dispatchEvent(new CustomEvent('ol-search-bar-ready'));
    }

    render() {
        const formClasses = {
            'search-bar-input': true,
            'in-collapsible-mode': this._collapsible,
        };

        return html`
            <div class="search-bar-component">
                <div class="search-bar">
                    <ol-facet-select
                        .options=${FACET_OPTIONS}
                        value=${this.facet}
                        accessible-label="Search by"
                        @ol-facet-select-change=${this._onFacetChange}
                    ></ol-facet-select>
                    <form
                        class=${classMap(formClasses)}
                        action="/search"
                        method="get"
                        role="search"
                    >
                        <input
                            type="text"
                            name="q"
                            placeholder="Search"
                            aria-label="Search"
                            autocomplete="off"
                        >
                        <input
                            name="mode"
                            type="checkbox"
                            aria-hidden="true"
                            aria-label="Search checkbox"
                            checked
                            value=""
                            id="ftokenstop"
                            class="hidden instantsearch-mode"
                        >
                        <input
                            type="submit"
                            value=""
                            class="search-bar-submit"
                            aria-label="Search submit"
                        >
                        <div class="vertical-separator"></div>
                        <a
                            id="barcode_scanner_link"
                            class="search-by-barcode-submit"
                            aria-label="Search by barcode"
                            title="Search by barcode"
                            href="/barcodescanner?returnTo=/isbn/$$$"
                        ></a>
                    </form>
                </div>
                <div class="search-dropdown">
                    <ul class="search-results"></ul>
                </div>
            </div>
        `;
    }

    // ── Collapsible mode (mobile) ──────────────────────────────────

    _updateCollapsible() {
        const shouldCollapse = window.innerWidth < COLLAPSE_BREAKPOINT;
        if (shouldCollapse && !this._collapsible) {
            this._collapsible = true;
            this._collapsed = true;
            this._applyExpandedClass(false);
        } else if (!shouldCollapse && this._collapsible) {
            this._collapsible = false;
            this._collapsed = false;
            this._applyExpandedClass(false);
            this._showLogo(true);
        }
    }

    _applyExpandedClass(expanded) {
        this.closest('.search-component')?.classList.toggle('expanded', expanded);
        this._collapsed = !expanded;
    }

    _showLogo(visible) {
        document.querySelector('header#header-bar .logo-component')
            ?.classList.toggle('hidden', !visible);
    }

    expand() {
        this._showLogo(false);
        this._applyExpandedClass(true);
    }

    collapse() {
        this._showLogo(true);
        this._applyExpandedClass(false);
    }

    _onDocumentClick(e) {
        if (!this._collapsible) return;
        const searchComp = this.closest('.search-component');
        const target = e.target;

        const clickedInSearch = searchComp?.contains(target);
        const clickedSearchLink = target.closest?.('a[href="/search"]');

        if (clickedInSearch || clickedSearchLink) {
            if (this._collapsed) {
                e.preventDefault();
                this.expand();
                this.querySelector('input[name="q"]')?.focus();
            }
        } else if (!this._collapsed) {
            this.collapse();
        }
    }

    // ── Facet change ───────────────────────────────────────────────

    _onFacetChange(e) {
        this.facet = e.detail.value;
        this.dispatchEvent(new CustomEvent('ol-facet-change', {
            bubbles: true, composed: true,
            detail: { facet: e.detail.value, label: e.detail.label },
        }));
    }
}

customElements.define('ol-search-bar', OlSearchBar);
