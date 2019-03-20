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
    var startTime = new Date();
    if (window.archive_analytics) {
        window.archive_analytics.ol_send_event_ping = function(values) {
            var endTime = new Date();
            window.archive_analytics.send_ping({
                'service':'ol',
                'kind':'event',
                'ec':values['category'],
                'ea':values['action'],
                'el':location.pathname,
                'ev':1,
                // startTime is defined in openlibrary\plugins\openlibrary\js\ol.js
                // eslint-disable-next-line no-undef
                'loadtime':(endTime.getTime() - startTime.getTime()),
                'cache_bust':Math.random()
            });
        }
    }
}
