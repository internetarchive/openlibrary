import { initClampers, resetReadMoreButtons } from '../../../openlibrary/plugins/openlibrary/js/readmore';
import $ from 'jquery';
import {clamperSample} from './html-test-data'

describe('resetReadMoreButtons', () => {
    const $dummyEl = $('<div class="a-parent"><div class="restricted-view"></div></div>');
    $dummyEl.appendTo(document.body);

    test('restricted view if big scroll height', () => {
        const restrictedViewEl = $dummyEl.find('.restricted-view')[0];
        jest.spyOn(restrictedViewEl, 'scrollHeight', 'get').mockImplementation(() => 100);
        resetReadMoreButtons();
        expect(restrictedViewEl.classList.contains('restricted-height')).toBe(true);
    });

    test('no restricted view if small scroll height', () => {
        const restrictedViewEl = $dummyEl.find('.restricted-view')[0];
        jest.spyOn(restrictedViewEl, 'scrollHeight', 'get').mockImplementation(() => 50);
        resetReadMoreButtons();
        expect(restrictedViewEl.classList.contains('restricted-height')).toBe(false);
        $dummyEl.remove();
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
