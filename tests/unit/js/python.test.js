import { commify } from '../../../openlibrary/plugins/openlibrary/js/python';

test('commify', () => {
    expect(commify('5443232')).toBe('5,443,232');
    expect(commify('50')).toBe('50');
    expect(commify('5000')).toBe('5,000');
    expect(commify(['1','2','3','45'])).toBe('1,2,3,45');
    expect(commify([1, 20, 3])).toBe('1,20,3');
});
