import { FadingToast } from '../Toast';
import { commentOnRequest, declineRequest, claimRequest, unassignRequest } from './MergeRequestService';

let dropMenuButtons
let dropMenus

/**
 * Adds functionality for closing librarian requests.
 *
 * @param {NodeList<HTMLElement>} elems Elements that trigger request close updates
 */
export function initCloseLinks(elems) {
    for (const elem of elems) {
        elem.addEventListener('click', function () {
            const mrid = elem.dataset.mrid
            onCloseClick(mrid, elem.parentNode.parentNode)
        })
    }
}

/**
 * Closes librarian request with the given ID.
 *
 * Prompts patron for comment and close the given librarian request.
 * Removes the request's row from the UI on success.
 *
 * @param {Number} mrid Unique ID of the record that is being closed
 * @param {HTMLTableRowElement} parentRow The record's row in the request table
 */
async function onCloseClick(mrid, parentRow) {
    const comment = prompt('(Optional) Why are you closing this request?')
    if (comment !== null) {
        await close(mrid, comment)
            .then(result => result.json())
            .then(data => {
                if (data.status === 'ok') {
                    removeRow(parentRow)
                }
            })
            .catch(e => {
                throw e
            });
    }
}

/**
 * POSTs update to close a librarian request to Open Library's servers.
 *
 * @param {Number} mrid Unique identifier for a librarian request
 * @param {string} comment Message stating why the request was closed
 * @returns {Promise<Response>} The results of the update POST
 */
async function close(mrid, comment) {
    return declineRequest(mrid, comment)
}

/**
 * Adds functionality for commenting on librarian requests.
 *
 * @param {NodeList<HTMLElement>} elems Elements that trigger comments on requests
 */
export function initCommenting(elems) {
    for (const elem of elems) {
        elem.addEventListener('click', function () {
            const mrid = elem.dataset.mrid
            onCommentClick(elem.previousElementSibling, mrid)
        })
    }
}

/**
 * Comments on given librarian request and updates the UI.
 *
 * @param {HTMLTextAreaElement} textarea The element that contains the comment
 * @param {Number} mrid Unique identifier for the request that is being commented on
 */
async function onCommentClick(textarea, mrid) {
    const c = textarea.value;

    if (c) {
        await comment(mrid, c)
            .then(result => result.json())
            .then(data => {
                if (data.status === 'ok') {
                    new FadingToast('Comment updated!').show()
                    updateCommentsView(mrid, c)
                    textarea.value = ''
                } else {
                    new FadingToast('Failed to submit comment. Please try again in a few moments.').show()
                }
            })
            .catch(e => {
                throw e
            })
    }
}

/**
 * POSTs comment update to Open Library's servers.
 *
 * @param {Number} mrid Unique identifier for a librarian request
 * @param {string} comment The new comment
 * @returns {Promise<Response>} The results of the update POST request
 */
async function comment(mrid, comment) {
    return commentOnRequest(mrid, comment)
}

/**
 * Fetches comment HTML from server and updates table with the results.
 *
 * In the comment cell of the librarian request table, the most recent comment and
 * all other comments are in separate containers.  This function moves the previously
 * newest comment to the end of the old comments container, and adds the new comment
 * to the empty new comment container.
 *
 * @param {Number} mrid Unique identifier for the request that's being commented upon
 * @param {string} comment The new comment
 */
async function updateCommentsView(mrid, comment) {
    const commentCell = document.querySelector(`#comment-cell-${mrid}`)
    const newCommentDiv = commentCell.querySelector('.comment-cell__newest-comment')

    await fetch(`/merges/partials?type=comment&comment=${comment}`, {
        method: 'GET'
    })
        .then(result => result.text())
        .then(html => {
            // Create new comment element
            const template = document.createElement('template')
            template.innerHTML = html.trim()

            // Remove newest comment (or "No comments yet" message)
            const newestComment = newCommentDiv.firstElementChild
            newCommentDiv.removeChild(newestComment)

            if (newestComment.classList.contains('comment')) {  // "No comments yet" element will not have this class
                // Append newest comment to old comments element
                const oldComments = document.querySelector('.comment-cell__old-comments')
                oldComments.appendChild(newestComment)
            }

            // Display new
            newCommentDiv.appendChild(template.content.firstChild)
        })
}

/**
 * Removes the given row from the requests table.
 *
 * @param {HTMLTableRowElement} row The row being removed
 */
function removeRow(row) {
    row.parentNode.removeChild(row)
}

/**
 * Adds functionality for toggling visibility of older comments.
 *
 * @param {NodeList<HTMLElement>} elems Links that toggle comment visibility
 */
export function initShowAllCommentsLinks(elems) {
    for (const elem of elems) {
        elem.addEventListener('click', function() {
            toggleAllComments(elem)
        })
    }
}

/**
 * Toggles visibility of a request's older comments.
 *
 * @param {HTMLELement} elem Element which contains a reference to the old comments
 */
function toggleAllComments(elem) {
    const targetId = elem.dataset.targetId;
    const target = document.querySelector(`#${targetId}`)
    target.classList.toggle('hidden')

    const isHidden = target.classList.contains('hidden')
    const prevSibling = elem.previousElementSibling;
    if (isHidden) {
        prevSibling.textContent = 'Showing most recent comment only.'
        elem.textContent = 'View all'
    } else {
        prevSibling.textContent = 'Showing all comments.'
        elem.textContent = 'View most recent only'
    }
}

/**
 * Adds functionality for claiming librarian requests.
 *
 * @param {NodeList<HTMLElement>} elems Elements that, on click, initiates a claim
 */
export function initRequestClaiming(elems) {
    for (const elem of elems) {
        elem.addEventListener('click', function() {
            const mrid = elem.dataset.mrid
            claim(mrid, elem)
        })
    }
}

/**
 * Sends a claim request to the server and updates the table on success.
 *
 * @param {Number} mrid Unique identifier for the request being claimed
 */
async function claim(mrid) {
    await claimRequest(mrid)
        .then(result => result.json())
        .then(data => {
            if (data.status === 'ok') {
                const reviewerHtml = `${data.reviewer}
                    <span class="mr-unassign" data-mrid="${mrid}">&times;</span>`
                updateRow(mrid, data.newStatus, reviewerHtml)

                // Hide the row's merge link:
                const mergeLink = document.querySelector(`#mr-resolve-link-${mrid}`)
                if (!mergeLink.classList.contains('hidden')) {
                    toggleMergeLink(mergeLink)
                }
            }
        })
}

/**
 * Updates status and reviewer of the designated request table row.
 *
 * @param {Number} mrid The row's unique identifier
 * @param {string} status Optional new value for the row's status cell
 * @param {string} reviewer Optional new value for the row's reviewer cell
 */
function updateRow(mrid, status=null, reviewer=null) {
    if (status) {
        const statusCell = document.querySelector(`#status-cell-${mrid}`)
        statusCell.textContent = status
    }
    if (reviewer) {
        const reviewerCell = document.querySelector(`#reviewer-cell-${mrid}`)
        reviewerCell.innerHTML = reviewer

        initUnassignment(reviewerCell.querySelectorAll('.mr-unassign'))
    }
}

export function initUnassignment(elems) {
    for (const elem of elems) {
        elem.addEventListener('click', function() {
            const mrid = elem.dataset.mrid
            unassign(mrid)
        })
    }
}

async function unassign(mrid) {
    await unassignRequest(mrid)
        .then(result => result.json())
        .then(data => {
            if (data.status === 'ok') {
                updateRow(mrid, data.newStatus, ' ')

                // Display the row's merge link:
                const mergeLink = document.querySelector(`#mr-resolve-link-${mrid}`)
                if (mergeLink.classList.contains('hidden')) {
                    toggleMergeLink(mergeLink)
                }
            }
        })
}

/**
 * Toggles 'hidden' class for element with given ID.
 *
 * @param {HTMLElement} mergeLink Reference to a merge link element
 */
function toggleMergeLink(mergeLink) {
    if (mergeLink) {
        mergeLink.classList.toggle('hidden')
    }
}

/**
 * Toggle a dropdown menu while closing other dropdown menus.
 *
 * @param {Event} event
 * @param {string} menuButtonId
 */
function toggleAMenuWhileClosingOthers(event, menuButtonId) {
    // prevent closing of menu on bubbling unless click menuButton itself
    if (event.target.id === menuButtonId) {
        // close other open menus, then toggle selected menu
        closeOtherMenus(menuButtonId)
        event.target.firstElementChild.classList.toggle('hidden')
    }
}

/**
 * Close dropdown menus whose menu button doesn't match a given id.
 *
 * @param {string} menuButtonId
 */
function closeOtherMenus(menuButtonId) {
    dropMenuButtons.forEach((menuButton) => {
        if (menuButton.id !== menuButtonId) {
            menuButton.firstElementChild.classList.add('hidden')
        }
    })
}

/**
 * Filters of dropdown menu items using case-insensitive string matching.
 *
 * @param {Event} event
 */
function filterMenuItems(event) {
    const input = document.getElementById(event.target.id)
    const filter = input.value.toUpperCase()
    const menu = input.closest('.mr-dropdown-menu')
    const items = menu.getElementsByClassName('dropdown-item')
    // skip first item in menu
    for (let i=1; i < items.length; i++) {
        const text = items[i].textContent
        if (text.toUpperCase().indexOf(filter) > -1) {
            items[i].classList.remove('hidden')
        }
        else {
            items[i].classList.add('hidden')
        }
    }
}

/**
 * Close all dropdown menus when click anywhere on screen that's not part of
 * the dropdown menu; otherwise, keep dropdown menu open.
 *
 * @param {Event} event
 */
function closeMenusIfClickOutside(event) {
    const menusClicked = Array.from(dropMenuButtons).filter((menuButton) => {
        return menuButton.contains(event.target)
    })
    // want to preserve clicking in a menu, i.e. when filtering for users
    if (!menusClicked.length) {
        dropMenus.forEach((menu) => menu.classList.add('hidden'))
    }
}

/**
 * Initialize events for merge queue filter dropdown menu functionality.
 *
 */
export function initFilters() {
    dropMenuButtons = document.querySelectorAll('.mr-dropdown')
    dropMenus = document.querySelectorAll('.mr-dropdown-menu')
    dropMenuButtons.forEach((menuButton) => {
        menuButton.addEventListener('click', (event) => {
            toggleAMenuWhileClosingOthers(event, menuButton.id)
        })
    })
    const closeButtons = document.querySelectorAll('.dropdown-close')
    closeButtons.forEach((button) => {
        button.addEventListener('click', (event) => {
            event.target.closest('.mr-dropdown-menu').classList.toggle('hidden')
        })
    })
    const inputs = document.querySelectorAll('.filter')
    inputs.forEach((input) => {
        input.addEventListener('keyup', (event) => filterMenuItems(event))
    })
    document.addEventListener('click', (event) => closeMenusIfClickOutside(event))
}
