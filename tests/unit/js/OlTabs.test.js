/**
 * Unit tests for <ol-tabs>: it turns <ol-tab> children into an ARIA tab list,
 * and arrows move the selection with focus following it.
 */
import '../../../openlibrary/components/lit/OlTabs.js';

async function mount(value = '') {
    document.body.innerHTML = `
        <ol-tabs ${value ? `value="${value}"` : ''} accessible-label="Sci-Fi subgenres">
            <ol-tab value="all">All Sci-Fi</ol-tab>
            <ol-tab value="space-opera">Space Opera</ol-tab>
            <ol-tab value="dystopian">Dystopian</ol-tab>
        </ol-tabs>`;
    const el = document.querySelector('ol-tabs');
    await el.updateComplete;
    return el;
}

const tabs = el => Array.from(el.shadowRoot.querySelectorAll('[role="tab"]'));
const selected = el => tabs(el).find(t => t.getAttribute('aria-selected') === 'true');
const press = (el, key, opts = {}) => selected(el).dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, composed: true, ...opts }));

// jsdom has no layout; the component scrolls a keyboard-selected tab into view.
beforeAll(() => {
    Element.prototype.scrollIntoView = () => {};
});

afterEach(() => {
    document.body.innerHTML = '';
});

test('renders a labelled tab list with one tab stop', async() => {
    const el = await mount('space-opera');
    expect(el.shadowRoot.querySelector('[role="tablist"]').getAttribute('aria-label')).toBe('Sci-Fi subgenres');
    expect(tabs(el).map(t => t.textContent.trim().split(/\s+/)[0])).toEqual(['All', 'Space', 'Dystopian']);
    expect(selected(el).textContent).toContain('Space Opera');
    expect(tabs(el).map(t => t.tabIndex)).toEqual([-1, 0, -1]);
});

test('defaults to the first tab when value is missing or unknown', async() => {
    expect((await mount()).value).toBe('all');
    expect((await mount('nope')).value).toBe('all');
});

test('a click selects the tab and fires ol-tabs-change', async() => {
    const el = await mount();
    const onChange = vi.fn();
    el.addEventListener('ol-tabs-change', e => onChange(e.detail.value));
    tabs(el)[2].click();
    await el.updateComplete;
    expect(el.value).toBe('dystopian');
    expect(onChange).toHaveBeenCalledWith('dystopian');

    tabs(el)[2].click();
    expect(onChange).toHaveBeenCalledTimes(1);
});

test('arrows wrap, Home/End jump, and auto-repeat is ignored', async() => {
    const el = await mount();
    press(el, 'ArrowLeft');
    await el.updateComplete;
    expect(el.value).toBe('dystopian');

    press(el, 'Home');
    await el.updateComplete;
    expect(el.value).toBe('all');

    press(el, 'ArrowRight', { repeat: true });
    await el.updateComplete;
    expect(el.value).toBe('all');

    press(el, 'End');
    await el.updateComplete;
    expect(el.value).toBe('dystopian');
});
