import { LitElement, html, css, nothing } from 'lit';

/**
 * A tooltip component that displays contextual information on hover/focus.
 *
 * Wraps a trigger element and shows a tooltip panel with configurable placement,
 * delay, and arrow. Supports "warm" behavior — moving between multiple tooltips
 * skips the show delay after the first one, so scanning a toolbar feels instant.
 *
 * @element ol-tooltip
 *
 * @prop {String} content - Text content of the tooltip
 * @prop {String} placement - Preferred placement relative to the trigger.
 *     Format: "{side}" or "{side}-{align}" where side is "top", "bottom",
 *     "left", or "right" and align is "start", "center", or "end".
 *     Default: "top"
 * @prop {Number} showDelay - Milliseconds to wait before showing (default: 150).
 *     Skipped when moving between tooltips quickly ("warm" mode).
 * @prop {Number} hideDelay - Milliseconds to wait before hiding (default: 0)
 * @prop {Number} offset - Gap in px between trigger and tooltip (default: 8)
 * @prop {Boolean} withoutArrow - Hides the directional arrow
 * @prop {Boolean} disabled - Prevents the tooltip from showing
 *
 * @fires ol-tooltip-show - Fired when the tooltip opens
 * @fires ol-tooltip-hide - Fired when the tooltip closes
 *
 * @slot - The trigger element (button, icon, link, etc.)
 * @slot content - Optional rich HTML tooltip content (overrides the content attribute)
 *
 * @example
 * <ol-tooltip content="Edit this item">
 *   <button>Edit</button>
 * </ol-tooltip>
 *
 * @example
 * <ol-tooltip placement="bottom-start" show-delay="300">
 *   <button>Options</button>
 *   <span slot="content">Rich <strong>HTML</strong> content</span>
 * </ol-tooltip>
 */
export class OlTooltip extends LitElement {
    // ── Warm-mode tracking ──
    // When any tooltip hides, we record the timestamp. If another tooltip
    // tries to show within the warm window, we skip its show delay entirely.
    // We also save the outgoing tooltip's position so the next tooltip can
    // morph (slide) from the old position to its own.
    static _lastHideTime = 0;
    static _lastRect = null;
    static _activeInstance = null;
    static WARM_WINDOW = 300; // ms
    static _idCounter = 0;

    static properties = {
        content: { type: String },
        placement: { type: String },
        showDelay: { type: Number, attribute: 'show-delay' },
        hideDelay: { type: Number, attribute: 'hide-delay' },
        offset: { type: Number },
        withoutArrow: { type: Boolean, attribute: 'without-arrow' },
        disabled: { type: Boolean },
        _visible: { state: true },
        _position: { state: true },
        _actualSide: { state: true },
        _arrowOffset: { state: true },
        _animState: { state: true },
    };

    static styles = css`
        :host {
            display: inline-flex;
            position: relative;
        }

        .tooltip {
            position: fixed;
            z-index: 1000;
            max-width: var(--ol-tooltip-max-width, 280px);
            padding: 6px 10px;
            background: var(--grey-darker, #333);
            color: var(--white, #fff);
            font-size: 13px;
            line-height: 1.4;
            border-radius: var(--border-radius-small, 6px);
            pointer-events: none;
            user-select: none;
            width: max-content;

            /* Hidden by default */
            display: none;
            opacity: 0;
            transform: scale(0.8);
        }

        /* ── Content wrapper for text crossfade ── */

        .tooltip-content {
            display: block;
        }

        /* ── Entering (normal show) ── */

        .tooltip[data-state="preparing"],
        .tooltip[data-state="entering"],
        .tooltip[data-state="open"],
        .tooltip[data-state="morph-preparing"],
        .tooltip[data-state="morphing"],
        .tooltip[data-state="exiting"] {
            display: block;
        }

        .tooltip[data-state="entering"],
        .tooltip[data-state="open"] {
            opacity: 1;
            transform: scale(1);
        }

        .tooltip[data-state="morph-preparing"] {
            opacity: 1;
            transform: scale(1);
        }

        .tooltip[data-state="entering"] {
            transition:
                opacity 350ms cubic-bezier(0.23, 1, 0.32, 1),
                transform 350ms cubic-bezier(0.23, 1, 0.32, 1);
        }

        /* ── Warm-mode morph: slide panel, crossfade text ── */

        .tooltip[data-state="morphing"] {
            opacity: 1;
            transform: scale(1);
            transition:
                top 300ms cubic-bezier(0.23, 1, 0.32, 1),
                left 300ms cubic-bezier(0.23, 1, 0.32, 1);
        }

        .tooltip[data-state="morph-preparing"] .tooltip-content {
            opacity: 0;
        }

        .tooltip[data-state="morphing"] .tooltip-content {
            animation: content-enter 280ms cubic-bezier(0.23, 1, 0.32, 1) both;
        }

        /* ── Exiting ── */

        .tooltip[data-state="exiting"] {
            opacity: 0;
            transform: scale(0.8);
            transition:
                opacity 250ms cubic-bezier(0.165, 0.84, 0.44, 1),
                transform 250ms cubic-bezier(0.165, 0.84, 0.44, 1);
        }

        @keyframes content-enter {
            from {
                opacity: 0;
            }
            to {
                opacity: 1;
            }
        }

        /* ── Arrow ── */

        .arrow {
            position: absolute;
            width: 8px;
            height: 8px;
            background: inherit;
            transform: rotate(45deg);
        }

        :host([data-side="top"]) .arrow {
            bottom: -4px;
        }
        :host([data-side="bottom"]) .arrow {
            top: -4px;
        }
        :host([data-side="left"]) .arrow {
            right: -4px;
        }
        :host([data-side="right"]) .arrow {
            left: -4px;
        }

        @media (prefers-reduced-motion: reduce) {
            .tooltip[data-state="entering"],
            .tooltip[data-state="exiting"],
            .tooltip[data-state="morphing"] {
                transition: none;
            }
            .tooltip[data-state="entering"] .tooltip-content,
            .tooltip[data-state="exiting"] .tooltip-content,
            .tooltip[data-state="morphing"] .tooltip-content {
                transition: none;
                animation: none;
            }
        }
    `;

    constructor() {
        super();
        this.content = '';
        this.placement = 'top';
        this.showDelay = 150;
        this.hideDelay = 0;
        this.offset = 8;
        this.withoutArrow = false;
        this.disabled = false;
        this._visible = false;
        this._position = { top: 0, left: 0 };
        this._actualSide = 'top';
        this._arrowOffset = 0;
        this._animState = 'closed';
        this._reducedMotion = false;
        this._showTimer = null;
        this._hideTimer = null;
        this._tooltipId = `ol-tooltip-${++OlTooltip._idCounter}`;

        this._onMouseEnter = this._onMouseEnter.bind(this);
        this._onMouseLeave = this._onMouseLeave.bind(this);
        this._onFocusIn = this._onFocusIn.bind(this);
        this._onFocusOut = this._onFocusOut.bind(this);
        this._onKeydown = this._onKeydown.bind(this);
        this._onTouchOutside = this._onTouchOutside.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        this.addEventListener('mouseenter', this._onMouseEnter);
        this.addEventListener('mouseleave', this._onMouseLeave);
        this.addEventListener('focusin', this._onFocusIn);
        this.addEventListener('focusout', this._onFocusOut);
        this.addEventListener('keydown', this._onKeydown);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this.removeEventListener('mouseenter', this._onMouseEnter);
        this.removeEventListener('mouseleave', this._onMouseLeave);
        this.removeEventListener('focusin', this._onFocusIn);
        this.removeEventListener('focusout', this._onFocusOut);
        this.removeEventListener('keydown', this._onKeydown);
        document.removeEventListener('touchstart', this._onTouchOutside, true);
        this._clearTimers();
    }

    render() {
        // Reflect the actual side as a host attribute for arrow CSS
        if (this._animState !== 'closed') {
            this.dataset.side = this._actualSide;
        }

        return html`
            <slot @slotchange="${this._onSlotChange}"></slot>
            <div
                class="tooltip"
                id="${this._tooltipId}"
                role="tooltip"
                data-state="${this._animState}"
                style="
                    top: ${this._position.top}px;
                    left: ${this._position.left}px;
                    transform-origin: ${this._transformOrigin};
                "
                @transitionend="${this._onTransitionEnd}"
            >
                <span class="tooltip-content">
                    <slot name="content">${this.content}</slot>
                </span>
                ${!this.withoutArrow ? html`
                    <div
                        class="arrow"
                        aria-hidden="true"
                        style="${this._arrowStyle}"
                    ></div>
                ` : nothing}
            </div>
        `;
    }

    _onSlotChange() {
        const trigger = this._triggerEl;
        if (trigger) {
            trigger.setAttribute('aria-describedby', this._tooltipId);
        }
    }

    // ── Trigger handlers ──

    _onMouseEnter() {
        if (this.disabled) return;
        this._clearTimers();
        const delay = this._isWarm() ? 0 : this.showDelay;
        if (delay > 0) {
            this._showTimer = setTimeout(() => this._show(), delay);
        } else {
            this._show();
        }
    }

    _onMouseLeave() {
        this._clearTimers();
        if (this.hideDelay > 0) {
            this._hideTimer = setTimeout(() => this._hide(), this.hideDelay);
        } else {
            this._hide();
        }
    }

    _onFocusIn() {
        if (this.disabled) return;
        this._clearTimers();
        this._show();
        // On touch devices, listen for taps outside to dismiss
        document.addEventListener('touchstart', this._onTouchOutside, true);
    }

    _onFocusOut() {
        this._clearTimers();
        this._hide();
        document.removeEventListener('touchstart', this._onTouchOutside, true);
    }

    _onTouchOutside(e) {
        if (!e.composedPath().includes(this)) {
            this._clearTimers();
            this._hide();
            document.removeEventListener('touchstart', this._onTouchOutside, true);
        }
    }

    _onKeydown(e) {
        if (e.key === 'Escape' && this._animState !== 'closed') {
            this._hide();
        }
    }

    // ── Warm-mode check ──

    _isWarm() {
        return (Date.now() - OlTooltip._lastHideTime) < OlTooltip.WARM_WINDOW;
    }

    // ── Show / Hide ──

    _show() {
        if (this._animState === 'open' || this._animState === 'entering' || this._animState === 'morphing' || this._animState === 'morph-preparing') return;

        this._reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        const warm = this._isWarm();
        const morphFrom = warm ? OlTooltip._lastRect : null;

        // Clear saved rect so it's only used once
        OlTooltip._lastRect = null;

        // Force-close any tooltip that's still animating out,
        // so only one panel is visible during a morph
        if (morphFrom && OlTooltip._activeInstance && OlTooltip._activeInstance !== this) {
            OlTooltip._activeInstance._animState = 'closed';
            OlTooltip._activeInstance.requestUpdate();
        }

        OlTooltip._activeInstance = this;

        if (morphFrom) {
            // Morph: render at previous tooltip's position first (visible, no transition),
            // then slide to the computed position via CSS transition.
            //
            // Three-phase sequence:
            //   1. Render at old position with 'morph-preparing' (visible, no transition)
            //   2. Measure panel, compute final position, switch to 'morphing' (adds transition)
            //   3. On next frame, update position — CSS transition animates the slide
            this._position = { top: morphFrom.top, left: morphFrom.left };
            this._animState = 'morph-preparing';

            this.updateComplete.then(() => {
                const tooltip = this.shadowRoot.querySelector('.tooltip');
                if (!tooltip) return;

                // Measure panel and compute final position
                const panelW = tooltip.offsetWidth;
                const panelH = tooltip.offsetHeight;
                this._computePosition(panelW, panelH);
                const finalPos = { ...this._position };
                const finalSide = this._actualSide;
                const finalArrowOffset = this._arrowOffset;

                if (this._reducedMotion) {
                    this._animState = 'open';
                    this.dispatchEvent(new CustomEvent('ol-tooltip-show', {
                        bubbles: true, composed: true
                    }));
                    return;
                }

                // Restore old position and enable transition
                this._position = { top: morphFrom.top, left: morphFrom.left };
                this._animState = 'morphing';

                // After Lit renders with transition active, update to final position
                this.updateComplete.then(() => {
                    tooltip.getBoundingClientRect();

                    this._position = finalPos;
                    this._actualSide = finalSide;
                    this._arrowOffset = finalArrowOffset;

                    this.dispatchEvent(new CustomEvent('ol-tooltip-show', {
                        bubbles: true, composed: true
                    }));
                });
            });
        } else {
            // Normal show: render off-screen to measure, then animate in
            this._position = { top: -9999, left: -9999 };
            this._animState = this._reducedMotion ? 'open' : 'preparing';

            this.updateComplete.then(() => {
                const tooltip = this.shadowRoot.querySelector('.tooltip');
                if (!tooltip) return;

                this._computePosition(tooltip.offsetWidth, tooltip.offsetHeight);

                if (this._reducedMotion) {
                    this.dispatchEvent(new CustomEvent('ol-tooltip-show', {
                        bubbles: true, composed: true
                    }));
                    return;
                }

                // Force reflow so browser paints the start position
                tooltip.getBoundingClientRect();

                this._animState = 'entering';
                this.dispatchEvent(new CustomEvent('ol-tooltip-show', {
                    bubbles: true, composed: true
                }));
            });
        }
    }

    _hide() {
        if (this._animState === 'closed' || this._animState === 'exiting') return;

        OlTooltip._lastHideTime = Date.now();
        // Don't clear _activeInstance here — keep it pointing to this tooltip
        // so the next tooltip's _show() can force-close it instantly during
        // warm handoff, preventing two tooltips from being visible at once.

        // Save position for morph handoff to the next tooltip
        OlTooltip._lastRect = {
            top: this._position.top,
            left: this._position.left,
        };

        if (this._reducedMotion) {
            this._animState = 'closed';
            if (OlTooltip._activeInstance === this) {
                OlTooltip._activeInstance = null;
            }
            this.dispatchEvent(new CustomEvent('ol-tooltip-hide', {
                bubbles: true, composed: true
            }));
            return;
        }

        this._animState = 'exiting';
        this.dispatchEvent(new CustomEvent('ol-tooltip-hide', {
            bubbles: true, composed: true
        }));
    }

    _onTransitionEnd(e) {
        if (e.target !== e.currentTarget) return;

        if (this._animState === 'entering' || this._animState === 'morphing') {
            this._animState = 'open';
        } else if (this._animState === 'exiting') {
            this._animState = 'closed';
            if (OlTooltip._activeInstance === this) {
                OlTooltip._activeInstance = null;
            }
        }
    }

    // ── Positioning ──

    _computePosition(panelW, panelH) {
        const trigger = this._triggerEl;
        if (!trigger) return;

        const anchor = trigger.getBoundingClientRect();
        const gap = this.offset;
        const viewW = window.innerWidth;
        const viewH = window.innerHeight;
        const pad = 8;
        const arrowSize = this.withoutArrow ? 0 : 4;

        const [reqSide, reqAlign] = this._parsePlacement(this.placement);

        // Determine side with flip
        let side = reqSide;
        if (side === 'top' && anchor.top - gap - panelH < pad && (viewH - anchor.bottom - gap) > (anchor.top - gap)) {
            side = 'bottom';
        } else if (side === 'bottom' && anchor.bottom + gap + panelH > viewH - pad && (anchor.top - gap) > (viewH - anchor.bottom - gap)) {
            side = 'top';
        } else if (side === 'left' && anchor.left - gap - panelW < pad && (viewW - anchor.right - gap) > (anchor.left - gap)) {
            side = 'right';
        } else if (side === 'right' && anchor.right + gap + panelW > viewW - pad && (anchor.left - gap) > (viewW - anchor.right - gap)) {
            side = 'left';
        }

        let top, left;
        const totalGap = gap + arrowSize;

        // Primary axis
        switch (side) {
        case 'top':
            top = anchor.top - totalGap - panelH;
            break;
        case 'bottom':
            top = anchor.bottom + totalGap;
            break;
        case 'left':
            left = anchor.left - totalGap - panelW;
            break;
        case 'right':
            left = anchor.right + totalGap;
            break;
        }

        // Cross axis
        const anchorCenterX = anchor.left + anchor.width / 2;
        const anchorCenterY = anchor.top + anchor.height / 2;

        if (side === 'top' || side === 'bottom') {
            switch (reqAlign) {
            case 'start':
                left = anchor.left;
                break;
            case 'end':
                left = anchor.right - panelW;
                break;
            case 'center':
            default:
                left = anchorCenterX - panelW / 2;
                break;
            }
            // Clamp horizontal
            if (left + panelW > viewW - pad) left = viewW - pad - panelW;
            if (left < pad) left = pad;
        } else {
            switch (reqAlign) {
            case 'start':
                top = anchor.top;
                break;
            case 'end':
                top = anchor.bottom - panelH;
                break;
            case 'center':
            default:
                top = anchorCenterY - panelH / 2;
                break;
            }
            // Clamp vertical
            if (top + panelH > viewH - pad) top = viewH - pad - panelH;
            if (top < pad) top = pad;
        }

        // Arrow positioning: point at anchor center, clamped to tooltip bounds
        let arrowPos;
        if (side === 'top' || side === 'bottom') {
            arrowPos = Math.max(8, Math.min(anchorCenterX - left, panelW - 8));
        } else {
            arrowPos = Math.max(8, Math.min(anchorCenterY - top, panelH - 8));
        }

        this._position = { top, left };
        this._actualSide = side;
        this._arrowOffset = arrowPos;
    }

    get _transformOrigin() {
        switch (this._actualSide) {
        case 'top': return `${this._arrowOffset}px bottom`;
        case 'bottom': return `${this._arrowOffset}px top`;
        case 'left': return `right ${this._arrowOffset}px`;
        case 'right': return `left ${this._arrowOffset}px`;
        default: return 'center center';
        }
    }

    get _arrowStyle() {
        const pos = this._arrowOffset;
        switch (this._actualSide) {
        case 'top':
        case 'bottom':
            return `left: ${pos}px; transform: translateX(-50%) rotate(45deg);`;
        case 'left':
        case 'right':
            return `top: ${pos}px; transform: translateY(-50%) rotate(45deg);`;
        default:
            return '';
        }
    }

    _parsePlacement(placement) {
        const parts = (placement || 'top').split('-');
        const side = ['top', 'bottom', 'left', 'right'].includes(parts[0]) ? parts[0] : 'top';
        const align = ['start', 'center', 'end'].includes(parts[1]) ? parts[1] : 'center';
        return [side, align];
    }

    get _triggerEl() {
        const slot = this.shadowRoot?.querySelector('slot:not([name])');
        return slot?.assignedElements()[0] ?? null;
    }

    _clearTimers() {
        if (this._showTimer) {
            clearTimeout(this._showTimer);
            this._showTimer = null;
        }
        if (this._hideTimer) {
            clearTimeout(this._hideTimer);
            this._hideTimer = null;
        }
    }
}

customElements.define('ol-tooltip', OlTooltip);
