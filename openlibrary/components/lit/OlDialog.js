import { LitElement, html, css, isServer } from 'lit';
import { ifDefined } from 'lit/directives/if-defined.js';
import { FOCUSABLE_SELECTOR, findFocusableIndex, getDeepActiveElement, getFocusableFromSlot, isFocusable } from './utils/focus-utils.js';
import { slotHasContent } from './utils/slot-utils.js';

/**
 * A modal dialog built on the native `<dialog>` element. Provides focus trap,
 * focus restoration, scroll lock (via `showModal()`), backdrop dismissal, and
 * Escape-to-close out of the box. Supports slotted header/body/footer content
 * and a fullscreen mode for mobile.
 *
 * @element ol-dialog
 *
 * @prop {Boolean} open - Whether the dialog is open.
 * @prop {String} label - Title shown in the default header. Also used as the
 *     accessible name when `withoutHeader` is true.
 * @prop {Boolean} withoutHeader - Hide the default header (title + close
 *     button). The `header` slot still works.
 * @prop {String} width - Width preset: `'small'` (400px), `'medium'` (550px,
 *     default), or `'large'` (800px). Override per-instance via
 *     `--ol-dialog-width-*` host CSS variables.
 * @prop {Boolean} closeOnBackdropClick - Whether clicking the backdrop closes
 *     the dialog. Default `true`. Attribute: `close-on-backdrop-click`.
 * @prop {Boolean} closeOnEscape - Whether pressing Escape closes the dialog.
 *     Default `true`. Attribute: `close-on-escape`.
 * @prop {Boolean} fullscreenOnMobile - At viewports ≤767px, render edge-to-edge
 *     (full viewport, no border-radius). Attribute: `fullscreen-on-mobile`.
 * @prop {String} placement - `'center'` (default) keeps the dialog vertically
 *     centered like a normal modal. `'top'` anchors it a fixed distance from
 *     the top of the viewport so the top edge stays put as content grows or
 *     shrinks (command-palette / search-modal pattern).
 *
 * @slot - Default slot for the dialog body.
 * @slot header - Optional custom header. When filled, replaces the default
 *     title + close-button row entirely. Useful for search bars, custom
 *     toolbars, etc.
 * @slot footer - Slot for action buttons. Footer region is hidden when empty.
 *
 * @cssprop --ol-dialog-padding - Padding around body and footer regions.
 *     Set to `0` for edge-to-edge content (e.g. when slotting a search bar
 *     or filter row that owns its own padding).
 * @cssprop --ol-dialog-border-radius - Corner radius (ignored in fullscreen mode).
 * @cssprop --ol-dialog-backdrop-color - Backdrop color.
 * @cssprop --ol-dialog-animation-duration - Open/close animation duration.
 * @cssprop --ol-dialog-top-offset - Distance from viewport top when
 *     `placement="top"`. Default `clamp(40px, 8vh, 96px)`.
 *
 * @fires ol-open - Fires when the dialog starts opening.
 * @fires ol-after-open - Fires after the open animation completes.
 * @fires ol-close - Fires when the dialog starts closing. Cancelable —
 *     calling `event.preventDefault()` keeps the dialog open.
 * @fires ol-after-close - Fires after the close animation completes.
 *
 * @example
 * <ol-dialog label="Edit profile" width="medium" open>
 *   <p>Form goes here.</p>
 *   <button slot="footer">Save</button>
 * </ol-dialog>
 *
 * @example
 * <!-- Custom header (e.g. a search bar) with no body padding -->
 * <ol-dialog without-header fullscreen-on-mobile
 *            style="--ol-dialog-padding: 0">
 *   <div slot="header"><input type="search" placeholder="Search…"/></div>
 *   <div>Results…</div>
 * </ol-dialog>
 */
export class OlDialog extends LitElement {
    static properties = {
        open: { type: Boolean, reflect: true },
        label: { type: String },
        withoutHeader: { type: Boolean, attribute: 'without-header' },
        width: { type: String },
        closeOnBackdropClick: { type: Boolean, attribute: 'close-on-backdrop-click' },
        closeOnEscape: { type: Boolean, attribute: 'close-on-escape' },
        fullscreenOnMobile: { type: Boolean, attribute: 'fullscreen-on-mobile', reflect: true },
        placement: { type: String, reflect: true },
        _hasHeaderContent: { state: true },
        _hasFooterContent: { state: true },
    };

    static styles = css`
        :host {
            --ol-dialog-width-small: 400px;
            --ol-dialog-width-medium: 550px;
            --ol-dialog-width-large: 800px;
            --ol-dialog-padding: var(--spacing-xl);
            --ol-dialog-border-radius: var(--border-radius-overlay);
            --ol-dialog-animation-duration: 200ms;
            --ol-dialog-backdrop-color: hsla(0, 0%, 0%, 0.25);
            --ol-dialog-top-offset: clamp(40px, 8vh, 96px);

            font-family: var(--font-family-body);
        }

        dialog {
            border: none;
            border-radius: var(--ol-dialog-border-radius);
            padding: 0;
            max-width: 90vw;
            max-height: 85vh;
            overflow: hidden;
            box-shadow: 0 4px 24px var(--boxshadow-black);
        }

        dialog:focus {
            outline: none;
        }

        dialog:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        dialog[open] {
            display: flex;
            flex-direction: column;
            animation: dialog-open var(--ol-dialog-animation-duration) ease-out;
        }

        dialog.closing {
            animation: dialog-close var(--ol-dialog-animation-duration) ease-in;
        }

        dialog::backdrop {
            background-color: var(--ol-dialog-backdrop-color);
            animation: backdrop-fade-in var(--ol-dialog-animation-duration) ease-out;
        }

        dialog.closing::backdrop {
            animation: backdrop-fade-out var(--ol-dialog-animation-duration) ease-in;
        }

        @keyframes dialog-open {
            from {
                opacity: 0;
                transform: scale(0.95);
            }
            to {
                opacity: 1;
                transform: scale(1);
            }
        }

        @keyframes dialog-close {
            from {
                opacity: 1;
                transform: scale(1);
            }
            to {
                opacity: 0;
                transform: scale(0.95);
            }
        }

        @keyframes backdrop-fade-in {
            from { opacity: 0; }
            to { opacity: 1; }
        }

        @keyframes backdrop-fade-out {
            from { opacity: 1; }
            to { opacity: 0; }
        }

        @media (prefers-reduced-motion: reduce) {
            dialog[open],
            dialog.closing,
            dialog::backdrop,
            dialog.closing::backdrop,
            :host([placement="top"]) dialog[open],
            :host([placement="top"]) dialog.closing {
                animation: none;
            }
        }

        /* Top-anchored placement: keeps the dialog's top edge fixed as its
           own height grows or shrinks (search modal / command palette). */
        :host([placement="top"]) dialog {
            margin-block-start: var(--ol-dialog-top-offset);
            margin-block-end: auto;
            max-height: calc(100dvh - var(--ol-dialog-top-offset) - var(--spacing-xl));
            transform-origin: top center;
        }

        :host([placement="top"]) dialog[open] {
            animation: dialog-open-top var(--ol-dialog-animation-duration) ease-out;
        }

        :host([placement="top"]) dialog.closing {
            animation: dialog-close-top var(--ol-dialog-animation-duration) ease-in;
        }

        @keyframes dialog-open-top {
            from {
                opacity: 0;
                transform: translateY(-8px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        @keyframes dialog-close-top {
            from {
                opacity: 1;
                transform: translateY(0);
            }
            to {
                opacity: 0;
                transform: translateY(-8px);
            }
        }

        /* Width variants */
        :host([width="small"]) dialog {
            width: var(--ol-dialog-width-small);
        }

        :host([width="medium"]) dialog {
            width: var(--ol-dialog-width-medium);
        }

        :host([width="large"]) dialog {
            width: var(--ol-dialog-width-large);
        }

        /* Fullscreen on mobile — overrides width preset and removes chrome.
           Also neutralizes placement="top" so the dialog truly fills the
           viewport (no top offset, no leftover max-height clamp). */
        @media (max-width: 767px) {
            :host([fullscreen-on-mobile]) dialog {
                width: 100vw;
                height: 100dvh;
                max-width: none;
                max-height: none;
                border-radius: 0;
            }

            :host([fullscreen-on-mobile][placement="top"]) dialog {
                margin-block-start: 0;
                margin-block-end: 0;
                max-height: 100dvh;
            }
        }

        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: var(--ol-dialog-padding) var(--ol-dialog-padding) 0 var(--ol-dialog-padding);
        }

        .header.hidden {
            display: none;
        }

        h2.title {
            margin: 0;
            padding: 0;
            font-size: 1.25rem;
            font-weight: 600;
        }

        .close-button {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 32px;
            height: 32px;
            padding: 0;
            background: transparent;
            border: none;
            border-radius: var(--border-radius-button);
            color: inherit;
            cursor: pointer;
            transition: background-color 150ms ease;
        }

        @media (hover: hover) and (pointer: fine) {
            .close-button:hover {
                background-color: var(--icon-link-grey);
            }
        }

        .close-button:focus-visible {
            outline: 2px solid var(--color-focus-ring);
            outline-offset: 2px;
        }

        @media (prefers-reduced-motion: reduce) {
            .close-button {
                transition: none;
            }
        }

        .close-button svg {
            width: 20px;
            height: 20px;
        }

        .body {
            padding: var(--ol-dialog-padding);
            overflow-y: auto;
        }

        .footer {
            padding: 0 var(--ol-dialog-padding) var(--ol-dialog-padding) var(--ol-dialog-padding);
        }

        .footer[hidden] {
            display: none;
        }
    `;

    constructor() {
        super();
        this.open = false;
        this.label = '';
        this.withoutHeader = false;
        this.width = 'medium';
        this.closeOnBackdropClick = true;
        this.closeOnEscape = true;
        this.fullscreenOnMobile = false;
        this.placement = 'center';
        this._hasHeaderContent = false;
        this._hasFooterContent = false;

        /** @type {HTMLElement|null} Element that had focus before dialog opened */
        this._previouslyFocusedElement = null;

        this._handleCancel = this._handleCancel.bind(this);
        this._handleBackdropClick = this._handleBackdropClick.bind(this);
        this._handleHeaderSlotChange = this._handleHeaderSlotChange.bind(this);
        this._handleFooterSlotChange = this._handleFooterSlotChange.bind(this);
        this._handleKeyDown = this._handleKeyDown.bind(this);
    }

    /** Unique ID for ARIA labelledby association */
    get _titleId() {
        return `${this.id || 'ol-dialog'}-title`;
    }

    /** @returns {HTMLDialogElement} */
    get dialog() {
        return this.renderRoot?.querySelector('dialog');
    }

    updated(changedProperties) {
        if (changedProperties.has('open')) {
            if (this.open) {
                this._openDialog();
            } else if (changedProperties.get('open') === true) {
                this._closeDialog();
            }
        }
    }

    _openDialog() {
        const dialog = this.dialog;
        if (!dialog || dialog.open) return;

        this._previouslyFocusedElement = document.activeElement;

        this.dispatchEvent(new CustomEvent('ol-open', {
            bubbles: true,
            composed: true,
        }));

        dialog.showModal();

        // Capture phase to intercept Tab before Safari's native handling.
        document.addEventListener('keydown', this._handleKeyDown, true);

        this._setInitialFocus();

        dialog.addEventListener('animationend', () => {
            this.dispatchEvent(new CustomEvent('ol-after-open', {
                bubbles: true,
                composed: true,
            }));
        }, { once: true });
    }

    /**
     * Sets initial focus when dialog opens.
     * Priority: [autofocus] > first focusable in body > close button > dialog
     */
    _setInitialFocus() {
        requestAnimationFrame(() => {
            const dialog = this.dialog;
            if (!dialog) return;

            const autofocusEl = this.querySelector('[autofocus]');
            if (autofocusEl) {
                autofocusEl.focus();
                return;
            }

            const firstFocusable = this.querySelector(FOCUSABLE_SELECTOR);
            if (firstFocusable) {
                firstFocusable.focus();
                return;
            }

            const closeButton = this.renderRoot?.querySelector('.close-button');
            if (closeButton && !this.withoutHeader && !this._hasHeaderContent) {
                closeButton.focus();
                return;
            }

            dialog.focus();
        });
    }

    _closeDialog() {
        const dialog = this.dialog;
        if (!dialog || !dialog.open) return;

        const closeEvent = new CustomEvent('ol-close', {
            bubbles: true,
            composed: true,
            cancelable: true,
        });

        this.dispatchEvent(closeEvent);

        if (closeEvent.defaultPrevented) {
            this.open = true;
            return;
        }

        document.removeEventListener('keydown', this._handleKeyDown, true);

        dialog.classList.add('closing');

        dialog.addEventListener('animationend', () => {
            dialog.classList.remove('closing');
            dialog.close();

            this._restoreFocus();

            this.dispatchEvent(new CustomEvent('ol-after-close', {
                bubbles: true,
                composed: true,
            }));
        }, { once: true });
    }

    _restoreFocus() {
        if (this._previouslyFocusedElement && typeof this._previouslyFocusedElement.focus === 'function') {
            // setTimeout ensures focus happens after dialog is fully closed.
            setTimeout(() => {
                this._previouslyFocusedElement?.focus();
                this._previouslyFocusedElement = null;
            }, 0);
        }
    }

    /** Native dialog cancel event (Escape key). */
    _handleCancel(event) {
        // Prevent default close so we can animate.
        event.preventDefault();

        if (this.closeOnEscape) {
            this.open = false;
        }
    }

    _handleBackdropClick(event) {
        if (!this.closeOnBackdropClick) return;

        // Clicks on the ::backdrop register the dialog as the target.
        // Clicks on dialog content target a child element.
        if (event.target === this.dialog) {
            this.open = false;
        }
    }

    _handleCloseClick() {
        this.open = false;
    }

    /**
     * Returns all focusable elements within the dialog in DOM order:
     * header → body → footer. Includes the default close button when no
     * custom header is slotted.
     * @returns {HTMLElement[]}
     */
    _getFocusableElements() {
        if (!this.dialog) return [];

        const focusable = [];

        const headerSlot = this.renderRoot?.querySelector('slot[name="header"]');
        const headerSlotted = getFocusableFromSlot(headerSlot);
        if (headerSlotted.length > 0) {
            focusable.push(...headerSlotted);
        } else {
            const closeButton = this.renderRoot?.querySelector('.close-button');
            if (closeButton && !this.withoutHeader && isFocusable(closeButton)) {
                focusable.push(closeButton);
            }
        }

        const bodySlot = this.renderRoot?.querySelector('slot:not([name])');
        focusable.push(...getFocusableFromSlot(bodySlot));

        const footerSlot = this.renderRoot?.querySelector('slot[name="footer"]');
        focusable.push(...getFocusableFromSlot(footerSlot));

        return focusable;
    }

    /**
     * Walks up from `el` (across shadow boundaries) looking for an open
     * nested overlay inside this dialog — currently any `<ol-popover>`
     * with the `open` attribute set. Used to skip Tab trapping when a
     * sub-overlay is driving its own focus.
     * @param {Element|null} el
     * @returns {Boolean}
     */
    _isInsideOpenOverlay(el) {
        let cur = el;
        while (cur && cur !== this.dialog) {
            // ol-popover reflects `open` to its attribute (see OlPopover.js).
            // We match by tagName to avoid an import-time coupling to the
            // OlPopover class itself.
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

    /**
     * Manual Tab focus trap. Needed because Safari doesn't trap focus across
     * shadow DOM boundaries for slotted content.
     */
    _handleKeyDown(event) {
        if (event.key !== 'Tab') return;

        const activeElement = getDeepActiveElement();

        // If focus is inside an open nested overlay (e.g. an <ol-popover> the
        // user just opened from a trigger in this dialog), that overlay owns
        // its own focus trap — don't intercept Tab or we'll yank focus back
        // out of the popover.
        if (this._isInsideOpenOverlay(activeElement)) return;

        const focusable = this._getFocusableElements();
        if (focusable.length === 0) return;

        event.preventDefault();

        // findFocusableIndex climbs shadow boundaries so a custom-element
        // wrapper (e.g. <ol-options-popover>) that delegates focus inward to
        // a deeper button still matches its host entry in the trap list.
        const currentIndex = findFocusableIndex(focusable, activeElement);

        let nextIndex;
        if (event.shiftKey) {
            nextIndex = currentIndex <= 0 ? focusable.length - 1 : currentIndex - 1;
        } else {
            nextIndex = currentIndex >= focusable.length - 1 ? 0 : currentIndex + 1;
        }

        focusable[nextIndex].focus();
    }

    _handleHeaderSlotChange(event) {
        this._hasHeaderContent = slotHasContent(event.target);
    }

    _handleFooterSlotChange(event) {
        this._hasFooterContent = slotHasContent(event.target);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('keydown', this._handleKeyDown, true);
        const dialog = this.dialog;
        if (dialog) {
            dialog.removeEventListener('cancel', this._handleCancel);
            dialog.removeEventListener('click', this._handleBackdropClick);
        }
    }

    firstUpdated() {
        const dialog = this.dialog;
        if (dialog) {
            dialog.addEventListener('cancel', this._handleCancel);
            dialog.addEventListener('click', this._handleBackdropClick);

            if (this.open) {
                this._openDialog();
            }
        }
    }

    render() {
        const showDefaultHeader = !this.withoutHeader && !this._hasHeaderContent;
        const ariaLabel = (this.withoutHeader || this._hasHeaderContent) && this.label ? this.label : undefined;
        const ariaLabelledBy = showDefaultHeader && this.label ? this._titleId : undefined;

        return html`
            <dialog
                role="dialog"
                aria-modal="true"
                aria-label=${ifDefined(ariaLabel)}
                aria-labelledby=${ifDefined(ariaLabelledBy)}
            >
                <header class="header ${showDefaultHeader ? '' : 'hidden'}">
                    <h2 class="title" id=${this._titleId}>${this.label}</h2>
                    <button
                        class="close-button"
                        type="button"
                        aria-label="Close dialog"
                        @click=${this._handleCloseClick}
                    >
                        <svg
                            xmlns="http://www.w3.org/2000/svg"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            stroke-width="2"
                            stroke-linecap="round"
                            stroke-linejoin="round"
                            aria-hidden="true"
                        >
                            <line x1="18" y1="6" x2="6" y2="18"></line>
                            <line x1="6" y1="6" x2="18" y2="18"></line>
                        </svg>
                    </button>
                </header>
                <slot name="header" @slotchange=${this._handleHeaderSlotChange}></slot>
                <div class="body">
                    <slot></slot>
                </div>
                <footer class="footer" ?hidden=${!this._hasFooterContent}>
                    <slot name="footer" @slotchange=${this._handleFooterSlotChange}></slot>
                </footer>
            </dialog>
        `;
    }
}

// SSR-safe registration. Guarded against double-registration when both the
// lit-components bundle and a webpack consumer (e.g. SearchModal) import the
// component module.
if (!isServer && !customElements.get('ol-dialog')) {
    customElements.define('ol-dialog', OlDialog);
}
