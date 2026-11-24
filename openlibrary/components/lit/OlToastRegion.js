import { LitElement, html, css } from 'lit';
import './OlToast.js';

/** Vertical gap between stacked toasts. */
const GAP_PX = 14;

/**
 * A fixed bottom-center region that arranges its <ol-toast> children into a
 * plain vertical list anchored to the bottom edge: the newest toast occupies
 * the bottom slot and older ones stack straight up with a fixed gap. Adding a
 * toast slides it up from below into the bottom slot while the others slide up
 * to make room. Hovering or focusing the list pauses every toast's dismiss
 * timer. There is no depth, scaling, or collapse/expand — just a spaced list.
 *
 * The region owns the placement, not the toasts: it sets each child's
 * `data-stacked` attribute and an `--ol-toast-offset` custom property (the
 * cumulative height of the newer toasts below it). The toasts' own
 * transitions animate between offset states.
 *
 * Most callers should use showToast() from toast.js rather than
 * instantiating the region directly.
 *
 * @element ol-toast-region
 *
 * @prop {String} labelRegion - Aria label for the landmark (default: "Notifications")
 *
 * @example
 * <ol-toast-region label-region="$_('Notifications')"></ol-toast-region>
 */
export class OlToastRegion extends LitElement {
    static properties = {
        labelRegion: { type: String, attribute: 'label-region' }
    };

    static styles = css`
        :host {
            --ol-toast-gap: ${GAP_PX}px;

            position: fixed;
            bottom: var(--spacing-inset-md);
            left: 50%;
            transform: translateX(-50%);
            width: min(356px, calc(100vw - 32px));
            z-index: var(--z-index-toast);
            pointer-events: none;
        }
    `;

    constructor() {
        super();
        this.labelRegion = 'Notifications';
        this._expanded = false;
    }

    /**
     * Whether the user is currently interacting with the list (hovered or
     * focused). While true the region owns the toasts' timers — it has paused
     * them all — and OlToast.resumeTimer() checks this so that mouseleave
     * between toasts can't restart a single timer mid-hover.
     * @returns {Boolean}
     */
    get expanded() {
        return this._expanded;
    }

    connectedCallback() {
        super.connectedCallback();
        this.setAttribute('role', 'region');
        if (!this.hasAttribute('aria-label')) {
            this.setAttribute('aria-label', this.labelRegion);
        }
        // mouseenter/leave fire for descendants too, even though the host
        // itself is pointer-events: none
        this.addEventListener('mouseenter', this._expand);
        this.addEventListener('mouseleave', this._collapse);
        this.addEventListener('focusin', this._expand);
        this.addEventListener('focusout', this._collapse);
        // Re-place the survivors as soon as a toast starts closing (they slide
        // down to fill the gap), rather than waiting for its exit transition.
        this.addEventListener('ol-toast-close', () => requestAnimationFrame(() => this._layout()));
        // A toast grows once it populates its live region (one frame after
        // mount); re-place the list so offsets account for its height.
        this.addEventListener('ol-toast-resize', () => this._layout());
    }

    /** @returns {Array<import('./OlToast.js').OlToast>} open toasts, oldest first */
    _toasts() {
        return [...this.querySelectorAll(':scope > ol-toast:not([data-closing])')];
    }

    /**
     * Place each toast in the bottom-anchored list. Newest (last in DOM) sits
     * in the bottom slot; --ol-toast-offset carries the cumulative height of
     * the newer toasts below it, so placement is a pure transform transition —
     * no layout work.
     */
    _layout() {
        const toasts = this._toasts().reverse();
        // Pass 1 — stacked mode flips each toast to position:absolute / full
        // width, which can change its wrapped height.
        toasts.forEach((toast, i) => {
            toast.toggleAttribute('data-stacked', true);
            toast.style.zIndex = String(toasts.length - i);
        });
        // Pass 2 — measure once (single reflow) now that every toast is
        // stacked, then assign cumulative offsets. --ol-toast-offset only feeds
        // a transform, so writing it forces no further layout.
        const heights = toasts.map(toast => toast.offsetHeight);
        let offset = 0;
        toasts.forEach((toast, i) => {
            toast.style.setProperty('--ol-toast-offset', `${offset}px`);
            offset += heights[i] + GAP_PX;
        });
    }

    _expand() {
        if (this._expanded) return;
        this._expanded = true;
        this._toasts().forEach(toast => toast.pauseTimer?.());
    }

    _collapse(e) {
        if (!this._expanded) return;
        // Don't resume timers while the user is still interacting with the list.
        // Tabbing between toasts fires focusout on the region (relatedTarget
        // stays inside); dismissing a toast drops focus to <body> via focusout
        // while the pointer is still hovering. In both cases the timers should
        // stay paused — without this guard they'd resume (and possibly fire)
        // mid-interaction. The :hover check is skipped for mouseleave, where its
        // timing is unreliable; there we rely on relatedTarget / activeElement.
        const stillInteracting =
            (e?.relatedTarget && this.contains(e.relatedTarget)) ||
            this.contains(document.activeElement) ||
            (e?.type !== 'mouseleave' && this.matches(':hover'));
        if (stillInteracting) return;
        this._expanded = false;
        this._toasts().forEach(toast => toast.resumeTimer?.());
    }

    render() {
        return html`<slot @slotchange=${() => this._layout()}></slot>`;
    }
}

customElements.define('ol-toast-region', OlToastRegion);
