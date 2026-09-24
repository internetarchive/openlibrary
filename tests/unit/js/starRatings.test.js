/**
 * The legacy star widget tells the page's shelf buttons about a rating, with
 * the shelf the server will have put the book on.
 */
import { announceRating } from '../../../openlibrary/plugins/openlibrary/js/star-ratings/index.js';

let seen;
const record = e => seen.push(e.detail);

beforeEach(() => {
    seen = [];
    document.addEventListener('ol-book-state-change', record);
});

afterEach(() => {
    document.removeEventListener('ol-book-state-change', record);
    document.body.innerHTML = '';
});

function button(shelf) {
    const el = document.createElement('ol-shelf-button');
    el.setAttribute('work-key', '/works/OL1W');
    el.shelf = shelf;
    document.body.appendChild(el);
}

test('rating an unshelved book moves it to Already Read', () => {
    button(null);
    announceRating('/works/OL1W', 4);
    expect(seen).toEqual([{ key: '/works/OL1W', shelf: 3, rating: 4 }]);
});

test('rating a Want to Read book moves it to Already Read', () => {
    button(1);
    announceRating('/works/OL1W', 4);
    expect(seen).toEqual([{ key: '/works/OL1W', shelf: 3, rating: 4 }]);
});

test('rating a Currently Reading book leaves its shelf alone', () => {
    button(2);
    announceRating('/works/OL1W', 4);
    expect(seen).toEqual([{ key: '/works/OL1W', shelf: 2, rating: 4 }]);
});

test('clearing a rating keeps the shelf', () => {
    button(3);
    announceRating('/works/OL1W', null);
    expect(seen).toEqual([{ key: '/works/OL1W', shelf: 3, rating: null }]);
});

test('without a work key nothing is said', () => {
    announceRating('', 4);
    expect(seen).toEqual([]);
});
