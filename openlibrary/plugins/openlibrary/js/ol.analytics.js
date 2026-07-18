/**
* OpenLibrary-specific convenience functions for use with Archive.org athena.js
*
* Depends on Archive.org athena.js function archive_analytics.send_ping()
*
*/

/**
 * Report a custom interaction event to Matomo from JS.
 *
 * Use this for interactions that Matomo's DOM-based trigger can't see — chiefly
 * Shadow DOM controls (Lit components), where a `data-ol-link-track` attribute
 * on an inner element is invisible to Matomo's selector-based click trigger. We
 * push a `trackEvent` straight onto Matomo's `_paq` queue — the same path that
 * trigger ultimately uses, so the event lands in Matomo under the given
 * category/action/label. (Athena does not forward into Matomo, so the `_paq`
 * push is what actually makes these events report.)
 *
 * Guarded so a blocked or absent analytics script can never break the
 * interaction that triggered it.
 *
 * @param {string} category  Event category, e.g. 'SearchModal'
 * @param {string} action    Event action, e.g. 'ResultClick'
 * @param {string} [label]   Optional event label, e.g. 'edition:3'
 */
export function trackEvent(category, action, label) {
    if (!window._paq) return;
    const event = ['trackEvent', category, action];
    if (label) event.push(label);
    window._paq.push(event);
}

export default function initAnalytics() {
    var vs, i;
    var startTime = new Date();
    if (window.archive_analytics) {
        // Setup analytics, depends on script loaded from CDN
        window.archive_analytics.set_up_event_tracking();

        window.archive_analytics.ol_send_event_ping = function(values) {
            var endTime = new Date();
            window.archive_analytics.send_ping({
                service: 'ol',
                kind: 'event',
                ec: values['category'],
                ea: values['action'],
                el: values['label'] || location.pathname,
                ev: 1,
                loadtime: (endTime.getTime() - startTime.getTime()),
                cache_bust: Math.random()
            });
        };

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
            window.archive_analytics.ol_send_event_ping({
                category: category_action[0],
                action: category_action[1],
                label: category_action[2],
            });
        });
    }
    window.vs = vs;

    // NOTE: This might cause issues if this script is made async #4474
    window.addEventListener('DOMContentLoaded', function send_analytics_pageview() {
        window.archive_analytics.send_pageview({});
    });
}
