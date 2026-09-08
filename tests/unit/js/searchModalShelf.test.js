/**
 * Unit tests for the search modal's row shelf buttons: state is fetched on
 * intent, not with the search; one batch covers the rows; it is cached across
 * queries; and changes made anywhere on the page reach the same map.
 *
 * Exercised on a SearchModal instance, the way searchModalFacets.test.js
 * does — the rendered row is covered once, at the end.
 */

import { SearchModal } from '../../../openlibrary/plugins/openlibrary/js/search-modal/SearchModal.js';

const WORKS = [
    { key: '/works/OL1W', title: 'The Two Towers', author_name: ['J. R. R. Tolkien'] },
    { key: '/works/OL2W', title: 'Dune', editions: { docs: [{ key: '/books/OL22M', title: 'Dune (1965)' }] } },
];

const STATE = {
    OL1W: { shelf: 1, rating: null, read_date: null, event_id: null },
    OL2W: { shelf: 3, rating: 4, read_date: '2026-01', event_id: 9 },
};

let calls;

function stubFetch({ ok = true, works = STATE } = {}) {
    calls = [];
    global.fetch = jest.fn(async(url) => {
        calls.push(String(url));
        return { ok, status: ok ? 200 : 500, json: async() => ({ user_key: '/people/tester', works }) };
    });
}

function makeModal({ userKey = '/people/tester', results = WORKS } = {}) {
    const modal = new SearchModal();
    modal._userKey = userKey;
    modal._results = results;
    return modal;
}

const tick = () => new Promise(r => setTimeout(r, 0));

beforeEach(() => stubFetch());

describe('fetching on intent', () => {
    test('nothing is fetched with the search itself', () => {
        makeModal();
        expect(calls).toHaveLength(0);
    });

    test('the first intent fetches every row in one batch', async() => {
        const modal = makeModal();
        modal._onShelfIntent();
        await tick();
        expect(calls).toHaveLength(1);
        expect(calls[0]).toContain('ReadingState');
        expect(decodeURIComponent(calls[0])).toContain('work_ids=OL1W,OL2W');
        expect(modal._readingState.get('OL2W')).toEqual(STATE.OL2W);
    });

    test('a second intent, or the same rows again, never refetches', async() => {
        const modal = makeModal();
        modal._onShelfIntent();
        await tick();
        modal._onShelfIntent();
        await modal._loadShelfState();
        expect(calls).toHaveLength(1);
    });

    test('signed out, intent fetches nothing', async() => {
        const modal = makeModal({ userKey: '' });
        modal._onShelfIntent();
        await tick();
        expect(calls).toHaveLength(0);
    });

    test('once wanted, a new result set is fetched for its unknown rows only', async() => {
        const modal = makeModal();
        modal._onShelfIntent();
        await tick();
        modal._results = [WORKS[1], { key: '/works/OL3W', title: 'Emma' }];
        await modal._loadShelfState();
        expect(calls).toHaveLength(2);
        expect(decodeURIComponent(calls[1])).toContain('work_ids=OL3W');
    });

    test('a failed batch is retried on the next intent', async() => {
        stubFetch({ ok: false });
        const modal = makeModal();
        modal._onShelfIntent();
        await tick();
        expect(modal._readingState.size).toBe(0);
        stubFetch();
        await modal._loadShelfState();
        expect(calls).toHaveLength(1);
        expect(modal._readingState.size).toBe(2);
    });

    test('closing the modal forgets the intent but keeps the state', async() => {
        const modal = makeModal();
        modal._onShelfIntent();
        await tick();
        modal._onDialogClosed();
        expect(modal._shelfStateWanted).toBe(false);
        expect(modal._readingState.size).toBe(2);
    });
});

describe('changes made elsewhere', () => {
    function attached() {
        const modal = makeModal();
        document.body.appendChild(modal);
        return modal;
    }

    afterEach(() => {
        document.body.innerHTML = '';
    });

    test('a shelf change on the page updates a known book', async() => {
        const modal = attached();
        modal._onShelfIntent();
        await tick();
        document.dispatchEvent(new CustomEvent('ol-book-state-change', { detail: { key: '/works/OL1W', shelf: null, rating: 2 } }));
        expect(modal._readingState.get('OL1W')).toEqual({ shelf: null, rating: 2, read_date: null, event_id: null });
    });

    test('coming off a shelf drops the check-in with it', async() => {
        const modal = attached();
        modal._onShelfIntent();
        await tick();
        document.dispatchEvent(new CustomEvent('ol-book-state-change', { detail: { key: '/works/OL2W', shelf: null, rating: 4 } }));
        expect(modal._readingState.get('OL2W').read_date).toBeNull();
        expect(modal._readingState.get('OL2W').event_id).toBeNull();
    });

    test('a check-in lands on the book', async() => {
        const modal = attached();
        modal._onShelfIntent();
        await tick();
        document.dispatchEvent(new CustomEvent('ol-book-check-in', { detail: { key: '/works/OL1W', date: '2026-09', eventId: 12 } }));
        expect(modal._readingState.get('OL1W')).toMatchObject({ read_date: '2026-09', event_id: 12 });
    });

    // A partial picture would let the popover open on the shelf but not the
    // date; leaving it unknown means the next intent fetches it whole.
    test('an unknown book stays unknown', () => {
        const modal = attached();
        document.dispatchEvent(new CustomEvent('ol-book-state-change', { detail: { key: '/works/OL1W', shelf: 1, rating: null } }));
        expect(modal._readingState.has('OL1W')).toBe(false);
    });

    test('stops listening once detached', async() => {
        const modal = attached();
        modal._onShelfIntent();
        await tick();
        modal.remove();
        document.dispatchEvent(new CustomEvent('ol-book-state-change', { detail: { key: '/works/OL1W', shelf: null, rating: null } }));
        expect(modal._readingState.get('OL1W').shelf).toBe(1);
    });
});

describe('the rendered row', () => {
    afterEach(() => {
        document.body.innerHTML = '';
    });

    async function rendered(overrides) {
        const modal = makeModal(overrides);
        modal._query = 'tolkien';
        modal._hasSearched = true;
        document.body.appendChild(modal);
        await modal.updateComplete;
        return modal;
    }

    test('each row has a button beside the link, not inside it', async() => {
        const modal = await rendered();
        const rows = modal.renderRoot.querySelectorAll('.results-list .result-row');
        expect(rows).toHaveLength(2);
        const button = rows[0].querySelector('ol-shelf-button');
        expect(button.closest('a')).toBeNull();
        expect(button.getAttribute('variant')).toBe('outline');
        expect(button.getAttribute('work-key')).toBe('/works/OL1W');
        expect(button.getAttribute('user-key')).toBe('/people/tester');
    });

    test('acts on the work even when the row links to an edition, and records the edition', async() => {
        const modal = await rendered();
        const button = modal.renderRoot.querySelectorAll('.results-list ol-shelf-button')[1];
        expect(button.getAttribute('work-key')).toBe('/works/OL2W');
        expect(button.getAttribute('edition-key')).toBe('OL22M');
        expect(modal.renderRoot.querySelectorAll('.results-list ol-shelf-button')[0].hasAttribute('edition-key')).toBe(false);
    });

    test('signed in, a row is pending until its state is known, then carries it', async() => {
        const modal = await rendered();
        const button = () => modal.renderRoot.querySelectorAll('.results-list ol-shelf-button')[1];
        expect(button().hasAttribute('pending')).toBe(true);
        expect(button().shelf).toBeNull();
        modal._onShelfIntent();
        await tick();
        await modal.updateComplete;
        expect(button().hasAttribute('pending')).toBe(false);
        expect(button().shelf).toBe(3);
        expect(button().rating).toBe(4);
        expect(button().readDate).toBe('2026-01');
        expect(button().eventId).toBe(9);
    });

    test('signed out, nothing is pending: the click goes to login', async() => {
        const modal = await rendered({ userKey: '' });
        const button = modal.renderRoot.querySelector('.results-list ol-shelf-button');
        expect(button.hasAttribute('pending')).toBe(false);
        expect(button.getAttribute('user-key')).toBe('');
    });
});
