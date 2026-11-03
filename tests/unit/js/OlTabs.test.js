/**
 * Tests for <ol-tabs>: ARIA wiring, initial selection, and click / keyboard /
 * hash behaviour.
 */
import '../../../openlibrary/components/lit/OlTabs.js';

const MARKUP = `
    <a slot="tab" href="#one">One</a>
    <a slot="tab" href="#two">Two</a>
    <a slot="tab" href="#three">Three</a>
    <div id="one"></div>
    <div id="two"></div>
    <div id="three"></div>
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

function dispatch(target, event) {
    target.dispatchEvent(event);
    return event;
}
const click = (target, init = {}) => dispatch(target, new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, ...init }));
const press = (target, key, init = {}) => dispatch(target, new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init }));

describe('ol-tabs', () => {
    afterEach(() => {
        document.body.innerHTML = '';
        history.replaceState(null, '', window.location.pathname);
        vi.restoreAllMocks();
    });

    it('wires up the ARIA tabs pattern and shows only the first panel', async () => {
        const el = await mount();
        const [one, two] = tabs(el);
        const panel = el.querySelector('#one');

        expect(el.shadowRoot.querySelector('[role="tablist"]')).not.toBeNull();
        expect(one.getAttribute('role')).toBe('tab');
        expect(one.getAttribute('aria-controls')).toBe('one');
        expect(panel.getAttribute('role')).toBe('tabpanel');
        expect(panel.getAttribute('aria-labelledby')).toBe(one.id);
        expect([one.getAttribute('aria-selected'), two.getAttribute('aria-selected')]).toEqual(['true', 'false']);
        expect(tabs(el).map(t => t.tabIndex)).toEqual([0, -1, -1]);
        expect(visiblePanels(el)).toEqual(['one']);
    });

    it('starts on the panel named by the selected attribute', async () => {
        const el = await mount({ attrs: 'selected="two"' });
        expect(visiblePanels(el)).toEqual(['two']);
    });

    it('starts on the panel marked data-selected', async () => {
        const el = await mount({ markup: MARKUP.replace('<div id="three">', '<div id="three" data-selected>') });
        expect(visiblePanels(el)).toEqual(['three']);
        expect(el.selected).toBe('three');
    });

    it('prefers the selected attribute over a data-selected panel', async () => {
        const el = await mount({ attrs: 'selected="two"', markup: MARKUP.replace('<div id="three">', '<div id="three" data-selected>') });
        expect(visiblePanels(el)).toEqual(['two']);
    });

    it('starts on the panel named by the URL hash, ignoring anything after a slash', async () => {
        history.replaceState(null, '', '#three/some-field');
        const el = await mount({ attrs: 'selected="two"' });
        expect(visiblePanels(el)).toEqual(['three']);
    });

    describe('clicking', () => {
        it('switches panels without following the link', async () => {
            const el = await mount();
            const onChange = vi.fn();
            el.addEventListener('ol-tabs-change', onChange);

            const event = click(tabs(el)[1]);
            await el.updateComplete;

            expect(event.defaultPrevented).toBe(true);
            expect(visiblePanels(el)).toEqual(['two']);
            expect(onChange.mock.calls.map(([e]) => e.detail)).toEqual([{ selected: 'two' }]);
            expect(window.location.hash).toBe('');
        });

        it('does nothing when the tab already shown is clicked', async () => {
            const el = await mount({ attrs: 'sync-hash' });
            const onChange = vi.fn();
            el.addEventListener('ol-tabs-change', onChange);

            click(tabs(el)[0]);

            expect(onChange).not.toHaveBeenCalled();
            expect(window.location.hash).toBe('');
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
        it('moves selection and focus with the arrow keys, wrapping at the ends', async () => {
            const el = await mount();
            const [one, two, three] = tabs(el);

            press(one, 'ArrowRight');
            await el.updateComplete;
            expect(document.activeElement).toBe(two);
            expect(visiblePanels(el)).toEqual(['two']);
            expect(tabs(el).map(t => t.tabIndex)).toEqual([-1, 0, -1]);

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
            expect(visiblePanels(el)).toEqual(['three']);

            press(three, 'Home');
            await el.updateComplete;
            expect(document.activeElement).toBe(one);
            expect(visiblePanels(el)).toEqual(['one']);
        });

        it('follows the mirrored row under RTL', async () => {
            const el = await mount({ attrs: 'style="direction: rtl"' });
            const [one, two] = tabs(el);

            press(one, 'ArrowLeft');
            await el.updateComplete;
            expect(document.activeElement).toBe(two);
            expect(visiblePanels(el)).toEqual(['two']);

            press(two, 'ArrowRight');
            await el.updateComplete;
            expect(document.activeElement).toBe(one);
        });

        it('leaves browser shortcuts like Alt+ArrowLeft alone', async () => {
            const el = await mount();
            const event = press(tabs(el)[0], 'ArrowLeft', { altKey: true });
            await el.updateComplete;

            expect(event.defaultPrevented).toBe(false);
            expect(visiblePanels(el)).toEqual(['one']);
        });
    });

    it('follows a later hash change to one of its panels and reports it', async () => {
        const el = await mount();
        const onChange = vi.fn();
        el.addEventListener('ol-tabs-change', onChange);

        history.replaceState(null, '', '#three/field');
        window.dispatchEvent(new HashChangeEvent('hashchange'));
        await el.updateComplete;
        expect(visiblePanels(el)).toEqual(['three']);
        expect(onChange.mock.calls.map(([e]) => e.detail)).toEqual([{ selected: 'three' }]);

        // A hash that isn't one of our panels, or the one already shown, changes nothing.
        history.replaceState(null, '', '#elsewhere');
        window.dispatchEvent(new HashChangeEvent('hashchange'));
        await el.updateComplete;
        expect(visiblePanels(el)).toEqual(['three']);
        expect(onChange).toHaveBeenCalledTimes(1);

        // An emptied hash (Back past the first switch) restores the default tab.
        history.replaceState(null, '', window.location.pathname);
        window.dispatchEvent(new HashChangeEvent('hashchange'));
        await el.updateComplete;
        expect(visiblePanels(el)).toEqual(['one']);
        expect(onChange.mock.calls.map(([e]) => e.detail)).toEqual([{ selected: 'three' }, { selected: 'one' }]);
    });

    it('makes a panel with nothing focusable inside a tab stop', async () => {
        const el = await mount({
            markup: `
                <a slot="tab" href="#plain">Plain</a>
                <a slot="tab" href="#linked">Linked</a>
                <div id="plain">Just text.</div>
                <div id="linked"><a href="/x">A link</a></div>
            `
        });
        expect(el.querySelector('#plain').tabIndex).toBe(0);

        click(tabs(el)[1]);
        await el.updateComplete;
        expect(el.querySelector('#linked').hasAttribute('tabindex')).toBe(false);
    });

    it('rechecks the panel tab stop when content arrives later', async () => {
        const el = await mount({ markup: '<a slot="tab" href="#late">Late</a><div id="late"></div>' });
        const panel = el.querySelector('#late');
        expect(panel.tabIndex).toBe(0);

        panel.append(Object.assign(document.createElement('button'), { textContent: 'Go' }));
        await new Promise(resolve => setTimeout(resolve));
        expect(panel.hasAttribute('tabindex')).toBe(false);
    });

    it('counts an iframe as focusable content', async () => {
        const el = await mount({ markup: '<a slot="tab" href="#framed">Framed</a><div id="framed"><iframe></iframe></div>' });
        expect(el.querySelector('#framed').hasAttribute('tabindex')).toBe(false);
    });

    it('with sync-hash, replaces the URL hash on switch but not on first render', async () => {
        const replaceState = vi.spyOn(history, 'replaceState');
        const el = await mount({ attrs: 'sync-hash' });
        expect(replaceState).not.toHaveBeenCalled();

        click(tabs(el)[1]);

        expect(replaceState).toHaveBeenCalledTimes(1);
        expect(window.location.hash).toBe('#two');
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

        click(tabs(inner)[1]);
        await inner.updateComplete;
        await el.updateComplete;

        expect(visiblePanels(inner)).toEqual(['inner-y']);
        expect(visiblePanels(el)).toEqual(['outer-a']);
    });
});
