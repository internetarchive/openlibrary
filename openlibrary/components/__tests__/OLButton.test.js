/**
 * OLButton renders a real <button> into the light DOM, and only that button is
 * the form's submitter — so anything the browser reads off a submitter has to
 * be forwarded to it. The /status bulk actions rely on that for the plain form
 * post they fall back to before the controller loads.
 */
import { cleanup, mount, setupComponentEnv } from '../test-utils/a11y.js';
import '../lit/OLButton.js';

beforeEach(() => setupComponentEnv());
afterEach(cleanup);

describe('ol-button', () => {
    test('forwards formaction to the inner button', async() => {
        const el = await mount('<ol-button type="submit" formaction="/status/enable">Enable</ol-button>');

        const button = el.querySelector('button');
        expect(button.getAttribute('type')).toBe('submit');
        expect(button.getAttribute('formaction')).toBe('/status/enable');
    });

    test('leaves formaction off when the host has none', async() => {
        const el = await mount('<ol-button type="submit">Save</ol-button>');

        expect(el.querySelector('button').hasAttribute('formaction')).toBe(false);
    });
});
