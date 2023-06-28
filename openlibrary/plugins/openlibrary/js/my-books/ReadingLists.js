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
         * @property {HTMLElement} dropperAnchor Reference to the "Add to list" dropdown affordance
         * @property {HTMLElement} showcaseListItem Reference to this list in the "Already list" showcase
         */
        /**
         * Maps list keys to objects containing more data about the list.
         *
         * @type {Record<string, ActiveListData>}
         */
        this.patronLists = {}

        this.initialize()
    }

    /**
     * Adds functionality to all of the dropper's list affordances.
     */
    initialize() {
        this.initAddToListAnchors(this.dropper.querySelectorAll('.add-to-list'))
        this.registerListItems(this.showcaseItems)

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
     * and the dropdown affordance is hidden (and vice versa if the item is not on
     * the list)
     *
     * @param {boolean} isListMember True if the item is on the list
     * @param {string} listKey Unique identifier for a list
     */
    toggleDisplayedType(isListMember, listKey) {
        const listData = this.patronLists[listKey]

        if (isListMember) {
            if (listData.showcaseListItem) {
                listData.showcaseListItem.classList.remove('hidden')
            } else {
                this.addToShowcase(listKey, this.seedKey, listData.title)
            }
            listData.dropperAnchor.classList.add('hidden')
        } else {
            if (listData.showcaseListItem) {
                listData.showcaseListItem.classList.add('hidden')
            }
            listData.dropperAnchor.classList.remove('hidden')
        }
    }

    /**
     * Hydrates the given "Add to list" elements and stores list data.
     *
     * Each given element is decorated with additional information
     * about the list.  This method also populates the patronLists
     * record.
     * @param {NodeList<HTMLElement>} addToListAnchors
     */
    initAddToListAnchors(addToListAnchors) {
        for (const anchor of addToListAnchors) {
            const listItemKeys = anchor.dataset.listItems
            const listKey = anchor.dataset.listKey

            this.patronLists[listKey] = {
                title: anchor.innerText,
                coverUrl: anchor.listCoverUrl,
                itemOnList: listItemKeys.includes(this.seedKey),
                dropperAnchor: anchor.parentElement,
                showcaseListItem: null
            }
            if (!this.patronLists[listKey].coverUrl) {
                this.patronLists[listKey].coverUrl = DEFAULT_COVER_URL
            }
            if (this.workCheckBox) {
                this.patronLists[listKey].workOnList = listItemKeys.includes(this.workKey)
            }

            anchor.addEventListener('click', (event) => {
                event.preventDefault()
                this.addItemToList(listKey)
            })
        }
    }

    /**
     * Adds a document to the list identified by the given key.
     *
     * @param {string} listKey Unique key for list
     */
    async addItemToList(listKey) {
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

        await addItem(listKey, seed)
            .then(response => response.json())
            .then(() => {
                this.updateViewAfterAddingItem(listKey, seed, isWork)
            })
    }

    /**
     * Updates view and patronLists record after an item has been added to a list.
     *
     * Hides appropriate "Add to list" dropdown element, add the list to the patron's
     * "Already list" list, and closes the dropper.
     *
     * @param {string} listKey
     * @param {object|string} seed
     * @param {boolean} isWork
     */
    updateViewAfterAddingItem(listKey, seed, isWork) {
        const elemToHide = this.patronLists[listKey].dropperAnchor

        if (isWork) {
            this.patronLists[listKey].workOnList = true
        } else {
            this.patronLists[listKey].itemOnList = true
        }

        // Seeds of subjects are strings; all others, objects.
        const isSubjectSeed = typeof seed === 'string'
        const seedKey = isSubjectSeed ? seed : seed['key']

        this.addToShowcase(listKey, seedKey, this.patronLists[listKey].title)

        elemToHide.classList.add('hidden')

        // Close dropper
        fireDropperCloseEvent(elemToHide)
    }

    /**
     * Updates view to add a list to the "Already list" showcase.
     *
     * First checks the patronLists record for a reference to an existing
     * showcase element.  If one is found, its visibility is toggled.  Otherwise,
     * a new element is rendered and hydrated.
     *
     * @param {string} listKey Unique identifier to a list
     * @param {string} seedKey Identifies the item that was added to the list
     * @param {string} listTitle The title of the list
     * @returns {HTMLElement} Reference to the showcase item
     */
    addToShowcase(listKey, seedKey, listTitle) {
        const listData = this.patronLists[listKey]
        const primaryShowcaseItem = listData.showcaseListItem
        if (primaryShowcaseItem) {
            primaryShowcaseItem.classList.remove('hidden')
            return primaryShowcaseItem
        }

        const alreadyLists = document.querySelector('.already-lists')
        const splitKey = listKey.split('/')
        const userKey = `/${splitKey[1]}/${splitKey[2]}`
        const i18nInput = document.querySelector('input[name=list-i18n-strings]')
        const i18nStrings = JSON.parse(i18nInput.value)
        const seedType = seedKey[0] !== '/' ? 'subject' : ''

        const itemMarkUp = `<span class="image">
                        <a href="${listKey}"><img src="${listData.coverUrl}" alt="${i18nStrings['cover_of']}${listTitle}" title="${i18nStrings['cover_of']}${listData.title}"/></a>
                    </span>
                    <span class="data">
                        <span class="label">
                            <a href="${listKey}" data-list-title="${listData.title}" title="${i18nStrings['see_this_list']}">${listData.title}</a>
                            <input type="hidden" name="seed-title" value="${listData.title}"/>
                            <input type="hidden" name="seed-key" value="${seedKey}"/>
                            <input type="hidden" name="seed-type" value="${seedType}"/>
                            <a href="${listKey}" class="remove-from-list red smaller arial plain" data-list-key="${listKey}" title="${i18nStrings['remove_from_list']}">[X]</a>
                        </span>
                        <span class="owner">${i18nStrings['from']} <a href="${userKey}">${i18nStrings['you']}</a></span>
                    </span>`

        const li = document.createElement('li')
        li.classList.add('actionable-item')
        li.dataset.listKey = listKey
        li.innerHTML = itemMarkUp
        if (alreadyLists) {
            alreadyLists.appendChild(li)
            this.patronLists[listKey].showcaseListItem = li
            this.registerShowcaseItem(li)
        }

        return li;
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

        let seed
        if (isSubject) {
            seed = key
        } else {
            if (this.workCheckBox && this.workCheckBox.checked) {
                seed = { key: this.workKey }
            } else {
                seed = { key: key }
            }
        }

        anchors[1].addEventListener('click', (event) => {
            event.preventDefault()
            this.removeShowcaseItem(elem, listKey, seed)
        })
    }

    /**
     * Sends request to remove an item from a list, then updates the view.
     *
     * @param {HTMLElement} showcaseItem Reference to the showcase element that will be hidden
     * @param {string} listKey Unique identifier for the list
     * @param {object|string} seed Identifies item being removed from list
     */
    async removeShowcaseItem(showcaseItem, listKey, seed) {
        await removeItem(listKey, seed)
            .then(response => response.json())
            .then(this.updateViewAfterRemovingItem(showcaseItem, listKey))
    }

    /**
     * Hides the given showcase item, and removes "hidden" class from the
     * appropriate "Add to list" dropdown affordance.
     *
     * @param {HTMLElement} showcaseItem Element to be hidden
     * @param {string} listKey Unique identifier for the list
     */
    updateViewAfterRemovingItem(showcaseItem, listKey) {
        const parentList = showcaseItem.closest('ul')

        if (!parentList.classList.contains('already-lists')) {  // In the "Lists" section of the books page
            showcaseItem.remove()
        }

        this.patronLists[listKey].showcaseListItem.classList.add('hidden')

        if (this.workCheckBox && this.workCheckBox.checked) {
            this.patronLists[listKey].workOnList = false
        } else {
            this.patronLists[listKey].itemOnList = false
        }

        this.patronLists[listKey].dropperAnchor.classList.remove('hidden')
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

        // XXX: Double-check if new list can be made on author, subject pages
        let seed;
        if (this.workCheckBox && this.workCheckBox.checked) {
            // seed is work key
            seed = this.workKey
        } else {
            // seed is edition key
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
                this.onListCreationSuccess(data['key'], listTitle, seed)
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
     * @param {string} seed Identifies the item that was added to the list
     */
    onListCreationSuccess(listKey, listTitle, seed) {
        const dropperAnchor = this.createDropdownListAnchor(listKey, listTitle)

        this.patronLists[listKey] = {
            title: listTitle,
            coverUrl: DEFAULT_COVER_URL,
            dropperAnchor: dropperAnchor
        }

        if (this.workCheckBox && this.workCheckBox.checked) {
            this.patronLists[listKey].itemOnList = false
            this.patronLists[listKey].workOnList = true
        } else {
            this.patronLists[listKey].itemOnList = true
            this.patronLists[listKey].workOnList = false
        }

        this.addToShowcase(listKey, seed, listTitle)
    }

    /**
     * Creates and hydrates a new, hidden, "Add to list" dropdown affordance.
     *
     * @param {string} listKey Unique identifier for a list
     * @param {string} listTitle The list's title
     * @returns {HTMLElement} Reference to the newly created element
     */
    createDropdownListAnchor(listKey, listTitle) {
        const itemMarkUp = `<a href="${listKey}" class="add-to-list dropper__close" data-list-cover-url="${DEFAULT_COVER_URL}" data-list-key="${listKey}">${listTitle}</a>`
        const p = document.createElement('p')
        p.classList.add('list', 'hidden')
        p.innerHTML = itemMarkUp
        this.dropperListsElement.appendChild(p)

        p.children[0].addEventListener('click', (event) => {
            event.preventDefault()
            this.addItemToList(p.children[0])
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
     * @param {NodeList<HTMLElement>} listItemElements 
     */
    registerListItems(listItemElements) {
        for (const elem of listItemElements) {
            const parentList = elem.closest('ul')

            this.registerShowcaseItem(elem)

            if (parentList.classList.contains('already-lists')) {
                const listKey = elem.dataset.listKey
                this.patronLists[listKey].showcaseListItem = elem
            }
        }
    }
}
