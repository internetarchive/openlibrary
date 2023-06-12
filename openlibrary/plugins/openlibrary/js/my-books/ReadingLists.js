/**
 * Defines functionality related to the My Books dropper's list affordances.
 * @module my-books/ReadingLists
 */
import { getDropperCloseEvent } from '../droppers'
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
         * References the "Create list" form's submission button.  There should only
         * be a single "Create list" form per page.
         * @param {HTMLElement}
         */
        this.createListButton = document.querySelector('#create-list-button')

        // XXX: Search page issues here:
        this.showcaseItems = document.querySelectorAll('.actionable-item')

        this.workCheckBox = dropper.querySelector('.work-checkbox')
        this.workCheckBox.checked = false

        this.dropperListsElement = dropper.querySelector('.my-lists')
        this.seedKey = this.dropperListsElement.dataset.seedKey
        this.workKey = this.dropperListsElement.dataset.workKey
        this.userKey = this.dropperListsElement.dataset.userKey

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

    initAddToListAnchors(addToListAnchors) {
        for (const anchor of addToListAnchors) {
            const listItemKeys = anchor.dataset.listItems

            this.patronLists[anchor.dataset.listKey] = {
                title: anchor.innerText,
                coverUrl: anchor.listCoverUrl,
                itemOnList: listItemKeys.includes(this.seedKey),
                dropperAnchor: anchor.parentElement,
                showcaseListItem: null
            }
            // XXX: Make sure a cover URL is always in the data attribute (update template)
            if (!this.patronLists[anchor.dataset.listKey].coverUrl) {
                this.patronLists[anchor.dataset.listKey].coverUrl = DEFAULT_COVER_URL
            }
            if (this.workCheckBox) {
                this.patronLists[anchor.dataset.listKey].workOnList = listItemKeys.includes(this.workKey)
            }

            anchor.addEventListener('click', (event) => {
                event.preventDefault()
                this.addItemToList(anchor)
            })
        }
    }

    async addItemToList(anchor) {
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

        const listKey = anchor.dataset.listKey

        await addItem(listKey, seed)
            .then(response => response.json())
            .then(() => {
                this.onAddItemSuccess(listKey, seed, isWork)
            })
    }

    onAddItemSuccess(listKey, seed, isWork) {
        const elemToHide = this.patronLists[listKey].dropperAnchor

        if (isWork) {
            this.patronLists[listKey].workOnList = true
        } else {
            this.patronLists[listKey].itemOnList = true
        }

        // Seeds of subjects are strings; all others, objects.
        const isSubjectSeed = typeof seed === 'string'
        const seedKey = isSubjectSeed ? seed : seed['key']

        if (isWork) {
            this.patronLists[listKey].workOnList = true
        } else {
            this.patronLists[listKey].itemOnList = true
        }

        this.addToShowcase(listKey, seedKey, this.patronLists[listKey].title)

        elemToHide.classList.add('hidden')

        // Close dropper
        elemToHide.dispatchEvent(getDropperCloseEvent())
    }

    addToShowcase(listKey, seedKey, listTitle) {
        const listData = this.patronLists[listKey]
        const primaryShowcaseItem = listData.showcaseListItem
        if (primaryShowcaseItem) {
            primaryShowcaseItem.classList.remove('hidden')
            return primaryShowcaseItem
        }

        // XXX: May have multiple on the page (search results):
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
        alreadyLists.appendChild(li)

        this.patronLists[listKey].showcaseListItem = li

        this.registerShowcaseItem(li)

        return li;
    }

    registerShowcaseItem(elem) {
        // XXX: How many variable are really needed here?
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
            if (this.workCheckBox.checked) {
                seed = { key: this.workKey }
            } else {
                seed = { key: key }
            }
        }

        anchors[1].addEventListener('click', (event) => {
            event.preventDefault()
            this.updateShowcase(elem, listKey, seed)
        })
    }

    async updateShowcase(showcaseItem, listKey, seed) {
        await removeItem(listKey, seed)
            .then(response => response.json())
            .then(this.onUpdateShowcaseSuccess(showcaseItem, listKey))
    }

    onUpdateShowcaseSuccess(showcaseItem, listKey) {
        const parentList = showcaseItem.closest('ul')

        if (!parentList.classList.contains('already-lists')) {  // In the "Lists" section of the books page
            showcaseItem.remove()
        }

        this.patronLists[listKey].showcaseListItem.classList.add('hidden')

        if (this.workCheckBox.checked) {
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

    async createNewList() {
        const nameField = document.querySelector('#list_label')
        const descriptionField = document.querySelector('#list_desc')

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

    onListCreationSuccess(listKey, listTitle, seed) {
        const dropperAnchor = this.createDropdownListAnchor(listKey, listTitle)

        this.patronLists[listKey] = {
            title: listTitle,
            coverUrl: DEFAULT_COVER_URL,
            dropperAnchor: dropperAnchor
        }

        if (this.workCheckBox.checked) {
            this.patronLists[listKey].itemOnList = false
            this.patronLists[listKey].workOnList = true
        } else {
            this.patronLists[listKey].itemOnList = true
            this.patronLists[listKey].workOnList = false
        }

        this.addToShowcase(listKey, seed, listTitle)
    }

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
