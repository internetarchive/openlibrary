import { trackEvent } from '../../../openlibrary/plugins/openlibrary/js/ol.analytics.js';

describe('trackEvent', () => {
    afterEach(() => {
        delete window._paq;
        delete window.archive_analytics;
    });

    test('reports to Matomo and to the athena event ping alike', () => {
        window._paq = [];
        const ping = vi.fn();
        window.archive_analytics = { ol_send_event_ping: ping };

        trackEvent('CheckInPrompt', 'SetDateToday', 'edition:3');

        expect(window._paq).toEqual([['trackEvent', 'CheckInPrompt', 'SetDateToday', 'edition:3']]);
        expect(ping).toHaveBeenCalledWith({ category: 'CheckInPrompt', action: 'SetDateToday', label: 'edition:3' });
    });

    test('leaves the label off the Matomo event when there is none', () => {
        window._paq = [];
        trackEvent('Lists', 'CreateList');
        expect(window._paq).toEqual([['trackEvent', 'Lists', 'CreateList']]);
    });

    test('is a no-op without either script, and survives one without the other', () => {
        expect(() => trackEvent('Lists', 'CreateList')).not.toThrow();

        window.archive_analytics = {};
        expect(() => trackEvent('Lists', 'CreateList')).not.toThrow();

        window._paq = [];
        trackEvent('Lists', 'CreateList');
        expect(window._paq).toHaveLength(1);
    });
});
