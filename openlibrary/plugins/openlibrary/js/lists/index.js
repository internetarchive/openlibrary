/**
 * Defines code needed for the reading log/list dropper.
 * @module lists/index
 */

import { createList, addToList, removeFromList, updateReadingLog, fetchPartials } from './ListService'
import { websafe } from '../jsdef'

/**
 * Maps a list key to an array of references to removeable list items.
 */
const actionableItems = {}

/**
 * @typedef ListData
 * @type {object}
 * @property {string} title - The list's title
 * @property {string} anchor - A reference to the list's dropper link
 */
/**
 * Maps a list key to an object containing the list's title and a reference
 * to the list's dropper link.
 *
 * @type {Record<string, ListData>}
 */
const dropperLists = {}

/**
 * Add all necessary event listeners to the given collection of reading
 * log droppers.
 *
 * @param {HTMLCollection} droppers Collection of reading log droppers.
 */
export function initDroppers(droppers) {
    for (const dropper of droppers) {
        const anchors = dropper.querySelectorAll('.add-to-list');
        initAddToListAnchors(anchors, dropper)

        const openModalButton = dropper.querySelector('.create-new-list')
        if (openModalButton) {
            addOpenModalClickListener(openModalButton)

            const createListButton = document.querySelector('#create-list-button')
            if (createListButton) {
                addCreateListClickListener(createListButton, dropper)
            }
        }

        const submitButtons = dropper.querySelectorAll('button')

        for (const button of submitButtons) {
            addReadingLogButtonClickListener(button)
        }
    }
}

/**
 * Adds click listeners to the given "add-to-list" anchors in dropper
 *
 * @param {NodeListOf<Element>} anchors The "add-to-list" links
 * @param {HTMLElement} dropper The reading log dropper
 */
function initAddToListAnchors(anchors, dropper) {
    for (const anchor of anchors) {
        // Store reference to anchor and list title:
        dropperLists[anchor.dataset.listKey] = {
            title: anchor.innerText,
            element: anchor
        }
        addListClickListener(anchor, dropper);
    }
}

/**
 * Adds click listeners to the given "add-to-list" link in the given dropper.
 *
 * On click the item is added to the list, and the view is updated.
 *
 * @param {HTMLAnchorElement} elem A link that adds an item to a list.
 * @param {HTMLDivElement} parentDropper The link's parent dropper element.
 */
function addListClickListener(elem, parentDropper) {
    elem.addEventListener('click', function(event){
        event.preventDefault()
        // Add book to list
        const workCheckBox = parentDropper.querySelector('.work-checkbox');
        const hiddenWorkInput = parentDropper.querySelector('input[name=work_id]')
        const hiddenKeyInput = parentDropper.querySelector('input[name=default-key]')

        let seed;
        const isWork = workCheckBox && workCheckBox.checked

        // Seed will be a string if it's type is 'subject'
        const seedIsSubject = hiddenKeyInput.value[0] !== '/'
        if (isWork) {
            seed = { key: hiddenWorkInput.value }
        } else if (seedIsSubject) {
            seed = hiddenKeyInput.value
        } else {
            seed = { key: hiddenKeyInput.value }
        }

        const listKey = elem.dataset.listKey;

        const successCallback = function() {
            if (!isWork) {
                const seedKey = seedIsSubject ? seed : seed['key']
                const listTitle = elem.innerText;
                const listUrl = elem.dataset.listCoverUrl
                const li = updateAlreadyList(listKey, listTitle, listUrl, seedKey)

                if (dropperLists.hasOwnProperty(listKey)) {
                    dropperLists[listKey].element.remove()
                    delete dropperLists[listKey]
                }

                if (actionableItems.hasOwnProperty(listKey)) {
                    actionableItems[listKey].append(li)
                } else {
                    actionableItems[listKey] = [li]
                }
            }

            // close dropper
            toggleDropper(parentDropper)
        }

        addToList(listKey, seed, successCallback)

    })
}

/**
 * Toggles given dropper's expanded state.
 *
 * @param {HTMLDivElement} dropper A reading log button reference.
 */
function toggleDropper(dropper) {
    $(dropper).find('.dropdown').first().slideToggle(25);
    $(dropper).find('.arrow').first().toggleClass('up');
}

/**
 * Add listener to dropper's create list button.
 *
 * When pressed, a modal with the list creation form will open.
 *
 * @param {HTMLButtonElement} submitButton Dropper's create list button.
 */
function addOpenModalClickListener(submitButton) {
    submitButton.addEventListener('click', function(event) {
        event.preventDefault()

        // Open modal
        $.colorbox({
            inline: true,
            opacity: '0.5',
            href: '#addList',
            onClosed: clearCreateListForm
        })
    })
}

/**
 * Adds click listener to the create list modal's submit button.
 *
 * When clicked the form is validated, a new list is created, and the
 * item is added to the new list.
 *
 * @param {HTMLButtonElement} button The modal's submit button.
 * @param {HTMLDivElement} parentDropper The dropper from which the modal was opened.
 */
function addCreateListClickListener(button, parentDropper) {
    const nameField = document.querySelector('#list_label');
    const descriptionField = document.querySelector('#list_desc')
    const workCheckBox = parentDropper.querySelector('.work-checkbox')
    const hiddenWorkInput = parentDropper.querySelector('input[name=work_id]')
    const hiddenKeyInput = parentDropper.querySelector('input[name=default-key]')
    const hiddenUserInput = parentDropper.querySelector('input[name=user-key]')

    button.addEventListener('click', function(event){
        // if form is valid:
        if (nameField.checkValidity()) {
            // prevent default button behavior
            event.preventDefault()

            let seed;
            if (workCheckBox && workCheckBox.checked) {
                // seed is work key
                seed = hiddenWorkInput.value
            } else {
                // seed is edition key
                seed = hiddenKeyInput.value
            }

            // Make call to create list
            const data = {
                name: websafe(nameField.value),
                description: websafe(descriptionField.value),
                seeds: [seed],
            }

            const successCallback = function(listKey, listTitle) {
                const seedKey = typeof seed === 'string' ? seed : seed['key']
                // Add actionable item to view, map
                const li = updateAlreadyList(listKey, listTitle, '/images/icons/avatar_book-sm.png', seedKey)
                actionableItems[listKey] = [li]
            }

            createList(hiddenUserInput.value, data, successCallback)

            // Close colorbox
            $.colorbox.close()
        }
    })
}

/**
 * Clears the inputs of the "Create new list" modal form.
 *
 * NOTE: This function intended for internal use.
 */
export function clearCreateListForm() {
    document.querySelector('#list_label').value = '';
    document.querySelector('#list_desc').value = '';
}

/**
 * Adds click listener to the given reading log button.
 *
 * On click, the patron's reading log will be updated, and the dropper
 * will be repainted with the new state.
 * @param {HTMLButtonElement} button Adds click listener to the given reading log button.
 */
function addReadingLogButtonClickListener(button) {
    button.addEventListener('click', function(event) {
        event.preventDefault();

        const form = button.parentElement
        const dropper = button.closest('.widget-add')
        const primaryButton = dropper.querySelector('.want-to-read')
        const initialText = primaryButton.children[1].innerText
        const dropClick = dropper.querySelector('.dropclick')

        primaryButton.children[1].innerText = 'saving...'

        const success = function() {
            if (button.classList.contains('want-to-read')) {
                // Primary button pressed
                // Toggle checkmark
                button.children[0].classList.toggle('hidden')

                // Toggle button class 'activated' <-> 'unactivated'
                button.classList.toggle('activated')
                button.classList.toggle('unactivated')

                // Toggle dropclick and arrow
                dropClick.classList.toggle('dropclick-activated')
                dropClick.classList.toggle('dropclick-unactivated')

                dropClick.children[0].classList.toggle('arrow-activated')
                dropClick.children[0].classList.toggle('arrow-unactivated')

                //Toggle action value 'add' <-> 'remove'
                const actionInput = form.querySelector('input[name=action]')
                if (actionInput.value === 'add') {
                    actionInput.value = 'remove'
                } else {
                    actionInput.value = 'add'
                }

                button.children[1].innerText = initialText

                // Close dropper if expanded:
                if ($(dropper).find('.arrow').first().hasClass('up')) {
                    toggleDropper(dropper)
                }
            } else {
                toggleDropper(dropper)
                // Secondary button pressed

                // Change primary button's text to new value:
                primaryButton.children[1].innerText = button.innerText

                // Show checkmark:
                primaryButton.children[0].classList.remove('hidden')

                // Ensure button and dropclick arrow have activated classes:
                primaryButton.classList.remove('unactivated')
                primaryButton.classList.add('activated')
                dropClick.classList.remove('dropclick-unactivated')
                dropClick.classList.add('dropclick-activated')
                dropClick.children[0].classList.remove('arrow-unactivated')
                dropClick.children[0].classList.add('arrow-activated')

                // Update primary form's hidden inputs:
                const newBookshelfId = button.parentElement.querySelector('input[name=bookshelf_id]').value
                dropper.querySelector('input[name=action]').value = 'remove'
                dropper.querySelector('input[name=bookshelf_id]').value = newBookshelfId

                // Hide clicked dropdown button, but show all others
                const dropdownButtons = dropper.querySelectorAll('.dropdown button')
                for (const btn of dropdownButtons) {
                    btn.classList.remove('hidden')
                }
                button.classList.add('hidden')
            }
        }

        updateReadingLog(form, success)
    })
}

/**
 * Adds click listeners to the given list items.
 *
 * Stores references to each given list item.
 * @param {HTMLCollection} listItemElements Collection of removeable list item elements.
 */
export function registerListItems(listItemElements) {
    for (const elem of listItemElements) {
        addRemoveClickListener(elem);

        const label = elem.querySelector('.label');
        const anchors = label.querySelectorAll('a');
        const listKey = anchors[1].dataset.listKey;

        if (actionableItems.hasOwnProperty(listKey)) {
            actionableItems[listKey].push(elem)
        } else {
            actionableItems[listKey] = [elem]
        }
    }
}

/**
 * Adds click listeners to the "[X]" anchor element of each given
 * removeable list item.
 *
 * On click, the item will be removed from the associated list, and all
 * corresponding removeable list item elements will be removed.
 *
 * @param {HTMLLIElement} elem A list item element that can be removed.
 */
function addRemoveClickListener(elem) {
    const label = elem.querySelector('.label');
    const anchors = label.querySelectorAll('a');
    const listTitle = anchors[0].dataset.listTitle;
    const listKey = anchors[1].dataset.listKey;
    const type = label.querySelector('input[name=seed-type]').value;
    const key = label.querySelector('input[name=seed-key]').value;

    const seed = type === 'subject' ? key : { key: key }

    anchors[1].addEventListener('click', function(event) {
        event.preventDefault()

        const successCallback = function() {
            // Update view:
            // 1. Remove this element from the view and map
            if (actionableItems.hasOwnProperty(listKey)) {
                for (const e of actionableItems[listKey]) {
                    e.remove()
                }
                delete actionableItems[listKey]
            }

            // If list missing from dropper:
            if (!dropperLists.hasOwnProperty(listKey)) {
                // 2. Add list item to dropper
                const coverUrl = elem.querySelector('img').src
                const p = updateDropperList(listKey, listTitle, coverUrl)

                // Add item to dropper list
                dropperLists[listKey] = {
                    title: listTitle,
                    element: p.children[0]
                }
            }
        }

        removeFromList(listKey, seed, successCallback)
    })
}

/**
 * Creates a new add-to-list dropper link element, attaches new element to the DOM,
 * and adds click listener to the element.
 *
 * @param {string} listKey The list's key, in the form "/people/{username}/lists/{list OLID}"
 * @param {string} listTitle The list's title
 * @param {string} coverUrl The list's cover image URL
 * @returns {HTMLParagraphElement} The newly created add-to-list link.
 */
function updateDropperList(listKey, listTitle, coverUrl) {
    const itemMarkUp = `<a href="${listKey}" class="add-to-list" data-list-cover-url="${coverUrl}" data-list-key="${listKey}">${listTitle}</a>`

    const p = document.createElement('p')
    p.classList.add('list')
    p.innerHTML = itemMarkUp
    const dropperList = document.querySelector('.my-lists');
    dropperList.appendChild(p)
    addListClickListener(p.children[0], p.closest('.widget-add'))

    return p
}

/**
 * Creates a new removeable list item element, attaches new element to the DOM, and adds click
 * listener to the element.
 *
 * @param {string} listKey    The list's key, in the form of "/people/{username}/lists/{list OLID}"
 * @param {string} listTitle  The name of the list.
 * @param {string} coverUrl   Location of the list's cover image.
 * @param {string} seedKey    The target seed's key.
 *
 * @returns {HTMLLIElement} The newly created list item element.
 */
function updateAlreadyList(listKey, listTitle, coverUrl, seedKey) {
    const alreadyLists = document.querySelector('.already-lists');
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

    addRemoveClickListener(li)

    return li;
}

/**
 * Initializes asynchronous list widget loading.
 *
 * Get references to all loading indicators and begins their animations.
 * Gets the edition or work key for the book referenced by the dropper, and
 * fetches HTML partials for the key.
 *
 * Once the partials are received, the loading indicators are replaced with the
 * partials, and click listeners are added to the new elements
 * @param {HTMLElement} dropperList Container for dropper list items
 * @param {HTMLElement} activeList Container for active lists list items
 */
export function initListLoading(dropperList, activeList) {
    const loadingIndicators = dropperList ? [dropperList.querySelector('.loading-ellipsis')] : []
    if (activeList) {
        loadingIndicators.push(activeList.querySelector('.loading-ellipsis'))
    }
    const intervalId = initLoadingAnimation(loadingIndicators)

    let key
    if (dropperList) {  // Not defined for logged out patrons
        if (dropperList.dataset.editionKey) {
            key = dropperList.dataset.editionKey
        } else if (dropperList.dataset.workKey) {
            key = dropperList.dataset.workKey
        }
    }

    if (key) {
        fetchPartials(key, function(data) {
            clearInterval(intervalId)
            replaceLoadingIndicators(dropperList, activeList, data)
        })
    } else {
        removeChildren(dropperList, activeList)
    }
}

/**
 * Animates ellipsis that follows the word "Loading"
 *
 * A new dot is appended every 1.5 seconds, until there
 * is a full ellipsis.  This cycle repeats indefinately.
 *
 * Returns an interval ID, which should be used to terminate
 * the `setInterval` call.
 * @param {HTMLElement[]} loadingIndicators References to the loading indicators
 * @returns {number} Interval ID returned by the internal `setInterval` call
 */
function initLoadingAnimation(loadingIndicators) {
    let count = 0;
    const intervalId = setInterval(function() {
        let ellipsis = ''
        for (let i = 0; i < count % 4; ++i) {
            ellipsis += '.'
        }
        for (const elem of loadingIndicators) {
            elem.innerText = ellipsis
        }
        ++count;
    }, 1500)

    return intervalId
}

/**
 * Replaces loading indicators with partials fetched from server.
 *
 * Adds click listeners to the newly added elements.
 *
 * @param {HTMLElement} dropperLists Dropper component that displays patron's lists
 * @param {HTMLElement} activeLists Component from which patron can remove an item from a list
 * @param {{dropper: string, active: string}} partials HTML for the active and dropper lists
 */
function replaceLoadingIndicators(dropperLists, activeLists, partials) {
    const dropperParent = dropperLists ? dropperLists.parentElement : null
    const activeListsParent = activeLists ? activeLists.parentElement : null

    if (dropperParent) {
        removeChildren(dropperParent)
        dropperParent.insertAdjacentHTML('afterbegin', partials['dropper'])

        const dropper = dropperParent.closest('.widget-add')
        const anchors = dropper.querySelectorAll('.add-to-list');
        initAddToListAnchors(anchors, dropper)
    }

    if (activeListsParent) {
        removeChildren(activeListsParent)
        activeListsParent.insertAdjacentHTML('afterbegin', partials['active'])
        const actionableListItems = activeListsParent.querySelectorAll('.actionable-item')
        registerListItems(actionableListItems)
    }
}

/**
 * Removes all child elements from each given element
 *
 * @param {HTMLElement} elem The element that we are removing children from
 */
function removeChildren(...elements) {
    for (const elem of elements) {
        if (elem) {
            while (elem.firstChild) {
                elem.removeChild(elem.firstChild)
            }
        }
    }
}
