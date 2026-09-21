import { debounce, maxBy, uniqBy } from '../../../openlibrary/plugins/openlibrary/js/nonjquery_utils.js';

describe('debounce', () => {
    afterEach(() => {
        vi.useRealTimers();
    });

    test('func not called during initialization', () => {
        const spy = vi.fn();
        debounce(spy, 100, false);
        expect(spy).not.toHaveBeenCalled();
    });

    test('func called after threshold when !execAsap', () => {
        vi.useFakeTimers();
        const spy = vi.fn();
        const debouncedSpy = debounce(spy, 100, false);
        debouncedSpy();
        expect(spy).not.toHaveBeenCalled();
        vi.advanceTimersByTime(99);
        expect(spy).not.toHaveBeenCalled();
        vi.advanceTimersByTime(1);
        expect(spy).toHaveBeenCalledTimes(1);
    });

    test('func called immediately when execAsap', () => {
        vi.useFakeTimers();
        const spy = vi.fn();
        const debouncedSpy = debounce(spy, 100, true);
        debouncedSpy();
        expect(spy).toHaveBeenCalledTimes(1);
        vi.advanceTimersByTime(100);
        expect(spy).toHaveBeenCalledTimes(1);
    });

    test('func called with correct context and arguments', () => {
        const spy = vi.fn();
        const debouncedSpy = debounce(spy, 100, true);
        const context = {};
        debouncedSpy.call(context, 1, 2, 3);
        expect(spy.mock.contexts[0]).toBe(context);
        expect(spy).toHaveBeenCalledWith(1, 2, 3);
    });

    test('func only called once when spammed', () => {
        vi.useFakeTimers();
        const spy = vi.fn();
        const debouncedSpy = debounce(spy, 100, false);
        for (let i = 0; i < 10; i++) {
            debouncedSpy();
            expect(spy).not.toHaveBeenCalled();
        }
        vi.advanceTimersByTime(100);
        expect(spy).toHaveBeenCalledTimes(1);
    });
});

describe('uniqBy', () => {
    test('keeps the first item for each key', () => {
        const items = [{ id: 1, n: 'a' }, { id: 2, n: 'b' }, { id: 1, n: 'c' }];
        expect(uniqBy(items, x => x.id)).toEqual([{ id: 1, n: 'a' }, { id: 2, n: 'b' }]);
    });

    test('treats undefined as a key', () => {
        expect(uniqBy([undefined, { value: 'x' }, undefined], x => x?.value)).toEqual([undefined, { value: 'x' }]);
    });
});

describe('maxBy', () => {
    test('returns the first item with the largest key', () => {
        expect(maxBy(['aa', 'b', 'cc'], s => s.length)).toBe('aa');
    });

    test('returns undefined for an empty array', () => {
        expect(maxBy([], x => x)).toBeUndefined();
    });

    test('skips null, undefined and NaN keys', () => {
        expect(maxBy([undefined, 2], x => x)).toBe(2);
        expect(maxBy([NaN, 2, null], x => x)).toBe(2);
        expect(maxBy([NaN, undefined], x => x)).toBeUndefined();
    });
});
