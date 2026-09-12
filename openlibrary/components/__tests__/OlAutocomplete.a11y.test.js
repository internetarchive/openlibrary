/**
 * Accessibility and behaviour tests for OlAutocomplete.
 *
 * Renders the real component so axe inspects its shadow DOM: the combobox
 * wiring on the input, and the listbox of options once a search returns.
 */
import { vi } from 'vitest';
import { checkA11y, cleanup, mount, setupComponentEnv } from '../test-utils/a11y.js';
import '../lit/OlAutocomplete.js';

const AUTHORS = [
    { key: '/authors/OL26320A', name: 'J.R.R. Tolkien', birth_date: '1892', death_date: '1973', works: ['The Lord of the Rings'] },
    { key: '/authors/OL1A', name: 'Christopher Tolkien', works: [] },
];

const input = (el) => el.shadowRoot.querySelector('input');
const options = (el) => [...el.shadowRoot.querySelectorAll('[role="option"]')];

function type(el, text) {
    input(el).value = text;
    input(el).dispatchEvent(new Event('input', { bubbles: true }));
}

async function mountWithResults(results = AUTHORS) {
    global.fetch = vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve(results) }));
    const el = await mount('<ol-autocomplete kind="author" label="Author" placeholder="Author name, OLID or URL"></ol-autocomplete>');
    type(el, 'tolk');
    await el.search();
    await el.updateComplete;
    return el;
}

beforeEach(() => setupComponentEnv());
afterEach(() => { cleanup(); delete global.fetch; });

describe('OlAutocomplete a11y', () => {
    test('closed: the input is a labelled, collapsed combobox', async() => {
        const el = await mount('<ol-autocomplete kind="author" label="Author"></ol-autocomplete>');

        const field = input(el);
        expect(field.getAttribute('role')).toBe('combobox');
        expect(field.getAttribute('aria-label')).toBe('Author');
        expect(field.getAttribute('aria-expanded')).toBe('false');
        expect(field.getAttribute('aria-controls')).toBe(el.shadowRoot.querySelector('[role="listbox"]').id);
        expect(await checkA11y()).toHaveNoViolations();
    });

    test('open: results form a listbox of options and the combobox expands', async() => {
        const el = await mountWithResults();

        expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/authors/_autocomplete?q=tolk'), expect.any(Object));
        expect(input(el).getAttribute('aria-expanded')).toBe('true');
        expect(options(el)).toHaveLength(AUTHORS.length);
        expect(options(el)[0].textContent).toContain('J.R.R. Tolkien');
        expect(await checkA11y()).toHaveNoViolations();
    });

    test('keyboard: arrows move aria-activedescendant, Enter picks and reports the key', async() => {
        const el = await mountWithResults();
        const picked = vi.fn();
        el.addEventListener('ol-autocomplete-select', (e) => picked(e.detail));

        input(el).dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
        await el.updateComplete;
        expect(input(el).getAttribute('aria-activedescendant')).toBe(options(el)[0].id);
        expect(options(el)[0].getAttribute('aria-selected')).toBe('true');

        input(el).dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        await el.updateComplete;
        expect(picked).toHaveBeenCalledWith(expect.objectContaining({ key: '/authors/OL26320A', name: 'J.R.R. Tolkien' }));
        expect(el.value).toBe('J.R.R. Tolkien');
        expect(el.key).toBe('/authors/OL26320A');
        expect(input(el).getAttribute('aria-expanded')).toBe('false');
    });

    test('an OLID typed straight in is accepted without searching', async() => {
        global.fetch = vi.fn();
        const el = await mount('<ol-autocomplete kind="author" label="Author"></ol-autocomplete>');
        const typed = vi.fn();
        el.addEventListener('ol-autocomplete-input', (e) => typed(e.detail.value));

        type(el, 'OL26320A');
        await el.updateComplete;
        expect(typed).toHaveBeenCalledWith('OL26320A');
        expect(global.fetch).not.toHaveBeenCalled();
        expect(input(el).getAttribute('aria-expanded')).toBe('false');
    });

    test('no results: a status line reports it and the listbox stays hidden', async() => {
        const el = await mountWithResults([]);

        expect(el.shadowRoot.querySelector('[role="listbox"]').hidden).toBe(true);
        const status = el.shadowRoot.querySelector('[role="status"]');
        expect(status.hidden).toBe(false);
        expect(status.textContent).toBe('No matches');
        expect(await checkA11y()).toHaveNoViolations();
    });
});
