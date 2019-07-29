import sinon from 'sinon';
import { debounce } from '../../../openlibrary/plugins/openlibrary/js/nonjquery_utils.js';

describe('debounce', () => {
    test('func not called during initialization', () => {
        const spy = sinon.spy();
        debounce(spy, 100, false);
        expect(spy.callCount).toBe(0);
    });

    test('func called after threshold when !execAsap', () => {
        const clock = sinon.useFakeTimers();
        const spy = sinon.spy();
        const debouncedSpy = debounce(spy, 100, false);
        debouncedSpy();
        expect(spy.callCount).toBe(0);
        clock.tick(99);
        expect(spy.callCount).toBe(0);
        clock.tick(1);
        expect(spy.callCount).toBe(1);
        clock.restore();
    });

    test('func called immediately when execAsap', () => {
        const clock = sinon.useFakeTimers();
        const spy = sinon.spy();
        const debouncedSpy = debounce(spy, 100, true);
        debouncedSpy();
        expect(spy.callCount).toBe(1);
        clock.tick(100);
        expect(spy.callCount).toBe(1);
        clock.restore();
    });

    test('func called with correct context and arguments', () => {
        const spy = sinon.spy();
        const debouncedSpy = debounce(spy, 100, true);
        const context = {};
        debouncedSpy.call(context, 1, 2, 3);
        expect(spy.thisValues[0]).toBe(context);
        expect(spy.args[0]).toEqual([1, 2, 3]);
    });

    test('func only called once when spammed', () => {
        const clock = sinon.useFakeTimers();
        const spy = sinon.spy();
        const debouncedSpy = debounce(spy, 100, false);
        for (let i = 0; i < 10; i++) {
            debouncedSpy();
            expect(spy.callCount).toBe(0);
        }
        clock.tick(100);
        expect(spy.callCount).toBe(1);
        clock.restore();
    });
});
