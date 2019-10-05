import jquery from 'jquery';
import sinon from 'sinon';
import { initReadingListFeature } from '../../../openlibrary/plugins/openlibrary/js/ol';
import { bookDropdownSample } from './html-test-data'
import * as nonjquery_utils from '../../../openlibrary/plugins/openlibrary/js/nonjquery_utils.js';
let sandbox;

beforeEach(() => {
    sandbox = sinon.createSandbox();
    global.$ = jquery;
    sandbox.stub(global, '$').callsFake(jquery);
});

describe('initReadingList', () => {
    test.only('dropdown changes arrow direction on click', () => {
        // Stub debounce to avoid have to manipulate time (!)
        const stub = sinon.stub(nonjquery_utils, 'debounce').callsFake(fn => fn);

        initReadingListFeature();
        $(document.body).html(bookDropdownSample);
        const $dropclick = $('.dropclick');
        const $arrow = $dropclick.find('.arrow');

        for (let i = 0; i < 2; i++) {
            $dropclick.trigger('click');
            expect($arrow.hasClass('up')).toBe(true);

            $dropclick.trigger('click');
            expect($arrow.hasClass('up')).toBe(false);
        }

        stub.restore();
    });
});
