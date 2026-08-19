import { LitElement, html, css, nothing } from 'lit';

/**
 * A Netflix-style carousel component with page-based navigation.
 *
 * Items are passed as direct children. The component controls their width
 * based on responsive breakpoints, shows peek areas at the edges, and
 * provides arrow buttons and bar-segment indicators for navigation.
 *
 * The viewport is a native scroll container: the component declares snap
 * points and reports the settled page, the browser does everything else.
 * Off-page items are deliberately not `inert` — in a scroll container they
 * are legitimately reachable by tab, screen reader and find-in-page.
 *
 * Deferring off-page images is the browser's job: put the real URL in `src`
 * and mark it `loading="lazy"`. A scroll container clips its overflow, so
 * off-page items never intersect the viewport and are never fetched. Do not
 * pass a placeholder `src` with the real URL parked in a data attribute —
 * that is a pre-`loading` carousel-library convention and it defeats this.
 *
 * @element ol-carousel
 *
 * @prop {Number} peek - Fraction of item width visible at edges (0–0.5, default: 0.03)
 * @prop {Number} gap - Gap between items in px (default: 8)
 * @prop {String} label - Accessible label for the carousel region (default: "Carousel")
 * @prop {String} labelPrevious - Aria-label for previous arrow (default: "Previous page")
 * @prop {String} labelNext - Aria-label for next arrow (default: "Next page")
 * @prop {String} labelPages - Aria-label for the page indicator tablist (default: "Carousel pages")
 * @prop {String} labelGoToPage - Aria-label template for each page indicator, use {page} and
 *                                {total} as placeholders (default: "Go to page {page} of {total}")
 * @prop {Boolean} showIndicators - When present, shows the page indicator bar (default: false)
 *
 * @fires ol-carousel-page-change - Fired once the scroller settles on a new page. detail: { page: Number, totalPages: Number }
 *
 * @slot - Carousel items. Each direct child becomes one card; the component controls its width.
 *
 * @cssprop [--ol-carousel-arrow-color=var(--neutral-700)] - Colour of the arrow glyphs
 * @cssprop [--ol-carousel-arrow-icon-bg=var(--color-surface)] - Background of the round arrow buttons
 * @cssprop [--ol-carousel-arrow-icon-border=var(--color-border-subtle)] - Border of the round arrow buttons
 * @cssprop [--ol-carousel-arrow-icon-size=36px] - Diameter of the round arrow buttons
 * @cssprop [--ol-carousel-indicator-color=var(--neutral-300)] - Colour of the inactive page indicators
 * @cssprop [--ol-carousel-indicator-active=var(--neutral-700)] - Colour of the active page indicator
 * @cssprop [--ol-carousel-viewport-padding=0px] - Inner viewport padding so slotted items can show a hover lift/shadow without being clipped
 *
 * Browser support: scroll-snap (Safari 11) and scroll-padding (14.5) are the
 * load-bearing ones. scroll-behavior (15.4) and overscroll-behavior (16)
 * degrade gracefully. scrollend is Safari 26.2, so it is feature-detected.
 *
 * @example
 * <ol-carousel label="Trending Books">
 *   <div class="book-card"><img src="/cover1.jpg" alt="Book 1" /></div>
 *   <div class="book-card"><img src="/cover2.jpg" alt="Book 2" /></div>
 * </ol-carousel>
 */
export class OlCarousel extends LitElement {
    static properties = {
        peek: { type: Number },
        gap: { type: Number },
        label: { type: String },
        labelPrevious: { type: String, attribute: 'label-previous' },
        labelNext: { type: String, attribute: 'label-next' },
        labelPages: { type: String, attribute: 'label-pages' },
        labelGoToPage: { type: String, attribute: 'label-go-to-page' },
        showIndicators: { type: Boolean, attribute: 'show-indicators' },
        _page: { type: Number, state: true },
        _totalPages: { type: Number, state: true },
        _columns: { type: Number, state: true },
        _itemCount: { type: Number, state: true },
        _atStart: { type: Boolean, state: true },
        _atEnd: { type: Boolean, state: true },
    };

    static styles = css`
        :host {
            display: block;
            /* A shadow root is not a stacking context — without this the
               edge fades' and arrows' z-index compete with the whole page. */
            isolation: isolate;
            --_arrow-color: var(--ol-carousel-arrow-color, var(--neutral-700));
            --_arrow-icon-bg: var(--ol-carousel-arrow-icon-bg, var(--color-surface));
            --_arrow-icon-border: var(--ol-carousel-arrow-icon-border, var(--color-border-subtle));
            --_arrow-icon-size: var(--ol-carousel-arrow-icon-size, 36px);
            --_indicator-color: var(--ol-carousel-indicator-color, var(--neutral-300));
            --_indicator-active: var(--ol-carousel-indicator-active, var(--neutral-700));
            /* Breathing room inside the clipped viewport so slotted items can
               show a hover lift/shadow without it being cut off. Opt-in: 0 by
               default, set --ol-carousel-viewport-padding to enable. */
            --_viewport-padding: var(--ol-carousel-viewport-padding, 0px);
        }

        .carousel {
            position: relative;
        }

        /* ── Indicators ── */
        .indicators {
            display: flex;
            justify-content: flex-end;
            gap: 2px;
            padding: 0 4px 6px;
        }

        .indicators[hidden] {
            display: none;
        }

        .indicator {
            height: 2px;
            flex: 1;
            max-width: 24px;
            border: none;
            border-radius: 1px;
            padding: 0;
            background: var(--_indicator-color);
            cursor: pointer;
            transition: background 0.2s;
        }

        .indicator:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        .indicator[aria-current="true"] {
            background: var(--_indicator-active);
        }

        /* ── Frame ──
           Arrows and fades live here, not in the scroller — absolutely
           positioned children of a scroll container scroll away. */
        .frame {
            position: relative;
        }

        /* ── Viewport (the scroll container) ── */
        .viewport {
            display: flex;
            gap: var(--_gap, 4px);
            overflow-x: auto;
            /* Can't stay visible beside a scrolling axis; padding-block gives
               the hover lift room instead. */
            overflow-y: hidden;
            padding-block: var(--_viewport-padding);
            scroll-snap-type: x mandatory;
            /* Start padding is the edge peek; the end stays flush. */
            scroll-padding-inline: calc(var(--_peek, 0.03) * 100%) 0;
            scroll-behavior: smooth;
            /* No macOS history swipe when the rail hits its end. */
            overscroll-behavior-x: contain;
            scrollbar-width: none;
        }

        /* scrollbar-width is Safari 18.2+; this covers older WebKit/Blink. */
        .viewport::-webkit-scrollbar {
            display: none;
        }

        @media (prefers-reduced-motion: reduce) {
            .viewport {
                scroll-behavior: auto;
            }
        }

        /* ── Slotted items ── */
        ::slotted(*) {
            flex: 0 0 var(--_item-width);
            min-width: 0;
            box-sizing: border-box;
            margin: 0;
            -webkit-user-drag: none;
        }

        /* ── Edge gradients (always visible to hint at more content) ── */
        .edge-fade {
            position: absolute;
            top: 0;
            bottom: 0;
            width: calc(var(--_peek, 0.075) * 100% + 16px);
            z-index: var(--z-index-local-1);
            pointer-events: none;
        }

        .edge-fade[hidden] {
            display: none;
        }

        .edge-fade.prev {
            left: 0;
            background: linear-gradient(to left, transparent, rgba(255, 255, 255, 0.4) 40%, rgba(255, 255, 255, 0.85));
        }

        .edge-fade.next {
            right: 0;
            background: linear-gradient(to right, transparent, rgba(255, 255, 255, 0.4) 40%, rgba(255, 255, 255, 0.85));
        }

        /* ── Arrow buttons ── */
        .arrow {
            display: flex;
            align-items: center;
            justify-content: center;
            position: absolute;
            top: 0;
            bottom: 0;
            width: var(--_arrow-icon-size);
            z-index: var(--z-index-local-2);
            border: none;
            background: none;
            cursor: pointer;
            opacity: 0;
            transition: opacity 0.2s;
            padding: 0;
        }

        .arrow:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: -2px;
        }

        .arrow.prev {
            left: 8px;
        }

        .arrow.next {
            right: 8px;
        }

        .arrow[hidden] {
            display: none;
        }

        /* Show arrow icons on hover/focus, hide on touch */
        @media (hover: hover) {
            .carousel:hover .arrow:not([hidden]),
            .carousel:focus-within .arrow:not([hidden]) {
                opacity: 1;
            }
        }

        @media (hover: none) {
            .arrow {
                display: none;
            }
        }

        .arrow-icon {
            display: flex;
            align-items: center;
            justify-content: center;
            width: var(--_arrow-icon-size);
            height: 64px;
            border-radius: 16px;
            background: var(--_arrow-icon-bg);
            color: var(--_arrow-color);
            border: 1px solid var(--_arrow-icon-border);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
        }

        /* Tactile press: nudge the icon down in scale, matching ol-button,
           ol-chip, ol-pagination et al. Snaps (no transition) like the others. */
        .arrow:active .arrow-icon {
            transform: scale(0.92);
        }

        .arrow svg {
            width: 28px;
            height: 28px;
        }
    `;

    /** Left chevron SVG */
    static _leftArrow = html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>`;

    /** Right chevron SVG */
    static _rightArrow = html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>`;

    /** Breakpoints: [maxWidth, columns] sorted ascending. Last entry is the default. */
    static _breakpoints = [
        [480, 3],
        [600, 4],
        [768, 5],
        [1024, 7],
        [Infinity, 8],
    ];

    /** Safari only got `scrollend` in 26.2; without it we debounce `scroll`. */
    static _supportsScrollEnd = typeof window !== 'undefined' && 'onscrollend' in window;

    /** Idle gap (ms) standing in for `scrollend`. Long enough to outlast a
     *  fling's momentum tail, short enough to still feel immediate. */
    static _scrollEndFallbackDelay = 120;

    constructor() {
        super();
        this.peek = 0.03;
        this.gap = 8;
        // Translatable label defaults (English). Consumers pass $_() values in.
        this.label = 'Carousel';
        this.labelPrevious = 'Previous page';
        this.labelNext = 'Next page';
        this.labelPages = 'Carousel pages';
        this.labelGoToPage = 'Go to page {page} of {total}';
        this.showIndicators = false;
        this._page = 0;
        this._totalPages = 1;
        this._columns = 6;
        this._itemCount = 0;
        this._atStart = true;
        this._atEnd = false;

        // Resting scrollLeft per page, measured in _measurePageOffsets.
        this._pageOffsets = [0];
        this._maxScroll = 0;

        // Keeps a settle that lands back on the same page from re-emitting.
        this._lastEmittedPage = 0;

        /** @type {ResizeObserver|null} */
        this._resizeObserver = null;
        this._scrollEndTimer = null;

        this._onScroll = this._onScroll.bind(this);
        this._onScrollEnd = this._onScrollEnd.bind(this);
        this._onIndicatorKeydown = this._onIndicatorKeydown.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        this._resizeObserver = new ResizeObserver((entries) => {
            const width = entries[0]?.contentRect.width ?? this.clientWidth;
            this._updateColumns(width);
            this._applyTrackLayout();
            this._refreshGeometry();
        });
        this._resizeObserver.observe(this);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._resizeObserver?.disconnect();
        this._resizeObserver = null;
        clearTimeout(this._scrollEndTimer);
    }

    firstUpdated() {
        this._countItems();
        this._updateColumns(this.clientWidth);
        this._recalculate();
        this._applyTrackLayout();
        this._refreshGeometry();
    }

    updated(changedProperties) {
        if (changedProperties.has('_columns') || changedProperties.has('_itemCount')
            || changedProperties.has('peek') || changedProperties.has('gap')) {
            this._recalculate();
            this._applyTrackLayout();
            this._refreshGeometry();
        }
    }

    // ── Public API ──

    /** Current page (0-indexed). Meaningful after `firstUpdated`/`updateComplete`. */
    get page() { return this._page; }

    /** Total number of pages. Depends on measured width, so read after `updateComplete`. */
    get totalPages() { return this._totalPages; }

    /** Advance to the next page. */
    next() {
        this.goToPage(this._page + 1);
    }

    /** Go to the previous page. */
    prev() {
        this.goToPage(this._page - 1);
    }

    /** Jump to a specific page (0-indexed). */
    goToPage(index) {
        const scroller = this._scroller;
        if (!scroller) return;
        const clamped = Math.max(0, Math.min(index, this._totalPages - 1));
        // Optimistic, so indicators move now; _syncFromScroll reconciles.
        this._page = clamped;
        // No `behavior`: defers to CSS scroll-behavior, so the reduced-motion
        // media query covers both paths.
        scroller.scrollTo({ left: this._pageOffsets[clamped] ?? 0 });
    }

    // ── Geometry ──

    /** @returns {HTMLElement|null} the scroll container */
    get _scroller() {
        return this.shadowRoot?.querySelector('.viewport') ?? null;
    }

    /** @returns {Element[]} slotted carousel items */
    get _items() {
        return this.shadowRoot?.querySelector('slot')?.assignedElements() ?? [];
    }

    _countItems() {
        this._itemCount = this._items.length;
    }

    _updateColumns(width) {
        for (const [maxWidth, cols] of OlCarousel._breakpoints) {
            if (width <= maxWidth) {
                if (cols !== this._columns) {
                    this._columns = cols;
                }
                break;
            }
        }
    }

    _recalculate() {
        const count = this._itemCount;
        const cols = this._columns;
        if (count <= 0 || cols <= 0) {
            this._totalPages = 1;
            this._page = 0;
            return;
        }
        this._totalPages = Math.max(1, Math.ceil(count / cols));
        if (this._page >= this._totalPages) {
            this._page = this._totalPages - 1;
        }
    }

    /** Re-derive everything layout-dependent after a resize or slot change. */
    _refreshGeometry() {
        this._applySnapPoints();
        this._measurePageOffsets();
        this._syncFromScroll();
    }

    /** Mark page boundaries; the browser owns landing on them. The last item
     *  gets `end` so a short final page rests flush against the edge. */
    _applySnapPoints() {
        const items = this._items;
        const cols = this._columns;
        const last = items.length - 1;
        items.forEach((item, i) => {
            if (i === last) {
                item.style.scrollSnapAlign = 'end';
            } else if (cols > 0 && i % cols === 0) {
                item.style.scrollSnapAlign = 'start';
            } else {
                item.style.scrollSnapAlign = '';
            }
        });
    }

    /** Measure each page's resting scrollLeft from the DOM. Only needs to be
     *  close enough to pick the right snap point — the browser corrects it. */
    _measurePageOffsets() {
        const scroller = this._scroller;
        const items = this._items;
        if (!scroller || !items.length) {
            this._pageOffsets = [0];
            this._maxScroll = 0;
            return;
        }

        const maxScroll = Math.max(0, scroller.scrollWidth - scroller.clientWidth);
        const scrollerLeft = scroller.getBoundingClientRect().left;
        const peekPx = this.peek * scroller.clientWidth;
        const offsets = [];
        // Cached so _syncFromScroll never forces a layout mid-scroll.
        this._maxScroll = maxScroll;

        for (let page = 0; page < this._totalPages; page++) {
            // Matches the `scroll-snap-align: end` on the last item.
            if (page === this._totalPages - 1) {
                offsets.push(maxScroll);
                continue;
            }
            const item = items[page * this._columns];
            if (!item) {
                offsets.push(maxScroll);
                continue;
            }
            // Scroll-invariant distance from the scroller's start edge.
            const itemLeft = item.getBoundingClientRect().left - scrollerLeft + scroller.scrollLeft;
            offsets.push(Math.min(maxScroll, Math.max(0, itemLeft - peekPx)));
        }

        this._pageOffsets = offsets.length ? offsets : [0];
    }

    /** Nearest page to the scroller's current position. */
    _pageFromScroll() {
        const scroller = this._scroller;
        if (!scroller) return 0;
        const x = scroller.scrollLeft;
        let best = 0;
        let bestDist = Infinity;
        this._pageOffsets.forEach((offset, page) => {
            const dist = Math.abs(offset - x);
            if (dist < bestDist) {
                bestDist = dist;
                best = page;
            }
        });
        return best;
    }

    /** Pull page index and edge state off the live scroll position. Reads only
     *  scrollLeft, so it is safe on every scroll event. */
    _syncFromScroll() {
        const scroller = this._scroller;
        if (!scroller) return;
        // 1px slack absorbs sub-pixel resting positions on fractional widths.
        this._atStart = scroller.scrollLeft <= 1;
        this._atEnd = scroller.scrollLeft >= this._maxScroll - 1;
        this._page = this._pageFromScroll();
    }

    // ── Scroll tracking ──

    _onScroll() {
        // Keeps indicators, arrows and fades in step mid-scroll.
        this._syncFromScroll();

        if (!OlCarousel._supportsScrollEnd) {
            clearTimeout(this._scrollEndTimer);
            this._scrollEndTimer = setTimeout(this._onScrollEnd, OlCarousel._scrollEndFallbackDelay);
        }
    }

    /** The only place page-change fires, so a multi-page fling reports once. */
    _onScrollEnd() {
        this._syncFromScroll();
        if (this._page !== this._lastEmittedPage) {
            this._lastEmittedPage = this._page;
            this._emitPageChange();
        }
    }

    _emitPageChange() {
        this.dispatchEvent(new CustomEvent('ol-carousel-page-change', {
            detail: { page: this._page, totalPages: this._totalPages },
            bubbles: true,
            composed: true,
        }));
    }

    // ── Layout ──

    /** Set layout CSS custom properties on the host element.
     *  These cascade into the shadow DOM for ::slotted(*) and .arrow sizing. */
    _applyTrackLayout() {
        const cols = this._columns;
        const peek = this.peek;
        const gap = this.gap;
        const itemPercent = ((1 - peek * 2) / cols) * 100;

        this.style.setProperty('--_item-width', `calc(${itemPercent}% - ${gap}px + ${gap / cols}px)`);
        this.style.setProperty('--_peek', String(peek));
        this.style.setProperty('--_gap', `${gap}px`);
    }

    // ── Slot change ──

    _onSlotChange() {
        this._countItems();
        this._refreshGeometry();
    }

    // ── Keyboard ──

    /** Arrow-key nav for the indicator tablist (APG "Tabs", horizontal).
     *  Scoped to the indicators, not the region — hijacking ←/→ over the
     *  scroller would steal the browser's own scroll keys. */
    _onIndicatorKeydown(e) {
        let target;
        switch (e.key) {
        case 'ArrowLeft':
            target = this._page - 1;
            break;
        case 'ArrowRight':
            target = this._page + 1;
            break;
        case 'Home':
            target = 0;
            break;
        case 'End':
            target = this._totalPages - 1;
            break;
        default:
            return;
        }
        e.preventDefault();
        const clamped = Math.max(0, Math.min(target, this._totalPages - 1));
        if (clamped !== this._page) {
            this.goToPage(clamped);
        }
        this._focusIndicator(clamped);
    }

    /** Focus by index, not by active state — a smooth scroll walks the active
     *  page through the intermediate ones before it settles. */
    _focusIndicator(index) {
        this.updateComplete?.then?.(() => {
            this.shadowRoot?.querySelectorAll('.indicator')?.[index]?.focus();
        });
    }

    // ── Render ──

    /** Replace {key} placeholders in a translatable label template. Matches
     *  the same helper in <ol-pagination>. */
    _interpolateLabel(template, values) {
        return template.replace(/\{(\w+)\}/g, (_, key) => values[key] ?? '');
    }

    _renderIndicators() {
        if (!this.showIndicators || this._totalPages <= 1) return nothing;
        return html`
            <div
                class="indicators"
                role="tablist"
                aria-label=${this.labelPages}
                @keydown=${this._onIndicatorKeydown}
            >
                ${Array.from({ length: this._totalPages }, (_, i) => html`
                    <button
                        class="indicator"
                        role="tab"
                        aria-label=${this._interpolateLabel(this.labelGoToPage, { page: i + 1, total: this._totalPages })}
                        aria-current=${i === this._page ? 'true' : 'false'}
                        aria-selected=${i === this._page ? 'true' : 'false'}
                        tabindex=${i === this._page ? '0' : '-1'}
                        @click=${() => this.goToPage(i)}
                    ></button>
                `)}
            </div>
        `;
    }

    render() {
        const multiPage = this._totalPages > 1;
        const showPrev = multiPage && !this._atStart;
        const showNext = multiPage && !this._atEnd;

        return html`
            <section
                class="carousel"
                role="region"
                aria-roledescription="carousel"
                aria-label=${this.label}
            >
                ${this._renderIndicators()}
                <div class="frame">
                    <div class="edge-fade prev" ?hidden=${!showPrev}></div>
                    <div class="edge-fade next" ?hidden=${!showNext}></div>

                    <button
                        class="arrow prev"
                        aria-label=${this.labelPrevious}
                        ?hidden=${!showPrev}
                        @click=${() => this.prev()}
                    ><span class="arrow-icon">${OlCarousel._leftArrow}</span></button>

                    <div class="viewport" @scroll=${this._onScroll} @scrollend=${this._onScrollEnd}>
                        <slot @slotchange=${this._onSlotChange}></slot>
                    </div>

                    <button
                        class="arrow next"
                        aria-label=${this.labelNext}
                        ?hidden=${!showNext}
                        @click=${() => this.next()}
                    ><span class="arrow-icon">${OlCarousel._rightArrow}</span></button>
                </div>
            </section>
        `;
    }
}

customElements.define('ol-carousel', OlCarousel);
