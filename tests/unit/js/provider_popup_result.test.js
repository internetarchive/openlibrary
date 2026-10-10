/**
 * The script inside `templates/borrow/provider_popup_result.html.jinja`.
 *
 * It is the half of the popup contract that lives in a template rather than in
 * the bundle, so nothing in this suite reached it: the Python tests assert on
 * the rendered *source text*, which cannot tell a navigation that happens from
 * a string that is present. This file executes the real script.
 *
 * It reads the shipped template and runs the script it finds there, rather
 * than a copy pasted into this file. A copy would drift and a drift guard
 * would be the tell that the copy was the problem. The `<script>` block
 * contains no Jinja, so the text in the file is the text the browser gets --
 * which the first test below asserts, because it is the premise everything
 * here rests on.
 *
 * Globals are injected as function parameters rather than patched onto the
 * real `window`: jsdom refuses to navigate and makes `location.replace`
 * awkward to spy on, and the script touches nothing except `window.*`,
 * `document.*` and `screen.*`.
 */
import {readFileSync} from 'fs';
import {resolve} from 'path';

const TEMPLATE = resolve(__dirname, '../../../openlibrary/templates/borrow/provider_popup_result.html.jinja');
const READ_URL = 'https://lennyforlibraries.org/v1/api/items/51008637/read';
const MESSAGE_TYPE = 'ol-provider-borrow';

function shippedScript() {
    const source = readFileSync(TEMPLATE, 'utf-8');
    const match = source.match(/<script>\n([\s\S]*?)\n<\/script>/);
    if (!match) throw new Error(`no <script> block in ${TEMPLATE}`);
    return match[1];
}

/** The attributes `lenny.render_borrowed` / `render_error` put on the div. */
function mount({ok = true, readUrl = READ_URL, returnUrl = '/books/OL51008637M'} = {}) {
    document.body.innerHTML = `
        <div id="provider-borrow-result"
             data-ok="${ok ? '1' : '0'}"
             data-return-url="${returnUrl}"
             data-read-url="${readUrl}"
             data-message-type="${MESSAGE_TYPE}">
            <a class="js-provider-borrow-return" href="${returnUrl}">Back</a>
        </div>`;
}

function fakeWindow(opener) {
    return {
        opener,
        location: {origin: 'https://openlibrary.org', replace: vi.fn(), assign: vi.fn()},
        close: vi.fn(),
        resizeTo: vi.fn(),
    };
}

function run(win) {

    new Function('window', 'document', 'screen', shippedScript())(win, document, {availWidth: 1600, availHeight: 1200});
}

describe('the popup result script', () => {
    let opener;

    beforeEach(() => {
        opener = {closed: false, postMessage: vi.fn(), focus: vi.fn(), location: {assign: vi.fn()}};
    });

    test('the script it runs is the one in the shipped template', () => {
        // The premise of this file. If the block ever grows a Jinja expression
        // this stops being true and every assertion below is about something
        // the browser never sees.
        const script = shippedScript();
        expect(script).toContain('provider-borrow-result');
        expect(script).not.toMatch(/\{\{|\{%/);
    });

    test('a borrowed window goes to the reader', () => {
        mount();
        const win = fakeWindow(opener);

        run(win);

        expect(win.location.replace).toHaveBeenCalledWith(READ_URL);
    });

    test('the opener is told the loan exists', () => {
        mount();
        const win = fakeWindow(opener);

        run(win);

        expect(opener.postMessage).toHaveBeenCalledWith({type: MESSAGE_TYPE, ok: true}, 'https://openlibrary.org');
    });

    test('the opener is told before this window navigates', () => {
        // Ordering, exercised rather than read off the source: an unload
        // partway through loses the message, and the message is the only thing
        // that refreshes the book page.
        mount();
        const order = [];
        opener.postMessage = vi.fn(() => order.push('post'));
        const win = fakeWindow(opener);
        win.location.replace = vi.fn(() => order.push('replace'));

        run(win);

        expect(order).toEqual(['post', 'replace']);
    });

    test('the window is not closed, because it is becoming the reader', () => {
        mount();
        const win = fakeWindow(opener);

        run(win);

        expect(win.close).not.toHaveBeenCalled();
    });

    test('a blocked popup with no opener still reaches the reader', () => {
        // The target="_blank" fallback. It cannot refresh the book page --
        // there is nothing to refresh -- but the patron still gets the book
        // instead of a confirmation page.
        mount();
        const win = fakeWindow(null);

        run(win);

        expect(win.location.replace).toHaveBeenCalledWith(READ_URL);
    });

    test('a closed opener is not posted to', () => {
        mount();
        opener.closed = true;
        const win = fakeWindow(opener);

        run(win);

        expect(opener.postMessage).not.toHaveBeenCalled();
        expect(win.location.replace).toHaveBeenCalledWith(READ_URL);
    });

    test('a failure stays on screen rather than navigating', () => {
        mount({ok: false, readUrl: ''});
        const win = fakeWindow(opener);

        run(win);

        expect(win.location.replace).not.toHaveBeenCalled();
        expect(opener.postMessage).toHaveBeenCalledWith({type: MESSAGE_TYPE, ok: false}, 'https://openlibrary.org');
    });

    test('a failure sends the Back link to the page the patron came from', () => {
        mount({ok: false, readUrl: ''});
        const win = fakeWindow(opener);
        run(win);

        document.querySelector('.js-provider-borrow-return').dispatchEvent(
            new MouseEvent('click', {bubbles: true, cancelable: true})
        );

        expect(opener.location.assign).toHaveBeenCalledWith(expect.stringContaining('/books/OL51008637M'));
        expect(win.close).toHaveBeenCalledOnce();
    });

    test('a success with no reader to go to closes instead of hanging', () => {
        mount({readUrl: ''});
        const win = fakeWindow(opener);

        run(win);

        expect(win.location.replace).not.toHaveBeenCalled();
        expect(win.close).toHaveBeenCalledOnce();
    });

    test('a popup is resized, because 520px is a consent screen and not a book', () => {
        mount();
        const win = fakeWindow(opener);

        run(win);

        expect(win.resizeTo).toHaveBeenCalledWith(1200, 1000);
    });

    test('a resize a browser refuses does not stop the reader loading', () => {
        mount();
        const win = fakeWindow(opener);
        win.resizeTo = vi.fn(() => {
            throw new Error('nope');
        });

        run(win);

        expect(win.location.replace).toHaveBeenCalledWith(READ_URL);
    });
});
