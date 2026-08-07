/**
 * @jest-environment jsdom
 */

import { initContinueReading } from '../../../openlibrary/plugins/openlibrary/js/my-books/continueReading';
import * as readingHistoryStore from '../../../openlibrary/plugins/openlibrary/js/my-books/store/readingHistory';

describe('initContinueReading', () => {
    beforeEach(() => {
        document.body.innerHTML = '';
        jest.restoreAllMocks();
    });

    test('does nothing when container is not in DOM', () => {
        const spy = jest.spyOn(readingHistoryStore, 'getHistory');
        expect(() => initContinueReading()).not.toThrow();
        expect(spy).not.toHaveBeenCalled();
    });

    test('keeps container hidden when reading history is empty', () => {
        document.body.innerHTML = `
            <div id="continue-reading-container" style="display: none;">
                <div class="continue-reading-carousel"></div>
            </div>
        `;
        jest.spyOn(readingHistoryStore, 'getHistory').mockReturnValue([]);

        initContinueReading();

        const container = document.querySelector('#continue-reading-container');
        expect(container.style.display).toBe('none');
    });

    test('populates carousel and displays container when history exists', () => {
        document.body.innerHTML = `
            <div id="continue-reading-container" style="display: none;">
                <div class="continue-reading-carousel"></div>
            </div>
        `;

        const mockItems = [
            {
                olid: 'OL123M',
                workKey: '/works/OL123W',
                title: 'Dune',
                coverId: 45678,
                ocaid: 'dune0000herb',
                authorNames: ['Frank Herbert'],
                timestamp: 1600000000000,
            },
            {
                olid: 'OL999M',
                workKey: '/works/OL999W',
                title: 'Foundation & Empire',
                coverEditionKey: 'OL999M',
                ocaid: null,
                authorNames: ['Isaac Asimov'],
                timestamp: 1500000000000,
            },
        ];

        jest.spyOn(readingHistoryStore, 'getHistory').mockReturnValue(mockItems);

        initContinueReading();

        const container = document.querySelector('#continue-reading-container');
        expect(container.style.display).toBe('block');

        const cards = container.querySelectorAll('.book.carousel__item');
        expect(cards.length).toBe(2);

        // First item checks
        const firstCard = cards[0];
        expect(firstCard.querySelector('a').getAttribute('href')).toBe('/works/OL123W');
        expect(firstCard.querySelector('img').getAttribute('src')).toBe('https://covers.openlibrary.org/b/id/45678-M.jpg');
        expect(firstCard.querySelector('img').getAttribute('title')).toBe('Dune by Frank Herbert');
        expect(firstCard.querySelector('a.cta-btn').getAttribute('href')).toBe('/borrow/ia/dune0000herb?ref=ol');

        // Second item checks
        const secondCard = cards[1];
        expect(secondCard.querySelector('img').getAttribute('src')).toBe('https://covers.openlibrary.org/b/olid/OL999M-M.jpg');
        expect(secondCard.querySelector('a.cta-btn').getAttribute('href')).toBe('/works/OL999W');
    });

    test('escapes HTML special characters in title and authors', () => {
        document.body.innerHTML = `
            <div id="continue-reading-container" style="display: none;">
                <div class="continue-reading-carousel"></div>
            </div>
        `;

        const mockItems = [
            {
                olid: 'OL1M',
                workKey: '/works/OL1W',
                title: 'Cat & Mouse <Script>',
                coverId: 100,
                ocaid: 'cat',
                authorNames: ['Author <1>', 'Author & 2'],
                timestamp: 1600000000000,
            },
        ];

        jest.spyOn(readingHistoryStore, 'getHistory').mockReturnValue(mockItems);

        initContinueReading();

        const card = document.querySelector('#continue-reading-container .book');
        expect(card.innerHTML).toContain('Cat &amp; Mouse');
        expect(card.querySelector('script')).toBeNull();
        const img = document.querySelector('#continue-reading-container img');
        expect(img.getAttribute('alt')).toBe('Cat & Mouse <Script>');
    });
});
