import initAnalytics, { trackEvent } from '../../../openlibrary/plugins/openlibrary/js/ol.analytics.js';

function fakeAthena() {
    return {
        set_up_event_tracking: vi.fn(),
        get_data_packets: () => [{}],
        send_pageview: vi.fn(),
        send_ping: vi.fn()
    };
}

describe('initAnalytics', () => {
    afterEach(() => {
        delete window.archive_analytics;
        document.body.innerHTML = '';
    });

    test('sets up athena right away when it already ran', () => {
        const athena = (window.archive_analytics = fakeAthena());
        initAnalytics();
        expect(athena.set_up_event_tracking).toHaveBeenCalledTimes(1);
        expect(athena.send_pageview).toHaveBeenCalledTimes(1);
        expect(typeof athena.ol_send_event_ping).toBe('function');
    });

    test('waits for the async athena.js script when it arrives after the bundle', () => {
        document.body.innerHTML = '<script src="/cdn/archive.org/athena.js" async></script>';
        initAnalytics();

        const athena = (window.archive_analytics = fakeAthena());
        expect(athena.send_pageview).not.toHaveBeenCalled();

        document.querySelector('script').dispatchEvent(new Event('load'));
        expect(athena.set_up_event_tracking).toHaveBeenCalledTimes(1);
        expect(athena.send_pageview).toHaveBeenCalledTimes(1);
    });

    test('does nothing when athena.js is missing or blocked', () => {
        expect(() => initAnalytics()).not.toThrow();

        document.body.innerHTML = '<script src="/cdn/archive.org/athena.js" async></script>';
        initAnalytics();
        expect(() => document.querySelector('script').dispatchEvent(new Event('load'))).not.toThrow();
    });
});

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
