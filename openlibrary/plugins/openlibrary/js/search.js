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
function more(header, start_facet_count, facet_inc) {
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
function less(header, start_facet_count, facet_inc) {
    const facetEntry = `div.${header} div.facetEntry`
    const shown = $(`${facetEntry}:not(:hidden)`).length
    const total = $(facetEntry).length
    const increment_extra = (shown - start_facet_count) % facet_inc;
    const next_shown = shown - ((increment_extra == 0) ? facet_inc:increment_extra);
    if (next_shown == start_facet_count) {
        $(`#${header}_less`).hide();
        $(`#${header}_bull`).hide();
    }
    if (shown == total) {
        $(`#${header}_more`).show();
        $(`#${header}_bull`).show();
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

let readapi_starttime = 0;

/**
 * Displays difference between readapi_starttime and now in '#adminTiming' element.
 */
function readapi_callback() {
    const endtime = Date.now();
    const duration = (endtime - readapi_starttime) / 1000;
    const disp = document.getElementById('adminTiming');
    if (disp) {
        disp.innerHTML += `<br/><br/><span class="adminOnly">Read API call took ${duration} seconds</span>`;
    }
}

/**
 * Initializes adminTiming element.
 *
 * Calls read_multiget API for a list of works.
 * Assumes presence of element with '#adminTiming' id and 'data-wks' attribute.
 */
export function initAdminTiming() {
    // ALL admin views are sampled.
    readapi_starttime = Date.now();
    const wks = $('#adminTiming').data('wks');
    $.ajax({
        url: `https://openlibrary.org/api/volumes/brief/json/${wks}?listofworks=True&no_details=True&stats=True`,
        dataType: 'jsonp',
        success: readapi_callback
    });
}
