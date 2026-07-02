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
 * @cssprop [--ol-carousel-arrow-color=var(--color-text)] - Colour of the arrow glyphs
 * @cssprop [--ol-carousel-arrow-icon-bg=var(--color-surface)] - Background of the round arrow buttons
 * @cssprop [--ol-carousel-arrow-icon-border=hsl(55, 20%, 83%)] - Border of the round arrow buttons
 * @cssprop [--ol-carousel-arrow-icon-size=36px] - Diameter of the round arrow buttons
 * @cssprop [--ol-carousel-indicator-color=var(--neutral-300)] - Colour of the inactive page indicators
 * @cssprop [--ol-carousel-indicator-active=var(--color-text)] - Colour of the active page indicator
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
            --_arrow-color: var(--ol-carousel-arrow-color, var(--color-text));
            --_arrow-icon-bg: var(--ol-carousel-arrow-icon-bg, var(--color-surface));
            --_arrow-icon-border: var(--ol-carousel-arrow-icon-border, hsl(55, 20%, 83%));
            --_arrow-icon-size: var(--ol-carousel-arrow-icon-size, 36px);
            --_indicator-color: var(--ol-carousel-indicator-color, var(--neutral-300));
            --_indicator-active: var(--ol-carousel-indicator-active, var(--color-text));
            /* Breathing room inside the clipped viewport so slotted items can
           show a hover lift/shadow without it being cut off. Opt-in: 0 by
           default, set --ol-carousel-viewport-padding to enable. */
            --_viewport-padding: var(--ol-carousel-viewport-padding, 0);
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
        .viewport {
            position: relative;
            overflow: hidden;
            padding-block: var(--_viewport-padding);
        }

        /* ── Track ── */
        .track {
            display: flex;
            gap: var(--_gap, 4px);
            will-change: transform;
            touch-action: pan-y pinch-zoom;
            user-select: none;
            -webkit-user-select: none;
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
            z-index: var(--z-index-level-1);
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
            z-index: var(--z-index-level-2);
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

        // Current track position in % (source of truth for rendering)
        this._currentPos = 0;

        /** @type {ResizeObserver|null} */
        this._resizeObserver = null;

        // Pointer / drag state (non-reactive for zero-overhead drag)
        this._dragging = false;
        this._pointerStartX = 0;
        this._pointerId = null;
        this._dragDelta = 0;
        this._velocity = 0;
        this._pointerPrevX = 0;
        this._pointerPrevTime = 0;

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
        this._onClickCapture = this._onClickCapture.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();

        // ── Drag-click prevention ──
        // Intercept clicks in the CAPTURE phase on the host element.
        // Composed click events from slotted light-DOM children (e.g. <a>
        // tags) bubble up through the shadow boundary. By listening in
        // capture on the host, we fire before the click reaches any <a>.
        this.addEventListener('click', this._onClickCapture, true);

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
        const loadThrough = Math.min(items.length - 1, endVisible + this._columns);
        for (let i = 0; i <= loadThrough; i++) {
            const imgs = items[i].querySelectorAll?.('img[data-lazy]');
            if (!imgs) continue;
            imgs.forEach((img) => {
                img.src = img.dataset.lazy;
                img.removeAttribute('data-lazy');
            });
        }
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

    _onPointerDown(e) {
        if (e.button !== 0) return;

        // Interrupt any running animation and start from current position
        this._cancelAnimation();

        this._dragging = true;
        this._draggedPastThreshold = false;
        this._pointerStartX = e.clientX;
        this._pointerId = e.pointerId;
        this._dragDelta = 0;
        this._velocity = 0;
        this._pointerPrevX = e.clientX;
        this._pointerPrevTime = performance.now();

        // Use window-level listeners instead of pointer capture.
        window.addEventListener('pointermove', this._onPointerMove);
        window.addEventListener('pointerup', this._onPointerUp);
        window.addEventListener('pointercancel', this._onPointerUp);
    }

    _onPointerMove(e) {
        if (!this._dragging || e.pointerId !== this._pointerId) return;
        this._dragDelta = e.clientX - this._pointerStartX;

        // Mark that a real drag occurred (past the 5px dead zone).
        // This flag is checked by _onClickCapture to suppress the click.
        if (Math.abs(this._dragDelta) > 5) {
            this._draggedPastThreshold = true;
            this.classList.add('dragging');
        }

        // Track velocity from recent movement
        const now = performance.now();
        const dt = now - this._pointerPrevTime;
        if (dt > 0) {
            this._velocity = (e.clientX - this._pointerPrevX) / dt;
        }
        this._pointerPrevX = e.clientX;
        this._pointerPrevTime = now;

        // Direct DOM update — no Lit re-render overhead
        const deltaPct = (this._dragDelta / this.clientWidth) * 100;
        const rawPos = this._currentPos + deltaPct;

        // Rubber-band when dragging past the first or last page
        const minPos = this._getOffsetForPage(this._totalPages - 1);
        const maxPos = this._getOffsetForPage(0); // 0
        this._applyTransform(OlCarousel._rubberBand(rawPos, minPos, maxPos, this.clientWidth));
    }

    _onPointerUp(e) {
        if (e.pointerId !== this._pointerId) return;
        window.removeEventListener('pointermove', this._onPointerMove);
        window.removeEventListener('pointerup', this._onPointerUp);
        window.removeEventListener('pointercancel', this._onPointerUp);

        this._dragging = false;

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
        const velocity = this._velocity; // px/ms
        const width = this.clientWidth;

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

        // Project endpoint with momentum to decide target page
        const projectedDelta = delta + velocity * 200;
        const threshold = width * 0.1;

        let targetPage = this._page;
        if (Math.abs(projectedDelta) > threshold) {
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

    // ── Render ──

    _renderIndicators() {
        if (!this.showIndicators || this._totalPages <= 1) return nothing;
        return html`
            <div class="indicators" role="tablist" aria-label="Carousel pages">
                ${Array.from({ length: this._totalPages }, (_, i) => html`
                    <button
                        class="indicator"
                        role="tab"
                        aria-label="Go to page ${i + 1} of ${this._totalPages}"
                        aria-current=${i === this._page ? 'true' : 'false'}
                        aria-selected=${i === this._page ? 'true' : 'false'}
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
                >
                    <div class="edge-fade prev" ?hidden=${!showPrev}></div>
                    <div class="edge-fade next" ?hidden=${!showNext}></div>

                    <button
                        class="arrow prev"
                        aria-label=${this.labelPrevious}
                        ?hidden=${!showPrev}
                        @click=${() => this.prev()}
                    ><span class="arrow-icon">${OlCarousel._leftArrow}</span></button>

                    <div
                        class="track"
                        @pointerdown=${this._onPointerDown}
                        @dragstart=${(e) => e.preventDefault()}
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
            </section>
        `;
    }
}

customElements.define('ol-carousel', OlCarousel);
