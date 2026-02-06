import { LitElement, html, css } from 'lit';

/**
 * A pagination component that displays page numbers with navigation controls.
 *
 * @element ol-pagination
 *
 * @prop {Number} totalPages - Total number of pages
 * @prop {Number} currentPage - Currently selected page (1-indexed)
 * @prop {String} baseUrl - Optional base URL for generating page links. When provided,
 *                          renders anchor tags for SEO-friendly navigation. When omitted,
 *                          renders buttons and emits events.
 * @prop {String} labelPreviousPage - Aria label for "previous page" button (default: "Go to previous page")
 * @prop {String} labelNextPage - Aria label for "next page" button (default: "Go to next page")
 * @prop {String} labelGoToPage - Aria label template for page buttons, use {page} as placeholder
 *                                (default: "Go to page {page}")
 * @prop {String} labelCurrentPage - Aria label template for current page, use {page} as placeholder
 *                                   (default: "Page {page}, current page")
 * @prop {String} labelPagination - Aria label for the navigation landmark (default: "Pagination")
 *
 * @fires update:page - Fired when a page is selected, detail contains the page number
 *
 * @example
 * <!-- Event-based -->
 * <ol-pagination total-pages="50" current-page="1"></ol-pagination>
 *
 * @example
 * <!-- URL-based -->
 * <ol-pagination total-pages="50" current-page="1" base-url="/search?q=hello"></ol-pagination>
 *
 * @example
 * <!-- With translated labels -->
 * <ol-pagination
 *     total-pages="50"
 *     current-page="1"
 *     label-previous-page="Ir a la página anterior"
 *     label-next-page="Ir a la página siguiente"
 *     label-go-to-page="Ir a la página {page}"
 *     label-current-page="Página {page}, página actual"
 *     label-pagination="Paginación"
 * ></ol-pagination>
 */
export class OlPagination extends LitElement {
    static properties = {
        totalPages: { type: Number, attribute: 'total-pages' },
        currentPage: { type: Number, attribute: 'current-page' },
        baseUrl: { type: String, attribute: 'base-url' },
        labelPreviousPage: { type: String, attribute: 'label-previous-page' },
        labelNextPage: { type: String, attribute: 'label-next-page' },
        labelGoToPage: { type: String, attribute: 'label-go-to-page' },
        labelCurrentPage: { type: String, attribute: 'label-current-page' },
        labelPagination: { type: String, attribute: 'label-pagination' },
        _focusedIndex: { type: Number, state: true }
    };

    static styles = css`
        :host {
            display: block;
            font-family: system-ui, -apple-system, sans-serif;
        }

        .pagination {
            display: flex;
            font-size: 14px;
            gap: 2px;
        }

        .pagination-item {
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 0.2em 0.6em;
            border: 1px solid transparent;
            border-radius: 4px;
            background: transparent;
            color: #444;
            cursor: pointer;
            text-decoration: none;
        }

        .pagination-item:hover:not([aria-disabled="true"]):not([aria-current="page"]) {
            background: rgba(0, 0, 0, 0.1);
        }

        .pagination-item:focus {
            outline: none;
        }

        .pagination-item:focus-visible {
            outline: 2px solid #5B8DD9;
            outline-offset: 2px;
        }

        .pagination-item[aria-current="page"] {
            border-color: #ddd;
            cursor: default;
            user-select: none;
        }

        .pagination-item[aria-disabled="true"] {
            color: #ddd;
            cursor: not-allowed;
        }

        .pagination-arrow {
            padding: 0 0.15em;
        }

        .ellipsis {
            display: flex;
            align-items: center;
            justify-content: center;
            color: #aaa;
            cursor: default;
            user-select: none;
        }
    `;

    /** Left chevron arrow icon */
    static _leftArrowIcon = html`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6"/></svg>`;

    /** Right chevron arrow icon */
    static _rightArrowIcon = html`<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 18 6-6-6-6"/></svg>`;

    constructor() {
        super();
        this.totalPages = 1;
        this.currentPage = 1;
        this.baseUrl = '';
        this._focusedIndex = -1;

        // Translatable label defaults (English)
        this.labelPreviousPage = 'Go to previous page';
        this.labelNextPage = 'Go to next page';
        this.labelGoToPage = 'Go to page {page}';
        this.labelCurrentPage = 'Page {page}, current page';
        this.labelPagination = 'Pagination';
    }

    /**
     * Interpolate a label template by replacing {key} placeholders with values.
     * @param {String} template - The label template (e.g., "Go to page {page}")
     * @param {Object} values - Key-value pairs to substitute (e.g., { page: 5 })
     * @returns {String} The interpolated string
     */
    _interpolateLabel(template, values) {
        return template.replace(/\{(\w+)\}/g, (_, key) => values[key] ?? '');
    }

    /**
     * Build URL for a specific page number.
     * Returns null if baseUrl is not set.
     * @param {Number} page - The page number
     * @returns {String|null} The URL for the page, or null if baseUrl not set
     */
    _getPageUrl(page) {
        if (!this.baseUrl) return null;

        try {
            const url = new URL(this.baseUrl, window.location.origin);
            if (page === 1) {
                url.searchParams.delete('page');
            } else {
                url.searchParams.set('page', page);
            }
            return url.pathname + url.search;
        } catch {
            return null;
        }
    }

    /**
     * Calculate which page numbers to display based on current page and total pages.
     * Always shows exactly 5 page numbers max, adjusting position based on current page:
     * - Near start: 1, 2, 3, 4 ... last (5 total)
     * - Middle: 1 ... current-1, current, current+1 ... last (5 total)
     * - Near end: 1 ... last-3, last-2, last-1, last (5 total)
     * @returns {Array} Array of page numbers and 'ellipsis' markers
     */
    _getVisiblePages() {
        const total = this.totalPages;
        const current = this.currentPage;

        if (total <= 5) return [...Array(total)].map((_, i) => i + 1);
        if (current <= 3) return [1, 2, 3, 4, 'ellipsis-right', total];
        if (current >= total - 2) return [1, 'ellipsis-left', total - 3, total - 2, total - 1, total];

        return [1, 'ellipsis-left', current - 1, current, current + 1, 'ellipsis-right', total];
    }

    /**
     * Get all focusable elements in the pagination
     * @returns {Array} Array of focusable elements (buttons or anchors)
     */
    _getFocusableElements() {
        return Array.from(
            this.shadowRoot.querySelectorAll('.pagination-item:not([aria-disabled="true"])')
        );
    }

    /**
     * Handle keyboard navigation within the pagination
     * @param {KeyboardEvent} e
     */
    _handleKeyDown(e) {
        const focusable = this._getFocusableElements();
        const currentIndex = focusable.indexOf(this.shadowRoot.activeElement);

        switch (e.key) {
        case 'ArrowLeft':
            e.preventDefault();
            if (currentIndex > 0) {
                focusable[currentIndex - 1].focus();
            }
            break;
        case 'ArrowRight':
            e.preventDefault();
            if (currentIndex < focusable.length - 1) {
                focusable[currentIndex + 1].focus();
            }
            break;
        case 'Home':
            e.preventDefault();
            focusable[0]?.focus();
            break;
        case 'End':
            e.preventDefault();
            focusable[focusable.length - 1]?.focus();
            break;
        }
    }

    /**
     * Navigate to a specific page
     * @param {Number} page - The page number to navigate to
     */
    _goToPage(page) {
        if (page < 1 || page > this.totalPages || page === this.currentPage) {
            return;
        }

        this.dispatchEvent(new CustomEvent('update:page', {
            detail: page,
            bubbles: true,
            composed: true
        }));
    }

    /**
     * Handle click on anchor-based page links.
     * Dispatches the update:page event to allow interception.
     * @param {Event} e - Click event
     * @param {Number} page - The page number
     */
    _handlePageClick(e, page) {
        const event = new CustomEvent('update:page', {
            detail: page,
            bubbles: true,
            composed: true,
            cancelable: true
        });
        this.dispatchEvent(event);
    }

    /**
     * Render a pagination item (button or anchor based on URL mode)
     * @param {Object} options - Render options
     * @param {Number} options.page - Target page number
     * @param {String} options.label - Aria label for the item
     * @param {String} options.className - Additional CSS class
     * @param {TemplateResult} options.content - Content to render inside the item
     * @returns {TemplateResult} Lit template for the button or anchor
     */
    _renderPaginationItem({ page, label, className = '', content }) {
        const url = this._getPageUrl(page);
        const isCurrent = page === this.currentPage;
        const ariaCurrent = isCurrent ? 'page' : 'false';

        if (url) {
            return html`
                <a
                    href=${url}
                    class="pagination-item ${className}"
                    aria-label=${label}
                    aria-current=${ariaCurrent}
                    @click=${(e) => this._handlePageClick(e, page)}
                >${content}</a>
            `;
        }

        return html`
            <button
                class="pagination-item ${className}"
                aria-label=${label}
                aria-current=${ariaCurrent}
                @click=${() => this._goToPage(page)}
            >${content}</button>
        `;
    }

    /**
     * Render a single page button/link or ellipsis
     * @param {Number|String} page - Page number or 'ellipsis-left'/'ellipsis-right'
     * @returns {TemplateResult} Lit template for the button or anchor
     */
    _renderPageButton(page) {
        if (typeof page === 'string' && page.startsWith('ellipsis')) {
            return html`<span class="ellipsis" aria-hidden="true">•••</span>`;
        }

        const isCurrent = page === this.currentPage;
        const label = isCurrent
            ? this._interpolateLabel(this.labelCurrentPage, { page })
            : this._interpolateLabel(this.labelGoToPage, { page });

        return this._renderPaginationItem({ page, label, content: page });
    }

    /**
     * Render a navigation arrow (previous or next)
     * @param {String} direction - 'prev' or 'next'
     * @returns {TemplateResult} Lit template for the arrow
     */
    _renderNavArrow(direction) {
        const isPrev = direction === 'prev';
        const isDisabled = isPrev
            ? this.currentPage === 1
            : this.currentPage === this.totalPages;

        if (isDisabled) return html``;

        const page = isPrev ? this.currentPage - 1 : this.currentPage + 1;
        const label = isPrev ? this.labelPreviousPage : this.labelNextPage;
        const icon = isPrev ? OlPagination._leftArrowIcon : OlPagination._rightArrowIcon;

        return this._renderPaginationItem({
            page,
            label,
            className: 'pagination-arrow',
            content: icon
        });
    }

    render() {
        const visiblePages = this._getVisiblePages();

        return html`
            <nav
                class="pagination"
                role="navigation"
                aria-label=${this.labelPagination}
                @keydown=${this._handleKeyDown}
            >
                ${this._renderNavArrow('prev')}
                ${visiblePages.map(page => this._renderPageButton(page))}
                ${this._renderNavArrow('next')}
            </nav>
        `;
    }
}

customElements.define('ol-pagination', OlPagination);
