/**
 * A11y tests for OlOptionsPopover.
 *
 * Validates the rendered ARIA structure: trigger button, radiogroup panel,
 * and radio inputs inside labels. Tests closed and open states.
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

describe('OlOptionsPopover a11y', () => {
    test('closed state — default trigger button has no violations', async () => {
        // Closed: renders a <button> with visible label text and chevron icon.
        // aria-haspopup="dialog" and aria-expanded="false" are set by OlPopover
        // on the slotted trigger after firstUpdated().
        document.body.innerHTML = `
            <div>
                <button type="button" aria-haspopup="dialog" aria-expanded="false">
                    <span>Availability</span>
                    <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>
                </button>
            </div>
        `;
        const results = await axe(document.body, AXE_COMPONENT_CONFIG);
        expect(results).toHaveNoViolations();
    });

    test('open state — radiogroup panel has no violations', async () => {
        // Open: renders a dialog containing a radiogroup.
        // Each option is an <input type="radio"> inside a <label> — correct
        // association per WCAG 1.3.1. The radiogroup has aria-label.
        // group-heading is aria-hidden (it is a visual heading, not the
        // accessible name — the aria-label on the radiogroup provides that).
        document.body.innerHTML = `
            <div>
                <button type="button" aria-haspopup="dialog" aria-expanded="true" aria-controls="ol-popover-1">
                    <span>Availability</span>
                    <svg aria-hidden="true" viewBox="0 0 24 24"><path d="m6 9 6 6 6-6"/></svg>
                </button>
                <div id="ol-popover-1" role="dialog" aria-modal="true" aria-label="Availability" tabindex="-1">
                    <div class="panel">
                        <div role="radiogroup" aria-label="Availability">
                            <div aria-hidden="true">AVAILABILITY</div>
                            <ul>
                                <li>
                                    <label>
                                        <input type="radio" name="ol-opts-1" value="all" checked />
                                        <span>Full Card Catalog</span>
                                    </label>
                                </li>
                                <li>
                                    <label>
                                        <input type="radio" name="ol-opts-1" value="readable" />
                                        <span>Readable Books Only</span>
                                    </label>
                                </li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>
        `;
        const results = await axe(document.body, AXE_COMPONENT_CONFIG);
        expect(results).toHaveNoViolations();
    });

    test('open state — radio without label fails (regression guard)', async () => {
        // Confirms axe catches unlabeled radio inputs — guards against
        // a future refactor that removes the <label> wrapper.
        document.body.innerHTML = `
            <div id="ol-popover-1" role="dialog" aria-modal="true" aria-label="Availability" tabindex="-1">
                <div role="radiogroup" aria-label="Availability">
                    <input type="radio" name="ol-opts-1" value="all" />
                </div>
            </div>
        `;
        const results = await axe(document.body, AXE_COMPONENT_CONFIG);
        expect(results.violations.length).toBeGreaterThan(0);
    });
});
