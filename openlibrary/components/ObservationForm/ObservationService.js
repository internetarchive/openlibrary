/**
 * Sends a POST request to add or delete a patron's observation.
 *
 * @param {'add' | 'delete'} action 'add' if an observation is being created, 'delete' if an observation is being deleted.
 * @param {String} type The observation's type
 * @param {String} value The observation's value
 * @param {String} workKey Location of work, in the form `/works/<work OLID>`
 * @param {String} username Username of patron that is updating an observation
 *
 * @returns A Promise representing the state of the POST request.
 */
export function updateObservation(action, type, value, workKey, username) {
  const data = constructDataObject(type, value, username, action)

  return fetch(`${workKey}/observations`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
  })
    .then(response => {
      if (!response.ok) {
        throw new Error('Server response was not ok')
      }
    })
    .catch(error => {
      throw error
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
 * @param {'add' | 'delete'} action 'add' for creating a new observation, or 'delete' for removing an existing one
 * @returns An object that represents the observation update that will be made.
 */
function constructDataObject(type, value, username, action) {
  const data = {
    username: username,
    action: action,
    observation: {}
  }

  data.observation[type] = value;

  return data;
}
