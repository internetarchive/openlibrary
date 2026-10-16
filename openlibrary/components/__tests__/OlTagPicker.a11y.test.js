/**
 * Accessibility tests for OlTagPicker.
 *
 * Renders the real component so axe inspects its actual shadow DOM: the slotted
 * trigger and the selection chips when closed, and the combobox + listbox once
 * the popover is open.
 */
import { checkA11y, cleanup, mount, openPopover, setupComponentEnv } from '../test-utils/a11y.js';
import '../lit/OlTagPicker.js';

const OPTIONS = [
    { key: '/tags/OL120T', name: 'Almanac' },
    { key: '/tags/OL134T', name: 'Manga' },
    { key: '/tags/OL136T', name: 'Novel' },
    { key: '/tags/OL130T', name: 'Essays' },
];

const MARKUP = `
    <ol-tag-picker tag-type="content_formats" aria-label="Content formats">
        <button slot="trigger" type="button">+ Add Content Formats</button>
    </ol-tag-picker>
`;

/** The OlPopover this component composes around; it owns the open state. */
const innerPopover = (el) => el.shadowRoot.querySelector('ol-popover');

async function mountPicker(props = {}) {
    const el = await mount(MARKUP);
    Object.assign(el, { options: OPTIONS, ...props });
    await el.updateComplete;
    return el;
}

async function mountOpened(props = {}) {
    const el = await mountPicker(props);
    await openPopover(innerPopover(el));
    return el;
}

beforeEach(() => setupComponentEnv());
afterEach(cleanup);

describe('OlTagPicker a11y', () => {
    test('closed: no violations, selections render as chips', async() => {
        const el = await mountPicker({ value: ['/tags/OL120T', '/tags/OL134T'] });

        const chips = [...el.shadowRoot.querySelectorAll('ol-chip')];
        expect(chips).toHaveLength(2);
        expect(await checkA11y()).toHaveNoViolations();
    });

    test('open: combobox + listbox are wired and labelled, no violations', async() => {
        const el = await mountOpened();

        const combo = el.shadowRoot.querySelector('[role="combobox"]');
        expect(combo.getAttribute('aria-expanded')).toBe('true');
        expect(combo.getAttribute('aria-autocomplete')).toBe('list');
        expect(combo.getAttribute('aria-label')).toBe('Content formats');

        const listbox = el.shadowRoot.getElementById(combo.getAttribute('aria-controls'));
        expect(listbox.getAttribute('role')).toBe('listbox');
        expect(listbox.querySelectorAll('[role="option"]')).toHaveLength(OPTIONS.length);

        expect(await checkA11y()).toHaveNoViolations();
    });

    test('open with a selection: options exclude it and chips carry a remove name', async() => {
        const el = await mountOpened({ value: ['/tags/OL134T'] });

        const optionNames = [...el.shadowRoot.querySelectorAll('[role="option"]')].map((o) => o.textContent.trim());
        expect(optionNames).not.toContain('Manga');

        const chip = el.shadowRoot.querySelector('ol-chip');
        // OLChip maps accessible-label onto its inner button's aria-label.
        expect(chip.getAttribute('accessible-label')).toBe('Remove Manga');

        expect(await checkA11y()).toHaveNoViolations();
    });

    test('open: an active option is referenced by aria-activedescendant and marked selected', async() => {
        const el = await mountOpened();
        const combo = el.shadowRoot.querySelector('[role="combobox"]');
        combo.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
        await el.updateComplete;

        const activeId = combo.getAttribute('aria-activedescendant');
        expect(activeId).toBeTruthy();
        const active = el.shadowRoot.getElementById(activeId);
        expect(active.getAttribute('role')).toBe('option');
        expect(active.getAttribute('aria-selected')).toBe('true');

        expect(await checkA11y()).toHaveNoViolations();
    });

    test('open with no matches: empty state keeps the listbox valid, no violations', async() => {
        const el = await mountOpened();
        const combo = el.shadowRoot.querySelector('[role="combobox"]');
        combo.value = 'nothing-matches-this';
        combo.dispatchEvent(new Event('input'));
        await el.updateComplete;

        expect(el.shadowRoot.querySelectorAll('[role="option"]')).toHaveLength(0);
        expect(await checkA11y()).toHaveNoViolations();
    });
});
