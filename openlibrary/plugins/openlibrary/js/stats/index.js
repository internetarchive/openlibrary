/**
 * Fetches unique login counts and updates the view with the results.
 *
 * @param {HTMLElement} containerElem
 * @returns {Promise<void>}
 * @see /openlibrary/templates/admin/index.html
 */
export async function initUniqueLoginCounts(containerElem) {
    const loadingIndicator = containerElem.querySelector('.loadingIndicator')
    const i18nStrings = JSON.parse(containerElem.dataset.i18n)

    const counts = await fetchCounts()
        .then((resp) => {
            if (resp.status !== 200) {
                throw new Error(`Failed to fetch partials. Status code: ${resp.status}`)
            }
            return resp.json()
        })

    const countDiv = document.createElement('DIV')
    countDiv.innerHTML = i18nStrings.uniqueLoginsCopy
    const countSpan = countDiv.querySelector('.login-counts')
    countSpan.textContent = counts.loginCount
    loadingIndicator.replaceWith(countDiv)
}

/**
 * Fetches login counts from the server.
 *
 * @returns {Promise<Response>}
 * @see `monthly_logins` class in /openlibrary/plugins/openlibrary/api.py
 */
async function fetchCounts() {
    return fetch('/api/monthly_logins.json')
}
