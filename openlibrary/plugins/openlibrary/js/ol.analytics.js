import $ from 'jquery';
/**
* OpenLibrary-specific convenience functions for use with Archive.org athena.js
*
* Depends on Archive.org athena.js function archive_analytics.send_ping()
*
*/

/**
 * Report a custom interaction event from JS, the same way a `data-ol-link-track`
 * click does: to Matomo through its `_paq` queue, and to Archive.org's own
 * analytics through the athena event ping. Both, so an interaction that moves
 * from a tracked link to a JS call keeps reporting wherever it was counted.
 *
 * Use this for interactions that the click trigger can't see — chiefly Shadow
 * DOM controls (Lit components), where the attribute on an inner element is
 * invisible to the document-level selector.
 *
 * Guarded so a blocked or absent analytics script can never break the
 * interaction that triggered it.
 *
 * @param {string} category  Event category, e.g. 'SearchModal'
 * @param {string} action    Event action, e.g. 'ResultClick'
 * @param {string} [label]   Optional event label, e.g. 'edition:3'
 */
export function trackEvent(category, action, label) {
    if (window._paq) {
        const event = ['trackEvent', category, action];
        if (label) event.push(label);
        window._paq.push(event);
    }
    window.archive_analytics?.ol_send_event_ping?.({ category, action, label });
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
            trackEvent(category_action[0], category_action[1], category_action[2]);
        });
    }
    window.vs = vs;

    // The bundle loads asynchronously, so DOMContentLoaded may already have fired (#4474)
    function sendPageview() {
        if (!window.archive_analytics) return;
        window.archive_analytics.send_pageview({});
    }
    if (document.readyState === 'loading') {
        window.addEventListener('DOMContentLoaded', sendPageview);
    } else {
        sendPageview();
    }
}
