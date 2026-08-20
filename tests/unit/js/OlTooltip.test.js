/**
 * Regression tests for <ol-tooltip>'s top-layer promotion.
 *
 * Same failure as <ol-popover>: the panel is positioned from viewport
 * coordinates, but plain `position: fixed` resolves against the nearest
 * transformed ancestor, so inside a carousel track the tooltip lands far from
 * its trigger and is clipped. See openlibrary/components/lit/utils/top-layer.js.
 *
 * jsdom has no layout engine, so these assert the mechanism rather than the
 * geometry, which is verified in the browser.
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

/**
 * Import OlTooltip fresh and register it under a unique tag. The support check
 * is a module-level constant read at import time, so each scenario needs its own
 * module instance — and customElements.define is one-shot per name.
 */
let tagSeq = 0;
async function mountTooltip(parent = document.body) {
    const tag = `ol-tooltip-test-${++tagSeq}`;
    let el;
    await jest.isolateModulesAsync(async() => {
        const { OlTooltip } = await import('../../../openlibrary/components/lit/OlTooltip.js');
        customElements.define(tag, class extends OlTooltip {});
        el = document.createElement(tag);
        el.setAttribute('content', 'Tooltip text');
        el.setAttribute('show-delay', '0');
        el.innerHTML = '<button>Trigger</button>';
        parent.appendChild(el);
    });
    await el.updateComplete;
    return el;
}

/**
 * A stand-in for <ol-carousel>: a scroll container inside a shadow root, with
 * the tooltip slotted into it from the light DOM.
 * @returns {{host: HTMLElement, viewport: HTMLElement}}
 */
let hostSeq = 0;
function mountScrollHost() {
    const tag = `scroll-host-test-${++hostSeq}`;
    customElements.define(tag, class extends HTMLElement {
        connectedCallback() {
            const root = this.attachShadow({ mode: 'open' });
            root.innerHTML = '<div class="viewport" style="overflow-x: auto"><slot></slot></div>';
        }
    });
    const host = document.createElement(tag);
    document.body.appendChild(host);
    return { host, viewport: host.shadowRoot.querySelector('.viewport') };
}

const tooltipOf = (el) => el.shadowRoot.querySelector('.tooltip');

/** Showing spans several update cycles; the promotion runs in a follow-up callback. */
async function settle(el) {
    for (let i = 0; i < 5; i++) {
        await el.updateComplete;
        await Promise.resolve();
    }
}

describe('ol-tooltip top-layer promotion', () => {
    let popoverApi;

    beforeEach(() => {
        // jsdom has no matchMedia; the component reads it on construction.
        window.matchMedia = (query) => ({
            matches: false,
            media: query,
            addEventListener() {},
            removeEventListener() {},
            addListener() {},
            removeListener() {},
        });
        document.body.innerHTML = '';
    });

    afterEach(() => {
        popoverApi?.restore();
        popoverApi = null;
        document.body.innerHTML = '';
    });

    it('promotes the tooltip to the top layer when it shows', async() => {
        popoverApi = installPopoverApiStub();
        const el = await mountTooltip();

        el._show();
        await settle(el);

        const tooltip = tooltipOf(el);
        expect(tooltip.getAttribute('popover')).toBe('manual');
        expect(popoverApi.isOpen(tooltip)).toBe(true);
    });

    it('demotes the tooltip when it hides', async() => {
        popoverApi = installPopoverApiStub();
        const el = await mountTooltip();

        el._show();
        await settle(el);
        const tooltip = tooltipOf(el);
        expect(popoverApi.isOpen(tooltip)).toBe(true);

        el._hide();
        await settle(el);

        expect(popoverApi.isOpen(tooltip)).toBe(false);
    });

    it('falls back to plain position: fixed without the Popover API', async() => {
        // No stub installed — jsdom has no showPopover, standing in for Safari < 17.
        const el = await mountTooltip();

        el._show();
        await settle(el);

        expect(tooltipOf(el).hasAttribute('popover')).toBe(false);
    });

    it('does not throw when hide runs without a preceding show', async() => {
        popoverApi = installPopoverApiStub();
        const el = await mountTooltip();

        expect(() => el._hide()).not.toThrow();
    });
});

describe('ol-tooltip scroll dismissal', () => {
    beforeEach(() => {
        window.matchMedia = (query) => ({
            matches: false,
            media: query,
            addEventListener() {},
            removeEventListener() {},
            addListener() {},
            removeListener() {},
        });
        document.body.innerHTML = '';
    });

    /** jsdom has no layout, so the trigger reports whatever rect we hand it. */
    function stubTriggerRect(el, rect) {
        const trigger = el.querySelector('button');
        const box = { top: 0, left: 0, width: 100, height: 20, ...rect };
        trigger.getBoundingClientRect = () => ({ ...box, right: box.left + box.width, bottom: box.top + box.height });
        return (next) => Object.assign(box, next);
    }

    it('hides when a scroller inside a shadow root moves the trigger', async() => {
        // `scroll` is not composed, so a window-level capture listener never
        // sees this one — the tooltip has to listen on the scroller itself or
        // it strands above a cover that has already been swiped away.
        const { host, viewport } = mountScrollHost();
        const el = await mountTooltip(host);
        const moveTrigger = stubTriggerRect(el, { top: 200, left: 300 });

        el._show();
        await settle(el);
        expect(el._visible).toBe(true);

        moveTrigger({ left: 40 });
        viewport.dispatchEvent(new Event('scroll'));
        expect(el._visible).toBe(false);
    });

    it('stays open when a scroll leaves the trigger where it was', async() => {
        // A snap container settles back to the same offset and still emits
        // scroll events; those must not dismiss a tooltip under the pointer.
        const { host, viewport } = mountScrollHost();
        const el = await mountTooltip(host);
        stubTriggerRect(el, { top: 200, left: 300 });

        el._show();
        await settle(el);

        viewport.dispatchEvent(new Event('scroll'));
        expect(el._visible).toBe(true);
    });

    it('stops listening on the scroller once hidden', async() => {
        const { host, viewport } = mountScrollHost();
        const el = await mountTooltip(host);
        const remove = jest.spyOn(viewport, 'removeEventListener');

        el._show();
        await settle(el);
        el._hide();

        expect(remove).toHaveBeenCalledWith('scroll', expect.any(Function), true);
        expect(el._scrollTargets).toEqual([]);
    });
});
