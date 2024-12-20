/**
 * Defines functions for calling internal list and reading log APIs.
 * @module lists/ListService
 */

/**
 * Makes a POST to a `.json` endpoint.
 * @param {object} data Configurations and payload for POST request.
 */
function post(data) {
    $.ajax({
        type: 'POST',
        url: data.url,
        contentType: 'application/json',
        data: JSON.stringify(data.data),
        dataType: 'json',

        beforeSend: function(xhr) {
            xhr.setRequestHeader('Content-Type', 'application/json');
            xhr.setRequestHeader('Accept', 'application/json');
        },
        success: data.success,
        complete: data.complete
    });
}

/**
 * Submits request to create new list,
 *
 * Executes given callback on success.
 * @param {string} userKey The patron's key, in the form "/people/{username}".
 * @param {object} data Object containing the new list's name, description, and seeds.
 * @param {function} success Callback to be executed on successful POST.
 */
export function createNewList(userKey, data, success) {
    post({
        url: `${userKey}/lists.json`,
        data: data,
        success: function(resp) {
            success(resp.key, data.name)
        }
    });
}

/**
 * Submits request to create new list.  Returns Promise.
 *
 * @param {string} userKey The patron's key, in the form "/people/{username}"
 * @param {object} data Object containing the new list's name, description, and seeds.
 * @returns {Promise<Response>} The results of the POST request
 */
export async function createList(userKey, data) {
    return await fetch(`${userKey}/lists.json`, {
        method: 'post',
        headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json'
        },
        body: JSON.stringify(data)
    })
}

/**
 * Submits request to add given seed to list.
 *
 * Executes given callback on success.
 * @param {string} listKey The list's key.
 * @param {string|{ key: string }} seed The item being added to the list.
 * @param {function} success Callback to be executed on successful POST.
 */
export function addToList(listKey, seed, success) {
    post({
        url: `${listKey}/seeds.json`,
        data: { add: [seed] },
        success: success
    });
}

/**
 * Adds an item to a list.  Promise-based.
 *
 * @param {string} listKey The patron's key, in the form "/people/{username}"
 * @param {object} seed Object containing the new list's name, description, and seeds.
 * @returns {Promise<Response>} The result of the POST request
 */
export async function addItem(listKey, seed) {
    const body = { add: [seed] }
    return await fetch(`${listKey}/seeds.json`, {
        method: 'post',
        headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json'
        },
        body: JSON.stringify(body)
    })
}

/**
 * Submits request to remove given seed from list.
 *
 * Executes given callback on success.
 * @param {string} listKey The list's key.
 * @param {string|{ key: string }} seed The item being removed from the list.
 * @param {function} success Callback to be executed on successful POST.
 */
export function removeFromList(listKey, seed, success) {
    post({
        url: `${listKey}/seeds.json`,
        data: { remove: [seed] },
        success: success
    });
}

/**
 * Submits request to remove given seed from list. Promise-based.
 *
 * @param {string} listKey The list's key.
 * @param {string|{ key: string }} seed The item being removed from the list.
 * @returns {Promise<Response>} The POST response
 */
export async function removeItem(listKey, seed) {
    const body = { remove: [seed] }
    return await fetch(`${listKey}/seeds.json`, {
        method: 'post',
        headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json'
        },
        body: JSON.stringify(body)
    })
}

/**
 * Submits reading log update form data and executes the given callback on success.
 *
 * @param {HTMLFormElement} formElem Reference to the submitted form.
 * @param {function} success Callback to be executed on successful POST.
 */
export function updateReadingLog(formElem, success) {
    const formData = new FormData(formElem)

    $.ajax({
        type: 'POST',
        url: formElem.getAttribute('action'),
        data: formData,
        processData: false,
        contentType: false,
        success: success
    })
}

/**
 * Fetches HTML for list components
 *
 * @param {string} key Key of record that can be added/removed to the list
 * @param {function} success Callback to be executed on fetch success
 */
export function fetchPartials(key, success) {
    $.ajax({
        type: 'GET',
        url: `/lists/partials.json?key=${key}`,
        success: success
    })
}

// XXX : jsdoc
export async function getListPartials() {
    return await fetch('/lists/partials.json', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json'
        }
    })
}
