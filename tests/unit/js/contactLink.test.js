import { buildContactBody, withBody, pageUrl, DEFAULT_NOTE, DEFAULT_PRIVACY } from '../../../openlibrary/plugins/openlibrary/js/contact-link.js';

const strings = { note: DEFAULT_NOTE, privacy: DEFAULT_PRIVACY };
const env = {
    url: 'https://openlibrary.org/search?q=dune',
    account: 'https://openlibrary.org/people/bob',
    userAgent: 'Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)',
    viewport: { width: 820, height: 1030 }
};

describe('buildContactBody', () => {
    test('leaves room for the message, then the notes and details', () => {
        const lines = buildContactBody(strings, env).split('\r\n');
        expect(lines.slice(0, 3)).toEqual(['', '', '']);
        expect(lines[3]).toBe(`----- ${DEFAULT_NOTE} -----`);
        expect(lines[4]).toBe(DEFAULT_PRIVACY);
        expect(lines.slice(6)).toEqual([
            'Page: https://openlibrary.org/search?q=dune',
            'Account: https://openlibrary.org/people/bob',
            'Browser: Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)',
            'Window size: 820x1030'
        ]);
    });

    test('leaves out the account when signed out', () => {
        expect(buildContactBody(strings, { ...env, account: '' })).not.toContain('Account');
    });
});

describe('pageUrl', () => {
    const origin = 'https://openlibrary.org';

    test('keeps the query string but drops the fragment', () => {
        expect(pageUrl({ origin, pathname: '/search', search: '?q=dune', hash: '#x' })).toBe('https://openlibrary.org/search?q=dune');
    });

    test('drops the query string on account pages', () => {
        expect(pageUrl({ origin, pathname: '/account/verify', search: '?t=secret' })).toBe('https://openlibrary.org/account/verify');
    });
});

describe('withBody', () => {
    test('keeps the subject and encodes the body', () => {
        const href = withBody('mailto:openlibrary@archive.org?subject=Support%20Case', 'a&b=c\r\nd');
        expect(href).toBe('mailto:openlibrary@archive.org?subject=Support%20Case&body=a%26b%3Dc%0D%0Ad');
    });

    test('replaces an existing body instead of adding a second one', () => {
        const once = withBody('mailto:x@y.org?subject=S', 'one');
        expect(withBody(once, 'two')).toBe('mailto:x@y.org?subject=S&body=two');
    });

    test('works without existing parameters', () => {
        expect(withBody('mailto:x@y.org', 'hi')).toBe('mailto:x@y.org?body=hi');
    });
});
