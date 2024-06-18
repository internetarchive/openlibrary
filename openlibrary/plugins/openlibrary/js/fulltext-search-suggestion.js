export function initFulltextSearchSuggestion(fulltextSearchSuggestion) {
    const isLoading = showLoadingIndicators(fulltextSearchSuggestion)
    if(isLoading) {
        const query = fulltextSearchSuggestion.dataset.query
        getPartials(fulltextSearchSuggestion, query)
    }
}

function showLoadingIndicators(fulltextSearchSuggestion) {
    let isLoading = false
    const loadingIndicator = fulltextSearchSuggestion.querySelector('.loadingIndicator')
        if (loadingIndicator) {
            isLoading = true
            loadingIndicator.classList.remove('hidden')
        }

    return isLoading
}
async function getPartials(fulltextSearchSuggestion, query) {
    const queryParam = encodeURIComponent(query)
    return fetch(`/partials.json?_component=FulltextSearchSuggestion&data=${queryParam}`)
        .then((resp) => {
            if (resp.status !== 200) {
                throw new Error(`Failed to fetch partials. Status code: ${resp.status}`)
            }
            return resp.json()
        })
        .then((data) => {
            fulltextSearchSuggestion.innerHTML += data['partials']
            const loadingIndicator = fulltextSearchSuggestion.querySelector('.loadingIndicator');
            if (loadingIndicator) {
                loadingIndicator.classList.add('hidden')
            }
        })
        .catch(() => {
            const loadingIndicator = section.querySelector('.loadingIndicator')
            if (loadingIndicator) {
                loadingIndicator.classList.add('hidden')
            }
            const existingRetryAffordance = section.querySelector('.fulltext-search-suggestion__retry')
            if (existingRetryAffordance) {
                existingRetryAffordance.classList.remove('hidden')
            } else {
                section.insertAdjacentHTML('afterbegin', renderRetryLink())
                const retryAffordance = section.querySelector('.affiliate-links-section__retry')
                retryAffordance.addEventListener('click', () => {
                    retryAffordance.classList.add('hidden')
                    getPartials(fulltextSearchSuggestion, query)
                })
            }

        })
}

/**
 * Returns HTML string with error message and retry link.
 *
 * @returns {string} HTML for a retry link.
 */
function renderRetryLink() {
    return '<span class="fulltext-search-suggestion__retry">Failed to fetch fulltext search suggestions. <a href="javascript:;">Retry?</a></span>'
}
