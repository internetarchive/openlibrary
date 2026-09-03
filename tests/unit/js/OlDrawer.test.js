/**
 * Regression tests for <ol-drawer>'s Tab trap scrolling the focused element
 * into view.
 *
 * The trap preventDefault()s every Tab and moves focus itself, which also
 * cancels the browser's native scroll-into-view. Without an explicit
 * scrollIntoView, Tab could land on a control below the fold of the panel's own
 * scroller — invisible to the user, and a WCAG 2.4.11 failure.
 *
 * jsdom has no layout engine, so these assert the call rather than the
 * resulting scrollTop, which is verified in the browser.
 */

/** jsdom implements neither <dialog>'s modal methods nor scrollIntoView. */
function installDomStubs() {
    const dialogProto = window.HTMLDialogElement.prototype;
    dialogProto.showModal = function() { this.open = true; };
    dialogProto.close = function() { this.open = false; };
    Element.prototype.scrollIntoView = jest.fn();
    // The body scroll lock restores the offset through it on release.
    const realScrollTo = window.scrollTo;
    window.scrollTo = () => {};
    return () => {
        delete dialogProto.showModal;
        delete dialogProto.close;
        delete Element.prototype.scrollIntoView;
        window.scrollTo = realScrollTo;
    };
}

const LINKS = ['first', 'second', 'third'];

async function mountDrawer() {
    const { OlDrawer } = await import('../../../openlibrary/components/lit/OlDrawer.js');
    const el = new OlDrawer();
    el.label = 'Menu';
    el.innerHTML = LINKS.map((id) => `<a id="${id}" href="/${id}">${id}</a>`).join('');
    document.body.appendChild(el);
    await el.updateComplete;

    el.open = true;
    await el.updateComplete;
    return el;
}

/** Fire Tab at the document, where the trap listens in the capture phase. */
function pressTab({ shiftKey = false } = {}) {
    document.dispatchEvent(new KeyboardEvent('keydown', {
        key: 'Tab', shiftKey, bubbles: true, cancelable: true,
    }));
}

describe('ol-drawer Tab trap', () => {
    let restoreDom;

    beforeEach(() => {
        restoreDom = installDomStubs();
    });

    afterEach(() => {
        document.body.innerHTML = '';
        restoreDom();
        jest.restoreAllMocks();
    });

    it('scrolls the newly focused element into view', async() => {
        const el = await mountDrawer();
        Element.prototype.scrollIntoView.mockClear();

        pressTab();

        const second = el.querySelector('#second');
        const scrollIntoView = Element.prototype.scrollIntoView;
        expect(document.activeElement).toBe(second);
        expect(scrollIntoView).toHaveBeenCalledWith({ block: 'nearest', inline: 'nearest' });
        // The mock lives on the prototype, so the receiver is what ties the
        // call to the element Tab just landed on.
        expect(scrollIntoView.mock.contexts).toEqual([second]);
    });

    it('scrolls back up when Tab wraps to the first element', async() => {
        // The wrap is the longest jump in the panel, so it's the one a missing
        // scroll strands the user furthest from.
        const el = await mountDrawer();
        el.querySelector('#third').focus();
        Element.prototype.scrollIntoView.mockClear();

        pressTab();

        expect(document.activeElement).toBe(el.querySelector('#first'));
        expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(1);
    });

    it('scrolls on Shift+Tab too', async() => {
        const el = await mountDrawer();
        el.querySelector('#third').focus();
        Element.prototype.scrollIntoView.mockClear();

        pressTab({ shiftKey: true });

        expect(document.activeElement).toBe(el.querySelector('#second'));
        expect(Element.prototype.scrollIntoView).toHaveBeenCalledTimes(1);
    });

    it('leaves ancestors alone, so the clipped dialog cannot scroll', async() => {
        // focus() without preventScroll scrolls every scrollable ancestor; the
        // panel parked off-screen made that scroll the dialog sideways.
        const el = await mountDrawer();
        const second = el.querySelector('#second');
        const focusSpy = jest.spyOn(second, 'focus');

        pressTab();

        expect(focusSpy).toHaveBeenCalledWith({ preventScroll: true });
    });
});
