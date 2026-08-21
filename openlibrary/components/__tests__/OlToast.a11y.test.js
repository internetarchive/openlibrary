/**
 * Accessibility tests for OlToast.
 *
 * Renders the real component so axe inspects its actual shadow DOM: the
 * role/aria-live pairing per type, and the close button's accessible name.
 */
import { toHaveNoViolations } from 'jest-axe';
import { checkA11y, cleanup, mount, nextFrames, setupComponentEnv } from '../test-utils/a11y.js';
import '../lit/OlToast.js';

expect.extend(toHaveNoViolations);

beforeEach(() => setupComponentEnv());
afterEach(cleanup);

describe('OlToast a11y', () => {
    test.each([
        ['info', 'status', 'polite'],
        ['success', 'status', 'polite'],
        ['error', 'alert', 'assertive'],
    ])('%s toast announces via role=%s aria-live=%s', async(type, role, live) => {
        const el = await mount(`<ol-toast type="${type}" message="Changes saved."></ol-toast>`);
        await nextFrames();

        const toast = el.shadowRoot.querySelector('[aria-live]');
        expect(toast.getAttribute('role')).toBe(role);
        expect(toast.getAttribute('aria-live')).toBe(live);
        expect(await checkA11y()).toHaveNoViolations();
    });

    test('close button has an accessible name', async() => {
        const el = await mount('<ol-toast message="Changes saved."></ol-toast>');
        // The close control is an <ol-button>; the real <button> lives in its shadow root.
        const button = el.shadowRoot.querySelector('ol-button').shadowRoot.querySelector('button');
        expect(button.getAttribute('aria-label')).toBe('Close');
    });

    test('regression guard: an unlabelled close button is reported as button-name', async() => {
        await mount('<ol-toast message="Changes saved." label-close=""></ol-toast>');
        const results = await checkA11y();
        expect(results.violations.map((v) => v.id)).toContain('button-name');
    });
});
