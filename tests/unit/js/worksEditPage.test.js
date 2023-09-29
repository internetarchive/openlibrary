import { initWorkIdentifierValidation } from '../../../openlibrary/plugins/openlibrary/js/edit.js';
import sinon from 'sinon';
import * as testData from './html-test-data';
import { htmlquote } from '../../../openlibrary/plugins/openlibrary/js/jsdef';
import jQueryRepeat from '../../../openlibrary/plugins/openlibrary/js/jquery.repeat';

let sandbox;

/**
 *
 * Test various patterns with the work identifier parsing function,
 * validateIdentifiers(), that initIdentifierValidation() calls when
 * attempting to add and validate a new id e.g. wikidata to an work.
 * These tests are meant to make sure that when adding ids:
 * - valid identifiers are accepted;
 * - duplicate identifiers are not;
 * - any spaces are stripped before passing to the back end;
 * - stripped and unstripped identifiers are treated equally as identical;
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
    $(document.body).html(testData.workIdentifiersSample);
    initWorkIdentifierValidation()
});

// Per the test data used, and beforeEach(), the length always starts out at 5.
describe('initWorkIdentifierValidation', () => {
    // ISBN 10
    it('does add a valid Wikidata ID starting in Q', () => {
        $('#workid-value').val('Q24').trigger('input');
        expect($('#workselect-id').val()).toBe('wikidata');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(2);
        expect($('#workselect-id').trigger('change').val()).toBe('');
    });

    it('does add a valid Wikidata url', () => {
        $('#workid-value').val('https://www.wikidata.org/wiki/Q46248').trigger('input');
        expect($('#workselect-id').val()).toBe('wikidata');
        expect($('#workid-value').val()).toBe('Q46248');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(2);
        expect($('#workselect-id').trigger('change').val()).toBe('');
    });

    it('does add a valid viaf ', () => {
        $('#workselect-id').val('viaf');
        $('#workid-value').val('0596520689');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(2);
        expect($('#workselect-id').trigger('change').val()).toBe('');
    });

    it('does NOT add a duplicate wikidata ID', () => {
        $('#workid-value').val('Q42').trigger('input');
        expect($('#workselect-id').val()).toBe('wikidata');
        $('.repeat-add').trigger('click');
        $('#workid-value').val('Q42').trigger('input');
        expect($('#workselect-id').val()).toBe('wikidata');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(2);
    });

    it('does properly trim spaces from a valid wikidata ID', () => {
        $('#workid-value').val('   Q1711833   ').trigger('input');
        expect($('#workselect-id').val()).toBe('wikidata');
        expect($('#workid-value').val()).toBe('Q1711833');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(2);
        expect($('#workselect-id').trigger('change').val()).toBe('');
    })

    it('does count identical trimmed and untrimmed wikidata and urls as the same', () => {
        $('#workid-value').val('   Q1711833   ').trigger('input');
        expect($('#workselect-id').val()).toBe('wikidata');
        expect($('#workid-value').val()).toBe('Q1711833');
        $('.repeat-add').trigger('click');
        expect($('#workid-value').val()).toBe('');
        expect($('.repeat-item').length).toBe(2);
        expect($('#workselect-id').trigger('change').val()).toBe('');

        $('#workid-value').val('Q1711833').trigger('input');
        expect($('#workselect-id').trigger('change').val()).toBe('wikidata');
        expect($('#workid-value').val()).toBe('Q1711833');
        $('.repeat-add').trigger('click');
        expect($('#workid-value').val()).toBe('');
        expect($('.repeat-item').length).toBe(2);
        expect($('#workselect-id').trigger('change').val()).toBe('wikidata');

        $('#workid-value').val('https://www.wikidata.org/wiki/Q1711833').trigger('input');
        expect($('#workselect-id').val()).toBe('wikidata');
        expect($('#workid-value').val()).toBe('Q1711833');
        $('.repeat-add').trigger('click');
        expect($('.repeat-item').length).toBe(2);
        expect($('#workselect-id').trigger('change').val()).toBe('wikidata');
    });

});
