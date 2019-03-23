import { foreach, range, join, len, htmlquote, enumerate,
    websafe } from '../../../openlibrary/plugins/openlibrary/js/jsdef';

test('jsdef: python range function', () => {
    expect(range(2, 5)).toEqual([2, 3, 4]);
    expect(range(5)).toEqual([0, 1, 2, 3, 4]);
    expect(range(0, 10, 2)).toEqual([0, 2, 4, 6, 8]);
});

test('jsdef: enumerate', () => {
    expect(enumerate([1, 2, 3])).toEqual([
        ['0', 1],
        ['1', 2],
        ['2', 3]
    ]);
});

test('jsdef: foreach', () => {
    let called = 0;
    const loop = [];
    const listToLoop = [1, 2, 3];
    expect.assertions(1);
    return new Promise((resolve) => {
        foreach(listToLoop, loop, function () {
            called += 1;
            if (called === 3) {
                expect(called).toBe(3);
                resolve();
            }
        })
    });
});

test('jsdef: join', () => {
    const str = '-';
    const joinFn = join.bind(str);
    expect(joinFn(['1', '2'])).toBe('1-2');
});

test('jsdef: len', () => {
    expect(len(['1', '2'])).toBe(2);
});

test('jsdef: htmlquote', () => {
    expect(htmlquote(5)).toBe('5');
    expect(htmlquote('<foo>')).toBe('&lt;foo&gt;');
    expect(htmlquote('\'foo\': "bar"')).toBe('&#39;foo&#39;: &quot;bar&quot;');
    expect(htmlquote('a&b')).toBe('a&amp;b');
});

test('jsdef: websafe', () => {
    expect(websafe('<script>')).toBe('&lt;script&gt;');
    // not sure if these are really necessary, but they document the current behaviour
    expect(websafe(undefined)).toBe('');
    expect(websafe(null)).toBe('');
    expect(websafe({toString: undefined})).toBe('');
});
