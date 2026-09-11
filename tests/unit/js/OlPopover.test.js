/**
 * Regression tests for <ol-popover>'s top-layer promotion.
 *
 * The panel is positioned with viewport coordinates from
 * getBoundingClientRect(). Plain `position: fixed` resolves against the nearest
 * *transformed* ancestor rather than the viewport, so inside a carousel track
 * (or any transformed container) the panel rendered hundreds of pixels off and
 * clipped. Promoting it to the top layer via the Popover API makes the viewport
 * the containing block again.
 *
 * jsdom has no layout engine, so these tests assert the mechanism — the popover
 * attribute and the show/hide calls — rather than the resulting geometry, which
 * is verified in the browser.
 */

/** Minimal Popover API stand-in: jsdom implements neither the methods nor the pseudo-class. */
function installPopoverApiStub() {
    const open = new WeakSet();
    HTMLElement.prototype.showPopover = jest.fn(function() {
        if (open.has(this)) throw new DOMException('already open', 'InvalidStateError');
        open.add(this);
    });
    HTMLElement.prototype.hidePopover = jest.fn(function() {
        if (!open.has(this)) throw new DOMException('not open', 'InvalidStateError');
        open.delete(this);
    });
    const realMatches = Element.prototype.matches;
    Element.prototype.matches = function(selector) {
        if (selector === ':popover-open') return open.has(this);
        return realMatches.call(this, selector);
    };
    return {
        isOpen: (el) => open.has(el),
        restore: () => {
            delete HTMLElement.prototype.showPopover;
            delete HTMLElement.prototype.hidePopover;
            Element.prototype.matches = realMatches;
        },
    };
}

function installMatchMediaStub(matches = false) {
    window.matchMedia = (query) => ({
        matches: typeof matches === 'function' ? matches(query) : matches,
        media: query,
        addEventListener() {},
        removeEventListener() {},
        addListener() {},
        removeListener() {},
    });
}

/**
 * Import OlPopover fresh and register it under a unique tag. The support check
 * is a module-level constant read at import time, so each scenario needs its own
 * module instance — and customElements.define is one-shot per name.
 */
let tagSeq = 0;
async function mountPopover() {
    const tag = `ol-popover-test-${++tagSeq}`;
    let el;
    await jest.isolateModulesAsync(async() => {
        const { OlPopover } = await import('../../../openlibrary/components/lit/OlPopover.js');
        customElements.define(tag, class extends OlPopover {});
        el = document.createElement(tag);
        el.innerHTML = '<button slot="trigger">Open</button><div>Panel content</div>';
        document.body.appendChild(el);
    });
    await el.updateComplete;
    return el;
}

const panelOf = (el) => el.shadowRoot.querySelector('.panel');

/**
 * Opening runs across several update cycles: `open` triggers `_show()`, which
 * sets the animation state, and the promotion happens in a follow-up
 * `updateComplete` callback. Settle all of them.
 */
async function openAndSettle(el) {
    el.open = true;
    for (let i = 0; i < 5; i++) {
        await el.updateComplete;
        await Promise.resolve();
    }
}

describe('ol-popover top-layer promotion', () => {
    let popoverApi;

    beforeEach(() => {
        installMatchMediaStub();
        document.body.innerHTML = '';
    });

    afterEach(() => {
        popoverApi?.restore();
        popoverApi = null;
        document.body.innerHTML = '';
    });

    it('promotes the panel to the top layer when the Popover API exists', async() => {
        popoverApi = installPopoverApiStub();
        const el = await mountPopover();

        await openAndSettle(el);

        const panel = panelOf(el);
        expect(panel).not.toBeNull();
        expect(panel.getAttribute('popover')).toBe('manual');
        expect(popoverApi.isOpen(panel)).toBe(true);
    });

    it('uses popover="manual", never "auto"', async() => {
        // "auto" would light-dismiss and force-close sibling popovers outside the
        // ancestor chain, collapsing the component's own nesting stack.
        popoverApi = installPopoverApiStub();
        const el = await mountPopover();

        await openAndSettle(el);

        expect(panelOf(el).getAttribute('popover')).not.toBe('auto');
    });

    it('falls back to plain position: fixed without the Popover API', async() => {
        // No stub installed — jsdom has no showPopover, standing in for Safari < 17.
        const el = await mountPopover();

        await openAndSettle(el);

        expect(panelOf(el).hasAttribute('popover')).toBe(false);
    });

    it('demotes the panel out of the top layer when it closes', async() => {
        popoverApi = installPopoverApiStub();
        const el = await mountPopover();

        await openAndSettle(el);
        const panel = panelOf(el);
        expect(popoverApi.isOpen(panel)).toBe(true);

        el._cleanup();

        expect(popoverApi.isOpen(panel)).toBe(false);
        expect(HTMLElement.prototype.hidePopover).toHaveBeenCalled();
    });

    it('does not throw when cleanup runs on an already-hidden panel', async() => {
        popoverApi = installPopoverApiStub();
        const el = await mountPopover();

        await openAndSettle(el);

        el._cleanup();
        expect(() => el._cleanup()).not.toThrow();
    });
});

/**
 * The close path hangs off a single `transitionend`. When that event never
 * arrives — a backgrounded tab paints no frames, and preparing → exiting
 * changes no animatable property — the panel stayed promoted, above the page
 * and holding focus, while the trigger already reported aria-expanded="false".
 */
describe('ol-popover close fallback', () => {
    let popoverApi;

    let realScrollTo;

    beforeEach(() => {
        jest.useFakeTimers();
        installMatchMediaStub();
        // jsdom has no scrollTo; releasing the mobile scroll lock calls it.
        realScrollTo = window.scrollTo;
        window.scrollTo = () => {};
        document.body.innerHTML = '';
    });

    afterEach(() => {
        window.scrollTo = realScrollTo;
        jest.useRealTimers();
        popoverApi?.restore();
        popoverApi = null;
        document.body.innerHTML = '';
    });

    it('demotes and restores focus when transitionend never fires', async() => {
        popoverApi = installPopoverApiStub();
        const el = await mountPopover();
        const trigger = el.querySelector('[slot="trigger"]');
        trigger.focus();

        await openAndSettle(el);
        const panel = panelOf(el);
        expect(popoverApi.isOpen(panel)).toBe(true);

        el.open = false;
        await el.updateComplete;
        expect(el._animState).toBe('exiting');

        // No transitionend in jsdom, exactly as in a tab that paints no frames.
        jest.advanceTimersByTime(400);

        expect(el._animState).toBe('closed');
        expect(popoverApi.isOpen(panel)).toBe(false);
        expect(document.activeElement).toBe(trigger);
    });

    it('lets a real transitionend win, without a second cleanup', async() => {
        popoverApi = installPopoverApiStub();
        const el = await mountPopover();

        await openAndSettle(el);
        const panel = panelOf(el);

        el.open = false;
        await el.updateComplete;
        panel.dispatchEvent(new Event('transitionend'));
        expect(el._animState).toBe('closed');

        // The armed timer must not fire a second cleanup into the closed popover.
        const hideCalls = HTMLElement.prototype.hidePopover.mock.calls.length;
        jest.advanceTimersByTime(400);
        expect(HTMLElement.prototype.hidePopover.mock.calls.length).toBe(hideCalls);
    });

    it('cancels the pending close when reopened mid-exit', async() => {
        popoverApi = installPopoverApiStub();
        const el = await mountPopover();

        await openAndSettle(el);
        el.open = false;
        await el.updateComplete;

        await openAndSettle(el);
        jest.advanceTimersByTime(400);

        expect(el._animState).not.toBe('closed');
        expect(popoverApi.isOpen(panelOf(el))).toBe(true);
    });

    it('takes only one body scroll lock when reopened mid-exit', async() => {
        // A second lock would outlive the single _releaseScrollLock() and leave
        // <body> pinned at position: fixed for the rest of the session.
        installMatchMediaStub((q) => q.includes('max-width'));
        popoverApi = installPopoverApiStub();
        const el = await mountPopover();

        await openAndSettle(el);
        el.open = false;
        await el.updateComplete;
        await openAndSettle(el);

        el.open = false;
        await el.updateComplete;
        jest.advanceTimersByTime(400);

        expect(document.body.style.position).toBe('');
    });
});
