import { LitElement, html, css, nothing } from 'lit';
import { ifDefined } from 'lit/directives/if-defined.js';
import { lockBodyScroll, unlockBodyScroll } from './utils/scroll-lock.js';
import { getDeepActiveElement, getTabbableFromSlot } from './utils/focus-utils.js';
import { topLayerAttr, promoteToTopLayer, demoteFromTopLayer } from './utils/top-layer.js';

let _idCounter = 0;

/**
 * How long to wait for the exit `transitionend` before finishing the close
 * ourselves. Comfortably past the longest exit transition (150ms panel, 200ms
 * tray) so it never truncates a real animation.
 */
const CLOSE_FALLBACK_MS = 400;

/**
 * Open popovers, topmost (most recently shown) last. Escape is a document-level
 * listener, so every open popover sees the keypress; consulting this stack lets
 * only the innermost popover close, dismissing one layer at a time when popovers
 * are nested (rather than collapsing the whole stack on a single Escape).
 * @type {OlPopover[]}
 */
const _openPopoverStack = [];

/** Drop `el` from the open-popover stack if present. */
function _removeFromOverlayStack(el) {
    const i = _openPopoverStack.indexOf(el);
    if (i !== -1) _openPopoverStack.splice(i, 1);
}

/**
 * A reusable popover component that anchors to a trigger element.
 *
 * Renders a trigger slot and a popover panel that opens/closes with animation.
 * The panel is promoted to the top layer via the Popover API so it escapes
 * overflow clipping, ancestor transforms and z-index stacking, falling back to
 * plain `position: fixed` on browsers without it. It animates from the trigger's
 * location using `transform-origin`. The `popover` type is `manual`, not `auto`:
 * this component owns its Escape, outside-click and nesting behaviour, and
 * `auto` would force-close sibling popovers outside the ancestor chain.
 *
 * Self-manages open state by default — clicking the slotted trigger toggles
 * the popover, Escape and outside-click close it. Consumers can drive `open`
 * imperatively for programmatic control. The `ol-popover-close` event is
 * cancelable: call `event.preventDefault()` to keep the popover open.
 *
 * Automatically flips and shifts when the panel would overflow the viewport.
 * Repositions on scroll and resize. On mobile viewports, renders as a bottom
 * tray with a drag handle, swipe-to-dismiss, and body scroll locking.
 *
 * Non-modal: while open it keeps focus within the panel, but Tab/Shift+Tab off
 * either edge closes it and returns focus to the trigger (a keyboard user must
 * be able to Tab out — the page behind stays interactive, so we don't set
 * `aria-modal`). The mobile tray is the exception: it has a scrim and locks
 * scroll, so it is `aria-modal` and a screen reader stays inside it too.
 * Restores focus to the previously-focused element on close. The
 * host's `aria-label` is forwarded to the inner dialog as its accessible name.
 *
 * @element ol-popover
 *
 * @prop {Boolean} open - Whether the popover is currently open
 * @prop {String} placement - Preferred placement relative to the trigger.
 *     Format: "{side}-{align}" where side is "top" or "bottom" and align is
 *     "start", "center", or "end". Default: "bottom-start" — a panel is
 *     usually wider than the control that opens it, and aligning their leading
 *     edges keeps it under the trigger instead of straddling it.
 * @prop {Number} offset - Gap in px between trigger and popover (default: 4)
 * @prop {Boolean} autoClose - Whether outside clicks close the popover.
 *     Escape always closes for accessibility. Default: true
 *
 * @attr aria-label - Forwarded to the inner dialog as its accessible name.
 *
 * @fires ol-popover-open - Fired when the popover opens.
 *     detail: { placement: String }
 * @fires ol-popover-close - Cancelable. Fired when the popover requests to
 *     close. Call `preventDefault()` to keep it open. Note: the swipe-dismiss
 *     close fires after the gesture completes and is not cancelable.
 *     detail: { reason: 'escape' | 'outside-click' | 'swipe' | 'trigger' | 'tab' }
 *
 * @slot trigger - The trigger element (button, icon, etc.)
 * @slot - Default slot for popover content
 *
 * @example
 * <ol-popover aria-label="Edit options">
 *   <button slot="trigger">Open</button>
 *   <div>Popover content here</div>
 * </ol-popover>
 */
export class OlPopover extends LitElement {
    static properties = {
        open: { type: Boolean, reflect: true },
        placement: { type: String },
        offset: { type: Number },
        autoClose: { type: Boolean, attribute: 'auto-close' },
        _position: { state: true },
        _transformOrigin: { state: true },
        _animState: { state: true },
        _mobile: { state: true },
    };

    // Animation states: closed → preparing → entering → open → exiting → closed
    // "preparing" renders the panel in the DOM at its start position (opacity 0,
    // scale 0.95) without a transition so the browser paints it. We measure the
    // panel here for collision detection, then move to "entering".

    static styles = css`
        :host {
            display: inline-flex;
            align-items: center;
            position: relative;
        }


        .panel {
            position: fixed;
            z-index: var(--z-index-dropdown);
            background: var(--white);
            border: var(--border-overlay);
            border-radius: var(--border-radius-overlay);
            box-shadow: var(--box-shadow-overlay);
            opacity: 0;
            transform: scale(0.95);
            pointer-events: none;
        }

        /* Neutralize the UA's [popover] defaults (inset: 0, margin: auto,
           border, padding, overflow, system colors) so the top-layer panel is
           laid out purely by the inline top/left we compute. Must precede
           .panel.tray, which restates its own inset and margin. The border is
           restated rather than zeroed: this rule outranks .panel, and the
           hairline is what separates the panel from the page. */
        .panel[popover] {
            inset: auto;
            width: auto;
            height: auto;
            margin: 0;
            padding: 0;
            border: var(--border-overlay);
            overflow: visible;
            color: inherit;
        }

        .panel[data-state="preparing"],
        .panel[data-state="entering"] {
            will-change: transform, opacity;
        }

        .panel[data-state="entering"],
        .panel[data-state="open"] {
            opacity: 1;
            transform: scale(1);
            pointer-events: auto;
        }

        .panel[data-state="entering"] {
            transition:
                opacity var(--duration-base) var(--ease-enter),
                transform var(--duration-base) var(--ease-enter);
        }

        .panel[data-state="exiting"] {
            opacity: 0;
            transform: scale(0.95);
            pointer-events: none;
            transition:
                opacity var(--duration-fast) var(--ease-exit),
                transform var(--duration-fast) var(--ease-exit);
            will-change: transform, opacity;
        }

        /* ── Mobile tray backdrop ── */

        /* Same scrim as ol-dialog: the tray is modal, so it should push the
           page back the same way. The blur is constant, so only opacity
           animates. */
        .backdrop {
            position: fixed;
            inset: 0;
            z-index: var(--z-index-dropdown);
            /* Undo the UA [popover] defaults. width/height matter most: the UA's
               fit-content beats inset: 0, collapsing the backdrop to 0x0 and
               taking the dimming layer and its tap-to-dismiss target with it. */
            width: auto;
            height: auto;
            margin: 0;
            padding: 0;
            border: none;
            background: var(--overlay-backdrop-color);
            opacity: 0;
            backdrop-filter: blur(var(--overlay-backdrop-blur));
            -webkit-backdrop-filter: blur(var(--overlay-backdrop-blur));
            pointer-events: none;
        }

        .backdrop[data-state="entering"],
        .backdrop[data-state="open"] {
            opacity: 1;
            pointer-events: auto;
        }

        .backdrop[data-state="entering"] {
            transition: opacity var(--duration-slow) var(--ease-enter);
        }

        .backdrop[data-state="exiting"] {
            opacity: 0;
            pointer-events: none;
            transition: opacity var(--duration-base) var(--ease-enter);
        }

        /* ── Mobile tray panel ── */

        .panel.tray {
            top: auto;
            bottom: 0;
            left: 0;
            right: 0;
            width: auto;
            max-height: 85vh;
            max-height: 85dvh;
            overflow-y: auto;
            -webkit-overflow-scrolling: touch;
            margin: 0 12px calc(12px + env(safe-area-inset-bottom));
            border-radius: var(--border-radius-overlay);
            opacity: 1;
            transform: translateY(100%);
            touch-action: manipulation;
        }

        .panel.tray[data-state="preparing"],
        .panel.tray[data-state="entering"] {
            will-change: transform;
        }

        .panel.tray[data-state="entering"],
        .panel.tray[data-state="open"] {
            opacity: 1;
            transform: translateY(0);
            pointer-events: auto;
        }

        .panel.tray[data-state="entering"] {
            transition: transform var(--duration-slow) var(--ease-enter);
        }

        .panel.tray[data-state="exiting"] {
            opacity: 1;
            transform: translateY(100%);
            pointer-events: none;
            transition: transform var(--duration-base) var(--ease-enter);
            will-change: transform;
        }

        /* ── Tray drag handle ── */

        .tray-handle {
            display: flex;
            justify-content: center;
            padding: 10px 0 2px;
            cursor: grab;
            touch-action: none;
        }

        .tray-handle:active {
            cursor: grabbing;
        }

        .tray-handle-bar {
            width: 36px;
            height: 4px;
            border-radius: 2px;
            background: var(--color-drag-handle);
        }

        /* ── Focus sentinel (visually hidden) ── */

        .focus-sentinel {
            position: absolute;
            width: 1px;
            height: 1px;
            padding: 0;
            margin: -1px;
            overflow: hidden;
            clip: rect(0, 0, 0, 0);
            white-space: nowrap;
            border: 0;
        }

        @media (prefers-reduced-motion: reduce) {
            .panel[data-state="entering"],
            .panel[data-state="exiting"],
            .panel.tray[data-state="entering"],
            .panel.tray[data-state="exiting"],
            .backdrop[data-state="entering"],
            .backdrop[data-state="exiting"] {
                transition: none;
            }
        }
    `;

    constructor() {
        super();
        this.open = false;
        this.placement = 'bottom-start';
        this.offset = 4;
        this.autoClose = true;
        this._position = { top: 0, left: 0 };
        this._transformOrigin = 'top left';
        this._animState = 'closed';
        this._mobile = false;
        this._scrollLocked = false;
        this._panelId = `ol-popover-${++_idCounter}`;
        this._prevFocus = null;
        this._rafId = null;
        this._closeFallbackId = null;

        // Touch drag state
        this._touchStartY = 0;
        this._touchStartTime = 0;
        this._isDragging = false;
        this._isHandleDrag = false;
        this._lastDragY = 0;

        this._onTriggerClick = this._onTriggerClick.bind(this);
        this._onOutsideClick = this._onOutsideClick.bind(this);
        this._onKeydownGlobal = this._onKeydownGlobal.bind(this);
        this._onScrollResize = this._onScrollResize.bind(this);
        this._onTouchStart = this._onTouchStart.bind(this);
        this._onTouchMove = this._onTouchMove.bind(this);
        this._onTouchEnd = this._onTouchEnd.bind(this);
    }

    render() {
        const showPanel = this._animState !== 'closed';
        return html`
            <slot name="trigger" @click="${this._onTriggerClick}"></slot>
            ${showPanel ? html`
                ${this._mobile ? html`
                    <div
                        class="backdrop"
                        popover="${ifDefined(topLayerAttr())}"
                        data-state="${this._animState}"
                        @click="${this._onBackdropClick}"
                    ></div>
                ` : nothing}
                <!-- Sentinels bracket the panel (rather than nesting inside it)
                     so focus reaching one means the user has Tabbed past the
                     panel's edge. A popover is non-modal, so that closes it (see
                     _onSentinelFocus) rather than wrapping — Tab must be able to
                     leave. They're only reached by a genuine boundary crossing. -->
                <span
                    class="focus-sentinel"
                    tabindex="0"
                    aria-hidden="true"
                    data-edge="start"
                    @focus="${this._onSentinelFocus}"
                ></span>
                <div
                    id="${this._panelId}"
                    class="panel ${this._mobile ? 'tray' : ''}"
                    popover="${ifDefined(topLayerAttr())}"
                    data-state="${this._animState}"
                    role="dialog"
                    aria-label="${ifDefined(this.getAttribute('aria-label') || undefined)}"
                    aria-modal="${ifDefined(this._mobile ? 'true' : undefined)}"
                    tabindex="-1"
                    style="${this._mobile ? '' : `
                        top: ${this._position.top}px;
                        left: ${this._position.left}px;
                        transform-origin: ${this._transformOrigin};
                    `}"
                    @transitionend="${this._onTransitionEnd}"
                >
                    ${this._mobile ? html`
                        <div class="tray-handle" aria-hidden="true">
                            <div class="tray-handle-bar"></div>
                        </div>
                    ` : nothing}
                    <slot></slot>
                </div>
                <span
                    class="focus-sentinel"
                    tabindex="0"
                    aria-hidden="true"
                    data-edge="end"
                    @focus="${this._onSentinelFocus}"
                ></span>
            ` : nothing}
        `;
    }

    firstUpdated() {
        const triggerSlot = this.shadowRoot.querySelector('slot[name="trigger"]');
        triggerSlot?.addEventListener('slotchange', () => this._syncTriggerAria());
    }

    updated(changed) {
        if (changed.has('open')) {
            this._syncTriggerAria();
            if (this.open) {
                this._show();
            } else if (changed.get('open') === true) {
                this._hide();
            }
        }
    }

    // ── Show / Hide ─────────────────────────────────────────────

    _show() {
        // Reopening mid-exit cancels the pending close rather than letting its
        // timer fire into the reopened popover.
        this._clearCloseFallback();
        this._prevFocus = getDeepActiveElement();

        document.addEventListener('click', this._onOutsideClick, true);
        document.addEventListener('keydown', this._onKeydownGlobal);

        // Become the topmost overlay for Escape handling. Remove any stale entry
        // first so a re-show can't leave us in the stack twice.
        _removeFromOverlayStack(this);
        _openPopoverStack.push(this);

        // Keep 767px (--width-breakpoint-tablet - 1px) in sync with the tray
        // media queries in header-bar.css / OlSelectPopover.js.
        this._mobile = window.matchMedia('(max-width: 767px)').matches;
        const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        // Guard on _scrollLocked: reopening during the exit transition would take
        // a second refcount that the single _releaseScrollLock() never gives
        // back, pinning <body> for good.
        if (this._mobile && !this._scrollLocked) {
            lockBodyScroll();
            this._scrollLocked = true;
        }

        // On desktop, render panel off-screen first so we can measure it.
        // On mobile, CSS positions the tray at the bottom automatically.
        if (!this._mobile) {
            this._position = { top: -9999, left: -9999 };
        }
        this._animState = reducedMotion ? 'open' : 'preparing';

        this.updateComplete.then(() => {
            const panel = this.shadowRoot.querySelector('.panel');
            if (!panel) return;

            // Promote to the top layer before measuring — a [popover] element is
            // `display: none` until shown, so offsetWidth/Height would read 0.
            // Backdrop first: within the top layer, later-shown paints on top.
            promoteToTopLayer(this.shadowRoot.querySelector('.backdrop'));
            promoteToTopLayer(panel);

            // Desktop: measure and position relative to trigger.
            // Use offsetWidth/Height — getBoundingClientRect includes the
            // scale(0.95) transform from the preparing state, under-reporting
            // the true layout size by 5%.
            if (!this._mobile) {
                this._computePosition(panel.offsetWidth, panel.offsetHeight);
            }

            // Add scroll/resize listeners for repositioning (desktop)
            this._addScrollResizeListeners();

            // Add touch listeners for swipe-to-dismiss (mobile)
            if (this._mobile) {
                panel.addEventListener('touchstart', this._onTouchStart, { passive: true });
                panel.addEventListener('touchmove', this._onTouchMove, { passive: false });
                panel.addEventListener('touchend', this._onTouchEnd, { passive: true });
            }

            // Focus the panel for screen reader context
            panel.focus({ preventScroll: true });

            if (reducedMotion) {
                this.dispatchEvent(new CustomEvent('ol-popover-open', {
                    bubbles: true, composed: true,
                    detail: { placement: this.placement },
                }));
                return;
            }

            // Force reflow so the browser paints the start position
            panel.getBoundingClientRect();

            this._animState = 'entering';
            this.dispatchEvent(new CustomEvent('ol-popover-open', {
                bubbles: true, composed: true,
                detail: { placement: this.placement },
            }));
        });
    }

    _hide() {
        if (this._animState === 'closed') return;

        const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (reducedMotion) {
            this._animState = 'closed';
            this._cleanup();
            return;
        }

        this._animState = 'exiting';
        this._armCloseFallback();
    }

    /**
     * `transitionend` drives the whole close path — top-layer demotion, listener
     * removal, scroll unlock, focus restore — so a transition that never runs
     * strands the panel in the top layer, above the page, holding focus inside a
     * `role="dialog"` whose trigger already reports `aria-expanded="false"`.
     *
     * Two ways to miss the event: a backgrounded tab paints no frames, so the
     * transition never starts; and closing while still in "preparing" changes no
     * property at all (preparing and exiting both compute to `opacity: 0` with
     * the same transform), so nothing transitions. Finish the close on a timer
     * when the event doesn't arrive.
     */
    _armCloseFallback() {
        this._clearCloseFallback();
        this._closeFallbackId = setTimeout(() => {
            this._closeFallbackId = null;
            if (this._animState !== 'exiting') return;
            this._animState = 'closed';
            this._cleanup();
        }, CLOSE_FALLBACK_MS);
    }

    _clearCloseFallback() {
        if (this._closeFallbackId) {
            clearTimeout(this._closeFallbackId);
            this._closeFallbackId = null;
        }
    }

    _onTransitionEnd(e) {
        if (e.target !== e.currentTarget) return;

        if (this._animState === 'entering') {
            this._animState = 'open';
        } else if (this._animState === 'exiting') {
            this._animState = 'closed';
            this._cleanup();
        }
    }

    /**
     * Central cleanup called when the popover finishes closing.
     * Removes all global listeners, unlocks scroll, and restores focus.
     */
    _cleanup() {
        this._clearCloseFallback();
        this._removeListeners();
        this._releaseScrollLock();
        demoteFromTopLayer(this.shadowRoot?.querySelector('.panel'));
        demoteFromTopLayer(this.shadowRoot?.querySelector('.backdrop'));
        this._restoreFocus();
    }

    _restoreFocus() {
        if (this._prevFocus && typeof this._prevFocus.focus === 'function') {
            this._prevFocus.focus({ preventScroll: true });
        }
        this._prevFocus = null;
    }

    // ── Trigger ARIA ────────────────────────────────────────────

    /**
     * No aria-controls: the trigger is slotted from outside this shadow root
     * and the panel's id lives inside it, so the reference could never resolve
     * — a dangling IDREF is worse than none. haspopup + expanded carry the
     * relationship.
     */
    _syncTriggerAria() {
        const trigger = this._triggerEl;
        if (!trigger) return;
        trigger.setAttribute('aria-haspopup', 'dialog');
        trigger.setAttribute('aria-expanded', String(this.open));
    }

    // ── Focus containment (non-modal: Tab out closes) ───────────

    _getFocusableElements() {
        // Deep, shadow-piercing collection of the panel's slotted content, so a
        // custom element in the panel contributes its real inner focusable (a
        // plain querySelectorAll would stop at its shadow boundary).
        return getTabbableFromSlot(this.shadowRoot?.querySelector('.panel slot:not([name])'));
    }

    /**
     * Focus reached a bracketing sentinel → the user Tabbed past the panel's
     * edge. A popover is non-modal, so we close it and let focus return to the
     * trigger (via _restoreFocus) instead of wrapping back into the panel — a
     * keyboard user must be able to Tab out. The sentinels detect the boundary
     * crossing robustly regardless of the panel's internal tab semantics (e.g.
     * a native radio group, which is a single tab stop), which an index-based
     * edge check could not.
     *
     * If a consumer cancels the close (`ol-popover-close` is cancelable), fall
     * back to wrapping so focus never sticks on the hidden sentinel.
     */
    _onSentinelFocus(e) {
        const edge = e.target.dataset.edge;
        this._requestClose('tab');
        if (!this.open) return; // closed as expected — focus restored to trigger

        // Close was vetoed: keep focus usable by wrapping within the panel.
        const focusable = this._getFocusableElements();
        if (focusable.length === 0) {
            this.shadowRoot.querySelector('.panel')?.focus({ preventScroll: true });
        } else if (edge === 'start') {
            focusable[focusable.length - 1].focus({ preventScroll: true });
        } else {
            focusable[0].focus({ preventScroll: true });
        }
    }

    // ── Positioning ─────────────────────────────────────────────

    /**
     * Compute the final position of the popover panel, flipping and shifting
     * as needed to keep it within the viewport.
     */
    _computePosition(panelW, panelH) {
        const trigger = this._triggerEl;
        if (!trigger) return;

        const anchor = trigger.getBoundingClientRect();
        const gap = this.offset;
        const viewW = window.innerWidth;
        const viewH = window.innerHeight;
        const pad = 8; // minimum distance from viewport edge

        // Parse requested placement
        const [reqSide, reqAlign] = this._parsePlacement(this.placement);

        // Determine side (top or bottom), flipping if it would overflow
        let side = reqSide;
        const spaceBelow = viewH - anchor.bottom - gap;
        const spaceAbove = anchor.top - gap;

        if (side === 'bottom' && panelH > spaceBelow && spaceAbove > spaceBelow) {
            side = 'top';
        } else if (side === 'top' && panelH > spaceAbove && spaceBelow > spaceAbove) {
            side = 'bottom';
        }

        // Vertical position
        let top;
        if (side === 'bottom') {
            top = anchor.bottom + gap;
        } else {
            top = anchor.top - gap - panelH;
        }

        // Horizontal position based on alignment
        let left;
        const anchorCenter = anchor.left + anchor.width / 2;

        switch (reqAlign) {
        case 'center':
            left = anchorCenter - panelW / 2;
            break;
        case 'end':
            left = anchor.right - panelW;
            break;
        case 'start':
        default:
            left = anchor.left;
            break;
        }

        // Shift horizontally to keep within viewport
        if (left + panelW > viewW - pad) {
            left = viewW - pad - panelW;
        }
        if (left < pad) {
            left = pad;
        }

        // Shift vertically to keep within viewport
        if (top + panelH > viewH - pad) {
            top = viewH - pad - panelH;
        }
        if (top < pad) {
            top = pad;
        }

        // Compute transform-origin so the animation radiates from the trigger.
        // The origin is expressed relative to the panel's top-left corner.
        const originY = side === 'bottom' ? 'top' : 'bottom';

        // Find where the anchor center falls within the panel horizontally
        const anchorCenterInPanel = anchorCenter - left;
        const originX = `${anchorCenterInPanel}px`;

        this._position = { top, left };
        this._transformOrigin = `${originX} ${originY}`;
    }

    _parsePlacement(placement) {
        const parts = (placement || 'bottom-start').split('-');
        const side = parts[0] === 'top' ? 'top' : 'bottom';
        const align = ['start', 'center', 'end'].includes(parts[1]) ? parts[1] : 'start';
        return [side, align];
    }

    get _triggerEl() {
        const slot = this.shadowRoot?.querySelector('slot[name="trigger"]');
        // flatten:true unwraps nested <slot>s (ol-select-popover) so we anchor
        // to the real trigger element, not a layout-less slot node.
        return slot?.assignedElements({ flatten: true })[0] ?? null;
    }

    // ── Scroll / resize repositioning ───────────────────────────

    _addScrollResizeListeners() {
        window.addEventListener('scroll', this._onScrollResize, { capture: true, passive: true });
        window.addEventListener('resize', this._onScrollResize, { passive: true });
    }

    _removeScrollResizeListeners() {
        window.removeEventListener('scroll', this._onScrollResize, { capture: true });
        window.removeEventListener('resize', this._onScrollResize);
        if (this._rafId) {
            cancelAnimationFrame(this._rafId);
            this._rafId = null;
        }
    }

    _onScrollResize() {
        if (this._rafId) return;
        this._rafId = requestAnimationFrame(() => {
            this._rafId = null;
            if (this._mobile) return;
            if (this._animState !== 'open' && this._animState !== 'entering') return;
            const panel = this.shadowRoot?.querySelector('.panel');
            if (panel) {
                this._computePosition(panel.offsetWidth, panel.offsetHeight);
            }
        });
    }

    // ── Trigger / outside click / keyboard ──────────────────────

    _onTriggerClick() {
        if (this.open) {
            this._requestClose('trigger');
        } else {
            this.open = true;
        }
    }

    _onOutsideClick(e) {
        if (!this.autoClose) return;
        if (this._animState === 'closed' || this._animState === 'exiting') return;
        const path = e.composedPath();
        if (!path.includes(this)) {
            this._requestClose('outside-click');
        }
    }

    _onBackdropClick() {
        if (this.autoClose) {
            this._requestClose('outside-click');
        }
    }

    _onKeydownGlobal(e) {
        if (e.key === 'Escape' && this.open) {
            // Only the innermost open popover responds, so nested popovers close
            // one layer per Escape instead of all at once.
            if (_openPopoverStack[_openPopoverStack.length - 1] !== this) return;
            e.preventDefault();
            this._requestClose('escape');
        }
    }

    _requestClose(reason) {
        const ev = new CustomEvent('ol-popover-close', {
            bubbles: true, composed: true, cancelable: true,
            detail: { reason },
        });
        this.dispatchEvent(ev);
        if (!ev.defaultPrevented) {
            this.open = false;
        }
    }

    // ── Mobile touch / swipe-to-dismiss ─────────────────────────

    _onTouchStart(e) {
        const handle = this.shadowRoot.querySelector('.tray-handle');
        const panel = this.shadowRoot.querySelector('.panel');
        const touch = e.touches[0];
        const path = e.composedPath();

        this._touchStartY = touch.clientY;
        this._touchStartTime = Date.now();
        this._isDragging = false;
        this._dragBlocked = false;
        this._lastDragY = 0;
        this._isHandleDrag = !!(handle && path.includes(handle));
        // Read scroll position from the actual scroll container under the touch,
        // not the panel — consumers like ol-select-popover scroll an inner
        // element, so panel.scrollTop stays 0 and would wrongly read as
        // "scrolled to top", triggering swipe-to-dismiss mid-list.
        this._touchScrollTop = this._scrollableInPath(path, panel)?.scrollTop ?? 0;
    }

    /**
     * Walk the touch's composed path (which includes slotted light-DOM content)
     * up to and including the panel, returning the first vertically scrollable
     * element. Falls back to the panel itself.
     */
    _scrollableInPath(path, panel) {
        for (const el of path) {
            if (el instanceof HTMLElement && el.scrollHeight > el.clientHeight) {
                const overflowY = getComputedStyle(el).overflowY;
                if (overflowY === 'auto' || overflowY === 'scroll') return el;
            }
            if (el === panel) break;
        }
        return panel;
    }

    _onTouchMove(e) {
        if (this._dragBlocked) return;

        const touch = e.touches[0];
        const deltaY = touch.clientY - this._touchStartY;

        if (!this._isDragging) {
            // Start drag if touching handle, or at scroll-top and swiping down
            if (this._isHandleDrag || (this._touchScrollTop <= 0 && deltaY > 5)) {
                // Scrolling already underway — the browser won't let us cancel
                // the gesture, and preventDefault() would only log a console
                // intervention. Leave the rest of the touch to the scroller.
                if (!e.cancelable) {
                    this._dragBlocked = true;
                    return;
                }
                this._isDragging = true;
            } else {
                return; // Let normal scroll happen
            }
        }

        const dragY = Math.max(0, deltaY);
        this._lastDragY = dragY;
        if (e.cancelable) e.preventDefault();

        const panel = this.shadowRoot.querySelector('.panel');
        if (panel) {
            panel.style.transform = `translateY(${dragY}px)`;
            panel.style.transition = 'none';
        }

        const backdrop = this.shadowRoot.querySelector('.backdrop');
        if (backdrop) {
            const progress = Math.min(dragY / 300, 1);
            backdrop.style.opacity = String(1 - progress);
            backdrop.style.transition = 'none';
        }
    }

    _onTouchEnd() {
        if (!this._isDragging) return;

        const dragY = this._lastDragY;
        const elapsed = Date.now() - this._touchStartTime;
        const velocity = dragY / Math.max(elapsed, 1);

        this._isDragging = false;
        this._dragBlocked = false;
        this._lastDragY = 0;

        const panel = this.shadowRoot.querySelector('.panel');
        const backdrop = this.shadowRoot.querySelector('.backdrop');

        const DISMISS_THRESHOLD = 80;
        const VELOCITY_THRESHOLD = 0.5;

        if (dragY > DISMISS_THRESHOLD || velocity > VELOCITY_THRESHOLD) {
            // Swipe dismiss — animate to off-screen, then close
            if (panel) {
                panel.style.transition = 'transform var(--duration-base) var(--ease-enter)';
                panel.style.transform = 'translateY(100%)';
            }
            if (backdrop) {
                backdrop.style.transition = 'opacity var(--duration-base) var(--ease-enter)';
                backdrop.style.opacity = '0';
            }

            const onDone = () => {
                panel?.removeEventListener('transitionend', onDone);
                this._clearDragStyles();
                this._animState = 'closed';
                this._cleanup();
                // Sync the `open` property so the trigger toggles correctly on
                // the next tap. _animState is already 'closed', so the _hide()
                // this triggers early-returns without re-animating.
                this.open = false;
                this.dispatchEvent(new CustomEvent('ol-popover-close', {
                    bubbles: true, composed: true,
                    detail: { reason: 'swipe' },
                }));
            };

            if (panel) {
                panel.addEventListener('transitionend', onDone, { once: true });
            } else {
                onDone();
            }
        } else {
            // Snap back to open position
            if (panel) {
                panel.style.transition = 'transform var(--duration-base) var(--ease-enter)';
                panel.style.transform = '';
            }
            if (backdrop) {
                backdrop.style.transition = 'opacity var(--duration-base) var(--ease-enter)';
                backdrop.style.opacity = '';
            }

            const onDone = () => {
                panel?.removeEventListener('transitionend', onDone);
                this._clearDragStyles();
            };

            if (panel) {
                panel.addEventListener('transitionend', onDone, { once: true });
            }
        }
    }

    _clearDragStyles() {
        const panel = this.shadowRoot?.querySelector('.panel');
        const backdrop = this.shadowRoot?.querySelector('.backdrop');
        if (panel) {
            panel.style.transition = '';
            panel.style.transform = '';
        }
        if (backdrop) {
            backdrop.style.transition = '';
            backdrop.style.opacity = '';
        }
    }

    // ── Body scroll lock ────────────────────────────────────────

    /** Releases the body scroll lock if this popover holds one. Idempotent. */
    _releaseScrollLock() {
        if (this._scrollLocked) {
            unlockBodyScroll();
            this._scrollLocked = false;
        }
    }

    // ── Listener management ─────────────────────────────────────

    _removeListeners() {
        document.removeEventListener('click', this._onOutsideClick, true);
        document.removeEventListener('keydown', this._onKeydownGlobal);
        _removeFromOverlayStack(this);
        this._removeScrollResizeListeners();

        // Remove touch listeners from panel
        const panel = this.shadowRoot?.querySelector('.panel');
        if (panel) {
            panel.removeEventListener('touchstart', this._onTouchStart);
            panel.removeEventListener('touchmove', this._onTouchMove);
            panel.removeEventListener('touchend', this._onTouchEnd);
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._clearCloseFallback();
        this._removeListeners();
        this._releaseScrollLock();
    }
}

if (!customElements.get('ol-popover')) {
    customElements.define('ol-popover', OlPopover);
}
