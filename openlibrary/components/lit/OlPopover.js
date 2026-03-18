import { LitElement, html, css, nothing } from 'lit';
import { ifDefined } from 'lit/directives/if-defined.js';

let _idCounter = 0;

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * A reusable popover component that anchors to a trigger element.
 *
 * Renders a trigger slot and a popover panel that opens/closes with animation.
 * The popover uses `position: fixed` to escape overflow clipping and animates
 * from the trigger's location using `transform-origin`.
 *
 * Automatically flips and shifts when the panel would overflow the viewport.
 * Repositions on scroll and resize. On mobile viewports, renders as a bottom
 * tray with a drag handle, swipe-to-dismiss, and body scroll locking.
 *
 * Traps focus within the popover while open and restores focus to the
 * previously-focused element on close.
 *
 * @element ol-popover
 *
 * @prop {Boolean} open - Whether the popover is currently open
 * @prop {String} placement - Preferred placement relative to the trigger.
 *     Format: "{side}-{align}" where side is "top" or "bottom" and align is
 *     "start", "center", or "end". Default: "bottom-center"
 * @prop {Number} offset - Gap in px between trigger and popover (default: 4)
 * @prop {String} label - Accessible label for the popover dialog
 * @prop {Boolean} autoClose - Whether outside clicks close the popover.
 *     Escape always closes for accessibility. Default: true
 *
 * @fires ol-popover-open - Fired when the popover opens.
 *     detail: { placement: String }
 * @fires ol-popover-close - Fired when the popover requests to close.
 *     detail: { reason: 'escape' | 'outside-click' | 'swipe' }
 *
 * @slot trigger - The trigger element (button, icon, etc.)
 * @slot - Default slot for popover content
 *
 * @example
 * <ol-popover label="Edit options">
 *   <button slot="trigger">Open</button>
 *   <div>Popover content here</div>
 * </ol-popover>
 */
export class OlPopover extends LitElement {
    static properties = {
        open: { type: Boolean, reflect: true },
        placement: { type: String },
        offset: { type: Number },
        label: { type: String },
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
            z-index: 1000;
            background: var(--white, #fff);
            border-radius: var(--border-radius-overlay, 12px);
            box-shadow: 0 8px 24px var(--boxshadow-black, hsla(0, 0%, 0%, 0.15));
            opacity: 0;
            transform: scale(0.95);
            pointer-events: none;
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
                opacity 200ms cubic-bezier(0.165, 0.84, 0.44, 1),
                transform 200ms cubic-bezier(0.165, 0.84, 0.44, 1);
        }

        .panel[data-state="exiting"] {
            opacity: 0;
            transform: scale(0.95);
            pointer-events: none;
            transition:
                opacity 150ms cubic-bezier(0.165, 0.84, 0.44, 1),
                transform 150ms cubic-bezier(0.165, 0.84, 0.44, 1);
            will-change: transform, opacity;
        }

        /* ── Mobile tray backdrop ── */

        .backdrop {
            position: fixed;
            inset: 0;
            z-index: 999;
            background: hsla(0, 0%, 0%, 0.4);
            opacity: 0;
            pointer-events: none;
        }

        .backdrop[data-state="entering"],
        .backdrop[data-state="open"] {
            opacity: 1;
            pointer-events: auto;
        }

        .backdrop[data-state="entering"] {
            transition: opacity 280ms cubic-bezier(0.23, 1, 0.32, 1);
        }

        .backdrop[data-state="exiting"] {
            opacity: 0;
            pointer-events: none;
            transition: opacity 200ms cubic-bezier(0.23, 1, 0.32, 1);
        }

        /* ── Mobile tray panel ── */

        .panel.tray {
            top: auto;
            bottom: 0;
            left: 0;
            right: 0;
            width: auto;
            max-height: 85vh;
            overflow-y: auto;
            -webkit-overflow-scrolling: touch;
            margin: 0 12px calc(12px + env(safe-area-inset-bottom));
            border-radius: 20px;
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
            transition: transform 280ms cubic-bezier(0.23, 1, 0.32, 1);
        }

        .panel.tray[data-state="exiting"] {
            opacity: 1;
            transform: translateY(100%);
            pointer-events: none;
            transition: transform 200ms cubic-bezier(0.23, 1, 0.32, 1);
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
            background: hsla(0, 0%, 0%, 0.2);
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
        this.placement = 'bottom-center';
        this.offset = 4;
        this.label = '';
        this.autoClose = true;
        this._position = { top: 0, left: 0 };
        this._transformOrigin = 'top left';
        this._animState = 'closed';
        this._mobile = false;
        this._panelId = `ol-popover-${++_idCounter}`;
        this._prevFocus = null;
        this._rafId = null;
        this._savedOverflow = null;

        // Touch drag state
        this._touchStartY = 0;
        this._touchStartTime = 0;
        this._isDragging = false;
        this._isHandleDrag = false;
        this._lastDragY = 0;

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
            <slot name="trigger"></slot>
            ${showPanel ? html`
                ${this._mobile ? html`
                    <div
                        class="backdrop"
                        data-state="${this._animState}"
                        @click="${this._onBackdropClick}"
                    ></div>
                ` : nothing}
                <div
                    id="${this._panelId}"
                    class="panel ${this._mobile ? 'tray' : ''}"
                    data-state="${this._animState}"
                    role="dialog"
                    aria-modal="true"
                    aria-label="${ifDefined(this.label || undefined)}"
                    tabindex="-1"
                    style="${this._mobile ? '' : `
                        top: ${this._position.top}px;
                        left: ${this._position.left}px;
                        transform-origin: ${this._transformOrigin};
                    `}"
                    @transitionend="${this._onTransitionEnd}"
                >
                    <span
                        class="focus-sentinel"
                        tabindex="0"
                        aria-hidden="true"
                        data-edge="start"
                        @focus="${this._onSentinelFocus}"
                    ></span>
                    ${this._mobile ? html`
                        <div class="tray-handle" aria-hidden="true">
                            <div class="tray-handle-bar"></div>
                        </div>
                    ` : nothing}
                    <slot></slot>
                    <span
                        class="focus-sentinel"
                        tabindex="0"
                        aria-hidden="true"
                        data-edge="end"
                        @focus="${this._onSentinelFocus}"
                    ></span>
                </div>
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
        this._prevFocus = document.activeElement;

        document.addEventListener('click', this._onOutsideClick, true);
        document.addEventListener('keydown', this._onKeydownGlobal);

        this._mobile = window.matchMedia('(max-width: 767px)').matches;
        const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        if (this._mobile) {
            this._lockBodyScroll();
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
        this._removeListeners();
        this._unlockBodyScroll();
        this._restoreFocus();
    }

    _restoreFocus() {
        if (this._prevFocus && typeof this._prevFocus.focus === 'function') {
            this._prevFocus.focus({ preventScroll: true });
        }
        this._prevFocus = null;
    }

    // ── Trigger ARIA ────────────────────────────────────────────

    _syncTriggerAria() {
        const trigger = this._triggerEl;
        if (!trigger) return;
        trigger.setAttribute('aria-haspopup', 'dialog');
        trigger.setAttribute('aria-expanded', String(this.open));
        if (this.open) {
            trigger.setAttribute('aria-controls', this._panelId);
        } else {
            trigger.removeAttribute('aria-controls');
        }
    }

    // ── Focus trap ──────────────────────────────────────────────

    _getFocusableElements() {
        const slot = this.shadowRoot?.querySelector('.panel slot:not([name])');
        if (!slot) return [];
        const elements = [];
        for (const node of slot.assignedElements({ flatten: true })) {
            if (node.matches?.(FOCUSABLE)) elements.push(node);
            elements.push(...node.querySelectorAll(FOCUSABLE));
        }
        return elements;
    }

    _onSentinelFocus(e) {
        const edge = e.target.dataset.edge;
        const focusable = this._getFocusableElements();
        if (focusable.length === 0) {
            // No focusable children — keep focus on the panel itself
            this.shadowRoot.querySelector('.panel')?.focus({ preventScroll: true });
            return;
        }
        if (edge === 'start') {
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
        const parts = (placement || 'bottom-center').split('-');
        const side = parts[0] === 'top' ? 'top' : 'bottom';
        const align = ['start', 'center', 'end'].includes(parts[1]) ? parts[1] : 'center';
        return [side, align];
    }

    get _triggerEl() {
        const slot = this.shadowRoot?.querySelector('slot[name="trigger"]');
        return slot?.assignedElements()[0] ?? null;
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

    // ── Outside click / keyboard ────────────────────────────────

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
            e.preventDefault();
            this._requestClose('escape');
        }
    }

    _requestClose(reason) {
        this.dispatchEvent(new CustomEvent('ol-popover-close', {
            bubbles: true, composed: true,
            detail: { reason },
        }));
    }

    // ── Mobile touch / swipe-to-dismiss ─────────────────────────

    _onTouchStart(e) {
        const handle = this.shadowRoot.querySelector('.tray-handle');
        const panel = this.shadowRoot.querySelector('.panel');
        const touch = e.touches[0];

        this._touchStartY = touch.clientY;
        this._touchStartTime = Date.now();
        this._isDragging = false;
        this._lastDragY = 0;
        this._isHandleDrag = !!(handle && e.composedPath().includes(handle));
        this._touchScrollTop = panel?.scrollTop ?? 0;
    }

    _onTouchMove(e) {
        const touch = e.touches[0];
        const deltaY = touch.clientY - this._touchStartY;

        if (!this._isDragging) {
            // Start drag if touching handle, or at scroll-top and swiping down
            if (this._isHandleDrag || (this._touchScrollTop <= 0 && deltaY > 5)) {
                this._isDragging = true;
            } else {
                return; // Let normal scroll happen
            }
        }

        const dragY = Math.max(0, deltaY);
        this._lastDragY = dragY;
        e.preventDefault();

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
        this._lastDragY = 0;

        const panel = this.shadowRoot.querySelector('.panel');
        const backdrop = this.shadowRoot.querySelector('.backdrop');

        const DISMISS_THRESHOLD = 80;
        const VELOCITY_THRESHOLD = 0.5;

        if (dragY > DISMISS_THRESHOLD || velocity > VELOCITY_THRESHOLD) {
            // Swipe dismiss — animate to off-screen, then close
            if (panel) {
                panel.style.transition = 'transform 200ms cubic-bezier(0.23, 1, 0.32, 1)';
                panel.style.transform = 'translateY(100%)';
            }
            if (backdrop) {
                backdrop.style.transition = 'opacity 200ms cubic-bezier(0.23, 1, 0.32, 1)';
                backdrop.style.opacity = '0';
            }

            const onDone = () => {
                panel?.removeEventListener('transitionend', onDone);
                this._clearDragStyles();
                this._animState = 'closed';
                this._cleanup();
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
                panel.style.transition = 'transform 200ms cubic-bezier(0.23, 1, 0.32, 1)';
                panel.style.transform = '';
            }
            if (backdrop) {
                backdrop.style.transition = 'opacity 200ms cubic-bezier(0.23, 1, 0.32, 1)';
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

    _lockBodyScroll() {
        this._savedOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
    }

    _unlockBodyScroll() {
        if (this._savedOverflow !== null) {
            document.body.style.overflow = this._savedOverflow;
            this._savedOverflow = null;
        }
    }

    // ── Listener management ─────────────────────────────────────

    _removeListeners() {
        document.removeEventListener('click', this._onOutsideClick, true);
        document.removeEventListener('keydown', this._onKeydownGlobal);
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
        this._removeListeners();
        this._unlockBodyScroll();
    }
}

customElements.define('ol-popover', OlPopover);
