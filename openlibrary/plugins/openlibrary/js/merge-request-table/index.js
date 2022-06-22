import { FadingToast } from '../Toast';

export function initCloseLinks(elems) {
    for (const elem of elems) {
        elem.addEventListener('click', function () {
            const mrid = elem.dataset.mrid
            onCloseClick(mrid, elem.parentNode.parentNode)
        })
    }
}

export function initCommentLinks(elems) {
    for (const elem of elems) {
        elem.addEventListener('click', function () {
            const mrid = elem.dataset.mrid
            onCommentClick(mrid)
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

async function onCommentClick(mrid) {
    const comment = promptForComment('Please enter your response.')
    if (comment !== null) {
        await commentOnRequest(mrid, comment)
            .then(result => result.json())
            .then(data => {
                if (data.status === 'ok') {
                    // We did it!
                    // Tell the submitter somehow
                    new FadingToast('Comment updated!').show()
                }
            })
            .catch(e => {
                throw e
            })
    }
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
