/**
* OpenLibrary-specific convenience functions for use with Archive.org analytics.js
*
* Depends on Archive.org analytics.js function archive_analytics.send_ping()
*
* Usage:
*     $("select#role").add_new_field({href: "#role-popup"});
*
*/

export default function initAnalytics() {
    var vs, i;
    var startTime = new Date();
    if (window.archive_analytics) {
        window.archive_analytics.ol_send_event_ping = function(values) {
            var endTime = new Date();
            window.archive_analytics.send_ping({
                service: 'ol',
                kind: 'event',
                ec: values['category'],
                ea: values['action'],
                el: location.pathname,
                ev: 1,
                loadtime: (endTime.getTime() - startTime.getTime()),
                cache_bust: Math.random()
            });
        }

        vs = window.archive_analytics.get_data_packets();
        // console.log(vs);
        for (i in vs) {
            vs[i]['cache_bust']=Math.random();
            // console.log(vs[i]['cache_bust']);
            vs[i]['server_ms']=$('.analytics-stats-time-calculator').data('time');
            //console.log(vs[i]['server_ms']);
            vs[i]['server_name']='ol-web.us.archive.org';
            vs[i]['service']='ol';
        }
        if (window.flights){
            window.flights.init();
        }
        if ($('.more_search').size()>0) {
            window.archive_analytics.send_scroll_fetch_base_event();
        }
        $(document).on('click', '[data-ol-link-track]', function() {
            var category_action = $(this).attr('data-ol-link-track').split('|');
            window.archive_analytics.ol_send_event_ping({category: category_action[0], action: category_action[1]});
        });
    }
}
