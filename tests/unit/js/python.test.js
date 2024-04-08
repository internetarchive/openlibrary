import { commify, urlencode, slice } from '../../../openlibrary/plugins/openlibrary/js/python';

test('commify', () => {
    expect(commify('5443232')).toBe('5,443,232');
    expect(commify('50')).toBe('50');
    expect(commify('5000')).toBe('5,000');
    expect(commify(['1','2','3','45'])).toBe('1,2,3,45');
    expect(commify([1, 20, 3])).toBe('1,20,3');
});

describe('urlencode', () => {
    test('empty array', () => {
        expect(urlencode([])).toEqual('');
    });
    test('array of 1', () => {
        expect(urlencode(['apple'])).toEqual('0=apple');
    });
    test('array of 3', () => {
        expect(urlencode(['apple', 'grapes', 'orange'])).toEqual('0=apple&1=grapes&2=orange');
    });
});

describe('slice', () => {
    test('empty array', () => {
        expect(slice([], 0, 0)).toEqual([]);
    });
    test('array of 2', () => {
        expect(slice([1, 2], 0, 1)).toEqual([1]);
    });
    test('arr length less than end', () => {
        expect(slice([1, 2, 3], 0, 5)).toEqual([1, 2, 3]);
    });
    test('beginning greater than end', () => {
        expect(slice([1, 2, 3, 4, 5], 4, 3)).toEqual([]);
    });
    test('array of 5', () => {
        expect(slice([1, 2, 3, 4, 5], 0, 3)).toEqual([1, 2, 3]);
    });
});
