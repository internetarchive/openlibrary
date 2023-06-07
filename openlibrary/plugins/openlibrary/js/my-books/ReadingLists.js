/**
 * Defines functionality related to the My Books dropper's list affordances.
 * @module my-books/ReadingLists
 */
import { getDropperCloseEvent } from '../droppers'
import { addToList, createList, removeFromList } from '../lists/ListService'
import { websafe } from '../jsdef'

/**
 * XXX: What am I?
 * @class
 */
export default class ReadingLists {
    /**
     * Adds functionality to the given dropper's list affordances.
     * @param {HTMLElement} dropper
     */
    constructor(dropper) {
        /**
         * This dropper's "Add to list" links.
         * @param {NodeList<HTMLElement>}
         */
        this.addToListAnchors = dropper.querySelectorAll('.add-to-list')

        /**
         * This dropper's "Create a new list" link.
         * @param {HTMLElement}
         */
        this.openListModalButton = dropper.querySelector('.create-new-list')

        /**
         * References the "Create list" form's submission button.  There should only
         * be a single "Create list" form per page.
         * @param {HTMLElement}
         */
        this.createListButton = document.querySelector('#create-list-button')

        this.actionableItems = {}

        this.dropperLists = {}

        this.workCheckBox = dropper.querySelector('.work-checkbox')
        this.hiddenWorkInput = dropper.querySelector('input[name=work_id]')
        this.hiddenKeyInput = dropper.querySelector('input[name=default-key]')
        this.hiddenUserInput = dropper.querySelector('input[name=user-key]')

        this.initialize()
    }

    /**
     * Adds functionality to all of the dropper's list affordances.
     */
    initialize() {
        this.initAddToListAnchors(this.addToListAnchors)
        if (this.openListModalButton) {
            this.addOpenListModalClickListener()

            if (this.createListButton) {
                this.addCreateListClickListener()
            }
        }
    }

    /**
     * XXX: Improve documentation, improve approach
     * Populates `dropperLists` with patron's list info, and adds click
     * listeners to each list anchor in the dropper.
     */
    initAddToListAnchors(addToListAnchors) {
        for (const anchor of addToListAnchors) {
            this.dropperLists[anchor.dataset.listKey] = {
                title: anchor.innerText,
                element: anchor
            }
            this.addListClickListener(anchor)
        }
    }

    /**
     * XXX: improve approach
     *
     * Click listener for dropper anchor tags
     */
    addListClickListener(anchor) {
        anchor.addEventListener('click', (event) => {
            event.preventDefault()

            const anchorParent = anchor.parentElement

            let seed
            const isWork = this.workCheckBox && this.workCheckBox.checked

            // Seed will be a string if its type is 'subject'
            const isSubjectSeed = this.hiddenKeyInput.value[0] !== '/'
            if (isWork) {
                seed = { key: this.hiddenWorkInput.value }
            } else if (isSubjectSeed) {
                seed = this.hiddenKeyInput.value
            } else {
                seed = { key: this.hiddenKeyInput.value }
            }

            const listKey = anchor.dataset.listKey

            const successCallback = () => {
                if (!isWork) {
                    const seedKey = isSubjectSeed ? seed : seed['key']
                    const listTitle = anchor.innerText
                    const listUrl = anchor.dataset.listCoverUrl
                    const li = this.updateAlreadyList(listKey, listTitle, listUrl, seedKey)

                    if (this.dropperLists.hasOwnProperty(listKey)) {
                        this.dropperLists[listKey].element.remove()
                        delete this.dropperLists[listKey]
                    }

                    if (this.actionableItems.hasOwnProperty(listKey)) {
                        this.actionableItems[listKey].append(li)
                    } else {
                        this.actionableItems[listKey] = [li]
                    }
                }

                // Close dropper
                anchorParent.dispatchEvent(getDropperCloseEvent())
            }

            addToList(listKey, seed, successCallback)
        })
    }

    /**
     * Adds a new list to the "already on list" of lists.
     * @param {*} listKey 
     * @param {*} listTitle 
     * @param {*} coverUrl 
     * @param {*} seedKey 
     * @returns 
     */
    updateAlreadyList(listKey, listTitle, coverUrl, seedKey) {
        // XXX: May have multiple on the page (search results):
        const alreadyLists = document.querySelector('.already-lists')
        const splitKey = listKey.split('/')
        const userKey = `/${splitKey[1]}/${splitKey[2]}`
        const i18nInput = document.querySelector('input[name=list-i18n-strings]')
        const i18nStrings = JSON.parse(i18nInput.value)
        const seedType = seedKey[0] !== '/' ? 'subject' : ''

        const itemMarkUp = `<span class="image">
                <a href="${listKey}"><img src="${coverUrl}" alt="${i18nStrings['cover_of']}${listTitle}" title="${i18nStrings['cover_of']}${listTitle}"/></a>
            </span>
            <span class="data">
                <span class="label">
                    <a href="${listKey}" data-list-title="${listTitle}" title="${i18nStrings['see_this_list']}">${listTitle}</a>
                    <input type="hidden" name="seed-title" value="${listTitle}"/>
                    <input type="hidden" name="seed-key" value="${seedKey}"/>
                    <input type="hidden" name="seed-type" value="${seedType}"/>
                    <a href="${listKey}" class="remove-from-list red smaller arial plain" data-list-key="${listKey}" title="${i18nStrings['remove_from_list']}">[X]</a>
                </span>
                <span class="owner">${i18nStrings['from']} <a href="${userKey}">${i18nStrings['you']}</a></span>
            </span>`

        const li = document.createElement('li')
        li.classList.add('actionable-item')
        li.innerHTML = itemMarkUp
        alreadyLists.appendChild(li)

        this.addRemoveClickListener(li)

        return li;
    }

    /**
     * Click listener for removing item from list
     * @param {*} elem 
     */
    addRemoveClickListener(elem) {
        const label = elem.querySelector('.label')
        const anchors = label.querySelectorAll('a')
        const listTitle = anchors[0].dataset.listTitle
        const listKey = anchors[1].dataset.listKey
        const type = label.querySelector('input[name=seed-type]').value
        const key = label.querySelector('input[name=seed-key]').value

        const seed = type === 'subject' ? key : { key: key }

        anchors[1].addEventListener('click', (event) => {
            event.preventDefault()

            const successCallback = () => {
                // Update view:
                // Remove this element from the view and map:
                if (this.actionableItems.hasOwnProperty(listKey)) {
                    for (const e of this.actionableItems[listKey]) {
                        e.remove()
                    }
                    delete this.actionableItems[listKey]
                }

                if (!this.dropperLists.hasOwnProperty(listKey)) {
                    // Add list item to dropper
                    const coverUrl = elem.querySelector('img').src
                    const p = this.updateDropperList(listKey, listTitle, coverUrl)

                    this.dropperLists[listKey] = {
                        title: listTitle,
                        element: p.children[0]
                    }
                }
            }

            removeFromList(listKey, seed, successCallback)
        })
    }

    /**
     * XXX: Just hide and show the list
     * Adds list anchor to dropper.
     * @param {*} listKey 
     * @param {*} listTitle 
     * @param {*} coverUrl 
     * @returns 
     */
    updateDropperList(listKey, listTitle, coverUrl) {
        const itemMarkUp = `<a href="${listKey}" class="add-to-list dropper__close" data-list-cover-url="${coverUrl}" data-list-key="${listKey}">${listTitle}</a>`

        const p = document.createElement('p')
        p.classList.add('list')
        p.innerHTML = itemMarkUp
        // XXX: May be multiple on page (search results)
        const dropperList = document.querySelector('.my-lists')
        dropperList.appendChild(p)
        this.addListClickListener(p.children[0])

        return p
    }

    /**
     * Adds click listener to the dropper's "Create a new list" button.
     *
     * When the button is clicked, a modal containing the list creation form
     * is displayed. When the modal is closed, the form's inputs are cleared.
     */
    addOpenListModalClickListener() {
        this.openListModalButton.addEventListener('click', (event) => {
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
     * Adds listener to create list button
     */
    addCreateListClickListener() {
        const nameField = document.querySelector('#list_label')
        const descriptionField = document.querySelector('#list_desc')

        this.createListButton.addEventListener('click', (event) => {
            event.preventDefault()

            let seed;
            if (this.workCheckBox && this.workCheckBox.checked) {
                // seed is work key
                seed = this.hiddenWorkInput.value
            } else {
                // seed is edition key
                seed = this.hiddenKeyInput.value
            }

            // Make call to create list
            const data = {
                name: websafe(nameField.value),
                description: websafe(descriptionField.value),
                seeds: [seed]
            }

            const successCallback = (listKey, listTitle) => {
                const seedKey = typeof seed === 'string' ? seed : seed['key']
                // XXX: Why the default image:
                const li = this.updateAlreadyList(listKey, listTitle, '/images/icons/avatar_book-sm.png', seedKey)
                this.actionableItems[listKey] = [li]
            }

            createList(this.hiddenUserInput.value, data, successCallback)

            $.colorbox.close()
        })
    }

    /**
     * Adds click listeners to the remove from list "X" buttons
     * @param {*} listItemElements 
     */
    registerListItems(listItemElements) {
        for (const elem of listItemElements) {
            this.addRemoveClickListener(elem)

            const label = elem.querySelector('.label')
            const anchors = label.querySelectorAll('a')
            const listKey = anchors[1].dataset.listKey

            if (this.actionableItems.hasOwnProperty(listKey)) {
                this.actionableItems[listKey].push(elem)
            } else {
                this.actionableItems[listKey] = [elem]
            }
        }
    }
}
