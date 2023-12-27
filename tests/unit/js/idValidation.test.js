import {
    parseIsbn,
    parseLccn,
    isChecksumValidIsbn10,
    isChecksumValidIsbn13,
    isFormatValidIsbn10,
    isFormatValidIsbn13,
    isValidLccn
} from '../../../openlibrary/plugins/openlibrary/js/idValidation.js';

describe('parseIsbn', () => {
    it('correctly parses ISBN 10 with dashes', () => {
        expect(parseIsbn('0-553-38168-7')).toBe('0553381687');
    });
    it('correctly parses ISBN 13 with dashes', () => {
        expect(parseIsbn('978-0-553-38168-9')).toBe('9780553381689');
    });
})

// testing from examples listed here:
// https://www.loc.gov/marc/lccn-namespace.html
describe('parseLccn', () => {
    it('correctly parses LCCN example 1', () => {
        expect(parseLccn('n78-890351')).toBe('n78890351');
    });
    it('correctly parses LCCN example 2', () => {
        expect(parseLccn('n78-89035')).toBe('n78089035');
    });
    it('correctly parses LCCN example 3', () => {
        expect(parseLccn('n 78890351 ')).toBe('n78890351');
    });
    it('correctly parses LCCN example 4', () => {
        expect(parseLccn(' 85000002')).toBe('85000002');
    });
    it('correctly parses LCCN example 5', () => {
        expect(parseLccn('85-2 ')).toBe('85000002');
    });
    it('correctly parses LCCN example 6', () => {
        expect(parseLccn('2001-000002')).toBe('2001000002');
    });
    it('correctly parses LCCN example 7', () => {
        expect(parseLccn('75-425165//r75')).toBe('75425165');
    });
    it('correctly parses LCCN example 8', () => {
        expect(parseLccn(' 79139101 /AC/r932')).toBe('79139101');
    });
})

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

describe('isFormatValidIsbn10', () => {
    it('returns true with valid ISBN 10 (X check character)', () => {
        expect(isFormatValidIsbn10('080442957X')).toBe(true);
    });
    it('returns true with valid ISBN 10', () => {
        expect(isFormatValidIsbn10('1593279280')).toBe(true);
    });

    it('returns false with invalid ISBN 10', () => {
        expect(isFormatValidIsbn10('a234567890')).toBe(false);
    });
    it('returns false with blank value', () => {
        expect(isFormatValidIsbn10('')).toBe(false);
    });
})

describe('isFormatValidIsbn13', () => {
    it('returns true with valid ISBN 13', () => {
        expect(isFormatValidIsbn13('9781789801217')).toBe(true);
    });

    it('returns false with invalid ISBN 13 (too long)', () => {
        expect(isFormatValidIsbn13('97918430918002')).toBe(false);
    });
    it('returns false with invalid ISBN 13 (too short)', () => {
        expect(isFormatValidIsbn13('979843091802')).toBe(false);
    });
    it('returns false with invalis ISBN 13 (non-numeric)', () => {
        expect(isFormatValidIsbn13('979a430918002')).toBe(false);
    });
})

// testing from examples listed here:
// https://www.loc.gov/marc/lccn-namespace.html
// https://www.oclc.org/bibformats/en/0xx/010.html
describe('isValidLccn', () => {
    it('returns true for LCCN of length 8', () => {
        expect(isValidLccn('85000002')).toBe(true);
    });
    it('returns true for LCCN of length 9', () => {
        expect(isValidLccn('n78890351')).toBe(true);
    });
    it('returns true for LCCN of length 10 (all digits)', () => {
        expect(isValidLccn('2001000002')).toBe(true);
    });
    it('returns true for LCCN of length 10 (alpha prefix)', () => {
        expect(isValidLccn('sn85000678')).toBe(true);
    });
    it('returns true for LCCN of length 11 (alpha-numeric prefix)', () => {
        expect(isValidLccn('a2500000003')).toBe(true);
    });
    it('returns true for LCCN of length 11 (alpha prefix)', () => {
        expect(isValidLccn('agr25000003')).toBe(true);
    });
    it('returns true for LCCN of length 12', () => {
        expect(isValidLccn('mm2002084896')).toBe(true);
    });

    it('returns false for LCCN below minimum length', () => {
        expect(isValidLccn('8500002')).toBe(false);
    });
    it('returns false for LCCN of length 9 with all digits', () => {
        expect(isValidLccn('178890351')).toBe(false);
    });
    it('returns false for LCCN of length 10 with alpha characters', () => {
        expect(isValidLccn('a001000002')).toBe(false);
    });
    it('returns false for LCCN of length 11 with all digits', () => {
        expect(isValidLccn('12500000003')).toBe(false);
    });
    it('returns false for LCCN of length 12 with all digits', () => {
        expect(isValidLccn('125000000003')).toBe(false);
    });
    it('returns false for LCCN of length 13', () => {
        expect(isValidLccn('1250000000003')).toBe(false);
    });
})
