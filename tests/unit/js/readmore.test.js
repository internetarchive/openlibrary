import { initClampers, ReadMoreComponent } from '../../../openlibrary/plugins/openlibrary/js/readmore';
import {clamperSample} from './html-test-data'

describe('ReadMoreComponent', () => {
    /** @type {ReadMoreComponent} */
    let readMore;

    beforeEach(() => {
        readMore = new ReadMoreComponent(
            $(`
                <div class="read-more">
                    <div class="read-more__content" style="max-height:40px">
                    </div>
                </div>
            `)
                .appendTo(document.body)[0]
        );
    });

    afterEach(() => {
        readMore.$container.remove();
    });

    test('collapsed if big scroll height', () => {
        jest.spyOn(readMore.$content, 'scrollHeight', 'get').mockImplementation(() => 100);
        readMore.reset();
        expect(readMore.$container.classList.contains('read-more--unnecessary')).toBe(false);
        expect(readMore.$container.classList.contains('read-more--expanded')).toBe(false);
        expect(readMore.$content.style.maxHeight).toBe('40px');
    });

    test('expanded if small scroll height', () => {
        jest.spyOn(readMore.$content, 'scrollHeight', 'get').mockImplementation(() => 30);
        readMore.reset();
        expect(readMore.$container.classList.contains('read-more--unnecessary')).toBe(true);
        expect(readMore.$container.classList.contains('read-more--expanded')).toBe(true);
        expect(readMore.$content.style.maxHeight).not.toBe('40px');
    });
});

describe('initClampers', () => {
    test('clamp removed if not needed', () => {
        const clamper = document.createElement('div');
        clamper.classList.add('clamp');
        jest
            .spyOn(clamper, 'scrollHeight', 'get')
            .mockImplementation(() => 100);
        jest
            .spyOn(clamper, 'clientHeight', 'get')
            .mockImplementation(() => 100);
        initClampers([clamper]);
        expect(clamper.classList.contains('clamp')).toBe(false);

    });

    test('clamp not removed if  needed', () => {
        const clamper = document.createElement('div');
        clamper.classList.add('clamp');
        jest
            .spyOn(clamper, 'scrollHeight', 'get')
            .mockImplementation(() => 100);
        jest
            .spyOn(clamper, 'clientHeight', 'get')
            .mockImplementation(() => 10);
        initClampers([clamper]);
        expect(clamper.classList.contains('clamp')).toBe(true);

    });

    test('Clicking anchor tag does not expand', () => {
        const $clamper = $(clamperSample);
        jest
            .spyOn($clamper[0], 'scrollHeight', 'get')
            .mockImplementation(() => 100);
        jest
            .spyOn($clamper[0], 'clientHeight', 'get')
            .mockImplementation(() => 10);
        initClampers($clamper);
        $($clamper).find('a').first().trigger('click');
        expect($clamper.css('display')).toBe('unset');
    });
    test('Clicking non-anchor tag does clamp', () => {
        const $clamper = $(clamperSample);
        jest
            .spyOn($clamper[0], 'scrollHeight', 'get')
            .mockImplementation(() => 100);
        jest
            .spyOn($clamper[0], 'clientHeight', 'get')
            .mockImplementation(() => 10);
        initClampers($clamper);
        $($clamper).find('h6').first().trigger('click');
        expect($clamper.css('display')).not.toBe('unset');
    });

});
