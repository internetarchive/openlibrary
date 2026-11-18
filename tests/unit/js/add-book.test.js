import { isValidWebBookUrl } from '../../../openlibrary/plugins/openlibrary/js/add-book.js';

describe('isValidWebBookUrl', () => {
    it('returns true for a blank value (field is optional)', () => {
        expect(isValidWebBookUrl('')).toBe(true);
    });
    it('returns true for a whitespace-only value', () => {
        expect(isValidWebBookUrl('   ')).toBe(true);
    });
    it('returns true for a valid http URL', () => {
        expect(isValidWebBookUrl('http://example.com/book.epub')).toBe(true);
    });
    it('returns true for a valid https URL', () => {
        expect(isValidWebBookUrl('https://example.com/book.epub')).toBe(true);
    });

    it('returns false for an unparseable string', () => {
        expect(isValidWebBookUrl('not-a-url')).toBe(false);
    });
    it('returns false for a javascript: scheme URL', () => {
        expect(isValidWebBookUrl('javascript:alert(1)')).toBe(false);
    });
    it('returns false for a mailto: scheme URL', () => {
        expect(isValidWebBookUrl('mailto:a@b.com')).toBe(false);
    });
});
