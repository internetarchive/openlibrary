import { LitElement, html, css, nothing } from 'lit';

/**
 * A reusable popover component that anchors to a trigger element.
 *
 * Renders a trigger slot and a popover panel that opens/closes with animation.
 * The popover uses `position: fixed` to escape overflow clipping and animates
 * from the trigger's location using `transform-origin`.
 *
 * Automatically flips and shifts when the panel would overflow the viewport.
 *
 * @element ol-popover
 *
 * @prop {Boolean} open - Whether the popover is currently open
 * @prop {String} placement - Preferred placement relative to the trigger.
 *     Format: "{side}-{align}" where side is "top" or "bottom" and align is
 *     "start", "center", or "end". Default: "bottom-start"
 * @prop {Number} offset - Gap in px between trigger and popover (default: 4)
 *
 * @fires ol-popover-open - Fired when the popover opens
 * @fires ol-popover-close - Fired when the popover requests to close (Escape, outside click)
 *
 * @slot trigger - The trigger element (button, icon, etc.)
 * @slot - Default slot for popover content
 *
 * @example
 * <ol-popover>
 *   <button slot="trigger">Open</button>
 *   <div>Popover content here</div>
 * </ol-popover>
 */
export class OlPopover extends LitElement {
    static properties = {
        open: { type: Boolean, reflect: true },
        placement: { type: String },
        offset: { type: Number },
        _position: { state: true },
        _transformOrigin: { state: true },
        _animState: { state: true },
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
            border: 1px solid var(--color-border-subtle, hsl(0, 0%, 87%));
            border-radius: var(--border-radius-overlay, 12px);
            box-shadow: 0 8px 24px var(--boxshadow-black, hsla(0, 0%, 0%, 0.15));
            opacity: 0;
            transform: scale(0.95);
            pointer-events: none;
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
        }

        @media (prefers-reduced-motion: reduce) {
            .panel[data-state="entering"],
            .panel[data-state="exiting"] {
                transition: none;
            }
        }
    `;

    constructor() {
        super();
        this.open = false;
        this.placement = 'bottom-start';
        this.offset = 4;
        this._position = { top: 0, left: 0 };
        this._transformOrigin = 'top left';
        this._animState = 'closed';
        this._onOutsideClick = this._onOutsideClick.bind(this);
        this._onKeydownGlobal = this._onKeydownGlobal.bind(this);
    }

    render() {
        const showPanel = this._animState !== 'closed';
        return html`
            <slot name="trigger"></slot>
            ${showPanel ? html`
                <div
                    class="panel"
                    data-state="${this._animState}"
                    role="dialog"
                    style="
                        top: ${this._position.top}px;
                        left: ${this._position.left}px;
                        transform-origin: ${this._transformOrigin};
                    "
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

    _show() {
        document.addEventListener('click', this._onOutsideClick, true);
        document.addEventListener('keydown', this._onKeydownGlobal);

        const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        // Render panel off-screen first so we can measure it
        this._position = { top: -9999, left: -9999 };
        this._animState = reducedMotion ? 'open' : 'preparing';

        this.updateComplete.then(() => {
            const panel = this.shadowRoot.querySelector('.panel');
            if (!panel) return;

            // Now that the panel is in the DOM, measure and position it
            const panelRect = panel.getBoundingClientRect();
            this._computePosition(panelRect.width, panelRect.height);

            if (reducedMotion) {
                this.dispatchEvent(new CustomEvent('ol-popover-open', {
                    bubbles: true, composed: true
                }));
                return;
            }

            // Force reflow so the browser paints the start position
            panel.getBoundingClientRect();

            this._animState = 'entering';
            this.dispatchEvent(new CustomEvent('ol-popover-open', {
                bubbles: true, composed: true
            }));
        });
    }

    _hide() {
        if (this._animState === 'closed') return;

        const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        if (reducedMotion) {
            this._animState = 'closed';
            this._removeListeners();
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
            this._removeListeners();
        }
    }

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
        return slot?.assignedElements()[0] ?? null;
    }

    _onOutsideClick(e) {
        if (this._animState === 'closed' || this._animState === 'exiting') return;
        const path = e.composedPath();
        if (!path.includes(this)) {
            this._requestClose();
        }
    }

    _onKeydownGlobal(e) {
        if (e.key === 'Escape' && this.open) {
            e.preventDefault();
            this._requestClose();
        }
    }

    _requestClose() {
        this.dispatchEvent(new CustomEvent('ol-popover-close', {
            bubbles: true, composed: true
        }));
    }

    _removeListeners() {
        document.removeEventListener('click', this._onOutsideClick, true);
        document.removeEventListener('keydown', this._onKeydownGlobal);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._removeListeners();
    }
}

customElements.define('ol-popover', OlPopover);
