/**
 * Unit tests for <ol-tag-picker>.
 *
 * The combobox input and listbox live in the component's own shadow root
 * (slotted into <ol-popover>), so they are queryable whether or not the popover
 * is "open" — these tests exercise behaviour directly against the shadow DOM.
 */
import { afterAll, afterEach, beforeAll, describe, expect, test, vi } from 'vitest';
import '../../../openlibrary/components/lit/OlTagPicker.js';

// jsdom has no attachInternals; give every element a fake so the form plumbing
// (setFormValue) doesn't throw. Installed before any element is constructed —
// the FormAssociatedMixin constructor calls attachInternals?.(). Mirrors the
// stubs in OLButton.test.js / formAssociatedMixin.test.js.
beforeAll(() => {
    HTMLElement.prototype.attachInternals = function() {
        return { form: null, labels: [], setFormValue: vi.fn() };
    };
});
afterAll(() => {
    delete HTMLElement.prototype.attachInternals;
});

const CONTENT_FORMATS = [
    { key: '/tags/OL120T', name: 'Almanac' },
    { key: '/tags/OL131T', name: 'Graphic Novel' },
    { key: '/tags/OL134T', name: 'Manga' },
    { key: '/tags/OL136T', name: 'Novel' },
    { key: '/tags/OL130T', name: 'Essays' },
];

/**
 * Mount an <ol-tag-picker> with options supplied directly (no network), plus
 * any extra attributes/properties.
 */
async function mount({ attrs = {}, props = {}, parent = document.body } = {}) {
    const el = document.createElement('ol-tag-picker');
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    el.options = CONTENT_FORMATS;
    for (const [k, v] of Object.entries(props)) el[k] = v;
    parent.appendChild(el);
    await el.updateComplete;
    return el;
}

const input = (el) => el.shadowRoot.querySelector('.filter-input');
const optionEls = (el) => Array.from(el.shadowRoot.querySelectorAll('.option'));
const optionNames = (el) => optionEls(el).map((li) => li.textContent.trim());
const chipEls = (el) => Array.from(el.shadowRoot.querySelectorAll('ol-chip'));
const chipNames = (el) => chipEls(el).map((c) => c.textContent.trim());

async function type(el, text) {
    const field = input(el);
    field.value = text;
    field.dispatchEvent(new Event('input'));
    await el.updateComplete;
}

afterEach(() => {
    document.body.innerHTML = '';
});

describe('ol-tag-picker rendering & trigger', () => {
    test('injects a default trigger labelled "+ Add <Type>" from tag-type', async() => {
        const el = await mount({ attrs: { 'tag-type': 'content_formats' } });
        const trigger = el.querySelector('[slot="trigger"]');
        expect(trigger).toBeTruthy();
        expect(trigger.textContent.trim()).toBe('+ Add Content Formats');
    });

    test('an explicit label overrides the derived one', async() => {
        const el = await mount({ attrs: { 'tag-type': 'content_formats', label: '+ Add formats' } });
        expect(el.querySelector('[slot="trigger"]').textContent.trim()).toBe('+ Add formats');
    });

    test('lists every unselected option by name', async() => {
        const el = await mount();
        expect(optionNames(el).sort()).toEqual(
            ['Almanac', 'Essays', 'Graphic Novel', 'Manga', 'Novel'].sort(),
        );
    });
});

describe('ol-tag-picker case-insensitive filtering', () => {
    test('typing "mang" matches only "Manga"', async() => {
        const el = await mount();
        await type(el, 'mang');
        expect(optionNames(el)).toEqual(['Manga']);
    });

    test('filtering is case-insensitive: "MANG" matches "Manga" too, identically', async() => {
        const lower = await mount();
        await type(lower, 'mang');
        const upper = await mount();
        await type(upper, 'MANG');
        expect(optionNames(upper)).toEqual(['Manga']);
        expect(optionNames(upper)).toEqual(optionNames(lower));
    });

    test('a substring match is enough ("nov" matches "Graphic Novel" and "Novel")', async() => {
        const el = await mount();
        await type(el, 'nov');
        expect(optionNames(el).sort()).toEqual(['Graphic Novel', 'Novel'].sort());
    });

    test('no matches shows the empty state and no options', async() => {
        const el = await mount();
        await type(el, 'zzz');
        expect(optionEls(el)).toHaveLength(0);
        expect(el.shadowRoot.querySelector('.empty-state').textContent.trim()).toBe('No matches');
    });
});

describe('ol-tag-picker initial value — both stored shapes', () => {
    test('accepts plain key strings', async() => {
        const el = await mount({ props: { value: ['/tags/OL120T'] } });
        expect(chipNames(el)).toEqual(['Almanac']);
    });

    test('accepts {key} refs', async() => {
        const el = await mount({ props: { value: [{ key: '/tags/OL120T' }] } });
        expect(chipNames(el)).toEqual(['Almanac']);
    });

    test('accepts a mix of both shapes, de-duplicated', async() => {
        const el = await mount({ props: { value: ['/tags/OL120T', { key: '/tags/OL134T' }, '/tags/OL120T'] } });
        expect(chipNames(el)).toEqual(['Almanac', 'Manga']);
    });

    test('a selected option is removed from the listbox', async() => {
        const el = await mount({ props: { value: ['/tags/OL134T'] } });
        expect(optionNames(el)).not.toContain('Manga');
    });
});

describe('ol-tag-picker selection', () => {
    test('clicking an option adds a chip, fires change, and keeps the option out of the list', async() => {
        const el = await mount();
        const changes = [];
        el.addEventListener('ol-tag-picker-change', (e) => changes.push(e.detail));

        const manga = optionEls(el).find((li) => li.textContent.trim() === 'Manga');
        manga.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        await el.updateComplete;

        expect(chipNames(el)).toEqual(['Manga']);
        expect(optionNames(el)).not.toContain('Manga');
        expect(changes).toHaveLength(1);
        expect(changes[0]).toEqual({ value: ['/tags/OL134T'], added: '/tags/OL134T', removed: null });
    });

    test('Enter selects the active option', async() => {
        const el = await mount();
        await type(el, 'nov'); // Graphic Novel, Novel; active resets to index 0
        input(el).dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        await el.updateComplete;
        expect(chipNames(el)).toHaveLength(1);
        expect(['Graphic Novel', 'Novel']).toContain(chipNames(el)[0]);
    });

    test('several can be added in a row (query clears after each pick)', async() => {
        const el = await mount();
        await type(el, 'mang'); // unique → Manga
        input(el).dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        await el.updateComplete;
        expect(input(el).value).toBe('');
        await type(el, 'alman'); // unique → Almanac
        input(el).dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        await el.updateComplete;
        expect(chipNames(el).sort()).toEqual(['Almanac', 'Manga'].sort());
    });
});

describe('ol-tag-picker removal', () => {
    test('a chip close (ol-chip-select selected:false) removes that tag', async() => {
        const el = await mount({ props: { value: ['/tags/OL120T', '/tags/OL134T'] } });
        const changes = [];
        el.addEventListener('ol-tag-picker-change', (e) => changes.push(e.detail));

        const mangaChip = chipEls(el).find((c) => c.textContent.trim() === 'Manga');
        mangaChip.dispatchEvent(
            new CustomEvent('ol-chip-select', { detail: { selected: false }, bubbles: true, composed: true }),
        );
        await el.updateComplete;

        expect(chipNames(el)).toEqual(['Almanac']);
        expect(optionNames(el)).toContain('Manga'); // returns to the list
        expect(changes.at(-1)).toEqual({ value: ['/tags/OL120T'], added: null, removed: '/tags/OL134T' });
    });

    test('Backspace on an empty input removes the last chip', async() => {
        const el = await mount({ props: { value: ['/tags/OL120T', '/tags/OL134T'] } });
        input(el).dispatchEvent(new KeyboardEvent('keydown', { key: 'Backspace', bubbles: true }));
        await el.updateComplete;
        expect(chipNames(el)).toEqual(['Almanac']);
    });

    test('Backspace with a non-empty query does NOT remove a chip', async() => {
        const el = await mount({ props: { value: ['/tags/OL120T'] } });
        await type(el, 'nov');
        input(el).dispatchEvent(new KeyboardEvent('keydown', { key: 'Backspace', bubbles: true }));
        await el.updateComplete;
        expect(chipNames(el)).toEqual(['Almanac']);
    });
});

describe('ol-tag-picker keyboard navigation', () => {
    test('ArrowDown moves the active descendant through the listbox', async() => {
        const el = await mount();
        const field = input(el);
        // nothing active initially
        expect(field.getAttribute('aria-activedescendant')).toBeFalsy();
        field.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
        await el.updateComplete;
        const active = el.shadowRoot.querySelector('.option--active');
        expect(active).toBeTruthy();
        expect(field.getAttribute('aria-activedescendant')).toBe(active.id);
        expect(active.getAttribute('aria-selected')).toBe('true');
    });

    test('combobox wiring: aria-controls points at the listbox', async() => {
        const el = await mount();
        const field = input(el);
        expect(field.getAttribute('role')).toBe('combobox');
        expect(field.getAttribute('aria-expanded')).toBe('true');
        const listboxId = field.getAttribute('aria-controls');
        const listbox = el.shadowRoot.getElementById(listboxId);
        expect(listbox.getAttribute('role')).toBe('listbox');
    });
});

describe('ol-tag-picker form association', () => {
    test('formAssociatedValue posts one entry per selected key under `name`', async() => {
        const el = await mount({ attrs: { name: 'content_formats' }, props: { value: ['/tags/OL120T', { key: '/tags/OL134T' }] } });
        const fd = el.formAssociatedValue;
        expect(fd).toBeInstanceOf(FormData);
        expect(fd.getAll('content_formats')).toEqual(['/tags/OL120T', '/tags/OL134T']);
    });

    test('no name → no form value', async() => {
        const el = await mount({ props: { value: ['/tags/OL120T'] } });
        expect(el.formAssociatedValue).toBeNull();
    });

    test('empty selection → no form value', async() => {
        const el = await mount({ attrs: { name: 'content_formats' } });
        expect(el.formAssociatedValue).toBeNull();
    });

    test('formAssociatedReset restores the authored default selection', async() => {
        const el = await mount({ attrs: { name: 'content_formats' }, props: { value: ['/tags/OL120T'] } });
        el._selectKey('/tags/OL134T');
        await el.updateComplete;
        expect(chipNames(el).sort()).toEqual(['Almanac', 'Manga'].sort());
        el.formAssociatedReset();
        await el.updateComplete;
        expect(chipNames(el)).toEqual(['Almanac']);
    });
});

describe('ol-tag-picker never creates tags', () => {
    test('typing a non-existent name yields no options and selection is impossible', async() => {
        const el = await mount();
        const changes = vi.fn();
        el.addEventListener('ol-tag-picker-change', changes);
        await type(el, 'Nonexistent Format');
        input(el).dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
        await el.updateComplete;
        expect(chipEls(el)).toHaveLength(0);
        expect(changes).not.toHaveBeenCalled();
    });
});
