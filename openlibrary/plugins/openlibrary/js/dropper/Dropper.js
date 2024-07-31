/**
 * Defines functionality for the dropper components.
 * @module dropper/Dropper
 */

/**
 * Defines the base functionality for Open Library's dropper components.
 *
 * A dropper is a button with a two clickable regions: a primary action button
 * and a button to toggle an initially hidden drop-down that provides additional
 * functionality.
 *
 * A dropper can have a "disabled" state.  If a dropper is disabled, it cannot be
 * opened nor closed.  This is useful when the dropdown content contains affordances
 * which make authenticated API requests, as droppers can be disabled for logged-out
 * patrons.
 *
 * This class adds functionality for toggling and closing a dropper's drop-down content.
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
         * jQuery object containing the root element of the dropper.
         *
         * **Note:** jQuery is only used here for its slide animations.
         * This can be removed when and if these animations are handled
         * strictly with CSS.
         *
         * @member {JQuery<HTMLElement>}
         */
        this.$dropper = $(dropper);

        /**
         * Reference to the affordance that, when clicked, toggles
         * the "Open" state of this dropper.
         *
         * @member {HTMLElement}
         */
        this.dropClick = dropper.querySelector('.generic-dropper__dropclick');

        /**
         * Reference to the dropdown content.
         *
         * @member {HTMLElement}
         */
        this.dropdownContent = dropper.querySelector('.generic-dropper__dropdown');

        /**
         * Tracks the current "Open" state of this dropper.
         *
         * @member {boolean}
         */
        this.isDropperOpen = dropper.classList.contains('generic-dropper-wrapper--active');

        /**
         * Tracks whether this dropper is disabled.
         *
         * A disabled dropper cannot be toggled.
         *
         * @member {boolean}
         */
        this.isDropperDisabled = dropper.classList.contains('generic-dropper--disabled');

        // Set initial ARIA attributes
        this.updateAriaAttributes();
    }

    /**
     * Adds click listener to dropper's toggle arrow.
     */
    initialize() {
        this.dropClick.addEventListener('click', () => {
            this.toggleDropper();
        });
    }

    /**
     * Updates ARIA attributes based on the current state of the dropper.
     */
    updateAriaAttributes() {
        this.dropClick.setAttribute('role', 'button');
        this.dropClick.setAttribute('aria-controls', this.dropdownContent.id);
        this.dropClick.setAttribute('aria-expanded', this.isDropperOpen);
        this.dropdownContent.setAttribute('aria-hidden', !this.isDropperOpen);
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
     * Toggles value of `isDropperOpen`.
     *
     * Calls `onDisabledClick()` if this dropper is disabled.
     * Calls either `onOpen()` or `onClose()` after the dropper
     * has been toggled.
     */
    toggleDropper() {
        if (this.isDropperDisabled) {
            this.onDisabledClick();
        } else {
            // Toggle visibility with CSS class instead of jQuery
            this.dropdownContent.classList.toggle('visible');
            this.dropClick.querySelector('.arrow').classList.toggle('up');
            this.dropper.classList.toggle('generic-dropper-wrapper--active');
            this.isDropperOpen = !this.isDropperOpen;

            // Update ARIA attributes
            this.updateAriaAttributes();

            if (this.isDropperOpen) {
                this.onOpen();
            } else {
                this.onClose();
            }
        }
    }

    /**
     * Closes this dropper.
     *
     * Sets `isDropperOpen` to `false`./**
 * Defines functionality for the dropper components.
 * @module dropper/Dropper
 */

/**
 * Defines the base functionality for Open Library's dropper components.
 *
 * A dropper is a button with a two clickable regions: a primary action button
 * and a button to toggle an initially hidden drop-down that provides additional
 * functionality.
 *
 * A dropper can have a "disabled" state.  If a dropper is disabled, it cannot be
 * opened nor closed.  This is useful when the dropdown content contains affordances
 * which make authenticated API requests, as droppers can be disabled for logged-out
 * patrons.
 *
 * This class adds functionality for toggling and closing a dropper's drop-down content.
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
         * jQuery object containing the root element of the dropper.
         *
         * **Note:** jQuery is only used here for its slide animations.
         * This can be removed when and if these animations are handled
         * strictly with CSS.
         *
         * @member {JQuery<HTMLElement>}
         */
        this.$dropper = $(dropper);

        /**
         * Reference to the affordance that, when clicked, toggles
         * the "Open" state of this dropper.
         *
         * @member {HTMLElement}
         */
        this.dropClick = dropper.querySelector('.generic-dropper__dropclick');

        /**
         * Reference to the dropdown content.
         *
         * @member {HTMLElement}
         */
        this.dropdownContent = dropper.querySelector('.generic-dropper__dropdown');

        /**
         * Tracks the current "Open" state of this dropper.
         *
         * @member {boolean}
         */
        this.isDropperOpen = dropper.classList.contains('generic-dropper-wrapper--active');

        /**
         * Tracks whether this dropper is disabled.
         *
         * A disabled dropper cannot be toggled.
         *
         * @member {boolean}
         */
        this.isDropperDisabled = dropper.classList.contains('generic-dropper--disabled');

        // Set initial ARIA attributes
        this.updateAriaAttributes();
    }

    /**
     * Adds click listener to dropper's toggle arrow.
     */
    initialize() {
        this.dropClick.addEventListener('click', () => {
            this.toggleDropper();
        });
    }

    /**
     * Updates ARIA attributes based on the current state of the dropper.
     */
    updateAriaAttributes() {
        this.dropClick.setAttribute('role', 'button');
        this.dropClick.setAttribute('aria-controls', this.dropdownContent.id);
        this.dropClick.setAttribute('aria-expanded', this.isDropperOpen);
        this.dropdownContent.setAttribute('aria-hidden', !this.isDropperOpen);
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
     * Toggles value of `isDropperOpen`.
     *
     * Calls `onDisabledClick()` if this dropper is disabled.
     * Calls either `onOpen()` or `onClose()` after the dropper
     * has been toggled.
     */
    toggleDropper() {
        if (this.isDropperDisabled) {
            this.onDisabledClick();
        } else {
            // Toggle visibility with CSS class instead of jQuery
            this.dropdownContent.classList.toggle('visible');
            this.dropClick.querySelector('.arrow').classList.toggle('up');
            this.dropper.classList.toggle('generic-dropper-wrapper--active');
            this.isDropperOpen = !this.isDropperOpen;

            // Update ARIA attributes
            this.updateAriaAttributes();

            if (this.isDropperOpen) {
                this.onOpen();
            } else {
                this.onClose();
            }
        }
    }
