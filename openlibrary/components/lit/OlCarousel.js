import { LitElement, html, css, nothing } from 'lit';

/**
 * A Netflix-style carousel component with page-based navigation.
 *
 * Items are passed as direct children. The component controls their width
 * based on responsive breakpoints, shows peek areas at the edges, and
 * provides arrow buttons and bar-segment indicators for navigation.
 *
 * All motion (button clicks, swipe release) uses spring physics via
 * requestAnimationFrame for natural momentum and deceleration.
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
 * @fires ol-carousel-page-change - Fired after page transition. detail: { page: Number, totalPages: Number }
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

        /* ── Viewport ── */
        /* The swipe gesture (pointerdown, touch-action, user-select) lives on
           the viewport, which never moves, rather than the track, which slides
           sideways when you page. A touch can land anywhere in the viewport and
           still start a swipe; on the track it could miss (gaps, padding, items
           slid off-page) or hit an iOS Safari bug with transformed elements. */
        .viewport {
            position: relative;
            overflow: hidden;
            padding-block: var(--_viewport-padding);
            touch-action: pan-y pinch-zoom;
            user-select: none;
            -webkit-user-select: none;
        }

        /* ── Track ── */
        .track {
            display: flex;
            gap: var(--_gap, 4px);
            will-change: transform;
        }

        /* ── Slotted items ── */
        ::slotted(*) {
            flex: 0 0 var(--_item-width);
            min-width: 0;
            box-sizing: border-box;
            margin: 0;
            -webkit-user-drag: none;
        }

        /* During drag, make children transparent to pointer events so the
           browser's click (fired on pointerup) lands on the track, not on
           any <a> inside the slotted children. */
        :host(.dragging) ::slotted(*) {
            pointer-events: none !important;
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

    /** Spring physics constants */
    static _spring = {
        stiffness: 0.09, // Pull strength toward target; lower = gentler, higher = snappier
        damping: 0.5, // Velocity retained per frame; lower = more friction/less bounce, higher = more oscillation
        precision: 0.02, // Threshold to snap to final position; lower = smoother finish, higher = earlier cutoff
    };

    /** How far a finger travels (px) before we decide whether it's a swipe
     *  or a page scroll. Lower = the carousel commits to swipes faster, but
     *  taps that wobble slightly can be mistaken for swipes. Higher = the
     *  carousel feels less responsive to start a swipe. */
    static _axisLockThreshold = 8;

    /** How forgiving we are about diagonal swipes. Higher = angled swipes
     *  still move the carousel instead of scrolling the page (2 catches
     *  swipes up to ~63° off horizontal, which suits real thumb drags that
     *  drift vertically). Lower = swipes must be more strictly horizontal. */
    static _horizontalBias = 2;

    /** Smallest time gap (ms) we'll use to gauge swipe speed. Raise it if
     *  release momentum feels jumpy or unpredictable (very rapid-fire touch
     *  events can otherwise register a wild, meaningless speed). Lower risks
     *  those spikes; there's rarely a reason to go below this. */
    static _velocitySampleWindow = 4;

    /** Ceiling on how fast a swipe-release can fling the carousel (px/ms).
     *  Lower = flings feel tamer and travel fewer pages. Higher = a hard
     *  flick throws further, but a single glitchy reading can launch it
     *  faster than any real finger could. */
    static _maxVelocity = 4;

    /** Apply rubber-band resistance when position exceeds bounds.
     *  Uses an iOS-style formula: overscroll is dampened asymptotically
     *  so the track resists increasingly as you drag further out.
     *  Maximum visual overscroll is capped at one viewport width. */
    static _rubberBand(pos, min, max, dimension) {
        const c = 0.5;        // Rubber-band constant (lower = stiffer resistance)
        const maxOver = 0.5; // Max overscroll as fraction of viewport width
        if (pos > max) {
            const overPx = ((pos - max) / 100) * dimension;
            const dampedPx = dimension * maxOver * (1 - 1 / (overPx * c / dimension + 1));
            return max + (dampedPx / dimension) * 100;
        }
        if (pos < min) {
            const overPx = ((min - pos) / 100) * dimension;
            const dampedPx = dimension * maxOver * (1 - 1 / (overPx * c / dimension + 1));
            return min - (dampedPx / dimension) * 100;
        }
        return pos;
    }

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

        // Cover-prefetch depth, in pages beyond the visible page. Starts at one
        // page (the structural lookahead) and deepens to two on the first sign
        // of engagement (hover / keyboard focus) — see _onIntent.
        this._lookaheadPages = 1;

        // Current track position in % (source of truth for rendering)
        this._currentPos = 0;

        /** @type {ResizeObserver|null} */
        this._resizeObserver = null;

        // Pointer / drag state (non-reactive for zero-overhead drag)
        this._dragging = false;
        this._pointerStartX = 0;
        this._pointerStartY = 0;
        this._pointerId = null;
        this._dragDelta = 0;
        this._velocity = 0;
        this._pointerPrevX = 0;
        this._pointerPrevTime = 0;

        // Gesture axis lock: null until the pointer travels past
        // _axisLockThreshold, then 'x' (carousel drag) or 'y' (page scroll —
        // the drag is abandoned). Mouse pointers lock to 'x' immediately
        // since they never conflict with page scrolling.
        this._axisLock = null;

        // Drag-click prevention: set true when a drag exceeds the movement
        // threshold. Checked by the capture-phase click handler to suppress
        // accidental link activation.
        this._draggedPastThreshold = false;

        // Spring animation state
        this._animationFrame = null;
        this._springVel = 0;

        this._onPointerDown = this._onPointerDown.bind(this);
        this._onPointerMove = this._onPointerMove.bind(this);
        this._onPointerUp = this._onPointerUp.bind(this);
        this._onPointerCancel = this._onPointerCancel.bind(this);
        this._onTouchMove = this._onTouchMove.bind(this);
        this._onClickCapture = this._onClickCapture.bind(this);
        this._onIntent = this._onIntent.bind(this);
        this._onIndicatorKeydown = this._onIndicatorKeydown.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();

        // ── Drag-click prevention ──
        // Intercept clicks in the CAPTURE phase on the host element.
        // Composed click events from slotted light-DOM children (e.g. <a>
        // tags) bubble up through the shadow boundary. By listening in
        // capture on the host, we fire before the click reaches any <a>.
        this.addEventListener('click', this._onClickCapture, true);

        // ── Engagement-driven cover prefetch ──
        // Hovering anywhere on the carousel (or tabbing into it) is the
        // earliest, cheapest signal that the patron intends to browse. On the
        // first such signal we deepen the cover lookahead by one page so fast
        // page-flipping never catches up to the edge of the warmed range.
        // { once: true } — the deepening is one-way, so we self-remove.
        this.addEventListener('pointerenter', this._onIntent, { once: true });
        this.addEventListener('focusin', this._onIntent, { once: true });

        this._resizeObserver = new ResizeObserver((entries) => {
            const width = entries[0]?.contentRect.width ?? this.clientWidth;
            this._updateColumns(width);
            this._applyTrackLayout();
            // Recompute offset on resize (gap px correction depends on width)
            if (!this._dragging && !this._animationFrame) {
                this._currentPos = this._getOffsetForPage(this._page);
                this._applyTransform(this._currentPos);
            }
        });
        this._resizeObserver.observe(this);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this.removeEventListener('click', this._onClickCapture, true);
        // No-ops if they already fired (once: true), but needed when the
        // element is removed before any engagement.
        this.removeEventListener('pointerenter', this._onIntent);
        this.removeEventListener('focusin', this._onIntent);
        this._removeDragListeners();
        this._resizeObserver?.disconnect();
        this._resizeObserver = null;
        this._cancelAnimation();
    }

    firstUpdated() {
        this._countItems();
        this._recalculate();
        this._applyTrackLayout();
        this._currentPos = this._getOffsetForPage(this._page);
        this._applyTransform(this._currentPos);
        this._updateInert();
    }

    updated(changedProperties) {
        if (changedProperties.has('_columns') || changedProperties.has('_itemCount')
            || changedProperties.has('peek') || changedProperties.has('gap')) {
            this._recalculate();
            this._applyTrackLayout();
            this._currentPos = this._getOffsetForPage(this._page);
            this._applyTransform(this._currentPos);
            this._updateInert();
        }
    }

    // ── Public methods ──

    /** Current page (0-indexed). Meaningful after `firstUpdated`/`updateComplete`. */
    get page() { return this._page; }

    /** Total number of pages. Depends on measured width, so read after `updateComplete`. */
    get totalPages() { return this._totalPages; }

    /** Advance to the next page. */
    next() {
        if (this._page < this._totalPages - 1) {
            this._navigateToPage(this._page + 1);
        }
    }

    /** Go to the previous page. */
    prev() {
        if (this._page > 0) {
            this._navigateToPage(this._page - 1);
        }
    }

    /** Jump to a specific page (0-indexed). */
    goToPage(index) {
        const clamped = Math.max(0, Math.min(index, this._totalPages - 1));
        if (clamped !== this._page) {
            this._navigateToPage(clamped);
        }
    }

    // ── Navigation ──

    _navigateToPage(targetPage, initialVelocity = 0) {
        const targetPos = this._getOffsetForPage(targetPage);
        this._page = targetPage;
        this._updateInert();
        this._animateSpring(this._currentPos, initialVelocity, targetPos, () => {
            this._emitPageChange();
        });
    }

    // ── Spring animation ──

    _animateSpring(fromPos, initialVelocity, targetPos, onComplete) {
        this._cancelAnimation();

        const { stiffness, damping, precision } = OlCarousel._spring;
        const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        // Snap immediately for reduced-motion preference
        if (reducedMotion) {
            this._currentPos = targetPos;
            this._applyTransform(targetPos);
            if (onComplete) onComplete();
            return;
        }

        let pos = fromPos;
        // Convert velocity from %/ms to %/frame (~16ms)
        let vel = initialVelocity * 16;

        const step = () => {
            const displacement = targetPos - pos;
            vel += displacement * stiffness;
            vel *= damping;
            pos += vel;

            this._currentPos = pos;
            this._applyTransform(pos);

            if (Math.abs(vel) < precision && Math.abs(displacement) < precision) {
                this._currentPos = targetPos;
                this._applyTransform(targetPos);
                this._animationFrame = null;
                if (onComplete) onComplete();
                return;
            }

            this._animationFrame = requestAnimationFrame(step);
        };

        this._animationFrame = requestAnimationFrame(step);
    }

    _cancelAnimation() {
        if (this._animationFrame) {
            cancelAnimationFrame(this._animationFrame);
            this._animationFrame = null;
        }
    }

    _applyTransform(pos) {
        const track = this.shadowRoot?.querySelector('.track');
        if (track) {
            track.style.transform = `translateX(${pos}%)`;
        }
    }

    // ── Internals ──

    _countItems() {
        const slot = this.shadowRoot?.querySelector('slot');
        if (slot) {
            this._itemCount = slot.assignedElements().length;
        }
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

    /** Calculate the translateX offset (%) for a given page.
     *  Uses pixel math to account for gap, then converts to % of track width
     *  (track is a block-level flex container, so its width = viewport width). */
    _getOffsetForPage(page) {
        const count = this._itemCount;
        const cols = this._columns;
        const peek = this.peek;
        const gap = this.gap;
        const width = this.clientWidth || 1;

        if (count <= 0 || cols <= 0 || page <= 0) return 0;

        const itemFraction = (1 - peek * 2) / cols;
        const itemWidthPx = itemFraction * width - gap + gap / cols;
        const stepPx = itemWidthPx + gap; // item width + trailing gap

        if (page >= this._totalPages - 1) {
            // Align last item's right edge with the viewport's right edge
            const totalPx = count * itemWidthPx + (count - 1) * gap;
            return -((totalPx - width) / width) * 100;
        }

        // Position first item of this page at the peek offset
        const itemPosPx = page * cols * stepPx;
        const peekPx = peek * width;
        return -((itemPosPx - peekPx) / width) * 100;
    }

    _updateInert() {
        const slot = this.shadowRoot?.querySelector('slot');
        if (!slot) return;
        const items = slot.assignedElements();
        const cols = this._columns;
        const page = this._page;

        let startVisible, endVisible;
        if (page === 0) {
            startVisible = 0;
            endVisible = cols - 1;
        } else if (page >= this._totalPages - 1) {
            endVisible = items.length - 1;
            startVisible = Math.max(0, items.length - cols);
        } else {
            startVisible = page * cols;
            endVisible = startVisible + cols - 1;
        }

        items.forEach((item, i) => {
            if (i >= startVisible && i <= endVisible) {
                item.removeAttribute('inert');
                item.setAttribute('aria-hidden', 'false');
            } else {
                item.setAttribute('inert', '');
                item.setAttribute('aria-hidden', 'true');
            }
        });

        this._loadVisibleImages(items, endVisible);
    }

    /** Swap cover `data-lazy` → `src` for the visible range plus a one-page
     *  lookahead. Cards past the first page render with a placeholder src and
     *  the real URL in `data-lazy` (see books/custom_carousel_card.html). The
     *  legacy Slick carousel got this for free via `lazyLoad: 'ondemand'`;
     *  <ol-carousel> uses a transform-based track (not native scroll), so it
     *  must do the swap itself or paged-in covers never load. */
    _loadVisibleImages(items, endVisible) {
        const loadThrough = Math.min(
            items.length - 1,
            endVisible + this._columns * this._lookaheadPages
        );
        for (let i = 0; i <= loadThrough; i++) {
            const imgs = items[i].querySelectorAll?.('img[data-lazy]');
            if (!imgs) continue;
            imgs.forEach((img) => {
                img.src = img.dataset.lazy;
                img.removeAttribute('data-lazy');
            });
        }
    }

    /** First-engagement handler: deepen the cover lookahead by one page and
     *  re-run the swap so the extra page is warmed immediately. Skipped on
     *  data-saver / very slow connections, where eagerly pulling covers the
     *  patron may never reach is the wrong trade. Fires at most once. */
    _onIntent() {
        const conn = navigator.connection;
        if (conn && (conn.saveData || /(^|-)2g$/.test(conn.effectiveType || ''))) {
            return;
        }
        if (this._lookaheadPages >= 2) return;
        this._lookaheadPages = 2;
        this._updateInert();
    }

    _emitPageChange() {
        this.dispatchEvent(new CustomEvent('ol-carousel-page-change', {
            detail: { page: this._page, totalPages: this._totalPages },
            bubbles: true,
            composed: true,
        }));
    }

    // ── Slot change ──

    _onSlotChange() {
        this._countItems();
    }

    // ── Drag-click prevention ──
    //
    // WHY the CSS-only approach (`:host(.dragging) ::slotted(*) { pointer-events: none }`)
    // is insufficient:
    //
    // `pointer-events: none` only affects hit-testing for NEW events. When the
    // user presses down on an <a>, the browser records that element as the
    // mousedown target. Changing pointer-events to `none` mid-drag does NOT
    // retroactively change the click target — the browser still fires `click`
    // on the original <a> when the pointer is released.
    //
    // Additionally, with shadow DOM `setPointerCapture` on the track element,
    // mousedown lands on the <a> (light DOM) while pointerup/mouseup go to the
    // track (shadow DOM). Click target resolution across this boundary is
    // browser-dependent and unreliable.
    //
    // SOLUTION: Capture-phase click listener on the host element.
    // Composed click events from slotted children bubble through the shadow
    // boundary, so a capture-phase listener on the host fires BEFORE the click
    // reaches any <a>. If a drag occurred, we suppress it.

    _onClickCapture(e) {
        if (this._draggedPastThreshold) {
            e.preventDefault();
            e.stopPropagation();
            this._draggedPastThreshold = false;
            return;
        }
    }

    // ── Pointer / swipe ──
    //
    // We intentionally do NOT use setPointerCapture(). Pointer capture on a
    // shadow-DOM element (the track) causes the browser to retarget the
    // synthesized click event to the host element instead of the original
    // light-DOM target (e.g. an <a> tag inside a slotted child). This breaks
    // normal click navigation entirely.
    //
    // Instead we use window-level pointermove/pointerup listeners, which:
    //  - Track drag movement even when the pointer leaves the carousel
    //  - Preserve native click target resolution so <a> tags work normally
    //  - Work for both mouse and touch (touch has implicit capture anyway)
    //
    // TOUCH GESTURE OWNERSHIP: the viewport's `touch-action: pan-y pinch-zoom`
    // leaves vertical panning to the browser, so a touch gesture starts out
    // ambiguous — it could become a carousel swipe or a page scroll. We
    // resolve it with an axis lock: the first _axisLockThreshold px of
    // movement decide the owner.
    //  - Mostly vertical → the drag is abandoned (no navigation, no track
    //    movement) and the browser scrolls the page.
    //  - Mostly horizontal → the carousel claims the gesture and a
    //    non-passive touchmove listener calls preventDefault() so the page
    //    cannot scroll underneath the swipe.
    // If the browser wins the race and takes the gesture first, it fires
    // pointercancel — handled as an abort (spring home), never a navigation.

    _onPointerDown(e) {
        if (e.button !== 0) return;

        // The viewport hosts the arrow buttons too — a press on an arrow is
        // a click, not the start of a drag.
        if (e.target?.closest?.('.arrow')) return;

        // Interrupt any running animation and start from current position
        this._cancelAnimation();

        this._dragging = true;
        this._draggedPastThreshold = false;
        this._pointerStartX = e.clientX;
        this._pointerStartY = e.clientY;
        this._pointerId = e.pointerId;
        this._dragDelta = 0;
        this._velocity = 0;
        this._pointerPrevX = e.clientX;
        this._pointerPrevTime = performance.now();

        // A mouse never scrolls the page by dragging, so there is no gesture
        // ambiguity to resolve — lock to the carousel axis immediately.
        this._axisLock = e.pointerType === 'mouse' ? 'x' : null;

        // Use window-level listeners instead of pointer capture.
        window.addEventListener('pointermove', this._onPointerMove);
        window.addEventListener('pointerup', this._onPointerUp);
        window.addEventListener('pointercancel', this._onPointerCancel);
        // Non-passive so we can preventDefault() page scrolling once the
        // gesture is locked horizontal (see _onTouchMove).
        window.addEventListener('touchmove', this._onTouchMove, { passive: false });
    }

    /** While a drag is locked horizontal, block the browser's vertical page
     *  scroll so the swipe owns the gesture exclusively. Before the axis lock
     *  resolves (or when it resolves vertical) this does nothing and native
     *  scrolling proceeds as normal. */
    _onTouchMove(e) {
        if (this._dragging && this._axisLock === 'x' && e.cancelable) {
            e.preventDefault();
        }
    }

    _onPointerMove(e) {
        if (!this._dragging || e.pointerId !== this._pointerId) return;

        // Resolve the axis lock for touch/pen gestures. Until the pointer
        // leaves the dead zone the track does not move at all — this keeps
        // vertical page scrolling from wiggling the carousel sideways.
        if (!this._axisLock) {
            const dx = e.clientX - this._pointerStartX;
            const dy = e.clientY - this._pointerStartY;
            if (Math.abs(dx) < OlCarousel._axisLockThreshold
                && Math.abs(dy) < OlCarousel._axisLockThreshold) {
                return;
            }
            if (Math.abs(dy) > Math.abs(dx) * OlCarousel._horizontalBias) {
                // Clearly vertical: hand it to the browser for page scroll.
                this._abortDrag();
                return;
            }
            this._axisLock = 'x';
            // Re-anchor the drag at the lock point so the track doesn't
            // jump by the dead-zone distance on the first locked frame.
            this._pointerStartX = e.clientX;
            this._pointerPrevX = e.clientX;
            this._pointerPrevTime = performance.now();
            this._draggedPastThreshold = true;
            this.classList.add('dragging');
            return;
        }

        this._dragDelta = e.clientX - this._pointerStartX;

        // Mark that a real drag occurred (past the 5px dead zone).
        // This flag is checked by _onClickCapture to suppress the click.
        if (Math.abs(this._dragDelta) > 5) {
            this._draggedPastThreshold = true;
            this.classList.add('dragging');
        }

        // Track velocity from recent movement. Samples accumulate over at
        // least _velocitySampleWindow ms (see note there), and an exponential
        // moving average smooths jitter so release momentum is stable.
        const now = performance.now();
        const dt = now - this._pointerPrevTime;
        if (dt >= OlCarousel._velocitySampleWindow) {
            const instantVelocity = (e.clientX - this._pointerPrevX) / dt;
            this._velocity = this._velocity === 0
                ? instantVelocity
                : instantVelocity * 0.8 + this._velocity * 0.2;
            this._pointerPrevX = e.clientX;
            this._pointerPrevTime = now;
        }

        // Direct DOM update — no Lit re-render overhead
        const deltaPct = (this._dragDelta / this.clientWidth) * 100;
        const rawPos = this._currentPos + deltaPct;

        // Rubber-band when dragging past the first or last page
        const minPos = this._getOffsetForPage(this._totalPages - 1);
        const maxPos = this._getOffsetForPage(0); // 0
        this._applyTransform(OlCarousel._rubberBand(rawPos, minPos, maxPos, this.clientWidth));
    }

    _removeDragListeners() {
        window.removeEventListener('pointermove', this._onPointerMove);
        window.removeEventListener('pointerup', this._onPointerUp);
        window.removeEventListener('pointercancel', this._onPointerCancel);
        window.removeEventListener('touchmove', this._onTouchMove);
    }

    /** End the drag without navigating: release the gesture to the browser
     *  and spring the track home to the current page (recovers cleanly when
     *  pointerdown interrupted a running page animation). */
    _abortDrag() {
        this._removeDragListeners();
        this._dragging = false;
        this._axisLock = null;
        requestAnimationFrame(() => {
            this.classList.remove('dragging');
            this._draggedPastThreshold = false;
        });
        this._animateSpring(this._currentPos, 0, this._getOffsetForPage(this._page));
    }

    /** The browser took the gesture (started scrolling, alert, etc.).
     *  Never navigate from a cancelled pointer — just spring home. */
    _onPointerCancel(e) {
        if (e.pointerId !== this._pointerId) return;
        // The track may have moved if the gesture was briefly locked
        // horizontal before the browser claimed it — return from there.
        const width = this.clientWidth;
        const rawPos = this._currentPos + (this._dragDelta / width) * 100;
        const minPos = this._getOffsetForPage(this._totalPages - 1);
        const maxPos = this._getOffsetForPage(0);
        this._currentPos = OlCarousel._rubberBand(rawPos, minPos, maxPos, width);
        this._abortDrag();
    }

    /** Return the page whose resting offset is closest to `pos` (%), so a
     *  long drag can land several pages away instead of snapping back. */
    _nearestPage(pos) {
        let best = 0;
        let bestDist = Infinity;
        for (let p = 0; p < this._totalPages; p++) {
            const dist = Math.abs(this._getOffsetForPage(p) - pos);
            if (dist < bestDist) {
                bestDist = dist;
                best = p;
            }
        }
        return best;
    }

    _onPointerUp(e) {
        if (e.pointerId !== this._pointerId) return;
        this._removeDragListeners();

        this._dragging = false;
        this._axisLock = null;

        // Remove dragging class and clear the drag-click guard after the click
        // event has been processed. rAF fires after event dispatch but before
        // next paint, so the drag's own synthetic click is still suppressed by
        // _onClickCapture, but the flag never lingers to eat a later click
        // (e.g. when the drag was released off the carousel, or a touch swipe
        // fires no synthetic click at all — see _onClickCapture).
        requestAnimationFrame(() => {
            this.classList.remove('dragging');
            this._draggedPastThreshold = false;
        });

        const delta = this._dragDelta;
        const width = this.clientWidth;

        // Discard stale velocity: if the pointer sat still before release
        // (drag, hold, let go) there is no momentum — without this check the
        // last recorded movement would fling the track on release. Fresh
        // velocity is capped so one noisy sample can't launch the track.
        const staleVelocity = performance.now() - this._pointerPrevTime > 100;
        const velocity = staleVelocity
            ? 0
            : Math.max(-OlCarousel._maxVelocity,
                Math.min(OlCarousel._maxVelocity, this._velocity)); // px/ms

        // Current visual position after drag (with rubber-banding applied)
        const rawPos = this._currentPos + (delta / width) * 100;
        const minPos = this._getOffsetForPage(this._totalPages - 1);
        const maxPos = this._getOffsetForPage(0);
        const releasePos = OlCarousel._rubberBand(rawPos, minPos, maxPos, width);
        this._currentPos = releasePos;

        // When released out of bounds, zero out velocity so the spring
        // snaps back cleanly without overshooting past the target page.
        const outOfBounds = rawPos > maxPos || rawPos < minPos;
        const velPct = outOfBounds ? 0 : (velocity / width) * 100;

        // A long drag lands on the page nearest the release position, so one
        // gesture can cross several pages. Momentum projects the endpoint
        // 200ms out, but carries the track at most one page beyond where the
        // drag physically rests — flicks feel lively without launching the
        // carousel out of control.
        const restingPage = this._nearestPage(releasePos);
        const projectedPos = releasePos + velPct * 200;
        let targetPage = Math.max(
            restingPage - 1,
            Math.min(restingPage + 1, this._nearestPage(projectedPos))
        );

        // Preserve the quick flick: a short sharp swipe should advance one
        // page even when the projection falls short of the halfway point.
        const projectedDelta = delta + velocity * 200;
        const threshold = width * 0.1;
        if (targetPage === this._page && Math.abs(projectedDelta) > threshold) {
            if (projectedDelta < 0 && this._page < this._totalPages - 1) {
                targetPage = this._page + 1;
            } else if (projectedDelta > 0 && this._page > 0) {
                targetPage = this._page - 1;
            }
        }

        const targetPos = this._getOffsetForPage(targetPage);
        this._page = targetPage;
        this._updateInert();

        // Spring from release position/velocity to target
        this._animateSpring(releasePos, velPct, targetPos, () => {
            this._emitPageChange();
        });
    }

    // ── Layout ──

    /** Set layout CSS custom properties on the host element.
     *  These cascade into the shadow DOM for ::slotted(*) and .arrow sizing.
     *  Kept separate from the track's inline style so Lit re-renders
     *  never overwrite the imperatively-set transform. */
    _applyTrackLayout() {
        const cols = this._columns;
        const peek = this.peek;
        const gap = this.gap;
        const itemFraction = (1 - peek * 2) / cols;
        const itemPercent = itemFraction * 100;

        this.style.setProperty('--_item-width', `calc(${itemPercent}% - ${gap}px + ${gap / cols}px)`);
        this.style.setProperty('--_peek', String(peek));
        this.style.setProperty('--_gap', `${gap}px`);
    }

    // ── Keyboard ──

    /** Arrow-key navigation for the indicator tablist (APG "Tabs" pattern,
     *  horizontal orientation). The indicators carry a roving tabindex so the
     *  tablist is a single Tab stop; ←/→ and Home/End move between pages and
     *  carry focus to the newly-active indicator. Scoped to the indicators
     *  rather than the whole region on purpose: paging inert-hides the
     *  off-page slotted items, so stealing arrow keys while a book link is
     *  focused would strand that focus on a now-inert element. The arrow
     *  buttons remain the keyboard affordance when indicators are hidden. */
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
        this._focusActiveIndicator();
    }

    /** Move focus to the active indicator after the roving tabindex updates.
     *  Waits for the Lit re-render so the target has tabindex="0". */
    _focusActiveIndicator() {
        this.updateComplete?.then?.(() => {
            this.shadowRoot?.querySelector('.indicator[aria-current="true"]')?.focus();
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
        const showPrev = this._page > 0;
        const showNext = this._page < this._totalPages - 1;

        return html`
            <section
                class="carousel"
                role="region"
                aria-roledescription="carousel"
                aria-label=${this.label}
            >
                ${this._renderIndicators()}
                <div
                    class="viewport"
                    aria-live="polite"
                    aria-atomic="false"
                    @pointerdown=${this._onPointerDown}
                    @dragstart=${(e) => e.preventDefault()}
                >
                    <div class="edge-fade prev" ?hidden=${!showPrev}></div>
                    <div class="edge-fade next" ?hidden=${!showNext}></div>

                    <button
                        class="arrow prev"
                        aria-label=${this.labelPrevious}
                        ?hidden=${!showPrev}
                        @click=${() => this.prev()}
                    ><span class="arrow-icon">${OlCarousel._leftArrow}</span></button>

                    <div class="track">
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
