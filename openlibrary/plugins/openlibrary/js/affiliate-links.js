/**
 * Adds functionality to fetch affialite links asyncronously.
 *
 * Fetches and attaches partials to DOM _iff_ any of the given affiliate link
 * sections contain a loading indicator.  Adds affordance for retrying if the
 * call for partials fails.
 *
 * @param {NodeList<HTMLElement>} affiliateLinksSections Collection of each affiliate links section that is on the page
 */
export function initAffiliateLinks(affiliateLinksSections) {
    const isLoading = showLoadingIndicators(affiliateLinksSections)
    if (isLoading) {
        // Replace loading indicators with fetched partials

        const title = affiliateLinksSections[0].dataset.title
        const opts = JSON.parse(affiliateLinksSections[0].dataset.opts)
        const args = [title, opts]
        const d = {args: args}

        getPartials(d, affiliateLinksSections)
    }
}

/**
 * Removes `hidden` class from any loading indicators nested within the given
 * elements.
 *
 * @param {NodeList<HTMLElement>} linkSections
 * @returns {boolean} `true` if a loading indicator is displayed on the screen
 */
function showLoadingIndicators(linkSections) {
    let isLoading = false
    for (const section of linkSections) {
        const loadingIndicator = section.querySelector('.loadingIndicator')
        if (loadingIndicator) {
            isLoading = true
            loadingIndicator.classList.remove('hidden')
        }
    }
    return isLoading
}

/**
 * Fetches rendered affiliate links template using the given arguments.
 *
 * @param {object} data Contains array of positional arguments for the template
 * @param {NodeList<HTMLElement>} affiliateLinksSections
 * @returns {Promise}
 */
async function getPartials(data, affiliateLinksSections) {
    const dataString = JSON.stringify(data)
    console.log('DATASTRING', dataString)
    const dataQueryParam = encodeURIComponent(dataString)

    return fetch(`/partials.json?_component=AffiliateLinks&data=${dataQueryParam}`)
        .then((resp) => {
            if (resp.status !== 200) {
                throw new Error(`Failed to fetch partials. Status code: ${resp.status}`)
            }
            return resp.json()
        })
        .then((data) => {
            const span = document.createElement('span')
            span.innerHTML = data['partials']
            const links = span.firstElementChild
            for (const section of affiliateLinksSections) {
                section.replaceWith(links.cloneNode(true))
            }
        })
        .catch(() => {
            // XXX : Handle errors sensibly
            for (const section of affiliateLinksSections) {
                const loadingIndicator = section.querySelector('.loadingIndicator')
                if (loadingIndicator) {
                    loadingIndicator.classList.add('hidden')
                }

                const existingRetryAffordance = section.querySelector('.affiliate-links-section__retry')
                if (existingRetryAffordance) {
                    existingRetryAffordance.classList.remove('hidden')
                } else {
                    section.insertAdjacentHTML('afterbegin', renderRetryLink())
                    const retryAffordance = section.querySelector('.affiliate-links-section__retry')
                    retryAffordance.addEventListener('click', () => {
                        retryAffordance.classList.add('hidden')
                        getPartials(data, affiliateLinksSections)
                    })
                }
            }
        })
}

/**
 * Returns HTML string with error message and retry link.
 *
 * @returns {string} HTML for a retry link.
 */
function renderRetryLink() {
    return '<span class="affiliate-links-section__retry">Failed to fetch affiliate links. <a href="javascript:;">Retry?</a></span>'
}
