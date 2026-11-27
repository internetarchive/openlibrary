import { _ } from '../i18n.js';

/**
 * Fetches unique login counts and updates the view with the results.
 *
 * @param {HTMLElement} containerElem
 * @returns {Promise<void>}
 * @see /openlibrary/templates/admin/index.html
 */
export async function initUniqueLoginCounts(containerElem) {
    const loadingIndicator = containerElem.querySelector('.loadingIndicator');

    const counts = await fetchCounts().then(resp => {
        if (resp.status !== 200) {
            throw new Error(`Failed to fetch partials. Status code: ${resp.status}`);
        }
        return resp.json();
    });

    const countDiv = document.createElement('DIV');
    countDiv.innerHTML = _('<span class="login-counts">0</span> patrons have logged in at least once over the past 30 days.');
    const countSpan = countDiv.querySelector('.login-counts');
    countSpan.textContent = counts.loginCount;
    loadingIndicator.replaceWith(countDiv);
}

/**
 * Fetches login counts from the server.
 *
 * @returns {Promise<Response>}
 * @see `monthly_logins` class in /openlibrary/plugins/openlibrary/api.py
 */
async function fetchCounts() {
    return fetch('/api/monthly_logins.json');
}
