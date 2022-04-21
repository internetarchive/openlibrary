import { initClampers, resetReadMoreButtons } from '../../../openlibrary/plugins/openlibrary/js/readmore';
import $ from 'jquery';

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
    const DUMMY_HTML = 
    `<span class='clamp' data-before='▾  ' style='display: unset;'>
        <h6>Subjects</h6>
        <a>Ghosts</a>
        <a>Monsters</a>
        <a>Vampires</a>
        <a>Witches</a> 
        <a>Challenges and Overcoming Obstacles</a> 
        <a>Magic and Supernatural</a> 
        <a>Cleverness</a>
        <a>School Life</a> 
        <a>school stories</a>     
        <a>Wizards</a>
        <a>Magic</a>
        <a>MAGIA</a> 
        <a>MAGOS</a>
        <a>Juvenile fiction</a>
        <a>Fiction</a>
        <a>NOVELAS INGLESAS</a> 
        <a>Schools</a>
        <a>orphans</a>
        <a>fantasy fiction</a> 
        <a>England in fiction</a>
      </span>`;
    test("Clicking anchor tag does not expand", () => {
        const $clamper = $(DUMMY_HTML);
        jest
            .spyOn($clamper[0], 'scrollHeight', 'get')
            .mockImplementation(() => 100);
        jest
            .spyOn($clamper[0], 'clientHeight', 'get')
            .mockImplementation(() => 10);
        initClampers($clamper);
        $($clamper).find('a').first().trigger('click');
        expect($clamper.css("display")).toBe('unset');
    });
    test("Clicking non-anchor tag does clamp", () => {
        const $clamper = $(DUMMY_HTML);
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
