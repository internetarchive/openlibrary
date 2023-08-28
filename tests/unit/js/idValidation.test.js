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
    })
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
    
})

describe('isFormatValidIsbn13', () => {
    
})

describe('isValidLccn', () => {
    
})
