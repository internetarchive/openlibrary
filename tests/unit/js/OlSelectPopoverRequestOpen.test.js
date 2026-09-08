/**
 * Tests for <ol-select-popover>'s deferred-open gate.
 *
 * A host that loads its items on demand can hold the panel shut while it
 * fetches, so the panel opens once at its final size instead of swapping a
 * spinner for a shorter, re-sorted list under the pointer. The trigger's
 * chevron carries the busy state meanwhile.
 *
 * jsdom has no layout engine and no Popover API, so these assert the mechanism
 * — the event, the busy attribute, and whether the inner ol-popover was asked
 * to open — rather than anything visual.
 */

import { setupComponentEnv } from '../../../openlibrary/components/test-utils/a11y.js';
import '../../../openlibrary/components/lit/OlSelectPopover.js';

setupComponentEnv();

/** Mount a popover and let Lit render its shadow root. */
async function mount() {
    const el = document.createElement('ol-select-popover');
    el.label = 'Language';
    el.items = [{ value: 'eng', label: 'English' }];
    document.body.appendChild(el);
    await el.updateComplete;
    return el;
}

/** The inner ol-popover, stubbed so nothing tries to animate or measure. */
function stubInnerPopover(el) {
    const popover = el.shadowRoot.querySelector('ol-popover');
    const opened = { count: 0 };
    Object.defineProperty(popover, 'open', {
        configurable: true,
        get: () => opened.count > 0,
        set: (v) => { if (v) opened.count++; },
    });
    return opened;
}

/** Click the default trigger the way a patron would. */
function clickTrigger(el) {
    const trigger = el.querySelector('[slot="trigger"]');
    const evt = new MouseEvent('click', { bubbles: true, composed: true, cancelable: true });
    trigger.dispatchEvent(evt);
    return { trigger, evt };
}

afterEach(() => {
    document.body.innerHTML = '';
});

describe('ol-select-popover request-open gate', () => {
    test('fires a cancelable request-open when the trigger is clicked', async() => {
        const el = await mount();
        const opened = stubInnerPopover(el);
        const seen = [];
        el.addEventListener('ol-select-popover-request-open', e => seen.push(e));

        clickTrigger(el);

        expect(seen).toHaveLength(1);
        expect(seen[0].cancelable).toBe(true);
        expect(seen[0].detail).toEqual({ focusFirst: false });
        // Nothing cancelled it, so the click carries on to ol-popover and the
        // panel opens immediately — hosts that don't opt in are unaffected.
        expect(opened.count).toBe(1);
    });

    test('preventDefault holds the panel shut', async() => {
        const el = await mount();
        const opened = stubInnerPopover(el);
        el.addEventListener('ol-select-popover-request-open', e => e.preventDefault());

        const { evt } = clickTrigger(el);

        expect(opened.count).toBe(0);
        // Stopped in capture, so ol-popover never sees the click.
        expect(evt.defaultPrevented).toBe(true);
    });

    test('show() opens the panel', async() => {
        const el = await mount();
        const opened = stubInnerPopover(el);
        el.addEventListener('ol-select-popover-request-open', e => e.preventDefault());
        clickTrigger(el);

        el.show();

        expect(opened.count).toBe(1);
    });

    test('leaves the trigger untouched while an open is deferred', async() => {
        // The component must not restyle or re-mark the trigger — a host that
        // wants a busy affordance owns it.
        const el = await mount();
        stubInnerPopover(el);
        el.addEventListener('ol-select-popover-request-open', e => e.preventDefault());
        const trigger = el.querySelector('[slot="trigger"]');
        const before = trigger.getAttributeNames().sort();

        clickTrigger(el);

        expect(trigger.getAttributeNames().sort()).toEqual(before);
    });

    test('ArrowDown on the trigger routes through the same gate', async() => {
        const el = await mount();
        stubInnerPopover(el);
        const seen = [];
        el.addEventListener('ol-select-popover-request-open', e => { seen.push(e); e.preventDefault(); });

        el.querySelector('[slot="trigger"]').dispatchEvent(
            new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, composed: true, cancelable: true }),
        );

        expect(seen).toHaveLength(1);
        expect(seen[0].detail.focusFirst).toBe(true);
    });

    test('does not re-request while an open is already pending', async() => {
        const el = await mount();
        stubInnerPopover(el);
        const seen = [];
        el.addEventListener('ol-select-popover-request-open', e => { seen.push(e); e.preventDefault(); });

        clickTrigger(el);
        clickTrigger(el);

        expect(seen).toHaveLength(1);
    });

    test('opening by any route ends the deferral', async() => {
        const el = await mount();
        stubInnerPopover(el);
        const seen = [];
        el.addEventListener('ol-select-popover-request-open', e => { seen.push(e); e.preventDefault(); });
        clickTrigger(el);
        expect(el._openDeferred).toBe(true);

        // ol-popover reports itself open without going through show().
        el.shadowRoot.querySelector('ol-popover')
            .dispatchEvent(new CustomEvent('ol-popover-open', { bubbles: true, composed: true }));

        expect(el._openDeferred).toBe(false);
    });
});
