export function initFulltextSearchSuggestion(fulltextSearchSuggestion) {
    const query = fulltextSearchSuggestion.dataset.query
    getPartials(fulltextSearchSuggestion, query)
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
        })
}
