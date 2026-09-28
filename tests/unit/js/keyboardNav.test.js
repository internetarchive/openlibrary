import { getNextKeyboardFocusIndex } from '../../../openlibrary/components/lit/utils/keyboard-nav.js';

describe('getNextKeyboardFocusIndex', () => {
    const opts = (over = {}) => ({ count: 4, current: 1, ...over });

    test('ArrowRight / ArrowDown move forward (orientation both)', () => {
        expect(getNextKeyboardFocusIndex('ArrowRight', opts())).toBe(2);
        expect(getNextKeyboardFocusIndex('ArrowDown', opts())).toBe(2);
    });

    test('ArrowLeft / ArrowUp move backward (orientation both)', () => {
        expect(getNextKeyboardFocusIndex('ArrowLeft', opts())).toBe(0);
        expect(getNextKeyboardFocusIndex('ArrowUp', opts())).toBe(0);
    });

    test('Home / End jump to the ends', () => {
        expect(getNextKeyboardFocusIndex('Home', opts())).toBe(0);
        expect(getNextKeyboardFocusIndex('End', opts())).toBe(3);
    });

    test('returns -1 for non-navigation keys', () => {
        expect(getNextKeyboardFocusIndex('Enter', opts())).toBe(-1);
        expect(getNextKeyboardFocusIndex('a', opts())).toBe(-1);
        expect(getNextKeyboardFocusIndex(' ', opts())).toBe(-1);
    });

    describe('wrap', () => {
        test('wraps past the ends when wrap=true (default)', () => {
            expect(getNextKeyboardFocusIndex('ArrowRight', opts({ current: 3 }))).toBe(0);
            expect(getNextKeyboardFocusIndex('ArrowLeft', opts({ current: 0 }))).toBe(3);
        });

        test('stops at the ends when wrap=false', () => {
            expect(getNextKeyboardFocusIndex('ArrowRight', opts({ current: 3, wrap: false }))).toBe(-1);
            expect(getNextKeyboardFocusIndex('ArrowLeft', opts({ current: 0, wrap: false }))).toBe(-1);
        });
    });

    describe('orientation', () => {
        test('horizontal ignores ArrowUp/ArrowDown', () => {
            expect(getNextKeyboardFocusIndex('ArrowDown', opts({ orientation: 'horizontal' }))).toBe(-1);
            expect(getNextKeyboardFocusIndex('ArrowUp', opts({ orientation: 'horizontal' }))).toBe(-1);
            expect(getNextKeyboardFocusIndex('ArrowRight', opts({ orientation: 'horizontal' }))).toBe(2);
        });

        test('vertical ignores ArrowLeft/ArrowRight', () => {
            expect(getNextKeyboardFocusIndex('ArrowRight', opts({ orientation: 'vertical' }))).toBe(-1);
            expect(getNextKeyboardFocusIndex('ArrowDown', opts({ orientation: 'vertical' }))).toBe(2);
        });
    });

    describe('disabled items', () => {
        const isDisabled = (i) => i === 2; // index 2 is disabled

        test('skips a disabled item when stepping forward', () => {
            expect(getNextKeyboardFocusIndex('ArrowRight', opts({ current: 1, isDisabled }))).toBe(3);
        });

        test('skips a disabled item when stepping backward', () => {
            expect(getNextKeyboardFocusIndex('ArrowLeft', opts({ current: 3, isDisabled }))).toBe(1);
        });

        test('Home / End land on the first/last ENABLED item', () => {
            const allButEnds = (i) => i === 0 || i === 3; // ends disabled
            expect(getNextKeyboardFocusIndex('Home', opts({ isDisabled: allButEnds }))).toBe(1);
            expect(getNextKeyboardFocusIndex('End', opts({ isDisabled: allButEnds }))).toBe(2);
        });

        test('returns -1 when every item is disabled', () => {
            expect(getNextKeyboardFocusIndex('ArrowRight', opts({ isDisabled: () => true }))).toBe(-1);
            expect(getNextKeyboardFocusIndex('Home', opts({ isDisabled: () => true }))).toBe(-1);
        });
    });

    test('handles current = -1 (nothing focused) by stepping from the edge', () => {
        expect(getNextKeyboardFocusIndex('ArrowRight', opts({ current: -1 }))).toBe(0);
        expect(getNextKeyboardFocusIndex('Home', opts({ current: -1 }))).toBe(0);
    });

    test('returns -1 for an empty set', () => {
        expect(getNextKeyboardFocusIndex('ArrowRight', { count: 0, current: -1 })).toBe(-1);
    });
});
