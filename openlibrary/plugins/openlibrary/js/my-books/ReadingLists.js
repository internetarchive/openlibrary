/**
 * Defines functionality related to the My Books dropper's list affordances.
 * @module my-books/ReadingLists
 */
import { fireDropperCloseEvent } from '../droppers'
import { addItem, removeItem, createList } from '../lists/ListService'
import { websafe } from '../jsdef'


const DEFAULT_COVER_URL = '/images/icons/avatar_book-sm.png'

/**
 * Represents a single My Books dropper's list affordances, and defines their
 * functionalities.
 *
 * @class
 */
export default class ReadingLists {
    /**
     * Adds functionality to the given dropper's list affordances.
     * @param {HTMLElement} dropper
     */
    constructor(dropper) {
        /**
         * References the given My Books Dropper
         * @param {HTMLElement}
         */
        this.dropper = dropper

        /**
         * References the "Create list" form's submission button.
         * @param {HTMLElement}
         */
        // XXX: Use class-based query here, and ensure that this ID is unique in template (or remove)
        this.createListButton = dropper.querySelector('#create-list-button')

        /**
         * References to each showcase item that can be removed by the patron.  Showcase items
         * can be found in a patron's "Already lists" list, or in the "Lists" section of the
         * books page.
         * @param {NodeList<HTMLElement>}
         */
        this.showcaseItems = document.querySelectorAll('.actionable-item')

        /**
         * Reference to the "Use work" checkbox.
         * @param {HTMLElement|null}
         */
        this.workCheckBox = dropper.querySelector('.work-checkbox')
        if (this.workCheckBox) {
            // Uncheck "Use work" checkbox on page refresh
            this.workCheckBox.checked = false
        }

        /**
         * Reference to the "My Reading Lists" section of the dropdown content.
         * @param {HTMLElement}
         */
        this.dropperListsElement = dropper.querySelector('.my-lists')

        /**
         * Key of the document that will be added to or removed from a list.
         * @param {string}
         */
        this.seedKey = this.dropperListsElement.dataset.seedKey

        /**
         * Key of the work associated with this dropper. Will be an empty
         * string if no work is associated.
         * @param {string}
         */
        this.workKey = this.dropperListsElement.dataset.workKey

        /**
         * The patron's user key.
         * @param {string}
         */
        this.userKey = this.dropperListsElement.dataset.userKey

        /**
         * Stores information about a single list.
         *
         * @typedef ActiveListData
         * @type {object}
         * @property {string} title The title of the list
         * @property {string} coverUrl URL for the seed's image
         * @property {boolean} itemOnList True if the list contains the default seed key
         * @property {boolean} workOnList True if the list contains a reference to a work
         * @property {HTMLElement} dropperListAffordance Reference to the "Add to list" dropdown affordance
         */
        /**
         * Maps list keys to objects containing more data about the list.
         *
         * @type {Record<string, ActiveListData>}
         */
        this.patronLists = {}
    }

    /**
     * Adds functionality to all of the dropper's list affordances.
     */
    initialize() {
        this.initModifyListAffordances(this.dropper.querySelectorAll('.modify-list'))
        this.registerShowcases(this.showcaseItems)

        const openListModalButton = this.dropper.querySelector('.create-new-list')

        if (openListModalButton) {
            this.addOpenListModalClickListener(openListModalButton)

            if (this.createListButton) {
                this.createListButton.addEventListener('click', (event) => {
                    event.preventDefault()
                    this.createNewList()
                })
            }
        }

        if (this.workCheckBox) {
            this.workCheckBox.addEventListener('click', () => {
                const isWork = this.workCheckBox.checked
                this.updateListDisplays(isWork)
            })
        }
    }

    /**
     * Updates dropdown and "Already list" list affordances when the "Use work" checkbox
     * is ticked.
     *
     * @param {boolean} isWorkSelected True if the "Use work" checkbox is ticked
     */
    updateListDisplays(isWorkSelected) {
        for (const key of Object.keys(this.patronLists)) {
            const listData = this.patronLists[key]

            if (isWorkSelected) {
                this.toggleDisplayedType(listData.workOnList, key)
            } else {
                this.toggleDisplayedType(listData.itemOnList, key)
            }
        }
    }

    /**
     * Changes list affordance visibility in the dropper and "Already list"
     * list based on an item's membership to the given list.
     *
     * If the item is on the list, the "Already list" list affordance is displayed
     * and the dropdown affordance will display a checkmark.
     *
     * @param {boolean} isListMember True if the item is on the list
     * @param {string} listKey Unique identifier for a list
     */
    toggleDisplayedType(isListMember, listKey) {
        const listData = this.patronLists[listKey]

        if (isListMember) {
            listData.dropperListAffordance.classList.add('list--active')
        } else {
            listData.dropperListAffordance.classList.remove('list--active')
        }
    }

    /**
     * Hydrates the given dropdown list affordance elements and stores list data.
     *
     * Each given element is decorated with additional information about the list.
     * This method also populates the patronLists record.
     *
     * @param {NodeList<HTMLElement>} modifyListElements
     */
    initModifyListAffordances(modifyListElements) {
        for (const elem of modifyListElements) {
            const listItemKeys = elem.dataset.listItems
            const listKey = elem.dataset.listKey

            this.patronLists[listKey] = {
                title: elem.innerText,
                coverUrl: elem.listCoverUrl,
                itemOnList: listItemKeys.includes(this.seedKey),
                dropperListAffordance: elem.parentElement,  // The .list element
            }
            if (!this.patronLists[listKey].coverUrl) {
                this.patronLists[listKey].coverUrl = DEFAULT_COVER_URL
            }
            if (this.workCheckBox) {
                this.patronLists[listKey].workOnList = listItemKeys.includes(this.workKey)
            }

            elem.addEventListener('click', (event) => {
                event.preventDefault()
                const isAddingItem = !this.patronLists[listKey].dropperListAffordance.classList.contains('list--active')
                this.modifyList(listKey, isAddingItem)
            })
        }
    }

    /**
     * Adds or removes a document to or from the list identified by the given key.
     *
     * @param {string} listKey Unique key for list
     * @param {boolean} isAddingItem `true` if an item is being added to a list
     */
    async modifyList(listKey, isAddingItem) {
        let seed
        const isWork = this.workCheckBox && this.workCheckBox.checked

        // Seed will be a string if its type is 'subject'
        const isSubjectSeed = this.seedKey[0] !== '/'

        if (isWork) {
            seed = { key: this.workKey }
        } else if (isSubjectSeed) {
            seed = this.seedKey
        } else {
            seed = { key: this.seedKey }
        }

        const makeChange = isAddingItem ? addItem : removeItem

        await makeChange(listKey, seed)
            .then(response => response.json())
            .then(() => {
                this.updateViewAfterModifyingList(listKey, isWork, isAddingItem)
            })
    }

    /**
     * Updates view and patronLists record after an item has been added to a list.
     *
     * Toggles checkmark in appropriate "Add to list" dropdown element, add the list
     * to the patron's "Already list" list, and closes the dropper.
     *
     * @param {string} listKey Unique identifier for a list
     * @param {boolean} isWork `true` if seed represents a work
     * @param {boolean} wasAdded `true` if the seed was added from the list
     */
    updateViewAfterModifyingList(listKey, isWork, wasAdded) {
        if (isWork) {
            this.patronLists[listKey].workOnList = wasAdded
        } else {
            this.patronLists[listKey].itemOnList = wasAdded
        }

        if (wasAdded) {
            this.patronLists[listKey].dropperListAffordance.classList.add('list--active')
        } else {
            this.patronLists[listKey].dropperListAffordance.classList.remove('list--active')
        }

        // Close dropper
        fireDropperCloseEvent(this.patronLists[listKey].dropperListAffordance)
    }

    /**
     * Adds "Remove from list" click handlers to showcase list items.
     *
     * @param {HTMLElement} elem
     */
    registerShowcaseItem(elem) {
        // XXX: How many variables are really needed here?
        const label = elem.querySelector('.label')
        const anchors = label.querySelectorAll('a')
        const listKey = anchors[1].dataset.listKey
        const type = label.querySelector('input[name=seed-type]').value
        const key = label.querySelector('input[name=seed-key]').value

        const isSubject = type === 'subject'
        const isWork = !isSubject && key.slice(-1) === 'W'

        let seed
        if (isSubject) {
            seed = key
        } else {
            seed = { key: key }
        }

        anchors[1].addEventListener('click', (event) => {
            event.preventDefault()
            this.removeShowcaseItem(elem, listKey, seed, isWork)
        })
    }

    /**
     * Sends request to remove an item from a list, then updates the view.
     *
     * @param {HTMLElement} showcaseItem Reference to the showcase element that will be hidden
     * @param {string} listKey Unique identifier for the list
     * @param {object|string} seed Identifies item being removed from list
     * @param {boolean} isWork `true` if the seed references a work
     */
    async removeShowcaseItem(showcaseItem, listKey, seed, isWork) {
        await removeItem(listKey, seed)
            .then(response => response.json())
            .then(this.updateViewAfterRemovingItem(showcaseItem, listKey, isWork))
    }

    /**
     * Removes the given showcase item, and hides checkmark in the
     * appropriate "Add to list" dropdown affordance.
     *
     * @param {HTMLElement} showcaseItem Element to be hidden
     * @param {string} listKey Unique identifier for the list
     * @param {boolean} isWork `true` if the seed references a work
     */
    updateViewAfterRemovingItem(showcaseItem, listKey, isWork) {
        showcaseItem.remove()

        if (isWork) {
            this.patronLists[listKey].workOnList = false
        } else {
            this.patronLists[listKey].itemOnList = false
        }

        if (this.workCheckBox) {  // This is a book page
            if ((this.workCheckBox.checked && isWork) || (!this.workCheckBox.checked && !isWork)) {
                this.patronLists[listKey].dropperListAffordance.classList.remove('list--active')
            }
        } else {
            this.patronLists[listKey].dropperListAffordance.classList.remove('list--active')
        }
    }

    /**
     * Adds click listener to the given "Create a new list" button.
     *
     * When the button is clicked, a modal containing the list creation form
     * is displayed. When the modal is closed, the form's inputs are cleared.
     *
     * @param {HTMLElement} openListModalButton
     */
    addOpenListModalClickListener(openListModalButton) {
        openListModalButton.addEventListener('click', (event) => {
            event.preventDefault()

            $.colorbox({
                inline: true,
                opacity: '0.5',
                href: '#addList',
                onClosed: this.clearCreateListForm
            })
        })
    }

    /**
     * Clears the inpus of the "Create new list" modal form.
     */
    clearCreateListForm() {
        document.querySelector('#list_label').value = ''
        document.querySelector('#list_desc').value = ''
    }

    /**
     * Creates a new list and updates the view.
     */
    async createNewList() {
        const nameField = document.querySelector('#list_label')
        const descriptionField = document.querySelector('#list_desc')

        let seed;
        if (this.workCheckBox && this.workCheckBox.checked) {
            // seed is work key
            seed = this.workKey
        } else {
            // seed is edition or author key
            seed = this.seedKey
        }

        const listTitle = websafe(nameField.value)

        // Make call to create list
        const data = {
            name: listTitle,
            description: websafe(descriptionField.value),
            seeds: [seed]
        }

        await createList(this.userKey, data)
            .then(response => response.json())
            .then((data) => {
                this.onListCreationSuccess(data['key'], listTitle)
            })

        $.colorbox.close()
    }

    /**
     * Updates patronLists record and adds the list to the showcase.
     *
     * Creates and hydrates an "Add to list" dropdown affordance, as well.
     *
     * @param {string} listKey Unique identifier for the new list
     * @param {string} listTitle Title of the list
     */
    onListCreationSuccess(listKey, listTitle) {
        const dropperListAffordance = this.createDropdownListAffordance(listKey, listTitle)

        this.patronLists[listKey] = {
            title: listTitle,
            coverUrl: DEFAULT_COVER_URL,
            dropperListAffordance: dropperListAffordance
        }

        if (this.workCheckBox && this.workCheckBox.checked) {
            this.patronLists[listKey].itemOnList = false
            this.patronLists[listKey].workOnList = true
        } else {
            this.patronLists[listKey].itemOnList = true
            this.patronLists[listKey].workOnList = false
        }
    }

    /**
     * Creates and hydrates a new "Add to list" dropdown affordance.
     *
     * @param {string} listKey Unique identifier for a list
     * @param {string} listTitle The list's title
     * @returns {HTMLElement} Reference to the newly created element
     */
    createDropdownListAffordance(listKey, listTitle) {
        const itemMarkUp = `<span class="check">✔️</span>
        <a href="${listKey}" class="modify-list dropper__close" data-list-cover-url="${DEFAULT_COVER_URL}" data-list-key="${listKey}">${listTitle}</a>
        `
        const p = document.createElement('p')
        p.classList.add('list', 'list--active')
        p.innerHTML = itemMarkUp
        this.dropperListsElement.appendChild(p)

        p.children[0].addEventListener('click', (event) => {
            event.preventDefault()
            this.modifyList(p.children[0], true)
        })

        return p
    }

    /**
     * Hydrates all given showcase elements.
     *
     * Used to hydrate all showcases' items on a page.  If an element is
     * located within the "Already lists" list, it is added to the
     * patronLists record.
     *
     * @param {NodeList<HTMLElement>} showcaseItemElements
     */
    registerShowcases(showcaseItemElements) {
        for (const elem of showcaseItemElements) {
            this.registerShowcaseItem(elem)
        }
    }
}