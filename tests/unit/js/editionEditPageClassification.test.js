import $ from 'jquery';
import { initClassificationValidation } from '../../../openlibrary/plugins/openlibrary/js/edit.js';
import * as testData from './html-test-data';
import { htmlquote } from '../../../openlibrary/plugins/openlibrary/js/jsdef';
import { init } from '../../../openlibrary/plugins/openlibrary/js/jquery.repeat';

beforeEach(() => {
    // Clear session storage
    // htmlquote is used inside an eval expression (yuck) so is an implied dependency
    global.htmlquote = htmlquote;
    // setup Query repeat
    init();
    // setup the HTML
    $(document.body).html(testData.readClassification);
    initClassificationValidation();
});

describe('initClassificationValidation', () => {
    test.each([
    // format: [testName, selectValue, classificationValue, expectedDisplay]
        ['Can have a classification and any value', 'lc_classifications', 'anything at all', 'none'],
        ['Cannot have both an empty classification and classification value', '', '', 'block'],
        ['Cannot have an empty classification', '', 'Test', 'block'],
        ['Cannot have an empty classification value', 'lc_classifications', '', 'block'],
        ['Cannot have --- as a classification WITHOUT a value', '---', 'test', 'block'],
        ['Cannot have --- as a classification with a value', '---', '', 'block'],
    ])('Test: %s', (testName, selectValue, classificationValue, expectedDisplay) => {
        $('#select-classification').val(selectValue);
        $('#classification-value').val(classificationValue);
        $('.repeat-add').trigger('click');
        const displayError = $('#classification-errors').css('display');
        expect(displayError).toBe(expectedDisplay);
    });
});
