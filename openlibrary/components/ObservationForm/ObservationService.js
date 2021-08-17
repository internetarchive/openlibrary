/**
 * Sends a POST request to delete a patron's observation.
 *
 * @param {String} type The observation's type
 * @param {String} value The observation's value
 * @param {String} workKey Location of work, in the form `/works/<work OLID>`
 * @param {String} username Username of patron that is deleting an observation
 */
export function deleteObservation(type, value, workKey, username) {
    const data = constructDataObject(type, value, username, 'delete');

    fetch(`${workKey}/observations`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
}

/**
 * Sends a POST request to add a new patron observation about a work.
 *
 * @param {String} type The observation's type
 * @param {String} value The observation's value
 * @param {String} workKey Location of work, in the form `/works/<work OLID>`
 * @param {String} username Username of patron that is adding an observation
 */
export function addObservation(type, value, workKey, username) {
    const data = constructDataObject(type, value, username, 'add');
    fetch(`${workKey}/observations`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    })
}

/**
 * Creates an object that represents an update to a patron's observations.
 *
 * Data object is expected by the server to have the following form:
 * {
 *  "username": <username>,
 *  "action": <"add"|"delete">,
 *  "observation": {
 *   <type>: <value>
 *  }
 * }
 *
 * @param {String} type The observation type
 * @param {String} value The observation value
 * @param {String} username Username of patron making the update
 * @param {String} action 'add' for creating a new observation, or 'delete' for removing an existing one
 * @returns An object that represents the observation update that will be made.
 */
function constructDataObject(type, value, username, action) {
    const data = {
        username: username,
        action: action,
        observation: {}
    }

    data.observation[type.toLowerCase()] = value.toLowerCase();

    return data;
}
