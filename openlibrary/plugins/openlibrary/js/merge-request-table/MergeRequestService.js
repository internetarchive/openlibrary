
export const REQUEST_TYPES = {
  WORK_MERGE: 1,
  AUTHOR_MERGE: 2
}

export async function createRequest(olids, action, type, comment = null, primary = null) {
  const data = {
    rtype: 'create-request',
    action: action,
    mr_type: type,
    olids: olids
  }
  if (comment) {
    data['comment'] = comment
  }
  if (primary) {
    data['primary'] = primary
  }

  return fetch('/merges', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
  })
}

/**
 * Updates an existing librarian request.
 *
 * @param {'comment'|'claim'|'approve'|'decline'} action Denotes the type of update being sent
 * @param {Number} mrid Unique ID of the request that's being updated
 * @param {string} comment Optional comment about the update
 * @returns {Promise<Response>}
 */
async function updateRequest(action, mrid, comment = null) {
  const data = {
    rtype: 'update-request',
    action: action,
    mrid: mrid
  }
  if (comment) {
    data['comment'] = comment
  }

  return fetch('/merges', {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(data)
  })
}

/**
 * POSTs comment update to Open Library's servers.
 *
 * @param {Number} mrid Unique identifier for a librarian request
 * @param {string} comment The new comment
 * @returns {Promise<Response>} The results of the update POST request
 */
export async function commentOnRequest(mrid, comment) {
  return updateRequest('comment', mrid, comment)
}

/**
 * Sends a claim request to the server.
 *
 * @param {Number} mrid Unique identifier for the request being claimed
 */
export async function claimRequest(mrid) {
  return updateRequest('claim', mrid)
}

export async function unassignRequest(mrid) {
  return updateRequest('unassign', mrid)
}

export async function declineRequest(mrid, comment) {
  return updateRequest('decline', mrid, comment)
}

export async function approveRequest(mrid, comment) {
  return updateRequest('approve', mrid, comment)
}
