/**
 * Unit tests for the page-level owner of `<ol-shelf-button>` state.
 *
 * The buttons are stateless by contract, so without this module a shelf change
 * is written to the server and then dropped on the floor: the label keeps
 * showing whatever the server rendered. These tests pin that, plus the two
 * things that only work because the state is applied centrally — duplicate
 * cards for one work staying in step, and the check-in prompt following along.
 */
import { initShelfButtons } from '../../../openlibrary/plugins/openlibrary/js/my-books/shelf-buttons';

const instances = [];

jest.mock('../../../openlibrary/plugins/openlibrary/js/my-books/MyBooksDropper/CheckInComponents', () => ({
    CheckInComponents: jest.fn().mockImplementation(function() {
        this.readDate = false;
        this.initialize = jest.fn();
        this.hasReadDate = jest.fn(() => this.readDate);
        this.showCheckInPrompt = jest.fn();
        this.hideCheckInPrompt = jest.fn();
        this.hideCheckInDisplay = jest.fn();
        this.resetForm = jest.fn();
        instances.push(this);
    }),
}));

/** A stand-in for the upgraded element: the module only sets properties. */
function button(workKey) {
    const el = document.createElement('ol-shelf-button');
    el.setAttribute('work-key', workKey);
    el.shelf = null;
    el.rating = null;
    document.body.appendChild(el);
    return el;
}

function checkInContainer(olid) {
    const el = document.createElement('div');
    el.id = `check-in-container-${olid}`;
    document.body.appendChild(el);
    return el;
}

function change(key, shelf, rating = null) {
    document.dispatchEvent(new CustomEvent('ol-book-state-change', {
        bubbles: true, composed: true, detail: { key, shelf, rating },
    }));
}

afterEach(() => {
    document.body.innerHTML = '';
    instances.length = 0;
    jest.clearAllMocks();
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

describe('keeping the check-in prompt in step', () => {
    test('reaching Already Read with no date asks for one', () => {
        const el = button('/works/OL1W');
        checkInContainer('OL1W');
        initShelfButtons([el]);
        change('/works/OL1W', 3);
        expect(instances[0].showCheckInPrompt).toHaveBeenCalled();
    });

    test('reaching Already Read with a date already recorded does not', () => {
        const el = button('/works/OL1W');
        checkInContainer('OL1W');
        initShelfButtons([el]);
        instances[0].readDate = true;
        change('/works/OL1W', 3);
        expect(instances[0].showCheckInPrompt).not.toHaveBeenCalled();
    });

    test('coming off a shelf clears the prompt, the date and the form', () => {
        const el = button('/works/OL1W');
        checkInContainer('OL1W');
        initShelfButtons([el]);
        change('/works/OL1W', null);
        expect(instances[0].hideCheckInPrompt).toHaveBeenCalled();
        expect(instances[0].hideCheckInDisplay).toHaveBeenCalled();
        expect(instances[0].resetForm).toHaveBeenCalled();
    });

    test('another shelf just hides the prompt', () => {
        const el = button('/works/OL1W');
        checkInContainer('OL1W');
        initShelfButtons([el]);
        change('/works/OL1W', 2);
        expect(instances[0].hideCheckInPrompt).toHaveBeenCalled();
        expect(instances[0].hideCheckInDisplay).not.toHaveBeenCalled();
    });

    test('signed out there is no container, and state still applies', () => {
        const el = button('/works/OL1W');
        initShelfButtons([el]);
        change('/works/OL1W', 1);
        expect(instances).toHaveLength(0);
        expect(el.shelf).toBe(1);
    });
});
