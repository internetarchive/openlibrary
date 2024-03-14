import { removeURLParameter, getJsonFromUrl } from '../../../openlibrary/plugins/openlibrary/js/Browser';

describe('removeURLParameter', () => {
    const fn = removeURLParameter;

    test('URL with no parameters', () => {
        expect(fn('http://foo.com', 'x')).toBe('http://foo.com');
    });

    test('URL with the given parameter', () => {
        expect(fn('http://foo.com?x=3', 'x')).toBe('http://foo.com');
        expect(fn('http://foo.com?x=3&y=4&z=5', 'x')).toBe('http://foo.com?y=4&z=5');
        expect(fn('http://foo.com?x=3&y=4&z=5', 'y')).toBe('http://foo.com?x=3&z=5');
        expect(fn('http://foo.com?x=3&y=4&z=5', 'z')).toBe('http://foo.com?x=3&y=4');
    });

    test('URL without the given parameter', () => {
        expect(fn('http://foo.com?x=3', 'y')).toBe('http://foo.com?x=3');
        expect(fn('http://foo.com?x=3&y=4&z=5', 'w')).toBe('http://foo.com?x=3&y=4&z=5');
    });

    test('URL with multiple occurences of param', () => {
        expect(fn('http://foo.com?x=3&x=4&x=5', 'x')).toBe('http://foo.com');
        expect(fn('http://foo.com?x=3&x=4&z=5', 'x')).toBe('http://foo.com?z=5');
    })
});

describe('getJsonFromUrl', () => {
    const fn = getJsonFromUrl;

    test('Handles empty strings', () => {
        expect(fn('')).toEqual({});
        expect(fn('?')).toEqual({});
    });

    test('Handles normal params', () => {
        expect(fn('?hello=world')).toEqual({hello: 'world'});
        expect(fn('?x=3&y=4&z=5')).toEqual({x: '3', y: '4', z: '5'});
    });

    test('Decodes parameter values', () => {
        expect(fn('?q=foo%20bar')).toEqual({q: 'foo bar'});
    });

    test('Parameters override each other', () => {
        expect(fn('?x=1&x=2&x=3')).toEqual({x: '3'});
    });
});
