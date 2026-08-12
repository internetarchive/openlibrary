/**
 * Service layer for the /status Testing Environment table.
 *
 * Talks to the existing web.py endpoints (/status/add, /status/enable, …).
 * Those return a 303 to /status, so `fetch` follows the redirect and hands
 * back the freshly rendered page — one round trip per action instead of
 * "mutate, then re-read".
 *
 * Note on /status/testing.json: the FastAPI endpoint is only same-origin
 * behind the production `/_fast` proxy. Locally FastAPI is a separate origin
 * and its CORS config sets allow_credentials=false, so a cookie-authenticated
 * browser call cannot work there. Reading the server-rendered page keeps this
 * identical across dev, testing, and production.
 */

/**
 * POST an action and return the resulting /status document.
 *
 * @param {String} action Endpoint path, e.g. '/status/pull-latest'
 * @param {Object} fields Form fields. Array values are repeated, matching
 *   how web.input(prs=[]) expects multiple checkboxes.
 * @return {Promise<Document>}
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
        body
    });
    if (!response.ok) {
        throw new Error(`${action} failed: ${response.status}`);
    }
    return new DOMParser().parseFromString(await response.text(), 'text/html');
}
