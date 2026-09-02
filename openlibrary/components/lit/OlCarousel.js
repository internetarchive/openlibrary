import { LitElement, html, css, nothing } from 'lit';
import './OlIcon.js';

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
 * @prop {String} labelPageAnnouncement - Screen-reader announcement template read after each
 *                                        page change, use {page} and {total} as placeholders
 *                                        (default: "Page {page} of {total}")
 * @prop {Boolean} showIndicators - When present, shows the page indicator bar (default: false)
 *
 * @fires ol-carousel-page-change - Fired once the scroller settles on a new page. detail:
 *     { page: Number, previousPage: Number, totalPages: Number } — previousPage lets
 *     consumers (e.g. analytics) infer direction without keeping state
 * @fires ol-carousel-near-end - Fired when the rail settles (or items change) within two pages
 *     of the end, at most once per item count — appending items re-arms it, so a load-more
 *     consumer that stops appending stops hearing it. A rail shorter than three pages fires
 *     on first render, which lets a consumer fill it immediately. detail: { page: Number,
 *     totalPages: Number, itemCount: Number }
 *
 * Items at least half visible in the viewport carry a `data-in-view` attribute
 * (see also `itemsInView()`), so consumers can style or measure what is
 * actually showing without re-deriving geometry.
 *
 * Mouse pointers can grab and throw the rail: scrollLeft follows the pointer
 * directly, a release under 0.1 px/ms (measured over the last 170ms of
 * movement) settles on the nearest page, a faster flick advances exactly one
 * page — never further than the page adjacent to where the grab began,
 * however hard the throw — and any drag past 10px swallows the click so
 * covers never navigate
 * mid-drag. Touch and trackpad input stays fully native. The grab engages
 * only after 4px of travel (or instantly on a moving rail): pointer capture
 * retargets the release click to the viewport, so capturing every press
 * would stop slotted buttons and links from ever receiving mouse clicks.
 *
 * Tabbing into an off-page card aligns its whole page: the browser's minimal
 * scroll-into-view would otherwise strand the rail between pages. Mouse
 * focus (not :focus-visible) never moves the rail.
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
 * load-bearing ones. scroll-behavior (15.4), scroll-snap-stop (15) and
 * overscroll-behavior (16) degrade gracefully. scrollend is Safari 26.2, so
 * it is feature-detected.
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
        labelPageAnnouncement: { type: String, attribute: 'label-page-announcement' },
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
            /* Mouse pointers can grab the rail; links keep their own cursor. */
            cursor: grab;
        }

        /* Mid-drag: we drive scrollLeft per pointer frame, so the browser
           must neither smooth each write nor re-snap between them. */
        .viewport.dragging {
            scroll-snap-type: none;
            scroll-behavior: auto;
            cursor: grabbing;
            user-select: none;
            -webkit-user-select: none;
        }

        /* Grabbing cursor everywhere (the hovered element decides the
           cursor), and no hover lifts while the rail flies underneath. */
        .viewport.dragging ::slotted(*) {
            pointer-events: none;
        }

        /* Release: snap stays off through the settle animation — mandatory
           re-snap would fight the flick target — smooth comes back via the
           class removal so reduced-motion still governs it. */
        .viewport.settling {
            scroll-snap-type: none;
        }

        /* One instant programmatic write (a resize reflow, not a navigation). */
        .viewport.no-smooth {
            scroll-behavior: auto;
        }

        /* Visually hidden live region: screen readers hear page changes land
           while focus stays on the arrow or indicator. */
        .announcer {
            position: absolute;
            width: 1px;
            height: 1px;
            margin: -1px;
            overflow: hidden;
            clip-path: inset(50%);
            white-space: nowrap;
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

        .arrow ol-icon {
            width: 28px;
            height: 28px;
            /* Heavier stroke than the system default, to hold up against cover art. */
            --ol-icon-stroke-width: 2.5;
        }
    `;

    static _leftArrow = html`<ol-icon name="chevron-left"></ol-icon>`;

    static _rightArrow = html`<ol-icon name="chevron-right"></ol-icon>`;

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

    /** A rail is "near its end" within this many pages of the last one.
     *  Matches the legacy carousel's load-more look-ahead of two pages. */
    static _nearEndPageBuffer = 2;

    /** Only the trailing window of movement (ms) counts toward release
     *  velocity, so hold-then-release never flings. (Embla-derived.) */
    static _dragVelocityWindow = 170;

    /** Release speed (px/ms) separating a plain drop from a flick. */
    static _dragFlickVelocity = 0.1;

    /** Cumulative drag (px) beyond which the release click is swallowed. */
    static _dragClickThreshold = 10;

    /** Cumulative travel (px) before a press engages the grab layer. */
    static _dragEngageSlop = 4;

    /** An item counts as in view once this fraction of it shows. */
    static _inViewThreshold = 0.5;

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
        this.labelPageAnnouncement = 'Page {page} of {total}';
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

        // Item count at the last near-end emission; a changed count re-arms it.
        this._nearEndEmittedForCount = 0;

        // Item index whose page a breakpoint change should restore, or null.
        this._resizeAnchorItem = null;

        /** @type {ResizeObserver|null} */
        this._resizeObserver = null;
        this._scrollEndTimer = null;

        /** @type {IntersectionObserver|null} */
        this._itemObserver = null;
        /** @type {Set<Element>} items currently intersecting the viewport */
        this._inView = new Set();

        // Mouse-drag state. Touch and trackpad scrolling stay native.
        this._dragging = false;
        this._dragEngaged = false;
        this._dragStartPage = 0;
        this._suppressClick = false;
        this._dragFromMotion = false;
        this._dragLastX = 0;
        this._dragDistance = 0;
        /** @type {{t: Number, x: Number}[]} recent pointer samples */
        this._dragSamples = [];

        this._onScroll = this._onScroll.bind(this);
        this._onScrollEnd = this._onScrollEnd.bind(this);
        this._onIndicatorKeydown = this._onIndicatorKeydown.bind(this);
        this._onItemIntersect = this._onItemIntersect.bind(this);
        this._onDragPointerDown = this._onDragPointerDown.bind(this);
        this._onDragPointerMove = this._onDragPointerMove.bind(this);
        this._onDragPointerUp = this._onDragPointerUp.bind(this);
        this._onDragPointerLeave = this._onDragPointerLeave.bind(this);
        this._onDragCancel = this._onDragCancel.bind(this);
        this._onDragStartNative = this._onDragStartNative.bind(this);
        this._onViewportClickCapture = this._onViewportClickCapture.bind(this);
        this._onFocusIn = this._onFocusIn.bind(this);

        // On the host, so it hears light-DOM (slotted) focus; shadow focus
        // retargets to the host itself and is filtered out by containment.
        this.addEventListener('focusin', this._onFocusIn);
    }

    connectedCallback() {
        super.connectedCallback();
        this._resizeObserver = new ResizeObserver((entries) => {
            const width = entries[0]?.contentRect.width ?? this.clientWidth;
            const prevColumns = this._columns;
            // First item of the current page — the reader's place. A column
            // change reflows the pages, so stash it for the update pass
            // (which owns the recalculated page count) to restore.
            const anchorItem = this._page * prevColumns;
            this._updateColumns(width);
            if (this._columns !== prevColumns) {
                this._resizeAnchorItem = anchorItem;
            }
            this._applyTrackLayout();
            this._refreshGeometry();
        });
        this._resizeObserver.observe(this);
        // firstUpdated covers the initial connect; this covers re-connects.
        if (this.hasUpdated) {
            this._observeItems();
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._resizeObserver?.disconnect();
        this._resizeObserver = null;
        clearTimeout(this._scrollEndTimer);
        this._itemObserver?.disconnect();
        this._itemObserver = null;
        this._inView.clear();
        this._endDrag();
        this._scroller?.classList.remove('settling');
    }

    firstUpdated() {
        this._countItems();
        this._updateColumns(this.clientWidth);
        this._recalculate();
        this._applyTrackLayout();
        this._refreshGeometry();
        this._observeItems();
        // Capture phase (not a template binding) so a post-drag click dies
        // before it reaches a book link. Lives on our own shadow node, so it
        // needs no teardown — it is collected with the component.
        this._scroller?.addEventListener('click', this._onViewportClickCapture, true);
    }

    updated(changedProperties) {
        if (changedProperties.has('_columns') || changedProperties.has('_itemCount')
            || changedProperties.has('peek') || changedProperties.has('gap')) {
            this._recalculate();
            this._applyTrackLayout();
            this._refreshGeometry();
            if (this._resizeAnchorItem !== null) {
                this._restoreAnchor(this._resizeAnchorItem);
                this._resizeAnchorItem = null;
            }
            this._maybeEmitNearEnd();
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

    /** Indices of the items currently at least half visible in the viewport. */
    itemsInView() {
        return this._items.reduce((indices, item, i) => {
            if (this._inView.has(item)) {
                indices.push(i);
            }
            return indices;
        }, []);
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
     *  gets `end` so a short final page rests flush against the edge.
     *  Boundaries are hard stops (`scroll-snap-stop`): a hard fling advances
     *  one page at a time instead of sailing past several, matching the
     *  arrows and the one-page mouse flick. */
    _applySnapPoints() {
        const items = this._items;
        const cols = this._columns;
        const last = items.length - 1;
        items.forEach((item, i) => {
            if (i === last) {
                item.style.scrollSnapAlign = 'end';
                item.style.scrollSnapStop = 'always';
            } else if (cols > 0 && i % cols === 0) {
                item.style.scrollSnapAlign = 'start';
                item.style.scrollSnapStop = 'always';
            } else {
                item.style.scrollSnapAlign = '';
                item.style.scrollSnapStop = '';
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

    /** Jump — instantly, this is a reflow, not a navigation — to the page
     *  that now contains `itemIndex`, so a breakpoint change keeps the
     *  reader's place instead of stranding the rail wherever scrollLeft
     *  happened to land. */
    _restoreAnchor(itemIndex) {
        const scroller = this._scroller;
        if (!scroller || this._columns <= 0) return;
        const page = Math.max(0, Math.min(Math.floor(itemIndex / this._columns), this._totalPages - 1));
        // Compare positions, not page numbers — the rail can rest between
        // the new offsets while still mapping to the right page.
        if (Math.abs(scroller.scrollLeft - (this._pageOffsets[page] ?? 0)) < 1) return;
        this._page = page;
        scroller.classList.add('no-smooth');
        // Let the style land so the write below is not smoothed.
        void scroller.offsetWidth;
        scroller.scrollLeft = this._pageOffsets[page] ?? 0;
        scroller.classList.remove('no-smooth');
        this._syncFromScroll();
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

    // ── In-view tracking ──

    /** (Re)observe the slotted items. One observer per connected life; a
     *  slot change re-registers the targets on the same instance. */
    _observeItems() {
        const scroller = this._scroller;
        if (!scroller) return;
        if (!this._itemObserver) {
            this._itemObserver = new IntersectionObserver(this._onItemIntersect, {
                root: scroller,
                threshold: OlCarousel._inViewThreshold,
            });
        }
        this._itemObserver.disconnect();
        this._inView.clear();
        this._items.forEach((item) => this._itemObserver.observe(item));
    }

    _onItemIntersect(entries) {
        for (const entry of entries) {
            if (entry.isIntersecting) {
                this._inView.add(entry.target);
                entry.target.setAttribute('data-in-view', '');
            } else {
                this._inView.delete(entry.target);
                entry.target.removeAttribute('data-in-view');
            }
        }
    }

    // ── Scroll tracking ──

    _onScroll() {
        // Keeps indicators, arrows and fades in step mid-scroll.
        this._syncFromScroll();

        // A finger pause mid-drag must not read as a settle.
        if (!OlCarousel._supportsScrollEnd && !this._dragging) {
            clearTimeout(this._scrollEndTimer);
            this._scrollEndTimer = setTimeout(this._onScrollEnd, OlCarousel._scrollEndFallbackDelay);
        }
    }

    /** The only place page-change fires, so a multi-page fling reports once. */
    _onScrollEnd() {
        // Native scrollend fires between pointer pauses during a drag.
        if (this._dragging) return;
        this._scroller?.classList.remove('settling');
        this._syncFromScroll();
        if (this._page !== this._lastEmittedPage) {
            const previousPage = this._lastEmittedPage;
            this._lastEmittedPage = this._page;
            this._emitPageChange(previousPage);
            this._announcePage();
        }
        this._maybeEmitNearEnd();
    }

    _emitPageChange(previousPage) {
        this.dispatchEvent(new CustomEvent('ol-carousel-page-change', {
            detail: { page: this._page, previousPage, totalPages: this._totalPages },
            bubbles: true,
            composed: true,
        }));
    }

    /** Update the polite live region so a screen-reader user hears arrow,
     *  drag and swipe navigation land — focus stays on the control while
     *  the content changes beside it. */
    _announcePage() {
        const announcer = this.shadowRoot?.querySelector('.announcer');
        if (!announcer) return;
        announcer.textContent = this._interpolateLabel(this.labelPageAnnouncement, {
            page: this._page + 1,
            total: this._totalPages,
        });
    }

    /** Ask for more items when the rail runs low. Emission is keyed to the
     *  item count, so each append re-arms it and a consumer with nothing
     *  left to add is not asked again. */
    _maybeEmitNearEnd() {
        if (this._itemCount <= 0) return;
        if (this._page < this._totalPages - OlCarousel._nearEndPageBuffer) return;
        if (this._itemCount === this._nearEndEmittedForCount) return;
        this._nearEndEmittedForCount = this._itemCount;
        this.dispatchEvent(new CustomEvent('ol-carousel-near-end', {
            detail: { page: this._page, totalPages: this._totalPages, itemCount: this._itemCount },
            bubbles: true,
            composed: true,
        }));
    }

    // ── Mouse drag ──
    // Native scroll owns touch and trackpad; this layer adds grab-and-throw
    // for mouse pointers by driving scrollLeft from pointer deltas.

    _onDragPointerDown(e) {
        if (e.pointerType !== 'mouse' || e.button !== 0) return;
        if (this._totalPages <= 1) return;
        const scroller = this._scroller;
        if (!scroller) return;

        this._dragging = true;
        this._dragEngaged = false;
        this._dragStartPage = this._pageFromScroll();
        this._dragLastX = e.clientX;
        this._dragDistance = 0;
        this._dragSamples = [{ t: performance.now(), x: e.clientX }];
        // Off a resting offset means the rail was still moving: this grab is
        // a stop, and stopping is not clicking, however little it moves.
        this._dragFromMotion =
            Math.abs(scroller.scrollLeft - (this._pageOffsets[this._pageFromScroll()] ?? 0)) > 1;
        clearTimeout(this._scrollEndTimer);

        scroller.addEventListener('pointermove', this._onDragPointerMove);
        scroller.addEventListener('pointerup', this._onDragPointerUp);
        scroller.addEventListener('pointerleave', this._onDragPointerLeave);
        scroller.addEventListener('pointercancel', this._onDragCancel);
        scroller.addEventListener('lostpointercapture', this._onDragCancel);

        // A grab of a moving rail is a stop, never a click — engage at once.
        // A press at rest stays unengaged until real travel (_dragEngageSlop).
        if (this._dragFromMotion) {
            this._engageDrag(e);
        }
    }

    /** Flip a pending press into an actual grab. Deferred past pointerdown
     *  because pointer capture retargets the release — and with it the click —
     *  to this scroller, so capturing every press would stop slotted buttons
     *  and links from ever receiving mouse clicks. */
    _engageDrag(e) {
        if (this._dragEngaged) return;
        this._dragEngaged = true;
        const scroller = this._scroller;
        if (!scroller) return;

        scroller.classList.add('dragging');
        scroller.classList.remove('settling');
        // Grab-to-stop: a self-assignment aborts any in-flight smooth scroll.
        scroller.scrollLeft += 0;

        // Capture retargets move/up here even when the pointer leaves the
        // window, so no document-level listeners are needed.
        try {
            if (typeof scroller.setPointerCapture === 'function') {
                scroller.setPointerCapture(e.pointerId);
            }
        } catch { /* stale pointer id or jsdom — capture is best-effort */ }
    }

    _onDragPointerMove(e) {
        // The button went up without a pointerup reaching us (e.g. an alert).
        if ((e.buttons & 1) === 0) {
            this._onDragPointerUp(e);
            return;
        }
        const dx = this._dragLastX - e.clientX;
        this._dragLastX = e.clientX;
        this._dragDistance += Math.abs(dx);

        const now = performance.now();
        this._dragSamples.push({ t: now, x: e.clientX });
        const cutoff = now - OlCarousel._dragVelocityWindow;
        while (this._dragSamples.length > 1 && this._dragSamples[0].t < cutoff) {
            this._dragSamples.shift();
        }

        // Inside the slop this is still a click in progress: leave the rail
        // alone so the press neither scrolls nor loses its click target.
        if (!this._dragEngaged) {
            if (this._dragDistance <= OlCarousel._dragEngageSlop) return;
            this._engageDrag(e);
        }
        e.preventDefault();

        const scroller = this._scroller;
        if (scroller) {
            // The browser clamps at the edges; incremental deltas mean a
            // reversal responds immediately even after overshooting.
            scroller.scrollLeft += dx;
        }
    }

    _onDragPointerUp() {
        const samples = this._dragSamples;
        let velocity = 0;
        if (samples.length > 1) {
            const first = samples[0];
            const last = samples[samples.length - 1];
            const dt = last.t - first.t;
            // Positive scrolls forward: the content follows the pointer.
            if (dt > 0) {
                velocity = (first.x - last.x) / dt;
            }
        }
        this._settleFromDrag(velocity);
    }

    _onDragCancel() {
        this._settleFromDrag(0);
    }

    /** Unengaged presses hold no capture, so a release outside the viewport
     *  would never reach the scroller's pointerup — treat leaving as one.
     *  While engaged, capture suppresses boundary events until release. */
    _onDragPointerLeave(e) {
        if (!this._dragEngaged) {
            this._onDragPointerUp(e);
        }
    }

    /** Shared release path: end the drag, pick a page, animate to it. */
    _settleFromDrag(velocity) {
        if (!this._dragging) return;
        this._suppressClick = this._dragDistance > OlCarousel._dragClickThreshold || this._dragFromMotion;
        this._endDrag();

        const nearest = this._pageFromScroll();
        let target = nearest;
        if (Math.abs(velocity) >= OlCarousel._dragFlickVelocity) {
            // One page per flick. Offsets ascend LTR and descend RTL, so the
            // flick sign maps through their ordering.
            const ascending = (this._pageOffsets[this._totalPages - 1] ?? 0) >= (this._pageOffsets[0] ?? 0);
            target = nearest + (ascending ? 1 : -1) * Math.sign(velocity);
        }
        // One page per gesture (Embla's skip-less snap model): a hard throw
        // travels far before release, so nearest-plus-flick alone would skip
        // pages — the release always lands adjacent to where the grab began.
        target = Math.max(this._dragStartPage - 1, Math.min(target, this._dragStartPage + 1));
        const clamped = Math.max(0, Math.min(target, this._totalPages - 1));

        const scroller = this._scroller;
        if (scroller && Math.abs(scroller.scrollLeft - (this._pageOffsets[clamped] ?? 0)) < 1) {
            // Already resting on the target: no scroll will fire, settle now.
            scroller.classList.remove('settling');
            this.goToPage(clamped);
            this._onScrollEnd();
            return;
        }
        this.goToPage(clamped);
    }

    /** Tear down drag listeners and state. The viewport moves to its
     *  settling phase: snap stays off until the release animation lands. */
    _endDrag() {
        this._dragging = false;
        this._dragEngaged = false;
        this._dragSamples = [];
        const scroller = this._scroller;
        if (!scroller) return;
        scroller.removeEventListener('pointermove', this._onDragPointerMove);
        scroller.removeEventListener('pointerup', this._onDragPointerUp);
        scroller.removeEventListener('pointerleave', this._onDragPointerLeave);
        scroller.removeEventListener('pointercancel', this._onDragCancel);
        scroller.removeEventListener('lostpointercapture', this._onDragCancel);
        if (scroller.classList.contains('dragging')) {
            scroller.classList.remove('dragging');
            scroller.classList.add('settling');
        }
    }

    /** Firefox starts a native link/image drag where WebKit's
     *  -webkit-user-drag does not apply. */
    _onDragStartNative(e) {
        if (this._dragging) {
            e.preventDefault();
        }
    }

    /** Swallow the click that follows a real drag, so dragging over a book
     *  cover never navigates. One-shot, capture phase. */
    _onViewportClickCapture(e) {
        if (!this._suppressClick) return;
        this._suppressClick = false;
        e.preventDefault();
        e.stopPropagation();
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
        this._observeItems();
    }

    // ── Keyboard ──

    /** Keyboard focus landing on an off-page card pulls that card's whole
     *  page into place. The browser's own scroll-into-view reveals the card
     *  but can strand the rail between pages; this aligns it. Mouse focus
     *  (not :focus-visible) never yanks the rail. */
    _onFocusIn(e) {
        const target = e.target;
        if (!(target instanceof Element)) return;
        let keyboard = true;
        try {
            keyboard = target.matches(':focus-visible');
        } catch { /* selector unsupported: treat the focus as keyboard */ }
        if (!keyboard) return;

        const index = this._items.findIndex((item) => item.contains(target));
        if (index === -1 || this._columns <= 0) return;
        const page = Math.min(Math.floor(index / this._columns), this._totalPages - 1);
        if (page !== this._page) {
            this.goToPage(page);
        }
    }

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

                    <div
                        class="viewport"
                        @scroll=${this._onScroll}
                        @scrollend=${this._onScrollEnd}
                        @pointerdown=${this._onDragPointerDown}
                        @dragstart=${this._onDragStartNative}
                    >
                        <slot @slotchange=${this._onSlotChange}></slot>
                    </div>

                    <button
                        class="arrow next"
                        aria-label=${this.labelNext}
                        ?hidden=${!showNext}
                        @click=${() => this.next()}
                    ><span class="arrow-icon">${OlCarousel._rightArrow}</span></button>
                </div>
                <div class="announcer" aria-live="polite" aria-atomic="true"></div>
            </section>
        `;
    }
}

customElements.define('ol-carousel', OlCarousel);
