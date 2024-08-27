/**
 * Defines functionality related to the My Books dropper's list affordances.
 * @module my-books/MyBooksDropper/ReadingLists
 */
import 'jquery-colorbox';
import myBooksStore from '../store'

import { addItem, removeItem } from '../../lists/ListService'
import { attachNewActiveShowcaseItem, toggleActiveShowcaseItems } from '../../lists/ShowcaseItem'
import { FadingToast } from '../../Toast'

const DEFAULT_COVER_URL = '/images/icons/avatar_book-sm.png'

/**
 * Represents a single My Books dropper's list affordances, and defines their
 * functionalities.
 *
 * @class
 */
export class ReadingLists {
    /**
     * Adds functionality to the given dropper's list affordances.
     * @param {HTMLElement} dropper
     */
    constructor(dropper) {
        /**
         * References the given My Books Dropper root element.
         *
         * @member {HTMLElement}
         */
        this.dropper = dropper

        /**
         * Reference to the "Use work" checkbox.
         *
         * @member {HTMLElement|null}
         */
        this.workCheckBox = dropper.querySelector('.work-checkbox')
        if (this.workCheckBox) {
            // Uncheck "Use work" checkbox on page refresh
            this.workCheckBox.checked = false
        }

        /**
         * Reference to the "My Reading Lists" section of the dropdown content.
         *
         * @member {HTMLElement}
         */
        this.dropperListsElement = dropper.querySelector('.my-lists')

        /**
         * Key of the document that will be added to or removed from a list.
         *
         * @member {string}
         */
        this.seedKey = this.dropperListsElement.dataset.seedKey

        /**
         * Key of the work associated with this dropper. Will be an empty
         * string if no work is associated.
         *
         * @member {string}
         */
        this.workKey = this.dropperListsElement.dataset.workKey

        /**
         * The patron's user key.
         *
         * @member {string}
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
         * @member {Record<string, ActiveListData>}
         */
        this.patronLists = {}
    }

    /**
     * Adds functionality to all of the dropper's list affordances.
     */
    initialize() {
        this.initModifyListAffordances(this.dropper.querySelectorAll('.modify-list'))

        const openListModalButton = this.dropper.querySelector('.create-new-list')

        if (openListModalButton) {
            this.addOpenListModalClickListener(openListModalButton)
        }

        if (this.workCheckBox) {
            this.workCheckBox.addEventListener('click', () => {
                this.updateListDisplays()
                toggleActiveShowcaseItems(this.workCheckBox.checked)
            })
        }
    }

    /**
     * Updates dropdown list affordances when an update occurs.
     */
    updateListDisplays() {
        const isWorkSelected = this.workCheckBox && this.workCheckBox.checked
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
            const itemOnList = listItemKeys.includes(this.seedKey)
            const elemParent = elem.parentElement

            this.patronLists[listKey] = {
                title: elem.innerText,
                coverUrl: elem.dataset.listCoverUrl,
                itemOnList: itemOnList,
                dropperListAffordance: elemParent,  // The .list element
            }
            if (!this.patronLists[listKey].coverUrl) {
                this.patronLists[listKey].coverUrl = DEFAULT_COVER_URL
            }
            if (this.workCheckBox) {
                // Check for work key membership:
                const workOnList = listItemKeys.includes(this.workKey)
                this.patronLists[listKey].workOnList = workOnList

                if (this.workCheckBox.checked) {
                    if (workOnList) {
                        elemParent.classList.add('list--active')
                    }
                } else {
                    if (itemOnList) {
                        elemParent.classList.add('list--active')
                    }
                }
            } else {
                if (itemOnList) {
                    elemParent.classList.add('list--active')
                }
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
     * @async
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
        this.patronLists[listKey].dropperListAffordance.classList.remove('list--active')
        this.patronLists[listKey].dropperListAffordance.classList.add('list--pending')

        await makeChange(listKey, seed)
            .then((response) => {
                if (response.status >= 400) {
                    throw new Error('List update failed')
                }
                response.json()
            })
            .then(() => {
                this.updateViewAfterModifyingList(listKey, isWork, isAddingItem)

                const seedKey = isWork ? this.workKey : this.seedKey
                if (isAddingItem) {
                    // make new active showcase item
                    const listTitle = this.patronLists[listKey].title
                    attachNewActiveShowcaseItem(listKey, seedKey, listTitle, this.patronLists[listKey].coverUrl)
                } else {
                    // remove existing showcase items
                    const showcases = myBooksStore.getShowcases()
                    const matchingShowcases = showcases.filter((item) => item.listKey === listKey && item.seedKey === seedKey)
                    for (const item of matchingShowcases) {
                        item.removeSelf()
                    }
                }
            })
            .catch(() => {
                if (!isAddingItem) {
                    // Replace check mark if patron was removing an item from a list
                    this.patronLists[listKey].dropperListAffordance.classList.add('list--active')
                }
                new FadingToast('Could not update list.  Please try again later.').show()
            })
            .finally(() => this.patronLists[listKey].dropperListAffordance.classList.remove('list--pending'))
    }

    /**
     * Updates `patronLists` with the new list membership information,
     * then updates the view.
     *
     * @param {string} listKey Unique identifier for the modified list
     * @param {boolean} isWork `true` if a work was added or removed
     * @param {boolean} wasItemAdded `true` if item was added to list
     */
    updateViewAfterModifyingList(listKey, isWork, wasItemAdded) {
        if (isWork) {
            this.patronLists[listKey].workOnList = wasItemAdded
        } else {
            this.patronLists[listKey].itemOnList = wasItemAdded
        }

        this.updateListDisplays()
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
                href: '#addList'
            })
        })
    }

    /**
     * Adds new entry to `patronLists` record and updates list dropdown.
     *
     * Creates and hydrates an "Add to list" dropdown affordance.
     *
     * @param {string} listKey Unique identifier for the new list
     * @param {string} listTitle Title of the list
     * @param {boolean} isActive `True` if this dropper's seed is on the list
     * @param {string} coverUrl URL for the list's cover image
     */
    onListCreationSuccess(listKey, listTitle, isActive, coverUrl) {
        const dropperListAffordance = this.createDropdownListAffordance(listKey, listTitle, isActive)

        this.patronLists[listKey] = {
            title: listTitle,
            coverUrl: coverUrl,
            dropperListAffordance: dropperListAffordance
        }

        if (isActive) {
            if (this.workCheckBox && this.workCheckBox.checked) {
                this.patronLists[listKey].itemOnList = false
                this.patronLists[listKey].workOnList = true
            } else {
                this.patronLists[listKey].itemOnList = true
                this.patronLists[listKey].workOnList = false
            }
        }
    }

    /**
     * Creates and hydrates a new "Add to list" dropdown affordance.
     *
     * @param {string} listKey Unique identifier for a list
     * @param {string} listTitle The list's title
     * @param {boolean} isActive `true` if the seed is on this list
     * @returns {HTMLElement} Reference to the newly created element
     */
    createDropdownListAffordance(listKey, listTitle, isActive) {
        const itemMarkUp = `<span class="list__status-indicator"></span>
        <a href="${listKey}" class="modify-list dropper__close" data-list-cover-url="${listKey}" data-list-key="${listKey}">${listTitle}</a>
        `
        const p = document.createElement('p')
        p.classList.add('list')
        if (isActive) {
            p.classList.add('list--active')
        }
        p.innerHTML = itemMarkUp
        this.dropperListsElement.appendChild(p)
        const listAffordance = p.querySelector('.modify-list')

        listAffordance.addEventListener('click', (event) => {
            event.preventDefault()
            const isAddingItem = !this.patronLists[listKey].dropperListAffordance.classList.contains('list--active')
            this.modifyList(listKey, isAddingItem)
        })

        return p
    }

    /**
     * Returns the seed of the object that can be added to this list.
     *
     * @returns {string} The seed key
     */
    getSeed() {
        if (this.workCheckBox && this.workCheckBox.checked) {
            // seed is the work key:
            return this.workKey
        }

        return this.seedKey
    }
}
