/**
 * Service layer for the /status Testing Environment panel.
 *
 * The read path is FastAPI JSON. Mutations remain on the existing web.py
 * handlers and are followed by a fresh JSON read so the client has one source
 * of truth for rendering.
 */

/**
 * Return the same-origin JSON endpoint for the current deployment.
 *
 * The testing site exposes FastAPI behind /_fast; local development proxies
 * the unprefixed path through web.py to the FastAPI container.
 *
 * @param {Location|Object} location Browser location, or a hostname-shaped
 * object for tests.
 * @return {String}
 */
export function testingStatusUrl(location = window.location) {
    return location.hostname === 'testing.openlibrary.org'
        ? '/_fast/status/testing.json'
        : '/status/testing.json';
}

/**
 * Fetch the testing-environment state.
 *
 * @return {Promise<Object>}
 */
export async function getTestingStatus() {
    const response = await fetch(testingStatusUrl(), {
        headers: { Accept: 'application/json' },
        credentials: 'same-origin'
    });
    if (!response.ok) {
        throw new Error(`Testing status failed: ${response.status}`);
    }
    return response.json();
}

/**
 * POST an action and return its response. The legacy handlers redirect to
 * /status; callers intentionally discard that HTML and fetch JSON afterward.
 *
 * @param {String} action Endpoint path, e.g. '/status/pull-latest'
 * @param {Object} fields Form fields. Array values are repeated, matching
 *   how web.input(prs=[]) expects multiple checkboxes.
 * @return {Promise<Response>}
 */
export async function postAction(action, fields = {}) {
    const body = new URLSearchParams();
    for (const [key, value] of Object.entries(fields)) {
        if (Array.isArray(value)) {
            value.forEach((item) => body.append(key, item));
        } else {
            body.append(key, value);
        }
    }

    const response = await fetch(action, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        credentials: 'same-origin',
        body
    });
    if (!response.ok) {
        throw new Error(`${action} failed: ${response.status}`);
    }
    return response;
}
