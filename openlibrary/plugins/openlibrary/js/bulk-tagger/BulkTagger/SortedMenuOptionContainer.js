/**
 * Represents a container which holds zero or more menu
 * options for the bulk tagger.
 *
 * Whenever a menu option is added to this container, it is attached
 * to the DOM in the correct order, based on tag name and type.
 */
export class SortedMenuOptionContainer {

    /**
     * Creates a new sorted menu options container, with the given
     * element as the root element.
     *
     * This container is meant to exclusively hold bulk tagger menu
     * options.  Adding other elements as direct descendents of this
     * container will result bugs during insertion and deletion of
     * menu options.
     *
     * @param {HTMLElement} element The container
     */
    constructor(element) {
        this.rootElement = element
        this.sortedMenuOptions = []
    }

    /**
     * Attaches the given menu options to this container, in order.
     *
     * @param  {...MenuOption} menuOptions Menu options to be added to the container.
     */
    add(...menuOptions) {
        for (const option of menuOptions) {
            const index = this.findIndex(option)
            this.sortedMenuOptions.splice(index, 0, option)
            this.updateViewOnAdd(option, index)
        }
    }

    /**
     * Adds the given menu option to this container at the given index.
     *
     * @param {MenuOption} menuOption The option being attached to the DOM.
     * @param {Number} index The index where the given option will be inserted.
     */
    updateViewOnAdd(menuOption, index) {
        if (index === 0) {
            this.rootElement.prepend(menuOption.rootElement)
        } else {
            const sibling = this.rootElement.children[index - 1]
            sibling.insertAdjacentElement('afterend', menuOption.rootElement)
        }
    }

    /**
     * Removes the given menu options from this container.
     *
     * @param  {...MenuOption} menuOptions Options that are to be removed from this container
     */
    remove(...menuOptions) {
        for (const option of menuOptions) {
            const index = this.findIndex(option)
            const removed = this.sortedMenuOptions.splice(index, 1)
            removed.forEach((option) => option.remove())
        }
    }

    /**
     * Finds the correct index to insert the given menu option, such that
     * the array is alphabetically ordered (case-insensitive).
     *
     * @param {MenuOption} menuOption
     * @returns {Number} Index where the given menu option should be inserted.
     */
    findIndex(menuOption) {
        let index = 0

        // XXX : Binary search?
        while (index < this.sortedMenuOptions.length) {
            const currentMenuOption = this.sortedMenuOptions[index]

            if (currentMenuOption.tag.tagName.toLowerCase() === menuOption.tag.tagName.toLowerCase()) {
                // Compare types
                if (currentMenuOption.tag.tagType.toLowerCase() >= menuOption.tag.tagType.toLowerCase()) {
                    return index
                }
            }
            else if (currentMenuOption.tag.tagName.toLowerCase() > menuOption.tag.tagName.toLowerCase()) {
                return index
            }
            ++index
        }

        return index
    }

    /**
     * Checks if the given menu option is in this container.
     *
     * @param {MenuOption} menuOption The object that we are searching for
     * @returns {boolean} `true` if a matching menu option exists in this container
     */
    contains(menuOption) {
        return this.sortedMenuOptions.some((option) => menuOption.tag.equals(option.tag))
    }

    /**
     * Checks if a menu option which represents the given tag is in this container.
     *
     * @param {Tag} tag
     * @returns {boolean} `true` if a menu option which represents the given tag is in this container.
     */
    containsOptionWithTag(tag) {
        return this.sortedMenuOptions.some((option) => tag.equals(option.tag))
    }

    /**
     * Returns the first menu option found which represents the given tag, or `undefined` if none were found.
     *
     * @param {Tag} tag
     * @returns {MenuOption|undefined} The first matching menu option, or `undefined` if none were found.
     */
    findByTag(tag) {
        return this.sortedMenuOptions.find((option) => tag.equals(option.tag))
    }

    /**
     * Removes all menu options from this container.
     */
    clear() {
        while (this.sortedMenuOptions.length > 0) {
            this.sortedMenuOptions.pop()
        }
        this.rootElement.innerHTML = ''
    }
}
