/**
 * Maps tag display types to BEM suffixes.
 */
const classTypeSuffixes = {
    subjects: '--subject',
    subject_people: '--person',
    subject_places: '--place',
    subject_times: '--time'
}

/**
 * @typedef OptionState
 * @property {number} NONE_TAGGED
 * @property {number} SOME_TAGGED
 * @property {number} ALL_TAGGED
 */
/**
 * Enum for amount of tagged works.
 *
 * @readonly
 * @enum {OptionState}
 */
export const MenuOptionState = {
    NONE_TAGGED: 0,
    SOME_TAGGED: 1,
    ALL_TAGGED: 2,
}

export class MenuOption {

    /**
     * Creates a new MenuOption that represents the given tag.
     *
     * `rootElement` of this object is not set until `initialize` is called.
     *
     * @param {Tag} tag
     * @param {OptionState} optionState
     * @param {Number} taggedWorksCount Number of selected works which have the given tag
     */
    constructor(tag, optionState, taggedWorksCount) {
        /**
         * Reference to the root element of this MenuOption.
         *
         * This is not set until `initialize` is called.
         * @member {HTMLElement}
         * @see {initialize}
         */
        this.rootElement

        /**
         * Copy of the tag which is represented by this menu option.
         *
         * @member {Tag}
         * @readonly
         */
        this.tag = tag

        /**
         * Represents the amount of selected works that share this tag.
         *
         * Not meant to be updated directly.  Use `updateMenuOptionState()`,
         * which also updates the UI, to set this value.
         *
         * @member {OptionState}
         */
        this.optionState = optionState

        /**
         * Tracks number of selected works which have this tag.
         *
         * @member {Number}
         */
        this.taggedWorksCount = taggedWorksCount
    }

    /**
     * Creates a new menu option.
     *
     * Must be called before an event handler can be attached to
     * this menu option
     */
    initialize() {
        this.createMenuOption()
    }

    /**
     * Creates a new menu option affordance based on the current menu option state.
     *
     * Stores newly created element as `rootElement`.  The new element is not
     * attached to the DOM, and does not yet have any attached event handlers.
     */
    createMenuOption() {
        const parentElem = document.createElement('div')
        parentElem.classList.add('selected-tag')

        let bemSuffix = ''
        switch (this.optionState) {
        case MenuOptionState.NONE_TAGGED:
            bemSuffix = 'none-tagged'
            break
        case MenuOptionState.SOME_TAGGED:
            bemSuffix = 'some-tagged'
            break
        case MenuOptionState.ALL_TAGGED:
            bemSuffix = 'all-tagged'
            break
        }

        const markup = `<span class="selected-tag__status selected-tag__status--${bemSuffix}"></span>
            <span class="selected-tag__name">${this.tag.tagName}</span>
            <span class="selected-tag__type-container">
                <span class="selected-tag__type selected-tag__type${classTypeSuffixes[this.tag.tagType]}">${this.tag.displayType}</span>
            </span>`

        parentElem.innerHTML = markup
        this.rootElement = parentElem
    }

    /**
     * Removes this MenuOption from the DOM.
     */
    remove() {
        this.rootElement.remove()
    }

    /**
     * Sets the value of `optionState` and updates the view.
     *
     * @param {OptionState} menuOptionState
     *
     * @throws Will throw an error if an unexpected menu option state is passed, or if this
     * `MenuOption` was not initialized prior to calling this method.
     * @see {@link MenuOptionState}
     * @see {initialize}
     */
    updateMenuOptionState(menuOptionState) {
        if (this.rootElement) {  // `rootElement` not set until `initialize` is called
            this.optionState = menuOptionState
            const statusIndicator = this.rootElement.querySelector('.selected-tag__status')
            switch (menuOptionState) {
            case MenuOptionState.NONE_TAGGED:
                statusIndicator.classList.remove('selected-tag__status--all-tagged', 'selected-tag__status--some-tagged')
                statusIndicator.classList.add('selected-tag__status--none-tagged')
                break;
            case MenuOptionState.SOME_TAGGED:
                statusIndicator.classList.remove('selected-tag__status--all-tagged', 'selected-tag__status--none-tagged')
                statusIndicator.classList.add('selected-tag__status--some-tagged')
                break;
            case MenuOptionState.ALL_TAGGED:
                statusIndicator.classList.remove('selected-tag__status--none-tagged', 'selected-tag__status--some-tagged')
                statusIndicator.classList.add('selected-tag__status--all-tagged')
                break;
            default:
                // XXX : `optionState` is now incorrect
                throw new Error('Unexpected value passed for menu option state.')
            }
        } else {
            throw new Error('MenuOption must be initialized before state can be updated.')
        }
    }

    /**
     * Hides this menu option.
     *
     * Fires an `option-hidden` event when this is called.
     */
    hide() {
        this.rootElement.classList.add('hidden')
        this.rootElement.dispatchEvent(new CustomEvent('option-hidden'))
    }

    /**
     * Shows this menu option.
     */
    show() {
        this.rootElement.classList.remove('hidden')
    }

    /**
     * Stages the selected menu option.
     */
    stage() {
        this.rootElement.classList.add('selected-tag--staged');
    }
}
