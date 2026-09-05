/**
 * Accessibility tests for OlPopover.
 *
 * Renders the real component so axe inspects its actual shadow DOM: the ARIA
 * wiring the component writes onto the slotted trigger, and the panel's
 * dialog semantics once open.
 */
import { toHaveNoViolations } from 'jest-axe';
import { checkA11y, cleanup, mount, openPopover, setupComponentEnv } from '../test-utils/a11y.js';
import '../lit/OlPopover.js';

expect.extend(toHaveNoViolations);

const POPOVER = `
    <ol-popover aria-label="Edit options">
        <button slot="trigger" type="button">Open options</button>
    </ol-popover>
`;

beforeEach(() => setupComponentEnv());
afterEach(cleanup);

describe('OlPopover a11y', () => {
    test('closed: the trigger advertises the popover it controls', async() => {
        const el = await mount(POPOVER);

        const trigger = el.querySelector('[slot="trigger"]');
        expect(trigger.getAttribute('aria-haspopup')).toBe('dialog');
        expect(trigger.getAttribute('aria-expanded')).toBe('false');
        expect(trigger.hasAttribute('aria-controls')).toBe(false);
        expect(await checkA11y()).toHaveNoViolations();
    });

    test('open: the panel is a named dialog and the trigger reports it expanded', async() => {
        const el = await openPopover(await mount(POPOVER));

        const panel = el.shadowRoot.querySelector('[role="dialog"]');
        expect(panel.getAttribute('aria-label')).toBe('Edit options');

        const trigger = el.querySelector('[slot="trigger"]');
        expect(trigger.getAttribute('aria-expanded')).toBe('true');
        // No aria-controls: the trigger is slotted from outside the shadow
        // root and the panel's id is inside it, so the IDREF could never
        // resolve. A dangling reference is worse than none.
        expect(trigger.hasAttribute('aria-controls')).toBe(false);
        expect(await checkA11y()).toHaveNoViolations();
    });

    test('open: the panel is not aria-modal, so Tab can leave it', async() => {
        // A popover is deliberately non-modal — the focus sentinels close it on
        // exit rather than trapping focus. aria-modal would misreport that to AT.
        const el = await openPopover(await mount(POPOVER));

        expect(el.shadowRoot.querySelector('[role="dialog"]').hasAttribute('aria-modal')).toBe(false);
    });

    test('open on mobile: the tray is still a named dialog', async() => {
        // The tray renders a backdrop and different markup than the desktop
        // panel, so it needs its own pass rather than riding on the above.
        setupComponentEnv({ mobile: true });
        const el = await openPopover(await mount(POPOVER));

        const panel = el.shadowRoot.querySelector('[role="dialog"]');
        expect(panel.classList.contains('tray')).toBe(true);
        expect(await checkA11y()).toHaveNoViolations();
    });

    test('regression guard: a panel with no aria-label is reported as an unnamed dialog', async() => {
        const el = await mount('<ol-popover><button slot="trigger" type="button">Open</button></ol-popover>');
        await openPopover(el);

        const results = await checkA11y();
        expect(results.violations.map((v) => v.id)).toContain('aria-dialog-name');
    });
});
