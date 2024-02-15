/**
 * Replaces loading indicators with partially rendered affiliate links.
 *
 * Fetches and attaches partials to DOM iff any of the given affiliate link
 * sections contain a loading indicator.
 *
 * @param {NodeList<HTMLElement>} affiliateLinksSections
 */
export function initAffiliateLinks(affiliateLinksSections) {
    if (Array.from(affiliateLinksSections).some((section) => hasLoadingIndicator(section))) {
        // Replace loading indicators with fetched partials

        const title = affiliateLinksSections[0].dataset.title
        const opts = JSON.parse(affiliateLinksSections[0].dataset.opts)
        const args = [title, opts]
        const d = {args: args}

        getPartials(d)
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
            .catch((error) => {
                // XXX : Handle errors sensibly
            })
    }
}

/**
 * Fetches rendered affiliate links template using the given arguments.
 *
 * @param {object} data Contains array of positional arguments for the template
 * @returns {Promise<Response>}
 */
async function getPartials(data) {
    const dataString = JSON.stringify(data)
    const dataQueryParam = encodeURIComponent(dataString)

    return fetch(`/partials.json?_component=AffiliateLinks&data=${dataQueryParam}`)
}

/**
 * Returns `true` if the given element contains a loading indicator.
 *
 * If a loading indicator is present, `data-async-load` will equal `true`.
 * @param {HTMLElement} affiliateLinkSection
 * @returns {boolean} `true` if a loading indicator is present in the section
 */
function hasLoadingIndicator(affiliateLinkSection) {
    const asyncLoad = affiliateLinkSection.dataset.asyncLoad
    return asyncLoad === 'true'
}
