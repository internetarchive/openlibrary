import { LitElement, html, css, nothing } from 'lit';

/**
 * A tooltip component that displays contextual information on hover/focus.
 *
 * Wraps a trigger element and shows a tooltip panel with configurable placement
 * and arrow. The tooltip appears after a short delay and is shown/hidden
 * instantly with no animation. Each tooltip is independent — moving from one
 * trigger to another hides the old tooltip and shows the new one.
 *
 * @element ol-tooltip
 *
 * @prop {String} content - Text content of the tooltip
 * @prop {String} placement - Preferred placement relative to the trigger.
 *     Format: "{side}" or "{side}-{align}" where side is "top", "bottom",
 *     "left", or "right" and align is "start", "center", or "end".
 *     Default: "top"
 * @prop {Number} showDelay - Milliseconds to wait before showing (default: 150).
 *     Set to 0 for an instant tooltip.
 * @prop {Number} hideDelay - Milliseconds to wait before hiding (default: 0)
 * @prop {Number} offset - Gap in px between trigger and tooltip (default: 4)
 * @prop {Boolean} arrow - Shows the directional arrow (hidden by default)
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
 * <ol-tooltip placement="bottom-start" show-delay="0">
 *   <button>Options</button>
 *   <span slot="content">Rich <strong>HTML</strong> content</span>
 * </ol-tooltip>
 */
export class OlTooltip extends LitElement {
    static _idCounter = 0;

    static properties = {
        content: { type: String },
        placement: { type: String },
        showDelay: { type: Number, attribute: 'show-delay' },
        hideDelay: { type: Number, attribute: 'hide-delay' },
        offset: { type: Number },
        arrow: { type: Boolean },
        disabled: { type: Boolean },
        _visible: { state: true },
        _position: { state: true },
        _actualSide: { state: true },
        _arrowOffset: { state: true },
    };

    static styles = css`
        :host {
            display: inline-flex;
            position: relative;
        }

        .tooltip {
            position: fixed;
            z-index: 1000;
            display: none;
            max-width: var(--ol-tooltip-max-width, 280px);
            padding: 6px 10px;
            background: var(--dark-grey);
            color: var(--white);
            font-size: 13px;
            line-height: var(--line-height-snug);
            border-radius: var(--border-radius-tooltip);
            pointer-events: none;
            user-select: none;
            width: max-content;
        }

        .tooltip[data-visible] {
            display: block;
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
    `;

    constructor() {
        super();
        this.content = '';
        this.placement = 'top';
        this.showDelay = 150;
        this.hideDelay = 0;
        this.offset = 4;
        this.arrow = false;
        this.disabled = false;
        this._visible = false;
        this._position = { top: 0, left: 0 };
        this._actualSide = 'top';
        this._arrowOffset = 0;
        this._showTimer = null;
        this._hideTimer = null;
        this._tooltipId = `ol-tooltip-${++OlTooltip._idCounter}`;

        // Gates the *pointer* path only. On touch devices a tap would both fire
        // the action and surface the tooltip via an emulated mouseenter, so we
        // arm mouseenter only on hover-capable pointers. Keyboard focus is not
        // gated on this — see _onFocusIn, which uses :focus-visible so tab-focus
        // works even on touch-capable devices (e.g. a tablet with a keyboard).
        this._canHover = window.matchMedia('(hover: hover) and (pointer: fine)').matches;

        this._onMouseEnter = this._onMouseEnter.bind(this);
        this._onMouseLeave = this._onMouseLeave.bind(this);
        this._onFocusIn = this._onFocusIn.bind(this);
        this._onFocusOut = this._onFocusOut.bind(this);
        this._onKeydown = this._onKeydown.bind(this);
        this._onScroll = this._onScroll.bind(this);
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
        window.removeEventListener('scroll', this._onScroll, true);
        this._clearTimers();
    }

    render() {
        // Reflect the actual side as a host attribute for arrow CSS
        if (this._visible) {
            this.dataset.side = this._actualSide;
        } else {
            delete this.dataset.side;
        }

        return html`
            <slot @slotchange="${this._onSlotChange}"></slot>
            <div
                class="tooltip"
                id="${this._tooltipId}"
                role="tooltip"
                ?data-visible="${this._visible}"
                style="top: ${this._position.top}px; left: ${this._position.left}px;"
            >
                <slot name="content">${this.content}</slot>
                ${this.arrow ? html`
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
        if (this.disabled || !this._canHover) return;
        this._clearTimers();
        if (this.showDelay > 0) {
            this._showTimer = setTimeout(() => this._show(), this.showDelay);
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
        // Show on genuine keyboard focus only, independent of pointer capability.
        // :focus-visible is the browser's own heuristic for "focus that warrants a
        // ring" — true for Tab/keyboard focus, false for a pointer (mouse/touch)
        // click — so a tap that focuses the trigger won't pop the tooltip, while a
        // keyboard user gets it even on a touch device with hover: none.
        const trigger = this._triggerEl;
        if (!trigger?.matches?.(':focus-visible')) return;
        this._clearTimers();
        this._show();
    }

    _onFocusOut() {
        this._clearTimers();
        this._hide();
    }

    _onKeydown(e) {
        if (e.key === 'Escape' && this._visible) {
            this._hide();
        }
    }

    _onScroll() {
        // The panel is positioned once at show time (position: fixed), so any
        // scroll would strand it away from the trigger. Hiding is simpler and
        // less jarring than repositioning mid-scroll.
        this._hide();
    }

    // ── Show / Hide ──

    _show() {
        if (this._visible) return;

        // Render off-screen first so we can measure the panel, then position it.
        // The off-screen frame is never seen on-screen, so the tooltip simply
        // pops into place once positioned — no flash at the wrong spot.
        this._position = { top: -9999, left: -9999 };
        this._visible = true;

        // Capture phase catches scrolls in any ancestor scroll container, not
        // just the window. Passive since we never preventDefault.
        window.addEventListener('scroll', this._onScroll, { capture: true, passive: true });

        this.updateComplete.then(() => {
            if (!this._visible) return;
            const tooltip = this.shadowRoot.querySelector('.tooltip');
            if (!tooltip) return;

            this._computePosition(tooltip.offsetWidth, tooltip.offsetHeight);
            this.dispatchEvent(new CustomEvent('ol-tooltip-show', {
                bubbles: true, composed: true
            }));
        });
    }

    _hide() {
        if (!this._visible) return;

        window.removeEventListener('scroll', this._onScroll, true);
        this._visible = false;
        this.dispatchEvent(new CustomEvent('ol-tooltip-hide', {
            bubbles: true, composed: true
        }));
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
        const arrowSize = this.arrow ? 4 : 0;

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
