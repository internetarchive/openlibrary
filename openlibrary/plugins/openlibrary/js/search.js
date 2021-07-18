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
    if (shown == start_facet_count) {
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
    const facet_dec = (increment_extra == 0) ? facet_inc:increment_extra;
    const next_shown = Math.max(start_facet_count, shown - facet_dec);
    if (shown == total) {
        $(`#${header}_more`).show();
        $(`#${header}_bull`).show();
    }
    if (next_shown == start_facet_count) {
        $(`#${header}_less`).hide();
        $(`#${header}_bull`).hide();
    }
    $(`${facetEntry}:not(:hidden)`).slice(next_shown, shown).addClass('ui-helper-hidden');
}

/**
 * Initializes searchFacets element.
 *
 * Hides '.header_bull' element and adds onclick events to '.header_(more|less)' elements.
 * Assumes presence of element with '#searchFacets' id and 'data-config' attribute.
 */
export function initSearchFacets() {
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
