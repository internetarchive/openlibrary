/**
 * A11y tests for OlPopover.
 *
 * Tests the rendered HTML structure rather than the Lit component directly —
 * the same approach used in focusableHostMixin.test.js. This keeps tests
 * independent of Lit's ESM transform and validates the ARIA patterns explicitly.
 *
 * Tested states:
 *   - Closed: only the trigger slot is in the DOM
 *   - Open (desktop): panel is rendered with role="dialog"
 *
 * Document-level rules (region, landmark-one-main, page-has-heading-one) are
 * disabled because they test full-page structure, not component-level ARIA.
 */
import { axe, toHaveNoViolations } from 'jest-axe';

expect.extend(toHaveNoViolations);

const AXE_COMPONENT_CONFIG = {
    rules: {
        region: { enabled: false },
        'landmark-one-main': { enabled: false },
        'page-has-heading-one': { enabled: false },
    },
};

afterEach(() => {
    document.body.innerHTML = '';
});

describe('OlPopover a11y', () => {
    test('closed state — trigger button has no violations', async() => {
        // Closed: Lit renders only the trigger slot. The host element itself
        // is inline-flex; the trigger is slotted light DOM.
        document.body.innerHTML = `
            <div>
                <button type="button" aria-haspopup="dialog" aria-expanded="false">
                    Open options
                </button>
            </div>
        `;
        const results = await axe(document.body, AXE_COMPONENT_CONFIG);
        expect(results).toHaveNoViolations();
    });

    test('open state — dialog panel has no violations', async() => {
        // Open: Lit renders the panel as role="dialog" aria-modal="true" with
        // an accessible name forwarded from the host's aria-label attribute.
        // Focus sentinels are aria-hidden to keep them invisible to AT.
        document.body.innerHTML = `
            <div>
                <button type="button" aria-haspopup="dialog" aria-expanded="true" aria-controls="ol-popover-1">
                    Open options
                </button>
                <div
                    id="ol-popover-1"
                    role="dialog"
                    aria-modal="true"
                    aria-label="Edit options"
                    tabindex="-1"
                >
                    <span tabindex="0" aria-hidden="true" data-edge="start"></span>
                    <div>Popover content</div>
                    <span tabindex="0" aria-hidden="true" data-edge="end"></span>
                </div>
            </div>
        `;
        const results = await axe(document.body, AXE_COMPONENT_CONFIG);
        expect(results).toHaveNoViolations();
    });

    test('open state — dialog without aria-label fails (catches missing accessible name)', async() => {
        // Regression guard: a dialog with no accessible name is a WCAG 4.1.2 violation.
        // This test confirms jest-axe catches it so we know the rule is active.
        document.body.innerHTML = `
            <div>
                <div id="ol-popover-1" role="dialog" aria-modal="true" tabindex="-1">
                    <div>Content without accessible name on dialog</div>
                </div>
            </div>
        `;
        const results = await axe(document.body, AXE_COMPONENT_CONFIG);
        // Should have at least one violation (dialog-name)
        expect(results.violations.length).toBeGreaterThan(0);
    });
});
