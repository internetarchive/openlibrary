import { ReadMoreComponent } from '../../../openlibrary/plugins/openlibrary/js/readmore';

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
