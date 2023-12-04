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
     * @param {Tag} tag
     * @param {OptionState} optionState
     */
    constructor(tag, optionState, worksTagged) {
        /**
         * Reference to the root element of this MenuOption.
         *
         * This is set by the `renderAndAttach` method.
         * @member {HTMLElement}
         */
        this.rootElement

        /**
         * @member {Tag}
         */
        this.tag = tag

        /**
         * Represents the amount of selected works that share this tag.
         *
         * @member {OptionState}
         */
        this.optionState = optionState

        /**
         * @member {Number}
         */
        this.worksTagged = worksTagged
    }

    /**
     * Renders a new MenuOption, and attaches it to the given element.
     *
     * The `rootElement` property will be undefined until this
     * method is called.
     *
     * @param {HTMLElement} target
     */
    renderAndAttach(target) {
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

        target.prepend(parentElem)
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
     * @throws Will throw an error if an unexpected menu option state is passed.
     * @see {@link MenuOptionState}
     */
    updateWorksTagged(menuOptionState) {
        this.optionState = menuOptionState

        if (this.rootElement) {  // `rootElement` not set until `renderAndAttach` is called
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
                throw new Error('Unexpected value passed for menu option state')
            }
        }
    }

    /**
     * Hides this MenuOption.
     */
    hide() {
        this.rootElement.classList.add('hidden')
    }

    /**
     * Shows this MenuOption.
     */
    show() {
        this.rootElement.classList.remove('hidden')
    }
}
