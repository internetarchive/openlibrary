/**
 * Accessibility tests for OlOptionsPopover.
 *
 * Renders the real component so axe inspects its actual shadow DOM: the ARIA
 * wiring on the slotted trigger, and the radiogroup of options once open.
 */
import { toHaveNoViolations } from 'jest-axe';
import { checkA11y, cleanup, mount, openPopover, setupComponentEnv } from '../test-utils/a11y.js';
import '../lit/OlOptionsPopover.js';

expect.extend(toHaveNoViolations);

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
