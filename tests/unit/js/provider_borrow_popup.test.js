import { initProviderBorrowPopup } from '../../../openlibrary/plugins/openlibrary/js/provider_borrow_popup';

const HREF = 'https://openlibrary.org/books/OL46539165M/-/borrow?action=borrow';

/** @returns {HTMLAnchorElement} */
function borrowLink(provider) {
    document.body.innerHTML = '';
    const link = document.createElement('a');
    link.className = 'cta-btn cta-btn--borrow';
    link.href = HREF;
    link.target = '_blank';
    if (provider !== null) {
        link.dataset.olProvider = provider;
    }
    document.body.appendChild(link);
    return link;
}

function fakePopup() {
    return {closed: false, close: vi.fn()};
}

/** A real click, so preventDefault reports what the browser would do. */
function click(link, init = {}) {
    const event = new MouseEvent('click', {bubbles: true, cancelable: true, button: 0, ...init});
    link.dispatchEvent(event);
    return event;
}

const ORIGIN = window.location.origin;

/** The popup's own message, as provider_popup_result.html.jinja posts it. */
function postFromPopup(data, origin = ORIGIN) {
    window.dispatchEvent(new MessageEvent('message', {data, origin}));
}

describe('initProviderBorrowPopup', () => {
    let popup;
    let reload;

    beforeEach(() => {
        popup = fakePopup();
        vi.spyOn(window, 'open').mockReturnValue(popup);
        // Injected rather than patched onto `window.location`: that property
        // and its `reload` both report `configurable: false, writable: false`
        // under jsdom, which is why the module takes it as a parameter.
        reload = vi.fn();
    });

    afterEach(() => {
        vi.restoreAllMocks();
        vi.useRealTimers();
    });

    test('a click on a mediated provider opens a popup instead of navigating', () => {
        const link = borrowLink('lenny');
        initProviderBorrowPopup([link], reload);

        const event = click(link);

        expect(window.open).toHaveBeenCalledOnce();
        expect(window.open.mock.calls[0][0]).toBe(HREF);
        expect(event.defaultPrevented).toBe(true);
    });

    test('a provider Open Library does not borrow for is left alone', () => {
        // DirectProvider's borrow URL is a third-party site, which belongs in
        // the tab the anchor already opens.
        const link = borrowLink('direct');
        initProviderBorrowPopup([link], reload);

        const event = click(link);

        expect(window.open).not.toHaveBeenCalled();
        expect(event.defaultPrevented).toBe(false);
    });

    test('a borrow button with no provider is left alone', () => {
        const link = borrowLink(null);
        initProviderBorrowPopup([link], reload);

        click(link);

        expect(window.open).not.toHaveBeenCalled();
    });

    test('a blocked popup falls through to the anchor', () => {
        // The whole reason window.open runs before preventDefault: target=_blank
        // still borrows, it just cannot refresh the page behind it.
        window.open.mockReturnValue(null);
        const link = borrowLink('lenny');
        initProviderBorrowPopup([link], reload);

        const event = click(link);

        expect(event.defaultPrevented).toBe(false);
    });

    test('a modifier click is the patron asking for a tab', () => {
        const link = borrowLink('lenny');
        initProviderBorrowPopup([link], reload);

        const event = click(link, {metaKey: true});

        expect(window.open).not.toHaveBeenCalled();
        expect(event.defaultPrevented).toBe(false);
    });

    test('a loan refreshes the page the patron started on', () => {
        const link = borrowLink('lenny');
        initProviderBorrowPopup([link], reload);
        click(link);

        postFromPopup({type: 'ol-provider-borrow', ok: true});

        expect(reload).toHaveBeenCalledOnce();
        expect(popup.close).toHaveBeenCalledOnce();
    });

    test('a message from another origin is ignored', () => {
        // The popup visits the lending node in between, so messages do arrive
        // from other origins; one of them claiming a loan must not be believed.
        const link = borrowLink('lenny');
        initProviderBorrowPopup([link], reload);
        click(link);

        postFromPopup({type: 'ol-provider-borrow', ok: true}, 'https://lennyforlibraries.org');

        expect(reload).not.toHaveBeenCalled();
    });

    test('an unrelated same-origin message is ignored', () => {
        const link = borrowLink('lenny');
        initProviderBorrowPopup([link], reload);
        click(link);

        postFromPopup({type: 'some-other-widget', ok: true});

        expect(reload).not.toHaveBeenCalled();
    });

    test('a failure does not refresh', () => {
        const link = borrowLink('lenny');
        initProviderBorrowPopup([link], reload);
        click(link);

        postFromPopup({type: 'ol-provider-borrow', ok: false});

        expect(reload).not.toHaveBeenCalled();
    });

    test('a patron who backs out is not refreshed at, and the listener goes away', () => {
        // Deliberate: the only evidence a loan exists is the callback saying
        // so. A closed popup is someone cancelling, most often at the
        // interstitial, and refreshing them is churn with nothing to show.
        vi.useFakeTimers();
        const link = borrowLink('lenny');
        initProviderBorrowPopup([link], reload);
        click(link);

        popup.closed = true;
        vi.advanceTimersByTime(1000);
        postFromPopup({type: 'ol-provider-borrow', ok: true});

        expect(reload).not.toHaveBeenCalled();
    });
});
