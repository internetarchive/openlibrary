import { initAsyncFollowing } from '../following';
import { buildPartialsUrl } from '../utils'

/**
 * Fetches and displays the activity feed for a "My Books" page.
 *
 * @param {HTMLElement} elem - Container for the activity feed
 * @returns {Promise<void>}
 *
 * @see `/openlibrary/templates/account/activity_feed.html` for activity feed template
 */
export async function initActivityFeedRequest(elem) {
    const fullPath = window.location.pathname
    const splitPath = fullPath.split('/')
    const username = splitPath[2]  // Assumes an activity feed can only appear on the patron's "My Books" page

    const loadingIndicator = elem.querySelector('.loadingIndicator')
    const retryElem = elem.querySelector('.retry-fetch')

    function fetchPartialsAndUpdatePage() {
        return fetch(buildPartialsUrl('ActivityFeed', {username: username}))
            .then(resp => {
                if (!resp.ok) {
                    throw Error('Failed to fetch partials')
                }
                return resp.json()
            })
            .then(data => {
                const div = document.createElement('div')
                div.innerHTML = data.partials.trim()
                const followButtons = div.querySelectorAll('.follow-form')
                initAsyncFollowing(followButtons)
                loadingIndicator.classList.add('hidden')
                for (const child of Array.from(div.children)) {
                    elem.insertAdjacentElement('beforeend', child)
                }
            })
            .catch(() => {
                // Show retry affordance
                loadingIndicator.classList.add('hidden')
                retryElem.classList.remove('hidden')
            })
    }

    // Hydrate retry button
    retryElem.addEventListener('click', async () => {
        retryElem.classList.add('hidden')
        loadingIndicator.classList.remove('hidden')
        await fetchPartialsAndUpdatePage()
    })

    await fetchPartialsAndUpdatePage()
}
