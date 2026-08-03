const BANNER_EVENTS = {
    'pending-action-container': { category: 'PreserveIntent', action: 'Dismiss' },
    'book-unavailable-banner': { category: 'OpenRelatedBooks', action: 'Dismiss' }
};

/**
 * Tracks Matomo and Archive Analytics events when banners are dismissed.
 */
export function initBannerAnalytics() {
    document.addEventListener('ol-banner-dismiss', (e) => {
        const bannerId = e.detail?.dismissId || e.target.id || e.target.getAttribute('dismiss-id');
        if (!bannerId) return;

        const event = BANNER_EVENTS[bannerId];
        if (event && window.archive_analytics && window.archive_analytics.ol_send_event_ping) {
            window.archive_analytics.ol_send_event_ping({
                category: event.category,
                action: event.action
            });
        }
    });
}
