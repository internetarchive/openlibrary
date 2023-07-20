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
            onCloseClick(mrid, elem.parentNode.parentNode.parentNode.parentNode)
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
            const username = elem.dataset.username;
            onCommentClick(elem.previousElementSibling, mrid, username)
        })
    }
}

/**
 * Comments on given librarian request and updates the UI.
 *
 * @param {HTMLTextAreaElement} textarea The element that contains the comment
 * @param {Number} mrid Unique identifier for the request that is being commented on
 */
async function onCommentClick(textarea, mrid, username) {
    const c = textarea.value;
    const commentCount = document.querySelector(`.comment-count-${mrid}`);

    if (c) {
        await comment(mrid, c)
            .then(result => result.json())
            .then(data => {
                if (data.status === 'ok') {
                    new FadingToast('Comment updated!').show()
                    updateCommentsView(mrid, c, username)
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
async function updateCommentsView(mrid, comment, username) {
    const commentCell = document.querySelector(`#comment-cell-${mrid}`);
    const hiddenCommentDiv = commentCell.querySelector('.comment-cell__old-comments-section');
    const newestComment = commentCell.querySelector('.comment-cell__newest-comment') ;

    newestComment.innerHTML = `${comment}`

    const newComment = document.createElement('div')
    newComment.innerHTML += `<div class="mr-comment__body"><span>@${username}</span> ${comment}</div>`

    hiddenCommentDiv.append(newComment);
    hiddenCommentDiv.scrollTop = hiddenCommentDiv.scrollHeight;
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
    const targetHiddenComments = elem.dataset.hiddenComments;
    const targetLatestComment = elem.dataset.latestComment || 0;
    const targetIdOldComments = elem.dataset.oldComments;
    const targetBtnComments = elem.dataset.btnComments;

    const hiddenCommentsTarget = document.querySelector(`#${targetHiddenComments}`)
    const latestCommentTarget = document.querySelector(`#${targetLatestComment}`)
    const oldCommentsTarget = document.querySelector(`#${targetIdOldComments}`)
    const targetCommentsBtn = document.querySelector(`.${targetBtnComments}`);

    hiddenCommentsTarget.classList.toggle('hidden')
    latestCommentTarget.classList.toggle('hidden')
    targetCommentsBtn.classList.toggle('border-toggle');

    oldCommentsTarget.scrollTop = oldCommentsTarget.scrollHeight;
}

export function initRequestClaiming(elems) {
    for (const elem of elems) {
        const mrid = elem.dataset.mrid;
        const unassignElements = document.querySelectorAll(`.mr-unassign[data-mrid="${mrid}"]`);

        if (unassignElements.length > 0) {
            const mergeBtn = document.querySelector(`#mr-resolve-btn-${mrid}`);
            mergeBtn.classList.add('hidden');
        }

        elem.addEventListener('click', function() {
            claim(mrid, elem);
        });
    }
}

async function claim(mrid) {
    await claimRequest(mrid)
        .then(result => result.json())
        .then(data => {
            if (data.status === 'ok') {
                const reviewerHtml = `${data.reviewer}
                    <span class="mr-unassign" data-mrid="${mrid}">&times;</span>`;
                const unassignElements = document.querySelectorAll(`.mr-unassign[data-mrid="${mrid}"]`);
                //for hiding the button it is being unassigned
                const mergeBtn = document.querySelector(`#mr-resolve-btn-${mrid}`);
                if (unassignElements.length > 0) {
                    mergeBtn.classList.add('hidden');
                }

                updateRow(mrid, data.newStatus, reviewerHtml, mergeBtn);
                toggleMergeLink(mrid, mergeBtn);
            }
        })
}


/**
 * Updates status and reviewer of the designated request table row.
 *
 * @param {Number} mrid The row's unique identifier
 * @param {string} status Optional new value for the row's status cell
 * @param {string} reviewer Optional new value for the row's reviewer cell
 * @param {Object} mergeLinkData Data from the resolve link to be passed into the "REVIEW" button toggle
 */
function updateRow(mrid, status=null, reviewer=null, btn) {
    if (reviewer) {
        const reviewerCell = document.querySelector(`#reviewer-cell-${mrid}`)
        reviewerCell.innerHTML = reviewer

        initUnassignment(reviewerCell.querySelectorAll('.mr-unassign'), btn)
    }
}

export function initUnassignment(elems, mergeLinkData) {

    for (const elem of elems) {
        elem.addEventListener('click', function() {
            const mrid = elem.dataset.mrid
            const btn = document.querySelector(`#mr-resolve-btn-${mrid}`)
            unassign(mrid, btn)
        })
    }
}

async function unassign(mrid, btn) {
    await unassignRequest(mrid, btn)
        .then(result => result.json())
        .then(data => {
            if (data.status === 'ok') {
                updateRow(mrid, data.newStatus, ' ', btn)
                toggleMergeLink(mrid, btn)
            }
        })

}

/**
 * Toggles hidden class on review button
 *
 * @param {Number} mrid Unique identifier for the request being claimed
 */
function toggleMergeLink(mrid, btn) {

    if (btn.classList.contains('hidden')){
        btn.classList.remove('hidden');
    } else {
        btn.classList.add('hidden');
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
