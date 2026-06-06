import { LitElement, html, css } from 'lit';

/**
 * A transient notification message ("toast").
 *
 * The common case sets the message via the `message` (and optional `description`)
 * attributes, which the component styles consistently. For uncommon rich
 * content (links, custom markup), provide light-DOM children instead — the
 * attribute-driven markup is the default slot's fallback, so slotted content
 * automatically replaces it.
 *
 * The toast announces itself to screen readers, auto-dismisses after
 * `timeout` milliseconds (unless `persistent`), and removes itself from the
 * DOM when closed. The dismiss timer pauses while the toast is hovered or
 * focused.
 *
 * The component owns no user-facing copy except the close button label
 * (override via `label-close` for i18n). Message content is provided by the
 * caller, already translated.
 *
 * Placed declaratively, the toast renders in-flow where the parent puts it.
 * For the common imperative case (show a toast in the fixed bottom-center
 * stack after a fetch resolves), use the `showToast` helper exported from
 * `OlToastRegion.js` — the region coordinates Sonner-style stacking by
 * setting `data-stacked` / `data-expanded` attributes and `--ol-toast-*`
 * custom properties on each toast.
 *
 * All motion is transition-driven (transform/opacity only): enter uses
 * @starting-style, exit and stack re-shuffles transition between states.
 *
 * @element ol-toast
 *
 * @prop {String}  type       - "info" (default) | "success" | "error".
 *                              Errors use role="alert" / assertive announcements.
 * @prop {String}  message     - The (already translated) message text.
 * @prop {String}  description - Optional secondary line, rendered smaller and muted.
 * @prop {Boolean} persistent - Toast stays until explicitly closed (no timer).
 * @prop {Number}  timeout    - Milliseconds before auto-dismiss. Default: 4000.
 * @prop {String}  labelClose - Aria label for the close button (default: "Close")
 *
 * @slot - Rich message content (links, custom markup). Overrides message/description.
 *
 * @fires ol-toast-close - Fired once when the toast begins closing.
 *                         detail: { reason: "timeout" | "close-button" | "dismiss" }
 *
 * @example
 * // Imperative, fixed bottom-center stack (message already translated)
 * import { showToast } from './OlToastRegion.js';
 * showToast(i18nStrings.updateSuccess, { type: 'success' });
 * showToast(i18nStrings.relaunchToUpdate, { description: version, persistent: true });
 *
 * @example
 * <!-- Rich content via the default slot -->
 * <ol-toast type="error" persistent label-close="$_('Close')">
 *   $_("Could not save.") <a href="/help">$_("Get help")</a>
 * </ol-toast>
 */
export class OlToast extends LitElement {
    static properties = {
        type: { type: String, reflect: true },
        message: { type: String },
        description: { type: String },
        persistent: { type: Boolean },
        timeout: { type: Number },
        labelClose: { type: String, attribute: 'label-close' },
    };

    static styles = css`
        :host {
            /* Sonner's curve — a strong ease-out with a hint of overshoot.
               Shared by enter, exit, and stack re-shuffles so the toasts
               move as one system (paired-elements rule). */
            --ol-toast-ease: cubic-bezier(0.21, 1.02, 0.73, 1);

            display: block;
            width: max-content;
            max-width: 100%;
            font-family: var(--font-family-body);
            pointer-events: auto;
            transition:
                transform 400ms var(--ol-toast-ease),
                opacity 400ms var(--ol-toast-ease);
            will-change: transform;

            /* Enter starting point: hidden, sitting below its final spot.
               The component flips data-mounted one frame after connecting,
               and the transition carries it up into place — same mounted-
               attribute technique as the reference implementation. */
            opacity: 0;
            transform: translateY(8px) scale(0.97);
        }

        :host([data-mounted]) {
            opacity: 1;
            transform: none;
        }

        /* --- Stacked mode: managed by <ol-toast-region> ------------------
           The region sets data-stacked / data-expanded / data-hidden and the
           --ol-toast-index / --ol-toast-offset custom properties. The stack
           is anchored to the bottom edge: the newest toast (index 0) slides
           up from below into the anchor slot, pushing older toasts up and
           back — nudged away and scaled down behind it. On hover the region
           expands the stack into a full list. */
        :host([data-stacked]) {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            width: auto;
            transform-origin: bottom center;
            /* Enter starting point: just below the stack's anchor slot */
            transform: translateY(calc(100% + var(--ol-toast-gap, 14px)));
        }

        :host([data-stacked][data-mounted]) {
            transform:
                translateY(calc(var(--ol-toast-index, 0) * -1 * var(--ol-toast-peek, 14px)))
                scale(calc(1 - var(--ol-toast-index, 0) * 0.05));
        }

        :host([data-stacked][data-expanded][data-mounted]) {
            transform: translateY(calc(-1 * var(--ol-toast-offset, 0px))) scale(1);
        }

        /* Invisible bridge over the gap above each expanded toast, so the
           pointer never "leaves" the stack while moving between toasts */
        :host([data-stacked][data-expanded])::after {
            content: '';
            position: absolute;
            left: 0;
            right: 0;
            bottom: 100%;
            height: var(--ol-toast-gap, 14px);
        }

        /* Deep toasts (4th and beyond) fade out rather than tower up */
        :host([data-hidden]) {
            opacity: 0;
            pointer-events: none;
        }

        /* Exit: fade while drifting back toward the bottom edge */
        :host([data-closing]) {
            opacity: 0;
            pointer-events: none;
        }

        :host([data-closing]:not([data-stacked])) {
            transform: translateY(8px) scale(0.97);
        }

        :host([data-stacked][data-closing]) {
            transform:
                translateY(calc(var(--ol-toast-index, 0) * -1 * var(--ol-toast-peek, 14px) + 12px))
                scale(calc(1 - var(--ol-toast-index, 0) * 0.05));
        }

        :host([data-stacked][data-expanded][data-closing]) {
            transform: translateY(calc(-1 * var(--ol-toast-offset, 0px) + 12px));
        }

        @media (prefers-reduced-motion: reduce) {
            :host {
                transition: none;
            }
        }

        .toast {
            display: flex;
            align-items: flex-start;
            gap: var(--spacing-inline-md);
            box-sizing: border-box;
            max-width: 100%;
            padding: var(--spacing-inset-md);
            background-color: var(--white);
            color: var(--darker-grey);
            font-size: var(--font-size-body-medium);
            line-height: 1.4;
            /* Borderless surface: a hairline ring plus two soft layers,
               in place of a hard border */
            border-radius: var(--border-radius-notification);
            box-shadow:
                0 0 0 1px var(--icon-link-grey),
                0 1px 2px -1px var(--icon-link-grey),
                0 2px 4px 0 var(--icon-link-grey);
        }

        :host([data-stacked]) .toast {
            width: 100%;
        }

        /* Type variants are signalled by a leading white glyph in a filled
           colored circle — sized to the first text line so it reads as part
           of the message, not a separate badge */
        .toast__icon {
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            width: 20px;
            height: 20px;
            margin-top: 1px; /* optically center against the first text line */
            border-radius: 50%;
            color: var(--white);
        }

        .toast--info .toast__icon {
            background-color: var(--primary-blue);
        }

        .toast--success .toast__icon {
            background-color: var(--green);
        }

        .toast--error .toast__icon {
            background-color: var(--red);
        }

        .toast__body {
            flex: 1;
            overflow-wrap: anywhere;
            /* Applied to the body (not just the message) so slotted rich
               content gets the same treatment */
            font-size: var(--font-size-body-large);
            font-weight: 500;
        }

        .toast__message {
            display: block;
        }

        .toast__description {
            display: block;
            margin-top: 2px;
            color: var(--accessible-grey);
            font-size: var(--font-size-label-medium);
            font-weight: normal;
        }

        .toast__close {
            flex-shrink: 0;
            padding: 0 var(--spacing-inset-xs);
            background: none;
            border: none;
            border-radius: var(--border-radius-sm);
            color: var(--accessible-grey);
            font-size: 1.2em;
            line-height: 1.4;
            cursor: pointer;
        }

        @media (hover: hover) and (pointer: fine) {
            .toast__close:hover {
                color: var(--darker-grey);
            }
        }

        .toast__close:focus {
            outline: none;
        }

        .toast__close:focus-visible {
            outline: var(--focus-width) solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        .toast__close:active {
            transform: scale(0.92);
        }
    `;

    /** "i" glyph shown on info toasts (the circle is drawn in CSS) */
    static _infoIcon = html`<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="6" x2="12.01" y2="6"/><line x1="12" y1="11" x2="12" y2="18"/></svg>`;

    /** Check glyph shown on success toasts (the circle is drawn in CSS) */
    static _successIcon = html`<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>`;

    /** Cross glyph shown on error toasts (the circle is drawn in CSS) */
    static _errorIcon = html`<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>`;

    constructor() {
        super();
        this.type = 'info';
        this.message = '';
        this.description = '';
        this.persistent = false;
        this.timeout = 4000;
        this.labelClose = 'Close';
        this._timerId = null;
        this._remainingMs = 0;
        this._timerStartedAt = 0;
        this._closing = false;
    }

    connectedCallback() {
        super.connectedCallback();
        if (!this.persistent) {
            this._remainingMs = this.timeout;
            this.resumeTimer();
        }
        // Let the browser paint one frame in the pre-mount (off-screen)
        // position — including any data-stacked attributes the region sets
        // on slotchange — then flip data-mounted to run the enter transition.
        requestAnimationFrame(() => {
            requestAnimationFrame(() => this.setAttribute('data-mounted', ''));
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._clearTimer();
    }

    _clearTimer() {
        if (this._timerId) {
            clearTimeout(this._timerId);
            this._timerId = null;
        }
    }

    /**
     * Pause the auto-dismiss timer, keeping the remaining time. Called on
     * hover/focus, and by <ol-toast-region> while the stack is expanded.
     */
    pauseTimer() {
        if (this._timerId) {
            this._clearTimer();
            this._remainingMs -= Date.now() - this._timerStartedAt;
        }
    }

    /**
     * Resume (or start) the auto-dismiss timer from the remaining time.
     * No-op while the parent region's stack is expanded — the region owns
     * the pause then, and moving the pointer between toasts (which fires
     * mouseleave on the one being left) must not restart its timer.
     */
    resumeTimer() {
        if (this.persistent || this._closing || this._timerId) return;
        if (this.closest('ol-toast-region')?.expanded) return;
        this._timerStartedAt = Date.now();
        this._timerId = setTimeout(() => this.close('timeout'), Math.max(0, this._remainingMs));
    }

    /**
     * Close the toast: fire ol-toast-close, run the exit transition, and
     * remove the element from the DOM.
     * @param {String} reason - "timeout" | "close-button" | "dismiss"
     */
    close(reason = 'dismiss') {
        if (this._closing) return;
        this._closing = true;
        this._clearTimer();
        this.dispatchEvent(new CustomEvent('ol-toast-close', {
            detail: { reason },
            bubbles: true,
            composed: true,
        }));

        // data-closing triggers the exit transition on the host
        this.setAttribute('data-closing', '');

        const finalize = () => this.remove();
        this.addEventListener('transitionend', (e) => {
            if (e.target === this && e.propertyName === 'opacity') finalize();
        });
        // Fallback in case no transition runs (e.g. prefers-reduced-motion)
        setTimeout(finalize, 500);
    }

    render() {
        const isError = this.type === 'error';
        const icon = this.type === 'success'
            ? OlToast._successIcon
            : isError ? OlToast._errorIcon : OlToast._infoIcon;
        return html`
            <div
                class="toast toast--${this.type}"
                role=${isError ? 'alert' : 'status'}
                aria-live=${isError ? 'assertive' : 'polite'}
                @mouseenter=${this.pauseTimer}
                @mouseleave=${this.resumeTimer}
                @focusin=${this.pauseTimer}
                @focusout=${this.resumeTimer}
            >
                <span class="toast__icon">${icon}</span>
                <span class="toast__body">
                    <slot>
                        <span class="toast__message">${this.message}</span>
                        ${this.description ? html`<span class="toast__description">${this.description}</span>` : ''}
                    </slot>
                </span>
                <button
                    class="toast__close"
                    aria-label=${this.labelClose}
                    @click=${() => this.close('close-button')}
                >&times;</button>
            </div>
        `;
    }
}

customElements.define('ol-toast', OlToast);
