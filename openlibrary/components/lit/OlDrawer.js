import { LitElement, html, css, nothing } from 'lit';
import { ifDefined } from 'lit/directives/if-defined.js';
import { findFocusableIndex, getDeepActiveElement, getFocusableFromSlot } from './utils/focus-utils.js';
import { lockBodyScroll, unlockBodyScroll } from './utils/scroll-lock.js';

/**
 * A slide-in drawer component that overlays the page from a viewport edge.
 *
 * The drawer uses `position: fixed` to cover the full viewport, independent
 * of its position in the DOM tree. It traps focus while open, locks body
 * scroll, and supports swipe-to-dismiss on touch devices.
 *
 * Place the element near the document root to avoid stacking-context issues.
 * Content is projected via the default slot (light DOM), so it can be
 * server-rendered and styled with your existing stylesheets.
 *
 * @element ol-drawer
 *
 * @prop {Boolean} open - Whether the drawer is currently visible.
 * @prop {String} placement - Which edge the drawer slides from:
 *     `'start'` (left in LTR) or `'end'` (right in LTR). Default: `'end'`
 * @prop {String} label - Accessible label for the drawer dialog.
 *
 * @cssprop [--ol-drawer-width=300px] - Width of the drawer panel.
 * @cssprop [--ol-drawer-backdrop-color=hsla(0, 0%, 0%, 0.5)] - Backdrop scrim color.
 * @cssprop [--ol-drawer-enter-duration=400ms] - Slide-in animation duration.
 * @cssprop [--ol-drawer-exit-duration=300ms] - Slide-out animation duration.
 *
 * @fires ol-drawer-show - Fired when the drawer begins opening.
 * @fires ol-drawer-after-show - Fired after the enter animation completes.
 * @fires ol-drawer-hide - Fired when a close is requested.
 *     detail: { reason: 'escape' | 'backdrop' | 'swipe' }
 * @fires ol-drawer-after-hide - Fired after the exit animation completes.
 *
 * @slot - Default slot for drawer content.
 *
 * @example
 * <ol-drawer label="Menu" placement="end">
 *   <nav>
 *     <a href="/home">Home</a>
 *     <a href="/about">About</a>
 *   </nav>
 * </ol-drawer>
 *
 * <script>
 *   document.querySelector('ol-drawer').open = true;
 * </script>
 */
export class OlDrawer extends LitElement {
    static properties = {
        open: { type: Boolean, reflect: true },
        placement: { type: String },
        label: { type: String },
        _animState: { state: true },
    };

    // Animation states: closed → preparing → entering → open → exiting → closed

    static styles = css`
        :host {
            --ol-drawer-width: 300px;
            --ol-drawer-backdrop-color: hsla(0, 0%, 0%, 0.5);
            --ol-drawer-enter-duration: 400ms;
            --ol-drawer-exit-duration: 300ms;

            display: contents;
        }

        /* ── Backdrop ── */

        .backdrop {
            position: fixed;
            inset: 0;
            z-index: var(--z-index-modal);
            background: var(--ol-drawer-backdrop-color);
            opacity: 0;
            pointer-events: none;
        }

        .backdrop[data-state="entering"],
        .backdrop[data-state="open"] {
            opacity: 1;
            pointer-events: auto;
        }

        .backdrop[data-state="entering"] {
            transition: opacity var(--ol-drawer-enter-duration) cubic-bezier(0.23, 1, 0.32, 1);
        }

        .backdrop[data-state="exiting"] {
            opacity: 0;
            pointer-events: none;
            transition: opacity var(--ol-drawer-exit-duration) cubic-bezier(0.23, 1, 0.32, 1);
        }

        /* ── Drawer panel ── */

        .drawer {
            position: fixed;
            top: 0;
            bottom: 0;
            width: var(--ol-drawer-width);
            max-width: 100vw;
            z-index: var(--z-index-modal);
            background: var(--light-beige);
            overflow-y: auto;
            overscroll-behavior: contain;
            -webkit-overflow-scrolling: touch;
            pointer-events: none;
        }

        .drawer--end {
            right: 0;
            box-shadow: -10px 0 10px -6px var(--boxshadow-black);
            transform: translateX(100%);
        }

        .drawer--start {
            left: 0;
            box-shadow: 10px 0 10px -6px var(--boxshadow-black);
            transform: translateX(-100%);
        }

        .drawer[data-state="preparing"] {
            will-change: transform;
        }

        .drawer[data-state="entering"],
        .drawer[data-state="open"] {
            transform: translateX(0);
            pointer-events: auto;
        }

        .drawer[data-state="open"] {
            will-change: auto;
        }

        .drawer[data-state="entering"] {
            transition: transform var(--ol-drawer-enter-duration) cubic-bezier(0.23, 1, 0.32, 1);
            will-change: transform;
        }

        .drawer[data-state="exiting"] {
            pointer-events: none;
            transition: transform var(--ol-drawer-exit-duration) cubic-bezier(0.23, 1, 0.32, 1);
            will-change: transform;
        }

        .drawer--end[data-state="exiting"] {
            transform: translateX(100%);
        }

        .drawer--start[data-state="exiting"] {
            transform: translateX(-100%);
        }

        @media (prefers-reduced-motion: reduce) {
            .drawer[data-state="entering"],
            .drawer[data-state="exiting"],
            .backdrop[data-state="entering"],
            .backdrop[data-state="exiting"] {
                transition: none;
            }
        }
    `;

    constructor() {
        super();
        this.open = false;
        this.placement = 'end';
        this.label = '';
        this._animState = 'closed';
        this._prevFocus = null;

        /** @type {boolean} Whether this drawer currently holds a body scroll lock */
        this._scrollLocked = false;

        // Touch drag state (horizontal swipe-to-dismiss)
        this._touchStartX = 0;
        this._touchStartTime = 0;
        this._isDragging = false;
        this._lastDragX = 0;

        this._onKeydown = this._onKeydown.bind(this);
        this._onTouchStart = this._onTouchStart.bind(this);
        this._onTouchMove = this._onTouchMove.bind(this);
        this._onTouchEnd = this._onTouchEnd.bind(this);
    }

    render() {
        const show = this._animState !== 'closed';
        const placementClass = this.placement === 'start' ? 'drawer--start' : 'drawer--end';

        return html`
            ${show ? html`
                <div
                    class="backdrop"
                    data-state="${this._animState}"
                    @click="${this._onBackdropClick}"
                ></div>
                <div
                    class="drawer ${placementClass}"
                    data-state="${this._animState}"
                    role="dialog"
                    aria-modal="true"
                    aria-label="${ifDefined(this.label || undefined)}"
                    tabindex="-1"
                    @transitionend="${this._onTransitionEnd}"
                >
                    <slot></slot>
                </div>
            ` : nothing}
        `;
    }

    updated(changed) {
        if (changed.has('open')) {
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
        if (!this._scrollLocked) {
            lockBodyScroll();
            this._scrollLocked = true;
        }

        // Capture phase to intercept Tab before the browser's native handling.
        document.addEventListener('keydown', this._onKeydown, true);

        const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        this._animState = reducedMotion ? 'open' : 'preparing';

        this.dispatchEvent(new CustomEvent('ol-drawer-show', {
            bubbles: true, composed: true,
        }));

        this.updateComplete.then(() => {
            const panel = this.shadowRoot.querySelector('.drawer');
            if (!panel) return;

            // Add touch listeners for swipe-to-dismiss
            panel.addEventListener('touchstart', this._onTouchStart, { passive: true });
            panel.addEventListener('touchmove', this._onTouchMove, { passive: false });
            panel.addEventListener('touchend', this._onTouchEnd, { passive: true });

            // Focus the first focusable slotted element, or the panel as fallback
            const focusable = this._getFocusableElements();
            const target = focusable.length > 0 ? focusable[0] : panel;
            target.focus({ preventScroll: true });

            if (reducedMotion) {
                this.dispatchEvent(new CustomEvent('ol-drawer-after-show', {
                    bubbles: true, composed: true,
                }));
                return;
            }

            // Force reflow so the browser paints the start position
            panel.getBoundingClientRect();
            this._animState = 'entering';
        });
    }

    _hide() {
        if (this._animState === 'closed') return;

        const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (reducedMotion) {
            this._animState = 'closed';
            this._cleanup();
            this.dispatchEvent(new CustomEvent('ol-drawer-after-hide', {
                bubbles: true, composed: true,
            }));
            return;
        }

        this._animState = 'exiting';
    }

    _onTransitionEnd(e) {
        if (e.target !== e.currentTarget) return;

        if (this._animState === 'entering') {
            this._animState = 'open';
            this.dispatchEvent(new CustomEvent('ol-drawer-after-show', {
                bubbles: true, composed: true,
            }));
        } else if (this._animState === 'exiting') {
            this._animState = 'closed';
            this._cleanup();
            this.dispatchEvent(new CustomEvent('ol-drawer-after-hide', {
                bubbles: true, composed: true,
            }));
        }
    }

    // ── Cleanup ─────────────────────────────────────────────────

    _cleanup() {
        this._removeListeners();
        this._releaseScrollLock();
        this._restoreFocus();
    }

    /** Releases the body scroll lock if this drawer holds one. Idempotent. */
    _releaseScrollLock() {
        if (this._scrollLocked) {
            unlockBodyScroll();
            this._scrollLocked = false;
        }
    }

    _restoreFocus() {
        if (this._prevFocus && typeof this._prevFocus.focus === 'function') {
            this._prevFocus.focus({ preventScroll: true });
        }
        this._prevFocus = null;
    }

    // ── Focus trap ──────────────────────────────────────────────

    /**
     * Focusable elements slotted into the drawer, in DOM order. Filtered to
     * currently-rendered elements by {@link getFocusableFromSlot}.
     * @returns {HTMLElement[]}
     */
    _getFocusableElements() {
        return getFocusableFromSlot(this.shadowRoot?.querySelector('.drawer slot:not([name])'));
    }

    /**
     * Handles Escape (dismiss) and Tab (manual focus trap). A manual trap is
     * needed because Safari doesn't trap focus across shadow DOM boundaries
     * for slotted content.
     */
    _onKeydown(e) {
        if (e.key === 'Escape' && this.open) {
            e.preventDefault();
            this._requestClose('escape');
            return;
        }

        if (e.key !== 'Tab') return;

        const focusable = this._getFocusableElements();
        if (focusable.length === 0) return;

        e.preventDefault();

        // findFocusableIndex climbs shadow boundaries so a slotted custom
        // element that delegates focus inward still matches its trap entry.
        const currentIndex = findFocusableIndex(focusable, getDeepActiveElement());

        let nextIndex;
        if (e.shiftKey) {
            nextIndex = currentIndex <= 0 ? focusable.length - 1 : currentIndex - 1;
        } else {
            nextIndex = currentIndex >= focusable.length - 1 ? 0 : currentIndex + 1;
        }

        focusable[nextIndex].focus({ preventScroll: true });
    }

    // ── Dismiss handlers ────────────────────────────────────────

    _onBackdropClick() {
        this._requestClose('backdrop');
    }

    _requestClose(reason) {
        this.open = false;
        this.dispatchEvent(new CustomEvent('ol-drawer-hide', {
            bubbles: true, composed: true,
            detail: { reason },
        }));
    }

    // ── Touch / swipe-to-dismiss ────────────────────────────────

    /** @returns {number} 1 for end placement (swipe right to dismiss), -1 for start (swipe left) */
    get _dismissDirection() {
        return this.placement === 'start' ? -1 : 1;
    }

    _onTouchStart(e) {
        const touch = e.touches[0];
        this._touchStartX = touch.clientX;
        this._touchStartTime = Date.now();
        this._isDragging = false;
        this._lastDragX = 0;
    }

    _onTouchMove(e) {
        const touch = e.touches[0];
        const rawDelta = touch.clientX - this._touchStartX;
        // Only drag in the dismiss direction
        const delta = rawDelta * this._dismissDirection;

        if (!this._isDragging) {
            // Require 5px in the dismiss direction to start dragging
            if (delta > 5) {
                this._isDragging = true;
            } else {
                return;
            }
        }

        const dragX = Math.max(0, delta);
        this._lastDragX = dragX;
        e.preventDefault();

        const panel = this.shadowRoot.querySelector('.drawer');
        if (panel) {
            const translateX = dragX * this._dismissDirection;
            panel.style.transform = `translateX(${translateX}px)`;
            panel.style.transition = 'none';
        }

        const backdrop = this.shadowRoot.querySelector('.backdrop');
        if (backdrop) {
            const panelWidth = panel ? panel.offsetWidth : 300;
            const progress = Math.min(dragX / panelWidth, 1);
            backdrop.style.opacity = String(1 - progress);
            backdrop.style.transition = 'none';
        }
    }

    _onTouchEnd() {
        if (!this._isDragging) return;

        const dragX = this._lastDragX;
        const elapsed = Date.now() - this._touchStartTime;
        const velocity = dragX / Math.max(elapsed, 1);

        this._isDragging = false;
        this._lastDragX = 0;

        const panel = this.shadowRoot.querySelector('.drawer');
        const backdrop = this.shadowRoot.querySelector('.backdrop');

        const DISMISS_THRESHOLD = 80;
        const VELOCITY_THRESHOLD = 0.5;

        if (dragX > DISMISS_THRESHOLD || velocity > VELOCITY_THRESHOLD) {
            // Swipe dismiss — animate off-screen, then close
            if (panel) {
                const offscreen = this.placement === 'start' ? '-100%' : '100%';
                panel.style.transition = 'transform 200ms cubic-bezier(0.23, 1, 0.32, 1)';
                panel.style.transform = `translateX(${offscreen})`;
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
                this.open = false;
                this.dispatchEvent(new CustomEvent('ol-drawer-hide', {
                    bubbles: true, composed: true,
                    detail: { reason: 'swipe' },
                }));
                this.dispatchEvent(new CustomEvent('ol-drawer-after-hide', {
                    bubbles: true, composed: true,
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
        const panel = this.shadowRoot?.querySelector('.drawer');
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

    // ── Listener management ─────────────────────────────────────

    _removeListeners() {
        document.removeEventListener('keydown', this._onKeydown, true);

        const panel = this.shadowRoot?.querySelector('.drawer');
        if (panel) {
            panel.removeEventListener('touchstart', this._onTouchStart);
            panel.removeEventListener('touchmove', this._onTouchMove);
            panel.removeEventListener('touchend', this._onTouchEnd);
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._removeListeners();
        // Safety net: if torn down while still open, don't leave the body pinned.
        this._releaseScrollLock();
    }
}

if (!customElements.get('ol-drawer')) {
    customElements.define('ol-drawer', OlDrawer);
}
