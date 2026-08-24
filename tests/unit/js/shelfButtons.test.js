/**
 * Unit tests for the page-level owner of `<ol-shelf-button>` state.
 *
 * The buttons are stateless by contract, so without this module a shelf change
 * is written to the server and then dropped on the floor: the label keeps
 * showing whatever the server rendered. These tests pin that, plus the two
 * things that only work because the state is applied centrally — duplicate
 * cards for one work staying in step, and the finish date the popover shows.
 */
import { initShelfButtons } from '../../../openlibrary/plugins/openlibrary/js/my-books/shelf-buttons';

/** A stand-in for the upgraded element: the module only sets properties. */
function button(workKey) {
    const el = document.createElement('ol-shelf-button');
    el.setAttribute('work-key', workKey);
    el.shelf = null;
    el.rating = null;
    document.body.appendChild(el);
    return el;
}

function change(key, shelf, rating = null) {
    document.dispatchEvent(new CustomEvent('ol-book-state-change', {
        bubbles: true, composed: true, detail: { key, shelf, rating },
    }));
}

function checkIn(key, date, eventId = 7) {
    document.dispatchEvent(new CustomEvent('ol-book-check-in', {
        bubbles: true, composed: true, detail: { key, date, eventId },
    }));
}

afterEach(() => {
    document.body.innerHTML = '';
});

describe('applying reported state', () => {
    test('a reported change lands on the button that reported it', () => {
        const el = button('/works/OL1W');
        initShelfButtons([el]);
        change('/works/OL1W', 2, 4);
        expect(el.shelf).toBe(2);
        expect(el.rating).toBe(4);
    });

    test('every button for the same work moves together', () => {
        const a = button('/works/OL1W');
        const b = button('/works/OL1W');
        initShelfButtons([a, b]);
        change('/works/OL1W', 3);
        expect([a.shelf, b.shelf]).toEqual([3, 3]);
    });

    test('other works are untouched', () => {
        const a = button('/works/OL1W');
        const b = button('/works/OL2W');
        initShelfButtons([a, b]);
        change('/works/OL1W', 1);
        expect(b.shelf).toBeNull();
    });

    test('a rollback is applied the same way as the optimistic update', () => {
        const el = button('/works/OL1W');
        initShelfButtons([el]);
        change('/works/OL1W', 1);
        change('/works/OL1W', null);
        expect(el.shelf).toBeNull();
    });
});

describe('keeping the read date in step', () => {
    test('a date saved in the popover lands on the button', () => {
        const el = button('/works/OL1W');
        initShelfButtons([el]);
        checkIn('/works/OL1W', '2026-08-22', 12);
        expect(el.readDate).toBe('2026-08-22');
        expect(el.eventId).toBe(12);
    });

    test('a date for another work is left alone', () => {
        const el = button('/works/OL1W');
        initShelfButtons([el]);
        checkIn('/works/OL2W', '2026');
        expect(el.readDate).toBeUndefined();
    });

    test('coming off a shelf clears the date, which the server deletes too', () => {
        const el = button('/works/OL1W');
        initShelfButtons([el]);
        checkIn('/works/OL1W', '2026');
        change('/works/OL1W', null);
        expect(el.readDate).toBeNull();
        expect(el.eventId).toBeNull();
    });

    test('moving between shelves leaves the date alone', () => {
        const el = button('/works/OL1W');
        initShelfButtons([el]);
        checkIn('/works/OL1W', '2026');
        change('/works/OL1W', 2);
        expect(el.readDate).toBe('2026');
    });
});
