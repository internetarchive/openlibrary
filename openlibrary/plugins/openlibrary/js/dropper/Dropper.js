/**
 * Defines functionality for the dropper components.
 * @module dropper/Dropper
 */

/**
 * Defines the base functionality for Open Library's dropper components.
 *
 * A dropper is a button with two clickable regions: a primary action button
 * and a button to toggle an initially hidden drop-down that provides additional
 * functionality.
 *
 * The drop-down itself is an `<ol-popover>`, which owns the trigger's ARIA
 * state, Escape and outside-click dismissal, focus restore, and the mobile
 * tray presentation. This class is the bridge between that component and the
 * dropper's own `open`/`close`/`disabled` vocabulary, which the reading log
 * and list affordances call into.
 *
 * A dropper can have a "disabled" state.  If a dropper is disabled, it cannot be
 * opened nor closed.  This is useful when the dropdown content contains affordances
 * which make authenticated API requests, as droppers can be disabled for logged-out
 * patrons.
 *
 * @see `/openlibrary/templates/lib/dropper.html` for base template for this component.
 * @class
 */
export class Dropper {
    /**
     * Creates a new dropper.
     *
     * Sets the initial state of the dropper, and sets references to key
     * dropper elements.
     *
     * @param {HTMLElement} dropper Reference to the dropper's root element
     */
    constructor(dropper) {
        /**
         * References the root element of the dropper.
         *
         * @member {HTMLElement}
         */
        this.dropper = dropper;

        /**
         * Reference to the popover that presents this dropper's drop-down.
         *
         * @member {HTMLElement|null}
         */
        this.popover = dropper.querySelector('ol-popover');

        /**
         * Reference to the affordance that, when clicked, toggles
         * the "Open" state of this dropper.
         *
         * @member {HTMLElement}
         */
        this.dropClick = dropper.querySelector('.generic-dropper__dropclick');

        /**
         * Tracks the current "Open" state of this dropper.
         *
         * @member {boolean}
         */
        this.isDropperOpen = Boolean(this.popover && this.popover.open);

        /**
         * Tracks whether this dropper is disabled.
         *
         * A disabled dropper cannot be toggled.
         *
         * @member {boolean}
         */
        this.isDropperDisabled = dropper.classList.contains('generic-dropper--disabled');
    }

    /**
     * Wires this dropper up to its popover.
     *
     * A disabled dropper swallows the trigger click before the popover sees it,
     * so `onDisabledClick()` can take over — the popover self-manages `open` on
     * trigger click and offers no veto for opening.
     */
    initialize() {
        if (this.isDropperDisabled) {
            if (this.dropClick) {
                this.dropClick.addEventListener('click', (event) => {
                    event.stopPropagation();
                    this.onDisabledClick();
                });
            }
            return;
        }

        // Listen on the wrapper rather than the popover: these events bubble and
        // compose, so this works whether or not the custom element has upgraded
        // by the time we get here.
        this.dropper.addEventListener('ol-popover-open', () => {
            this.isDropperOpen = true;
            this.onOpen();
        });
        this.dropper.addEventListener('ol-popover-close', () => {
            this.isDropperOpen = false;
            this.onClose();
        });
    }

    /**
     * Function that is called after a dropper has opened.
     *
     * Subclasses of `Dropper` may override this to add
     * functionality that should occur on dropper open.
     */
    onOpen() {}

    /**
     * Function that is called after a dropper has closed.
     *
     * Subclasses of `Dropper` may override this to add
     * functionality that should occur on dropper close.
     */
    onClose() {}

    /**
     * Function that is called when the drop-click affordance of
     * a disabled dropper is clicked.
     *
     * Subclasses of `Dropper` may override this as needed.
     */
    onDisabledClick() {}

    /**
     * Closes dropper if opened; opens dropper if closed.
     *
     * Calls `onDisabledClick()` if this dropper is disabled.
     *
     * `onOpen()` and `onClose()` are not called here — they fire from the
     * popover's own events, so they run for Escape and outside clicks too.
     */
    toggleDropper() {
        if (this.isDropperDisabled) {
            this.onDisabledClick();
        } else if (this.popover) {
            this.popover.open = !this.popover.open;
        }
    }

    /**
     * Closes this dropper.
     *
     * Calls `onDisabledClick()` if this dropper is disabled.
     */
    closeDropper() {
        if (this.isDropperDisabled) {
            this.onDisabledClick();
        } else if (this.popover) {
            this.popover.open = false;
        }
    }
}
