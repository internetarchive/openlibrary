import { LitElement, html, css } from 'lit';
import { ifDefined } from 'lit/directives/if-defined.js';
import { findFocusableIndex, getDeepActiveElement, getTabbableFromSlot } from './utils/focus-utils.js';
import { lockBodyScroll, unlockBodyScroll } from './utils/scroll-lock.js';

/**
 * A slide-in drawer that overlays the page from a viewport edge.
 *
 * Built on native `<dialog>.showModal()`, which puts the drawer in the top
 * layer: it paints above every page stacking context without a z-index, its
 * containing block is always the viewport (so a transformed ancestor can't
 * displace it), and the rest of the document is inerted for assistive tech —
 * which is what makes the `aria-modal` claim honest. See the overlay table in
 * `docs/ai/web-components.md`.
 *
 * The `<dialog>` itself fills the viewport and is transparent; the scrim and
 * the sliding panel are ordinary children of it. That costs one extra element
 * over `::backdrop`, and buys the ability to drive scrim opacity directly from
 * the swipe gesture — a pseudo-element takes no inline style.
 *
 * Content is projected via the default slot (light DOM), so it can be
 * server-rendered and styled with your existing stylesheets.
 *
 * @element ol-drawer
 *
 * @prop {Boolean} open - Whether the drawer is currently visible.
 * @prop {'start' | 'end'} placement - Which edge the drawer slides from:
 *     `'start'` (left in LTR) or `'end'` (right in LTR). Default: `'end'`
 * @prop {String} label - Accessible label for the drawer dialog.
 * @prop {Boolean} closeOnScrimClick - Whether clicking the scrim closes the
 *     drawer. Default `true`. Attribute: `close-on-scrim-click`.
 * @prop {Boolean} closeOnEscape - Whether Escape closes the drawer. Default
 *     `true`. Attribute: `close-on-escape`.
 *
 * @cssprop [--ol-drawer-width=300px] - Width of the drawer panel.
 * @cssprop [--ol-drawer-scrim-color=var(--overlay-backdrop-color)] - Scrim color.
 * @cssprop [--ol-drawer-scrim-blur=var(--overlay-backdrop-blur)] - Blur radius
 *     applied to the page behind the scrim. The drawer is modal, so it blurs;
 *     see docs/ai/design.md#blur-follows-modality-not-viewport-width.
 * @cssprop [--ol-drawer-enter-duration=var(--duration-slower)] - Slide-in duration.
 * @cssprop [--ol-drawer-exit-duration=var(--duration-slow)] - Slide-out duration.
 * @cssprop [--ol-drawer-scroll-padding=0] - Inset kept clear when Tab scrolls a
 *     focused element into view, for drawers with a sticky header or footer.
 *
 * @fires ol-drawer-show - Fired when the drawer begins opening.
 * @fires ol-drawer-after-show - Fired after the enter transition completes.
 * @fires ol-drawer-hide - Fired when a close is requested, before the exit
 *     transition. Cancelable — `event.preventDefault()` keeps the drawer open.
 *     detail: { reason: 'escape' | 'scrim' | 'swipe' | 'programmatic' }
 * @fires ol-drawer-after-hide - Fired after the exit transition completes.
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
        placement: { type: String, reflect: true },
        label: { type: String },
        closeOnScrimClick: { type: Boolean, attribute: 'close-on-scrim-click' },
        closeOnEscape: { type: Boolean, attribute: 'close-on-escape' },
    };

    static styles = css`
        :host {
            --ol-drawer-width: 300px;
            --ol-drawer-scrim-color: var(--overlay-backdrop-color);
            --ol-drawer-scrim-blur: var(--overlay-backdrop-blur);
            --ol-drawer-enter-duration: var(--duration-slower);
            --ol-drawer-exit-duration: var(--duration-slow);
            --ol-drawer-easing: var(--ease-enter);
            --ol-drawer-scroll-padding: 0;

            display: contents;
        }

        /* The UA stylesheet gives <dialog> fit-content sizing, a max-width, a
           border, padding, auto margins and an opaque background. Author styles
           only win for properties they actually declare, so every one of them
           is restated here — an undeclared width alone would collapse the
           viewport-filling box back to the panel's width. Sizing via auto plus
           inset: 0 (rather than 100vw/100dvh) matches the viewport exactly,
           with no scrollbar-width rounding to reason about. */
        dialog {
            position: fixed;
            inset: 0;
            width: auto;
            height: auto;
            max-width: none;
            max-height: none;
            margin: 0;
            padding: 0;
            border: none;
            background: transparent;
            /* Clips the panel while it sits off-screen. Must be clip, not
               hidden: hidden still creates a scroll container, and a panel
               parked at translateX(100%) sits in its scrollable overflow. Any
               focus inside that panel then scrolls the dialog by the panel's
               width to reveal it, and that offset fights the slide — the drawer
               appears already open, overshoots, then snaps back. Only end
               placement showed it; overflow to the left of the origin isn't
               scrollable, so start was always smooth. clip clips without ever
               becoming scrollable. */
            overflow: hidden;
            overflow: clip;
        }

        dialog:focus {
            outline: none;
        }

        /* The scrim below is the visible dimming layer; the native backdrop
           would sit underneath the viewport-filling dialog and never show. */
        dialog::backdrop {
            background: transparent;
        }

        /* ── Scrim ── */

        /* Same scrim as ol-dialog and the ol-popover tray: the drawer is
           modal, so it blurs. The blur is what lets the dim stay light — 32%
           over a page of covers still reads as content; blurred, it doesn't.
           Declared constant and carried by opacity, never animated as a
           radius: this layer is viewport-sized and the slide runs --duration-slower. */
        .scrim {
            position: absolute;
            inset: 0;
            background: var(--ol-drawer-scrim-color);
            opacity: 0;
            backdrop-filter: blur(var(--ol-drawer-scrim-blur));
            -webkit-backdrop-filter: blur(var(--ol-drawer-scrim-blur));
            transition: opacity var(--ol-drawer-exit-duration) var(--ol-drawer-easing);
        }

        .scrim.is-open {
            opacity: 1;
            transition-duration: var(--ol-drawer-enter-duration);
        }

        /* ── Panel ── */

        /* Only ever focused programmatically, as the empty-drawer fallback. */
        .panel:focus {
            outline: none;
        }

        .panel {
            position: absolute;
            top: 0;
            bottom: 0;
            width: var(--ol-drawer-width);
            max-width: 100%;
            background: var(--color-surface-header);
            overflow-y: auto;
            /* Keeps a Tab stop scrolled into view clear of any sticky header or
               footer the consumer slots in; the panel is shadow DOM, so this
               inset is only reachable through the custom property. */
            scroll-padding-block: var(--ol-drawer-scroll-padding);
            overscroll-behavior: contain;
            -webkit-overflow-scrolling: touch;
            transition: transform var(--ol-drawer-exit-duration) var(--ol-drawer-easing);
            /* Placement only swaps this offset and the edge it pins to, so
               transform is declared exactly once per state. Setting the closed
               transform on the :host([placement]) rules instead would
               out-specify .panel.is-open and the panel would never slide in. */
            transform: translateX(var(--_ol-drawer-closed-x));
        }

        .panel.is-open {
            transform: translateX(0);
            transition-duration: var(--ol-drawer-enter-duration);
        }

        :host(:not([placement="start"])) .panel {
            --_ol-drawer-closed-x: 100%;
            right: 0;
            box-shadow: var(--box-shadow-overlay);
        }

        :host([placement="start"]) .panel {
            --_ol-drawer-closed-x: -100%;
            left: 0;
            box-shadow: var(--box-shadow-overlay);
        }

        /* Resolved transition-duration is what drives the JS lifecycle, so
           zeroing it here is enough — no matchMedia check in the component. */
        @media (prefers-reduced-motion: reduce) {
            .scrim,
            .scrim.is-open,
            .panel,
            .panel.is-open {
                transition: none;
            }
        }
    `;

    constructor() {
        super();
        this.open = false;
        this.placement = 'end';
        this.label = '';
        this.closeOnScrimClick = true;
        this.closeOnEscape = true;

        /** @type {HTMLElement|null} Element that had focus before the drawer opened */
        this._previouslyFocusedElement = null;

        /** @type {boolean} Whether this drawer currently holds a body scroll lock */
        this._scrollLocked = false;

        /**
         * Reason carried by the next `ol-drawer-hide`. Set by the dismiss
         * handlers just before they flip `open`; a bare `drawer.open = false`
         * leaves it at the default.
         * @type {String}
         */
        this._closeReason = 'programmatic';

        /**
         * Bumped on every open and close. A pending transition callback from a
         * superseded cycle checks this and bows out, so a fast open→close can't
         * fire `ol-drawer-after-show` for a drawer that's already closing.
         */
        this._cycle = 0;

        // Touch drag state (horizontal swipe-to-dismiss)
        this._touchStartX = 0;
        this._touchStartY = 0;
        this._touchStartTime = 0;
        this._isDragging = false;
        this._dragBlocked = false;
        this._lastDragX = 0;

        this._handleCancel = this._handleCancel.bind(this);
        this._handleKeyDown = this._handleKeyDown.bind(this);
        this._onTouchStart = this._onTouchStart.bind(this);
        this._onTouchMove = this._onTouchMove.bind(this);
        this._onTouchEnd = this._onTouchEnd.bind(this);
    }

    render() {
        return html`
            <dialog
                role="dialog"
                aria-modal="true"
                aria-label=${ifDefined(this.label || undefined)}
                @cancel=${this._handleCancel}
            >
                <div class="scrim" @click=${this._handleScrimClick}></div>
                <!-- tabindex so an empty drawer still has somewhere to put focus. -->
                <div class="panel" tabindex="-1">
                    <slot></slot>
                </div>
            </dialog>
        `;
    }

    /** @returns {HTMLDialogElement} */
    get dialog() {
        return this.renderRoot?.querySelector('dialog');
    }

    /** @returns {HTMLElement} */
    get _panel() {
        return this.renderRoot?.querySelector('.panel');
    }

    /** @returns {HTMLElement} */
    get _scrim() {
        return this.renderRoot?.querySelector('.scrim');
    }

    updated(changedProperties) {
        if (changedProperties.has('open')) {
            if (this.open) {
                this._openDrawer();
            } else if (changedProperties.get('open') === true) {
                this._closeDrawer();
            }
        }
    }

    // ── Show / Hide ─────────────────────────────────────────────

    _openDrawer() {
        const dialog = this.dialog;
        if (!dialog) return;

        // The only way in here with an already-open dialog is a reopen during
        // the exit transition — `showModal()` is still in effect and the close
        // callback is still queued. Bumping the cycle below cancels it; the
        // rest of the entry is idempotent, so it just runs again.
        const reopening = dialog.open;

        if (!reopening) {
            // document.activeElement doesn't pass into shadow DOM
            this._previouslyFocusedElement = getDeepActiveElement();
        }
        const cycle = ++this._cycle;

        this.dispatchEvent(new CustomEvent('ol-drawer-show', {
            bubbles: true, composed: true,
        }));

        // Calling showModal() on an open dialog throws.
        if (!reopening) dialog.showModal();

        // showModal() blocks background scroll on desktop but not touch-scroll
        // on iOS Safari, so pin <body> as well. The lock reserves the scrollbar
        // width, so nothing shifts on platforms with classic scrollbars.
        if (!this._scrollLocked) {
            lockBodyScroll();
            this._scrollLocked = true;
        }

        const panel = this._panel;
        panel.addEventListener('touchstart', this._onTouchStart, { passive: true });
        panel.addEventListener('touchmove', this._onTouchMove, { passive: false });
        panel.addEventListener('touchend', this._onTouchEnd, { passive: true });

        // Capture phase to intercept Tab before Safari's native handling.
        document.addEventListener('keydown', this._handleKeyDown, true);

        // Flush style so the panel paints at its off-screen start position
        // before `.is-open` arms the slide; without this the browser coalesces
        // both into one style pass and there's nothing to transition from.
        panel.getBoundingClientRect();
        panel.classList.add('is-open');
        this._scrim.classList.add('is-open');

        this._setInitialFocus();

        // Fallback for engines without `overflow: clip` (Safari < 16), where the
        // dialog is still a scroll container and focusing into the off-screen
        // panel scrolls it. Same synchronous block as the focus calls above, so
        // nothing paints in between. A no-op wherever `clip` applies.
        dialog.scrollLeft = 0;

        this._afterTransition(panel, () => {
            if (cycle !== this._cycle) return;
            this.dispatchEvent(new CustomEvent('ol-drawer-after-show', {
                bubbles: true, composed: true,
            }));
        });
    }

    /**
     * Lands initial focus on the same element the Tab trap treats as the first
     * stop, using the shadow-piercing list so a slotted custom element whose
     * real focusable lives in its shadow root is found. `showModal()` has
     * already focused something by this point; this refines that choice.
     *
     * Runs synchronously rather than in a `requestAnimationFrame`: the dialog
     * is displayed and laid out by the time `showModal()` returns, so there is
     * nothing to wait for — and rAF is paused in a hidden or occluded tab,
     * which would strand focus on the dialog itself.
     */
    _setInitialFocus() {
        const dialog = this.dialog;
        if (!dialog?.open) return;

        const autofocusEl = this.querySelector('[autofocus]');
        if (autofocusEl) {
            autofocusEl.focus({ preventScroll: true });
            return;
        }

        const firstFocusable = this._getFocusableElements()[0];
        (firstFocusable || this._panel).focus({ preventScroll: true });
    }

    _closeDrawer() {
        const dialog = this.dialog;
        if (!dialog || !dialog.open) return;

        const reason = this._closeReason;
        this._closeReason = 'programmatic';

        const hideEvent = new CustomEvent('ol-drawer-hide', {
            bubbles: true, composed: true, cancelable: true,
            detail: { reason },
        });
        this.dispatchEvent(hideEvent);

        if (hideEvent.defaultPrevented) {
            this.open = true;
            return;
        }

        const cycle = ++this._cycle;
        document.removeEventListener('keydown', this._handleKeyDown, true);

        const panel = this._panel;
        // Dropping the drag styles in the same pass as `.is-open` lets the exit
        // transition run from wherever the finger left the panel.
        this._clearDragStyles();
        panel.classList.remove('is-open');
        this._scrim.classList.remove('is-open');

        this._afterTransition(panel, () => {
            if (cycle !== this._cycle) return;
            this._removeTouchListeners();
            dialog.close();
            this._releaseScrollLock();
            this._restoreFocus();
            this.dispatchEvent(new CustomEvent('ol-drawer-after-hide', {
                bubbles: true, composed: true,
            }));
        });
    }

    /**
     * Runs `done` once `el`'s current transform transition finishes.
     *
     * Under `prefers-reduced-motion: reduce` the stylesheet sets
     * `transition: none`, and an element with no transition never dispatches
     * `transitionend` — a naive listener would leave the drawer stuck open,
     * never calling `dialog.close()` or restoring focus. Read the resolved
     * duration instead: 0 runs `done` immediately, otherwise wait on
     * `transitionend` with a timer fallback in case the event is dropped
     * (e.g. a backgrounded tab).
     *
     * @param {HTMLElement} el
     * @param {() => void} done
     */
    _afterTransition(el, done) {
        const durationMs = this._transitionDurationMs(el);
        if (durationMs <= 0) {
            done();
            return;
        }

        let finished = false;
        const finish = () => {
            if (finished) return;
            finished = true;
            clearTimeout(timer);
            el.removeEventListener('transitionend', onEnd);
            done();
        };
        const onEnd = (event) => {
            // Slotted content sits inside the panel and its own transitions
            // bubble through — only the panel's transform marks the slide's end.
            if (event.target !== el || event.propertyName !== 'transform') return;
            finish();
        };
        const timer = setTimeout(finish, durationMs + 50);
        el.addEventListener('transitionend', onEnd);
    }

    /**
     * `el`'s resolved transition-duration in milliseconds (first value of the
     * list). Returns 0 when no transition is set (e.g. reduced motion).
     * @param {HTMLElement} el
     * @returns {Number}
     */
    _transitionDurationMs(el) {
        const raw = getComputedStyle(el).transitionDuration.split(',')[0].trim();
        if (raw.endsWith('ms')) return parseFloat(raw) || 0;
        if (raw.endsWith('s')) return (parseFloat(raw) || 0) * 1000;
        return 0;
    }

    // ── Cleanup ─────────────────────────────────────────────────

    /** Releases the body scroll lock if this drawer holds one. Idempotent. */
    _releaseScrollLock() {
        if (this._scrollLocked) {
            unlockBodyScroll();
            this._scrollLocked = false;
        }
    }

    _restoreFocus() {
        if (this._previouslyFocusedElement && typeof this._previouslyFocusedElement.focus === 'function') {
            // setTimeout so focus lands after the dialog is fully closed.
            setTimeout(() => {
                this._previouslyFocusedElement?.focus({ preventScroll: true });
                this._previouslyFocusedElement = null;
            }, 0);
        }
    }

    _removeTouchListeners() {
        const panel = this._panel;
        if (!panel) return;
        panel.removeEventListener('touchstart', this._onTouchStart);
        panel.removeEventListener('touchmove', this._onTouchMove);
        panel.removeEventListener('touchend', this._onTouchEnd);
    }

    // ── Focus trap ──────────────────────────────────────────────

    /**
     * Tab stops slotted into the drawer, in DOM order. Filtered to
     * currently-rendered elements by {@link getTabbableFromSlot}.
     * @returns {HTMLElement[]}
     */
    _getFocusableElements() {
        return getTabbableFromSlot(this.renderRoot?.querySelector('.panel slot:not([name])'));
    }

    /**
     * Manual Tab focus trap. `showModal()` inerts the background, but Safari
     * still doesn't cycle focus across shadow DOM boundaries for slotted
     * content, so the ordering is ours to enforce.
     */
    _handleKeyDown(event) {
        if (event.key !== 'Tab') return;

        const activeElement = getDeepActiveElement();

        // A nested open overlay (e.g. an <ol-popover> opened from inside the
        // drawer) owns its own trap — intercepting Tab here would yank focus
        // back out of it.
        if (this._isInsideOpenOverlay(activeElement)) return;

        const focusable = this._getFocusableElements();
        if (focusable.length === 0) return;

        event.preventDefault();

        // findFocusableIndex climbs shadow boundaries so a slotted custom
        // element that delegates focus inward still matches its trap entry.
        const currentIndex = findFocusableIndex(focusable, activeElement);

        let nextIndex;
        if (event.shiftKey) {
            nextIndex = currentIndex <= 0 ? focusable.length - 1 : currentIndex - 1;
        } else {
            nextIndex = currentIndex >= focusable.length - 1 ? 0 : currentIndex + 1;
        }

        // Scroll deliberately rather than letting focus() do it: focus scrolls
        // every ancestor, which is the off-screen-panel bug `overflow: clip`
        // guards against. `nearest` moves only the panel's own scroller, and
        // only when the target isn't already visible.
        const next = focusable[nextIndex];
        next.focus({ preventScroll: true });
        next.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    }

    /**
     * Whether `el` sits inside an open overlay nested within this drawer.
     * @param {Element|null} el
     * @returns {Boolean}
     */
    _isInsideOpenOverlay(el) {
        let cur = el;
        while (cur && cur !== this.dialog) {
            // ol-popover reflects `open` to its attribute (see OlPopover.js).
            // Matched by tagName to avoid an import-time coupling to the class.
            if (cur.tagName === 'OL-POPOVER' && cur.hasAttribute('open')) {
                return true;
            }
            const parent = cur.parentNode;
            cur = (parent?.nodeType === Node.DOCUMENT_FRAGMENT_NODE && parent.host)
                ? parent.host
                : cur.parentElement;
        }
        return false;
    }

    // ── Dismiss handlers ────────────────────────────────────────

    /** Native dialog cancel event (Escape key). */
    _handleCancel(event) {
        // Prevent the native close so we can animate the exit.
        event.preventDefault();

        if (this.closeOnEscape) {
            this._requestClose('escape');
        }
    }

    _handleScrimClick() {
        if (!this.closeOnScrimClick) return;
        this._requestClose('scrim');
    }

    /** @param {String} reason */
    _requestClose(reason) {
        this._closeReason = reason;
        this.open = false;
    }

    // ── Touch / swipe-to-dismiss ────────────────────────────────

    /** @returns {number} 1 for end placement (swipe right to dismiss), -1 for start (swipe left) */
    get _dismissDirection() {
        return this.placement === 'start' ? -1 : 1;
    }

    _onTouchStart(e) {
        const touch = e.touches[0];
        this._touchStartX = touch.clientX;
        this._touchStartY = touch.clientY;
        this._touchStartTime = Date.now();
        this._isDragging = false;
        this._dragBlocked = false;
        this._lastDragX = 0;
    }

    _onTouchMove(e) {
        if (this._dragBlocked) return;

        const touch = e.touches[0];
        // Only drag in the dismiss direction
        const delta = (touch.clientX - this._touchStartX) * this._dismissDirection;
        const deltaY = touch.clientY - this._touchStartY;

        if (!this._isDragging) {
            // Axis lock: a gesture that reads as a vertical scroll belongs to
            // the panel's own scroller for the rest of the touch. Without this,
            // sideways drift mid-scroll starts a drag the browser won't let us
            // cancel, and every preventDefault() logs a console intervention.
            if (Math.abs(deltaY) > Math.abs(delta)) {
                this._dragBlocked = true;
                return;
            }
            // Require 5px in the dismiss direction to start dragging
            if (delta <= 5) return;
            // Scrolling already underway — the gesture is no longer ours.
            if (!e.cancelable) {
                this._dragBlocked = true;
                return;
            }
            this._isDragging = true;
        }

        const dragX = Math.max(0, delta);
        this._lastDragX = dragX;
        if (e.cancelable) e.preventDefault();

        const panel = this._panel;
        panel.style.transition = 'none';
        panel.style.transform = `translateX(${dragX * this._dismissDirection}px)`;

        const scrim = this._scrim;
        const progress = Math.min(dragX / (panel.offsetWidth || 1), 1);
        scrim.style.transition = 'none';
        scrim.style.opacity = String(1 - progress);
    }

    _onTouchEnd() {
        if (!this._isDragging) return;

        const dragX = this._lastDragX;
        const velocity = dragX / Math.max(Date.now() - this._touchStartTime, 1);

        this._isDragging = false;
        this._dragBlocked = false;
        this._lastDragX = 0;

        const DISMISS_THRESHOLD = 80;
        const VELOCITY_THRESHOLD = 0.5;

        if (dragX > DISMISS_THRESHOLD || velocity > VELOCITY_THRESHOLD) {
            // _closeDrawer() drops the drag styles, so the exit transition
            // picks up from where the finger left off.
            this._requestClose('swipe');
        } else {
            // Snap back: clearing the inline styles hands the panel back to
            // `.is-open`, which transitions it home.
            this._clearDragStyles();
        }
    }

    _clearDragStyles() {
        const panel = this._panel;
        if (panel) {
            panel.style.transition = '';
            panel.style.transform = '';
        }
        const scrim = this._scrim;
        if (scrim) {
            scrim.style.transition = '';
            scrim.style.opacity = '';
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('keydown', this._handleKeyDown, true);
        this._removeTouchListeners();
        // Safety net: if torn down while still open, don't leave the body pinned.
        this._releaseScrollLock();
    }
}

if (!customElements.get('ol-drawer')) {
    customElements.define('ol-drawer', OlDrawer);
}
