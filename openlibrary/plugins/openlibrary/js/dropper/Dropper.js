/**
 * Defines functionality for the dropper components.
 * @module dropper/Dropper
 */

/**
 * Defines the base functionality for Open Library's dropper components.
 *
 * A dropper is a button with a two clickable regions: a primary action button
 * and a button to toggle an initially hidden drop-down that provides additional
 * additional functionality.
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
     * @param {HTMLElemnt} dropper Reference to the dropper's root element
     */
    constructor(dropper) {
        /**
         * References the root element of the dropper.
         *
         * @member {HTMLElement}
         */
        this.dropper = dropper

        /**
         * jQuery object containing the root element of the dropper.
         *
         * **Note:** jQuery is only used here for its slide animations.
         * This can be removed when and if these animations are handled
         * strictly with CSS.
         *
         * @member {JQuery<HTMLElement>}
         */
        this.$dropper = $(dropper)

        /**
         * Reference to the affordance that, when clicked, toggles
         * the "Open" state of this dropper.
         *
         * @member {HTMLElement}
         */
        this.dropClick = dropper.querySelector('.generic-dropper__dropclick')

        /**
         * Tracks the current "Open" state of this dropper.
         *
         * @member {boolean}
         */
        this.isDropperOpen = dropper.classList.contains('dropper-wrapper--active')

        /**
         * Tracks whether this dropper is disabled.
         *
         * A disabled dropper cannot be toggled.
         *
         * @member {boolean}
         */
        this.isDropperDisabled = dropper.querySelector('.generic-dropper').classList.contains('generic-dropper--disabled')
    }

    /**
     * Adds click listener to dropper's toggle arrow.
     */
    initialize() {
        this.dropClick.addEventListener('click', () => {
            // REVIEWER: `debounce` call was removed here.
            // Could not get it to work --- suspect that this has something to
            // do with `debounce` being called from an arrow function?
            //
            // I wonder if it's still needed? I don't think that we're doing
            // anything computationally heavy when this is opened or closed.
            // No calls to the server, either.
            this.toggleDropper()
        })
    }

    /**
     * Closes dropper if opened; opens dropper if closed.
     *
     * Toggles value of `isDropperOpen`.
     *
     * Does nothing if this dropper is disabled.
     */
    toggleDropper() {
        if (!this.isDropperDisabled) {
            this.$dropper.find('.generic-dropper__dropdown').slideToggle(25);
            this.$dropper.find('.arrow').toggleClass('up')
            this.$dropper.toggleClass('dropper-wrapper--active')
            this.isDropperOpen = !this.isDropperOpen
        }
    }

    /**
     * Closes this dropper.
     *
     * Sets `isDropperOpen` to `false`.
     *
     * Does nothing if this dropper is disabled.
     */
    closeDropper() {
        if (!this.isDropperDisabled) {
            this.$dropper.find('.generic-dropper__dropdown').slideUp(25)
            this.$dropper.find('.arrow').removeClass('up');
            this.$dropper.removeClass('dropper-wrapper--active')
            this.isDropperOpen = false
        }
    }
}
