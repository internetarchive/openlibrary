export function initFulltextSearchSuggestion(fulltextSearchSuggestion) {
    const isLoading = showLoadingIndicators(fulltextSearchSuggestion)
    if(isLoading) {
        const query = fulltextSearchSuggestion.dataset.query
        getPartials(fulltextSearchSuggestion, query)
    }
}

function showLoadingIndicators(searchSuggestion) {
    let isLoading = false
    const loadingIndicator = searchSuggestion.querySelector('.loadingIndicator')
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
            // console.log('DATA FROM PARTIAL', data['data'])
            fulltextSearchSuggestion.innerHTML += data['partials']
            const loadingIndicator = fulltextSearchSuggestion.querySelector('.loadingIndicator');
            if (loadingIndicator) {
                console.log('loadingindicator!')
                loadingIndicator.classList.add('hidden')
            }
        })
}
