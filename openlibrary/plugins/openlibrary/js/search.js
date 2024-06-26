/**
 * Functionalities for templates/work_search.
 */

/**
 * Displays more facets by removing the ui-helper-hidden class.
 *
 * @param {String} header class name
 * @param {Number} start_facet_count initial number of displayed facets
 * @param {Number} facet_inc number of hidden facets to be displayed
 */
export function more(header, start_facet_count, facet_inc) {
    const facetEntry = `div.${header} div.facetEntry`
    const shown = $(`${facetEntry}:not(:hidden)`).length
    const total = $(facetEntry).length
    if (shown === start_facet_count) {
        $(`#${header}_less`).show();
        $(`#${header}_bull`).show();
    }
    if (shown + facet_inc >= total) {
        $(`#${header}_more`).hide();
        $(`#${header}_bull`).hide();
    }
    $(`${facetEntry}:hidden`).slice(0, facet_inc).removeClass('ui-helper-hidden');
}

/**
 * Hides facets by adding the ui-helper-hidden class.
 *
 * @param {String} header class name
 * @param {Number} start_facet_count initial number of displayed facets
 * @param {Number} facet_inc number of displayed facets to be hidden
 */
export function less(header, start_facet_count, facet_inc) {
    const facetEntry = `div.${header} div.facetEntry`
    const shown = $(`${facetEntry}:not(:hidden)`).length
    const total = $(facetEntry).length
    const increment_extra = (shown - start_facet_count) % facet_inc;
    const facet_dec = (increment_extra === 0) ? facet_inc:increment_extra;
    const next_shown = Math.max(start_facet_count, shown - facet_dec);
    if (shown === total) {
        $(`#${header}_more`).show();
        $(`#${header}_bull`).show();
    }
    if (next_shown === start_facet_count) {
        $(`#${header}_less`).hide();
        $(`#${header}_bull`).hide();
    }
    $(`${facetEntry}:not(:hidden)`).slice(next_shown, shown).addClass('ui-helper-hidden');
}

/**
 * Initializes the search page's facets sidebar.
 *
 * If the search facets sidebar is in `asyncLoad` mode, the sidebar will contain loading
 * indicators instead of facet counts.  In this case, a request is made for sidebar markup
 * containing the actual counts, and the existing sidebar is replaced with the new sidebar.
 *
 * In either case, the sidebar is hydrated.
 *
 * @param {HTMLElement} facetsElem Root element of the search facets sidebar component
 */
export function initSearchFacets(facetsElem) {
    const asyncLoad = facetsElem.dataset.asyncLoad

    if (asyncLoad) {
        const param = JSON.parse(facetsElem.dataset.param)
        fetchPartials(param)
            .then((data) => {
                const activeFacetsElem = createElementFromMarkup(data.activeFacets)
                const activeFacetsContainer = document.querySelector('.selected-search-facets-container')
                activeFacetsContainer.replaceChildren(activeFacetsElem)

                const newFacetsElem = createElementFromMarkup(data.sidebar)
                facetsElem.replaceWith(newFacetsElem)
                hydrateFacets()
            })
            .catch(() => {
                // XXX : Handle case where `/partials` response is not `2XX` here
            })
    } else {
        hydrateFacets()
    }
}


/**
 * Adds click listeners to the "show more" and "show less" facet affordances.
 */
function hydrateFacets() {
    const data_config_json = $('#searchFacets').data('config');
    const start_facet_count = data_config_json['start_facet_count'];
    const facet_inc = data_config_json['facet_inc'];

    $('.header_bull').hide();
    $('.header_more').on('click', function(){
        more($(this).data('header'), start_facet_count, facet_inc);
    });
    $('.header_less').on('click', function(){
        less($(this).data('header'), start_facet_count, facet_inc);
    });
}

/**
 * Makes call for a partially rendered facet counts sidebar, using the given search
 * parameters.
 *
 * @param {Object} param
 * @returns {Promise<Response>}
 *
 * @throws Will throw error if `/partials` response is not in 200-299 range.
 */
function fetchPartials(param) {
    const data = {
            p: param,
            path: location.pathname,
            query: document.location.search
        }
    const dataString = JSON.stringify(data)
    const dataQueryParam = encodeURIComponent(dataString)

    console.log('data:')
    console.log(data)

    return fetch(`/partials.json?_component=SearchFacets&data=${dataQueryParam}`)
        .then((resp) => {
            if (!resp.ok) {
                throw new Error(`Failed to fetch partials. Status code: ${resp.status}`)
            }
            return resp.json()
        })
}

/**
 * Returns an `HTMLElement` that was created using the given `markup`.
 *
 * `markup` is expected to be well-formed, and only have a single root
 * element.
 *
 * @param {string} markup HTML markup for a single element
 * @returns {HTMLElement}
 */
function createElementFromMarkup(markup) {
    const template = document.createElement('template')
    template.innerHTML = markup
    return template.content.children[0]
}
