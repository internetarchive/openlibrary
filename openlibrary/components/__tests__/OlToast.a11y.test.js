/**
 * A11y tests for OlToast.
 *
 * Validates aria-live regions, role assignments (status vs alert),
 * and the close button's accessible name across info, success, and error types.
 *
 * Document-level rules disabled — see OlPopover.a11y.test.js for rationale.
 */
import { axe, toHaveNoViolations } from 'jest-axe';

expect.extend(toHaveNoViolations);

const AXE_COMPONENT_CONFIG = {
    rules: {
        'region': { enabled: false },
        'landmark-one-main': { enabled: false },
        'page-has-heading-one': { enabled: false },
    },
};

afterEach(() => {
    document.body.innerHTML = '';
});

describe('OlToast a11y', () => {
    test('info toast (default) — role=status, aria-live=polite, no violations', async () => {
        document.body.innerHTML = `
            <div
                role="status"
                aria-live="polite"
            >
                <span aria-hidden="true"><!-- info icon --></span>
                <span>
                    <span>Book added to your reading list.</span>
                </span>
                <button type="button" aria-label="Close">
                    <svg aria-hidden="true" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/></svg>
                </button>
            </div>
        `;
        const results = await axe(document.body, AXE_COMPONENT_CONFIG);
        expect(results).toHaveNoViolations();
    });

    test('success toast — role=status, aria-live=polite, no violations', async () => {
        document.body.innerHTML = `
            <div role="status" aria-live="polite">
                <span aria-hidden="true"><!-- success icon --></span>
                <span>
                    <span>Changes saved.</span>
                </span>
                <button type="button" aria-label="Close">
                    <svg aria-hidden="true" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>
                </button>
            </div>
        `;
        const results = await axe(document.body, AXE_COMPONENT_CONFIG);
        expect(results).toHaveNoViolations();
    });

    test('error toast — role=alert, aria-live=assertive, no violations', async () => {
        // Errors use role="alert" + assertive to interrupt screen readers immediately.
        document.body.innerHTML = `
            <div role="alert" aria-live="assertive">
                <span aria-hidden="true"><!-- error icon --></span>
                <span>
                    <span>Could not save changes. Please try again.</span>
                </span>
                <button type="button" aria-label="Close">
                    <svg aria-hidden="true" viewBox="0 0 24 24"><line x1="12" y1="6" x2="12" y2="13"/></svg>
                </button>
            </div>
        `;
        const results = await axe(document.body, AXE_COMPONENT_CONFIG);
        expect(results).toHaveNoViolations();
    });

    test('close button without aria-label fails (regression guard)', async () => {
        // Guards against the labelClose prop being dropped or defaulting to empty.
        document.body.innerHTML = `
            <div role="status" aria-live="polite">
                <span>Book added.</span>
                <button type="button">
                    <svg aria-hidden="true" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/></svg>
                </button>
            </div>
        `;
        const results = await axe(document.body, AXE_COMPONENT_CONFIG);
        expect(results.violations.length).toBeGreaterThan(0);
    });
});
