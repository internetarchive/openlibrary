export function initFulltextSearchBox(fulltextSearchBox) {
    console.log('MACRO HATH LOADED')
    const query = fulltextSearchBox.dataset.query
    getPartials(fulltextSearchBox, query)
}

async function getPartials(fulltextSearchBox, query) {
    const queryParam = encodeURIComponent(query)
    return fetch(`/partials.json?_component=FulltextSearchBox&data=${queryParam}`)
        .then((resp) => {
            if (resp.status !== 200) {
                throw new Error(`Failed to fetch partials. Status code: ${resp.status}`)
            }
            return resp.json()
        })
        .then((data) => {
            console.log('DATA FROM PARTIAL CALL', data['data'])
            fulltextSearchBox.innerHTML += data['partials']
        })
}
