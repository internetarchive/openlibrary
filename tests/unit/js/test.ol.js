import jquery from 'jquery';
import sinon from 'sinon';
import { initReadingListFeature } from '../../../openlibrary/plugins/openlibrary/js/ol';

let sandbox;

beforeEach(() => {
    sandbox = sinon.createSandbox();
    global.$ = jquery;
    sandbox.stub(global, '$').callsFake(jquery);
});

describe('initReadingList', () => {
    test('dropdown changes arrow direction on click', () => {
        const clock = sinon.useFakeTimers();
        initReadingListFeature();
        $(document.body).html(`
            <a href="javascript:;" class="dropclick dropclick-unactivated">
                <div class="arrow arrow-unactivated"></div>
            </a>
        `);

        const $dropclick = $('.dropclick');
        const $arrow = $dropclick.find('.arrow');

        for (let i = 0; i < 2; i++) {
            $dropclick.trigger('click');
            clock.next(); // need to step forward because using debounce
            expect($arrow.hasClass('up')).toBe(true);
            $dropclick.trigger('click');
            clock.next();
            expect($arrow.hasClass('up')).toBe(false);
        }
        clock.restore();
    });
});
