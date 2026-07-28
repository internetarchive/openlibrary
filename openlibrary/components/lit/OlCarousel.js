import { LitElement, html, css, nothing } from 'lit';

/**
 * A Netflix-style carousel component with page-based navigation.
 *
 * Items are passed as direct children. The component controls their width
 * based on responsive breakpoints, shows peek areas at the edges, and
 * provides arrow buttons and bar-segment indicators for navigation.
 *
 * The viewport is a NATIVE scroll container. Swipe, fling, momentum,
 * overscroll, axis locking, trackpad and wheel scrolling are all the
 * platform's own — the component only decides where the snap points are and
 * reports which page the scroller has settled on. See "Browser support" below
 * for the handful of places that still need a JS fallback.
 *
 * Off-page items are deliberately NOT `inert`. A transform-based track had to
 * hide them, because nothing but the component could scroll them into view. In
 * a real scroll container they are legitimately reachable: tabbing to one
 * scrolls it into view, and screen readers, find-in-page and voice control can
 * all reach the whole rail.
 *
 * @element ol-carousel
 *
 * @prop {Number} peek - Fraction of item width visible at edges (0–0.5, default: 0.03)
 * @prop {Number} gap - Gap between items in px (default: 8)
 * @prop {String} label - Accessible label for the carousel region (default: "Carousel")
 * @prop {String} labelPrevious - Aria-label for previous arrow (default: "Previous page")
 * @prop {String} labelNext - Aria-label for next arrow (default: "Next page")
 * @prop {Boolean} showIndicators - When present, shows the page indicator bar (default: false)
 *
 * @fires ol-carousel-page-change - Fired once the scroller settles on a new page. detail: { page: Number, totalPages: Number }
 *
 * @slot - Carousel items. Each direct child becomes one card; the component controls its width.
 *
 * @cssprop [--ol-carousel-arrow-color=#333] - Colour of the arrow glyphs
 * @cssprop [--ol-carousel-arrow-icon-bg=#fff] - Background of the round arrow buttons
 * @cssprop [--ol-carousel-arrow-icon-border=hsl(55, 20%, 83%)] - Border of the round arrow buttons
 * @cssprop [--ol-carousel-arrow-icon-size=36px] - Diameter of the round arrow buttons
 * @cssprop [--ol-carousel-indicator-color=#ccc] - Colour of the inactive page indicators
 * @cssprop [--ol-carousel-indicator-active=#333] - Colour of the active page indicator
 * @cssprop [--ol-carousel-viewport-padding=0px] - Inner viewport padding so slotted items can show a hover lift/shadow without being clipped
 *
 * Browser support (checked against the project browserslist):
 *  - scroll-snap-type / scroll-snap-align — Safari 11, Chrome 69, Firefox 68. Core, universally available.
 *  - scroll-padding — Safari 14.5. Older Safari loses the edge peek only.
 *  - scroll-behavior: smooth — Safari 15.4. Older Safari jumps instantly instead of gliding.
 *  - overscroll-behavior-x — Safari 16. Older Safari may still fire the macOS history swipe.
 *  - scrollbar-width: none — Safari 18.2 / Chrome 121, with a ::-webkit-scrollbar fallback for the rest.
 *  - scrollend — Safari 26.2 only, so it is feature-detected with a debounced `scroll` fallback (see _onScroll).
 *  - IntersectionObserver (Safari 12.1) and ResizeObserver (Safari 13.1) — both well below the floor.
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
            --_arrow-color: var(--ol-carousel-arrow-color, #333);
            --_arrow-icon-bg: var(--ol-carousel-arrow-icon-bg, #fff);
            --_arrow-icon-border: var(--ol-carousel-arrow-icon-border, hsl(55, 20%, 83%));
            --_arrow-icon-size: var(--ol-carousel-arrow-icon-size, 36px);
            --_indicator-color: var(--ol-carousel-indicator-color, #ccc);
            --_indicator-active: var(--ol-carousel-indicator-active, #333);
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
           Positioning context for the arrows and edge fades. They must sit
           OUTSIDE the scroller — anything absolutely positioned inside a scroll
           container scrolls away with the content. */
        .frame {
            position: relative;
        }

        /* ── Viewport (the scroll container) ── */
        .viewport {
            display: flex;
            gap: var(--_gap, 4px);
            overflow-x: auto;
            /* overflow-y cannot stay visible next to a scrolling axis, so the
               hover lift is given room by padding-block instead of overflow. */
            overflow-y: hidden;
            padding-block: var(--_viewport-padding);
            scroll-snap-type: x mandatory;
            /* Inline-start padding is the edge peek; the end stays flush so the
               last page aligns its final item with the viewport's edge. */
            scroll-padding-inline: calc(var(--_peek, 0.03) * 100%) 0;
            scroll-behavior: smooth;
            /* Stops a horizontal trackpad swipe from triggering the macOS
               browser back/forward gesture once the rail hits its end. */
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
            z-index: 1;
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
            z-index: 2;
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

    /** True when the browser fires `scrollend` (Safari only got it in 26.2).
     *  Without it we debounce `scroll` instead — see _onScroll. */
    static _supportsScrollEnd = typeof window !== 'undefined' && 'onscrollend' in window;

    /** Idle gap (ms) after the last `scroll` event that stands in for
     *  `scrollend` where it is unavailable. Long enough to outlast a fling's
     *  momentum tail, short enough that the page-change event still feels
     *  immediate. Unused when _supportsScrollEnd is true. */
    static _scrollEndFallbackDelay = 120;

    /** How far ahead of the scrollport covers start loading, as a multiple of
     *  the viewport width. One full viewport each side means the next page is
     *  already warm by the time the patron reaches it. */
    static _lazyRootMargin = '0px 100%';

    constructor() {
        super();
        this.peek = 0.03;
        this.gap = 8;
        this.label = 'Carousel';
        this.labelPrevious = 'Previous page';
        this.labelNext = 'Next page';
        this.showIndicators = false;
        this._page = 0;
        this._totalPages = 1;
        this._columns = 6;
        this._itemCount = 0;
        this._atStart = true;
        this._atEnd = false;

        // scrollLeft of each page's resting position, measured from the DOM
        // (see _measurePageOffsets). Index === page number.
        this._pageOffsets = [0];
        this._maxScroll = 0;

        // Last page reported via ol-carousel-page-change, so a settle that
        // lands back where it started stays quiet.
        this._lastEmittedPage = 0;

        /** @type {ResizeObserver|null} */
        this._resizeObserver = null;
        /** @type {IntersectionObserver|null} */
        this._lazyObserver = null;
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
        this._lazyObserver?.disconnect();
        this._lazyObserver = null;
        clearTimeout(this._scrollEndTimer);
    }

    firstUpdated() {
        this._countItems();
        this._updateColumns(this.clientWidth);
        this._recalculate();
        this._applyTrackLayout();
        this._refreshGeometry();
        this._setupLazyLoading();
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
        // Move the indicators/arrows now rather than waiting for the first
        // scroll event. _syncFromScroll reconciles from the real position as
        // the scroll runs, so an optimistic value can never drift.
        this._page = clamped;
        // No `behavior` option on purpose: leaving it at the default defers to
        // the scroller's CSS `scroll-behavior`, which the reduced-motion media
        // query already switches to `auto`. One rule covers both paths.
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

    /** Re-derive everything that depends on layout: where the snap points are,
     *  where each page rests, and which page we are currently on. Called after
     *  a resize, a slot change, or a property change. */
    _refreshGeometry() {
        this._applySnapPoints();
        this._measurePageOffsets();
        this._syncFromScroll();
    }

    /** Mark which items are page boundaries. The browser then owns everything
     *  about landing on them — this replaces the old hand-rolled offset table,
     *  release-velocity projection and nearest-page search.
     *
     *  The last item gets `end` so a short final page rests flush against the
     *  viewport's edge rather than leaving a gap after it. */
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

    /** Measure each page's resting scrollLeft straight from the DOM.
     *
     *  These only need to be close enough to pick the right snap point —
     *  mandatory snapping corrects any rounding error after the scroll lands,
     *  so the arithmetic here does not have to be pixel-exact the way the old
     *  transform offsets did. */
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
        // Cached so _syncFromScroll — which runs on every scroll event — never
        // has to touch scrollWidth and force a layout mid-scroll.
        this._maxScroll = maxScroll;

        for (let page = 0; page < this._totalPages; page++) {
            // The final page rests at the end of the scroll range, matching the
            // `scroll-snap-align: end` on the last item.
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

    /** Pull page index and edge state off the live scroll position.
     *  Reads only scrollLeft, so it is safe to run on every scroll event. */
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
        // Cheap, passive: keep the indicators, arrows and fades in step while
        // the scroll is still moving.
        this._syncFromScroll();

        if (!OlCarousel._supportsScrollEnd) {
            clearTimeout(this._scrollEndTimer);
            this._scrollEndTimer = setTimeout(this._onScrollEnd, OlCarousel._scrollEndFallbackDelay);
        }
    }

    /** The scroller has settled. This is the only place the public
     *  page-change event fires, so consumers never see intermediate pages
     *  during a multi-page fling. */
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

    // ── Lazy covers ──

    /** Swap `data-lazy` → `src` as items approach the scrollport.
     *
     *  A transform-based track had to compute this from the page index,
     *  because every item counted as on-screen as far as the browser was
     *  concerned. A real scroll container makes intersection meaningful, so
     *  the observer handles it — including the lookahead, which is just
     *  rootMargin.
     *
     *  Consumers rendering plain `loading="lazy"` covers need none of this;
     *  native lazy-loading works correctly inside a scroll container. */
    _setupLazyLoading() {
        const scroller = this._scroller;
        if (!scroller || typeof IntersectionObserver === 'undefined') return;

        this._lazyObserver = new IntersectionObserver((entries) => {
            for (const entry of entries) {
                if (!entry.isIntersecting) continue;
                entry.target.querySelectorAll?.('img[data-lazy]').forEach((img) => {
                    img.src = img.dataset.lazy;
                    img.removeAttribute('data-lazy');
                });
                this._lazyObserver?.unobserve(entry.target);
            }
        }, { root: scroller, rootMargin: OlCarousel._lazyRootMargin });

        this._observeLazyTargets();
    }

    _observeLazyTargets() {
        if (!this._lazyObserver) return;
        for (const item of this._items) {
            if (item.querySelector?.('img[data-lazy]')) {
                this._lazyObserver.observe(item);
            }
        }
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
        this._observeLazyTargets();
    }

    // ── Keyboard ──

    /** Arrow-key navigation for the indicator tablist (APG "Tabs" pattern,
     *  horizontal orientation). The indicators carry a roving tabindex so the
     *  tablist is a single Tab stop; ←/→ and Home/End move between pages and
     *  carry focus to the newly-active indicator.
     *
     *  Scoped to the indicators rather than the whole region: the slotted items
     *  are a native scroll container now, and hijacking ←/→ there would steal
     *  the browser's own scroll keys. */
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

    /** Move focus to a given indicator after the roving tabindex updates.
     *  Targets the index rather than whichever indicator is currently active,
     *  because a smooth scroll walks the active page through the intermediate
     *  ones before it settles. */
    _focusIndicator(index) {
        this.updateComplete?.then?.(() => {
            this.shadowRoot?.querySelectorAll('.indicator')?.[index]?.focus();
        });
    }

    // ── Render ──

    _renderIndicators() {
        if (!this.showIndicators || this._totalPages <= 1) return nothing;
        return html`
            <div
                class="indicators"
                role="tablist"
                aria-label="Carousel pages"
                @keydown=${this._onIndicatorKeydown}
            >
                ${Array.from({ length: this._totalPages }, (_, i) => html`
                    <button
                        class="indicator"
                        role="tab"
                        aria-label="Go to page ${i + 1} of ${this._totalPages}"
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
