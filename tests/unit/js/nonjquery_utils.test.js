import { debounce } from '../../../openlibrary/plugins/openlibrary/js/nonjquery_utils.js';

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
