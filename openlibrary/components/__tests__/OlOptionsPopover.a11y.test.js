/**
 * Accessibility tests for OlOptionsPopover.
 *
 * Renders the real component so axe inspects its actual shadow DOM: the ARIA
 * wiring on the slotted trigger, and the radiogroup of options once open.
 */
import { checkA11y, cleanup, mount, openPopover, setupComponentEnv } from '../test-utils/a11y.js';
import '../lit/OlOptionsPopover.js';

const ITEMS = [
    { value: 'all', label: 'Full Card Catalog' },
    { value: 'readable', label: 'Readable Books Only' },
];

const MARKUP = `
    <ol-options-popover aria-label="Availability">
        <button slot="trigger" type="button">Availability</button>
    </ol-options-popover>
`;

/** The OlPopover this component composes around; it owns the open state. */
const innerPopover = (el) => el.shadowRoot.querySelector('ol-popover');

async function mountOptions(props = {}) {
    const el = await mount(MARKUP);
    Object.assign(el, { label: 'Availability', heading: 'AVAILABILITY', items: ITEMS, selected: 'all', ...props });
    await el.updateComplete;
    return el;
}

async function mountOpened(props = {}) {
    const el = await mountOptions(props);
    await openPopover(innerPopover(el));
    return el;
}

beforeEach(() => setupComponentEnv());
afterEach(cleanup);

describe('OlOptionsPopover a11y', () => {
    test('closed: the slotted trigger advertises the popover it controls', async() => {
        const el = await mountOptions();

        const trigger = el.querySelector('[slot="trigger"]');
        expect(trigger.getAttribute('aria-haspopup')).toBe('dialog');
        expect(trigger.getAttribute('aria-expanded')).toBe('false');
        expect(await checkA11y()).toHaveNoViolations();
    });

    test('open: options form a labelled radiogroup inside the dialog', async() => {
        const el = await mountOpened();

        expect(innerPopover(el).shadowRoot.querySelector('.panel')).not.toBeNull();
        const group = el.shadowRoot.querySelector('[role="radiogroup"]');
        expect(group.getAttribute('aria-label')).toBe('Availability');
        expect(group.querySelectorAll('input[type="radio"]')).toHaveLength(ITEMS.length);
        expect(await checkA11y()).toHaveNoViolations();
    });

    test('open: each radio takes its accessible name from its wrapping label', async() => {
        const el = await mountOpened();

        const radios = [...el.shadowRoot.querySelectorAll('input[type="radio"]')];
        expect(radios).toHaveLength(ITEMS.length);
        radios.forEach((radio, i) => {
            const label = radio.closest('label');
            expect(label).not.toBeNull();
            expect(label.textContent).toContain(ITEMS[i].label);
        });
    });

    test('open: the visual group heading is hidden from assistive tech', async() => {
        // The radiogroup's aria-label already names the group, so exposing the
        // heading as well would announce "Availability" twice.
        const el = await mountOpened();

        expect(el.shadowRoot.querySelector('.group-heading').getAttribute('aria-hidden')).toBe('true');
    });

    test('regression guard: with no label the composed dialog is unnamed', async() => {
        // OlOptionsPopover passes its aria-label/label down to the inner
        // OlPopover. Drop both and axe should report the dialog as unnamed.
        const el = await mount('<ol-options-popover><button slot="trigger" type="button">Options</button></ol-options-popover>');
        Object.assign(el, { heading: 'AVAILABILITY', items: ITEMS, selected: 'all' });
        await el.updateComplete;
        await openPopover(innerPopover(el));

        const results = await checkA11y();
        expect(results.violations.map((v) => v.id)).toContain('aria-dialog-name');
    });
});

describe('OlOptionsPopover search', () => {
    const MANY = ['Arabic', 'Bengali', 'Chinese', 'Dutch', 'English', 'Old English', 'French', 'German', 'Hindi']
        .map((label) => ({ value: label.toLowerCase().replace(' ', '-'), label }));
    const filterInput = (el) => el.shadowRoot.querySelector('.filter-input');
    const labels = (el) => [...el.shadowRoot.querySelectorAll('.item-label')].map((n) => n.textContent);
    const type = async(el, text) => {
        const input = filterInput(el);
        input.value = text;
        input.dispatchEvent(new Event('input'));
        await el.updateComplete;
    };
    const press = (target, key) => target.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, composed: true }));

    test('no filter at or under the threshold', async() => {
        const el = await mountOpened();
        expect(filterInput(el)).toBeNull();
    });

    test('past the threshold a labelled filter narrows the list', async() => {
        const el = await mountOpened({ items: MANY, selected: '' });
        expect(filterInput(el)).not.toBeNull();

        await type(el, 'engl');
        expect(labels(el)).toEqual(['English', 'Old English']);
        expect(await checkA11y()).toHaveNoViolations();

        await type(el, 'zzz');
        expect(el.shadowRoot.querySelector('.empty-state').textContent).toBe('No matches');
    });

    test('Enter in the filter commits an exact match, not an ambiguous one', async() => {
        const el = await mountOpened({ items: MANY, selected: '' });

        await type(el, 'engl');
        press(filterInput(el), 'Enter');
        expect(el.selected).toBe('');

        await type(el, 'english');
        press(filterInput(el), 'Enter');
        expect(el.selected).toBe('english');
    });

    test('with a filter, arrows move focus without changing the value', async() => {
        const el = await mountOpened({ items: MANY, selected: 'arabic' });
        const radios = el.shadowRoot.querySelectorAll('.item-radio');
        radios[0].focus();
        press(radios[0], 'ArrowDown');

        expect(el.shadowRoot.activeElement).toBe(radios[1]);
        expect(el.selected).toBe('arabic');
    });

    test('show-selection labels the default trigger with the choice', async() => {
        const el = await mount('<ol-options-popover label="Choose a language" show-selection></ol-options-popover>');
        Object.assign(el, { items: MANY, selected: 'french' });
        await el.updateComplete;
        expect(el.querySelector('ol-button').textContent.trim()).toBe('French');

        el.selected = '';
        await el.updateComplete;
        expect(el.querySelector('ol-button').textContent.trim()).toBe('Choose a language');
    });
});
