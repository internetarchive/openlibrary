/**
 * Tests for <ol-tabs>: the ARIA tabs wiring it applies to server-rendered
 * links and panels, how it picks the initial tab, and click / keyboard / hash
 * behaviour.
 */
import '../../../openlibrary/components/lit/OlTabs.js';

const MARKUP = `
    <a slot="tab" href="#one">One</a>
    <a slot="tab" href="#two">Two</a>
    <a slot="tab" href="#three">Three</a>
    <div id="one">First panel</div>
    <div id="two">Second panel</div>
    <div id="three">Third panel</div>
`;

async function mount({ attrs = '', markup = MARKUP } = {}) {
    const wrapper = document.createElement('div');
    wrapper.innerHTML = `<ol-tabs ${attrs}>${markup}</ol-tabs>`;
    const el = wrapper.firstElementChild;
    document.body.appendChild(el);
    await el.updateComplete;
    return el;
}

const tabs = el => [...el.querySelectorAll(':scope > [slot="tab"]')];
const visiblePanels = el => [...el.querySelectorAll(':scope > div')].filter(p => !p.hidden).map(p => p.id);
const selectedTab = el => tabs(el).find(t => t.getAttribute('aria-selected') === 'true');

function press(target, key) {
    const event = new KeyboardEvent('keydown', { key, bubbles: true, composed: true, cancelable: true });
    target.dispatchEvent(event);
    return event;
}

function click(target, init = {}) {
    const event = new MouseEvent('click', { bubbles: true, composed: true, cancelable: true, button: 0, ...init });
    target.dispatchEvent(event);
    return event;
}

describe('ol-tabs', () => {
    afterEach(() => {
        document.body.innerHTML = '';
        history.replaceState(null, '', window.location.pathname);
        vi.restoreAllMocks();
    });

    describe('ARIA wiring', () => {
        it('applies the tabs pattern to the light-DOM links and panels', async () => {
            const el = await mount();
            const [one, two] = tabs(el);
            const panel = el.querySelector('#one');

            expect(el.shadowRoot.querySelector('[part="tablist"]').getAttribute('role')).toBe('tablist');
            expect(one.getAttribute('role')).toBe('tab');
            expect(one.id).toBe('one-tab');
            expect(one.getAttribute('aria-controls')).toBe('one');
            expect(panel.getAttribute('role')).toBe('tabpanel');
            expect(panel.getAttribute('aria-labelledby')).toBe('one-tab');
            expect(one.getAttribute('aria-selected')).toBe('true');
            expect(two.getAttribute('aria-selected')).toBe('false');
        });

        it('keeps an existing tab id', async () => {
            const el = await mount({ markup: '<a slot="tab" id="mine" href="#p">P</a><div id="p"></div>' });
            expect(tabs(el)[0].id).toBe('mine');
            expect(el.querySelector('#p').getAttribute('aria-labelledby')).toBe('mine');
        });

        it('gives only the selected tab a tab stop', async () => {
            const el = await mount();
            expect(tabs(el).map(t => t.tabIndex)).toEqual([0, -1, -1]);
        });

        it('labels the tab list from accessible-label', async () => {
            const el = await mount({ attrs: 'accessible-label="Changes"' });
            expect(el.shadowRoot.querySelector('[role="tablist"]').getAttribute('aria-label')).toBe('Changes');
        });
    });

    describe('initial selection', () => {
        it('defaults to the first tab and hides the other panels', async () => {
            const el = await mount();
            expect(visiblePanels(el)).toEqual(['one']);
        });

        it('honours the selected attribute', async () => {
            const el = await mount({ attrs: 'selected="two"' });
            expect(visiblePanels(el)).toEqual(['two']);
            expect(selectedTab(el).textContent).toBe('Two');
        });

        it('falls back to the first tab when selected names no panel', async () => {
            const el = await mount({ attrs: 'selected="nope"' });
            expect(visiblePanels(el)).toEqual(['one']);
        });

        it('prefers the URL hash over the selected attribute', async () => {
            history.replaceState(null, '', '#three');
            const el = await mount({ attrs: 'selected="two"' });
            expect(visiblePanels(el)).toEqual(['three']);
        });

        it('selects the panel named before a slash in the hash', async () => {
            history.replaceState(null, '', '#three/some-field');
            const el = await mount();
            expect(visiblePanels(el)).toEqual(['three']);
        });

        it('ignores a hash that names no panel', async () => {
            history.replaceState(null, '', '#elsewhere');
            const el = await mount({ attrs: 'selected="two"' });
            expect(visiblePanels(el)).toEqual(['two']);
        });
    });

    describe('clicking', () => {
        it('switches panels without following the link', async () => {
            const el = await mount();
            const event = click(tabs(el)[1]);
            await el.updateComplete;

            expect(event.defaultPrevented).toBe(true);
            expect(visiblePanels(el)).toEqual(['two']);
            expect(el.selected).toBe('two');
            expect(window.location.hash).toBe('');
        });

        it('fires ol-tabs-change once per change', async () => {
            const el = await mount();
            const onChange = vi.fn();
            el.addEventListener('ol-tabs-change', onChange);

            click(tabs(el)[2]);
            click(tabs(el)[2]);
            await el.updateComplete;

            expect(onChange).toHaveBeenCalledTimes(1);
            expect(onChange.mock.calls[0][0].detail).toEqual({ selected: 'three' });
        });

        it('leaves modified clicks to the browser', async () => {
            const el = await mount();
            const event = click(tabs(el)[1], { ctrlKey: true });
            await el.updateComplete;

            expect(event.defaultPrevented).toBe(false);
            expect(visiblePanels(el)).toEqual(['one']);
        });
    });

    describe('keyboard', () => {
        it('moves selection and focus with the arrow keys, wrapping', async () => {
            const el = await mount();
            const [one, two, three] = tabs(el);
            one.focus();

            expect(press(one, 'ArrowRight').defaultPrevented).toBe(true);
            await el.updateComplete;
            expect(document.activeElement).toBe(two);
            expect(visiblePanels(el)).toEqual(['two']);

            press(two, 'ArrowLeft');
            press(one, 'ArrowLeft');
            await el.updateComplete;
            expect(document.activeElement).toBe(three);
            expect(visiblePanels(el)).toEqual(['three']);
        });

        it('jumps to the ends with Home and End', async () => {
            const el = await mount();
            const [one, , three] = tabs(el);

            press(one, 'End');
            await el.updateComplete;
            expect(document.activeElement).toBe(three);

            press(three, 'Home');
            await el.updateComplete;
            expect(document.activeElement).toBe(one);
            expect(visiblePanels(el)).toEqual(['one']);
        });

        it('ignores keys outside the pattern', async () => {
            const el = await mount();
            const event = press(tabs(el)[0], 'ArrowDown');
            await el.updateComplete;

            expect(event.defaultPrevented).toBe(false);
            expect(visiblePanels(el)).toEqual(['one']);
        });

        it('keeps tab stops roving with the selection', async () => {
            const el = await mount();
            press(tabs(el)[0], 'ArrowRight');
            await el.updateComplete;
            expect(tabs(el).map(t => t.tabIndex)).toEqual([-1, 0, -1]);
        });
    });

    describe('sync-hash', () => {
        it('writes the selected panel to the hash without adding history', async () => {
            const el = await mount({ attrs: 'sync-hash' });
            const replaceState = vi.spyOn(history, 'replaceState');
            const pushState = vi.spyOn(history, 'pushState');

            click(tabs(el)[1]);

            expect(replaceState).toHaveBeenCalledTimes(1);
            expect(pushState).not.toHaveBeenCalled();
            expect(window.location.hash).toBe('#two');
        });

        it('leaves the hash alone on first render', async () => {
            const replaceState = vi.spyOn(history, 'replaceState');
            await mount({ attrs: 'sync-hash' });
            expect(replaceState).not.toHaveBeenCalled();
        });
    });

    it('switches panels when selected is set from script', async () => {
        const el = await mount();
        el.selected = 'three';
        await el.updateComplete;
        expect(visiblePanels(el)).toEqual(['three']);
    });

    it('keeps nested tab sets independent', async () => {
        const el = await mount({
            markup: `
                <a slot="tab" href="#outer-a">A</a>
                <a slot="tab" href="#outer-b">B</a>
                <div id="outer-a">
                    <ol-tabs>
                        <a slot="tab" href="#inner-x">X</a>
                        <a slot="tab" href="#inner-y">Y</a>
                        <div id="inner-x"></div>
                        <div id="inner-y"></div>
                    </ol-tabs>
                </div>
                <div id="outer-b"></div>
            `
        });
        const inner = el.querySelector('ol-tabs');
        await inner.updateComplete;

        click(tabs(inner)[1]);
        await inner.updateComplete;
        await el.updateComplete;

        expect(visiblePanels(inner)).toEqual(['inner-y']);
        expect(visiblePanels(el)).toEqual(['outer-a']);
    });
});
