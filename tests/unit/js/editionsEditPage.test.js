import { isChecksumValidIsbn10, isChecksumValidIsbn13 } from '../../../openlibrary/plugins/openlibrary/js/edit.js';
import { validateIdentifiers } from '../../../openlibrary/plugins/openlibrary/js/edit.js';
import sinon from 'sinon';
import * as testData from './html-test-data';
import { htmlquote } from '../../../openlibrary/plugins/openlibrary/js/jsdef';
import jQueryRepeat from '../../../openlibrary/plugins/openlibrary/js/jquery.repeat';

let sandbox;

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

/**
 * Test various patterns with the editions identifier parsing function,
 * validateIdentifiers(), that initIdentifierValidation() calls when
 * attempting to add and validate a new ISBN to an edition.
 * These tests are meant to make sure that when adding ISBN 10 and ISBN 13:
 * - valid numbers are accepted;
 * - duplicate numbers are not;
 * - formally valid numbers (correct number of digits) but with a failed
 *   check digit calculation can be added with a user override.
 * - numbers can be entered with spaces and hyphens;
 * - any numbers or hyphens are stripped before passing to the back end; and
 * - stripped and unstripped numbers are treated equally as identical.
 */

// Adapted from jquery.repeat.test.js

beforeEach(() => {
    // Clear session storage
    sandbox = sinon.createSandbox();
    global.htmlquote = htmlquote;
    // htmlquote is used inside an eval expression (yuck) so is an implied dependency
    sandbox.stub(global, 'htmlquote').callsFake(htmlquote);
    // setup Query repeat
    jQueryRepeat(global.$);
    // setup the HTML
    $(document.body).html(testData.editionIdentifiersSample);
    $('#identifiers').repeat({
        vars: {prefix: 'edition--'},
        validate: function(data) {return validateIdentifiers(data)},
    });
});

// Per the test data used, and beforeEach(), the length always starts out at 5.
describe('initIdentifierValidation', () => {
    // ISBN 10
    it('does add a valid ISBN 10 ending in X', () => {
        $('#select-id').val('isbn_10');
        $('#id-value').val('0-8044-2957-X');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(6);
    });

    it('does add a valid ISBN 10 NOT ending in X', () => {
        $('#select-id').val('isbn_10');
        $('#id-value').val('0596520689');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(6);
    });

    it('does NOT add an invalid ISBN 10 with a failed check digit', () => {
        $('#select-id').val('isbn_10');
        $('#id-value').val('1234567890');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(5);
    });

    it('does NOT prompt to add a formally invalid ISBN 10', () => {
        $('#select-id').val('isbn_10');
        $('#id-value').val('12345');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(5);
        expect($('.repeat-add').length).toBe(1);
        const errorDivText = $('#id-errors').text();
        const expected = 'Add it anyway?';
        expect(errorDivText).toEqual(expect.not.stringContaining(expected));
    });

    it('clears the invalid ISBN 10 error prompt and does not add an ISBN if a user clicks no', () => {
        $('#select-id').val('isbn_10');
        $('#id-value').val('2121212121');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(5);
        expect($('.repeat-add').length).toBe(2);
        $('#do-not-add-isbn').trigger('click');
        expect($('.repeat-item').length).toBe(5);
        const cssDisplay = $('#id-errors').css('display');
        expect(cssDisplay).toEqual('none')
    });

    it('does NOT add a duplicate ISBN 10', () => {
        $('#select-id').val('isbn_10');
        $('#id-value').val('0063162024');
        $('.repeat-add').trigger('click');
        $('#select-id').val('isbn_10');
        $('#id-value').val('0063162024');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(6);
    });

    it('does properly strip spaces and hypens from a valid ISBN 10 and add it', () => {
        $('#select-id').val('isbn_10');
        $('#id-value').val('09- 8478---2869  ');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(6);
    })

    it('does count identical stripped and unstripped ISBN 10s as the same ISBN', () => {
        $('#select-id').val('isbn_10');
        $('#id-value').val(' 144--93-55730 ');
        $('.repeat-add').trigger('click');
        $('#select-id').val('isbn_10');
        $('#id-value').val('1449355730');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(6);
    });

    // ISBN 13
    it('does add a valid ISBN 13', () => {
        $('#select-id').val('isbn_13');
        $('#id-value').val('9781789801217');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(6);
    });

    it('does NOT add an invalid ISBN 13', () => {
        $('#select-id').val('isbn_13');
        $('#id-value').val('1111111111111');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(5);
    });

    it('does NOT prompt to add a formally invalid ISBN 13', () => {
        $('#select-id').val('isbn_13');
        $('#id-value').val('12345');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(5);
        expect($('.repeat-add').length).toBe(1);
        const errorDivText = $('#id-errors').text();
        const expected = 'Add it anyway?';
        expect(errorDivText).toEqual(expect.not.stringContaining(expected));
    });

    it('clears the invalid ISBN 13 error prompt and does not add an ISBN if a user clicks no', () => {
        $('#select-id').val('isbn_13');
        $('#id-value').val('0123456789123');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(5);
        expect($('.repeat-add').length).toBe(2);
        $('#do-not-add-isbn').trigger('click');
        expect($('.repeat-item').length).toBe(5);
        const cssDisplay = $('#id-errors').css('display');
        expect(cssDisplay).toEqual('none')
    });

    it('does NOT add a duplicate ISBN 13', () => {
        $('#select-id').val('isbn_13');
        $('#id-value').val('9780984782857');
        $('.repeat-add').trigger('click');
        $('#select-id').val('isbn_13');
        $('#id-value').val('9780984782857');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(6);
    });

    it('does properly strip spaces and hypens from a valid ISBN 13 and add it', () => {
        $('#select-id').val('isbn_13');
        $('#id-value').val('978-16172--95 980  ');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(6);
    })

    it('does count identical stripped and unstripped ISBN 13s as the same ISBN', () => {
        $('#select-id').val('isbn_13');
        $('#id-value').val('-979-86 -64653403   ');
        $('.repeat-add').trigger('click');
        $('#select-id').val('isbn_13');
        $('#id-value').val('9798664653403');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(6);
    });
});
