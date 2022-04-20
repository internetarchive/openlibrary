import jquery from 'jquery';
import sinon from 'sinon';
import * as testData from './html-test-data';
import { htmlquote } from '../../../openlibrary/plugins/openlibrary/js/jsdef';
import jQueryRepeat from '../../../openlibrary/plugins/openlibrary/js/jquery.repeat';

let sandbox;

beforeEach(() => {
    sandbox = sinon.createSandbox();
    global.$ = jquery;
    global.htmlquote = htmlquote;
    // htmlquote is used inside an eval expression (yuck) so is an implied dependency
    sandbox.stub(global, 'htmlquote').callsFake(htmlquote);
    sandbox.stub(global, '$').callsFake(jquery);
});

test('identifiers of repeated elements are never the same.', () => {
    // setup Query repeat
    jQueryRepeat(global.$);
    // setup the HTML
    $(document.body).html(testData.editionIdentifiersSample);
    // turn on jQuery repeat
    $('#identifiers').repeat({
        vars: {
            prefix: 'edition--'
        },
        validate: () => {}
    });

    expect($('.repeat-item').length).toBe(5);
    $('#select-id').val('google');
    $('#id-value').text('fo4rzdaHDAwC');
    $('.repeat-add').trigger('click');
    expect($('.repeat-item').length).toBe(6);
    $('#identifiers--3 .repeat-remove').trigger('click')
    expect($('.repeat-item').length).toBe(5);
    $('#select-id').val('goodreads');
    $('#id-value').text('44415839');
    $('.repeat-add').trigger('click');
    expect($('.repeat-item').length).toBe(6);
    const ids = $('[id]').map((_, node) => node.getAttribute('id')).toArray();
    expect(ids.length).toBe(new Set(ids).size);
});
