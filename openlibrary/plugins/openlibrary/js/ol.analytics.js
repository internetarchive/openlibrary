/**
* OpenLibrary-specific convenience functions for use with Archive.org analytics.js
*
* Depends on Archive.org analytics.js function archive_analytics.send_ping()
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
        for (i in vs) {
            vs[i]['cache_bust']=Math.random();
            vs[i]['server_ms']=$('.analytics-stats-time-calculator').data('time');
            vs[i]['server_name']='ol-web.us.archive.org';
            vs[i]['service']='ol';
        }
        if (window.flights){
            window.flights.init();
        }
        $(document).on('click', '[data-ol-link-track]', function() {
            var category_action = $(this).attr('data-ol-link-track').split('|');
            // for testing,
            // console.log(category_action[0], category_action[1]);
            window.archive_analytics.ol_send_event_ping({category: category_action[0], action: category_action[1]});
        });
    }
    window.vs = vs;

    // NOTE: This might cause issues if this script is made async #4474
    window.addEventListener('DOMContentLoaded', function send_analytics_pageview() {
        window.archive_analytics.send_pageview({});
    });
}
