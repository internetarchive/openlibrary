function more(header, start_facet_count, facet_inc) {
    const div_header = "div." + header
    const facetEntry = div_header + " div.facetEntry"
    const shown = $(facetEntry + ":not(:hidden)").length
    const total = $(facetEntry).length
    if (shown == start_facet_count) {
        $("#" + header + "_less").show();
        $("#" + header + "_bull").show();
    }
    if (shown + facet_inc >= total) {
        $("#" + header + "_more").hide();
        $("#" + header + "_bull").hide();
    }
    $(facetEntry + ":hidden").slice(0, facet_inc).removeClass('ui-helper-hidden');
}

function less(header, start_facet_count, facet_inc) {
    const div_header = "div." + header
    const facetEntry = div_header + " div.facetEntry"
    const shown = $(facetEntry + ":not(:hidden)").length
    const total = $(facetEntry).length
    if (shown - facet_inc == start_facet_count) {
        $("#" + header + "_less").hide();
        $("#" + header + "_bull").hide();
    }
    if (shown == total) {
        $("#" + header + "_more").show();
        $("#" + header + "_bull").show();
    }
    $(facetEntry + ":not(:hidden)").slice(shown - facet_inc, shown).addClass('ui-helper-hidden');
}

export function initSearchFacets() {
    const data_config_json = $('#searchFacets').data('config');
    const start_facet_count = data_config_json['start_facet_count'];
    const facet_inc = data_config_json['facet_inc'];

    $(".header_bull").hide();
    $('.header_more').on('click', function(){
        more($(this).data('header'), start_facet_count, facet_inc);
    });
    $('.header_less').on('click', function(){
        less($(this).data('header'), start_facet_count, facet_inc);
    });
}

let readapi_starttime = 0;

function readapi_callback(data, textStatus, jqXHR) {
    const endtime = Date.now();
    //document.write(data.stats.summary.toSource());
    const duration = (endtime - readapi_starttime) / 1000;
    const disp = document.getElementById("adminTiming");
    if (disp) {
        disp.innerHTML += '<br/><br/><span class="adminOnly">Read API call took ' + duration + ' seconds</span>';
    }
}

export function initAdminTiming() {
    const readapi_percent = 100;
    if (Math.random() * 100 < readapi_percent) {
        readapi_starttime = Date.now();
        const ol = 'openlibrary.org';
        const wks = $('#adminTiming').data('wks');
        $.ajax({
            url: 'https://' + ol + '/api/volumes/brief/json/' + wks + '?listofworks=True&no_details=True&stats=True',
            dataType: 'jsonp',
            success: readapi_callback
        });
    }
}