/**
 * Defines functions for calling internal list and reading log APIs.
 * @module lists/ListService
 */

import { buildPartialsUrl } from '../utils';

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
            Accept: 'application/json',
        },
        body: JSON.stringify(data),
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
    const body = { add: [seed] };
    return await fetch(`${listKey}/seeds.json`, {
        method: 'post',
        headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
        },
        body: JSON.stringify(body),
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
    const body = { remove: [seed] };
    return await fetch(`${listKey}/seeds.json`, {
        method: 'post',
        headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
        },
        body: JSON.stringify(body),
    });
}

// XXX : jsdoc
// export async function getListPartials() {
//     return await fetch(buildPartialsUrl('/lists/partials.json'), {
//         method: 'GET',
//         headers: {
//             'Content-Type': 'application/json',
//             Accept: 'application/json',
//         },
//     });
// }
export async function getListPartials() {
    return await fetch(buildPartialsUrl('/partials.json', {
        _component: 'MyBooksDropperLists'
    }), {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
        },
    });
}

