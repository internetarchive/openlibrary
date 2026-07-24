import { getNextIndex } from '../../../openlibrary/components/lit/utils/keyboard-nav.js';

describe('getNextIndex', () => {
    const opts = (over = {}) => ({ count: 4, current: 1, ...over });

    test('ArrowRight / ArrowDown move forward (orientation both)', () => {
        expect(getNextIndex('ArrowRight', opts())).toBe(2);
        expect(getNextIndex('ArrowDown', opts())).toBe(2);
    });

    test('ArrowLeft / ArrowUp move backward (orientation both)', () => {
        expect(getNextIndex('ArrowLeft', opts())).toBe(0);
        expect(getNextIndex('ArrowUp', opts())).toBe(0);
    });

    test('Home / End jump to the ends', () => {
        expect(getNextIndex('Home', opts())).toBe(0);
        expect(getNextIndex('End', opts())).toBe(3);
    });

    test('returns -1 for non-navigation keys', () => {
        expect(getNextIndex('Enter', opts())).toBe(-1);
        expect(getNextIndex('a', opts())).toBe(-1);
        expect(getNextIndex(' ', opts())).toBe(-1);
    });

    describe('wrap', () => {
        test('wraps past the ends when wrap=true (default)', () => {
            expect(getNextIndex('ArrowRight', opts({ current: 3 }))).toBe(0);
            expect(getNextIndex('ArrowLeft', opts({ current: 0 }))).toBe(3);
        });

        test('stops at the ends when wrap=false', () => {
            expect(getNextIndex('ArrowRight', opts({ current: 3, wrap: false }))).toBe(-1);
            expect(getNextIndex('ArrowLeft', opts({ current: 0, wrap: false }))).toBe(-1);
        });
    });

    describe('orientation', () => {
        test('horizontal ignores ArrowUp/ArrowDown', () => {
            expect(getNextIndex('ArrowDown', opts({ orientation: 'horizontal' }))).toBe(-1);
            expect(getNextIndex('ArrowUp', opts({ orientation: 'horizontal' }))).toBe(-1);
            expect(getNextIndex('ArrowRight', opts({ orientation: 'horizontal' }))).toBe(2);
        });

        test('vertical ignores ArrowLeft/ArrowRight', () => {
            expect(getNextIndex('ArrowRight', opts({ orientation: 'vertical' }))).toBe(-1);
            expect(getNextIndex('ArrowDown', opts({ orientation: 'vertical' }))).toBe(2);
        });
    });

    describe('disabled items', () => {
        const isDisabled = (i) => i === 2; // index 2 is disabled

        test('skips a disabled item when stepping forward', () => {
            expect(getNextIndex('ArrowRight', opts({ current: 1, isDisabled }))).toBe(3);
        });

        test('skips a disabled item when stepping backward', () => {
            expect(getNextIndex('ArrowLeft', opts({ current: 3, isDisabled }))).toBe(1);
        });

        test('Home / End land on the first/last ENABLED item', () => {
            const allButEnds = (i) => i === 0 || i === 3; // ends disabled
            expect(getNextIndex('Home', opts({ isDisabled: allButEnds }))).toBe(1);
            expect(getNextIndex('End', opts({ isDisabled: allButEnds }))).toBe(2);
        });

        test('returns -1 when every item is disabled', () => {
            expect(getNextIndex('ArrowRight', opts({ isDisabled: () => true }))).toBe(-1);
            expect(getNextIndex('Home', opts({ isDisabled: () => true }))).toBe(-1);
        });
    });

    test('handles current = -1 (nothing focused) by stepping from the edge', () => {
        expect(getNextIndex('ArrowRight', opts({ current: -1 }))).toBe(0);
        expect(getNextIndex('Home', opts({ current: -1 }))).toBe(0);
    });

    test('returns -1 for an empty set', () => {
        expect(getNextIndex('ArrowRight', { count: 0, current: -1 })).toBe(-1);
    });
});
