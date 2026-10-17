/**
 * <ol-login-dialog> and olLogin(): the in-page login. Each way in (password,
 * one-time code, archive.org's third-party keys) ends the same way — the
 * reader's key on <body>, ol-login-success at the document, show() resolved —
 * and a refusal keeps the dialog open with the server's message. Network is
 * stubbed at fetch; the native <dialog> methods jsdom lacks are stubbed as in
 * OlDrawer.test.js.
 */
import '../../../openlibrary/components/lit/OlLoginDialog.js';
import { loginDialog, olLogin } from '../../../openlibrary/components/lit/login-dialog.js';

let fetchCalls;

/** @param {(call: {url: string, init: RequestInit}) => {status: number, body?: object}} respond */
function stubFetch(respond) {
    fetchCalls = [];
    global.fetch = vi.fn(async (url, init) => {
        const call = { url: String(url), init };
        fetchCalls.push(call);
        const { status, body = {} } = respond(call);
        return { ok: status < 400, status, json: async () => body };
    });
}

const LOGGED_IN = { success: true, user_key: '/people/tester', redirect: '/' };

beforeAll(() => {
    const dialogProto = window.HTMLDialogElement.prototype;
    dialogProto.showModal = function () {
        this.open = true;
    };
    dialogProto.close = function () {
        this.open = false;
    };
    window.matchMedia = query => ({
        matches: false,
        media: query,
        addEventListener() {},
        removeEventListener() {},
        addListener() {},
        removeListener() {}
    });
    global.ResizeObserver = class {
        observe() {}
        disconnect() {}
    };
    window._paq = [];
});

afterEach(() => {
    document.body.innerHTML = '';
    delete document.body.dataset.userKey;
    window._paq = [];
});

const tick = () => new Promise(r => setTimeout(r, 0));
const q = (el, selector) => el.renderRoot.querySelector(selector);

async function mount(props = {}) {
    const el = document.createElement('ol-login-dialog');
    Object.assign(el, props);
    document.body.append(el);
    await el.updateComplete;
    return el;
}

/**
 * Open the dialog and keep the promise show() hands back, boxed: returning it
 * bare from an async helper would make `await` wait for the dialog to close.
 */
async function open(el, options) {
    const outcome = el.show(options);
    await el.updateComplete;
    return { outcome };
}

async function submit(el, formSelector, values) {
    for (const [selector, value] of Object.entries(values)) {
        const input = q(el, selector);
        input.value = value;
        input.dispatchEvent(new Event('input', { bubbles: true }));
    }
    q(el, formSelector).dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await tick();
    await el.updateComplete;
}

function loginEvents() {
    const seen = [];
    document.addEventListener('ol-login-success', e => seen.push(e.detail));
    return seen;
}

describe('ol-login-dialog layout', () => {
    test('says why, offers sign-up first, then the login form', async () => {
        const el = await mount({ signupHref: '/account/create' });
        await open(el, { message: 'Log in or sign up to rate this book.' });
        expect(q(el, '.message').textContent).toBe('Log in or sign up to rate this book.');
        const signup = q(el, '.signup ol-button');
        expect(signup.getAttribute('href')).toBe('/account/create');
        expect(signup.textContent.trim()).toBe('Create a free account');
        expect(q(el, 'ol-dialog').label).toBe('Log in or sign up');
        expect(q(el, '.form #login-email')).not.toBeNull();
        expect(q(el, '.form #login-password')).not.toBeNull();
    });

    test('takes a heading per open and translated labels', async () => {
        const el = await mount({ labels: { heading: 'Identifícate', signup: 'Crear cuenta' } });
        await open(el, { heading: 'Guarda este libro' });
        expect(q(el, 'ol-dialog').label).toBe('Guarda este libro');
        expect(q(el, '.signup ol-button').textContent.trim()).toBe('Crear cuenta');
        await open(el, { heading: '' });
        expect(q(el, 'ol-dialog').label).toBe('Identifícate');
    });

    test('renders the third-party frame only when given one, and only while open', async () => {
        const el = await mount({ thirdPartySrc: 'https://archive.org/account/login.thirdparty.php?origin=x' });
        expect(q(el, 'iframe.third-party').getAttribute('src')).toContain('login.thirdparty.php');
        const bare = await mount();
        expect(q(bare, 'iframe')).toBeNull();
    });
});

describe('ol-login-dialog with a password', () => {
    test('posts the form asking for JSON, tells the page, and resolves with the login', async () => {
        stubFetch(() => ({ status: 200, body: LOGGED_IN }));
        const seen = loginEvents();
        const el = await mount();
        const { outcome } = await open(el, { redirect: '/works/OL1W' });

        await submit(el, '.form', { '#login-email': 'reader@example.com', '#login-password': 'hunter2' });

        expect(fetchCalls).toHaveLength(1);
        const [{ url, init }] = fetchCalls;
        expect(url).toBe('/account/login');
        expect(init.method).toBe('POST');
        expect(init.headers.Accept).toBe('application/json');
        const body = new URLSearchParams(init.body);
        expect(body.get('username')).toBe('reader@example.com');
        expect(body.get('password')).toBe('hunter2');
        expect(body.get('redirect')).toBe('/works/OL1W');

        expect(document.body.dataset.userKey).toBe('/people/tester');
        expect(seen).toEqual([{ userKey: '/people/tester', method: 'password' }]);
        await expect(outcome).resolves.toEqual({ userKey: '/people/tester', method: 'password' });
        expect(el.open).toBe(false);
    });

    test("a refused login shows the server's message and stays open", async () => {
        stubFetch(() => ({ status: 400, body: { error: 'account_bad_password', errorDisplayString: 'Wrong password. Please try again' } }));
        const el = await mount();
        await open(el);
        await submit(el, '.form', { '#login-email': 'reader@example.com', '#login-password': 'nope' });
        expect(q(el, '.error').textContent).toContain('Wrong password. Please try again');
        expect(q(el, '.error a')).toBeNull();
        expect(el.open).toBe(true);
        expect(document.body.dataset.userKey).toBeUndefined();
    });

    test('an account that needs the login page is sent there', async () => {
        stubFetch(() => ({
            status: 400,
            body: { error: 'account_not_verified', errorDisplayString: 'Please verify your Open Library account before logging in' }
        }));
        const el = await mount();
        await open(el, { redirect: '/works/OL1W' });
        await submit(el, '.form', { '#login-email': 'reader@example.com', '#login-password': 'hunter2' });
        expect(q(el, '.error a').getAttribute('href')).toBe('/account/login?redirect=%2Fworks%2FOL1W');
        expect(q(el, '.error a').textContent).toBe('Continue on the login page');
    });

    test('a network failure is reported in words, not swallowed', async () => {
        global.fetch = vi.fn(async () => {
            throw new TypeError('Failed to fetch');
        });
        const el = await mount();
        await open(el);
        await submit(el, '.form', { '#login-email': 'reader@example.com', '#login-password': 'hunter2' });
        expect(q(el, '.error').textContent).toContain('A network error occurred');
    });

    test('dismissing resolves null and leaves the page signed out', async () => {
        const el = await mount();
        const { outcome } = await open(el);
        q(el, 'ol-dialog').close();
        await expect(outcome).resolves.toBeNull();
        expect(el.open).toBe(false);
        expect(document.body.dataset.userKey).toBeUndefined();
    });

    test('the next open starts clean', async () => {
        stubFetch(() => ({ status: 400, body: { error: 'account_bad_password', errorDisplayString: 'Wrong password' } }));
        const el = await mount();
        const { outcome: first } = await open(el);
        await submit(el, '.form', { '#login-email': 'reader@example.com', '#login-password': 'nope' });
        expect(q(el, '.error')).not.toBeNull();
        q(el, 'ol-dialog').close();
        await first;
        await open(el);
        expect(q(el, '.error')).toBeNull();
    });
});

describe('ol-login-dialog with a one-time code', () => {
    test('issues a code to the email, redeems what is typed, and resolves as an otp login', async () => {
        stubFetch(({ url }) => ({ status: 200, body: url.endsWith('/redeem') ? { ...LOGGED_IN, user_key: '/people/coder' } : { success: true } }));
        const seen = loginEvents();
        const el = await mount();
        const { outcome } = await open(el, { redirect: '/works/OL1W' });

        q(el, '.alt .link').click();
        await el.updateComplete;
        expect(q(el, '.form #otp-email')).not.toBeNull();
        expect(q(el, '.form #login-password')).toBeNull();

        await submit(el, '.form', { '#otp-email': 'reader@example.com' });
        expect(fetchCalls[0].url).toBe('/account/login/otp/issue');
        expect(new URLSearchParams(fetchCalls[0].init.body).get('email')).toBe('reader@example.com');
        const otpForm = q(el, 'ia-otp-form');
        expect(otpForm).not.toBeNull();
        expect(q(el, '.hint').textContent).toBe('We sent a 6-digit code to reader@example.com.');

        otpForm.dispatchEvent(new CustomEvent('codeSubmitted', { detail: '123456' }));
        await tick();
        await el.updateComplete;
        expect(fetchCalls[1].url).toBe('/account/login/otp/redeem');
        const body = new URLSearchParams(fetchCalls[1].init.body);
        expect(body.get('otp')).toBe('123456');
        expect(body.get('email')).toBe('reader@example.com');
        expect(body.get('redirect')).toBe('/works/OL1W');

        expect(seen).toEqual([{ userKey: '/people/coder', method: 'otp' }]);
        await expect(outcome).resolves.toEqual({ userKey: '/people/coder', method: 'otp' });
    });

    test('a refused code is shown on the code form, not as a fresh start', async () => {
        stubFetch(({ url }) => ({ status: 200, body: url.endsWith('/redeem') ? { error: 'invalid_otp' } : { success: true } }));
        const el = await mount();
        await open(el);
        q(el, '.alt .link').click();
        await el.updateComplete;
        await submit(el, '.form', { '#otp-email': 'reader@example.com' });
        q(el, 'ia-otp-form').dispatchEvent(new CustomEvent('codeSubmitted', { detail: '000000' }));
        await tick();
        await el.updateComplete;
        expect(q(el, 'ia-otp-form').validationStatus).toBe('error');
        expect(el.open).toBe(true);
    });

    test('too many codes asked for says so', async () => {
        stubFetch(() => ({ status: 429, body: { error: 'ratelimit' } }));
        const el = await mount();
        await open(el);
        q(el, '.alt .link').click();
        await el.updateComplete;
        await submit(el, '.form', { '#otp-email': 'reader@example.com' });
        expect(q(el, '.error').textContent).toContain('Too many attempts');
        expect(q(el, 'ia-otp-form')).toBeNull();
    });

    test('there is a way back to the password form', async () => {
        const el = await mount();
        await open(el);
        q(el, '.alt .link').click();
        await el.updateComplete;
        q(el, '.alt .link').click();
        await el.updateComplete;
        expect(q(el, '.form #login-password')).not.toBeNull();
    });
});

describe('ol-login-dialog with third-party keys', () => {
    function keysFrom(origin) {
        window.dispatchEvent(new MessageEvent('message', { origin, data: { type: 's3-keys', s3: { access: 'AK', secret: 'SK' } } }));
    }

    test("archive.org's keys log in through the same form POST", async () => {
        stubFetch(() => ({ status: 200, body: LOGGED_IN }));
        const el = await mount({ thirdPartySrc: 'https://archive.org/account/login.thirdparty.php' });
        const { outcome } = await open(el);
        keysFrom('https://archive.org');
        await tick();
        expect(fetchCalls).toHaveLength(1);
        expect(fetchCalls[0].url).toBe('/account/login');
        const body = new URLSearchParams(fetchCalls[0].init.body);
        expect(body.get('access')).toBe('AK');
        expect(body.get('secret')).toBe('SK');
        await expect(outcome).resolves.toEqual({ userKey: '/people/tester', method: 'third-party' });
    });

    test('keys from anywhere else, or arriving while closed, are ignored', async () => {
        stubFetch(() => ({ status: 200, body: LOGGED_IN }));
        const el = await mount({ thirdPartySrc: 'https://archive.org/account/login.thirdparty.php' });
        keysFrom('https://archive.org');
        await tick();
        expect(fetchCalls).toHaveLength(0);
        await open(el);
        keysFrom('https://archive.org.evil.example');
        await tick();
        expect(fetchCalls).toHaveLength(0);
    });

    test('the frame takes the height archive.org reports', async () => {
        const el = await mount({ thirdPartySrc: 'https://archive.org/account/login.thirdparty.php' });
        await open(el);
        window.dispatchEvent(new MessageEvent('message', { origin: 'https://archive.org', data: { type: 'resize', height: 96 } }));
        expect(q(el, 'iframe.third-party').style.height).toBe('96px');
    });
});

describe('olLogin()', () => {
    test('resolves at once for a reader who is already in', async () => {
        document.body.dataset.userKey = '/people/tester';
        await expect(olLogin({ message: 'x' })).resolves.toEqual({ userKey: '/people/tester', method: 'session' });
        expect(document.querySelector('ol-login-dialog')).toBeNull();
    });

    test('reuses the dialog the shell rendered, creating one only when there is none', async () => {
        const created = loginDialog();
        expect(created.tagName).toBe('OL-LOGIN-DIALOG');
        expect(loginDialog()).toBe(created);
        const outcome = olLogin({ message: 'Log in or sign up to add books to your reading log.' });
        await tick();
        await created.updateComplete;
        expect(created.open).toBe(true);
        expect(q(created, '.message').textContent).toBe('Log in or sign up to add books to your reading log.');
        q(created, 'ol-dialog').close();
        await expect(outcome).resolves.toBeNull();
    });
});
