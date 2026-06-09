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
 * Most callers should use the exported {@link showToast} helper rather
 * than instantiating the region directly.
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
        labelRegion: { type: String, attribute: 'label-region' },
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
        const heights = toasts.map((toast) => toast.offsetHeight);
        let offset = 0;
        toasts.forEach((toast, i) => {
            toast.style.setProperty('--ol-toast-offset', `${offset}px`);
            offset += heights[i] + GAP_PX;
        });
    }

    _expand() {
        if (this._expanded) return;
        this._expanded = true;
        this._toasts().forEach((toast) => toast.pauseTimer?.());
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
        this._toasts().forEach((toast) => toast.resumeTimer?.());
    }

    render() {
        return html`<slot @slotchange=${() => this._layout()}></slot>`;
    }
}

customElements.define('ol-toast-region', OlToastRegion);

/**
 * Show a toast in the shared fixed bottom-center stack, creating the
 * <ol-toast-region> on first use.
 *
 * The common case passes a string, set as the `message` attribute — always
 * rendered as text, never HTML — so callers can safely pass user- or
 * server-derived strings. Pass already-translated strings (e.g. from the
 * page's i18nStrings payload).
 *
 * For rich content, author the markup in a page template — where $_() i18n
 * extraction works — inside an inert <template> element, and pass that
 * element; its content is cloned into the toast's slot:
 *
 *     <template id="save-error-toast">
 *       $_("Could not save.") <a href="/help">$_("Get help")</a>
 *     </template>
 *
 *     showToast(document.querySelector('#save-error-toast'), { type: 'error' });
 *
 * Nodes built in JS (or an array of Nodes and strings) also work; strings in
 * the array become text nodes. No path ever parses a runtime string as HTML.
 *
 * Plain-DOM equivalent for code outside this bundle:
 *
 *     const toast = document.createElement('ol-toast');
 *     toast.setAttribute('message', message);
 *     toast.setAttribute('type', 'error');
 *     let region = document.querySelector('ol-toast-region');
 *     if (!region) document.body.appendChild(region = document.createElement('ol-toast-region'));
 *     region.appendChild(toast);
 *
 * @param {String|HTMLTemplateElement|Node|Array<Node|String>} content -
 *     Already-translated message text, a <template> whose content is cloned
 *     in, or rich slot content as Node(s)
 * @param {Object} [options]
 * @param {String} [options.description] - Optional secondary line (smaller, muted).
 *     Only applies when content is a string; slotted content replaces it.
 * @param {String} [options.type] - "info" | "success" | "error"
 * @param {Boolean} [options.persistent] - Stay until explicitly closed
 * @param {Number} [options.timeout] - Auto-dismiss delay in ms
 * @param {String} [options.labelClose] - Translated close button label
 * @returns {import('./OlToast.js').OlToast} The toast element (call .close() to dismiss early)
 */
export function showToast(content, options = {}) {
    let region = document.querySelector('ol-toast-region');
    if (!region) {
        region = document.createElement('ol-toast-region');
        document.body.appendChild(region);
    }
    const toast = document.createElement('ol-toast');
    if (typeof content === 'string') {
        toast.setAttribute('message', content);
    } else if (content instanceof HTMLTemplateElement) {
        // Author-written markup from the page template (i18n-extracted,
        // server-escaped); cloned so the template stays reusable
        toast.append(content.content.cloneNode(true));
    } else {
        // Node or Array<Node|String> — append() renders strings as text,
        // never HTML, and slotted children override message/description
        toast.append(...[].concat(content));
    }
    if (options.description) toast.setAttribute('description', options.description);
    if (options.type) toast.setAttribute('type', options.type);
    if (options.persistent) toast.setAttribute('persistent', '');
    if (options.timeout !== undefined) toast.setAttribute('timeout', options.timeout);
    if (options.labelClose) toast.setAttribute('label-close', options.labelClose);
    region.appendChild(toast);
    return toast;
}
