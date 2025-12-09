import { LitElement, html, css, isServer } from 'lit';
import { ifDefined } from 'lit/directives/if-defined.js';

/**
 * A dialog web component for Open Library.
 *
 * @element ol-dialog
 *
 * @slot - Default slot for main dialog content
 * @slot footer - Slot for action buttons
 *
 * @fires ol-open - Fired when the dialog starts opening
 * @fires ol-after-open - Fired after the dialog open animation completes
 * @fires ol-close - Fired when the dialog starts closing (cancelable)
 * @fires ol-after-close - Fired after the dialog close animation completes
 */
export class OlDialog extends LitElement {
    static properties = {
        /** Whether the dialog is open */
        open: { type: Boolean, reflect: true },
        /** The dialog's label/title displayed in the header */
        label: { type: String },
        /** Hides the header when true */
        withoutHeader: { type: Boolean, attribute: 'without-header' },
        /** Dialog width preset: 'small', 'medium', or 'large' */
        width: { type: String },
        /** Whether clicking the backdrop closes the dialog */
        closeOnBackdropClick: { type: Boolean, attribute: 'close-on-backdrop-click' },
        /** Whether pressing Escape closes the dialog */
        closeOnEscape: { type: Boolean, attribute: 'close-on-escape' },
        /** @private Whether the footer slot has content */
        _hasFooterContent: { state: true }
    };

    static styles = css`
        :host {
            --ol-dialog-width-small: 400px;
            --ol-dialog-width-medium: 550px;
            --ol-dialog-width-large: 800px;
            --ol-dialog-padding: 1.25rem;
            --ol-dialog-border-radius: 12px;
            --ol-dialog-animation-duration: 200ms;
            --ol-dialog-backdrop-color: rgba(0, 0, 0, 0.25);
        }

        dialog {
            border: none;
            border-radius: var(--ol-dialog-border-radius);
            padding: 0;
            max-width: 90vw;
            max-height: 85vh;
            overflow: hidden;
            box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15);
        }

        dialog:focus {
            outline: none;
        }

        dialog:focus-visible {
            outline: 2px solid #0074d9;
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
            font-size: 1.25rem;
            font-weight: 600;
            margin: 0;
            /* Reset default h2 margins */
            padding: 0;
        }

        .close-button {
            display: flex;
            align-items: center;
            justify-content: center;
            width: 32px;
            height: 32px;
            padding: 0;
            border: none;
            background: transparent;
            cursor: pointer;
            border-radius: 4px;
            color: inherit;
            transition: background-color 150ms ease;
        }

        .close-button:hover {
            background-color: rgba(0, 0, 0, 0.1);
        }

        .close-button:focus-visible {
            outline: 2px solid #0074d9;
            outline-offset: 2px;
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
        this._hasFooterContent = false;

        /** @type {HTMLElement|null} Element that had focus before dialog opened */
        this._previouslyFocusedElement = null;

        // Bind event handlers
        this._handleCancel = this._handleCancel.bind(this);
        this._handleBackdropClick = this._handleBackdropClick.bind(this);
        this._handleFooterSlotChange = this._handleFooterSlotChange.bind(this);
        this._handleKeyDown = this._handleKeyDown.bind(this);
    }

    /**
     * Unique ID for ARIA labelledby association
     * @private
     */
    get _titleId() {
        return `${this.id || 'ol-dialog'}-title`;
    }

    /**
     * Unique ID for ARIA describedby association
     * @private
     */
    get _bodyId() {
        return `${this.id || 'ol-dialog'}-body`;
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
                // Only close if it was previously open
                this._closeDialog();
            }
        }
    }

    _openDialog() {
        const dialog = this.dialog;
        if (!dialog || dialog.open) return;

        // Save reference to previously focused element for focus restoration
        this._previouslyFocusedElement = document.activeElement;

        // Dispatch ol-open event
        this.dispatchEvent(new CustomEvent('ol-open', {
            bubbles: true,
            composed: true
        }));

        dialog.showModal();

        // Add focus trap listener for Safari compatibility
        // Use capture phase to intercept Tab before Safari's native handling
        document.addEventListener('keydown', this._handleKeyDown, true);

        // Set initial focus
        this._setInitialFocus();

        // Dispatch ol-after-open after animation
        dialog.addEventListener('animationend', () => {
            this.dispatchEvent(new CustomEvent('ol-after-open', {
                bubbles: true,
                composed: true
            }));
        }, { once: true });
    }

    /**
     * Sets initial focus when dialog opens.
     * Priority: [autofocus] element > first focusable > close button > dialog
     * @private
     */
    _setInitialFocus() {
        // Allow a microtask for slotted content to be available
        requestAnimationFrame(() => {
            const dialog = this.dialog;
            if (!dialog) return;

            // 1. Check for element with autofocus attribute in slotted content
            const autofocusEl = this.querySelector('[autofocus]');
            if (autofocusEl) {
                autofocusEl.focus();
                return;
            }

            // 2. Find first focusable element in slotted content
            const focusableSelector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
            const firstFocusable = this.querySelector(focusableSelector);
            if (firstFocusable) {
                firstFocusable.focus();
                return;
            }

            // 3. Fall back to close button
            const closeButton = this.renderRoot?.querySelector('.close-button');
            if (closeButton && !this.withoutHeader) {
                closeButton.focus();
                return;
            }

            // 4. Fall back to dialog itself
            dialog.focus();
        });
    }

    _closeDialog() {
        const dialog = this.dialog;
        if (!dialog || !dialog.open) return;

        // Dispatch cancelable ol-close event
        const closeEvent = new CustomEvent('ol-close', {
            bubbles: true,
            composed: true,
            cancelable: true
        });

        this.dispatchEvent(closeEvent);

        if (closeEvent.defaultPrevented) {
            // Restore open state if prevented
            this.open = true;
            return;
        }

        // Remove focus trap listener
        document.removeEventListener('keydown', this._handleKeyDown, true);

        // Add closing class for animation
        dialog.classList.add('closing');

        dialog.addEventListener('animationend', () => {
            dialog.classList.remove('closing');
            dialog.close();

            // Restore focus to previously focused element
            this._restoreFocus();

            this.dispatchEvent(new CustomEvent('ol-after-close', {
                bubbles: true,
                composed: true
            }));
        }, { once: true });
    }

    /**
     * Restores focus to the element that was focused before the dialog opened.
     * @private
     */
    _restoreFocus() {
        if (this._previouslyFocusedElement && typeof this._previouslyFocusedElement.focus === 'function') {
            // Use setTimeout to ensure focus happens after dialog is fully closed
            setTimeout(() => {
                this._previouslyFocusedElement?.focus();
                this._previouslyFocusedElement = null;
            }, 0);
        }
    }

    /**
     * Handles the native dialog cancel event (triggered by Escape key).
     * @param {Event} event
     * @private
     */
    _handleCancel(event) {
        // Prevent default browser close behavior so we can animate
        event.preventDefault();

        if (this.closeOnEscape) {
            this.open = false;
        }
    }

    /**
     * Handles clicks on the backdrop to close the dialog.
     * @param {MouseEvent} event
     * @private
     */
    _handleBackdropClick(event) {
        if (!this.closeOnBackdropClick) return;

        const dialog = this.dialog;
        if (!dialog) return;

        // Check if click was on the backdrop (::backdrop) by checking if click target is the dialog
        // and the click position is outside the dialog's bounds
        const rect = dialog.getBoundingClientRect();
        const clickedInDialog = (
            event.clientX >= rect.left &&
            event.clientX <= rect.right &&
            event.clientY >= rect.top &&
            event.clientY <= rect.bottom
        );

        if (!clickedInDialog) {
            this.open = false;
        }
    }

    _handleCloseClick() {
        this.open = false;
    }

    /**
     * Gets all focusable elements within the dialog, including slotted content.
     * Elements are returned in DOM/visual order.
     * @returns {HTMLElement[]} Array of focusable elements
     * @private
     */
    _getFocusableElements() {
        const focusableSelector = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';

        // Get the dialog element
        const dialog = this.dialog;
        if (!dialog) return [];

        // Get close button from shadow DOM (it comes first visually)
        const closeButton = this.renderRoot?.querySelector('.close-button');

        // Get the default slot and find focusable elements within assigned content
        const slot = this.renderRoot?.querySelector('slot:not([name])');
        const slottedFocusable = [];

        if (slot) {
            // Get all assigned elements (light DOM content)
            const assignedElements = slot.assignedElements({ flatten: true });
            for (const el of assignedElements) {
                // Check if the element itself is focusable
                if (el.matches?.(focusableSelector)) {
                    slottedFocusable.push(el);
                }
                // Find focusable descendants
                slottedFocusable.push(...el.querySelectorAll(focusableSelector));
            }
        }

        // Build the list in visual order: close button first, then slotted content
        const allFocusable = [];
        if (closeButton && !this.withoutHeader) {
            allFocusable.push(closeButton);
        }
        allFocusable.push(...slottedFocusable);

        // Filter out disabled elements
        return allFocusable.filter(el => !el.disabled);
    }

    /**
     * Gets the currently focused element, handling shadow DOM boundaries.
     * @returns {Element|null}
     * @private
     */
    _getDeepActiveElement() {
        let active = document.activeElement;
        while (active?.shadowRoot?.activeElement) {
            active = active.shadowRoot.activeElement;
        }
        return active;
    }

    /**
     * Handles keydown events to implement manual focus trapping.
     * This is needed because Safari doesn't properly trap focus for slotted content.
     * We manually handle ALL Tab navigation to ensure focus stays within the dialog.
     * @param {KeyboardEvent} event
     * @private
     */
    _handleKeyDown(event) {
        if (event.key !== 'Tab') return;

        const focusable = this._getFocusableElements();
        if (focusable.length === 0) return;

        // Always prevent default and handle focus manually for Safari compatibility
        event.preventDefault();

        const activeElement = this._getDeepActiveElement();
        const currentIndex = focusable.indexOf(activeElement);

        let nextIndex;
        if (event.shiftKey) {
            // Shift+Tab: move backwards
            nextIndex = currentIndex <= 0 ? focusable.length - 1 : currentIndex - 1;
        } else {
            // Tab: move forwards
            nextIndex = currentIndex >= focusable.length - 1 ? 0 : currentIndex + 1;
        }

        focusable[nextIndex].focus();
    }

    /**
     * Handles slotchange events on the footer slot to track if it has content.
     * @param {Event} event
     * @private
     */
    _handleFooterSlotChange(event) {
        const slot = event.target;
        const assignedNodes = slot.assignedNodes({ flatten: true });
        // Check if there are any non-empty text nodes or element nodes
        this._hasFooterContent = assignedNodes.some(node => {
            if (node.nodeType === Node.ELEMENT_NODE) return true;
            if (node.nodeType === Node.TEXT_NODE) return node.textContent.trim() !== '';
            return false;
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        // Clean up focus trap listener
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

            // If open is already true on first render, show the dialog
            if (this.open) {
                this._openDialog();
            }
        }
    }

    render() {
        // Use aria-label when header is hidden, otherwise use aria-labelledby
        const ariaLabel = this.withoutHeader && this.label ? this.label : undefined;
        const ariaLabelledBy = !this.withoutHeader && this.label ? this._titleId : undefined;

        return html`
            <dialog
                role="dialog"
                aria-modal="true"
                aria-label=${ifDefined(ariaLabel)}
                aria-labelledby=${ifDefined(ariaLabelledBy)}
                aria-describedby=${this._bodyId}
            >
                <header
                    class="header ${this.withoutHeader ? 'hidden' : ''}"
                >
                    <h2
                        class="title"
                        id=${this._titleId}
                    >
                        ${this.label}
                    </h2>
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
                <div
                    class="body"
                    id=${this._bodyId}
                >
                    <slot></slot>
                </div>
                <footer class="footer" ?hidden=${!this._hasFooterContent}>
                    <slot name="footer" @slotchange=${this._handleFooterSlotChange}></slot>
                </footer>
            </dialog>
        `;
    }
}

// SSR-safe custom element registration
// Only register when running in browser environment
if (!isServer) {
    customElements.define('ol-dialog', OlDialog);
}
