import { LitElement, html, css } from 'lit';
import './OlToast.js';

/** Vertical gap between expanded toasts, and the visible peek of collapsed ones. */
const GAP_PX = 14;
/** Collapsed toasts beyond this many are faded out entirely. */
const MAX_VISIBLE = 3;

/**
 * A fixed bottom-center region that stacks <ol-toast> children Sonner-style:
 * the newest toast slides up from below into the anchor slot, pushing older
 * toasts up behind it, scaled back and peeking out. Hovering or focusing the
 * stack expands it into a full list and pauses every toast's dismiss timer.
 *
 * The region owns the choreography, not the toasts: it assigns each child
 * its stack position via `--ol-toast-index` / `--ol-toast-offset` custom
 * properties and `data-stacked` / `data-expanded` / `data-hidden`
 * attributes. The toasts' own transitions animate between those states.
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
            --ol-toast-peek: ${GAP_PX}px;

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
     * Whether the stack is currently expanded (hovered or focused). While
     * true the region owns the toasts' timers: OlToast.resumeTimer() checks
     * this so that mouseleave between toasts can't restart a timer mid-hover.
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
        // Re-shuffle the survivors as soon as a toast starts closing,
        // rather than waiting for its exit transition to finish
        this.addEventListener('ol-toast-close', () => requestAnimationFrame(() => this._layout()));
    }

    /** @returns {Array<import('./OlToast.js').OlToast>} open toasts, oldest first */
    _toasts() {
        return [...this.querySelectorAll(':scope > ol-toast:not([data-closing])')];
    }

    /**
     * Assign each toast its stack position. Newest (last in DOM) is index 0,
     * in front. --ol-toast-offset carries the cumulative expanded-list
     * offset so expanding is a pure transform transition — no layout work.
     */
    _layout() {
        const toasts = this._toasts().reverse();
        let offset = 0;
        toasts.forEach((toast, i) => {
            toast.toggleAttribute('data-stacked', true);
            toast.toggleAttribute('data-expanded', this._expanded);
            toast.toggleAttribute('data-hidden', i >= MAX_VISIBLE);
            toast.style.setProperty('--ol-toast-index', i);
            toast.style.setProperty('--ol-toast-offset', `${offset}px`);
            toast.style.zIndex = String(toasts.length - i);
            offset += toast.offsetHeight + GAP_PX;
        });
    }

    _expand() {
        if (this._expanded) return;
        this._expanded = true;
        this._toasts().forEach((toast) => toast.pauseTimer?.());
        this._layout();
    }

    _collapse() {
        if (!this._expanded) return;
        this._expanded = false;
        this._toasts().forEach((toast) => toast.resumeTimer?.());
        this._layout();
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
