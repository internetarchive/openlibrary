import { FadingToast } from '../Toast';

export function initCloseLinks(elems) {
    for (const elem of elems) {
        elem.addEventListener('click', function () {
            const mrid = elem.dataset.mrid
            onCloseClick(mrid, elem.parentNode.parentNode)
        })
    }
}

export function initCommenting(elems) {
    for (const elem of elems) {
        elem.addEventListener('click', function () {
            const mrid = elem.dataset.mrid
            onCommentClick(elem, mrid)
        })
    }
}

async function onCloseClick(mrid, parentRow) {
    const comment = promptForComment('(Optional) Why are you closing this request?')
    if (comment !== null) {
        await closeRequest(mrid, comment)
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

async function onCommentClick(elem, mrid) {
    const textarea = elem.previousElementSibling
    const comment = textarea.value;

    if (comment) {
        await commentOnRequest(mrid, comment)
            .then(result => result.json())
            .then(data => {
                if (data.status === 'ok') {
                    new FadingToast('Comment updated!').show()
                    updateCommentsView(mrid, comment)
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

            // Remove newest comment (or "No comments yet" message)
            const newestComment = newCommentDiv.firstElementChild
            newCommentDiv.removeChild(newestComment)

            if (newestComment.classList.contains('comment')) {  // This is actually a comment
                // Append newest comment to old comments element
                const oldComments = document.querySelector('.comment-cell__old-comments')
                oldComments.appendChild(newestComment)
            }

            // Display new comment
            newCommentDiv.appendChild(template.content.firstChild)
        })

}

function promptForComment(msg) {
    return prompt(msg)
}

async function updateRequest(action, mrid, comment = null) {
    const formData = new FormData();
    formData.set('mrid', mrid)
    formData.set('action', action)
    if (comment) {
        formData.set('comment', comment)
    }

    return fetch('/merges', {
        method: 'POST',
        body: formData
    })
}

async function closeRequest(mrid, comment) {
    return updateRequest('decline', mrid, comment)
}

async function commentOnRequest(mrid, comment) {
    return updateRequest('comment', mrid, comment)
}

function removeRow(row) {
    row.parentNode.removeChild(row)
}

export function initShowAllCommentsLinks(elems) {
    for (const elem of elems) {
        elem.addEventListener('click', function() {
            toggleAllComments(elem)
        })
    }
}

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
