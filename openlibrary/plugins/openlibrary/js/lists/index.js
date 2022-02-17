import { createList, addToList, removeFromList } from './ListService'

const actionableItems = {}
const dropperLists = {}

export function initDroppers(droppers) {
    addListeners(droppers);
}

function addListeners(listComponents) {
    for (const dropper of listComponents) {
        const anchors = dropper.querySelectorAll('.add-to-list');

        for (const anchor of anchors) {
            dropperLists[anchor.dataset.listKey] = {
                title: anchor.innerText,
                element: anchor
            }
            addListClickListener(anchor, dropper);
        }

        const createListButton = dropper.querySelector('.create-new-list')
        addCreateListClickListener(createListButton, dropper)
    }
}

function addListClickListener(elem, parentDropper) {
    elem.addEventListener('click', function(event){
        event.preventDefault()
        // Add book to list
        const workCheckBox = parentDropper.querySelector('.work-checkbox');
        const hiddenWorkInput = parentDropper.querySelector('input[name=work_id]')
        const hiddenKeyInput = parentDropper.querySelector('input[name=default-key]')

        let seed;
        const isWork = workCheckBox && workCheckBox.checked

        if (isWork) {
            seed = hiddenWorkInput.value
        } else {
            seed = hiddenKeyInput.value
        }

        const listKey = elem.dataset.listKey;

        const successCallback = function() {
            if (!isWork) {
                const listTitle = elem.innerText;
                const listUrl = elem.dataset.listCoverUrl
                const li = updateAlreadyList(listKey, listTitle, listUrl)

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
            $(parentDropper).find('.dropdown').first().slideToggle(25);
            $(parentDropper).find('.arrow').first().toggleClass('up');
        }

        addToList(listKey, seed, successCallback)

    })
}

function addCreateListClickListener(submitButton, parentDropper) {
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

    const createListButton = document.querySelector('#create-list-button')
    if (createListButton) {
        const nameField = document.querySelector('#list_label');
        const descriptionField = document.querySelector('#list_desc')
        const workCheckBox = parentDropper.querySelector('.work-checkbox')
        const hiddenWorkInput = parentDropper.querySelector('input[name=work_id]')
        const hiddenKeyInput = parentDropper.querySelector('input[name=default-key]')
        const hiddenUserInput = parentDropper.querySelector('input[name=user-key]')

        createListButton.addEventListener('click', function(event){
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
                    name: nameField.value,
                    description: descriptionField.value,
                    seeds: [seed],
                }

                const successCallback = function(listKey, listTitle) {
                    // Add actionable item to view, map
                    const li = updateAlreadyList(listKey, listTitle, '/images/icons/avatar_book-sm.png')
                    actionableItems[listKey] = [li]
                }

                createList(hiddenUserInput.value, data, successCallback)

                // Close colorbox
                $.colorbox.close()
            }
        })
    }
}

function clearCreateListForm() {
    document.querySelector('#list_label').value = '';
    document.querySelector('#list_desc').value = '';
}

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

function addRemoveClickListener(elem) {
    const label = elem.querySelector('.label');
    const anchors = label.querySelectorAll('a');
    const listTitle = anchors[0].dataset.listTitle;
    const listKey = anchors[1].dataset.listKey;
    const seed = label.querySelector('input[name=seed-key').value;
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

function updateAlreadyList(listKey, listTitle, listUrl) {
    const alreadyLists = document.querySelector('.already-lists');
    const splitKey = listKey.split('/')
    const userKey = `/${splitKey[1]}/${splitKey[2]}`
    const itemMarkUp = `<span class="image">
          <a href="${listKey}"><img src="${listUrl}" alt="Cover of: ${listTitle}" title="Cover of: ${listTitle}"/></a>
        </span>
        <span class="data">
            <span class="label">
                <a href="${listKey}" data-list-title="${listTitle}" title="See this list">${listTitle}</a>
                <input type="hidden" name="seed-title" value="${listTitle}"/>
                <input type="hidden" name="seed-key" value="${listKey}"/>
                <input type="hidden" name="seed-type" value="edition"/>
                <a href="${listKey}" class="remove-from-list red smaller arial plain" data-list-key="${listKey}" title="Remove from your list?">[X]</a>
            </span>
            <span class="owner">from <a href="${userKey}">You</a></span>
        </span>`

    const li = document.createElement('li')
    li.classList.add('actionable-item')
    li.innerHTML = itemMarkUp
    alreadyLists.appendChild(li)

    addRemoveClickListener(li)

    return li;
}
