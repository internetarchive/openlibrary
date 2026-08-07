import { trackEvent } from './ol.analytics.js';

const BANNER_EVENTS = {
    'pending-action-container': { category: 'PreserveIntent', action: 'Dismiss' },
    'book-unavailable-banner': { category: 'OpenRelatedBooks', action: 'Dismiss' }
};

/**
 * Reports a Matomo event when a tracked <ol-banner> is dismissed.
 *
 * Must go through `trackEvent` (Matomo's `_paq` queue), NOT
 * `archive_analytics.ol_send_event_ping`. That helper pings Athena, and Athena
 * does not forward events into Matomo — so events sent that way silently never
 * report. Matomo's other ingest path is a tag-manager DOM trigger on
 * `data-ol-link-track`, which the close button (rendered by OlBanner) does not
 * carry. See #13261 and PR #13038.
 */
export function initBannerAnalytics() {
    document.addEventListener('ol-banner-dismiss', (e) => {
        const bannerId = e.detail?.dismissId || e.target.id || e.target.getAttribute('dismiss-id');
        if (!bannerId) return;

        const event = BANNER_EVENTS[bannerId];
        if (event) {
            trackEvent(event.category, event.action);
        }
    });
}
