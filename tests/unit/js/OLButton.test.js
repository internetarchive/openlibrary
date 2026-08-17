/**
 * <ol-button> rendering contract: which inner element it produces and how
 * disabled/loading map onto it. jsdom has no layout, so appearance (variants,
 * shapes, elevation) is CSS-only and verified in the browser / design page.
 */
import '../../../openlibrary/components/lit/OLButton.js';

async function mount(attrs = {}, label = 'Label') {
    const el = document.createElement('ol-button');
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    el.textContent = label;
    document.body.appendChild(el);
    await el.updateComplete;
    return el;
}

afterEach(() => {
    document.body.innerHTML = '';
});

describe('OLButton', () => {
    test('renders a <button> by default and moves the label inside it', async() => {
        const el = await mount();
        const btn = el.querySelector(':scope > button');
        expect(btn).not.toBeNull();
        expect(btn.type).toBe('button');
        expect(btn.querySelector('.ol-btn-label').textContent).toBe('Label');
        expect(el.hasAttribute('hydrated')).toBe(true);
    });

    test('renders an <a> when href is set, passing link attributes through', async() => {
        const el = await mount({ href: '/borrow/OL1M', target: '_blank', rel: 'noopener', download: 'x.pdf' });
        expect(el.querySelector(':scope > button')).toBeNull();
        const a = el.querySelector(':scope > a');
        expect(a.getAttribute('href')).toBe('/borrow/OL1M');
        expect(a.getAttribute('target')).toBe('_blank');
        expect(a.getAttribute('rel')).toBe('noopener');
        expect(a.getAttribute('download')).toBe('x.pdf');
        expect(a.hasAttribute('aria-disabled')).toBe(false);
        expect(a.querySelector('.ol-btn-label').textContent).toBe('Label');
    });

    test('a disabled link drops its href and sets aria-disabled', async() => {
        const el = await mount({ href: '/x', disabled: '' });
        const a = el.querySelector(':scope > a');
        expect(a.hasAttribute('href')).toBe(false);
        expect(a.getAttribute('aria-disabled')).toBe('true');
    });

    test('a loading link is also inert and reports aria-busy', async() => {
        const el = await mount({ href: '/x', loading: '' });
        const a = el.querySelector(':scope > a');
        expect(a.hasAttribute('href')).toBe(false);
        expect(a.getAttribute('aria-disabled')).toBe('true');
        expect(a.getAttribute('aria-busy')).toBe('true');
    });

    test('toggling href swaps between <a> and <button> and keeps the label', async() => {
        const el = await mount();
        el.href = '/x';
        await el.updateComplete;
        expect(el.querySelector(':scope > a .ol-btn-label').textContent).toBe('Label');
        el.href = undefined;
        await el.updateComplete;
        expect(el.querySelector(':scope > a')).toBeNull();
        expect(el.querySelector(':scope > button .ol-btn-label').textContent).toBe('Label');
    });

    test('mirrors aria-label onto the link', async() => {
        const el = await mount({ href: '/x', 'aria-label': 'Save' });
        expect(el.querySelector(':scope > a').getAttribute('aria-label')).toBe('Save');
    });
});
