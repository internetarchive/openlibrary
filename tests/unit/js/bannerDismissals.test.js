/**
 * Site glue for <ol-banner> dismissals (js/banner/index.js): closing a banner
 * persists its dismiss-id, and so does following a link inside a banner marked
 * data-dismiss-on-link.
 */
import { initOlBannerDismissals } from '../../../openlibrary/plugins/openlibrary/js/banner';

function mount(attrs = 'dismiss-id="tasks_pitch_1" data-cookie-duration-days="365" data-dismiss-on-link') {
    document.body.innerHTML = `
        <ol-banner ${attrs}>
            <p>Thank you</p>
            <ol-chip href="/tasks">A project</ol-chip>
        </ol-banner>`;
    return document.querySelector('ol-banner');
}

function sentCookies() {
    return global.fetch.mock.calls.map(([url, options]) => [url, JSON.parse(options.body)]);
}

describe('ol-banner dismissals', () => {
    beforeAll(() => initOlBannerDismissals());

    beforeEach(() => {
        global.fetch = vi.fn(() => Promise.resolve({ ok: true }));
    });

    test("closing a banner persists its dismiss-id for the banner's duration", () => {
        const banner = mount();
        banner.dispatchEvent(new CustomEvent('ol-banner-dismiss', { detail: { dismissId: 'tasks_pitch_1' }, bubbles: true }));
        expect(sentCookies()).toEqual([['/hide_banner', { 'cookie-name': 'tasks_pitch_1', 'cookie-duration-days': 365 }]]);
    });

    test('following a link in a dismiss-on-link banner persists it too', () => {
        mount().querySelector('ol-chip').click();
        expect(sentCookies()).toEqual([['/hide_banner', { 'cookie-name': 'tasks_pitch_1', 'cookie-duration-days': 365 }]]);
        // The request has to outlive the page the link leaves.
        expect(global.fetch.mock.calls[0][1].keepalive).toBe(true);
    });

    test('a click elsewhere in the banner persists nothing', () => {
        mount().querySelector('p').click();
        expect(global.fetch).not.toHaveBeenCalled();
    });

    test('links in an ordinary banner persist nothing', () => {
        mount('dismiss-id="yrg26"').querySelector('ol-chip').click();
        expect(global.fetch).not.toHaveBeenCalled();
    });
});
