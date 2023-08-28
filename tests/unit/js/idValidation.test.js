import {
    parseIsbn,
    parseLccn,
    isChecksumValidIsbn10,
    isChecksumValidIsbn13,
    isFormatValidIsbn10,
    isFormatValidIsbn13,
    isValidLccn
} from '../../../openlibrary/plugins/openlibrary/js/idValidation.js';

//TODO: Add tests for the rest of the functions in idValidation.js

describe('isChecksumValidIsbn10', () => {
    it('returns true with valid ISBN 10 (X check character)', () => {
        expect(isChecksumValidIsbn10('080442957X')).toBe(true);
    });
    it('returns true with valid ISBN 10 (numerical check character, check 1)', () => {
        expect(isChecksumValidIsbn10('1593279280')).toBe(true);
    });
    it('returns true with valid ISBN 10 (numerical check character, check 2)', () => {
        expect(isChecksumValidIsbn10('1617295981')).toBe(true);
    });
    it('returns false with an invalid ISBN 10', () => {
        expect(isChecksumValidIsbn10('1234567890')).toBe(false);
    });
})

describe('isChecksumValidIsbn13', () => {
    it('returns true with valid ISBN 13 (check 1)', () => {
        expect(isChecksumValidIsbn13('9781789801217')).toBe(true);
    });
    it('returns true with valid ISBN 13 (check 2)', () => {
        expect(isChecksumValidIsbn13('9798430918002')).toBe(true);
    });
    it('returns false with an invalid ISBN 13 (check 1)', () => {
        expect(isChecksumValidIsbn13('1234567890123')).toBe(false);
    });
    it('returns false with an invalid ISBN 13 (check 2)', () => {
        expect(isChecksumValidIsbn13('9790000000000')).toBe(false);
    });
})
