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
async function mountTooltip() {
    const tag = `ol-tooltip-test-${++tagSeq}`;
    let el;
    await jest.isolateModulesAsync(async() => {
        const { OlTooltip } = await import('../../../openlibrary/components/lit/OlTooltip.js');
        customElements.define(tag, class extends OlTooltip {});
        el = document.createElement(tag);
        el.setAttribute('content', 'Tooltip text');
        el.setAttribute('show-delay', '0');
        el.innerHTML = '<button>Trigger</button>';
        document.body.appendChild(el);
    });
    await el.updateComplete;
    return el;
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
