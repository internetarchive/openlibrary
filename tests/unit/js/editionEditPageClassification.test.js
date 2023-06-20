import { initClassificationValidation } from '../../../openlibrary/plugins/openlibrary/js/edit.js';
import sinon from 'sinon';
import * as testData from './html-test-data';
import { htmlquote } from '../../../openlibrary/plugins/openlibrary/js/jsdef';
import jQueryRepeat from '../../../openlibrary/plugins/openlibrary/js/jquery.repeat';

let sandbox;

beforeEach(() => {
    // Clear session storage
    sandbox = sinon.createSandbox();
    global.htmlquote = htmlquote;
    // htmlquote is used inside an eval expression (yuck) so is an implied dependency
    sandbox.stub(global, 'htmlquote').callsFake(htmlquote);
    // setup Query repeat
    jQueryRepeat(global.$);
    // setup the HTML
    $(document.body).html(testData.readClassification);
    initClassificationValidation();
});


describe('initClassificationValidation', ()=>{

    it('Validates that Select and Value are empty', ()=>{
        $('#select-classification').val('');
        $('#classification-value').val('');
        $('.repeat-add').trigger('click');
        const displayError = $('#classification-errors').css('display');
        expect(displayError).toBe('block');

    });
    it('Validates that the select is empty and the value has some value', ()=>{
        $('#select-classification').val('');
        $('#classification-value').val('Test');
        $('.repeat-add').trigger('click');
        const displayError = $('#classification-errors').css('display');
        expect(displayError).toBe('block');
    });
    it('Validates that Select is selected and Value is empty', ()=>{
        $('#select-classification').val('lc_classifications');
        $('#classification-value').val('');
        $('.repeat-add').trigger('click');
        const displayError = $('#classification-errors').css('display');
        expect(displayError).toBe('block');
    });
    it('Validates that Select is selected and Value has any value', ()=>{
        $('#select-classification').val('lc_classifications');
        $('#classification-value').val('Test');
        $('.repeat-add').trigger('click');
        const displayError = $('#classification-errors').css('display');
        expect(displayError).toBe('none');
    });
    it('Validates that select is with "---" and value is empty', ()=>{
        $('#select-classification').val('---');
        $('#classification-value').val('');
        $('.repeat-add').trigger('click');
        const displayError = $('#classification-errors').css('display');
        expect(displayError).toBe('block');
    });
    it('Validates that the select is with "---" and the value is with some value', ()=>{
        $('#select-classification').val('---');
        $('#classification-value').val('Test');
        $('.repeat-add').trigger('click');
        const displayError = $('#classification-errors').css('display');
        expect(displayError).toBe('block');
    });
});
